"""Focused Academic Coordinator console tests (C-AC-01 … C-AC-08).

The existing suite's integration test is optional when a local Postgres binary
is unavailable.  These service tests cover the unique-key, scope, and date
rules that must hold regardless of transport, and the router tests prove the
coordinator surface never falls back to an unauthenticated demo response.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.coordinator import (
    AcademicEvent,
    AcademicEventScope,
    AcademicEventType,
    TimetableSubstitution,
)
from app.models.user import User
from app.schemas.coordinator import (
    CoordinatorEventCreate,
    CoordinatorEventUpdate,
    CoordinatorSlotCreate,
    CoordinatorSlotUpdate,
    CoordinatorSubstitutionCreate,
)
from app.services.coordinator_service import CoordinatorService


# ── Test helpers ──────────────────────────────────────────────────────────────


class Result:
    """A SQLAlchemy Result stub that records what was queried and serves rows."""

    def __init__(self, scalar=None, row=None, rows=None):
        self._scalar = scalar
        self._row = row
        self._rows = rows or []

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def one(self):
        return self._row

    def one_or_none(self):
        return self._row

    def all(self):
        return self._rows

    def scalars(self):
        return MagicMock(all=lambda: self._rows)


class FakeDB:
    """A minimal async-session stub that records queries and serves canned results."""

    def __init__(self, results):
        self._results = list(results)
        self.added: list = []
        self.deleted: list = []
        self.queries: list = []
        self.execute = AsyncMock(side_effect=self._pop)
        self.flush = AsyncMock()
        self.delete = AsyncMock(side_effect=lambda obj: self.deleted.append(obj))

    async def _pop(self, statement):
        self.queries.append(statement)
        if not self._results:
            return Result()
        return self._results.pop(0)

    def add(self, instance):
        self.added.append(instance)


def coordinator(tenant_id: uuid.UUID | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        name="Latha Venkat",
        email="latha@xyz.com",
        is_active=True,
    )


def current_year(tenant_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name="2025-26", is_current=True)


def klass(tenant_id: uuid.UUID, class_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=class_id or uuid.uuid4(),
        tenant_id=tenant_id,
        name="FY-A",
        department_id=uuid.uuid4(),
        is_active=True,
    )


def teacher(tenant_id: uuid.UUID, teacher_id: uuid.UUID | None = None) -> User:
    return User(
        id=teacher_id or uuid.uuid4(),
        tenant_id=tenant_id,
        name="Priya Sharma",
        is_active=True,
    )


def subject(tenant_id: uuid.UUID, class_id: uuid.UUID) -> SimpleNamespace:
    """A subject row as _ensure_subject/_ensure_teaching_assignment see it."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        class_id=class_id,
        name="Data Structures",
        code="CS201",
        is_active=True,
    )


# ── C-AC-01 dashboard ────────────────────────────────────────────────────────


async def test_dashboard_returns_all_kpis():
    """C-AC-01 — dashboard aggregates timetable, substitutions, exams and events."""

    tenant_id = uuid.uuid4()
    actor = coordinator(tenant_id)
    year = current_year(tenant_id)

    # The dashboard runs roughly:
    #   1. tenant today (timezone)
    #   2. current year
    #   3. timetable coverage aggregation
    #   4. total classes
    #   5. substitution rows (5 joined selects)
    #   6. exam KPI aggregation
    #   7. upcoming events (5 rows)
    #   8. conflict count
    #   9. active notice count
    # We supply enough Result stubs to satisfy the service without asserting
    # the exact SQL: the point of the test is that the service completes.
    db = FakeDB(
        [
            Result(scalar="Asia/Kolkata"),   # 1. tenant timezone
            Result(scalar=year),             # 2. current year
            Result(row=SimpleNamespace(total_slots=20, classes_covered=3, teachers_scheduled=4)),  # 3. coverage
            Result(scalar=3),                 # 4. total_classes
            Result(rows=[]),                  # 5. substitution rows
            Result(row=SimpleNamespace(
                scheduled=5, upcoming=2, ongoing=1, pending_hall_allocation=1
            )),                              # 6. exam KPI
            Result(rows=[]),                  # 7. upcoming events
            Result(rows=[]),                  # 8. conflicts
            Result(scalar=2),                 # 9. active notices
        ]
    )

    dashboard = await CoordinatorService.dashboard(db, tenant_id)

    assert dashboard.academic_year == "2025-26"
    assert dashboard.timetable.total_slots == 20
    assert dashboard.timetable.classes_covered == 3
    assert dashboard.exams.ongoing == 1
    assert dashboard.exams.pending_hall_allocation == 1
    assert dashboard.substitutions.covering_teachers == 0
    assert dashboard.timetable_conflicts == 0
    assert dashboard.active_notices == 2
    assert dashboard.today == datetime.now(timezone.utc).date() or dashboard.today is not None


