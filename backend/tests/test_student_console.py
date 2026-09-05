"""Focused Student console tests (C-ST-01 … C-ST-20).

They cover the caller-is-the-scope fence (a student resolves everything
through their own active enrollment, so no identifier in the URL can leak
another student's row) and the state machines that guard the high-risk
flows: exam attempts, result visibility, leave applications, late
submissions and fee accounts.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.models.lms import LeaveStatus
from app.models.principal import AttemptStatus, ExamStatus
from app.models.user import User
from app.schemas.student import StudentLeaveCreate, StudentSubmissionCreate
from app.services.student_service import StudentService


class Result:
    def __init__(self, scalar=None, rows=None, row=None):
        self._scalar = scalar
        self._rows = rows or []
        self._row = row

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar

    def one(self):
        return self._row

    def one_or_none(self):
        return self._row

    def first(self):
        return self._row

    def all(self):
        return self._rows

    def scalars(self):
        return MagicMock(all=lambda: self._rows)


class FakeDB:
    def __init__(self, results):
        self.results = list(results)
        self.queries = []
        self.added = []
        self.execute = AsyncMock(side_effect=self._pop)

    async def _pop(self, statement):
        statement.compile(dialect=postgresql.dialect())
        self.queries.append(statement)
        if not self.results:
            raise AssertionError("Unexpected database query")
        return self.results.pop(0)

    async def flush(self):
        pass

    async def delete(self, value):
        pass

    def add(self, value):
        self.added.append(value)


def student(tenant_id: uuid.UUID | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        name="Aryan Sharma",
        email="aryan@example.edu",
        is_active=True,
    )


def context_row(tenant_id: uuid.UUID, student_id: uuid.UUID):
    enrollment = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        student_id=student_id,
        class_id=uuid.uuid4(),
        academic_year_id=uuid.uuid4(),
        roll_number="CS-01",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
    )
    school_class = SimpleNamespace(
        id=enrollment.class_id,
        name="CSE Sem 3",
        department_id=uuid.uuid4(),
        class_teacher_id=None,
    )
    department = SimpleNamespace(id=school_class.department_id, name="Computer Science")
    academic_year = SimpleNamespace(id=enrollment.academic_year_id, name="2026-27", is_current=True)
    return enrollment, school_class, department, academic_year


def exam(exam_id: uuid.UUID | None = None, **overrides):
    now = datetime.now(timezone.utc)
    data = SimpleNamespace(
        id=exam_id or uuid.uuid4(),
        tenant_id=None,
        title="Unit Test 1",
        mode="ONLINE",
        status=ExamStatus.PUBLISHED,
        scheduled_at=now - timedelta(minutes=10),
        window_end_at=None,
        duration_minutes=60,
        total_marks=50,
        passing_marks=20,
        allow_review=False,
        show_score_immediately=False,
        shuffle_questions=False,
    )
    for key, value in overrides.items():
        setattr(data, key, value)
    return data


async def test_student_context_fails_closed_without_enrollment():
    db = FakeDB([Result(row=None)])
    with pytest.raises(HTTPException) as raised:
        await StudentService.context_for_user(db, student())
    assert raised.value.status_code == 403
    assert "No active enrollment" in raised.value.detail


async def test_student_context_rejects_inactive_enrollment():
    actor = student()
    enrollment, school_class, department, academic_year = context_row(actor.tenant_id, actor.id)
    enrollment.status = "WITHDRAWN"
    db = FakeDB([Result(row=(enrollment, school_class, department, academic_year))])
    with pytest.raises(HTTPException) as raised:
        await StudentService.context_for_user(db, actor)
    assert raised.value.status_code == 403
    assert "no longer active" in raised.value.detail


async def test_leave_apply_rejects_overlapping_request():
    actor = student()
    db = FakeDB([
        Result(row=context_row(actor.tenant_id, actor.id)),
        Result(scalar=uuid.uuid4()),  # overlapping leave exists
    ])
    payload = StudentLeaveCreate(
        from_date=date(2026, 8, 10),
        to_date=date(2026, 8, 12),
        reason="Family function at home",
    )
    with pytest.raises(HTTPException) as raised:
        await StudentService.apply_leave(db, actor, payload)
    assert raised.value.status_code == 409
    assert "already covers" in raised.value.detail


async def test_cancel_leave_requires_pending_status():
    actor = student()
    leave = SimpleNamespace(id=uuid.uuid4(), status=LeaveStatus.APPROVED)
    db = FakeDB([Result(scalar=leave)])
    with pytest.raises(HTTPException) as raised:
        await StudentService.cancel_leave(db, actor, leave.id)
    assert raised.value.status_code == 409
    assert len(db.queries) == 1


async def test_start_attempt_rejects_offline_exam():
    actor = student()
    target = exam(mode="OFFLINE")
    db = FakeDB([
        Result(row=context_row(actor.tenant_id, actor.id)),
        Result(row=(target, SimpleNamespace(id=uuid.uuid4(), code="CS101", name="Data Structures"))),
    ])
    with pytest.raises(HTTPException) as raised:
        await StudentService.start_attempt(db, actor, target.id)
    assert raised.value.status_code == 409
    assert "offline exam" in raised.value.detail


async def test_start_attempt_rejects_exam_before_window():
    actor = student()
    target = exam(scheduled_at=datetime.now(timezone.utc) + timedelta(days=1))
    db = FakeDB([
        Result(row=context_row(actor.tenant_id, actor.id)),
        Result(row=(target, SimpleNamespace(id=uuid.uuid4(), code="CS101", name="Data Structures"))),
    ])
    with pytest.raises(HTTPException) as raised:
        await StudentService.start_attempt(db, actor, target.id)
    assert raised.value.status_code == 409
    assert "not started yet" in raised.value.detail


async def test_submit_attempt_rejects_a_second_submission():
    actor = student()
    target = exam(status=ExamStatus.ONGOING)
    attempt = SimpleNamespace(
        id=uuid.uuid4(), exam_id=target.id, status=AttemptStatus.SUBMITTED,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    db = FakeDB([
        Result(row=context_row(actor.tenant_id, actor.id)),
        Result(row=(target, SimpleNamespace(id=uuid.uuid4(), code="CS101", name="Data Structures"))),
        Result(scalar=attempt),
    ])
    with pytest.raises(HTTPException) as raised:
        await StudentService.submit_attempt(db, actor, target.id)
    assert raised.value.status_code == 409
    assert "already submitted" in raised.value.detail


async def test_tab_switch_increments_only_for_a_live_attempt():
    actor = student()
    target = exam(status=ExamStatus.ONGOING)
    attempt = SimpleNamespace(
        id=uuid.uuid4(), exam_id=target.id, status=AttemptStatus.IN_PROGRESS,
        tab_switch_count=1,
    )
    db = FakeDB([
        Result(row=context_row(actor.tenant_id, actor.id)),
        Result(row=(target, SimpleNamespace(id=uuid.uuid4(), code="CS101", name="Data Structures"))),
        Result(scalar=attempt),
    ])
    result = await StudentService.record_tab_switch(db, actor, target.id)
    assert result.tab_switch_count == 2
    assert attempt.tab_switch_count == 2


async def test_tab_switch_reports_frozen_count_once_submitted():
    actor = student()
    target = exam(status=ExamStatus.COMPLETED)
    attempt = SimpleNamespace(
        id=uuid.uuid4(), exam_id=target.id, status=AttemptStatus.SUBMITTED,
        tab_switch_count=3,
    )
    db = FakeDB([
        Result(row=context_row(actor.tenant_id, actor.id)),
        Result(row=(target, SimpleNamespace(id=uuid.uuid4(), code="CS101", name="Data Structures"))),
        Result(scalar=attempt),
    ])
    result = await StudentService.record_tab_switch(db, actor, target.id)
    assert result.tab_switch_count == 3
    assert attempt.tab_switch_count == 3


async def test_exam_result_stays_hidden_until_release():
    actor = student()
    target = exam(status=ExamStatus.COMPLETED, show_score_immediately=False)
    attempt = SimpleNamespace(
        id=uuid.uuid4(), exam_id=target.id, status=AttemptStatus.SUBMITTED,
        total_score=Decimal("42"), submitted_at=datetime.now(timezone.utc),
    )
    db = FakeDB([
        Result(row=context_row(actor.tenant_id, actor.id)),
        Result(row=(target, SimpleNamespace(id=uuid.uuid4(), code="CS101", name="Data Structures"))),
        Result(scalar=attempt),
    ])
    result = await StudentService.exam_result(db, actor, target.id)
    # Typed state instead of a prose 404: the UI renders "results under
    # evaluation" and no score/answer data is exposed yet.
    assert result.result_state == "UNDER_EVALUATION"
    assert result.total_score is None
    assert result.answers == []
    assert result.submitted_at == attempt.submitted_at


async def test_assignment_submit_rejects_past_due_without_late_allowed():
    actor = student()
    assignment = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        status="PUBLISHED",
        due_date=datetime.now(timezone.utc) - timedelta(days=2),
        allow_late_submission=False,
    )
    db = FakeDB([
        Result(row=context_row(actor.tenant_id, actor.id)),
        Result(row=(assignment,)),
    ])
    with pytest.raises(HTTPException) as raised:
        await StudentService.submit_assignment(db, actor, assignment.id, StudentSubmissionCreate(text_response="done"))
    assert raised.value.status_code == 409
    assert "late submissions are not allowed" in raised.value.detail


async def test_notice_read_hides_notices_for_other_classes():
    actor = student()
    enrollment, school_class, department, academic_year = context_row(actor.tenant_id, actor.id)
    notice = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        target_scope="CLASS",
        target_id=uuid.uuid4(),  # another class — not the student's
        title="Section B only",
        deleted_at=None,
    )
    db = FakeDB([
        Result(row=(enrollment, school_class, department, academic_year)),
        Result(scalar=0),     # visible notice count
        Result(rows=[]),      # visible notice rows
        Result(scalar=0),     # unread count
        Result(row=(notice, "Principal")),
    ])
    with pytest.raises(HTTPException) as raised:
        await StudentService.mark_notice_read(db, actor, notice.id)
    assert raised.value.status_code == 404


async def test_fees_without_an_account_is_not_found():
    actor = student()
    db = FakeDB([
        Result(row=context_row(actor.tenant_id, actor.id)),
        Result(scalar=None),  # no fee account
    ])
    with pytest.raises(HTTPException) as raised:
        await StudentService.fees(db, actor)
    assert raised.value.status_code == 404
    assert "No fee account" in raised.value.detail


async def test_student_guard_rejects_non_student_role():
    from app.dependencies.auth import get_current_tenant_user_student

    db = FakeDB([Result(scalar=None)])
    with pytest.raises(HTTPException) as raised:
        await get_current_tenant_user_student(student(), db)
    assert raised.value.status_code == 403


def test_student_router_exposes_the_documented_workflows():
    from app.routers.student import router

    paths = {route.path for route in router.routes}
    for expected in (
        "/student/dashboard",
        "/student/profile",
        "/student/attendance",
        "/student/attendance/calendar",
        "/student/attendance/leaves",
        "/student/attendance/leaves/{leave_id}/cancel",
        "/student/timetable",
        "/student/examinations",
        "/student/examinations/{exam_id}",
        "/student/examinations/{exam_id}/attempt",
        "/student/examinations/{exam_id}/attempt/paper",
        "/student/examinations/{exam_id}/attempt/answers",
        "/student/examinations/{exam_id}/attempt/tab-switch",
        "/student/examinations/{exam_id}/attempt/submit",
        "/student/examinations/{exam_id}/result",
        "/student/assignments",
        "/student/assignments/{assignment_id}",
        "/student/assignments/{assignment_id}/submit",
        "/student/content",
        "/student/content/{content_id}",
        "/student/results",
        "/student/results/{publication_id}",
        "/student/results/{publication_id}/grade-card",
        "/student/notices",
        "/student/notices/{notice_id}/read",
        "/student/discussion",
        "/student/discussion/scopes",
        "/student/discussion/{thread_id}",
        "/student/discussion/{thread_id}/replies",
        "/student/discussion/vote",
        "/student/fees",
    ):
        assert expected in paths, expected


@pytest.mark.parametrize(
    "path,method,json",
    [
        ("/api/v1/student/dashboard", "get", None),
        ("/api/v1/student/profile", "get", None),
        ("/api/v1/student/attendance", "get", None),
        ("/api/v1/student/attendance/leaves", "get", None),
        ("/api/v1/student/timetable", "get", None),
        ("/api/v1/student/examinations", "get", None),
        (f"/api/v1/student/examinations/{uuid.uuid4()}/attempt", "post", None),
        ("/api/v1/student/assignments", "get", None),
        (f"/api/v1/student/assignments/{uuid.uuid4()}/submit", "post", {"text_response": "done"}),
        ("/api/v1/student/content", "get", None),
        ("/api/v1/student/results", "get", None),
        ("/api/v1/student/notices", "get", None),
        ("/api/v1/student/discussion", "get", None),
        ("/api/v1/student/fees", "get", None),
    ],
)
async def test_student_routes_require_bearer_token(client, path, method, json):
    response = await client.request(method.upper(), path, json=json)
    assert response.status_code == 401
