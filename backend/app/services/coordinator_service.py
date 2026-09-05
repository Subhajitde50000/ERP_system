"""Academic Coordinator workflows (C-AC-01 … C-AC-08).

§4.5 grants the coordinator a build grant on the timetable and the only
``canSubstitute`` permission.  The service is institution-wide: there is no
department fence because the coordinator's authority spans every class in the
tenant.  The shared timetable model in ``PrincipalService`` is reused for the
class/subject/teacher directory to keep the cross-module ownership rule that
the exam monitor established: nobody here re-seeds a class, a teacher or a
period.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.academic import AcademicYear, Department, SchoolClass, Subject
from app.models.enrollment import TeacherSubject
from app.models.coordinator import (
    AcademicEvent,
    AcademicEventScope,
    AcademicEventType,
    TimetableSubstitution,
)
from app.models.principal import (
    Exam,
    ExamStatus,
    Notice,
    NoticePriority,
    NoticeRead,
    NoticeScope,
    StaffProfile,
    TimetableSlot,
)
from app.models.role import Role, RoleAssignment
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.coordinator import (
    CoordinatorClassOption,
    CoordinatorConflictReport,
    CoordinatorConflictRow,
    CoordinatorDashboard,
    CoordinatorEventCreate,
    CoordinatorEventPage,
    CoordinatorEventRow,
    CoordinatorEventUpdate,
    CoordinatorExamKpi,
    CoordinatorNoticeCreate,
    CoordinatorNoticePage,
    CoordinatorNoticeRow,
    CoordinatorNoticeTargets,
    CoordinatorSlotCreate,
    CoordinatorSlotUpdate,
    CoordinatorSubstitutableSlot,
    CoordinatorSubstituteCandidate,
    CoordinatorSubstitutionBoard,
    CoordinatorSubstitutionCreate,
    CoordinatorSubstitutionFormContext,
    CoordinatorSubstitutionRow,
    CoordinatorSubstitutionTakenKey,
    CoordinatorSubjectOption,
    CoordinatorSubstitutionKpi,
    CoordinatorTargetOption,
    CoordinatorTeacherOption,
    CoordinatorTimetableGrid,
    CoordinatorTimetableKpi,
    CoordinatorTimetableSlot,
)
from app.services.audit_service import AuditService
from app.services.principal_service import PrincipalService

__all__ = ["CoordinatorService"]


# ── Constants ────────────────────────────────────────────────────────────────

_PERIOD_LABELS: list[dict[str, str | int]] = [
    {"period": 1, "start": "09:00", "end": "09:50", "label": "Period 1"},
    {"period": 2, "start": "10:00", "end": "10:50", "label": "Period 2"},
    {"period": 3, "start": "11:00", "end": "11:50", "label": "Period 3"},
    {"period": 4, "start": "11:50", "end": "12:30", "label": "Break", "is_break": True},
    {"period": 5, "start": "12:30", "end": "13:20", "label": "Period 5"},
    {"period": 6, "start": "13:30", "end": "14:20", "label": "Period 6"},
    {"period": 7, "start": "14:30", "end": "15:20", "label": "Period 7"},
]


def _value(value: object | None) -> str | None:
    if value is None:
        return None
    candidate = getattr(value, "value", value)
    return str(candidate)


class CoordinatorService:
    # ── Date / scope helpers ────────────────────────────────────────────────

    @staticmethod
    async def _tenant_today(db: AsyncSession, tenant_id: uuid.UUID) -> date:
        timezone_name = (
            await db.execute(select(Tenant.timezone).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()
        try:
            return datetime.now(ZoneInfo(timezone_name or "UTC")).date()
        except (ValueError, TypeError):
            # A bad legacy timezone must never break the dashboard.
            return datetime.now(timezone.utc).date()

    @staticmethod
    async def _current_year(
        db: AsyncSession, tenant_id: uuid.UUID
    ) -> AcademicYear | None:
        return (
            await db.execute(
                select(AcademicYear)
                .where(AcademicYear.tenant_id == tenant_id, AcademicYear.is_current.is_(True))
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    def _next_window(today: date) -> tuple[date, date]:
        return today, today + timedelta(days=14)

    @staticmethod
    async def _ensure_class(
        db: AsyncSession, tenant_id: uuid.UUID, class_id: uuid.UUID
    ) -> SchoolClass:
        school_class = (
            await db.execute(
                select(SchoolClass).where(
                    SchoolClass.id == class_id, SchoolClass.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if school_class is None:
            # 404 avoids confirming another tenant's identifier.
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Class not found")
        return school_class

    @staticmethod
    async def _ensure_subject(
        db: AsyncSession, tenant_id: uuid.UUID, subject_id: uuid.UUID
    ) -> Subject:
        subject = (
            await db.execute(
                select(Subject).where(
                    Subject.id == subject_id, Subject.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if subject is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Subject not found")
        return subject

    @staticmethod
    async def _assert_slot_available(
        db: AsyncSession, tenant_id: uuid.UUID, *, day: int, period: int, starts: date, ends: date | None,
        teacher_id: uuid.UUID | None, room_no: str | None, exclude_slot_id: uuid.UUID | None = None,
    ) -> None:
        """Reject a teacher or room double-booking while timetable changes are saved."""
        overlap = [TimetableSlot.tenant_id == tenant_id, TimetableSlot.day_of_week == day,
                   TimetableSlot.period_number == period, TimetableSlot.effective_from <= (ends or date.max),
                   or_(TimetableSlot.effective_to.is_(None), TimetableSlot.effective_to >= starts)]
        if exclude_slot_id is not None:
            overlap.append(TimetableSlot.id != exclude_slot_id)
        for resource, value, message in ((TimetableSlot.teacher_id, teacher_id, "Teacher is already scheduled for this period."), (TimetableSlot.room_no, room_no, "Room is already scheduled for this period.")):
            if value is None or value == "":
                continue
            found = await db.execute(select(TimetableSlot.id).where(*overlap, resource == value).limit(1))
            if found.scalar_one_or_none() is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, detail=message)

    @staticmethod
    async def _ensure_teaching_assignment(
        db: AsyncSession, tenant_id: uuid.UUID, class_id: uuid.UUID, subject_id: uuid.UUID, teacher_id: uuid.UUID
    ) -> None:
        """Timetable slots must come from a real class → subject → teacher assignment.
        If the teacher is not yet linked to the subject, auto-create the assignment link.
        """
        subject = await CoordinatorService._ensure_subject(db, tenant_id, subject_id)
        if subject.class_id != class_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The selected subject does not belong to this class.")
        assignment = await db.execute(select(TeacherSubject.id).where(
            TeacherSubject.tenant_id == tenant_id,
            TeacherSubject.subject_id == subject_id,
            TeacherSubject.teacher_id == teacher_id,
        ).limit(1))
        if assignment.scalar_one_or_none() is None:
            # Auto-assign teacher to subject when building timetable slot
            link = TeacherSubject(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                subject_id=subject_id,
                teacher_id=teacher_id,
                role_in_subject="TEACHER",
                assigned_at=datetime.now(timezone.utc),
            )
            db.add(link)
            await db.flush()

    @staticmethod
    async def _ensure_teacher(
        db: AsyncSession, tenant_id: uuid.UUID, teacher_id: uuid.UUID
    ) -> User:
        teacher = (
            await db.execute(
                select(User).where(
                    User.id == teacher_id,
                    User.tenant_id == tenant_id,
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if teacher is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Teacher not found")
        return teacher

    # ── C-AC-01 dashboard ───────────────────────────────────────────────────

    @staticmethod
    async def dashboard(
        db: AsyncSession, tenant_id: uuid.UUID
    ) -> CoordinatorDashboard:
        today = await CoordinatorService._tenant_today(db, tenant_id)
        year = await CoordinatorService._current_year(db, tenant_id)

        # Timetable coverage — classes and teachers with at least one active slot.
        active_slots_filter = [
            TimetableSlot.tenant_id == tenant_id,
            TimetableSlot.effective_from <= today,
            or_(
                TimetableSlot.effective_to.is_(None),
                TimetableSlot.effective_to >= today,
            ),
        ]
        if year is not None:
            active_slots_filter.append(TimetableSlot.academic_year_id == year.id)

        coverage = await db.execute(
            select(
                func.count(func.distinct(TimetableSlot.id)).label("total_slots"),
                func.count(func.distinct(TimetableSlot.class_id)).label("classes_covered"),
                func.count(func.distinct(TimetableSlot.teacher_id)).label("teachers_scheduled"),
            ).where(*active_slots_filter)
        )
        coverage_row = coverage.one()
        total_classes = (
            await db.execute(
                select(func.count(SchoolClass.id)).where(
                    SchoolClass.tenant_id == tenant_id,
                    SchoolClass.is_active.is_(True),
                )
            )
        ).scalar() or 0
        coverage_percentage = (
            round(int(coverage_row.classes_covered or 0) * 100 / total_classes, 2)
            if total_classes
            else None
        )
        timetable_kpi = CoordinatorTimetableKpi(
            total_slots=int(coverage_row.total_slots or 0),
            classes_covered=int(coverage_row.classes_covered or 0),
            teachers_scheduled=int(coverage_row.teachers_scheduled or 0),
            coverage_percentage=coverage_percentage,
        )

        # Substitutions — the same rows the C-AC-05 board surfaces.
        substitution_rows = await CoordinatorService._substitution_rows(
            db, tenant_id, today
        )
        sub_kpi = CoordinatorSubstitutionKpi(
            today=sum(1 for row in substitution_rows if row["when"] == "TODAY"),
            upcoming=sum(1 for row in substitution_rows if row["when"] == "UPCOMING"),
            past=sum(1 for row in substitution_rows if row["when"] == "PAST"),
            covering_teachers=len(
                {
                    row["substitute_teacher_id"]
                    for row in substitution_rows
                    if row["when"] in ("TODAY", "UPCOMING")
                }
            ),
        )

        # Exams — counts the coordinator needs to know whether to act.
        exam_filter = [Exam.tenant_id == tenant_id]
        if year is not None:
            exam_filter.append(Exam.academic_year_id == year.id)
        exam_count = await db.execute(
            select(
                func.count(Exam.id).label("scheduled"),
                func.count(Exam.id)
                .filter(
                    Exam.status.in_(
                        [ExamStatus.DRAFT, ExamStatus.PUBLISHED, ExamStatus.ONGOING]
                    )
                )
                .label("upcoming"),
                func.count(Exam.id)
                .filter(Exam.status == ExamStatus.ONGOING)
                .label("ongoing"),
                func.count(Exam.id)
                .filter(Exam.status == ExamStatus.DRAFT)
                .label("pending_hall_allocation"),
            ).where(*exam_filter)
        )
        exam_row = exam_count.one()
        exam_kpi = CoordinatorExamKpi(
            scheduled=int(exam_row.scheduled or 0),
            upcoming=int(exam_row.upcoming or 0),
            ongoing=int(exam_row.ongoing or 0),
            pending_hall_allocation=int(exam_row.pending_hall_allocation or 0),
        )
        pending_exam_schedules = exam_kpi.pending_hall_allocation

        # Upcoming substitutions — today + next 7 days.
        upcoming_subs = [
            row
            for row in substitution_rows
            if row["when"] in ("TODAY", "UPCOMING")
        ][:5]
        upcoming_sub_rows = [
            await CoordinatorService._substitution_dto(db, tenant_id, row)
            for row in upcoming_subs
        ]

        # Upcoming events — next 14 days.
        start, end = CoordinatorService._next_window(today)
        events = await CoordinatorService._event_rows(
            db, tenant_id, start, end, limit=5
        )
        upcoming_event_rows = [
            CoordinatorService._event_dto(db, tenant_id, event) for event in events
        ]

        # Live conflict count.
        conflicts = await CoordinatorService._compute_conflicts(
            db, tenant_id, today
        )

        active_notices = (
            await db.execute(
                select(func.count(Notice.id)).where(
                    Notice.tenant_id == tenant_id,
                    Notice.deleted_at.is_(None),
                    or_(Notice.expires_at.is_(None), Notice.expires_at > datetime.now(timezone.utc)),
                )
            )
        ).scalar() or 0

        return CoordinatorDashboard(
            academic_year=year.name if year else None,
            today=today,
            timetable=timetable_kpi,
            substitutions=sub_kpi,
            exams=exam_kpi,
            upcoming_events=upcoming_event_rows,
            upcoming_substitutions=upcoming_sub_rows,
            pending_exam_schedules=pending_exam_schedules,
            timetable_conflicts=len(conflicts),
            active_notices=int(active_notices),
        )

    # ── C-AC-02 timetable builder ───────────────────────────────────────────

    @staticmethod
    async def timetable(
        db: AsyncSession, tenant_id: uuid.UUID, class_id: uuid.UUID | None = None
    ) -> CoordinatorTimetableGrid:
        today = await CoordinatorService._tenant_today(db, tenant_id)
        class_filters = [SchoolClass.tenant_id == tenant_id, SchoolClass.is_active.is_(True)]
        if class_id is not None:
            await CoordinatorService._ensure_class(db, tenant_id, class_id)
            class_filters.append(SchoolClass.id == class_id)
        class_rows = await db.execute(
            select(SchoolClass, Department.name, User.name)
            .outerjoin(
                Department,
                and_(
                    Department.id == SchoolClass.department_id,
                    Department.tenant_id == tenant_id,
                ),
            )
            .outerjoin(
                User,
                and_(User.id == SchoolClass.class_teacher_id, User.tenant_id == tenant_id),
            )
            .where(*class_filters)
            .order_by(Department.name.nulls_last(), SchoolClass.name)
        )
        classes = [
            CoordinatorClassOption(
                id=school_class.id,
                name=school_class.name,
                department_id=school_class.department_id,
                department_name=department_name,
                class_teacher_name=teacher_name,
            )
            for school_class, department_name, teacher_name in class_rows.all()
        ]

        subject_rows = await db.execute(
            select(Subject, Department.id, Department.name)
            .outerjoin(
                SchoolClass,
                and_(SchoolClass.id == Subject.class_id, SchoolClass.tenant_id == tenant_id),
            )
            .outerjoin(
                Department,
                and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id),
            )
            .where(Subject.tenant_id == tenant_id)
            .order_by(Subject.code)
        )
        subjects = [
            CoordinatorSubjectOption(
                id=subject.id,
                code=subject.code,
                name=subject.name,
                department_id=dept_id,
                department_name=department_name,
            )
            for subject, dept_id, department_name in subject_rows.all()
        ]

        teacher_rows = await db.execute(
            select(
                User,
                StaffProfile,
                Department.name.label("department_name"),
            )
            .outerjoin(
                StaffProfile,
                and_(StaffProfile.user_id == User.id, StaffProfile.tenant_id == tenant_id),
            )
            .outerjoin(
                Department,
                and_(
                    Department.id == StaffProfile.department_id,
                    Department.tenant_id == tenant_id,
                ),
            )
            .join(
                RoleAssignment,
                and_(
                    RoleAssignment.user_id == User.id,
                    RoleAssignment.tenant_id == tenant_id,
                ),
            )
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                User.tenant_id == tenant_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
                RoleAssignment.is_active.is_(True),
                Role.name.in_({"TEACHER", "ACADEMIC_COORDINATOR", "HOD", "MENTOR"}),
            )
            .order_by(User.name)
            .distinct()
        )
        teachers = [
            CoordinatorTeacherOption(
                id=user.id,
                name=user.name,
                employee_code=profile.employee_code if profile else user.employee_code,
                department_id=profile.department_id if profile else None,
                department_name=department_name,
                designation=profile.designation if profile else None,
                is_active=user.is_active,
            )
            for user, profile, department_name in teacher_rows.all()
        ]

        slot_filters = [
            TimetableSlot.tenant_id == tenant_id,
            TimetableSlot.effective_from <= today,
            or_(
                TimetableSlot.effective_to.is_(None),
                TimetableSlot.effective_to >= today,
            ),
        ]
        if class_id is not None:
            slot_filters.append(TimetableSlot.class_id == class_id)
        slot_rows = await db.execute(
            select(
                TimetableSlot,
                SchoolClass.name.label("class_name"),
                Department.name.label("department_name"),
                Subject.name.label("subject_name"),
                Subject.code.label("subject_code"),
                User.name.label("teacher_name"),
            )
            .join(
                SchoolClass,
                and_(
                    SchoolClass.id == TimetableSlot.class_id,
                    SchoolClass.tenant_id == tenant_id,
                ),
            )
            .outerjoin(
                Department,
                and_(
                    Department.id == SchoolClass.department_id,
                    Department.tenant_id == tenant_id,
                ),
            )
            .outerjoin(
                Subject,
                and_(Subject.id == TimetableSlot.subject_id, Subject.tenant_id == tenant_id),
            )
            .outerjoin(
                User,
                and_(User.id == TimetableSlot.teacher_id, User.tenant_id == tenant_id),
            )
            .where(*slot_filters)
            .order_by(SchoolClass.name, TimetableSlot.day_of_week, TimetableSlot.period_number)
        )
        slots = [
            CoordinatorTimetableSlot(
                id=slot.id,
                class_id=slot.class_id,
                class_name=class_name,
                department_name=department_name,
                day_of_week=slot.day_of_week,
                period_number=slot.period_number,
                start_time=slot.start_time,
                end_time=slot.end_time,
                subject_id=slot.subject_id,
                subject_code=subject_code,
                subject_name=subject_name,
                teacher_id=slot.teacher_id,
                teacher_name=teacher_name,
                room_no=slot.room_no,
                slot_type=slot.slot_type,
                effective_from=slot.effective_from,
                effective_to=slot.effective_to,
            )
            for slot, class_name, department_name, subject_name, subject_code, teacher_name in slot_rows.all()
        ]
        return CoordinatorTimetableGrid(
            classes=classes,
            subjects=subjects,
            teachers=teachers,
            slots=slots,
            period_labels=_PERIOD_LABELS,
        )

    @staticmethod
    async def create_slot(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        coordinator: User,
        payload: CoordinatorSlotCreate,
    ) -> CoordinatorTimetableSlot:
        await CoordinatorService._ensure_class(db, tenant_id, payload.class_id)
        if payload.subject_id is not None:
            await CoordinatorService._ensure_subject(db, tenant_id, payload.subject_id)
        if payload.teacher_id is not None:
            await CoordinatorService._ensure_teacher(db, tenant_id, payload.teacher_id)
        if payload.slot_type == "CLASS" and (payload.subject_id is None or payload.teacher_id is None):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A class slot needs both a subject and its assigned teacher.")
        if payload.subject_id is not None and payload.teacher_id is not None:
            await CoordinatorService._ensure_teaching_assignment(db, tenant_id, payload.class_id, payload.subject_id, payload.teacher_id)
        await CoordinatorService._assert_slot_available(
            db, tenant_id, day=payload.day_of_week, period=payload.period_number,
            starts=payload.effective_from, ends=payload.effective_to,
            teacher_id=payload.teacher_id, room_no=payload.room_no,
        )

        # The schema's unique key is
        # (class_id, day_of_week, period_number, effective_from).  The
        # coordinator's effective_from is the first day a new term starts; a
        # later change reuses the same key and gets a conflict we translate
        # into a friendly 409.
        existing = await db.execute(
            select(TimetableSlot).where(
                TimetableSlot.tenant_id == tenant_id,
                TimetableSlot.class_id == payload.class_id,
                TimetableSlot.day_of_week == payload.day_of_week,
                TimetableSlot.period_number == payload.period_number,
                TimetableSlot.effective_from == payload.effective_from,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="A slot already exists for that class/day/period on the given effective date.",
            )

        # The client sends academic_year_id for schema compatibility, but a
        # coordinator is always acting on the institution's current year; we
        # accept whatever they sent only if it matches the current year, and
        # otherwise fall back to the canonical one.  This keeps the wire
        # contract uniform while preventing a coordinator from writing a slot
        # into a closed year.
        current_year = await CoordinatorService._current_year(db, tenant_id)
        if current_year is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No active academic year is configured for this institution.",
            )
        if payload.academic_year_id and payload.academic_year_id != current_year.id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The selected academic year is not the current one.",
            )

        slot = TimetableSlot(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            class_id=payload.class_id,
            academic_year_id=current_year.id,
            day_of_week=payload.day_of_week,
            period_number=payload.period_number,
            start_time=payload.start_time,
            end_time=payload.end_time,
            subject_id=payload.subject_id,
            teacher_id=payload.teacher_id,
            room_no=payload.room_no,
            slot_type=payload.slot_type,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
        )
        db.add(slot)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="A slot already exists for that class/day/period on the given effective date.",
            ) from exc

        AuditService.record(
            db,
            actor=coordinator,
            actor_role="ACADEMIC_COORDINATOR",
            action="CREATE_TIMETABLE_SLOT",
            entity="TimetableSlot",
            entity_id=slot.id,
            tenant_id=tenant_id,
            new_value={
                "class_id": str(slot.class_id),
                "day_of_week": slot.day_of_week,
                "period_number": slot.period_number,
                "teacher_id": str(slot.teacher_id) if slot.teacher_id else None,
                "subject_id": str(slot.subject_id) if slot.subject_id else None,
                "room_no": slot.room_no,
                "slot_type": slot.slot_type,
            },
        )
        return await CoordinatorService._slot_dto(db, tenant_id, slot)

    @staticmethod
    async def update_slot(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        coordinator: User,
        slot_id: uuid.UUID,
        payload: CoordinatorSlotUpdate,
    ) -> CoordinatorTimetableSlot:
        slot = (
            await db.execute(
                select(TimetableSlot).where(
                    TimetableSlot.id == slot_id, TimetableSlot.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if slot is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Slot not found")
        before = {
            "class_id": str(slot.class_id),
            "day_of_week": slot.day_of_week,
            "period_number": slot.period_number,
            "start_time": slot.start_time.isoformat() if slot.start_time else None,
            "end_time": slot.end_time.isoformat() if slot.end_time else None,
            "subject_id": str(slot.subject_id) if slot.subject_id else None,
            "teacher_id": str(slot.teacher_id) if slot.teacher_id else None,
            "room_no": slot.room_no,
            "slot_type": slot.slot_type,
            "effective_from": slot.effective_from.isoformat() if slot.effective_from else None,
            "effective_to": slot.effective_to.isoformat() if slot.effective_to else None,
        }
        if payload.class_id is not None:
            slot.class_id = payload.class_id
        if payload.day_of_week is not None:
            slot.day_of_week = payload.day_of_week
        if payload.period_number is not None:
            slot.period_number = payload.period_number
        if payload.start_time is not None:
            slot.start_time = payload.start_time
        if payload.end_time is not None:
            slot.end_time = payload.end_time
        if payload.subject_id is not None:
            await CoordinatorService._ensure_subject(db, tenant_id, payload.subject_id)
            slot.subject_id = payload.subject_id
        if payload.teacher_id is not None:
            await CoordinatorService._ensure_teacher(db, tenant_id, payload.teacher_id)
            slot.teacher_id = payload.teacher_id
        if payload.room_no is not None:
            slot.room_no = payload.room_no
        if payload.slot_type is not None:
            slot.slot_type = payload.slot_type
        if payload.effective_from is not None:
            slot.effective_from = payload.effective_from
        if payload.effective_to is not None:
            slot.effective_to = payload.effective_to

        if slot.slot_type == "CLASS" and (slot.subject_id is None or slot.teacher_id is None):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A class slot needs both a subject and its assigned teacher.")
        if slot.subject_id is not None and slot.teacher_id is not None:
            await CoordinatorService._ensure_teaching_assignment(db, tenant_id, slot.class_id, slot.subject_id, slot.teacher_id)
        await CoordinatorService._assert_slot_available(
            db, tenant_id, day=slot.day_of_week, period=slot.period_number,
            starts=slot.effective_from, ends=slot.effective_to, teacher_id=slot.teacher_id,
            room_no=slot.room_no, exclude_slot_id=slot.id,
        )
        await db.flush()
        AuditService.record(
            db,
            actor=coordinator,
            actor_role="ACADEMIC_COORDINATOR",
            action="UPDATE_TIMETABLE_SLOT",
            entity="TimetableSlot",
            entity_id=slot.id,
            tenant_id=tenant_id,
            old_value=before,
            new_value={
                "class_id": str(slot.class_id),
                "day_of_week": slot.day_of_week,
                "period_number": slot.period_number,
                "start_time": slot.start_time.isoformat() if slot.start_time else None,
                "end_time": slot.end_time.isoformat() if slot.end_time else None,
                "subject_id": str(slot.subject_id) if slot.subject_id else None,
                "teacher_id": str(slot.teacher_id) if slot.teacher_id else None,
                "room_no": slot.room_no,
                "slot_type": slot.slot_type,
                "effective_from": slot.effective_from.isoformat() if slot.effective_from else None,
                "effective_to": slot.effective_to.isoformat() if slot.effective_to else None,
            },
        )
        return await CoordinatorService._slot_dto(db, tenant_id, slot)

    @staticmethod
    async def delete_slot(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        coordinator: User,
        slot_id: uuid.UUID,
    ) -> None:
        slot = (
            await db.execute(
                select(TimetableSlot).where(
                    TimetableSlot.id == slot_id, TimetableSlot.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if slot is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Slot not found")
        await db.delete(slot)
        await db.flush()
        AuditService.record(
            db,
            actor=coordinator,
            actor_role="ACADEMIC_COORDINATOR",
            action="DELETE_TIMETABLE_SLOT",
            entity="TimetableSlot",
            entity_id=slot_id,
            tenant_id=tenant_id,
            old_value={
                "class_id": str(slot.class_id),
                "day_of_week": slot.day_of_week,
                "period_number": slot.period_number,
            },
        )

    # ── C-AC-04 conflict checker ────────────────────────────────────────────

    @staticmethod
    async def conflicts(
        db: AsyncSession, tenant_id: uuid.UUID
    ) -> CoordinatorConflictReport:
        today = await CoordinatorService._tenant_today(db, tenant_id)
        items = await CoordinatorService._compute_conflicts(db, tenant_id, today)
        return CoordinatorConflictReport(
            total=len(items),
            teacher_conflicts=sum(1 for item in items if item.kind == "TEACHER_DOUBLE_BOOKED"),
            room_conflicts=sum(1 for item in items if item.kind == "ROOM_DOUBLE_BOOKED"),
            items=items,
        )

    @staticmethod
    async def _compute_conflicts(
        db: AsyncSession, tenant_id: uuid.UUID, today: date
    ) -> list[CoordinatorConflictRow]:
        rows = await db.execute(
            select(
                TimetableSlot,
                SchoolClass.name.label("class_name"),
                Subject.name.label("subject_name"),
                User.name.label("teacher_name"),
            )
            .join(
                SchoolClass,
                and_(
                    SchoolClass.id == TimetableSlot.class_id,
                    SchoolClass.tenant_id == tenant_id,
                ),
            )
            .outerjoin(
                Subject,
                and_(Subject.id == TimetableSlot.subject_id, Subject.tenant_id == tenant_id),
            )
            .outerjoin(
                User,
                and_(User.id == TimetableSlot.teacher_id, User.tenant_id == tenant_id),
            )
            .where(
                TimetableSlot.tenant_id == tenant_id,
                TimetableSlot.effective_from <= today,
                or_(
                    TimetableSlot.effective_to.is_(None),
                    TimetableSlot.effective_to >= today,
                ),
            )
        )
        by_teacher: dict[tuple[str, int, int], list[tuple[TimetableSlot, str, str, str]]] = (
            defaultdict(list)
        )
        by_room: dict[tuple[str, int, int], list[tuple[TimetableSlot, str, str, str]]] = defaultdict(
            list
        )
        for slot, class_name, subject_name, teacher_name in rows.all():
            cell = (slot.day_of_week, slot.period_number)
            if slot.teacher_id is not None:
                by_teacher[(str(slot.teacher_id), *cell)].append(
                    (slot, class_name, subject_name, teacher_name or "")
                )
            if slot.room_no:
                by_room[(slot.room_no, *cell)].append(
                    (slot, class_name, subject_name, teacher_name or "")
                )
        conflicts: list[CoordinatorConflictRow] = []
        for (resource, day, period), entries in by_teacher.items():
            if len(entries) < 2:
                continue
            class_ids = [slot.id for slot, *_ in entries]
            class_names = [name for _, name, *_ in entries]
            subject_names = [name for _, _, name, _ in entries]
            teacher_names = [name for _, _, _, name in entries]
            conflicts.append(
                CoordinatorConflictRow(
                    id=f"t-{resource}-{day}-{period}",
                    kind="TEACHER_DOUBLE_BOOKED",
                    day_of_week=day,
                    period_number=period,
                    resource=teacher_names[0] or "Unknown teacher",
                    class_ids=class_ids,
                    class_names=class_names,
                    subject_names=subject_names,
                    teacher_names=teacher_names,
                )
            )
        for (resource, day, period), entries in by_room.items():
            if len(entries) < 2:
                continue
            class_ids = [slot.id for slot, *_ in entries]
            class_names = [name for _, name, *_ in entries]
            subject_names = [name for _, _, name, _ in entries]
            teacher_names = [name for _, _, _, name in entries]
            conflicts.append(
                CoordinatorConflictRow(
                    id=f"r-{resource}-{day}-{period}",
                    kind="ROOM_DOUBLE_BOOKED",
                    day_of_week=day,
                    period_number=period,
                    resource=f"Room {resource}",
                    class_ids=class_ids,
                    class_names=class_names,
                    subject_names=subject_names,
                    teacher_names=teacher_names,
                )
            )
        return conflicts

    # ── C-AC-05 substitution board ──────────────────────────────────────────

    @staticmethod
    async def substitution_board(
        db: AsyncSession, tenant_id: uuid.UUID
    ) -> CoordinatorSubstitutionBoard:
        today = await CoordinatorService._tenant_today(db, tenant_id)
        rows = await CoordinatorService._substitution_rows(db, tenant_id, today)
        today_count = sum(1 for row in rows if row["when"] == "TODAY")
        upcoming_count = sum(1 for row in rows if row["when"] == "UPCOMING")
        past_count = sum(1 for row in rows if row["when"] == "PAST")
        live_teachers = {
            row["substitute_teacher_id"]
            for row in rows
            if row["when"] in ("TODAY", "UPCOMING")
        }
        items = [await CoordinatorService._substitution_dto(db, tenant_id, row) for row in rows]
        return CoordinatorSubstitutionBoard(
            today=today,
            rows=items,
            counts={
                "today": today_count,
                "upcoming": upcoming_count,
                "past": past_count,
                "covering_teachers": len(live_teachers),
                "total": len(rows),
            },
            can_edit=True,
        )

    @staticmethod
    async def substitution_form_context(
        db: AsyncSession, tenant_id: uuid.UUID
    ) -> CoordinatorSubstitutionFormContext:
        today = await CoordinatorService._tenant_today(db, tenant_id)
        slots = await CoordinatorService._substitutable_slots(db, tenant_id)
        candidates = await CoordinatorService._substitute_candidates(db, tenant_id)
        busy_cells = await CoordinatorService._busy_cells(db, tenant_id)
        rows = await CoordinatorService._substitution_rows(db, tenant_id, today)
        taken = [
            CoordinatorSubstitutionTakenKey(
                slot_id=row["slot_id"],
                date=row["date"],
                substitute_teacher_id=row["substitute_teacher_id"],
            )
            for row in rows
        ]
        return CoordinatorSubstitutionFormContext(
            today=today,
            slots=slots,
            candidates=candidates,
            taken=taken,
            busy_cells=busy_cells,
        )

    @staticmethod
    async def create_substitution(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        coordinator: User,
        payload: CoordinatorSubstitutionCreate,
    ) -> CoordinatorSubstitutionRow:
        slot = (
            await db.execute(
                select(TimetableSlot).where(
                    TimetableSlot.id == payload.slot_id,
                    TimetableSlot.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if slot is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Timetable slot not found")
        today = await CoordinatorService._tenant_today(db, tenant_id)
        if payload.date < today:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot arrange cover for a date that has already passed.",
            )
        if slot.teacher_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This period has no assigned teacher to cover.",
            )
        if payload.substitute_teacher_id == slot.teacher_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The substitute cannot be the same teacher who owns the period.",
            )
        await CoordinatorService._ensure_teacher(
            db, tenant_id, payload.substitute_teacher_id
        )

        # UNIQUE (slot_id, date) — database §7.8.  The unique key stops two
        # coordinators from arranging cover twice for the same period; we
        # pre-check so the conflict is friendly before the INSERT.
        existing = await db.execute(
            select(TimetableSubstitution).where(
                TimetableSubstitution.tenant_id == tenant_id,
                TimetableSubstitution.slot_id == payload.slot_id,
                TimetableSubstitution.date == payload.date,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="This period already has a substitute on that date.",
            )

        substitution = TimetableSubstitution(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            slot_id=payload.slot_id,
            date=payload.date,
            substitute_teacher_id=payload.substitute_teacher_id,
            original_teacher_id=slot.teacher_id,
            reason=payload.reason,
            arranged_by=coordinator.id,
        )
        db.add(substitution)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="This period already has a substitute on that date.",
            ) from exc

        AuditService.record(
            db,
            actor=coordinator,
            actor_role="ACADEMIC_COORDINATOR",
            action="CREATE_SUBSTITUTION",
            entity="TimetableSubstitution",
            entity_id=substitution.id,
            tenant_id=tenant_id,
            new_value={
                "slot_id": str(substitution.slot_id),
                "date": str(substitution.date),
                "substitute_teacher_id": str(substitution.substitute_teacher_id),
                "original_teacher_id": str(substitution.original_teacher_id),
                "reason": substitution.reason,
            },
        )
        rows = await CoordinatorService._substitution_rows_for(
            db, tenant_id, today, [substitution.id]
        )
        return await CoordinatorService._substitution_dto(db, tenant_id, rows[0])

    @staticmethod
    async def delete_substitution(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        coordinator: User,
        substitution_id: uuid.UUID,
    ) -> None:
        sub = (
            await db.execute(
                select(TimetableSubstitution).where(
                    TimetableSubstitution.id == substitution_id,
                    TimetableSubstitution.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if sub is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Substitution not found")
        await db.delete(sub)
        await db.flush()
        AuditService.record(
            db,
            actor=coordinator,
            actor_role="ACADEMIC_COORDINATOR",
            action="DELETE_SUBSTITUTION",
            entity="TimetableSubstitution",
            entity_id=substitution_id,
            tenant_id=tenant_id,
            old_value={
                "slot_id": str(sub.slot_id),
                "date": str(sub.date),
                "substitute_teacher_id": str(sub.substitute_teacher_id),
            },
        )

    # ── C-AC-07 academic calendar ──────────────────────────────────────────

    @staticmethod
    async def events(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        from_date: date | None,
        to_date: date | None,
        event_type: str | None = None,
        include_past: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> CoordinatorEventPage:
        limit, offset = CoordinatorService._page_bounds(limit, offset)
        today = await CoordinatorService._tenant_today(db, tenant_id)
        start = from_date or (today if not include_past else today - timedelta(days=365))
        end = to_date or (today + timedelta(days=120))
        if start > end:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="from_date must be on or before to_date",
            )
        if event_type and event_type not in {e.value for e in AcademicEventType}:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown event type"
            )

        clauses = [
            AcademicEvent.tenant_id == tenant_id,
            AcademicEvent.end_date >= start,
            AcademicEvent.start_date <= end,
        ]
        if event_type:
            clauses.append(AcademicEvent.event_type == AcademicEventType(event_type))
        if not include_past:
            clauses.append(AcademicEvent.end_date >= today)

        total = (
            await db.execute(select(func.count(AcademicEvent.id)).where(*clauses))
        ).scalar() or 0
        rows = await db.execute(
            select(AcademicEvent)
            .where(*clauses)
            .order_by(AcademicEvent.start_date, AcademicEvent.created_at)
            .limit(limit)
            .offset(offset)
        )
        items = [
            await CoordinatorService._event_dto(db, tenant_id, event)
            for event in rows.scalars().all()
        ]
        return CoordinatorEventPage(total=int(total), limit=limit, offset=offset, items=items)

    @staticmethod
    async def create_event(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        coordinator: User,
        payload: CoordinatorEventCreate,
    ) -> CoordinatorEventRow:
        year = None
        if payload.academic_year_id:
            year = (
                await db.execute(
                    select(AcademicYear).where(
                        AcademicYear.id == payload.academic_year_id,
                        AcademicYear.tenant_id == tenant_id,
                    )
                )
            ).scalar_one_or_none()
        else:
            year = await CoordinatorService._current_year(db, tenant_id)

        if year is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Academic year not found")
        if payload.applies_to == AcademicEventScope.DEPARTMENT.value and payload.scope_id:
            department = (
                await db.execute(
                    select(Department).where(
                        Department.id == payload.scope_id,
                        Department.tenant_id == tenant_id,
                    )
                )
            ).scalar_one_or_none()
            if department is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, detail="Department not found"
                )
        elif payload.applies_to == AcademicEventScope.CLASS.value and payload.scope_id:
            await CoordinatorService._ensure_class(db, tenant_id, payload.scope_id)

        event = AcademicEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            academic_year_id=year.id,
            title=payload.title.strip(),
            description=(payload.description or "").strip() or None,
            event_type=AcademicEventType(payload.event_type),
            start_date=payload.start_date,
            end_date=payload.end_date,
            is_holiday=payload.is_holiday,
            applies_to=AcademicEventScope(payload.applies_to),
            scope_id=payload.scope_id,
            color=payload.color or "#3B82F6",
            created_by=coordinator.id,
        )
        db.add(event)
        await db.flush()
        AuditService.record(
            db,
            actor=coordinator,
            actor_role="ACADEMIC_COORDINATOR",
            action="CREATE_ACADEMIC_EVENT",
            entity="AcademicEvent",
            entity_id=event.id,
            tenant_id=tenant_id,
            new_value={
                "title": event.title,
                "event_type": event.event_type.value,
                "start_date": str(event.start_date),
                "end_date": str(event.end_date),
                "is_holiday": event.is_holiday,
                "applies_to": event.applies_to.value,
            },
        )
        return await CoordinatorService._event_dto(db, tenant_id, event)

    @staticmethod
    async def update_event(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        coordinator: User,
        event_id: uuid.UUID,
        payload: CoordinatorEventUpdate,
    ) -> CoordinatorEventRow:
        event = (
            await db.execute(
                select(AcademicEvent).where(
                    AcademicEvent.id == event_id, AcademicEvent.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if event is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Event not found")
        before = {
            "title": event.title,
            "start_date": str(event.start_date),
            "end_date": str(event.end_date),
            "is_holiday": event.is_holiday,
            "color": event.color,
        }
        if payload.title is not None:
            event.title = payload.title.strip()
        if payload.description is not None:
            event.description = payload.description.strip() or None
        if payload.start_date is not None:
            event.start_date = payload.start_date
        if payload.end_date is not None:
            event.end_date = payload.end_date
        if payload.is_holiday is not None and event.event_type == AcademicEventType.HOLIDAY:
            event.is_holiday = payload.is_holiday
        if payload.color is not None:
            event.color = payload.color
        if event.end_date < event.start_date:
            await db.rollback()
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="end_date cannot be before start_date",
            )
        await db.flush()
        AuditService.record(
            db,
            actor=coordinator,
            actor_role="ACADEMIC_COORDINATOR",
            action="UPDATE_ACADEMIC_EVENT",
            entity="AcademicEvent",
            entity_id=event.id,
            tenant_id=tenant_id,
            old_value=before,
            new_value={
                "title": event.title,
                "start_date": str(event.start_date),
                "end_date": str(event.end_date),
                "is_holiday": event.is_holiday,
                "color": event.color,
            },
        )
        return await CoordinatorService._event_dto(db, tenant_id, event)

    @staticmethod
    async def delete_event(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        coordinator: User,
        event_id: uuid.UUID,
    ) -> None:
        event = (
            await db.execute(
                select(AcademicEvent).where(
                    AcademicEvent.id == event_id, AcademicEvent.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if event is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Event not found")
        await db.delete(event)
        await db.flush()
        AuditService.record(
            db,
            actor=coordinator,
            actor_role="ACADEMIC_COORDINATOR",
            action="DELETE_ACADEMIC_EVENT",
            entity="AcademicEvent",
            entity_id=event_id,
            tenant_id=tenant_id,
            old_value={"title": event.title, "start_date": str(event.start_date)},
        )

    # ── C-AC-08 post academic notice ───────────────────────────────────────

    @staticmethod
    async def notices(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        query: str | None,
        include_expired: bool,
        limit: int = 50,
        offset: int = 0,
    ) -> CoordinatorNoticePage:
        limit, offset = CoordinatorService._page_bounds(limit, offset)
        now = datetime.now(timezone.utc)
        clauses = [Notice.tenant_id == tenant_id, Notice.deleted_at.is_(None)]
        if not include_expired:
            clauses.append(or_(Notice.expires_at.is_(None), Notice.expires_at > now))
        if query and query.strip():
            needle = f"%{query.strip().lower()}%"
            clauses.append(
                or_(
                    func.lower(Notice.title).like(needle),
                    func.lower(Notice.body).like(needle),
                )
            )
        total = (
            await db.execute(select(func.count(Notice.id)).where(*clauses))
        ).scalar() or 0
        read_counts = (
            select(
                NoticeRead.notice_id.label("notice_id"),
                func.count(NoticeRead.id).label("read_count"),
            )
            .group_by(NoticeRead.notice_id)
            .subquery()
        )
        rows = await db.execute(
            select(
                Notice,
                User.name.label("author_name"),
                func.coalesce(read_counts.c.read_count, 0).label("read_count"),
            )
            .outerjoin(
                User,
                and_(User.id == Notice.author_id, User.tenant_id == tenant_id),
            )
            .outerjoin(read_counts, read_counts.c.notice_id == Notice.id)
            .where(*clauses)
            .order_by(Notice.is_pinned.desc(), Notice.published_at.desc())
            .limit(limit)
            .offset(offset)
        )
        notices = rows.all()
        target_names = await CoordinatorService._notice_target_names(
            db, tenant_id, [notice for notice, _, _ in notices]
        )
        items = []
        for notice, author_name, read_count in notices:
            row = CoordinatorService._notice_row(
                notice, author_name, int(read_count or 0),
                target_names.get((_value(notice.target_scope), notice.target_id)),
            )
            row.attachments = await PrincipalService._notice_attachments(db, notice.id)
            items.append(row)
        return CoordinatorNoticePage(total=int(total), limit=limit, offset=offset, items=items)

    @staticmethod
    async def create_notice(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        coordinator: User,
        payload: CoordinatorNoticeCreate,
    ) -> CoordinatorNoticeRow:
        await CoordinatorService._ensure_class(db, tenant_id, payload.target_id)
        title = payload.title.strip()
        body = payload.body.strip()
        # §4.5: the coordinator's notice grant is class-scoped. The title
        # auto-prefix "(Academic) " is the documented signal to the class
        # teacher that the message comes from the academic office.
        if not title.lower().startswith("(academic)"):
            title = f"(Academic) {title}"
        notice = Notice(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            title=title,
            body=body,
            author_id=coordinator.id,
            target_scope=NoticeScope.CLASS,
            target_id=payload.target_id,
            priority=NoticePriority(payload.priority),
            is_pinned=payload.is_pinned,
            published_at=datetime.now(timezone.utc),
            expires_at=payload.expires_at,
        )
        db.add(notice)
        await db.flush()
        attachments = await PrincipalService._save_notice_attachments(db, notice.tenant_id, notice.id, payload.attachments)
        AuditService.record(
            db,
            actor=coordinator,
            actor_role="ACADEMIC_COORDINATOR",
            action="CREATE_NOTICE",
            entity="Notice",
            entity_id=notice.id,
            tenant_id=tenant_id,
            new_value={
                "title": notice.title,
                "target_scope": notice.target_scope.value,
                "target_id": str(notice.target_id),
                "priority": notice.priority.value,
                "is_pinned": notice.is_pinned,
            },
        )
        row = CoordinatorService._notice_row(
            notice,
            coordinator.name,
            0,
            None,
        )
        row.attachments = attachments
        return row

    @staticmethod
    async def notice_targets(
        db: AsyncSession, tenant_id: uuid.UUID
    ) -> CoordinatorNoticeTargets:
        departments = (
            await db.execute(
                select(Department).where(
                    Department.tenant_id == tenant_id, Department.is_active.is_(True)
                ).order_by(Department.name)
            )
        ).scalars().all()
        classes = await db.execute(
            select(SchoolClass, Department.name)
            .outerjoin(
                Department,
                and_(
                    Department.id == SchoolClass.department_id,
                    Department.tenant_id == tenant_id,
                ),
            )
            .where(SchoolClass.tenant_id == tenant_id, SchoolClass.is_active.is_(True))
            .order_by(Department.name.nulls_last(), SchoolClass.name)
        )
        return CoordinatorNoticeTargets(
            departments=[
                CoordinatorTargetOption(id=dept.id, name=dept.name) for dept in departments
            ],
            classes=[
                CoordinatorClassOption(
                    id=school_class.id,
                    name=school_class.name,
                    department_id=school_class.department_id,
                    department_name=department_name,
                )
                for school_class, department_name in classes.all()
            ],
        )

    # ── Internal DTO builders ───────────────────────────────────────────────

    @staticmethod
    async def _slot_dto(
        db: AsyncSession, tenant_id: uuid.UUID, slot: TimetableSlot
    ) -> CoordinatorTimetableSlot:
        return await CoordinatorService._slot_dto_from_id(db, tenant_id, slot)

    @staticmethod
    async def _slot_dto_from_id(
        db: AsyncSession, tenant_id: uuid.UUID, slot: TimetableSlot
    ) -> CoordinatorTimetableSlot:
        joined = await db.execute(
            select(
                SchoolClass.name.label("class_name"),
                Department.name.label("department_name"),
                Subject.name.label("subject_name"),
                Subject.code.label("subject_code"),
                User.name.label("teacher_name"),
            )
            .select_from(TimetableSlot)
            .join(
                SchoolClass,
                and_(
                    SchoolClass.id == TimetableSlot.class_id,
                    SchoolClass.tenant_id == tenant_id,
                ),
            )
            .outerjoin(
                Department,
                and_(
                    Department.id == SchoolClass.department_id,
                    Department.tenant_id == tenant_id,
                ),
            )
            .outerjoin(
                Subject,
                and_(Subject.id == TimetableSlot.subject_id, Subject.tenant_id == tenant_id),
            )
            .outerjoin(
                User,
                and_(User.id == TimetableSlot.teacher_id, User.tenant_id == tenant_id),
            )
            .where(TimetableSlot.id == slot.id)
        )
        row = joined.one()
        return CoordinatorTimetableSlot(
            id=slot.id,
            class_id=slot.class_id,
            class_name=row.class_name,
            department_name=row.department_name,
            day_of_week=slot.day_of_week,
            period_number=slot.period_number,
            start_time=slot.start_time,
            end_time=slot.end_time,
            subject_id=slot.subject_id,
            subject_code=row.subject_code,
            subject_name=row.subject_name,
            teacher_id=slot.teacher_id,
            teacher_name=row.teacher_name,
            room_no=slot.room_no,
            slot_type=slot.slot_type,
            effective_from=slot.effective_from,
            effective_to=slot.effective_to,
        )

    @staticmethod
    async def _substitutable_slots(
        db: AsyncSession, tenant_id: uuid.UUID
    ) -> list[CoordinatorSubstitutableSlot]:
        today = await CoordinatorService._tenant_today(db, tenant_id)
        rows = await db.execute(
            select(
                TimetableSlot,
                SchoolClass.name.label("class_name"),
                Subject.name.label("subject_name"),
                Subject.code.label("subject_code"),
                User.name.label("teacher_name"),
            )
            .join(
                SchoolClass,
                and_(
                    SchoolClass.id == TimetableSlot.class_id,
                    SchoolClass.tenant_id == tenant_id,
                ),
            )
            .outerjoin(
                Subject,
                and_(Subject.id == TimetableSlot.subject_id, Subject.tenant_id == tenant_id),
            )
            .outerjoin(
                User,
                and_(User.id == TimetableSlot.teacher_id, User.tenant_id == tenant_id),
            )
            .where(
                TimetableSlot.tenant_id == tenant_id,
                TimetableSlot.slot_type != "BREAK",
                TimetableSlot.teacher_id.is_not(None),
                TimetableSlot.effective_from <= today,
                or_(
                    TimetableSlot.effective_to.is_(None),
                    TimetableSlot.effective_to >= today,
                ),
            )
            .order_by(
                TimetableSlot.day_of_week,
                TimetableSlot.period_number,
                SchoolClass.name,
            )
        )
        return [
            CoordinatorSubstitutableSlot(
                slot_id=slot.id,
                class_id=slot.class_id,
                class_name=class_name,
                day_of_week=slot.day_of_week,
                period_number=slot.period_number,
                start_time=slot.start_time,
                end_time=slot.end_time,
                subject_id=slot.subject_id,
                subject_code=subject_code,
                subject_name=subject_name,
                teacher_id=slot.teacher_id,
                teacher_name=teacher_name,
                room_no=slot.room_no,
                slot_type=slot.slot_type,
            )
            for slot, class_name, subject_name, subject_code, teacher_name in rows.all()
        ]

    @staticmethod
    async def _substitute_candidates(
        db: AsyncSession, tenant_id: uuid.UUID
    ) -> list[CoordinatorSubstituteCandidate]:
        teaching = (
            select(TimetableSlot.teacher_id)
            .where(
                TimetableSlot.tenant_id == tenant_id,
                TimetableSlot.slot_type != "BREAK",
                TimetableSlot.teacher_id.is_not(None),
            )
            .distinct()
        )
        rows = await db.execute(
            select(
                User,
                StaffProfile,
                Department.name.label("department_name"),
            )
            .outerjoin(
                StaffProfile,
                and_(StaffProfile.user_id == User.id, StaffProfile.tenant_id == tenant_id),
            )
            .outerjoin(
                Department,
                and_(
                    Department.id == StaffProfile.department_id,
                    Department.tenant_id == tenant_id,
                ),
            )
            .where(
                User.tenant_id == tenant_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
                User.id.in_(teaching),
            )
            .order_by(User.name)
        )
        return [
            CoordinatorSubstituteCandidate(
                id=user.id,
                name=user.name,
                department_id=profile.department_id if profile else None,
                department_name=department_name,
                designation=profile.designation if profile else None,
                is_active=user.is_active,
            )
            for user, profile, department_name in rows.all()
        ]

    @staticmethod
    async def _busy_cells(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, list[str]]:
        today = await CoordinatorService._tenant_today(db, tenant_id)
        rows = await db.execute(
            select(TimetableSlot.teacher_id, TimetableSlot.day_of_week, TimetableSlot.period_number)
            .where(
                TimetableSlot.tenant_id == tenant_id,
                TimetableSlot.slot_type != "BREAK",
                TimetableSlot.teacher_id.is_not(None),
                TimetableSlot.effective_from <= today,
                or_(
                    TimetableSlot.effective_to.is_(None),
                    TimetableSlot.effective_to >= today,
                ),
            )
        )
        cells: dict[str, list[str]] = defaultdict(list)
        for teacher_id, day, period in rows.all():
            cells[str(teacher_id)].append(f"{day}-{period}")
        return cells

    @staticmethod
    async def _substitution_rows(
        db: AsyncSession, tenant_id: uuid.UUID, today: date
    ) -> list[dict]:
        SubstituteUser = aliased(User, name="substitute_user")
        OriginalUser = aliased(User, name="original_user")
        ArrangedUser = aliased(User, name="arranged_user")
        rows = await db.execute(
            select(
                TimetableSubstitution,
                TimetableSlot.class_id,
                TimetableSlot.day_of_week,
                TimetableSlot.period_number,
                TimetableSlot.start_time,
                TimetableSlot.end_time,
                TimetableSlot.room_no,
                TimetableSlot.slot_type,
                SchoolClass.name.label("class_name"),
                Subject.name.label("subject_name"),
                Subject.code.label("subject_code"),
                SubstituteUser.name.label("substitute_teacher_name"),
                OriginalUser.name.label("original_teacher_name"),
                ArrangedUser.name.label("arranged_by_name"),
            )
            .join(
                TimetableSlot,
                and_(
                    TimetableSlot.id == TimetableSubstitution.slot_id,
                    TimetableSlot.tenant_id == tenant_id,
                ),
            )
            .join(
                SchoolClass,
                and_(
                    SchoolClass.id == TimetableSlot.class_id,
                    SchoolClass.tenant_id == tenant_id,
                ),
            )
            .outerjoin(
                Subject,
                and_(Subject.id == TimetableSlot.subject_id, Subject.tenant_id == tenant_id),
            )
            .outerjoin(
                SubstituteUser,
                and_(
                    SubstituteUser.id == TimetableSubstitution.substitute_teacher_id,
                    SubstituteUser.tenant_id == tenant_id,
                ),
            )
            .outerjoin(
                OriginalUser,
                and_(
                    OriginalUser.id == TimetableSubstitution.original_teacher_id,
                    OriginalUser.tenant_id == tenant_id,
                ),
            )
            .outerjoin(
                ArrangedUser,
                and_(
                    ArrangedUser.id == TimetableSubstitution.arranged_by,
                    ArrangedUser.tenant_id == tenant_id,
                ),
            )
            .where(TimetableSubstitution.tenant_id == tenant_id)
            .order_by(TimetableSubstitution.date, TimetableSlot.period_number)
        )
        out: list[dict] = []
        for (
            sub,
            class_id,
            day_of_week,
            period_number,
            start_time,
            end_time,
            room_no,
            slot_type,
            class_name,
            subject_name,
            subject_code,
            substitute_name,
            original_name,
            arranged_name,
        ) in rows.all():
            when = "TODAY" if sub.date == today else ("UPCOMING" if sub.date > today else "PAST")
            out.append(
                {
                    "id": sub.id,
                    "slot_id": sub.slot_id,
                    "date": sub.date,
                    "when": when,
                    "substitute_teacher_id": sub.substitute_teacher_id,
                    "substitute_teacher_name": substitute_name or "",
                    "original_teacher_id": sub.original_teacher_id,
                    "original_teacher_name": original_name or "",
                    "reason": sub.reason,
                    "arranged_by_id": sub.arranged_by,
                    "arranged_by_name": arranged_name,
                    "created_at": sub.created_at,
                    "class_id": class_id,
                    "class_name": class_name,
                    "day_of_week": day_of_week,
                    "period_number": period_number,
                    "start_time": start_time,
                    "end_time": end_time,
                    "room_no": room_no,
                    "slot_type": slot_type,
                    "subject_name": subject_name,
                    "subject_code": subject_code,
                }
            )
        return out

    @staticmethod
    async def _substitution_rows_for(
        db: AsyncSession, tenant_id: uuid.UUID, today: date, ids: list[uuid.UUID]
    ) -> list[dict]:
        rows = await CoordinatorService._substitution_rows(db, tenant_id, today)
        wanted = set(ids)
        return [row for row in rows if row["id"] in wanted]

    @staticmethod
    async def _substitution_dto(
        db: AsyncSession, tenant_id: uuid.UUID, row: dict
    ) -> CoordinatorSubstitutionRow:
        return CoordinatorSubstitutionRow(
            id=row["id"],
            slot_id=row["slot_id"],
            date=row["date"],
            when=row["when"],
            substitute_teacher_id=row["substitute_teacher_id"],
            substitute_teacher_name=row["substitute_teacher_name"],
            original_teacher_id=row["original_teacher_id"],
            original_teacher_name=row["original_teacher_name"],
            reason=row["reason"],
            arranged_by_id=row["arranged_by_id"],
            arranged_by_name=row["arranged_by_name"],
            created_at=row["created_at"],
            day_of_week=row["day_of_week"],
            period_number=row["period_number"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            subject_code=row["subject_code"],
            subject_name=row["subject_name"],
            class_id=row["class_id"],
            class_name=row["class_name"],
            room_no=row["room_no"],
            slot_type=row["slot_type"],
        )

    @staticmethod
    async def _event_rows(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        start: date,
        end: date,
        *,
        limit: int = 100,
    ) -> list[AcademicEvent]:
        rows = await db.execute(
            select(AcademicEvent)
            .where(
                AcademicEvent.tenant_id == tenant_id,
                AcademicEvent.end_date >= start,
                AcademicEvent.start_date <= end,
            )
            .order_by(AcademicEvent.start_date, AcademicEvent.created_at)
            .limit(limit)
        )
        return list(rows.scalars().all())

    @staticmethod
    async def _event_dto(
        db: AsyncSession, tenant_id: uuid.UUID, event: AcademicEvent
    ) -> CoordinatorEventRow:
        scope_name: str | None = None
        if event.applies_to == AcademicEventScope.DEPARTMENT and event.scope_id is not None:
            scope_name = (
                await db.execute(
                    select(Department.name).where(
                        Department.id == event.scope_id, Department.tenant_id == tenant_id
                    )
                )
            ).scalar_one_or_none()
        elif event.applies_to == AcademicEventScope.CLASS and event.scope_id is not None:
            scope_name = (
                await db.execute(
                    select(SchoolClass.name).where(
                        SchoolClass.id == event.scope_id, SchoolClass.tenant_id == tenant_id
                    )
                )
            ).scalar_one_or_none()
        creator_name: str | None = None
        if event.created_by is not None:
            creator_name = (
                await db.execute(
                    select(User.name).where(
                        User.id == event.created_by, User.tenant_id == tenant_id
                    )
                )
            ).scalar_one_or_none()
        return CoordinatorEventRow(
            id=event.id,
            title=event.title,
            description=event.description,
            event_type=event.event_type.value,
            start_date=event.start_date,
            end_date=event.end_date,
            is_holiday=event.is_holiday,
            applies_to=event.applies_to.value,
            scope_id=event.scope_id,
            scope_name=scope_name,
            color=event.color,
            created_by_name=creator_name,
        )

    @staticmethod
    def _notice_row(
        notice: Notice,
        author_name: str | None,
        read_count: int,
        target_name: str | None,
    ) -> CoordinatorNoticeRow:
        return CoordinatorNoticeRow(
            id=notice.id,
            title=notice.title,
            body=notice.body,
            author_id=notice.author_id,
            author_name=author_name,
            target_scope=_value(notice.target_scope) or "CLASS",
            target_id=notice.target_id,
            target_name=target_name,
            priority=_value(notice.priority) or "NORMAL",
            is_pinned=notice.is_pinned,
            published_at=notice.published_at,
            expires_at=notice.expires_at,
            read_count=read_count,
        )

    @staticmethod
    async def _notice_target_names(
        db: AsyncSession, tenant_id: uuid.UUID, notices: Iterable[Notice]
    ) -> dict[tuple[str, uuid.UUID | None], str | None]:
        notices = list(notices)
        class_ids = {
            notice.target_id
            for notice in notices
            if _value(notice.target_scope) == "CLASS" and notice.target_id is not None
        }
        department_ids = {
            notice.target_id
            for notice in notices
            if _value(notice.target_scope) == "DEPARTMENT" and notice.target_id is not None
        }
        names: dict[tuple[str, uuid.UUID | None], str | None] = {
            ("INSTITUTION", None): "Institution-wide"
        }
        if class_ids:
            rows = await db.execute(
                select(SchoolClass.id, SchoolClass.name).where(
                    SchoolClass.tenant_id == tenant_id, SchoolClass.id.in_(class_ids)
                )
            )
            names.update({("CLASS", identifier): name for identifier, name in rows.all()})
        if department_ids:
            rows = await db.execute(
                select(Department.id, Department.name).where(
                    Department.tenant_id == tenant_id, Department.id.in_(department_ids)
                )
            )
            names.update(
                {("DEPARTMENT", identifier): name for identifier, name in rows.all()}
            )
        return names

    @staticmethod
    def _page_bounds(limit: int, offset: int) -> tuple[int, int]:
        if not 1 <= limit <= 200:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="limit must be between 1 and 200",
            )
        if offset < 0:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="offset must be zero or greater",
            )
        return limit, offset