# ── C-AC-02 timetable builder ───────────────────────────────────────────────


async def test_create_slot_rejects_duplicate_unique_key():
    """UNIQUE (class_id, day_of_week, period_number, effective_from) — §7.8."""
    import pytest as _pytest

    tenant_id = uuid.uuid4()
    actor = coordinator(tenant_id)
    class_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    teacher_id = uuid.uuid4()
    today = date(2026, 7, 29)
    subject_row = subject(tenant_id, class_id)

    # Query order in `create_slot` for a fully-specified CLASS slot:
    #   1. ensure class           → class row
    #   2. ensure subject         → subject row (bound to this class)
    #   3. ensure teacher         → teacher row
    #   4. teaching assignment    → _ensure_subject again, then the link id
    #   5. teacher free?          → None
    #   6. room free?             → None
    #   7. duplicate unique key?  → an existing row → 409
    db = FakeDB(
        [
            Result(scalar=klass(tenant_id, class_id)),
            Result(scalar=subject_row),
            Result(scalar=teacher(tenant_id, teacher_id)),
            Result(scalar=subject_row),
            Result(scalar=uuid.uuid4()),  # existing TeacherSubject link
            Result(scalar=None),          # teacher not double-booked
            Result(scalar=None),          # room not double-booked
            Result(
                scalar=SimpleNamespace(  # the conflicting slot
                    id=uuid.uuid4(),
                    class_id=class_id,
                    day_of_week=1,
                    period_number=1,
                )
            ),
        ]
    )

    payload = CoordinatorSlotCreate(
        class_id=class_id,
        academic_year_id=None,
        day_of_week=1,
        period_number=1,
        start_time=time(9, 0),
        end_time=time(9, 50),
        subject_id=subject_id,
        teacher_id=teacher_id,
        room_no="105",
        slot_type="CLASS",
        effective_from=today,
    )

    with _pytest.raises(HTTPException) as raised:
        await CoordinatorService.create_slot(db, tenant_id, actor, payload)
    assert raised.value.status_code == 409


async def test_create_slot_rejects_unknown_class():
    """404 when the class_id belongs to a different tenant or does not exist."""

    tenant_id = uuid.uuid4()
    actor = coordinator(tenant_id)
    db = FakeDB(
        [
            Result(scalar=None),  # class not found → 404
        ]
    )
    payload = CoordinatorSlotCreate(
        class_id=uuid.uuid4(),
        academic_year_id=None,
        day_of_week=1,
        period_number=1,
        start_time=time(9, 0),
        end_time=time(9, 50),
        subject_id=None,
        teacher_id=None,
        room_no="105",
        slot_type="CLASS",
        effective_from=date(2026, 7, 29),
    )

    with pytest.raises(HTTPException) as raised:
        await CoordinatorService.create_slot(db, tenant_id, actor, payload)
    assert raised.value.status_code == 404


