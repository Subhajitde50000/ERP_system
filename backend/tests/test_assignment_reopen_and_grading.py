"""Regression tests for the two production defects fixed in this change set.

B1 — close → reopen → resubmit: reopening a closed assignment must hand
un-reviewed submissions back to students (RESUBMIT_REQUESTED) so the work
reappears in their pending list, and must never touch reviewed submissions.

B2 — grading context: the attempt payload must carry the full answer key
(every option, which is correct) plus MATCH pairings, not just the bare
selected/correct pair, so the grading panel can render a readable review.

Both are verified end-to-end against a real PostgreSQL in the E2E script
(see doc/bugfix-b1-b2.md); these unit tests pin the service contracts.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update

from app.models.hod import AssignmentStatus, SubmissionStatus
from app.schemas.teacher import TeacherAssignmentReopen
from app.services.teacher_service import TeacherService
from app.services import teacher_service as teacher_service_module

# Reuse the FakeDB harness from the teacher-console suite instead of copying it.
from tests.test_teacher_console import FakeDB, Result, teacher


def closed_assignment(actor):
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        teacher_id=actor.id,
        subject_id=uuid.uuid4(),
        class_id=uuid.uuid4(),
        title="Newton's laws worksheet",
        assignment_type="REGULAR",
        total_marks=20,
        passing_marks=8,
        due_date=datetime(2026, 9, 10, tzinfo=timezone.utc),
        description="Solve all problems.",
        allow_late_submission=False,
        late_penalty_percent=0,
        max_file_size_mb=10,
        allowed_file_types=["pdf"],
        min_group_size=2,
        max_group_size=6,
        instructions_url=None,
        status=AssignmentStatus.CLOSED,
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def detail_results(assignment, *, stats=(1, 1, 0), roster=1):
    """Query results assignment_detail() consumes after the transition."""
    subject = SimpleNamespace(id=assignment.subject_id, code="PHY", name="Physics")
    school_class = SimpleNamespace(id=assignment.class_id, name="Class X-A")
    year = SimpleNamespace(id=uuid.uuid4())
    return [
        Result(scalar=assignment),                                    # _owned_assignment
        Result(row=(subject, school_class)),                          # subject + class meta
        Result(rows=[(assignment.id, *stats)]),                       # _assignment_stats
        Result(scalar=year),                                          # _current_year
        Result(rows=[(assignment.class_id, roster)]),                 # roster counts
        Result(rows=[]),                                              # group counts
        Result(rows=[]),                                              # milestones
    ]


@pytest.fixture
def quiet_notifications(monkeypatch):
    """Keep the best-effort student nudge out of the DB-query sequence."""
    mock = AsyncMock(return_value=[])
    monkeypatch.setattr(teacher_service_module.PushService, "create_in_app_notifications", mock)
    return mock


async def test_reopen_hands_unreviewed_submissions_back_to_students(quiet_notifications):
    actor = teacher()
    assignment = closed_assignment(actor)
    student_id = uuid.uuid4()
    submission_id = uuid.uuid4()
    db = FakeDB(
        [
            Result(scalar=assignment),                                  # _owned_assignment (transition)
            Result(rows=[(submission_id, student_id)]),                 # UPDATE ... RETURNING
            *detail_results(assignment),                                # assignment_detail
        ]
    )

    detail = await TeacherService.transition_assignment(db, actor, assignment.id, "reopen")

    assert detail.status == "PUBLISHED"
    # The one extra write is the bulk reopen of un-reviewed submissions.
    update_stmt = next(q for q in db.queries if isinstance(q, Update))
    compiled = update_stmt.compile(dialect=postgresql.dialect())
    assert "status" in compiled.params or "submission_status" in str(update_stmt)
    assert compiled.params["status"] == SubmissionStatus.RESUBMIT_REQUESTED
    # Every affected student is nudged exactly once.
    quiet_notifications.assert_awaited_once()
    kwargs = quiet_notifications.await_args.kwargs
    assert kwargs["user_ids"] == [student_id]
    assert kwargs["notif_type"] == "ASSIGNMENT_REOPENED"


async def test_reopen_without_resubmission_skips_the_submission_update(quiet_notifications):
    actor = teacher()
    assignment = closed_assignment(actor)
    db = FakeDB(
        [
            Result(scalar=assignment),                                  # _owned_assignment (transition)
            *detail_results(assignment),                                # assignment_detail — nothing else
        ]
    )

    detail = await TeacherService.transition_assignment(
        db, actor, assignment.id, "reopen", request_resubmission=False
    )

    assert detail.status == "PUBLISHED"
    assert not any(isinstance(q, Update) for q in db.queries)
    quiet_notifications.assert_not_awaited()


async def test_reopen_rejects_assignments_that_are_not_closed():
    actor = teacher()
    assignment = closed_assignment(actor)
    assignment.status = AssignmentStatus.PUBLISHED
    db = FakeDB([Result(scalar=assignment)])
    with pytest.raises(HTTPException) as raised:
        await TeacherService.transition_assignment(db, actor, assignment.id, "reopen")
    assert raised.value.status_code == 409
    assert "Only closed assignments can be reopened" in raised.value.detail


async def test_reopen_schema_defaults_to_requesting_resubmission():
    """The router body is optional; omitted means the loop-friendly default."""
    assert TeacherAssignmentReopen().request_resubmission is True
    assert TeacherAssignmentReopen(request_resubmission=False).request_resubmission is False


# ── B2: grading context ──────────────────────────────────────────────────────


async def test_attempt_detail_returns_the_full_answer_key_and_match_pairs():
    actor = teacher()
    exam = SimpleNamespace(id=uuid.uuid4(), tenant_id=actor.tenant_id, created_by=actor.id)
    attempt = SimpleNamespace(
        id=uuid.uuid4(),
        status="SUBMITTED",
        started_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
        submitted_at=datetime(2026, 9, 4, 10, 25, tzinfo=timezone.utc),
        total_score=Decimal("2"),
        percentage=None,
        grade=None,
        tab_switch_count=0,
    )
    student = SimpleNamespace(id=uuid.uuid4(), name="Ada L", student_roll_no="101")

    correct_option = SimpleNamespace(
        id=uuid.uuid4(), question_id=uuid.uuid4(), text="Newton", is_correct=True, sort_order=1
    )
    wrong_option = SimpleNamespace(
        id=uuid.uuid4(), question_id=correct_option.question_id, text="Joule", is_correct=False, sort_order=2
    )
    match_question_id = uuid.uuid4()

    mcq = SimpleNamespace(
        id=uuid.uuid4(),
        selected_option_id=wrong_option.id,
        text_answer=None,
        matched_pairs=None,
        score=Decimal("0"),
        feedback=None,
        is_auto_graded=True,
    )
    mcq_question = SimpleNamespace(
        id=correct_option.question_id, text="SI unit of force?", question_type="MCQ", marks=Decimal("2")
    )
    match = SimpleNamespace(
        id=uuid.uuid4(),
        selected_option_id=None,
        text_answer=None,
        matched_pairs={"Newton": "N", "Joule": "J"},
        score=None,
        feedback=None,
        is_auto_graded=False,
    )
    match_question = SimpleNamespace(
        id=match_question_id, text="Match unit to symbol", question_type="MATCH", marks=Decimal("2")
    )

    db = FakeDB(
        [
            Result(scalar=exam),                                   # _owned_exam
            Result(row=(attempt, student)),                        # attempt + student
            Result(rows=[(mcq, mcq_question), (match, match_question)]),  # answers + questions
            Result(rows=[correct_option, wrong_option]),           # question options (full key)
            Result(rows=[(attempt.id, 1)]),                        # pending grading counts
        ]
    )

    detail = await TeacherService.attempt_detail(db, actor, exam.id, attempt.id)

    assert [a.question_type for a in detail.answers] == ["MCQ", "MATCH"]

    mcq_row = detail.answers[0]
    assert mcq_row.selected_option_text == "Joule"
    assert mcq_row.correct_option_text == "Newton"
    assert [(o.text, o.is_correct) for o in mcq_row.options] == [("Newton", True), ("Joule", False)]

    match_row = detail.answers[1]
    assert match_row.matched_pairs == {"Newton": "N", "Joule": "J"}
    assert match_row.options == []
    assert detail.pending_grading_count == 1
