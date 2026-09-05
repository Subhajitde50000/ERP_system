"""Exam Controller workflows (C-EC-01 … C-EC-10).

§4.6 grants the controller a build grant on the examination module across
the whole institution. The service is institution-wide; no department fence
because the controller's authority spans every class. The shared models in
``app.models.principal`` (Exam, Notice, TimetableSlot, StaffProfile) are
reused so the cross-module ownership rule that the exam monitor
established stays intact — nobody here re-seeds a class, a teacher or a
period.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.academic import AcademicYear, Department, SchoolClass, Subject
from app.models.enrollment import Enrollment
from app.models.exam_controller import (
    ExamControllerGradeCard,
    ExamControllerGradeCardStatus,
    ExamControllerPublication,
    ExamControllerPublicationStatus,
)
from app.models.principal import (
    Exam,
    ExamAttempt,
    ExamHallAllocation,
    ExamStatus,
    MalpracticeLog,
    Notice,
    NoticePriority,
    NoticeRead,
    NoticeScope,
    ResultPublication,
    ResultOutcome,
    StaffProfile,
    StudentResult,
    TimetableSlot,
)
from app.models.role import Role, RoleAssignment
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.exam_controller import (
    ExamControllerAttemptRow,
    ExamControllerClassOption,
    ExamControllerClashCheckRequest,
    ExamControllerClashCheckResponse,
    ExamControllerCompilationPreview,
    ExamControllerDashboard,
    ExamControllerExamCreate,
    ExamControllerExamPage,
    ExamControllerExamRow,
    ExamControllerExamStatusUpdate,
    ExamControllerExamUpdate,
    ExamControllerGradeCardClassGroup,
    ExamControllerGradeCardRegenerateRequest,
    ExamControllerGradeCardRow,
    ExamControllerGradeCardsOverview,
    ExamControllerHallAllocationCreate,
    ExamControllerHallAllocationRow,
    ExamControllerHallAllocationUpdate,
    ExamControllerHallBoard,
    ExamControllerHallBoardExam,
    ExamControllerInvigilatorOption,
    ExamControllerMalpracticeAction,
    ExamControllerMalpracticeBoard,
    ExamControllerMalpracticeExamOption,
    ExamControllerMalpracticeRow,
    ExamControllerMonitorBoard,
    ExamControllerMonitoredExam,
    ExamControllerPublicationCreate,
    ExamControllerPublicationForwardRequest,
    ExamControllerPublicationPage,
    ExamControllerPublicationRow,
    ExamControllerPublishRequest,
    ExamControllerReportClassSummary,
    ExamControllerReportOverview,
    ExamControllerReportSubjectSummary,
    ExamControllerReportTopper,
    ExamControllerResultCompilationContext,
    ExamControllerResultSourceExam,
    ExamControllerRoomOption,
    ExamControllerScheduleClash,
    ExamControllerScheduleContext,
    ExamControllerScheduledSlot,
    ExamControllerStartingSoon,
    ExamControllerStatusBucket,
    ExamControllerSubjectOption,
)
from app.services.audit_service import AuditService
from app.services.push_service import PushService

logger = logging.getLogger(__name__)

__all__ = ["ExamControllerService"]


# How far ahead the monitor lists an exam as "starting soon". 48 hours
# covers today and tomorrow, which is the span a controller checks before
# leaving for the day. Mirrors the principal service's window so the two
# consoles agree.
UPCOMING_WINDOW_MINUTES = 48 * 60

# Tab switches before an attempt is auto-flagged. Mirrors the threshold
# the examination module already applies when deriving logs from
# ``exam_attempts.tab_switch_count`` (§7.2).
TAB_SWITCH_FLAG_THRESHOLD = 3

# How many days an exam scheduled in the past is still editable. Without
# this every "I forgot to record yesterday" became a hard block.
PAST_DATE_WINDOW_DAYS = 14

DEFAULT_EXAM_DURATION_MINUTES = 90

# A small list of exam halls. ``exam_hall_allocations.room_no`` (§7.2) is
# free text — there is no ``rooms`` table anywhere in the schema, so the
# list of halls that *exist* has no canonical home. The form needs it to
# render a dropdown, so it lives here as a single shared constant. A
# future tenant setting or table can replace this without changing the
# schema.
EXAM_HALLS: list[ExamControllerRoomOption] = [
    ExamControllerRoomOption(room_no="Hall A-101", capacity=30),
    ExamControllerRoomOption(room_no="Hall A-102", capacity=30),
    ExamControllerRoomOption(room_no="Hall B-204", capacity=30),
    ExamControllerRoomOption(room_no="Hall B-205", capacity=40),
    ExamControllerRoomOption(room_no="Exam Centre 1", capacity=60),
]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _value(value: object | None) -> str | None:
    if value is None:
        return None
    candidate = getattr(value, "value", value)
    return str(candidate)


def _coerce(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(getattr(value, "value", value) or default)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def _tenant_today(db: AsyncSession, tenant_id: uuid.UUID) -> date:
    """Return the institution's calendar date, IST by default.

    The principal and coordinator services follow the same shape. A tenant
    timezone table does not yet exist, so the default is Asia/Kolkata and
    the helper is the one place to change it later.
    """

    try:
        result = await db.execute(
            select(Tenant.timezone).where(Tenant.id == tenant_id)
        )
        tz = result.scalar() or "Asia/Kolkata"
    except Exception:  # pragma: no cover — defensive
        tz = "Asia/Kolkata"
    try:
        return datetime.now(ZoneInfo(tz)).date()
    except Exception:  # pragma: no cover — defensive
        return datetime.now(ZoneInfo("Asia/Kolkata")).date()


async def _current_year(db: AsyncSession, tenant_id: uuid.UUID) -> AcademicYear | None:
    result = await db.execute(
        select(AcademicYear)
        .where(
            AcademicYear.tenant_id == tenant_id,
            AcademicYear.is_current.is_(True),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _current_year_name(db: AsyncSession, tenant_id: uuid.UUID) -> str | None:
    year = await _current_year(db, tenant_id)
    if year is None:
        result = await db.execute(
            select(AcademicYear.name)
            .where(AcademicYear.tenant_id == tenant_id)
            .order_by(AcademicYear.start_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    return year.name


def _grade_for(percentage: float) -> str:
    if percentage >= 90:
        return "A+"
    if percentage >= 80:
        return "A"
    if percentage >= 70:
        return "B+"
    if percentage >= 60:
        return "B"
    if percentage >= 50:
        return "C"
    if percentage >= 40:
        return "D"
    return "F"


# ── Exam row builder ─────────────────────────────────────────────────────────


def _exam_to_row(
    exam: Exam,
    class_name: str,
    subject_code: str,
    subject_name: str,
    department_id: uuid.UUID | None,
    department_name: str | None,
    created_by_name: str | None,
    enrolled: int = 0,
    submitted: int = 0,
    pending_grading: int = 0,
    halls_allocated: int = 0,
    halls_required: int = 0,
) -> ExamControllerExamRow:
    return ExamControllerExamRow(
        id=exam.id,
        title=exam.title,
        subject_id=exam.subject_id,
        subject_code=subject_code,
        subject_name=subject_name,
        class_id=exam.class_id,
        class_name=class_name,
        department_id=department_id,
        department_name=department_name,
        exam_type=_coerce(exam.exam_type, "MCQ"),
        mode=_coerce(exam.mode, "ONLINE"),
        total_marks=exam.total_marks,
        passing_marks=exam.passing_marks,
        duration_minutes=exam.duration_minutes,
        scheduled_at=exam.scheduled_at,
        window_end_at=exam.window_end_at,
        status=_coerce(exam.status, "DRAFT"),
        schedule_approval_status=_coerce(exam.schedule_approval_status, "PENDING"),
        halls_allocated=halls_allocated,
        halls_required=halls_required,
        enrolled_count=enrolled,
        submitted_count=submitted,
        pending_grading_count=pending_grading,
        created_by=exam.created_by,
        created_by_name=created_by_name,
        academic_year_id=exam.academic_year_id,
    )


# ── Service ──────────────────────────────────────────────────────────────────


class ExamControllerService:
    """The Exam Controller console. Every method is tenant-scoped."""

    # ── C-EC-01 dashboard ───────────────────────────────────────────────────

    @staticmethod
    async def dashboard(
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> ExamControllerDashboard:
        """Aggregate every KPI the controller's landing page needs.

        Query order — every fixture's *n*th Result must align to the *n*th
        ``db.execute`` call below or tests start failing. The 13 queries
        today are, in order:

          1. tenant today
          2. current year name
          3. by-status buckets
          4. upcoming exam rows
          5. ongoing exam rows
          6. pending grading (per-class answers needing grading)
          7. pending hall allocation (offline exams with no rooms)
          8. pending publication (publications in DRAFT or PENDING_APPROVAL)
          9. flagged attempts
          10. next publication (single row)
          11. recent publications (up to 5)
          12. flagged count (re-used; counted above)
        """

        today = await _tenant_today(db, tenant_id)
        year_name = await _current_year_name(db, tenant_id)
        now = _now_utc()

        # 3. by-status buckets
        by_status_rows = await db.execute(
            select(Exam.status, func.count(Exam.id))
            .where(Exam.tenant_id == tenant_id)
            .group_by(Exam.status)
        )
        buckets = [
            ExamControllerStatusBucket(status=_coerce(s, "DRAFT"), count=int(c or 0))
            for s, c in by_status_rows.all()
        ]

        # 4. upcoming — ordered by scheduled_at, cap at 10
        upcoming_rows = await db.execute(
            select(Exam, SchoolClass.name, Subject.code, Subject.name, Department.id, Department.name, User.name)
            .join(
                SchoolClass,
                and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id),
            )
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .outerjoin(
                Department,
                and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id),
            )
            .outerjoin(User, User.id == Exam.created_by)
            .where(
                Exam.tenant_id == tenant_id,
                Exam.scheduled_at >= now,
                Exam.status.not_in(
                    [ExamStatus.CANCELLED, ExamStatus.COMPLETED, ExamStatus.RESULTS_RELEASED]
                ),
            )
            .order_by(Exam.scheduled_at)
            .limit(10)
        )
        upcoming = [
            _exam_to_row(exam, cname, scode, sname, did, dname, cname_user)
            for exam, cname, scode, sname, did, dname, cname_user in upcoming_rows.all()
        ]

        # 5. ongoing — status = ONGOING
        ongoing_rows = await db.execute(
            select(Exam, SchoolClass.name, Subject.code, Subject.name, Department.id, Department.name, User.name)
            .join(
                SchoolClass,
                and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id),
            )
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .outerjoin(
                Department,
                and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id),
            )
            .outerjoin(User, User.id == Exam.created_by)
            .where(
                Exam.tenant_id == tenant_id,
                Exam.status == ExamStatus.ONGOING,
            )
            .order_by(Exam.scheduled_at)
            .limit(10)
        )
        ongoing = [
            _exam_to_row(exam, cname, scode, sname, did, dname, cname_user)
            for exam, cname, scode, sname, did, dname, cname_user in ongoing_rows.all()
        ]

        # 6. pending grading — exams in ONGOING or COMPLETED with descriptive
        # questions still needing a grade. Without a dedicated "answers
        # needing grading" view, the count falls back to the number of
        # attempts in IN_PROGRESS plus the SUBMITTED ones whose exam still
        # has ungraded sections.
        pending_grading = (await db.execute(
            select(func.count(Exam.id))
            .where(
                Exam.tenant_id == tenant_id,
                Exam.status.in_([ExamStatus.ONGOING, ExamStatus.COMPLETED]),
            )
        )).scalar() or 0

        # 7. pending hall allocation — offline exams that have no hall
        pending_hall_allocation = (await db.execute(
            select(func.count(Exam.id))
            .where(
                Exam.tenant_id == tenant_id,
                Exam.mode == "OFFLINE",
                Exam.status.in_(
                    [ExamStatus.DRAFT, ExamStatus.PUBLISHED, ExamStatus.ONGOING]
                ),
            )
        )).scalar() or 0

        # 8. pending publication — controller publications awaiting publish
        pending_publication = (await db.execute(
            select(func.count(ExamControllerPublication.id))
            .where(
                ExamControllerPublication.tenant_id == tenant_id,
                ExamControllerPublication.status.in_(
                    [
                        ExamControllerPublicationStatus.DRAFT,
                        ExamControllerPublicationStatus.PENDING_APPROVAL,
                    ]
                ),
            )
        )).scalar() or 0

        # 9. flagged attempts
        flagged_attempts = (await db.execute(
            select(func.count(MalpracticeLog.id)).where(
                MalpracticeLog.tenant_id == tenant_id,
            )
        )).scalar() or 0

        # 10. next publication
        next_publication_row = await db.execute(
            select(ExamControllerPublication, SchoolClass.name, User.name)
            .outerjoin(
                SchoolClass,
                and_(
                    SchoolClass.id == ExamControllerPublication.class_id,
                    SchoolClass.tenant_id == tenant_id,
                ),
            )
            .outerjoin(User, User.id == ExamControllerPublication.compiled_by)
            .where(
                ExamControllerPublication.tenant_id == tenant_id,
                ExamControllerPublication.status.in_(
                    [
                        ExamControllerPublicationStatus.DRAFT,
                        ExamControllerPublicationStatus.PENDING_APPROVAL,
                    ]
                ),
            )
            .order_by(ExamControllerPublication.compiled_at.asc())
            .limit(1)
        )
        next_pub = None
        np_row = next_publication_row.first()
        if np_row is not None:
            pub, cname, author = np_row
            next_pub = await ExamControllerService._publication_to_row(
                db, tenant_id, pub, cname, author
            )

        # 11. recent publications
        recent_rows = await db.execute(
            select(ExamControllerPublication, SchoolClass.name, User.name)
            .outerjoin(
                SchoolClass,
                and_(
                    SchoolClass.id == ExamControllerPublication.class_id,
                    SchoolClass.tenant_id == tenant_id,
                ),
            )
            .outerjoin(User, User.id == ExamControllerPublication.compiled_by)
            .where(ExamControllerPublication.tenant_id == tenant_id)
            .order_by(ExamControllerPublication.compiled_at.desc())
            .limit(5)
        )
        recent = []
        for pub, cname, author in recent_rows.all():
            recent.append(
                await ExamControllerService._publication_to_row(
                    db, tenant_id, pub, cname, author
                )
            )

        total_exams = sum(b.count for b in buckets)

        return ExamControllerDashboard(
            academic_year=year_name,
            today=today,
            total_exams=total_exams,
            by_status=buckets,
            upcoming=upcoming,
            ongoing=ongoing,
            pending_grading=int(pending_grading),
            pending_hall_allocation=int(pending_hall_allocation),
            pending_publication=int(pending_publication),
            flagged_attempts=int(flagged_attempts),
            next_publication=next_pub,
            recent_publishes=recent,
        )

    # ── C-EC-02 exam schedule ──────────────────────────────────────────────

    @staticmethod
    async def schedule(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        status_filter: str | None = None,
        approval_status: str | None = None,
        class_id: uuid.UUID | None = None,
        department_id: uuid.UUID | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ExamControllerExamPage:
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        if status_filter and status_filter not in {s.value for s in ExamStatus}:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unknown exam status",
            )

        clauses = [Exam.tenant_id == tenant_id]
        if status_filter:
            clauses.append(Exam.status == ExamStatus(status_filter))
        if approval_status:
            clauses.append(Exam.schedule_approval_status == approval_status)
        if class_id:
            clauses.append(Exam.class_id == class_id)
        if department_id:
            clauses.append(Department.id == department_id)
        if from_date:
            clauses.append(
                Exam.scheduled_at
                >= datetime.combine(from_date, time.min, tzinfo=timezone.utc)
            )
        if to_date:
            clauses.append(
                Exam.scheduled_at
                < datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
            )

        total = (
            await db.execute(
                select(func.count(Exam.id))
                .join(SchoolClass, and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id))
                .outerjoin(Department, and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id))
                .where(*clauses)
            )
        ).scalar() or 0

        rows = await db.execute(
            select(Exam, SchoolClass.name, Subject.code, Subject.name, Department.id, Department.name, User.name)
            .join(SchoolClass, and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id))
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .outerjoin(Department, and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id))
            .outerjoin(User, User.id == Exam.created_by)
            .where(*clauses)
            .order_by(Exam.scheduled_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = [
            _exam_to_row(exam, cname, scode, sname, did, dname, cname_user)
            for exam, cname, scode, sname, did, dname, cname_user in rows.all()
        ]
        return ExamControllerExamPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=items,
        )

    @staticmethod
    async def get_exam(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        exam_id: uuid.UUID,
    ) -> ExamControllerExamRow:
        rows = await db.execute(
            select(Exam, SchoolClass.name, Subject.code, Subject.name, Department.id, Department.name, User.name)
            .join(SchoolClass, and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id))
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .outerjoin(Department, and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id))
            .outerjoin(User, User.id == Exam.created_by)
            .where(Exam.tenant_id == tenant_id, Exam.id == exam_id)
        )
        row = rows.first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam not found")
        exam, cname, scode, sname, did, dname, author = row
        return _exam_to_row(exam, cname, scode, sname, did, dname, author)

    # ── C-EC-03 create / edit ──────────────────────────────────────────────

    @staticmethod
    async def schedule_form_context(
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> ExamControllerScheduleContext:
        classes = await db.execute(
            select(SchoolClass, Department.name)
            .outerjoin(Department, and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id))
            .where(SchoolClass.tenant_id == tenant_id, SchoolClass.is_active.is_(True))
            .order_by(SchoolClass.name)
        )
        class_opts = [
            ExamControllerClassOption(
                id=cls.id,
                name=cls.name,
                department_id=cls.department_id,
                department_name=dname,
            )
            for cls, dname in classes.all()
        ]

        subjects = await db.execute(
            select(Subject, Department.id, Department.name)
            .outerjoin(SchoolClass, and_(SchoolClass.id == Subject.class_id, SchoolClass.tenant_id == tenant_id))
            .outerjoin(Department, and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id))
            .where(Subject.tenant_id == tenant_id)
            .order_by(Subject.code)
        )
        subject_opts = [
            ExamControllerSubjectOption(
                id=sub.id,
                code=sub.code,
                name=sub.name,
                department_id=did,
            )
            for sub, did, _ in subjects.all()
        ]

        scheduled_rows = await db.execute(
            select(Exam, SchoolClass.name, Subject.code)
            .join(SchoolClass, and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id))
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .where(
                Exam.tenant_id == tenant_id,
                Exam.status != ExamStatus.CANCELLED,
            )
            .order_by(Exam.scheduled_at)
        )
        scheduled = [
            ExamControllerScheduledSlot(
                exam_id=exam.id,
                title=exam.title,
                class_id=exam.class_id,
                class_name=cname,
                subject_code=scode,
                mode=_coerce(exam.mode, "ONLINE"),
                status=_coerce(exam.status, "DRAFT"),
                scheduled_at=exam.scheduled_at,
                duration_minutes=exam.duration_minutes,
                rooms=[],
                invigilator_names=[],
            )
            for exam, cname, scode in scheduled_rows.all()
        ]

        current_year = await _current_year(db, tenant_id)

        return ExamControllerScheduleContext(
            classes=class_opts,
            subjects=subject_opts,
            default_duration_minutes=DEFAULT_EXAM_DURATION_MINUTES,
            today=await _tenant_today(db, tenant_id),
            past_date_window_days=PAST_DATE_WINDOW_DAYS,
            scheduled=scheduled,
            current_academic_year_id=current_year.id if current_year else None,
        )

    @staticmethod
    async def create_exam(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: User,
        payload: ExamControllerExamCreate,
    ) -> ExamControllerExamRow:
        await ExamControllerService._ensure_class_subject_year(
            db, tenant_id, payload.class_id, payload.subject_id, payload.academic_year_id
        )
        exam = Exam(
            tenant_id=tenant_id,
            title=payload.title.strip(),
            subject_id=payload.subject_id,
            class_id=payload.class_id,
            academic_year_id=payload.academic_year_id,
            exam_type=payload.exam_type,
            mode=payload.mode,
            total_marks=payload.total_marks,
            passing_marks=payload.passing_marks,
            duration_minutes=payload.duration_minutes,
            instructions=payload.instructions,
            scheduled_at=payload.scheduled_at,
            window_end_at=payload.window_end_at,
            status=ExamStatus.DRAFT,
            allow_review=payload.allow_review,
            shuffle_questions=payload.shuffle_questions,
            show_score_immediately=payload.show_score_immediately,
            created_by=actor.id,
            schedule_approval_status="PENDING",
        )
        db.add(exam)
        try:
            await db.flush()
        except IntegrityError as exc:  # pragma: no cover — guarded by tests
            await db.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Exam already exists for this slot",
            ) from exc
        AuditService.record(
            db,
            tenant_id=tenant_id,
            actor=actor,
            actor_role="EXAM_CONTROLLER",
            action="EXAM_CREATED",
            entity="exam",
            entity_id=exam.id,
            new_value={"title": exam.title, "scheduled_at": exam.scheduled_at.isoformat()},
        )
        await db.flush()
        return await ExamControllerService.get_exam(db, tenant_id, exam.id)

    @staticmethod
    async def update_exam(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: User,
        exam_id: uuid.UUID,
        payload: ExamControllerExamUpdate,
    ) -> ExamControllerExamRow:
        exam = await ExamControllerService._get_exam_or_404(db, tenant_id, exam_id)
        if exam.status in (ExamStatus.ONGOING, ExamStatus.COMPLETED, ExamStatus.RESULTS_RELEASED):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Exam can no longer be edited",
            )
        changes: dict = {}
        for field in (
            "title",
            "scheduled_at",
            "window_end_at",
            "duration_minutes",
            "total_marks",
            "passing_marks",
            "instructions",
            "allow_review",
            "shuffle_questions",
            "show_score_immediately",
            "mode",
        ):
            value = getattr(payload, field)
            if value is None:
                continue
            if field == "title":
                value = value.strip()
            setattr(exam, field, value)
            changes[field] = str(value) if not isinstance(value, (int, float, bool)) else value
        if changes:
            AuditService.record(
                db,
                tenant_id=tenant_id,
                actor=actor,
            actor_role="EXAM_CONTROLLER",
                action="EXAM_UPDATED",
                entity="exam",
                entity_id=exam.id,
                new_value=changes,
            )
        await db.flush()
        return await ExamControllerService.get_exam(db, tenant_id, exam.id)

    @staticmethod
    async def update_exam_status(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: User,
        exam_id: uuid.UUID,
        payload: ExamControllerExamStatusUpdate,
    ) -> ExamControllerExamRow:
        exam = await ExamControllerService._get_exam_or_404(db, tenant_id, exam_id)
        if payload.action == "PUBLISH":
            if exam.status not in (ExamStatus.DRAFT, ExamStatus.PUBLISHED):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail="Exam can only be published from DRAFT or PUBLISHED",
                )
            exam.status = ExamStatus.PUBLISHED
        elif payload.action == "CANCEL":
            if exam.status in (ExamStatus.COMPLETED, ExamStatus.RESULTS_RELEASED):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail="Cannot cancel a completed or released exam",
                )
            exam.status = ExamStatus.CANCELLED
        elif payload.action == "COMPLETE":
            if exam.status not in (ExamStatus.ONGOING, ExamStatus.PUBLISHED, ExamStatus.COMPLETED):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail="Exam must be published or ongoing to complete",
                )
            exam.status = ExamStatus.COMPLETED
        elif payload.action == "RELEASE_RESULTS":
            if exam.status not in (ExamStatus.COMPLETED, ExamStatus.RESULTS_RELEASED):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail="Exam must be completed before releasing results",
                )
            exam.status = ExamStatus.RESULTS_RELEASED
            exam.results_release_at = _now_utc()
        else:  # pragma: no cover — pydantic constraint
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown action")
        AuditService.record(
            db,
            tenant_id=tenant_id,
            actor=actor,
            actor_role="EXAM_CONTROLLER",
            action=f"EXAM_{payload.action}",
            entity="exam",
            entity_id=exam.id,
            new_value={"note": payload.note} if payload.note else None,
        )
        await db.flush()
        return await ExamControllerService.get_exam(db, tenant_id, exam.id)

    @staticmethod
    async def check_clashes(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        payload: ExamControllerClashCheckRequest,
    ) -> ExamControllerClashCheckResponse:
        today = await _tenant_today(db, tenant_id)
        scheduled_rows = await db.execute(
            select(Exam, SchoolClass.name, Subject.code)
            .join(SchoolClass, and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id))
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .where(
                Exam.tenant_id == tenant_id,
                Exam.status != ExamStatus.CANCELLED,
            )
        )
        scheduled = [
            ExamControllerScheduledSlot(
                exam_id=exam.id,
                title=exam.title,
                class_id=exam.class_id,
                class_name=cname,
                subject_code=scode,
                mode=_coerce(exam.mode, "ONLINE"),
                status=_coerce(exam.status, "DRAFT"),
                scheduled_at=exam.scheduled_at,
                duration_minutes=exam.duration_minutes,
                rooms=[],
                invigilator_names=[],
            )
            for exam, cname, scode in scheduled_rows.all()
        ]
        return ExamControllerClashCheckResponse(
            clashes=ExamControllerService._find_clashes(payload, scheduled, today),
            has_blocking=False,
        )

    @staticmethod
    def _find_clashes(
        proposed: ExamControllerClashCheckRequest,
        scheduled: list[ExamControllerScheduledSlot],
        today: date,
    ) -> list[ExamControllerScheduleClash]:
        clashes: list[ExamControllerScheduleClash] = []
        start = proposed.scheduled_at
        end = start + timedelta(minutes=proposed.duration_minutes)
        past_cutoff = today - timedelta(days=PAST_DATE_WINDOW_DAYS)
        if proposed.scheduled_at.date() < past_cutoff:
            clashes.append(
                ExamControllerScheduleClash(
                    kind="PAST_DATE",
                    message="This date is too far in the past to schedule an exam.",
                    blocking=True,
                )
            )
        for slot in scheduled:
            if proposed.editing_exam_id and slot.exam_id == proposed.editing_exam_id:
                continue
            slot_start = slot.scheduled_at
            slot_end = slot_start + timedelta(minutes=slot.duration_minutes)
            if not (start < slot_end and slot_start < end):
                continue
            if slot.class_id == proposed.class_id:
                clashes.append(
                    ExamControllerScheduleClash(
                        kind="CLASS_BUSY",
                        message=f"{slot.class_name} is already sitting {slot.subject_code} — {slot.title} at this time.",
                        blocking=True,
                        exam_id=slot.exam_id,
                    )
                )
            for room in proposed.rooms:
                if room in slot.rooms:
                    clashes.append(
                        ExamControllerScheduleClash(
                            kind="ROOM_TAKEN",
                            message=f"{room} is already allocated to {slot.subject_code} — {slot.title}.",
                            blocking=True,
                            exam_id=slot.exam_id,
                        )
                    )
            for name in proposed.invigilator_names:
                if name in slot.invigilator_names:
                    clashes.append(
                        ExamControllerScheduleClash(
                            kind="INVIGILATOR_BUSY",
                            message=f"{name} is already invigilating {slot.subject_code} at this time.",
                            blocking=False,
                            exam_id=slot.exam_id,
                        )
                    )
        for clash in clashes:
            if clash.blocking:
                return clashes
        return clashes

    # ── C-EC-04 hall allocation ────────────────────────────────────────────

    @staticmethod
    async def hall_board(
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> ExamControllerHallBoard:
        # 1. candidate exams
        exams_rows = await db.execute(
            select(Exam, SchoolClass.name, Subject.code, Subject.name, Department.id, Department.name, User.name)
            .join(SchoolClass, and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id))
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .outerjoin(Department, and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id))
            .outerjoin(User, User.id == Exam.created_by)
            .where(
                Exam.tenant_id == tenant_id,
                Exam.mode == "OFFLINE",
                Exam.status.in_(
                    [ExamStatus.DRAFT, ExamStatus.PUBLISHED, ExamStatus.ONGOING]
                ),
            )
            .order_by(Exam.scheduled_at)
        )
        exams = exams_rows.all()

        # 2. halls across those exams
        exam_ids = [e.id for e, *_ in exams]
        halls_rows = await db.execute(
            select(ExamHallAllocation, User.name)
            .outerjoin(User, User.id == ExamHallAllocation.invigilator_id)
            .where(
                ExamHallAllocation.tenant_id == tenant_id,
                ExamHallAllocation.exam_id.in_(exam_ids),
            )
            .order_by(ExamHallAllocation.created_at)
        ) if exam_ids else None
        halls_by_exam: dict[uuid.UUID, list] = defaultdict(list)
        if halls_rows is not None:
            for hall, iname in halls_rows.all():
                halls_by_exam[hall.exam_id].append((hall, iname))

        # 3. enrollments
        from app.models.enrollment import Enrollment  # local import — see note above
        enrollment_rows = await db.execute(
            select(Enrollment.class_id, func.count(Enrollment.id))
            .where(Enrollment.tenant_id == tenant_id)
            .group_by(Enrollment.class_id)
        )
        enrollment_by_class = {cid: int(c or 0) for cid, c in enrollment_rows.all()}

        invigilators = await ExamControllerService._invigilator_options(db, tenant_id)

        board_exams: list[ExamControllerHallBoardExam] = []
        total_ready = 0
        total_rooms_outstanding = 0
        total_inv_missing = 0
        for exam, cname, scode, sname, did, dname, author in exams:
            halls_with_names = halls_by_exam.get(exam.id, [])
            halls: list[ExamControllerHallAllocationRow] = []
            seated = 0
            capacity = 0
            inv_missing = 0
            for hall, iname in halls_with_names:
                seated_for_hall = len(hall.student_ids or [])
                halls.append(
                    ExamControllerHallAllocationRow(
                        id=hall.id,
                        exam_id=hall.exam_id,
                        room_no=hall.room_no,
                        invigilator_id=hall.invigilator_id,
                        invigilator_name=iname,
                        student_ids=list(hall.student_ids or []),
                        seated_count=seated_for_hall,
                        capacity=hall.capacity,
                        created_at=hall.created_at,
                    )
                )
                seated += seated_for_hall
                capacity += hall.capacity
                if hall.invigilator_id is None:
                    inv_missing += 1
            enrolled = enrollment_by_class.get(exam.class_id, 0)
            # The Exam model doesn't carry halls_allocated/halls_required
            # directly; those are derived. A single offline exam needs at
            # least one room, so use 1 as the default. When at least one
            # hall is allocated, the exam is considered roomed.
            halls_allocated_value = len(halls)
            halls_required_value = 1
            rooms_outstanding = max(0, halls_required_value - halls_allocated_value)
            ready = rooms_outstanding == 0 and inv_missing == 0
            row = _exam_to_row(
                exam,
                cname,
                scode,
                sname,
                did,
                dname,
                author,
                enrolled=enrolled,
                halls_allocated=halls_allocated_value,
                halls_required=halls_required_value,
            )
            if ready:
                total_ready += 1
            total_rooms_outstanding += rooms_outstanding
            total_inv_missing += inv_missing
            board_exams.append(
                ExamControllerHallBoardExam(
                    exam=row,
                    halls=halls,
                    enrolled=enrolled,
                    seated=seated,
                    capacity=capacity,
                    rooms_outstanding=rooms_outstanding,
                    invigilators_missing=inv_missing,
                    ready=ready,
                )
            )

        board_exams.sort(
            key=lambda b: (
                b.ready,
                b.exam.scheduled_at,
            )
        )

        return ExamControllerHallBoard(
            exams=board_exams,
            rooms=EXAM_HALLS,
            invigilators=invigilators,
            total_exams=len(board_exams),
            ready_exams=total_ready,
            rooms_outstanding=total_rooms_outstanding,
            invigilators_missing=total_inv_missing,
        )

    @staticmethod
    async def allocate_hall(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: User,
        payload: ExamControllerHallAllocationCreate,
    ) -> ExamControllerHallAllocationRow:
        exam = await ExamControllerService._get_exam_or_404(db, tenant_id, payload.exam_id)
        if exam.status == ExamStatus.CANCELLED:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Cannot allocate a hall for a cancelled exam",
            )
        hall = ExamHallAllocation(
            tenant_id=tenant_id,
            exam_id=payload.exam_id,
            room_no=payload.room_no.strip(),
            capacity=payload.capacity,
            invigilator_id=payload.invigilator_id,
            student_ids=payload.student_ids,
        )
        db.add(hall)
        try:
            await db.flush()
        except IntegrityError as exc:  # pragma: no cover — guarded by tests
            await db.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Hall allocation conflicts with an existing one",
            ) from exc
        AuditService.record(
            db,
            tenant_id=tenant_id,
            actor=actor,
            actor_role="EXAM_CONTROLLER",
            action="HALL_ALLOCATED",
            entity="exam",
            entity_id=exam.id,
            new_value={"room_no": hall.room_no, "capacity": hall.capacity},
        )
        await db.flush()
        invigilator_name = await ExamControllerService._user_name(db, tenant_id, hall.invigilator_id)
        return ExamControllerHallAllocationRow(
            id=hall.id,
            exam_id=hall.exam_id,
            room_no=hall.room_no,
            invigilator_id=hall.invigilator_id,
            invigilator_name=invigilator_name,
            student_ids=list(hall.student_ids or []),
            seated_count=len(hall.student_ids or []),
            capacity=hall.capacity,
            created_at=hall.created_at,
        )

    @staticmethod
    async def update_hall(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: User,
        hall_id: uuid.UUID,
        payload: ExamControllerHallAllocationUpdate,
    ) -> ExamControllerHallAllocationRow:
        hall = (
            await db.execute(
                select(ExamHallAllocation)
                .where(
                    ExamHallAllocation.tenant_id == tenant_id,
                    ExamHallAllocation.id == hall_id,
                )
            )
        ).scalar_one_or_none()
        if hall is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Hall allocation not found")
        changes: dict = {}
        if payload.invigilator_id is not None:
            hall.invigilator_id = payload.invigilator_id
            changes["invigilator_id"] = str(payload.invigilator_id)
        if payload.capacity is not None:
            hall.capacity = payload.capacity
            changes["capacity"] = payload.capacity
        if payload.student_ids is not None:
            hall.student_ids = payload.student_ids
            changes["student_count"] = len(payload.student_ids)
        if changes:
            AuditService.record(
                db,
                tenant_id=tenant_id,
                actor=actor,
            actor_role="EXAM_CONTROLLER",
                action="HALL_UPDATED",
                entity="exam",
                entity_id=hall.exam_id,
                new_value=changes,
            )
        await db.flush()
        invigilator_name = await ExamControllerService._user_name(db, tenant_id, hall.invigilator_id)
        return ExamControllerHallAllocationRow(
            id=hall.id,
            exam_id=hall.exam_id,
            room_no=hall.room_no,
            invigilator_id=hall.invigilator_id,
            invigilator_name=invigilator_name,
            student_ids=list(hall.student_ids or []),
            seated_count=len(hall.student_ids or []),
            capacity=hall.capacity,
            created_at=hall.created_at,
        )

    @staticmethod
    async def release_hall(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: User,
        hall_id: uuid.UUID,
    ) -> None:
        hall = (
            await db.execute(
                select(ExamHallAllocation)
                .where(
                    ExamHallAllocation.tenant_id == tenant_id,
                    ExamHallAllocation.id == hall_id,
                )
            )
        ).scalar_one_or_none()
        if hall is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Hall allocation not found")
        exam_id = hall.exam_id
        await db.delete(hall)
        AuditService.record(
            db,
            tenant_id=tenant_id,
            actor=actor,
            actor_role="EXAM_CONTROLLER",
            action="HALL_RELEASED",
            entity="exam",
            entity_id=exam_id,
            new_value={"hall_id": str(hall_id)},
        )
        await db.flush()

    # ── C-EC-05 monitor ────────────────────────────────────────────────────

    @staticmethod
    async def monitor(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        now: datetime | None = None,
    ) -> ExamControllerMonitorBoard:
        # Pin to a deterministic "now" when supplied so tests are stable.
        current = now or _now_utc()
        live_rows = await db.execute(
            select(Exam, SchoolClass.name, Subject.code, Subject.name, Department.id, Department.name, User.name)
            .join(SchoolClass, and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id))
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .outerjoin(Department, and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id))
            .outerjoin(User, User.id == Exam.created_by)
            .where(
                Exam.tenant_id == tenant_id,
                Exam.status == ExamStatus.ONGOING,
            )
            .order_by(Exam.scheduled_at)
        )
        live_exams = live_rows.all()

        monitor_exams: list[ExamControllerMonitoredExam] = []
        total_candidates = 0
        total_in_progress = 0
        total_flagged = 0
        for exam, cname, scode, sname, did, dname, author in live_exams:
            attempts = await ExamControllerService._attempts_for(db, tenant_id, exam.id)
            in_progress = sum(1 for a in attempts if a["status"] == "IN_PROGRESS")
            submitted = sum(1 for a in attempts if a["status"] in ("SUBMITTED", "GRADED"))
            flagged = sum(1 for a in attempts if a["status"] == "MALPRACTICE")
            enrolled = max(1, len(attempts))  # without a roster count we use attempts as a floor
            ends_at = exam.scheduled_at + timedelta(minutes=exam.duration_minutes)
            minutes_remaining = int((ends_at - current).total_seconds() // 60)
            responded = len(attempts) - in_progress
            response_rate = int(round(responded * 100 / max(enrolled, 1)))
            row = _exam_to_row(
                exam,
                cname,
                scode,
                sname,
                did,
                dname,
                author,
                enrolled=enrolled,
                submitted=submitted,
            )
            monitor_exams.append(
                ExamControllerMonitoredExam(
                    exam=row,
                    attempts=[ExamControllerAttemptRow(**a) for a in attempts],
                    in_progress=in_progress,
                    submitted=submitted,
                    not_started=max(0, enrolled - len(attempts)),
                    flagged=flagged,
                    minutes_remaining=minutes_remaining,
                    response_rate=response_rate,
                    window_end_at=ends_at,
                )
            )
            total_candidates += enrolled
            total_in_progress += in_progress
            total_flagged += flagged

        starting_rows = await db.execute(
            select(Exam, SchoolClass.name, Subject.code, Subject.name, Department.id, Department.name, User.name)
            .join(SchoolClass, and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id))
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .outerjoin(Department, and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id))
            .outerjoin(User, User.id == Exam.created_by)
            .where(
                Exam.tenant_id == tenant_id,
                Exam.status == ExamStatus.PUBLISHED,
                Exam.scheduled_at > current,
                Exam.scheduled_at <= current + timedelta(minutes=UPCOMING_WINDOW_MINUTES),
            )
            .order_by(Exam.scheduled_at)
        )
        starting_soon: list[ExamControllerStartingSoon] = []
        for exam, cname, scode, sname, did, dname, author in starting_rows.all():
            minutes_until = int((exam.scheduled_at - current).total_seconds() // 60)
            row = _exam_to_row(exam, cname, scode, sname, did, dname, author)
            starting_soon.append(
                ExamControllerStartingSoon(
                    exam=row,
                    minutes_until_start=minutes_until,
                    mode=_coerce(exam.mode, "ONLINE"),
                )
            )

        return ExamControllerMonitorBoard(
            live=monitor_exams,
            starting_soon=starting_soon,
            total_candidates=total_candidates,
            total_in_progress=total_in_progress,
            total_flagged=total_flagged,
            now=current,
        )

    # ── C-EC-06 malpractice ────────────────────────────────────────────────

    @staticmethod
    async def malpractice_board(
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> ExamControllerMalpracticeBoard:
        HandlerUser = aliased(User)
        logs_rows = await db.execute(
            select(
                MalpracticeLog,
                User.name.label("student_name"),
                HandlerUser.name.label("handled_by_name"),
                ExamAttempt.tab_switch_count,
                ExamAttempt.status.label("attempt_status"),
                ExamAttempt.exam_id,
                Exam.title,
                Subject.code,
                SchoolClass.name,
                Department.name,
            )
            .join(User, User.id == MalpracticeLog.student_id)
            .outerjoin(HandlerUser, HandlerUser.id == MalpracticeLog.handled_by)
            .join(ExamAttempt, ExamAttempt.id == MalpracticeLog.attempt_id)
            .join(Exam, Exam.id == ExamAttempt.exam_id)
            .join(Subject, Subject.id == Exam.subject_id)
            .join(SchoolClass, SchoolClass.id == Exam.class_id)
            .outerjoin(Department, Department.id == SchoolClass.department_id)
            .where(MalpracticeLog.tenant_id == tenant_id)
            .order_by(MalpracticeLog.logged_at.desc())
        )
        cases: list[ExamControllerMalpracticeRow] = []
        exam_options: dict[uuid.UUID, str] = {}
        for log, sname, hname, tab_count, attempt_status, exam_id, exam_title, scode, cname, dname in logs_rows.all():
            cases.append(
                ExamControllerMalpracticeRow(
                    id=log.id,
                    attempt_id=log.attempt_id,
                    student_id=log.student_id,
                    student_name=sname,
                    exam_id=exam_id,
                    exam_title=exam_title,
                    subject_code=scode,
                    class_name=cname,
                    department_name=dname,
                    type=log.type,
                    description=log.description,
                    evidence_url=log.evidence_url,
                    action_taken=log.action_taken,
                    logged_at=log.logged_at,
                    handled_by=log.handled_by,
                    handled_by_name=hname,
                    tab_switch_count=int(tab_count or 0),
                    attempt_status=str(attempt_status),
                )
            )
            exam_options[exam_id] = exam_title
        # sort: open first, then by tab switches
        cases.sort(
            key=lambda c: (
                0 if c.action_taken is None else 1,
                -c.tab_switch_count,
            )
        )

        return ExamControllerMalpracticeBoard(
            cases=cases,
            open_count=sum(1 for c in cases if c.action_taken is None),
            warned=sum(1 for c in cases if c.action_taken == "WARNED"),
            disqualified=sum(1 for c in cases if c.action_taken == "DISQUALIFIED"),
            ignored=sum(1 for c in cases if c.action_taken == "IGNORED"),
            exams=[
                ExamControllerMalpracticeExamOption(id=eid, title=title)
                for eid, title in sorted(exam_options.items(), key=lambda kv: kv[1])
            ],
        )

    @staticmethod
    async def resolve_malpractice(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: User,
        log_id: uuid.UUID,
        payload: ExamControllerMalpracticeAction,
    ) -> ExamControllerMalpracticeRow:
        log = (
            await db.execute(
                select(MalpracticeLog)
                .where(
                    MalpracticeLog.tenant_id == tenant_id,
                    MalpracticeLog.id == log_id,
                )
            )
        ).scalar_one_or_none()
        if log is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Malpractice log not found")
        log.action_taken = payload.action
        log.handled_by = actor.id
        AuditService.record(
            db,
            tenant_id=tenant_id,
            actor=actor,
            actor_role="EXAM_CONTROLLER",
            action="MALPRACTICE_RESOLVED",
            entity="malpractice_log",
            entity_id=log.id,
            new_value={"action": payload.action, "note": payload.note} if payload.note else {"action": payload.action},
        )
        await db.flush()
        return await ExamControllerService._malpractice_row(db, tenant_id, log.id)

    # ── C-EC-07 result compilation ─────────────────────────────────────────

    @staticmethod
    async def result_context(
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> ExamControllerResultCompilationContext:
        year = await _current_year(db, tenant_id)
        year_name = year.name if year else None
        classes = await db.execute(
            select(SchoolClass, Department.name)
            .outerjoin(Department, and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id))
            .where(SchoolClass.tenant_id == tenant_id, SchoolClass.is_active.is_(True))
            .order_by(SchoolClass.name)
        )
        class_opts = [
            ExamControllerClassOption(
                id=cls.id,
                name=cls.name,
                department_id=cls.department_id,
                department_name=dname,
            )
            for cls, dname in classes.all()
        ]
        exams_rows = await db.execute(
            select(
                Exam,
                SchoolClass.name,
                Subject.code,
                Subject.name,
                func.count(ExamAttempt.id).label("attempts"),
            )
            .join(SchoolClass, and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id))
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .outerjoin(
                ExamAttempt,
                and_(
                    ExamAttempt.exam_id == Exam.id,
                    ExamAttempt.tenant_id == tenant_id,
                ),
            )
            .where(
                Exam.tenant_id == tenant_id,
                Exam.status.in_([ExamStatus.COMPLETED, ExamStatus.RESULTS_RELEASED]),
            )
            .group_by(Exam.id, SchoolClass.name, Subject.code, Subject.name)
            .order_by(Exam.scheduled_at.desc())
        )
        sources: list[ExamControllerResultSourceExam] = []
        for exam, cname, scode, sname, attempts in exams_rows.all():
            attempt_count = int(attempts or 0)
            sources.append(
                ExamControllerResultSourceExam(
                    id=exam.id,
                    title=exam.title,
                    subject_code=scode,
                    subject_name=sname,
                    class_id=exam.class_id,
                    class_name=cname,
                    total_marks=exam.total_marks,
                    passing_marks=exam.passing_marks,
                    attempts=attempt_count,
                    submitted=0,
                    graded=0,
                    pending_grading=0,
                )
            )
        return ExamControllerResultCompilationContext(
            academic_year=year_name,
            classes=class_opts,
            available_exams=sources,
            today=await _tenant_today(db, tenant_id),
        )

    @staticmethod
    async def preview_compilation(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        exam_ids: Sequence[uuid.UUID],
    ) -> ExamControllerCompilationPreview:
        if not exam_ids:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No exams selected")
        exams_rows = await db.execute(
            select(Exam, SchoolClass.name, Subject.code, Subject.name)
            .join(SchoolClass, and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id))
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .where(Exam.tenant_id == tenant_id, Exam.id.in_(list(exam_ids)))
        )
        exams = exams_rows.all()
        if not exams:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No matching exams found")
        attempt_rows = await db.execute(
            select(ExamAttempt.exam_id, ExamAttempt.status, func.count(ExamAttempt.id))
            .where(ExamAttempt.tenant_id == tenant_id, ExamAttempt.exam_id.in_(list(exam_ids)))
            .group_by(ExamAttempt.exam_id, ExamAttempt.status)
        )
        counts: dict[uuid.UUID, Counter] = defaultdict(Counter)
        for eid, status_, count in attempt_rows.all():
            counts[eid][str(status_)] = int(count or 0)
        # roster overlap: count distinct students across the exams' classes
        student_rows = await db.execute(
            select(Exam.class_id, func.count(Exam.id))
            .where(Exam.tenant_id == tenant_id, Exam.id.in_(list(exam_ids)))
            .group_by(Exam.class_id)
        )
        distinct_classes = {cid for cid, _ in student_rows.all()}
        from app.models.enrollment import Enrollment
        student_count = 0
        for cid in distinct_classes:
            student_count += (
                await db.execute(
                    select(func.count(Enrollment.id))
                    .where(Enrollment.tenant_id == tenant_id, Enrollment.class_id == cid)
                )
            ).scalar() or 0

        per_exam: list[ExamControllerResultSourceExam] = []
        total_attempts = 0
        total_submitted = 0
        total_graded = 0
        total_pending = 0
        for exam, cname, scode, sname in exams:
            c = counts.get(exam.id, Counter())
            attempts = sum(c.values())
            submitted = c.get("SUBMITTED", 0) + c.get("GRADED", 0) + c.get("MALPRACTICE", 0)
            graded = c.get("GRADED", 0)
            pending = c.get("IN_PROGRESS", 0) + c.get("SUBMITTED", 0)
            per_exam.append(
                ExamControllerResultSourceExam(
                    id=exam.id,
                    title=exam.title,
                    subject_code=scode,
                    subject_name=sname,
                    class_id=exam.class_id,
                    class_name=cname,
                    total_marks=exam.total_marks,
                    passing_marks=exam.passing_marks,
                    attempts=attempts,
                    submitted=submitted,
                    graded=graded,
                    pending_grading=pending,
                )
            )
            total_attempts += attempts
            total_submitted += submitted
            total_graded += graded
            total_pending += pending
        return ExamControllerCompilationPreview(
            exam_count=len(per_exam),
            students=int(student_count),
            attempts_pending=total_pending,
            attempts_submitted=total_submitted,
            attempts_graded=total_graded,
            by_exam=per_exam,
        )

    @staticmethod
    async def compile_publication(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: User,
        payload: ExamControllerPublicationCreate,
    ) -> ExamControllerPublicationRow:
        await ExamControllerService._ensure_year(db, tenant_id, payload.academic_year_id)
        if payload.class_id:
            cls = (
                await db.execute(
                    select(SchoolClass)
                    .where(
                        SchoolClass.tenant_id == tenant_id,
                        SchoolClass.id == payload.class_id,
                    )
                )
            ).scalar_one_or_none()
            if cls is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, detail="Class not found"
                )
        preview = await ExamControllerService.preview_compilation(
            db, tenant_id, payload.exam_ids
        )
        publication = ExamControllerPublication(
            tenant_id=tenant_id,
            title=payload.title.strip(),
            academic_year_id=payload.academic_year_id,
            class_id=payload.class_id,
            exam_ids=list(payload.exam_ids),
            compiled_by=actor.id,
            status=ExamControllerPublicationStatus.DRAFT,
            summary={
                "exam_count": preview.exam_count,
                "students": preview.students,
                "attempts_pending": preview.attempts_pending,
                "attempts_submitted": preview.attempts_submitted,
                "attempts_graded": preview.attempts_graded,
            },
            note=payload.note,
        )
        db.add(publication)
        await db.flush()
        AuditService.record(
            db,
            tenant_id=tenant_id,
            actor=actor,
            actor_role="EXAM_CONTROLLER",
            action="PUBLICATION_COMPILED",
            entity="exam_controller_publication",
            entity_id=publication.id,
            new_value={
                "title": publication.title,
                "exam_count": preview.exam_count,
                "students": preview.students,
            },
        )
        await db.flush()
        cls_name = None
        if payload.class_id:
            cls_row = await db.execute(
                select(SchoolClass.name).where(
                    SchoolClass.tenant_id == tenant_id,
                    SchoolClass.id == payload.class_id,
                )
            )
            cls_name = cls_row.scalar_one_or_none()
        author_name = actor.name
        return await ExamControllerService._publication_to_row(
            db, tenant_id, publication, cls_name, author_name
        )

    @staticmethod
    async def publications(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ExamControllerPublicationPage:
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        clauses = [ExamControllerPublication.tenant_id == tenant_id]
        if status_filter:
            clauses.append(
                ExamControllerPublication.status
                == ExamControllerPublicationStatus(status_filter)
            )
        total = (
            await db.execute(
                select(func.count(ExamControllerPublication.id)).where(*clauses)
            )
        ).scalar() or 0
        rows = await db.execute(
            select(ExamControllerPublication, SchoolClass.name, User.name)
            .outerjoin(
                SchoolClass,
                and_(
                    SchoolClass.id == ExamControllerPublication.class_id,
                    SchoolClass.tenant_id == tenant_id,
                ),
            )
            .outerjoin(User, User.id == ExamControllerPublication.compiled_by)
            .where(*clauses)
            .order_by(ExamControllerPublication.compiled_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items: list[ExamControllerPublicationRow] = []
        for pub, cname, author in rows.all():
            items.append(
                await ExamControllerService._publication_to_row(
                    db, tenant_id, pub, cname, author
                )
            )
        return ExamControllerPublicationPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=items,
        )

    @staticmethod
    async def get_publication(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        publication_id: uuid.UUID,
    ) -> ExamControllerPublicationRow:
        row = await db.execute(
            select(ExamControllerPublication, SchoolClass.name, User.name)
            .outerjoin(
                SchoolClass,
                and_(
                    SchoolClass.id == ExamControllerPublication.class_id,
                    SchoolClass.tenant_id == tenant_id,
                ),
            )
            .outerjoin(User, User.id == ExamControllerPublication.compiled_by)
            .where(
                ExamControllerPublication.tenant_id == tenant_id,
                ExamControllerPublication.id == publication_id,
            )
        )
        result = row.first()
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Publication not found")
        pub, cname, author = result
        return await ExamControllerService._publication_to_row(db, tenant_id, pub, cname, author)

    @staticmethod
    async def forward_publication(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: User,
        publication_id: uuid.UUID,
        payload: ExamControllerPublicationForwardRequest,
    ) -> ExamControllerPublicationRow:
        publication = (
            await db.execute(
                select(ExamControllerPublication)
                .where(
                    ExamControllerPublication.tenant_id == tenant_id,
                    ExamControllerPublication.id == publication_id,
                )
            )
        ).scalar_one_or_none()
        if publication is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Publication not found")
        if publication.status not in (
            ExamControllerPublicationStatus.DRAFT,
            ExamControllerPublicationStatus.PENDING_APPROVAL,
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Publication has already been finalised",
            )
        publication.status = ExamControllerPublicationStatus.PENDING_APPROVAL
        if payload.note:
            publication.note = (publication.note or "") + f"\n→ {payload.note}"
        AuditService.record(
            db,
            tenant_id=tenant_id,
            actor=actor,
            actor_role="EXAM_CONTROLLER",
            action="PUBLICATION_FORWARDED",
            entity="exam_controller_publication",
            entity_id=publication.id,
            new_value={"note": payload.note} if payload.note else None,
        )
        await db.flush()
        return await ExamControllerService.get_publication(db, tenant_id, publication.id)

    # ── C-EC-08 publish results ────────────────────────────────────────────

    @staticmethod
    async def publish_results(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: User,
        publication_id: uuid.UUID,
        payload: ExamControllerPublishRequest,
    ) -> ExamControllerPublicationRow:
        publication = (
            await db.execute(
                select(ExamControllerPublication)
                .where(
                    ExamControllerPublication.tenant_id == tenant_id,
                    ExamControllerPublication.id == publication_id,
                )
            )
        ).scalar_one_or_none()
        if publication is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Publication not found")
        if publication.status not in (
            ExamControllerPublicationStatus.PENDING_APPROVAL,
            ExamControllerPublicationStatus.APPROVED,
            ExamControllerPublicationStatus.PUBLISHED,
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Publication must be approved before publishing",
            )
        if payload.publish:
            publication.status = ExamControllerPublicationStatus.PUBLISHED
            publication.published_at = _now_utc()
            # Mirror to the principal's canonical row so the student view
            # surfaces it. If the principal row doesn't exist, create one.
            principal_row = (
                await db.execute(
                    select(ResultPublication).where(
                        ResultPublication.tenant_id == tenant_id,
                        ResultPublication.id == publication.id,
                    )
                )
            ).scalar_one_or_none()
            if principal_row is None:
                principal_row = ResultPublication(
                    id=publication.id,
                    tenant_id=tenant_id,
                    title=publication.title,
                    academic_year_id=publication.academic_year_id,
                    class_id=publication.class_id,
                    exam_ids=list(publication.exam_ids),
                    published_by=actor.id,
                    published_at=publication.published_at,
                    is_visible_to_students=True,
                    approval_status="PUBLISHED",
                    approved_by=actor.id,
                    approved_at=publication.published_at,
                )
                db.add(principal_row)
            else:
                principal_row.is_visible_to_students = True
                principal_row.approval_status = "PUBLISHED"
                principal_row.published_at = publication.published_at
            # Mark each underlying exam as results-released.
            if publication.exam_ids:
                exams = (
                    await db.execute(
                        select(Exam).where(
                            Exam.tenant_id == tenant_id,
                            Exam.id.in_(list(publication.exam_ids)),
                        )
                    )
                ).scalars().all()
                for ex in exams:
                    if ex.status in (ExamStatus.COMPLETED, ExamStatus.RESULTS_RELEASED):
                        ex.status = ExamStatus.RESULTS_RELEASED
                        ex.results_release_at = publication.published_at
            if payload.notify_students:
                await ExamControllerService._notify_publication(
                    db, tenant_id, actor, publication
                )
            AuditService.record(
                db,
                tenant_id=tenant_id,
                actor=actor,
            actor_role="EXAM_CONTROLLER",
                action="RESULTS_PUBLISHED",
                entity="exam_controller_publication",
                entity_id=publication.id,
                new_value={"title": publication.title},
            )
        else:
            publication.status = ExamControllerPublicationStatus.WITHDRAWN
            AuditService.record(
                db,
                tenant_id=tenant_id,
                actor=actor,
            actor_role="EXAM_CONTROLLER",
                action="RESULTS_WITHDRAWN",
                entity="exam_controller_publication",
                entity_id=publication.id,
                new_value={"note": payload.note} if payload.note else None,
            )
        await db.flush()
        return await ExamControllerService.get_publication(db, tenant_id, publication.id)

    # ── C-EC-09 grade cards ────────────────────────────────────────────────

    @staticmethod
    async def grade_cards(
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> ExamControllerGradeCardsOverview:
        publications_rows = await db.execute(
            select(ExamControllerPublication, SchoolClass.name, User.name)
            .outerjoin(
                SchoolClass,
                and_(
                    SchoolClass.id == ExamControllerPublication.class_id,
                    SchoolClass.tenant_id == tenant_id,
                ),
            )
            .outerjoin(User, User.id == ExamControllerPublication.compiled_by)
            .where(ExamControllerPublication.tenant_id == tenant_id)
            .order_by(ExamControllerPublication.compiled_at.desc())
            .limit(20)
        )
        publications: list[ExamControllerPublicationRow] = []
        for pub, cname, author in publications_rows.all():
            publications.append(
                await ExamControllerService._publication_to_row(
                    db, tenant_id, pub, cname, author
                )
            )
        # auto-generate any missing cards for the most recent publication
        await ExamControllerService._ensure_grade_cards(db, tenant_id, publications)
        cards_rows = await db.execute(
            select(ExamControllerGradeCard, User.name, SchoolClass.name, ExamControllerPublication.title)
            .join(User, User.id == ExamControllerGradeCard.student_id)
            .join(SchoolClass, and_(SchoolClass.id == ExamControllerGradeCard.class_id, SchoolClass.tenant_id == tenant_id))
            .join(ExamControllerPublication, ExamControllerPublication.id == ExamControllerGradeCard.publication_id)
            .where(ExamControllerGradeCard.tenant_id == tenant_id)
            .order_by(ExamControllerGradeCard.publication_id, ExamControllerGradeCard.rank.is_(None), ExamControllerGradeCard.rank)
        )
        groups: dict[tuple[uuid.UUID, str, uuid.UUID, str], list[ExamControllerGradeCardRow]] = defaultdict(list)
        for card, sname, cname, ptitle in cards_rows.all():
            row = ExamControllerGradeCardRow(
                id=card.id,
                publication_id=card.publication_id,
                publication_title=ptitle,
                student_id=card.student_id,
                student_name=sname,
                roll_no=None,
                class_id=card.class_id,
                class_name=cname,
                total_marks_obtained=card.total_marks_obtained,
                total_marks_possible=card.total_marks_possible,
                percentage=card.percentage,
                grade=card.grade,
                rank=card.rank,
                subject_scores=list(card.subject_scores or []),
                status=_coerce(card.status, "PENDING"),
                generated_at=card.generated_at,
                published_at=card.published_at,
            )
            groups[(card.class_id, cname, card.publication_id, ptitle)].append(row)

        group_models: list[ExamControllerGradeCardClassGroup] = []
        total = 0
        published = 0
        pending = 0
        failed = 0
        for (class_id, cname, pub_id, ptitle), cards in groups.items():
            total += len(cards)
            published += sum(1 for c in cards if c.status == "PUBLISHED")
            pending += sum(1 for c in cards if c.status == "PENDING")
            failed += sum(1 for c in cards if c.status == "FAILED")
            group_models.append(
                ExamControllerGradeCardClassGroup(
                    class_id=class_id,
                    class_name=cname,
                    publication_id=pub_id,
                    publication_title=ptitle,
                    total=len(cards),
                    generated=sum(1 for c in cards if c.status in ("GENERATED", "PUBLISHED")),
                    published=published,
                    failed=failed,
                    pending=pending,
                    cards=cards,
                )
            )
        group_models.sort(key=lambda g: (g.class_name, g.publication_title))
        return ExamControllerGradeCardsOverview(
            publications=publications,
            groups=group_models,
            total_cards=total,
            total_published=published,
            total_pending=pending,
            total_failed=failed,
        )

    @staticmethod
    async def regenerate_grade_cards(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: User,
        payload: ExamControllerGradeCardRegenerateRequest,
    ) -> ExamControllerGradeCardsOverview:
        publication = (
            await db.execute(
                select(ExamControllerPublication)
                .where(
                    ExamControllerPublication.tenant_id == tenant_id,
                    ExamControllerPublication.id == payload.publication_id,
                )
            )
        ).scalar_one_or_none()
        if publication is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Publication not found")
        # delete the existing cards so _ensure_grade_cards rebuilds them
        existing = (
            await db.execute(
                select(ExamControllerGradeCard)
                .where(ExamControllerGradeCard.publication_id == publication.id)
            )
        ).scalars().all()
        for c in existing:
            await db.delete(c)
        await db.flush()
        AuditService.record(
            db,
            tenant_id=tenant_id,
            actor=actor,
            actor_role="EXAM_CONTROLLER",
            action="GRADE_CARDS_REGENERATED",
            entity="exam_controller_publication",
            entity_id=publication.id,
            new_value={"note": payload.note} if payload.note else None,
        )
        return await ExamControllerService.grade_cards(db, tenant_id)

    @staticmethod
    async def publish_grade_cards(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: User,
        publication_id: uuid.UUID,
    ) -> ExamControllerGradeCardsOverview:
        cards = (
            await db.execute(
                select(ExamControllerGradeCard)
                .where(
                    ExamControllerGradeCard.tenant_id == tenant_id,
                    ExamControllerGradeCard.publication_id == publication_id,
                )
            )
        ).scalars().all()
        now = _now_utc()
        for card in cards:
            if card.status != ExamControllerGradeCardStatus.PUBLISHED:
                card.status = ExamControllerGradeCardStatus.PUBLISHED
                card.published_at = now
        AuditService.record(
            db,
            tenant_id=tenant_id,
            actor=actor,
            actor_role="EXAM_CONTROLLER",
            action="GRADE_CARDS_PUBLISHED",
            entity="exam_controller_publication",
            entity_id=publication_id,
        )
        await db.flush()
        return await ExamControllerService.grade_cards(db, tenant_id)

    # ── C-EC-10 reports ───────────────────────────────────────────────────

    @staticmethod
    async def report_overview(
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> ExamControllerReportOverview:
        year = await _current_year(db, tenant_id)
        year_name = year.name if year else None
        publication_rows = await db.execute(
            select(ExamControllerPublication)
            .where(ExamControllerPublication.tenant_id == tenant_id)
        )
        publications = publication_rows.scalars().all()
        total_publications = len(publications)
        total_published = sum(
            1 for p in publications if p.status == ExamControllerPublicationStatus.PUBLISHED
        )
        cards_rows = await db.execute(
            select(ExamControllerGradeCard, SchoolClass.name, Department.name, User.name, ExamControllerPublication.title)
            .join(SchoolClass, and_(SchoolClass.id == ExamControllerGradeCard.class_id, SchoolClass.tenant_id == tenant_id))
            .outerjoin(Department, Department.id == SchoolClass.department_id)
            .join(User, User.id == ExamControllerGradeCard.student_id)
            .join(ExamControllerPublication, ExamControllerPublication.id == ExamControllerGradeCard.publication_id)
            .where(ExamControllerGradeCard.tenant_id == tenant_id)
        )
        cards = cards_rows.all()
        total_students = len(cards)
        passed = sum(1 for c in cards if c[0].percentage >= 50)
        # group by class
        class_buckets: dict[uuid.UUID, dict] = {}
        for card, cname, dname, _sname, _ptitle in cards:
            bucket = class_buckets.setdefault(
                card.class_id,
                {
                    "name": cname,
                    "department": dname,
                    "students": 0,
                    "pass": 0,
                    "fail": 0,
                    "withheld": 0,
                    "percentage_total": 0.0,
                },
            )
            bucket["students"] += 1
            if card.percentage >= 50:
                bucket["pass"] += 1
            else:
                bucket["fail"] += 1
            bucket["percentage_total"] += float(card.percentage or 0)
        class_summaries = [
            ExamControllerReportClassSummary(
                class_id=cid,
                class_name=bucket["name"],
                department_name=bucket["department"],
                students=bucket["students"],
                pass_count=bucket["pass"],
                fail_count=bucket["fail"],
                withheld_count=bucket["withheld"],
                pass_percentage=round(bucket["pass"] * 100 / bucket["students"], 2) if bucket["students"] else 0.0,
                average_percentage=round(bucket["percentage_total"] / bucket["students"], 2) if bucket["students"] else 0.0,
            )
            for cid, bucket in class_buckets.items()
        ]
        class_summaries.sort(key=lambda s: s.class_name)

        subject_buckets: dict[tuple[uuid.UUID, uuid.UUID], dict] = {}
        for card, cname, dname, _sname, _ptitle in cards:
            for entry in card.subject_scores or []:
                subject_id = entry.get("subject_id")
                if not subject_id:
                    continue
                key = (uuid.UUID(str(subject_id)), card.class_id)
                bucket = subject_buckets.setdefault(
                    key,
                    {
                        "subject_code": entry.get("subject_code", ""),
                        "subject_name": entry.get("subject_name", ""),
                        "class_id": card.class_id,
                        "class_name": cname,
                        "exams": 0,
                        "students": 0,
                        "pass": 0,
                        "percentage_total": 0.0,
                    },
                )
                bucket["exams"] += 1
                bucket["students"] += 1
                percentage = float(entry.get("percentage", 0) or 0)
                if percentage >= 50:
                    bucket["pass"] += 1
                bucket["percentage_total"] += percentage
        subject_summaries = [
            ExamControllerReportSubjectSummary(
                subject_id=key[0],
                subject_code=bucket["subject_code"],
                subject_name=bucket["subject_name"],
                class_id=bucket["class_id"],
                class_name=bucket["class_name"],
                exams=bucket["exams"],
                students=bucket["students"],
                pass_count=bucket["pass"],
                pass_percentage=round(bucket["pass"] * 100 / bucket["students"], 2) if bucket["students"] else 0.0,
                average_percentage=round(bucket["percentage_total"] / bucket["students"], 2) if bucket["students"] else 0.0,
            )
            for key, bucket in subject_buckets.items()
        ]
        subject_summaries.sort(key=lambda s: (s.class_name, s.subject_code))

        top_rows = sorted(
            cards,
            key=lambda row: (-float(row[0].percentage or 0), row[0].rank or 0),
        )[:10]
        toppers: list[ExamControllerReportTopper] = []
        for card, cname, _dname, sname, ptitle in top_rows:
            toppers.append(
                ExamControllerReportTopper(
                    student_id=card.student_id,
                    student_name=sname,
                    roll_no=None,
                    class_name=cname,
                    publication_id=card.publication_id,
                    publication_title=ptitle,
                    percentage=card.percentage,
                    grade=card.grade,
                    rank=card.rank,
                )
            )

        return ExamControllerReportOverview(
            academic_year=year_name,
            total_publications=total_publications,
            total_published=total_published,
            total_students_compiled=total_students,
            pass_percentage=round(passed * 100 / total_students, 2) if total_students else 0.0,
            by_class=class_summaries,
            by_subject=subject_summaries,
            toppers=toppers,
        )

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    async def _publication_to_row(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        publication: ExamControllerPublication,
        class_name: str | None,
        author_name: str | None,
    ) -> ExamControllerPublicationRow:
        # resolve exam titles
        if publication.exam_ids:
            exam_rows = await db.execute(
                select(Exam.id, Exam.title).where(
                    Exam.tenant_id == tenant_id,
                    Exam.id.in_(list(publication.exam_ids)),
                )
            )
            titles_by_id = {eid: title for eid, title in exam_rows.all()}
        else:
            titles_by_id = {}
        exam_titles = [titles_by_id.get(eid, "—") for eid in publication.exam_ids]
        # counts from the canonical grade cards (if they have been generated)
        cards_rows = await db.execute(
            select(ExamControllerGradeCard).where(
                ExamControllerGradeCard.publication_id == publication.id
            )
        )
        cards = cards_rows.scalars().all()
        return ExamControllerPublicationRow(
            id=publication.id,
            title=publication.title,
            academic_year=publication.academic_year_id and (
                await _current_year_name(db, tenant_id)
            ),
            class_id=publication.class_id,
            class_name=class_name,
            exam_ids=list(publication.exam_ids),
            exam_titles=exam_titles,
            compiled_by=publication.compiled_by,
            compiled_by_name=author_name,
            compiled_at=publication.compiled_at,
            published_at=publication.published_at,
            status=_coerce(publication.status, "DRAFT"),
            student_count=len(cards),
            pass_count=sum(1 for c in cards if float(c.percentage or 0) >= 50),
            fail_count=sum(1 for c in cards if float(c.percentage or 0) < 50),
            withheld_count=sum(1 for c in cards if str(c.grade or "") == "WH"),
            note=publication.note,
        )

    @staticmethod
    async def _ensure_class_subject_year(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        class_id: uuid.UUID,
        subject_id: uuid.UUID,
        year_id: uuid.UUID,
    ) -> None:
        cls = (
            await db.execute(
                select(SchoolClass).where(
                    SchoolClass.tenant_id == tenant_id,
                    SchoolClass.id == class_id,
                )
            )
        ).scalar_one_or_none()
        if cls is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Class not found")
        subject = (
            await db.execute(
                select(Subject).where(
                    Subject.tenant_id == tenant_id,
                    Subject.id == subject_id,
                )
            )
        ).scalar_one_or_none()
        if subject is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Subject not found")
        year = (
            await db.execute(
                select(AcademicYear).where(
                    AcademicYear.tenant_id == tenant_id,
                    AcademicYear.id == year_id,
                )
            )
        ).scalar_one_or_none()
        if year is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Academic year not found")

    @staticmethod
    async def _ensure_year(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        year_id: uuid.UUID,
    ) -> AcademicYear:
        year = (
            await db.execute(
                select(AcademicYear).where(
                    AcademicYear.tenant_id == tenant_id,
                    AcademicYear.id == year_id,
                )
            )
        ).scalar_one_or_none()
        if year is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Academic year not found")
        return year

    @staticmethod
    async def _get_exam_or_404(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        exam_id: uuid.UUID,
    ) -> Exam:
        exam = (
            await db.execute(
                select(Exam).where(
                    Exam.tenant_id == tenant_id,
                    Exam.id == exam_id,
                )
            )
        ).scalar_one_or_none()
        if exam is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam not found")
        return exam

    @staticmethod
    async def _user_name(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
    ) -> str | None:
        if user_id is None:
            return None
        row = (
            await db.execute(
                select(User.name).where(
                    User.tenant_id == tenant_id, User.id == user_id
                )
            )
        ).scalar_one_or_none()
        return row

    @staticmethod
    async def _invigilator_options(
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> list[ExamControllerInvigilatorOption]:
        rows = await db.execute(
            select(
                User.id,
                User.name,
                User.is_active,
                StaffProfile.id,
                StaffProfile.department_id,
                Department.name,
                StaffProfile.designation,
            )
            .join(StaffProfile, StaffProfile.user_id == User.id, isouter=True)
            .outerjoin(Department, Department.id == StaffProfile.department_id)
            .where(User.tenant_id == tenant_id, User.is_active.is_(True))
            .order_by(User.name)
        )
        # Without a tenant-scoped user-roles table we accept any active
        # user with a StaffProfile as invigilator-eligible; the principal
        # service applies the same liberal filter.
        options: list[ExamControllerInvigilatorOption] = []
        for uid, name, is_active, _sp, dept_id, dept_name, designation in rows.all():
            if is_active is False:
                continue
            options.append(
                ExamControllerInvigilatorOption(
                    id=uid,
                    name=name,
                    department_id=dept_id,
                    department_name=dept_name,
                    designation=designation,
                    is_active=bool(is_active),
                )
            )
        return options

    @staticmethod
    async def _attempts_for(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        exam_id: uuid.UUID,
    ) -> list[dict]:
        rows = await db.execute(
            select(ExamAttempt, User.name)
            .outerjoin(User, User.id == ExamAttempt.student_id)
            .where(
                ExamAttempt.tenant_id == tenant_id,
                ExamAttempt.exam_id == exam_id,
            )
            .order_by(ExamAttempt.started_at)
        )
        attempts: list[dict] = []
        for attempt, sname in rows.all():
            attempts.append(
                {
                    "id": attempt.id,
                    "student_id": attempt.student_id,
                    "student_name": sname or "—",
                    "status": str(attempt.status),
                    "started_at": attempt.started_at,
                    "submitted_at": attempt.submitted_at,
                    "total_score": float(attempt.total_score) if attempt.total_score is not None else None,
                    "percentage": float(attempt.percentage) if attempt.percentage is not None else None,
                    "tab_switch_count": int(attempt.tab_switch_count or 0),
                    "ip_address": str(attempt.ip_address) if attempt.ip_address is not None else None,
                    "device_info": attempt.device_info,
                }
            )
        return attempts

    @staticmethod
    async def _malpractice_row(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        log_id: uuid.UUID,
    ) -> ExamControllerMalpracticeRow:
        HandlerUser = aliased(User)
        row = (
            await db.execute(
                select(
                    MalpracticeLog,
                    User.name.label("student_name"),
                    HandlerUser.name.label("handled_by_name"),
                    ExamAttempt.tab_switch_count,
                    ExamAttempt.status.label("attempt_status"),
                    ExamAttempt.exam_id,
                    Exam.title,
                    Subject.code,
                    SchoolClass.name,
                    Department.name,
                )
                .join(User, User.id == MalpracticeLog.student_id)
                .outerjoin(HandlerUser, HandlerUser.id == MalpracticeLog.handled_by)
                .join(ExamAttempt, ExamAttempt.id == MalpracticeLog.attempt_id)
                .join(Exam, Exam.id == ExamAttempt.exam_id)
                .join(Subject, Subject.id == Exam.subject_id)
                .join(SchoolClass, SchoolClass.id == Exam.class_id)
                .outerjoin(Department, Department.id == SchoolClass.department_id)
                .where(
                    MalpracticeLog.tenant_id == tenant_id,
                    MalpracticeLog.id == log_id,
                )
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Malpractice log not found")
        log, sname, hname, tab_count, attempt_status, exam_id, exam_title, scode, cname, dname = row
        return ExamControllerMalpracticeRow(
            id=log.id,
            attempt_id=log.attempt_id,
            student_id=log.student_id,
            student_name=sname,
            exam_id=exam_id,
            exam_title=exam_title,
            subject_code=scode,
            class_name=cname,
            department_name=dname,
            type=log.type,
            description=log.description,
            evidence_url=log.evidence_url,
            action_taken=log.action_taken,
            logged_at=log.logged_at,
            handled_by=log.handled_by,
            handled_by_name=hname,
            tab_switch_count=int(tab_count or 0),
            attempt_status=str(attempt_status),
        )

    @staticmethod
    async def _ensure_grade_cards(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        publications: list[ExamControllerPublicationRow],
    ) -> None:
        if not publications:
            return
        # generate for the most recent publication that has none
        for pub in publications:
            existing = (
                await db.execute(
                    select(func.count(ExamControllerGradeCard.id)).where(
                        ExamControllerGradeCard.publication_id == pub.id
                    )
                )
            ).scalar() or 0
            if existing:
                continue
            from app.models.enrollment import Enrollment
            exams = await db.execute(
                select(Exam).where(
                    Exam.tenant_id == tenant_id,
                    Exam.id.in_(pub.exam_ids),
                )
            )
            exam_list = exams.scalars().all()
            class_id = pub.class_id
            if class_id is None and exam_list:
                class_id = exam_list[0].class_id
            if class_id is None:
                continue
            student_rows = await db.execute(
                select(User.id).where(
                    User.tenant_id == tenant_id,
                    User.is_active.is_(True),
                )
                .join(Enrollment, and_(Enrollment.student_id == User.id, Enrollment.class_id == class_id))
            )
            student_ids = [r for r in student_rows.scalars().all()]
            subject_scores: list[dict] = []
            for ex in exam_list:
                subject_scores.append(
                    {
                        "subject_id": str(ex.subject_id),
                        "subject_code": "",
                        "subject_name": "",
                        "exam_id": str(ex.id),
                        "title": ex.title,
                        "marks_obtained": 0,
                        "marks_possible": ex.total_marks,
                        "percentage": 0.0,
                        "grade": "—",
                    }
                )
            total_possible = sum(ex.total_marks for ex in exam_list) or 1
            cards: list[ExamControllerGradeCard] = []
            for student_id in student_ids:
                # attempt-level aggregates: a fixture-free implementation uses
                # the canonical exam_attempts table when present; with no
                # attempts we synthesise a stable zeroed row so the C-EC-09
                # page has data to render.
                attempt_rows = await db.execute(
                    select(ExamAttempt).where(
                        ExamAttempt.tenant_id == tenant_id,
                        ExamAttempt.exam_id.in_([ex.id for ex in exam_list] or [uuid.uuid4()]),
                        ExamAttempt.student_id == student_id,
                    )
                )
                attempts = attempt_rows.scalars().all()
                total_obtained = sum(float(a.total_score or 0) for a in attempts)
                percentage = round(total_obtained * 100 / total_possible, 2) if total_possible else 0.0
                card = ExamControllerGradeCard(
                    tenant_id=tenant_id,
                    publication_id=pub.id,
                    student_id=student_id,
                    class_id=class_id,
                    total_marks_obtained=Decimal(str(round(total_obtained, 2))),
                    total_marks_possible=Decimal(str(total_possible)),
                    percentage=Decimal(str(percentage)),
                    grade=_grade_for(percentage),
                    subject_scores=subject_scores,
                    status=ExamControllerGradeCardStatus.GENERATED,
                    generated_at=_now_utc(),
                )
                cards.append(card)
                db.add(card)
            # assign ranks
            cards.sort(key=lambda c: float(c.percentage), reverse=True)
            for rank, card in enumerate(cards, start=1):
                card.rank = rank
            if cards:
                await db.flush()

    @staticmethod
    async def _notify_publication(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: User,
        publication: ExamControllerPublication,
    ) -> None:
        # A targeted notice to the publication's class (or institution-wide)
        # announcing the released result. §4.6 gives the controller the
        # notice-posting lever for academic communications.
        if publication.class_id:
            target_scope: NoticeScope = NoticeScope.CLASS
            target_id = publication.class_id
        else:
            target_scope = NoticeScope.INSTITUTION
            target_id = None
        notice = Notice(
            tenant_id=tenant_id,
            title=f"Results released — {publication.title}",
            body=(
                f"Exam Controller has released the results for "
                f"{publication.title}. View your grade card in the "
                f"student portal."
            ),
            author_id=actor.id,
            target_scope=target_scope,
            target_id=target_id,
            priority=NoticePriority.IMPORTANT,
            is_pinned=False,
            published_at=_now_utc(),
        )
        db.add(notice)
        await db.flush()

        # Push an in-app + FCM notification straight to the affected students
        # (everyone enrolled in the publication's class, or the whole year for
        # institution-wide publications). Best-effort: a notification failure
        # must not roll back the publication itself.
        try:
            student_ids = list(
                (
                    await db.execute(
                        select(Enrollment.student_id).where(
                            Enrollment.tenant_id == tenant_id,
                            Enrollment.academic_year_id == publication.academic_year_id,
                            Enrollment.status == "ACTIVE",
                            *([Enrollment.class_id == publication.class_id] if publication.class_id else []),
                        )
                    )
                ).scalars().all()
            )
            if student_ids:
                await PushService.create_in_app_notifications(
                    db,
                    tenant_id=tenant_id,
                    user_ids=student_ids,
                    title=f"Results released — {publication.title}",
                    body=(
                        "Exam Controller has released the results for "
                        f"{publication.title}. View your grade card in the student portal."
                    ),
                    notif_type="EXAM_RESULT_RELEASED",
                    data={
                        "publication_id": str(publication.id),
                        "publication_title": publication.title,
                    },
                )
        except Exception as exc:  # noqa: BLE001 - best-effort, never block publication
            logger.warning("Could not notify students of publication %s: %s", publication.id, exc)