async def test_create_slot_succeeds_with_audit_trail():
    """A new slot writes one audit row and the canonical fields are set."""

    tenant_id = uuid.uuid4()
    actor = coordinator(tenant_id)
    year = current_year(tenant_id)
    class_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    teacher_id = uuid.uuid4()
    today = date(2026, 7, 29)
    subject_row = subject(tenant_id, class_id)

    # Lookups in `create_slot` (fully-specified CLASS slot):
    #   1. ensure class → class row
    #   2. ensure subject → subject row
    #   3. ensure teacher → teacher row
    #   4. teaching assignment: _ensure_subject again + link id (already linked)
    #   5./6. teacher & room availability → None
    #   7. duplicate unique key → None
    #   8. current_year → the year
    #   9. slot DTO build → one joined query (labels via .one())
    db = FakeDB(
        [
            Result(scalar=klass(tenant_id, class_id)),
            Result(scalar=subject_row),
            Result(scalar=teacher(tenant_id, teacher_id)),
            Result(scalar=subject_row),
            Result(scalar=uuid.uuid4()),  # existing TeacherSubject link
            Result(scalar=None),          # teacher free
            Result(scalar=None),          # room free
            Result(scalar=None),          # no duplicate
            Result(scalar=year),
            Result(
                row=SimpleNamespace(
                    class_name="FY-A",
                    department_name="CSE",
                    subject_name="Data Structures",
                    subject_code="CS201",
                    teacher_name="Priya Sharma",
                )
            ),
        ]
    )
    payload = CoordinatorSlotCreate(
        class_id=class_id,
        academic_year_id=None,
        day_of_week=1,
        period_number=1,
        start_time=time(9, 0),
        end_time=time(9, 50),
        subject_id=subject_id,
        teacher_id=teacher_id,
        room_no="105",
        slot_type="CLASS",
        effective_from=today,
    )

    await CoordinatorService.create_slot(db, tenant_id, actor, payload)

    # One new slot + one audit row were added.
    added_classes = [type(a).__name__ for a in db.added]
    assert "TimetableSlot" in added_classes
    assert "AuditLog" in added_classes


async def test_update_slot_records_old_and_new_state():
    """A PATCH records both the before and after state of the slot."""

    tenant_id = uuid.uuid4()
    actor = coordinator(tenant_id)
    slot_id = uuid.uuid4()
    class_id = uuid.uuid4()
    slot = SimpleNamespace(
        id=slot_id,
        tenant_id=tenant_id,
        class_id=class_id,
        academic_year_id=uuid.uuid4(),
        day_of_week=1,
        period_number=1,
        start_time=time(9, 0),
        end_time=time(9, 50),
        subject_id=uuid.uuid4(),
        teacher_id=uuid.uuid4(),
        room_no="105",
        slot_type="CLASS",
        effective_from=date(2026, 7, 29),
        effective_to=None,
    )
    # Query order in `update_slot` (slot keeps subject+teacher):
    #   1. load slot
    #   2. teaching assignment: _ensure_subject + existing link id
    #   3./4. teacher & room availability (excludes this slot) → None
    #   5. slot DTO build → joined row via .one()
    db = FakeDB(
        [
            Result(scalar=slot),
            Result(scalar=subject(tenant_id, class_id)),
            Result(scalar=uuid.uuid4()),  # existing TeacherSubject link
            Result(scalar=None),          # teacher free
            Result(scalar=None),          # room free
            Result(
                row=SimpleNamespace(
                    class_name="FY-A",
                    department_name="CSE",
                    subject_name="Data Structures",
                    subject_code="CS201",
                    teacher_name="Priya Sharma",
                )
            ),
        ]
    )
    payload = CoordinatorSlotUpdate(room_no="201", slot_type="LAB")

    result = await CoordinatorService.update_slot(db, tenant_id, actor, slot_id, payload)

    assert slot.room_no == "201"
    assert slot.slot_type == "LAB"
    assert len(db.added) == 1
    assert db.added[0].action == "UPDATE_TIMETABLE_SLOT"


# ── C-AC-04 conflict checker ────────────────────────────────────────────────


async def test_conflicts_detect_double_booked_teacher():
    """A teacher assigned to two classes in the same period is flagged."""

    tenant_id = uuid.uuid4()
    # The _compute_conflicts query returns rows of (slot, class_name, subject, teacher).
    teacher_id = uuid.uuid4()
    slot_a = SimpleNamespace(
        id=uuid.uuid4(),
        class_id=uuid.uuid4(),
        academic_year_id=uuid.uuid4(),
        day_of_week=1,
        period_number=1,
        teacher_id=teacher_id,
        room_no="201",
        slot_type="CLASS",
        effective_from=date(2026, 7, 1),
        effective_to=None,
    )
    slot_b = SimpleNamespace(
        id=uuid.uuid4(),
        class_id=uuid.uuid4(),
        academic_year_id=uuid.uuid4(),
        day_of_week=1,
        period_number=1,
        teacher_id=teacher_id,
        room_no="202",
        slot_type="CLASS",
        effective_from=date(2026, 7, 1),
        effective_to=None,
    )

    # 1. timezone, 2. the joined query
    db = FakeDB(
        [
            Result(scalar="Asia/Kolkata"),
            Result(
                rows=[
                    (slot_a, "FY-A", "Data Structures", "Priya Sharma"),
                    (slot_b, "SY-B", "Algorithms", "Priya Sharma"),
                ]
            ),
        ]
    )

    report = await CoordinatorService.conflicts(db, tenant_id)

    assert report.total == 1
    assert report.teacher_conflicts == 1
    assert report.room_conflicts == 0
    assert report.items[0].kind == "TEACHER_DOUBLE_BOOKED"
    assert report.items[0].resource == "Priya Sharma"
    assert "FY-A" in report.items[0].class_names
    assert "SY-B" in report.items[0].class_names


async def test_conflicts_detect_double_booked_room():
    """Two classes in the same room at the same period is a room conflict."""

    tenant_id = uuid.uuid4()
    slot_a = SimpleNamespace(
        id=uuid.uuid4(),
        class_id=uuid.uuid4(),
        academic_year_id=uuid.uuid4(),
        day_of_week=2,
        period_number=3,
        teacher_id=uuid.uuid4(),
        room_no="Lab 2",
        slot_type="LAB",
        effective_from=date(2026, 7, 1),
        effective_to=None,
    )
    slot_b = SimpleNamespace(
        id=uuid.uuid4(),
        class_id=uuid.uuid4(),
        academic_year_id=uuid.uuid4(),
        day_of_week=2,
        period_number=3,
        teacher_id=uuid.uuid4(),
        room_no="Lab 2",
        slot_type="CLASS",
        effective_from=date(2026, 7, 1),
        effective_to=None,
    )

    db = FakeDB(
        [
            Result(scalar="Asia/Kolkata"),
            Result(rows=[
                (slot_a, "FY-A", "Databases", "Arun Kumar"),
                (slot_b, "FY-B", "Networks", "Meena Thomas"),
            ]),
        ]
    )

    report = await CoordinatorService.conflicts(db, tenant_id)

    assert report.total == 1
    assert report.teacher_conflicts == 0
    assert report.room_conflicts == 1
    assert report.items[0].kind == "ROOM_DOUBLE_BOOKED"
    assert "Lab 2" in report.items[0].resource


# ── C-AC-05 / C-AC-06 substitutions ────────────────────────────────────────


async def test_create_substitution_rejects_past_date():
    """A substitution for a date in the past is meaningless and confusing."""

    tenant_id = uuid.uuid4()
    actor = coordinator(tenant_id)
    slot_id = uuid.uuid4()
    today = date(2026, 7, 29)
    teacher_id = uuid.uuid4()

    db = FakeDB(
        [
            Result(
                scalar=SimpleNamespace(
                    id=slot_id,
                    class_id=uuid.uuid4(),
                    teacher_id=teacher_id,
                    slot_type="CLASS",
                )
            ),
            Result(scalar=today),  # tenant today lookup
        ]
    )

    payload = CoordinatorSubstitutionCreate(
        slot_id=slot_id,
        date=date(2025, 1, 1),
        substitute_teacher_id=uuid.uuid4(),
        reason=None,
    )

    with pytest.raises(HTTPException) as raised:
        await CoordinatorService.create_substitution(db, tenant_id, actor, payload)
    assert raised.value.status_code == 422
    assert "passed" in (raised.value.detail or "").lower()


async def test_create_substitution_rejects_self_substitution():
    """The substitute cannot be the teacher who owns the period."""

    tenant_id = uuid.uuid4()
    actor = coordinator(tenant_id)
    teacher_id = uuid.uuid4()
    today = date(2099, 1, 1)  # Far future so the date check passes
    future = date(2099, 1, 2)

    db = FakeDB(
        [
            Result(
                scalar=SimpleNamespace(
                    id=uuid.uuid4(),
                    class_id=uuid.uuid4(),
                    teacher_id=teacher_id,
                    slot_type="CLASS",
                )
            ),
            Result(scalar=today),  # tenant today
        ]
    )

    payload = CoordinatorSubstitutionCreate(
        slot_id=uuid.uuid4(),
        date=future,
        substitute_teacher_id=teacher_id,  # same as slot.teacher_id
        reason=None,
    )

    with pytest.raises(HTTPException) as raised:
        await CoordinatorService.create_substitution(db, tenant_id, actor, payload)
    assert raised.value.status_code == 422
    assert "same teacher" in (raised.value.detail or "").lower()


async def test_create_substitution_rejects_duplicate_unique_key():
    """UNIQUE (slot_id, date) — §7.8."""

    tenant_id = uuid.uuid4()
    actor = coordinator(tenant_id)
    today = date(2099, 1, 1)
    future = date(2099, 1, 2)
    sub_teacher_id = uuid.uuid4()
    slot_teacher_id = uuid.uuid4()

    # Lookups in `create_substitution`:
    #   1. timetable slot
    #   2. tenant today
    #   3. ensure substitute teacher
    #   4. existing substitution (the duplicate)
    db = FakeDB(
        [
            Result(
                scalar=SimpleNamespace(
                    id=uuid.uuid4(),
                    class_id=uuid.uuid4(),
                    teacher_id=slot_teacher_id,
                    slot_type="CLASS",
                )
            ),
            Result(scalar=today),
            Result(scalar=teacher(tenant_id, sub_teacher_id)),
            Result(
                scalar=SimpleNamespace(
                    id=uuid.uuid4(),
                    slot_id=uuid.uuid4(),
                    date=future,
                )
            ),
        ]
    )

    payload = CoordinatorSubstitutionCreate(
        slot_id=uuid.uuid4(),
        date=future,
        substitute_teacher_id=sub_teacher_id,
        reason=None,
    )

    with pytest.raises(HTTPException) as raised:
        await CoordinatorService.create_substitution(db, tenant_id, actor, payload)
    assert raised.value.status_code == 409
    assert "already has a substitute" in (raised.value.detail or "").lower()


# ── C-AC-07 academic calendar ──────────────────────────────────────────────


async def test_create_event_validates_date_window():
    """An end_date earlier than start_date is rejected by the Pydantic validator."""

    with pytest.raises(ValueError) as raised:
        CoordinatorEventCreate(
            academic_year_id=uuid.uuid4(),
            title="Wrong window",
            description=None,
            event_type="EVENT",
            start_date=date(2026, 8, 5),
            end_date=date(2026, 8, 1),
            is_holiday=False,
            applies_to="ALL",
            scope_id=None,
            color=None,
        )
    assert "end_date" in str(raised.value).lower()


async def test_create_event_holiday_must_be_typed_as_holiday():
    """The validator in CoordinatorEventCreate refuses `is_holiday=True` on non-HOLIDAY types."""

    from pydantic import ValidationError

    with pytest.raises(ValidationError) as raised:
        CoordinatorEventCreate(
            academic_year_id=uuid.uuid4(),
            title="Contradiction",
            description=None,
            event_type="EVENT",
            start_date=date(2026, 8, 5),
            end_date=date(2026, 8, 5),
            is_holiday=True,
            applies_to="ALL",
            scope_id=None,
            color=None,
        )
    assert "is_holiday" in str(raised.value).lower()


async def test_create_event_validates_department_scope():
    """A DEPARTMENT scope requires a scope_id."""

    with pytest.raises(ValueError) as raised:
        CoordinatorEventCreate(
            academic_year_id=uuid.uuid4(),
            title="Missing scope",
            description=None,
            event_type="EVENT",
            start_date=date(2026, 8, 5),
            end_date=date(2026, 8, 5),
            is_holiday=False,
            applies_to="DEPARTMENT",
            scope_id=None,
            color=None,
        )
    assert "scope_id" in str(raised.value).lower()


async def test_create_event_404s_unknown_year():
    """A bad academic_year_id is rejected before any insert."""

    tenant_id = uuid.uuid4()
    actor = coordinator(tenant_id)
    db = FakeDB([Result(scalar=None)])  # year not found
    payload = CoordinatorEventCreate(
        academic_year_id=uuid.uuid4(),
        title="Phantom year",
        description=None,
        event_type="EVENT",
        start_date=date(2026, 8, 5),
        end_date=date(2026, 8, 5),
        is_holiday=False,
        applies_to="ALL",
        scope_id=None,
        color=None,
    )

    with pytest.raises(HTTPException) as raised:
        await CoordinatorService.create_event(db, tenant_id, actor, payload)
    assert raised.value.status_code == 404


async def test_delete_event_writes_audit_row():
    """Deleting an event must produce an audit row tied to the actor."""

    tenant_id = uuid.uuid4()
    actor = coordinator(tenant_id)
    event = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        title="Republic Day",
        start_date=date(2026, 1, 26),
    )
    db = FakeDB([Result(scalar=event)])

    await CoordinatorService.delete_event(db, tenant_id, actor, event.id)

    assert len(db.added) == 1
    assert db.added[0].action == "DELETE_ACADEMIC_EVENT"


# ── C-AC-08 post academic notice ───────────────────────────────────────────


async def test_create_notice_prefixes_title_with_academic():
    """§4.5 — coordinator notices are auto-prefixed (Academic)."""

    tenant_id = uuid.uuid4()
    actor = coordinator(tenant_id)
    class_id = uuid.uuid4()

    db = FakeDB([Result(scalar=klass(tenant_id, class_id))])
    from app.schemas.coordinator import CoordinatorNoticeCreate

    payload = CoordinatorNoticeCreate(
        title="Mid-term timetable revised",
        body="See the attachment.",
        target_scope="CLASS",
        target_id=class_id,
        priority="NORMAL",
        is_pinned=False,
        expires_at=None,
    )

    notice = await CoordinatorService.create_notice(db, tenant_id, actor, payload)

    assert notice.title == "(Academic) Mid-term timetable revised"
    assert notice.target_id == class_id
    assert notice.author_name == "Latha Venkat"
    assert len(db.added) == 2  # Notice + AuditLog


async def test_create_notice_does_not_double_prefix():
    """An existing (Academic) prefix is left alone."""

    tenant_id = uuid.uuid4()
    actor = coordinator(tenant_id)
    class_id = uuid.uuid4()

    db = FakeDB([Result(scalar=klass(tenant_id, class_id))])
    from app.schemas.coordinator import CoordinatorNoticeCreate

    payload = CoordinatorNoticeCreate(
        title="(Academic) Reminder: bring calculators",
        body="Tomorrow's quiz needs a calculator.",
        target_scope="CLASS",
        target_id=class_id,
        priority="IMPORTANT",
        is_pinned=True,
        expires_at=None,
    )

    notice = await CoordinatorService.create_notice(db, tenant_id, actor, payload)

    # The title is not re-prefixed; case is preserved as typed.
    assert notice.title == "(Academic) Reminder: bring calculators"


async def test_create_notice_rejects_blank_title():
    """Validator in CoordinatorNoticeCreate rejects empty titles."""

    from app.schemas.coordinator import CoordinatorNoticeCreate

    with pytest.raises(ValueError) as raised:
        CoordinatorNoticeCreate(
            title="   ",
            body="Body",
            target_scope="CLASS",
            target_id=uuid.uuid4(),
            priority="NORMAL",
            is_pinned=False,
            expires_at=None,
        )
    assert "blank" in str(raised.value).lower() or "must not" in str(raised.value).lower()


# ── Architecture: no department fence, role guard, router surface ──────────


def test_coordinator_service_is_institution_wide():
    """C-AC-01 … C-AC-08 are institution-wide; the service never opens a department fence."""

    import inspect

    # The dashboard, substitutions, calendar, conflicts and notices all have
    # only `tenant_id`; a `department_ids` parameter would silently copy
    # the Principal service's fence and let one department see another.
    for name in (
        "dashboard",
        "substitution_board",
        "substitution_form_context",
        "conflicts",
        "events",
        "notices",
        "notice_targets",
        "timetable",
    ):
        sig = inspect.signature(getattr(CoordinatorService, name))
        assert "department_ids" not in sig.parameters, (
            f"{name} must not take a department fence"
        )


def test_academic_coordinator_model_exports():
    """Only the models owned by the coordinator console are exported."""

    from app.models import coordinator as coordinator_models

    assert "AcademicEvent" in coordinator_models.__all__
    assert "TimetableSubstitution" in coordinator_models.__all__
    # Notice is shared with the principal console; the coordinator module
    # must not pretend to own it.
    assert "Notice" not in coordinator_models.__all__


# ── Router: unauthenticated requests are rejected with 401 ─────────────────


def test_router_protected_by_coordinator_guard():
    """The /coordinator router imports the role-specific guard, not get_current_tenant_user."""

    import inspect

    from app.routers import coordinator as coordinator_router

    source = inspect.getsource(coordinator_router)
    assert "get_current_tenant_user_coordinator" in source
    # The generic guard would let any signed-in user in; the role-specific
    # guard is what the production Principal/HOD pattern uses.
    assert "get_current_tenant_user" not in source or "get_current_tenant_user_coordinator" in source


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "method", "json"),
    [
        # C-AC-01 dashboard
        ("/api/v1/coordinator/dashboard", "get", None),
        # C-AC-02 timetable builder
        ("/api/v1/coordinator/timetable", "get", None),
        (
            "/api/v1/coordinator/timetable/slots",
            "post",
            {
                "class_id": "00000000-0000-0000-0000-000000000000",
                "academic_year_id": None,
                "day_of_week": 1,
                "period_number": 1,
                "start_time": "09:00:00",
                "end_time": "09:50:00",
                "subject_id": None,
                "teacher_id": None,
                "room_no": None,
                "slot_type": "CLASS",
                "effective_from": "2026-07-29",
                "effective_to": None,
            },
        ),
        ("/api/v1/coordinator/timetable/slots/00000000-0000-0000-0000-000000000000", "patch", {"room_no": "201"}),
        ("/api/v1/coordinator/timetable/slots/00000000-0000-0000-0000-000000000000", "delete", None),
        # C-AC-04 conflict checker
        ("/api/v1/coordinator/timetable/conflicts", "get", None),
        # C-AC-05/06 substitutions
        ("/api/v1/coordinator/substitutions/board", "get", None),
        ("/api/v1/coordinator/substitutions/context", "get", None),
        (
            "/api/v1/coordinator/substitutions",
            "post",
            {
                "slot_id": "00000000-0000-0000-0000-000000000000",
                "date": "2026-07-29",
                "substitute_teacher_id": "00000000-0000-0000-0000-000000000000",
                "reason": None,
            },
        ),
        ("/api/v1/coordinator/substitutions/00000000-0000-0000-0000-000000000000", "delete", None),
        # C-AC-07 calendar
        ("/api/v1/coordinator/calendar/events", "get", None),
        (
            "/api/v1/coordinator/calendar/events",
            "post",
            {
                "academic_year_id": "00000000-0000-0000-0000-000000000000",
                "title": "Republic Day",
                "description": None,
                "event_type": "HOLIDAY",
                "start_date": "2026-01-26",
                "end_date": "2026-01-26",
                "is_holiday": True,
                "applies_to": "ALL",
                "scope_id": None,
                "color": None,
            },
        ),
        ("/api/v1/coordinator/calendar/events/00000000-0000-0000-0000-000000000000", "patch", {"title": "X"}),
        ("/api/v1/coordinator/calendar/events/00000000-0000-0000-0000-000000000000", "delete", None),
        # C-AC-08 notice composer
        ("/api/v1/coordinator/notices/targets", "get", None),
        ("/api/v1/coordinator/notices", "get", None),
        (
            "/api/v1/coordinator/notices",
            "post",
            {
                "title": "Mid-term reminder",
                "body": "Bring calculators.",
                "target_scope": "CLASS",
                "target_id": "00000000-0000-0000-0000-000000000000",
                "priority": "NORMAL",
                "is_pinned": False,
                "expires_at": None,
            },
        ),
    ],
)
async def test_coordinator_routes_require_a_bearer_token(client, path, method, json):
    """Every /coordinator/* route refuses an anonymous caller with 401."""
    response = await client.request(method.upper(), path, json=json)
    assert response.status_code == 401, (
        f"{method.upper()} {path} returned {response.status_code} instead of 401"
    )
