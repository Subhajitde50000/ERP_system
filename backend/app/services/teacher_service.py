"""Teacher console workflows (C-TC-01 … C-TC-22).

Scope model — everything derives from what the signed-in teacher actually
teaches, resolved from the database on every call:

* ``teacher_subjects`` rows  → the subjects/classes they may mark attendance
  for, create exams/assignments/content in, and moderate discussions of;
* ``classes.class_teacher_id`` → the homeroom classes whose student leaves
  they may additionally review and post notices to.

Route ids alone never widen access: every mutating handler re-verifies the
referenced subject/class/thread/submission belongs to the caller's scope
before writing, exactly like the HOD department fence.
"""

from __future__ import annotations

import csv
import logging
import io
import json
import uuid

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic import AcademicYear, Department, SchoolClass, Subject
from app.models.enrollment import Enrollment, TeacherSubject
from app.models.hod import (
    Assignment,
    AssignmentStatus,
    AttendanceRecord,
    DiscussionThread,
    Submission,
    SubmissionStatus,
)
from app.models.lms import (
    Answer,
    AttendanceLeave,
    ContentItem,
    ContentKind,
    ContentTag,
    DifficultyLevel,
    DiscussionReply,
    LeaveStatus,
    Milestone,
    ProjectGroup,
    ProjectGroupMember,
    ProjectGroupMessage,
    ProjectGroupResource,
    ProjectGroupTask,
    Question,
    QuestionBankItem,
    QuestionOption,
    QuestionType,
    ReviewDecision,
    SubmissionFile,
    SubmissionReview,
)
from app.models.principal import (
    AttendanceSession,
    AttendanceStatus,
    Exam,
    ExamAttempt,
    ExamStatus,
    AttemptStatus,
    Notice,
    NoticePriority,
    NoticeScope,
    ResultPublication,
    StaffLeaveRequest,
    StudentResult,
    TimetableSlot,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.student import (
    StudentGroupMessageOut,
    StudentGroupResourceOut,
    StudentGroupTaskOut,
)
from app.schemas.teacher import (
    AttendanceRosterEntry,
    AttendanceSessionUpsert,
    TeacherAnswerOption,
    TeacherAnswerRow,
    TeacherAssignmentCreate,
    TeacherAssignmentDetail,
    TeacherAssignmentPage,
    TeacherAssignmentRow,
    TeacherAssignmentUpdate,
    TeacherAttemptDetail,
    TeacherAttemptPage,
    TeacherAttemptRow,
    TeacherAttendanceBoard,
    TeacherAttendanceSessionDetail,
    TeacherAttendanceSessionPage,
    TeacherAttendanceSessionRow,
    TeacherContentIn,
    TeacherContentPage,
    TeacherContentRow,
    TeacherContentUpdate,
    TeacherDashboard,
    TeacherExamCreate,
    TeacherExamDetail,
    TeacherExamPage,
    TeacherExamRow,
    TeacherExamUpdate,
    TeacherGroupMember,
    TeacherGroupPage,
    TeacherGroupRow,
    TeacherLeavePage,
    TeacherLeaveReview,
    TeacherLeaveRow,
    TeacherMilestoneIn,
    TeacherMilestoneOut,
    TeacherMilestoneUpdateIn,
    TeacherNoticeCreate,
    TeacherNoticePage,
    TeacherNoticeRow,
    TeacherQuestionIn,
    TeacherQuestionOptionOut,
    TeacherQuestionOut,
    TeacherQuestionUpdate,
    TeacherQuestionBankImportIn,
    TeacherQuestionBankItemIn,
    TeacherQuestionBankItemOut,
    TeacherQuestionBankItemUpdate,
    TeacherQuestionBankPage,
    TeacherReplyCreate,
    TeacherReplyRow,
    TeacherReviewHistoryRow,
    TeacherSchedule,
    TeacherScheduleSlot,
    TeacherSubmissionDetail,
    TeacherSubmissionFileOut,
    TeacherSubmissionPage,
    TeacherSubmissionReviewIn,
    TeacherSubmissionRow,
    TeacherTargetOption,
    TeacherTeamWorkspace,
    TeacherThreadCreate,
    TeacherThreadDetail,
    TeacherThreadModeration,
    TeacherThreadPage,
    TeacherThreadRow,
    TeacherUpcomingExam,
    TeachingAssignment,
)
from app.services.audit_service import AuditService
from app.services.principal_service import PrincipalService, _value
from app.services.push_service import PushService


logger = logging.getLogger(__name__)

_PENDING_SUBMISSION_STATUSES = (
    SubmissionStatus.SUBMITTED,
    SubmissionStatus.UNDER_REVIEW,
    SubmissionStatus.RESUBMIT_REQUESTED,
)
_OBJECTIVE_QUESTION_TYPES = (QuestionType.MCQ, QuestionType.TRUE_FALSE)


def grade_for(percentage: float | None, passing_percentage: float = 35.0) -> str | None:
    """Letter grade shared by exam release and submission review."""
    if percentage is None:
        return None
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
    if percentage >= passing_percentage:
        return "D"
    return "F"


@dataclass(frozen=True)
class TeacherScope:
    """What the caller teaches, resolved from the DB (never the JWT/URL)."""

    assignments: tuple[TeachingAssignment, ...]
    subject_ids: frozenset[uuid.UUID]
    class_ids: frozenset[uuid.UUID]
    homeroom_class_ids: frozenset[uuid.UUID]
    department_ids: frozenset[uuid.UUID]


class TeacherService:
    # ── Scope ───────────────────────────────────────────────────────────────

    @staticmethod
    async def scope_for_user(db: AsyncSession, teacher: User) -> TeacherScope:
        rows = (
            await db.execute(
                select(TeacherSubject, Subject, SchoolClass, Department)
                .join(Subject, and_(Subject.id == TeacherSubject.subject_id, Subject.tenant_id == teacher.tenant_id))
                .join(SchoolClass, and_(SchoolClass.id == Subject.class_id, SchoolClass.tenant_id == teacher.tenant_id))
                .outerjoin(
                    Department,
                    and_(Department.id == SchoolClass.department_id, Department.tenant_id == teacher.tenant_id),
                )
                .where(
                    TeacherSubject.tenant_id == teacher.tenant_id,
                    TeacherSubject.teacher_id == teacher.id,
                    Subject.is_active.is_(True),
                    SchoolClass.is_active.is_(True),
                )
                .order_by(SchoolClass.name, Subject.code)
            )
        ).all()

        homeroom_rows = (
            await db.execute(
                select(SchoolClass, Department)
                .outerjoin(
                    Department,
                    and_(Department.id == SchoolClass.department_id, Department.tenant_id == teacher.tenant_id),
                )
                .where(
                    SchoolClass.tenant_id == teacher.tenant_id,
                    SchoolClass.class_teacher_id == teacher.id,
                    SchoolClass.is_active.is_(True),
                )
            )
        ).all()

        assignments: list[TeachingAssignment] = []
        subject_ids: set[uuid.UUID] = set()
        class_ids: set[uuid.UUID] = set()
        department_ids: set[uuid.UUID] = set()
        homeroom_ids = {row[0].id for row in homeroom_rows}

        for teacher_subject, subject, school_class, department in rows:
            class_ids.add(school_class.id)
            subject_ids.add(subject.id)
            if department is not None:
                department_ids.add(department.id)
            assignments.append(
                TeachingAssignment(
                    subject_id=subject.id,
                    subject_code=subject.code,
                    subject_name=subject.name,
                    class_id=school_class.id,
                    class_name=school_class.name,
                    department_id=department.id if department else None,
                    department_name=department.name if department else None,
                    role_in_subject=teacher_subject.role_in_subject,
                    is_class_teacher=school_class.id in homeroom_ids,
                )
            )

        # Homeroom classes with no subject link still belong to the fence
        # (leave review, class notices), but are not teaching assignments.
        for school_class, department in homeroom_rows:
            class_ids.add(school_class.id)
            if department is not None:
                department_ids.add(department.id)

        if not assignments and not homeroom_ids:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="No teaching assignments found. Ask your HOD or admin to assign you a subject.",
            )
        return TeacherScope(
            assignments=tuple(assignments),
            subject_ids=frozenset(subject_ids),
            class_ids=frozenset(class_ids),
            homeroom_class_ids=frozenset(homeroom_ids),
            department_ids=frozenset(department_ids),
        )

    @staticmethod
    async def _current_year(db: AsyncSession, tenant_id: uuid.UUID) -> AcademicYear | None:
        return (
            await db.execute(
                select(AcademicYear)
                .where(AcademicYear.tenant_id == tenant_id, AcademicYear.is_current.is_(True))
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    def _ensure_teaches(scope: TeacherScope, subject_id: uuid.UUID, class_id: uuid.UUID) -> TeachingAssignment:
        """Fail closed unless this (subject, class) pair is the caller's."""
        for assignment in scope.assignments:
            if assignment.subject_id == subject_id and assignment.class_id == class_id:
                return assignment
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not teach this subject in this class")

    @staticmethod
    def _ensure_class_scope(scope: TeacherScope, class_id: uuid.UUID) -> None:
        if class_id not in scope.class_ids:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="This class is outside your teaching scope")

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        if not 1 <= limit <= 100 or offset < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid pagination")

    # ── C-TC-01 dashboard ───────────────────────────────────────────────────

    @staticmethod
    async def dashboard(db: AsyncSession, teacher: User) -> TeacherDashboard:
        scope = await TeacherService.scope_for_user(db, teacher)
        tenant_id = teacher.tenant_id
        today = await PrincipalService._tenant_today(db, tenant_id)
        current_year = await TeacherService._current_year(db, tenant_id)
        now = datetime.now(timezone.utc)

        today_slots: list[TeacherScheduleSlot] = []
        if current_year:
            today_slots = await TeacherService._slots_for(
                db, tenant_id, current_year.id, day=today, teacher_id=teacher.id
            )

        pending_counts = (
            await db.execute(
                select(
                    func.count(Submission.id),
                    func.coalesce(
                        func.sum(case((Submission.reviewed_at.is_(None), 1), else_=0)), 0
                    ),
                )
                .select_from(Submission)
                .join(Assignment, Assignment.id == Submission.assignment_id)
                .where(
                    Submission.tenant_id == tenant_id,
                    Assignment.teacher_id == teacher.id,
                    Submission.status.in_(_PENDING_SUBMISSION_STATUSES),
                )
            )
        ).one()
        total_pending = int(pending_counts[0] or 0)
        unreviewed = int(pending_counts[1] or 0)

        active_assignment_count = (
            await db.execute(
                select(func.count(Assignment.id)).where(
                    Assignment.tenant_id == tenant_id,
                    Assignment.teacher_id == teacher.id,
                    Assignment.status == AssignmentStatus.PUBLISHED,
                )
            )
        ).scalar() or 0

        upcoming_rows = (
            await db.execute(
                select(Exam, Subject.name, SchoolClass.name)
                .join(Subject, Subject.id == Exam.subject_id)
                .join(SchoolClass, SchoolClass.id == Exam.class_id)
                .where(
                    Exam.tenant_id == tenant_id,
                    Exam.created_by == teacher.id,
                    Exam.scheduled_at >= now,
                    Exam.status.in_((ExamStatus.PUBLISHED, ExamStatus.ONGOING)),
                )
                .order_by(Exam.scheduled_at)
                .limit(5)
            )
        ).all()
        upcoming_exams = [
            TeacherUpcomingExam(
                id=exam.id,
                title=exam.title,
                class_name=class_name,
                subject_name=subject_name,
                scheduled_at=exam.scheduled_at,
                status=_value(exam.status) or "PUBLISHED",
            )
            for exam, subject_name, class_name in upcoming_rows
        ]
        upcoming_count = (
            await db.execute(
                select(func.count(Exam.id)).where(
                    Exam.tenant_id == tenant_id,
                    Exam.created_by == teacher.id,
                    Exam.scheduled_at >= now,
                    Exam.status.in_((ExamStatus.PUBLISHED, ExamStatus.ONGOING)),
                )
            )
        ).scalar() or 0

        pending_leaves = (
            await db.execute(
                select(func.count(AttendanceLeave.id)).where(
                    AttendanceLeave.tenant_id == tenant_id,
                    AttendanceLeave.class_id.in_(scope.class_ids),
                    AttendanceLeave.status == LeaveStatus.PENDING,
                )
            )
        ).scalar() or 0

        notices = await TeacherService._notice_rows(db, teacher, scope, limit=5, offset=0)
        return TeacherDashboard(
            academic_year=current_year.name if current_year else None,
            teacher_name=teacher.name,
            teaching_assignment_count=len(scope.assignments),
            today_periods=today_slots,
            pending_submission_count=total_pending,
            pending_unreviewed_submissions=unreviewed,
            upcoming_exam_count=int(upcoming_count),
            upcoming_exams=upcoming_exams,
            active_assignment_count=int(active_assignment_count),
            pending_leave_count=int(pending_leaves),
            recent_notices=notices.items,
        )

    # ── C-TC-02 schedule ────────────────────────────────────────────────────

    @staticmethod
    async def schedule(db: AsyncSession, teacher: User) -> TeacherSchedule:
        scope = await TeacherService.scope_for_user(db, teacher)
        current_year = await TeacherService._current_year(db, teacher.tenant_id)
        if current_year is None:
            return TeacherSchedule(academic_year=None, assignments=list(scope.assignments), slots=[])
        slots = await TeacherService._slots_for(db, teacher.tenant_id, current_year.id, teacher_id=teacher.id)
        return TeacherSchedule(
            academic_year=current_year.name,
            assignments=list(scope.assignments),
            slots=slots,
        )

    @staticmethod
    async def _slots_for(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        academic_year_id: uuid.UUID,
        *,
        teacher_id: uuid.UUID,
        day: date | None = None,
    ) -> list[TeacherScheduleSlot]:
        today = day or await PrincipalService._tenant_today(db, tenant_id)
        clauses = [
            TimetableSlot.tenant_id == tenant_id,
            TimetableSlot.academic_year_id == academic_year_id,
            TimetableSlot.teacher_id == teacher_id,
            TimetableSlot.effective_from <= today,
            or_(TimetableSlot.effective_to.is_(None), TimetableSlot.effective_to >= today),
        ]
        if day is not None:
            clauses.append(TimetableSlot.day_of_week == day.isoweekday())
        rows = (
            await db.execute(
                select(TimetableSlot, SchoolClass.name, Subject)
                .join(SchoolClass, SchoolClass.id == TimetableSlot.class_id)
                .outerjoin(Subject, Subject.id == TimetableSlot.subject_id)
                .where(*clauses)
                .order_by(TimetableSlot.day_of_week, TimetableSlot.period_number)
            )
        ).all()
        return [
            TeacherScheduleSlot(
                id=slot.id,
                day_of_week=slot.day_of_week,
                period_number=slot.period_number,
                start_time=slot.start_time,
                end_time=slot.end_time,
                class_id=slot.class_id,
                class_name=class_name,
                subject_id=subject.id if subject else None,
                subject_code=subject.code if subject else None,
                subject_name=subject.name if subject else None,
                room_no=slot.room_no,
                slot_type=_value(slot.slot_type) or "CLASS",
            )
            for slot, class_name, subject in rows
        ]

    # ── C-TC-03 … C-TC-05 attendance ─────────────────────────────────────────

    @staticmethod
    async def attendance_options(db: AsyncSession, teacher: User) -> list[TeachingAssignment]:
        scope = await TeacherService.scope_for_user(db, teacher)
        return list(scope.assignments)

    @staticmethod
    async def attendance_board(
        db: AsyncSession,
        teacher: User,
        *,
        subject_id: uuid.UUID,
        class_id: uuid.UUID,
        on: date | None = None,
        period_label: str | None = None,
    ) -> TeacherAttendanceBoard:
        scope = await TeacherService.scope_for_user(db, teacher)
        TeacherService._ensure_teaches(scope, subject_id, class_id)
        tenant_id = teacher.tenant_id
        day = on or await PrincipalService._tenant_today(db, tenant_id)
        if day > await PrincipalService._tenant_today(db, tenant_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot mark attendance for a future date")
        roster = await TeacherService._roster(db, tenant_id, class_id)
        status_by_student: dict[uuid.UUID, tuple[str, int | None, str | None]] = {}
        detail = None
        if period_label:
            session = await TeacherService._find_session(
                db, tenant_id, subject_id=subject_id, class_id=class_id, on=day, period_label=period_label
            )
            if session is not None:
                detail = await TeacherService._session_detail(db, tenant_id, session)
                for record in detail.records:
                    if record.status:
                        status_by_student[record.student_id] = (
                            record.status,
                            record.late_by_minutes,
                            record.remarks,
                        )
        entries = [
            AttendanceRosterEntry(
                student_id=entry.student_id,
                student_name=entry.student_name,
                roll_number=entry.roll_number,
                status=status_by_student.get(entry.student_id, (None, None, None))[0],
                late_by_minutes=status_by_student.get(entry.student_id, (None, None, None))[1],
                remarks=status_by_student.get(entry.student_id, (None, None, None))[2],
            )
            for entry in roster
        ]
        return TeacherAttendanceBoard(assignments=list(scope.assignments), roster=entries, existing_session=detail)

    @staticmethod
    async def _roster(db: AsyncSession, tenant_id: uuid.UUID, class_id: uuid.UUID) -> list[AttendanceRosterEntry]:
        current_year = await TeacherService._current_year(db, tenant_id)
        if current_year is None:
            return []
        rows = (
            await db.execute(
                select(User, Enrollment)
                .join(Enrollment, and_(Enrollment.student_id == User.id, Enrollment.tenant_id == tenant_id))
                .where(
                    Enrollment.tenant_id == tenant_id,
                    Enrollment.class_id == class_id,
                    Enrollment.academic_year_id == current_year.id,
                    User.deleted_at.is_(None),
                )
                .order_by(User.name)
            )
        ).all()
        return [
            AttendanceRosterEntry(
                student_id=user.id,
                student_name=user.name,
                roll_number=enrollment.roll_number or user.student_roll_no,
            )
            for user, enrollment in rows
            if (_value(enrollment.status) or "ACTIVE") == "ACTIVE"
        ]

    @staticmethod
    async def _find_session(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        subject_id: uuid.UUID,
        class_id: uuid.UUID,
        on: date,
        period_label: str,
    ) -> AttendanceSession | None:
        return (
            await db.execute(
                select(AttendanceSession).where(
                    AttendanceSession.tenant_id == tenant_id,
                    AttendanceSession.subject_id == subject_id,
                    AttendanceSession.class_id == class_id,
                    AttendanceSession.date == on,
                    AttendanceSession.period_label == period_label.strip(),
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def save_attendance(
        db: AsyncSession, teacher: User, payload: AttendanceSessionUpsert
    ) -> TeacherAttendanceSessionDetail:
        scope = await TeacherService.scope_for_user(db, teacher)
        TeacherService._ensure_teaches(scope, payload.subject_id, payload.class_id)
        tenant_id = teacher.tenant_id
        today = await PrincipalService._tenant_today(db, tenant_id)
        if payload.date > today:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot mark attendance for a future date")
        current_year = await TeacherService._current_year(db, tenant_id)
        if current_year is None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="No current academic year is set")

        roster = await TeacherService._roster(db, tenant_id, payload.class_id)
        roster_ids = {entry.student_id for entry in roster}
        seen: set[uuid.UUID] = set()
        for record in payload.records:
            if record.student_id not in roster_ids:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Student not on this class roster")
            if record.student_id in seen:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Duplicate student in records")
            seen.add(record.student_id)
        if payload.start_time and payload.end_time and payload.end_time <= payload.start_time:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="end_time must be after start_time")

        session = await TeacherService._find_session(
            db,
            tenant_id,
            subject_id=payload.subject_id,
            class_id=payload.class_id,
            on=payload.date,
            period_label=payload.period_label,
        )
        if session is not None and session.is_locked:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This attendance session is locked")

        if session is None:
            session = AttendanceSession(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                subject_id=payload.subject_id,
                class_id=payload.class_id,
                teacher_id=teacher.id,
                academic_year_id=current_year.id,
                date=payload.date,
                period_label=payload.period_label.strip(),
                start_time=payload.start_time,
                end_time=payload.end_time,
                notes=payload.notes.strip() if payload.notes else None,
            )
            db.add(session)
            await db.flush()
            action = "MARK_ATTENDANCE"
        else:
            # Only the marking teacher may revise a session (before lock).
            if session.teacher_id != teacher.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the marking teacher can edit this session")
            session.start_time = payload.start_time
            session.end_time = payload.end_time
            session.notes = payload.notes.strip() if payload.notes else None
            await db.execute(delete(AttendanceRecord).where(AttendanceRecord.session_id == session.id))
            action = "UPDATE_ATTENDANCE"

        present = absent = 0
        for record in payload.records:
            state = AttendanceStatus(record.status)
            if state == AttendanceStatus.PRESENT or state == AttendanceStatus.LATE or state == AttendanceStatus.EXCUSED:
                present += 1
            if state == AttendanceStatus.ABSENT:
                absent += 1
            db.add(
                AttendanceRecord(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    session_id=session.id,
                    student_id=record.student_id,
                    status=state,
                    late_by_minutes=record.late_by_minutes if state == AttendanceStatus.LATE else None,
                    remarks=record.remarks.strip() if record.remarks else None,
                    updated_by=teacher.id,
                )
            )
        session.total_present = present
        session.total_absent = absent
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action=action,
            entity="AttendanceSession",
            entity_id=session.id,
            tenant_id=tenant_id,
            new_value={
                "date": str(payload.date),
                "period_label": session.period_label,
                "records": len(payload.records),
                "present": present,
                "absent": absent,
            },
        )
        return await TeacherService._session_detail(db, tenant_id, session)

    @staticmethod
    async def attendance_sessions(
        db: AsyncSession,
        teacher: User,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        class_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TeacherAttendanceSessionPage:
        TeacherService._validate_page(limit, offset)
        scope = await TeacherService.scope_for_user(db, teacher)
        tenant_id = teacher.tenant_id
        if class_id is not None:
            TeacherService._ensure_class_scope(scope, class_id)
        clauses = [
            AttendanceSession.tenant_id == tenant_id,
            AttendanceSession.teacher_id == teacher.id,
        ]
        if from_date is not None:
            clauses.append(AttendanceSession.date >= from_date)
        if to_date is not None:
            clauses.append(AttendanceSession.date <= to_date)
        if class_id is not None:
            clauses.append(AttendanceSession.class_id == class_id)
        if subject_id is not None:
            clauses.append(AttendanceSession.subject_id == subject_id)
        total = (
            await db.execute(select(func.count(AttendanceSession.id)).where(*clauses))
        ).scalar() or 0
        rows = (
            await db.execute(
                select(AttendanceSession, SchoolClass.name, Subject.code, Subject.name)
                .join(SchoolClass, SchoolClass.id == AttendanceSession.class_id)
                .join(Subject, Subject.id == AttendanceSession.subject_id)
                .where(*clauses)
                .order_by(AttendanceSession.date.desc(), AttendanceSession.period_label)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return TeacherAttendanceSessionPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[
                TeacherService._session_row(session, class_name, code, name)
                for session, class_name, code, name in rows
            ],
        )

    @staticmethod
    def _session_row(
        session: AttendanceSession, class_name: str, subject_code: str, subject_name: str
    ) -> TeacherAttendanceSessionRow:
        return TeacherAttendanceSessionRow(
            id=session.id,
            class_id=session.class_id,
            class_name=class_name,
            subject_id=session.subject_id,
            subject_code=subject_code,
            subject_name=subject_name,
            date=session.date,
            period_label=session.period_label,
            total_present=session.total_present,
            total_absent=session.total_absent,
            is_locked=session.is_locked,
            locked_at=session.locked_at,
            notes=session.notes,
        )

    @staticmethod
    async def attendance_session_detail(
        db: AsyncSession, teacher: User, session_id: uuid.UUID
    ) -> TeacherAttendanceSessionDetail:
        scope = await TeacherService.scope_for_user(db, teacher)
        session = (
            await db.execute(
                select(AttendanceSession).where(
                    AttendanceSession.id == session_id,
                    AttendanceSession.tenant_id == teacher.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attendance session not found")
        TeacherService._ensure_teaches(scope, session.subject_id, session.class_id)
        return await TeacherService._session_detail(db, teacher.tenant_id, session)

    @staticmethod
    async def _session_detail(
        db: AsyncSession, tenant_id: uuid.UUID, session: AttendanceSession
    ) -> TeacherAttendanceSessionDetail:
        names = (
            await db.execute(
                select(SchoolClass.name, Subject.code, Subject.name).select_from(SchoolClass)
                .join(Subject, Subject.class_id == SchoolClass.id)
                .where(SchoolClass.id == session.class_id, Subject.id == session.subject_id)
            )
        ).one()
        rows = (
            await db.execute(
                select(AttendanceRecord, User, Enrollment)
                .join(User, and_(User.id == AttendanceRecord.student_id, User.tenant_id == tenant_id))
                .outerjoin(
                    Enrollment,
                    and_(
                        Enrollment.student_id == AttendanceRecord.student_id,
                        Enrollment.class_id == session.class_id,
                        Enrollment.academic_year_id == session.academic_year_id,
                        Enrollment.tenant_id == tenant_id,
                    ),
                )
                .where(AttendanceRecord.session_id == session.id, AttendanceRecord.tenant_id == tenant_id)
                .order_by(User.name)
            )
        ).all()
        base = TeacherService._session_row(session, names[0], names[1], names[2])
        return TeacherAttendanceSessionDetail(
            **base.model_dump(),
            start_time=session.start_time,
            end_time=session.end_time,
            records=[
                AttendanceRosterEntry(
                    student_id=record.student_id,
                    student_name=user.name,
                    roll_number=(enrollment.roll_number if enrollment and enrollment.roll_number else user.student_roll_no),
                    status=_value(record.status),
                    late_by_minutes=record.late_by_minutes,
                    remarks=record.remarks,
                )
                for record, user, enrollment in rows
            ],
        )

    @staticmethod
    async def lock_attendance_session(
        db: AsyncSession, teacher: User, session_id: uuid.UUID
    ) -> TeacherAttendanceSessionDetail:
        session = (
            await db.execute(
                select(AttendanceSession)
                .where(AttendanceSession.id == session_id, AttendanceSession.tenant_id == teacher.tenant_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attendance session not found")
        if session.teacher_id != teacher.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the marking teacher can lock this session")
        if not session.is_locked:
            session.is_locked = True
            session.locked_at = datetime.now(timezone.utc)
            await db.flush()
            AuditService.record(
                db,
                actor=teacher,
                actor_role="TEACHER",
                action="LOCK_ATTENDANCE",
                entity="AttendanceSession",
                entity_id=session.id,
                tenant_id=teacher.tenant_id,
                new_value={"date": str(session.date), "period_label": session.period_label},
            )
        # Read the response AFTER the mutation so is_locked/locked_at reflect
        # reality — returning the pre-lock snapshot told the UI the lock failed.
        return await TeacherService.attendance_session_detail(db, teacher, session_id)

    # ── C-TC-06 student leave review ────────────────────────────────────────

    @staticmethod
    async def leaves(
        db: AsyncSession,
        teacher: User,
        *,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TeacherLeavePage:
        TeacherService._validate_page(limit, offset)
        scope = await TeacherService.scope_for_user(db, teacher)
        tenant_id = teacher.tenant_id
        clauses = [
            AttendanceLeave.tenant_id == tenant_id,
            AttendanceLeave.class_id.in_(scope.class_ids),
        ]
        if status_filter and status_filter.strip().upper() != "ALL":
            wanted = status_filter.strip().upper()
            if wanted not in LeaveStatus.__members__:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown leave status")
            clauses.append(AttendanceLeave.status == LeaveStatus[wanted])
        total = (
            await db.execute(select(func.count(AttendanceLeave.id)).where(*clauses))
        ).scalar() or 0
        pending = (
            await db.execute(
                select(func.count(AttendanceLeave.id)).where(
                    AttendanceLeave.tenant_id == tenant_id,
                    AttendanceLeave.class_id.in_(scope.class_ids),
                    AttendanceLeave.status == LeaveStatus.PENDING,
                )
            )
        ).scalar() or 0
        rows = (
            await db.execute(
                select(AttendanceLeave, User, SchoolClass, Enrollment)
                .join(User, and_(User.id == AttendanceLeave.student_id, User.tenant_id == tenant_id))
                .join(SchoolClass, and_(SchoolClass.id == AttendanceLeave.class_id, SchoolClass.tenant_id == tenant_id))
                .outerjoin(
                    Enrollment,
                    and_(
                        Enrollment.student_id == AttendanceLeave.student_id,
                        Enrollment.class_id == AttendanceLeave.class_id,
                        Enrollment.tenant_id == tenant_id,
                    ),
                )
                .where(*clauses)
                .order_by(AttendanceLeave.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        # One extra query for the whole page: whose words are these? Resolved in
        # bulk rather than per row, because a leave list is read all at once.
        requester_ids = {leave.requested_by for leave, *_rest in rows if leave.requested_by}
        requester_names: dict[uuid.UUID, str] = {}
        if requester_ids:
            requester_names = dict(
                (
                    await db.execute(
                        select(User.id, User.name).where(User.id.in_(list(requester_ids)))
                    )
                ).all()
            )
        return TeacherLeavePage(
            total=int(total),
            limit=limit,
            offset=offset,
            pending_count=int(pending),
            items=[
                TeacherService._leave_row(
                    leave, user, school_class, enrollment, requester_names.get(leave.requested_by)
                )
                for leave, user, school_class, enrollment in rows
            ],
        )

    @staticmethod
    def _leave_row(
        leave: AttendanceLeave,
        user: User,
        school_class: SchoolClass,
        enrollment,
        requested_by_name: str | None = None,
    ) -> TeacherLeaveRow:
        return TeacherLeaveRow(
            id=leave.id,
            student_id=leave.student_id,
            student_name=user.name,
            roll_number=(enrollment.roll_number if enrollment and enrollment.roll_number else user.student_roll_no),
            class_id=school_class.id,
            class_name=school_class.name,
            from_date=leave.from_date,
            to_date=leave.to_date,
            reason=leave.reason,
            document_url=leave.document_url,
            status=_value(leave.status) or "PENDING",
            reviewed_at=leave.reviewed_at,
            created_at=leave.created_at,
            request_source=leave.request_source or "STUDENT",
            requested_by_name=requested_by_name,
        )

    @staticmethod
    async def review_leave(
        db: AsyncSession, teacher: User, leave_id: uuid.UUID, payload: TeacherLeaveReview
    ) -> TeacherLeaveRow:
        scope = await TeacherService.scope_for_user(db, teacher)
        row = (
            await db.execute(
                select(AttendanceLeave, User, SchoolClass, Enrollment)
                .join(User, and_(User.id == AttendanceLeave.student_id, User.tenant_id == teacher.tenant_id))
                .join(
                    SchoolClass,
                    and_(SchoolClass.id == AttendanceLeave.class_id, SchoolClass.tenant_id == teacher.tenant_id),
                )
                .outerjoin(
                    Enrollment,
                    and_(
                        Enrollment.student_id == AttendanceLeave.student_id,
                        Enrollment.class_id == AttendanceLeave.class_id,
                        Enrollment.tenant_id == teacher.tenant_id,
                    ),
                )
                .where(
                    AttendanceLeave.id == leave_id,
                    AttendanceLeave.tenant_id == teacher.tenant_id,
                    AttendanceLeave.class_id.in_(scope.class_ids),
                )
                .with_for_update(of=AttendanceLeave)
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Leave request not found")
        leave, user, school_class, enrollment = row
        if leave.status != LeaveStatus.PENDING:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This leave request was already reviewed")
        leave.status = LeaveStatus(payload.decision)
        leave.reviewed_by = teacher.id
        leave.reviewed_at = datetime.now(timezone.utc)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action=f"LEAVE_{payload.decision}",
            entity="AttendanceLeave",
            entity_id=leave.id,
            tenant_id=teacher.tenant_id,
            new_value={"student_id": str(leave.student_id), "decision": payload.decision},
        )
        return TeacherService._leave_row(leave, user, school_class, enrollment)

    # ── C-TC-07 … C-TC-11 examinations ───────────────────────────────────────

    @staticmethod
    async def examinations(
        db: AsyncSession,
        teacher: User,
        *,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TeacherExamPage:
        TeacherService._validate_page(limit, offset)
        await TeacherService.scope_for_user(db, teacher)
        tenant_id = teacher.tenant_id
        clauses = [Exam.tenant_id == tenant_id, Exam.created_by == teacher.id]
        if status_filter and status_filter.strip().upper() != "ALL":
            wanted = status_filter.strip().upper()
            if wanted not in ExamStatus.__members__:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown exam status")
            clauses.append(Exam.status == ExamStatus[wanted])
        total = (await db.execute(select(func.count(Exam.id)).where(*clauses))).scalar() or 0
        rows = (
            await db.execute(
                select(Exam, Subject, SchoolClass)
                .join(Subject, Subject.id == Exam.subject_id)
                .join(SchoolClass, SchoolClass.id == Exam.class_id)
                .where(*clauses)
                .order_by(Exam.scheduled_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        stats = await TeacherService._exam_stats(db, tenant_id, [exam.id for exam, _s, _c in rows])
        return TeacherExamPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[
                TeacherService._exam_row(exam, subject, school_class, stats.get(exam.id))
                for exam, subject, school_class in rows
            ],
        )

    @staticmethod
    async def _exam_stats(db: AsyncSession, tenant_id: uuid.UUID, exam_ids: list[uuid.UUID]) -> dict:
        if not exam_ids:
            return {}
        question_counts = (
            await db.execute(
                select(Question.exam_id, func.count(Question.id))
                .where(Question.exam_id.in_(exam_ids))
                .group_by(Question.exam_id)
            )
        ).all()
        attempt_counts = (
            await db.execute(
                select(ExamAttempt.exam_id, func.count(ExamAttempt.id))
                .where(ExamAttempt.tenant_id == tenant_id, ExamAttempt.exam_id.in_(exam_ids))
                .group_by(ExamAttempt.exam_id)
            )
        ).all()
        pending = (
            await db.execute(
                select(ExamAttempt.exam_id, func.count(Answer.id))
                .join(Answer, Answer.attempt_id == ExamAttempt.id)
                .join(Question, Question.id == Answer.question_id)
                .where(
                    ExamAttempt.tenant_id == tenant_id,
                    ExamAttempt.exam_id.in_(exam_ids),
                    ExamAttempt.status == AttemptStatus.SUBMITTED,
                    Answer.score.is_(None),
                    Question.question_type.notin_(_OBJECTIVE_QUESTION_TYPES),
                )
                .group_by(ExamAttempt.exam_id)
            )
        ).all()
        stats: dict[uuid.UUID, dict[str, int]] = {}
        for exam_id, count in question_counts:
            stats.setdefault(exam_id, {})["question_count"] = int(count or 0)
        for exam_id, count in attempt_counts:
            stats.setdefault(exam_id, {})["attempt_count"] = int(count or 0)
        for exam_id, count in pending:
            stats.setdefault(exam_id, {})["pending_grading_count"] = int(count or 0)
        return stats

    @staticmethod
    def _exam_row(exam: Exam, subject: Subject, school_class: SchoolClass, stats) -> TeacherExamRow:
        stats = stats or {}
        return TeacherExamRow(
            id=exam.id,
            title=exam.title,
            class_id=exam.class_id,
            class_name=school_class.name,
            subject_id=exam.subject_id,
            subject_code=subject.code,
            subject_name=subject.name,
            exam_type=_value(exam.exam_type) or "MIXED",
            mode=_value(exam.mode) or "ONLINE",
            total_marks=exam.total_marks,
            passing_marks=exam.passing_marks,
            duration_minutes=exam.duration_minutes,
            scheduled_at=exam.scheduled_at,
            window_end_at=exam.window_end_at,
            status=_value(exam.status) or "DRAFT",
            question_count=stats.get("question_count", 0),
            attempt_count=stats.get("attempt_count", 0),
            pending_grading_count=stats.get("pending_grading_count", 0),
        )

    @staticmethod
    async def create_exam(db: AsyncSession, teacher: User, payload: TeacherExamCreate) -> TeacherExamDetail:
        scope = await TeacherService.scope_for_user(db, teacher)
        TeacherService._ensure_teaches(scope, payload.subject_id, payload.class_id)
        if payload.passing_marks > payload.total_marks:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="passing_marks cannot exceed total_marks")
        if payload.window_end_at and payload.window_end_at <= payload.scheduled_at:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="window_end_at must be after scheduled_at")
        subject = (
            await db.execute(
                select(Subject).where(Subject.id == payload.subject_id, Subject.tenant_id == teacher.tenant_id)
            )
        ).scalar_one()
        current_year = await TeacherService._current_year(db, teacher.tenant_id)
        if current_year is None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="No current academic year is set")
        exam = Exam(
            id=uuid.uuid4(),
            tenant_id=teacher.tenant_id,
            title=payload.title.strip(),
            subject_id=payload.subject_id,
            class_id=payload.class_id,
            academic_year_id=current_year.id,
            exam_type=payload.exam_type,
            mode=payload.mode,
            total_marks=payload.total_marks,
            passing_marks=payload.passing_marks,
            duration_minutes=payload.duration_minutes,
            instructions=payload.instructions.strip() if payload.instructions else None,
            scheduled_at=payload.scheduled_at,
            window_end_at=payload.window_end_at,
            status=ExamStatus.DRAFT,
            allow_review=payload.allow_review,
            shuffle_questions=payload.shuffle_questions,
            show_score_immediately=payload.show_score_immediately,
            created_by=teacher.id,
        )
        db.add(exam)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="CREATE_EXAM",
            entity="Exam",
            entity_id=exam.id,
            tenant_id=teacher.tenant_id,
            new_value={"title": exam.title, "subject_id": str(payload.subject_id), "scheduled_at": str(exam.scheduled_at)},
        )
        school_class = (
            await db.execute(
                select(SchoolClass).where(SchoolClass.id == payload.class_id, SchoolClass.tenant_id == teacher.tenant_id)
            )
        ).scalar_one()
        return TeacherService._exam_detail(exam, subject, school_class, [], {})

    @staticmethod
    async def _owned_exam(db: AsyncSession, teacher: User, exam_id: uuid.UUID) -> Exam:
        exam = (
            await db.execute(
                select(Exam).where(Exam.id == exam_id, Exam.tenant_id == teacher.tenant_id)
            )
        ).scalar_one_or_none()
        if exam is None or exam.created_by != teacher.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam not found")
        return exam

    @staticmethod
    def _exam_detail(
        exam: Exam, subject: Subject, school_class: SchoolClass, questions: list[TeacherQuestionOut], stats
    ) -> TeacherExamDetail:
        return TeacherExamDetail(
            **TeacherService._exam_row(exam, subject, school_class, stats).model_dump(),
            instructions=exam.instructions,
            allow_review=exam.allow_review,
            show_score_immediately=exam.show_score_immediately,
            shuffle_questions=exam.shuffle_questions,
            created_at=exam.created_at,
            questions=questions,
        )

    @staticmethod
    async def exam_detail(db: AsyncSession, teacher: User, exam_id: uuid.UUID) -> TeacherExamDetail:
        exam = await TeacherService._owned_exam(db, teacher, exam_id)
        meta = (
            await db.execute(
                select(Subject, SchoolClass)
                .join(SchoolClass, SchoolClass.id == Subject.class_id)
                .where(Subject.id == exam.subject_id)
            )
        ).one()
        questions = await TeacherService._questions_out(db, exam.id, include_correct=True)
        stats = await TeacherService._exam_stats(db, teacher.tenant_id, [exam.id])
        return TeacherService._exam_detail(exam, meta[0], meta[1], questions, stats.get(exam.id))

    @staticmethod
    async def _questions_out(db: AsyncSession, exam_id: uuid.UUID, *, include_correct: bool) -> list[TeacherQuestionOut]:
        question_rows = (
            await db.execute(
                select(Question).where(Question.exam_id == exam_id).order_by(Question.sort_order, Question.id)
            )
        ).scalars().all()
        option_rows = (
            await db.execute(
                select(QuestionOption)
                .where(QuestionOption.question_id.in_([q.id for q in question_rows] or [uuid.uuid4()]))
                .order_by(QuestionOption.sort_order, QuestionOption.id)
            )
        ).scalars().all() if question_rows else []
        options_by_question: dict[uuid.UUID, list[QuestionOption]] = {}
        for option in option_rows:
            options_by_question.setdefault(option.question_id, []).append(option)
        output = []
        for question in question_rows:
            output.append(
                TeacherQuestionOut(
                    id=question.id,
                    text=question.text,
                    question_type=_value(question.question_type) or "MCQ",
                    marks=float(question.marks),
                    negative_marks=float(question.negative_marks or 0),
                    image_url=question.image_url,
                    explanation=question.explanation,
                    difficulty=_value(question.difficulty),
                    sort_order=question.sort_order,
                    options=[
                        TeacherQuestionOptionOut(
                            id=option.id,
                            text=option.text,
                            image_url=option.image_url,
                            is_correct=option.is_correct if include_correct else False,
                            sort_order=option.sort_order,
                        )
                        for option in options_by_question.get(question.id, [])
                    ],
                )
            )
        return output

    @staticmethod
    def _ensure_exam_editable(exam: Exam) -> None:
        state = _value(exam.status) or "DRAFT"
        if state != ExamStatus.DRAFT.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Only draft exams can be edited")

    @staticmethod
    async def update_exam(
        db: AsyncSession, teacher: User, exam_id: uuid.UUID, payload: TeacherExamUpdate
    ) -> TeacherExamDetail:
        exam = await TeacherService._owned_exam(db, teacher, exam_id)
        TeacherService._ensure_exam_editable(exam)
        updates = payload.model_dump(exclude_unset=True)
        if "title" in updates and updates["title"] is not None:
            updates["title"] = updates["title"].strip()
        next_total = updates.get("total_marks", exam.total_marks)
        next_passing = updates.get("passing_marks", exam.passing_marks)
        if next_passing is not None and next_total is not None and next_passing > next_total:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="passing_marks cannot exceed total_marks")
        next_scheduled = updates.get("scheduled_at", exam.scheduled_at)
        next_window_end = updates.get("window_end_at", exam.window_end_at)
        if next_scheduled and next_window_end and next_window_end <= next_scheduled:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="window_end_at must be after scheduled_at")
        for key, value in updates.items():
            setattr(exam, key, value)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="UPDATE_EXAM",
            entity="Exam",
            entity_id=exam.id,
            tenant_id=teacher.tenant_id,
            new_value={key: str(value) for key, value in updates.items()},
        )
        return await TeacherService.exam_detail(db, teacher, exam_id)

    @staticmethod
    async def publish_exam(db: AsyncSession, teacher: User, exam_id: uuid.UUID) -> TeacherExamDetail:
        exam = await TeacherService._owned_exam(db, teacher, exam_id)
        state = _value(exam.status) or "DRAFT"
        if state != ExamStatus.DRAFT.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Only draft exams can be published")
        question_rows = (
            await db.execute(
                select(func.count(Question.id), func.coalesce(func.sum(Question.marks), 0)).where(
                    Question.exam_id == exam.id
                )
            )
        ).one()
        if not question_rows[0]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Add at least one question before publishing")
        question_marks = float(question_rows[1] or 0)
        if question_marks != exam.total_marks:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Question marks must equal the exam total_marks ({exam.total_marks}); currently {question_marks:g}",
            )
        exam.status = ExamStatus.PUBLISHED
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="PUBLISH_EXAM",
            entity="Exam",
            entity_id=exam.id,
            tenant_id=teacher.tenant_id,
            new_value={"title": exam.title, "questions": int(question_rows[0])},
        )
        return await TeacherService.exam_detail(db, teacher, exam_id)

    # ── C-TC-10 question authoring ──────────────────────────────────────────

    @staticmethod
    def _validate_question_payload(payload: TeacherQuestionIn | TeacherQuestionUpdate, question_type: str | None) -> None:
        options = payload.options
        kind = question_type or getattr(payload, "question_type", None)
        if options is None:
            return
        if kind in (QuestionType.MCQ.value, QuestionType.TRUE_FALSE.value):
            if len(options) < 2:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Objective questions need at least two options")
            if not any(option.is_correct for option in options):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Mark at least one option as correct")

    @staticmethod
    async def _save_to_question_bank(
        db: AsyncSession,
        teacher: User,
        subject_id: uuid.UUID | None,
        class_id: uuid.UUID | None,
        text: str,
        question_type: str,
        default_marks: Decimal,
        negative_marks: Decimal,
        options: list[dict],
        image_url: str | None = None,
        explanation: str | None = None,
        difficulty: str | None = None,
    ) -> QuestionBankItem:
        existing = (
            await db.execute(
                select(QuestionBankItem).where(
                    QuestionBankItem.tenant_id == teacher.tenant_id,
                    QuestionBankItem.text == text.strip(),
                    QuestionBankItem.question_type == QuestionType(question_type),
                )
            )
        ).scalars().first()

        if existing:
            # Only bump usage count — never overwrite existing bank content from
            # an auto-save; that would silently corrupt the shared bank entry.
            existing.usage_count = (existing.usage_count or 0) + 1
            existing.updated_at = datetime.now(timezone.utc)
            await db.flush()
            return existing

        bank_item = QuestionBankItem(
            id=uuid.uuid4(),
            tenant_id=teacher.tenant_id,
            created_by=teacher.id,
            subject_id=subject_id,
            class_id=class_id,
            text=text.strip(),
            question_type=QuestionType(question_type),
            default_marks=default_marks,
            negative_marks=negative_marks,
            options=options,
            image_url=image_url,
            explanation=explanation.strip() if explanation else None,
            difficulty=DifficultyLevel(difficulty) if difficulty else None,
            usage_count=1,
        )
        db.add(bank_item)
        await db.flush()
        return bank_item

    @staticmethod
    async def add_question(
        db: AsyncSession, teacher: User, exam_id: uuid.UUID, payload: TeacherQuestionIn
    ) -> TeacherQuestionOut:
        exam = await TeacherService._owned_exam(db, teacher, exam_id)
        TeacherService._ensure_exam_editable(exam)
        TeacherService._validate_question_payload(payload, payload.question_type)
        next_order = (
            await db.execute(
                select(func.coalesce(func.max(Question.sort_order), -1)).where(Question.exam_id == exam.id)
            )
        ).scalar()
        question = Question(
            id=uuid.uuid4(),
            exam_id=exam.id,
            text=payload.text.strip(),
            question_type=QuestionType(payload.question_type),
            marks=Decimal(str(payload.marks)),
            negative_marks=Decimal(str(payload.negative_marks)),
            image_url=payload.image_url,
            explanation=payload.explanation.strip() if payload.explanation else None,
            difficulty=payload.difficulty,
            sort_order=int(next_order or -1) + 1,
        )
        db.add(question)
        await db.flush()
        options = await TeacherService._replace_options(db, question.id, payload.options)

        # Auto-save into Question Bank — isolated so a bank error never blocks
        # the question from being added to the exam.
        try:
            options_dicts = [
                {
                    "text": opt.text.strip(),
                    "is_correct": opt.is_correct,
                    "image_url": opt.image_url,
                    "sort_order": opt.sort_order,
                }
                for opt in options
            ]
            bank_item = await TeacherService._save_to_question_bank(
                db,
                teacher,
                subject_id=exam.subject_id,
                class_id=exam.class_id,
                text=question.text,
                question_type=payload.question_type,
                default_marks=question.marks,
                negative_marks=question.negative_marks,
                options=options_dicts,
                image_url=question.image_url,
                explanation=question.explanation,
                difficulty=_value(question.difficulty),
            )
            question.bank_item_id = bank_item.id
            await db.flush()
        except Exception:
            pass  # Bank save is best-effort; exam question is already persisted

        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="ADD_EXAM_QUESTION",
            entity="Question",
            entity_id=question.id,
            tenant_id=teacher.tenant_id,
            new_value={"exam_id": str(exam.id), "type": payload.question_type, "marks": payload.marks},
        )
        return TeacherService._question_out(question, options)

    @staticmethod
    def _question_out(question: Question, options: list[QuestionOption]) -> TeacherQuestionOut:
        return TeacherQuestionOut(
            id=question.id,
            text=question.text,
            question_type=_value(question.question_type) or "MCQ",
            marks=float(question.marks),
            negative_marks=float(question.negative_marks or 0),
            image_url=question.image_url,
            explanation=question.explanation,
            difficulty=_value(question.difficulty),
            sort_order=question.sort_order,
            options=[
                TeacherQuestionOptionOut(
                    id=option.id,
                    text=option.text,
                    image_url=option.image_url,
                    is_correct=option.is_correct,
                    sort_order=option.sort_order,
                )
                for option in options
            ],
        )

    @staticmethod
    async def _replace_options(db: AsyncSession, question_id: uuid.UUID, options) -> list[QuestionOption]:
        await db.execute(delete(QuestionOption).where(QuestionOption.question_id == question_id))
        created = []
        for index, option in enumerate(options or []):
            row = QuestionOption(
                id=uuid.uuid4(),
                question_id=question_id,
                text=option.text.strip(),
                image_url=option.image_url,
                is_correct=option.is_correct,
                sort_order=option.sort_order if option.sort_order else index,
            )
            db.add(row)
            created.append(row)
        await db.flush()
        return created

    @staticmethod
    async def update_question(
        db: AsyncSession,
        teacher: User,
        exam_id: uuid.UUID,
        question_id: uuid.UUID,
        payload: TeacherQuestionUpdate,
    ) -> TeacherQuestionOut:
        exam = await TeacherService._owned_exam(db, teacher, exam_id)
        TeacherService._ensure_exam_editable(exam)
        question = (
            await db.execute(
                select(Question).where(Question.id == question_id, Question.exam_id == exam.id)
            )
        ).scalar_one_or_none()
        if question is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
        TeacherService._validate_question_payload(payload, _value(question.question_type))
        updates = payload.model_dump(exclude_unset=True, exclude={"options"})
        if "text" in updates and updates["text"] is not None:
            updates["text"] = updates["text"].strip()
        if "difficulty" in updates and updates["difficulty"] is not None:
            updates["difficulty"] = updates["difficulty"]
        for key, value in updates.items():
            setattr(question, key, value)
        options = None
        if payload.options is not None:
            options = await TeacherService._replace_options(db, question.id, payload.options)
        await db.flush()
        if options is None:
            options = (
                await db.execute(
                    select(QuestionOption).where(QuestionOption.question_id == question.id).order_by(QuestionOption.sort_order)
                )
            ).scalars().all()

        # Auto-save into Question Bank — isolated so a bank error never blocks
        # the question update.
        try:
            options_dicts = [
                {
                    "text": opt.text.strip(),
                    "is_correct": opt.is_correct,
                    "image_url": opt.image_url,
                    "sort_order": opt.sort_order,
                }
                for opt in options
            ]
            bank_item = await TeacherService._save_to_question_bank(
                db,
                teacher,
                subject_id=exam.subject_id,
                class_id=exam.class_id,
                text=question.text,
                question_type=_value(question.question_type) or "MCQ",
                default_marks=question.marks,
                negative_marks=question.negative_marks,
                options=options_dicts,
                image_url=question.image_url,
                explanation=question.explanation,
                difficulty=_value(question.difficulty),
            )
            question.bank_item_id = bank_item.id
            await db.flush()
        except Exception:
            pass  # Bank save is best-effort; exam question is already persisted

        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="UPDATE_EXAM_QUESTION",
            entity="Question",
            entity_id=question.id,
            tenant_id=teacher.tenant_id,
            new_value={"exam_id": str(exam.id)},
        )
        return TeacherService._question_out(question, list(options))

    # ── Question Bank workflows ────────────────────────────────────────────────

    @staticmethod
    async def list_question_bank(
        db: AsyncSession,
        teacher: User,
        subject_id: uuid.UUID | None = None,
        question_type: str | None = None,
        difficulty: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TeacherQuestionBankPage:
        query = select(QuestionBankItem).where(QuestionBankItem.tenant_id == teacher.tenant_id)
        if subject_id:
            query = query.where(QuestionBankItem.subject_id == subject_id)
        if question_type:
            query = query.where(QuestionBankItem.question_type == QuestionType(question_type))
        if difficulty:
            query = query.where(QuestionBankItem.difficulty == DifficultyLevel(difficulty))
        if search and search.strip():
            query = query.where(QuestionBankItem.text.ilike(f"%{search.strip()}%"))

        total = (
            await db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()

        rows = (
            await db.execute(
                query.order_by(QuestionBankItem.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()

        subject_ids = [r.subject_id for r in rows if r.subject_id]
        class_ids = [r.class_id for r in rows if r.class_id]

        subjects = {}
        if subject_ids:
            sub_rows = (await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))).scalars().all()
            subjects = {s.id: s.name for s in sub_rows}

        classes = {}
        if class_ids:
            cls_rows = (await db.execute(select(SchoolClass).where(SchoolClass.id.in_(class_ids)))).scalars().all()
            classes = {c.id: c.name for c in cls_rows}

        items = []
        for r in rows:
            items.append(
                TeacherQuestionBankItemOut(
                    id=r.id,
                    tenant_id=r.tenant_id,
                    created_by=r.created_by,
                    subject_id=r.subject_id,
                    subject_name=subjects.get(r.subject_id) if r.subject_id else None,
                    class_id=r.class_id,
                    class_name=classes.get(r.class_id) if r.class_id else None,
                    text=r.text,
                    question_type=_value(r.question_type) or "MCQ",
                    default_marks=float(r.default_marks),
                    negative_marks=float(r.negative_marks or 0),
                    options=r.options or [],
                    image_url=r.image_url,
                    explanation=r.explanation,
                    difficulty=_value(r.difficulty),
                    tags=r.tags or [],
                    usage_count=r.usage_count,
                    created_at=r.created_at,
                )
            )

        return TeacherQuestionBankPage(
            total=total,
            limit=limit,
            offset=offset,
            items=items,
        )

    @staticmethod
    async def create_question_bank_item(
        db: AsyncSession, teacher: User, payload: TeacherQuestionBankItemIn
    ) -> TeacherQuestionBankItemOut:
        options_dicts = [
            {
                "text": opt.text.strip(),
                "is_correct": opt.is_correct,
                "image_url": opt.image_url,
                "sort_order": opt.sort_order,
            }
            for opt in payload.options
        ]
        bank_item = await TeacherService._save_to_question_bank(
            db,
            teacher,
            subject_id=payload.subject_id,
            class_id=payload.class_id,
            text=payload.text,
            question_type=payload.question_type,
            default_marks=Decimal(str(payload.default_marks)),
            negative_marks=Decimal(str(payload.negative_marks)),
            options=options_dicts,
            image_url=payload.image_url,
            explanation=payload.explanation,
            difficulty=payload.difficulty,
        )
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="CREATE_QUESTION_BANK_ITEM",
            entity="QuestionBankItem",
            entity_id=bank_item.id,
            tenant_id=teacher.tenant_id,
            new_value={"type": payload.question_type},
        )
        return TeacherQuestionBankItemOut(
            id=bank_item.id,
            tenant_id=bank_item.tenant_id,
            created_by=bank_item.created_by,
            subject_id=bank_item.subject_id,
            class_id=bank_item.class_id,
            text=bank_item.text,
            question_type=_value(bank_item.question_type) or "MCQ",
            default_marks=float(bank_item.default_marks),
            negative_marks=float(bank_item.negative_marks or 0),
            options=bank_item.options or [],
            image_url=bank_item.image_url,
            explanation=bank_item.explanation,
            difficulty=_value(bank_item.difficulty),
            tags=bank_item.tags or [],
            usage_count=bank_item.usage_count,
            created_at=bank_item.created_at,
        )

    @staticmethod
    async def update_question_bank_item(
        db: AsyncSession, teacher: User, item_id: uuid.UUID, payload: TeacherQuestionBankItemUpdate
    ) -> TeacherQuestionBankItemOut:
        item = (
            await db.execute(
                select(QuestionBankItem).where(
                    QuestionBankItem.id == item_id, QuestionBankItem.tenant_id == teacher.tenant_id
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question bank item not found")

        if payload.text is not None:
            item.text = payload.text.strip()
        if payload.question_type is not None:
            item.question_type = QuestionType(payload.question_type)
        if payload.default_marks is not None:
            item.default_marks = Decimal(str(payload.default_marks))
        if payload.negative_marks is not None:
            item.negative_marks = Decimal(str(payload.negative_marks))
        if payload.options is not None:
            item.options = [
                {
                    "text": opt.text.strip(),
                    "is_correct": opt.is_correct,
                    "image_url": opt.image_url,
                    "sort_order": opt.sort_order,
                }
                for opt in payload.options
            ]
            flag_modified(item, "options")
        if payload.image_url is not None:
            item.image_url = payload.image_url
        if payload.explanation is not None:
            item.explanation = payload.explanation.strip() or None
        if payload.difficulty is not None:
            item.difficulty = DifficultyLevel(payload.difficulty)
        if payload.tags is not None:
            item.tags = [t.strip() for t in payload.tags if t.strip()]
            flag_modified(item, "tags")
        # subject / class can be explicitly cleared by passing None in the payload
        if payload.subject_id is not None:
            item.subject_id = payload.subject_id
        if payload.class_id is not None:
            item.class_id = payload.class_id

        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="UPDATE_QUESTION_BANK_ITEM",
            entity="QuestionBankItem",
            entity_id=item.id,
            tenant_id=teacher.tenant_id,
            new_value={"text": (item.text or "")[:120]},
        )

        # Resolve names for response
        subject_name: str | None = None
        class_name: str | None = None
        if item.subject_id:
            subj = (await db.execute(select(Subject).where(Subject.id == item.subject_id))).scalar_one_or_none()
            if subj:
                subject_name = subj.name
        if item.class_id:
            cls = (await db.execute(select(SchoolClass).where(SchoolClass.id == item.class_id))).scalar_one_or_none()
            if cls:
                class_name = cls.name

        return TeacherQuestionBankItemOut(
            id=item.id,
            tenant_id=item.tenant_id,
            created_by=item.created_by,
            subject_id=item.subject_id,
            subject_name=subject_name,
            class_id=item.class_id,
            class_name=class_name,
            text=item.text,
            question_type=_value(item.question_type) or "MCQ",
            default_marks=float(item.default_marks),
            negative_marks=float(item.negative_marks or 0),
            options=item.options or [],
            image_url=item.image_url,
            explanation=item.explanation,
            difficulty=_value(item.difficulty),
            tags=item.tags or [],
            usage_count=item.usage_count,
            created_at=item.created_at,
        )

    @staticmethod
    async def delete_question_bank_item(
        db: AsyncSession, teacher: User, item_id: uuid.UUID
    ) -> None:

        item = (
            await db.execute(
                select(QuestionBankItem).where(
                    QuestionBankItem.id == item_id, QuestionBankItem.tenant_id == teacher.tenant_id
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question bank item not found")
        await db.delete(item)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="DELETE_QUESTION_BANK_ITEM",
            entity="QuestionBankItem",
            entity_id=item_id,
            tenant_id=teacher.tenant_id,
        )

    # ── Question Bank export / file-import ──────────────────────────────────

    # CSV column order mirrored in the import parser below.
    _QB_CSV_FIELDS = [
        "text",
        "question_type",
        "difficulty",
        "default_marks",
        "negative_marks",
        "explanation",
        "options_json",   # JSON array: [{"text":"…","is_correct":true},…]
        "tags",           # comma-separated tag list
        "subject_id",
        "class_id",
    ]

    @staticmethod
    async def export_question_bank(
        db: AsyncSession,
        teacher: User,
        fmt: str = "csv",
        subject_id: uuid.UUID | None = None,
        question_type: str | None = None,
        difficulty: str | None = None,
        search: str | None = None,
    ) -> tuple[bytes, str, str]:
        """Return (file_bytes, filename, media_type) for the question bank export."""
        page = await TeacherService.list_question_bank(
            db,
            teacher,
            subject_id=subject_id,
            question_type=question_type,
            difficulty=difficulty,
            search=search,
            limit=10_000,
            offset=0,
        )

        if fmt == "json":
            data = [
                {
                    "text": item.text,
                    "question_type": item.question_type,
                    "difficulty": item.difficulty,
                    "default_marks": item.default_marks,
                    "negative_marks": item.negative_marks,
                    "explanation": item.explanation,
                    "options": item.options,
                    "tags": item.tags,
                    "subject_id": str(item.subject_id) if item.subject_id else None,
                    "class_id": str(item.class_id) if item.class_id else None,
                    "usage_count": item.usage_count,
                }
                for item in page.items
            ]
            raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            return raw, "question_bank.json", "application/json"

        # CSV (default)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=TeacherService._QB_CSV_FIELDS)
        writer.writeheader()
        for item in page.items:
            writer.writerow(
                {
                    "text": item.text,
                    "question_type": item.question_type,
                    "difficulty": item.difficulty or "",
                    "default_marks": item.default_marks,
                    "negative_marks": item.negative_marks,
                    "explanation": item.explanation or "",
                    "options_json": json.dumps(item.options, ensure_ascii=False),
                    "tags": ",".join(item.tags),
                    "subject_id": str(item.subject_id) if item.subject_id else "",
                    "class_id": str(item.class_id) if item.class_id else "",
                }
            )
        raw = buf.getvalue().encode("utf-8-sig")  # BOM so Excel opens UTF-8 cleanly
        return raw, "question_bank.csv", "text/csv; charset=utf-8-sig"

    @staticmethod
    async def import_question_bank_file(
        db: AsyncSession,
        teacher: User,
        filename: str,
        content: bytes,
    ) -> dict:
        """Parse a CSV or JSON file and bulk-insert into the question bank.

        Returns a summary dict with ``imported`` and ``errors`` counts.
        """
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext == "json":
            rows = TeacherService._parse_json_import(content)
        elif ext == "csv":
            rows = TeacherService._parse_csv_import(content)
        else:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported file type. Please upload a .csv or .json file.",
            )

        _VALID_TYPES = {"MCQ", "SHORT_ANSWER", "LONG_ANSWER", "TRUE_FALSE", "FILL_BLANK", "MATCH"}
        _VALID_DIFF = {"EASY", "MEDIUM", "HARD", None}

        imported = 0
        errors: list[str] = []

        for idx, row in enumerate(rows, start=1):
            text = (row.get("text") or "").strip()
            if not text:
                errors.append(f"Row {idx}: 'text' is required.")
                continue
            qtype = (row.get("question_type") or "MCQ").strip().upper()
            if qtype not in _VALID_TYPES:
                errors.append(f"Row {idx}: unknown question_type '{qtype}'.")
                continue
            diff = (row.get("difficulty") or "").strip().upper() or None
            if diff not in _VALID_DIFF:
                diff = None

            try:
                default_marks = float(row.get("default_marks") or 1)
                negative_marks = float(row.get("negative_marks") or 0)
            except (ValueError, TypeError):
                default_marks, negative_marks = 1.0, 0.0

            options_raw = row.get("options") or row.get("options_json") or []
            if isinstance(options_raw, str):
                try:
                    options_raw = json.loads(options_raw)
                except json.JSONDecodeError:
                    options_raw = []
            options = [
                {"text": str(o.get("text", "")).strip(), "is_correct": bool(o.get("is_correct", False))}
                for o in options_raw
                if isinstance(o, dict)
            ]

            tags_raw = row.get("tags") or []
            if isinstance(tags_raw, str):
                tags_raw = [t.strip() for t in tags_raw.split(",") if t.strip()]

            subject_id: uuid.UUID | None = None
            class_id: uuid.UUID | None = None
            try:
                if row.get("subject_id"):
                    subject_id = uuid.UUID(str(row["subject_id"]))
            except ValueError:
                pass
            try:
                if row.get("class_id"):
                    class_id = uuid.UUID(str(row["class_id"]))
            except ValueError:
                pass

            try:
                await TeacherService._save_to_question_bank(
                    db,
                    teacher,
                    subject_id=subject_id,
                    class_id=class_id,
                    text=text,
                    question_type=qtype,
                    default_marks=Decimal(str(default_marks)),
                    negative_marks=Decimal(str(negative_marks)),
                    options=options,
                    image_url=None,
                    explanation=(row.get("explanation") or "").strip() or None,
                    difficulty=diff,
                    tags=list(tags_raw),
                )
                imported += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Row {idx}: {exc}")

        if imported:
            await db.flush()
            AuditService.record(
                db,
                actor=teacher,
                actor_role="TEACHER",
                action="IMPORT_QUESTION_BANK_FILE",
                entity="QuestionBankItem",
                entity_id=teacher.id,
                tenant_id=teacher.tenant_id,
                new_value={"imported": imported, "errors": len(errors)},
            )

        return {"imported": imported, "errors": errors}

    @staticmethod
    def _parse_csv_import(content: bytes) -> list[dict]:
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)

    @staticmethod
    def _parse_json_import(content: bytes) -> list[dict]:
        data = json.loads(content.decode("utf-8", errors="replace"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="JSON file must contain an array of question objects.",
        )

    @staticmethod

    async def import_questions_from_bank(
        db: AsyncSession, teacher: User, exam_id: uuid.UUID, payload: TeacherQuestionBankImportIn
    ) -> TeacherExamDetail:
        exam = await TeacherService._owned_exam(db, teacher, exam_id)
        TeacherService._ensure_exam_editable(exam)

        bank_items = (
            await db.execute(
                select(QuestionBankItem).where(
                    QuestionBankItem.id.in_(payload.bank_item_ids),
                    QuestionBankItem.tenant_id == teacher.tenant_id,
                )
            )
        ).scalars().all()

        if not bank_items:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No matching question bank items found")

        next_order = (
            await db.execute(
                select(func.coalesce(func.max(Question.sort_order), -1)).where(Question.exam_id == exam.id)
            )
        ).scalar() or -1

        for bank_item in bank_items:
            next_order += 1
            question = Question(
                id=uuid.uuid4(),
                exam_id=exam.id,
                bank_item_id=bank_item.id,
                text=bank_item.text,
                question_type=bank_item.question_type,
                marks=bank_item.default_marks,
                negative_marks=bank_item.negative_marks,
                image_url=bank_item.image_url,
                explanation=bank_item.explanation,
                difficulty=bank_item.difficulty,
                sort_order=next_order,
            )
            db.add(question)
            await db.flush()

            bank_item.usage_count += 1

            for index, opt in enumerate(bank_item.options or []):
                option_row = QuestionOption(
                    id=uuid.uuid4(),
                    question_id=question.id,
                    text=opt.get("text", "").strip(),
                    image_url=opt.get("image_url"),
                    is_correct=bool(opt.get("is_correct", False)),
                    sort_order=opt.get("sort_order", index),
                )
                db.add(option_row)

        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="IMPORT_EXAM_QUESTIONS",
            entity="Exam",
            entity_id=exam.id,
            tenant_id=teacher.tenant_id,
            new_value={"imported_count": len(bank_items)},
        )
        return await TeacherService.exam_detail(db, teacher, exam_id)

    @staticmethod
    async def delete_question(db: AsyncSession, teacher: User, exam_id: uuid.UUID, question_id: uuid.UUID) -> TeacherExamDetail:
        exam = await TeacherService._owned_exam(db, teacher, exam_id)
        TeacherService._ensure_exam_editable(exam)
        question = (
            await db.execute(
                select(Question).where(Question.id == question_id, Question.exam_id == exam.id)
            )
        ).scalar_one_or_none()
        if question is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
        await db.delete(question)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="DELETE_EXAM_QUESTION",
            entity="Question",
            entity_id=question.id,
            tenant_id=teacher.tenant_id,
            old_value={"text": question.text[:120]},
        )
        return await TeacherService.exam_detail(db, teacher, exam_id)

    # ── C-TC-11 exam results & grading ──────────────────────────────────────

    @staticmethod
    async def exam_attempts(
        db: AsyncSession,
        teacher: User,
        exam_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> TeacherAttemptPage:
        TeacherService._validate_page(limit, offset)
        exam = await TeacherService._owned_exam(db, teacher, exam_id)
        tenant_id = teacher.tenant_id
        total = (
            await db.execute(
                select(func.count(ExamAttempt.id)).where(
                    ExamAttempt.tenant_id == tenant_id, ExamAttempt.exam_id == exam.id
                )
            )
        ).scalar() or 0
        rows = (
            await db.execute(
                select(ExamAttempt, User)
                .join(User, and_(User.id == ExamAttempt.student_id, User.tenant_id == tenant_id))
                .where(ExamAttempt.tenant_id == tenant_id, ExamAttempt.exam_id == exam.id)
                .order_by(User.name)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        pending = await TeacherService._pending_grading_by_attempt(db, tenant_id, [attempt.id for attempt, _u in rows])
        return TeacherAttemptPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[
                TeacherService._attempt_row(attempt, user, pending.get(attempt.id, 0))
                for attempt, user in rows
            ],
        )

    @staticmethod
    async def _pending_grading_by_attempt(
        db: AsyncSession, tenant_id: uuid.UUID, attempt_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not attempt_ids:
            return {}
        rows = (
            await db.execute(
                select(Answer.attempt_id, func.count(Answer.id))
                .join(Question, Question.id == Answer.question_id)
                .join(ExamAttempt, ExamAttempt.id == Answer.attempt_id)
                .where(
                    ExamAttempt.tenant_id == tenant_id,
                    Answer.attempt_id.in_(attempt_ids),
                    Answer.score.is_(None),
                    Question.question_type.notin_(_OBJECTIVE_QUESTION_TYPES),
                )
                .group_by(Answer.attempt_id)
            )
        ).all()
        return {attempt_id: int(count or 0) for attempt_id, count in rows}

    @staticmethod
    def _attempt_row(attempt: ExamAttempt, user: User, pending: int) -> TeacherAttemptRow:
        status_val = _value(attempt.status) or "IN_PROGRESS"
        return TeacherAttemptRow(
            attempt_id=attempt.id,
            student_id=user.id,
            student_name=user.name,
            roll_number=user.student_roll_no,
            status=status_val,
            started_at=attempt.started_at,
            submitted_at=attempt.submitted_at,
            total_score=float(attempt.total_score) if attempt.total_score is not None else None,
            percentage=float(attempt.percentage) if attempt.percentage is not None else None,
            grade=attempt.grade,
            tab_switch_count=attempt.tab_switch_count,
            pending_grading_count=pending,
        )

    @staticmethod
    async def attempt_detail(db: AsyncSession, teacher: User, exam_id: uuid.UUID, attempt_id: uuid.UUID) -> TeacherAttemptDetail:
        exam = await TeacherService._owned_exam(db, teacher, exam_id)
        row = (
            await db.execute(
                select(ExamAttempt, User)
                .join(User, and_(User.id == ExamAttempt.student_id, User.tenant_id == teacher.tenant_id))
                .where(
                    ExamAttempt.id == attempt_id,
                    ExamAttempt.tenant_id == teacher.tenant_id,
                    ExamAttempt.exam_id == exam.id,
                )
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam attempt not found")
        attempt, user = row
        answers = (
            await db.execute(
                select(Answer, Question)
                .join(Question, Question.id == Answer.question_id)
                .where(Answer.attempt_id == attempt.id)
                .order_by(Question.sort_order)
            )
        ).all()
        option_ids = [answer.selected_option_id for answer, _q in answers if answer.selected_option_id]
        question_ids = [question.id for _a, question in answers]
        option_texts: dict[uuid.UUID, str] = {}
        correct_texts: dict[uuid.UUID, str] = {}
        # Full option list per question so the grading panel can render the
        # complete answer key — every option, which one is correct and which
        # one the student picked — instead of a bare selected/correct pair.
        options_by_question: dict[uuid.UUID, list[TeacherAnswerOption]] = {}
        if option_ids or question_ids:
            option_rows = (
                await db.execute(
                    select(QuestionOption)
                    .where(
                        or_(
                            QuestionOption.id.in_(option_ids or [uuid.uuid4()]),
                            QuestionOption.question_id.in_(question_ids or [uuid.uuid4()]),
                        )
                    )
                    .order_by(QuestionOption.question_id, QuestionOption.sort_order)
                )
            ).scalars().all()
            for option in option_rows:
                option_texts[option.id] = option.text
                options_by_question.setdefault(option.question_id, []).append(
                    TeacherAnswerOption(
                        id=option.id,
                        text=option.text,
                        is_correct=option.is_correct,
                        sort_order=option.sort_order,
                    )
                )
                if option.is_correct:
                    correct_texts[option.question_id] = option.text
        pending = await TeacherService._pending_grading_by_attempt(db, teacher.tenant_id, [attempt.id])
        return TeacherAttemptDetail(
            **TeacherService._attempt_row(attempt, user, pending.get(attempt.id, 0)).model_dump(),
            answers=[
                TeacherAnswerRow(
                    answer_id=answer.id,
                    question_id=question.id,
                    question_text=question.text,
                    question_type=_value(question.question_type) or "SHORT_ANSWER",
                    marks=float(question.marks),
                    selected_option_id=answer.selected_option_id,
                    selected_option_text=option_texts.get(answer.selected_option_id) if answer.selected_option_id else None,
                    correct_option_text=correct_texts.get(question.id),
                    options=options_by_question.get(question.id, []),
                    text_answer=answer.text_answer,
                    matched_pairs=answer.matched_pairs,
                    score=float(answer.score) if answer.score is not None else None,
                    feedback=answer.feedback,
                    is_auto_graded=answer.is_auto_graded,
                )
                for answer, question in answers
            ],
        )

    @staticmethod
    async def grade_answers(
        db: AsyncSession, teacher: User, exam_id: uuid.UUID, attempt_id: uuid.UUID, payload
    ) -> TeacherAttemptDetail:
        exam = await TeacherService._owned_exam(db, teacher, exam_id)
        state = _value(exam.status) or "DRAFT"
        if state in (ExamStatus.RESULTS_RELEASED.value, ExamStatus.CANCELLED.value):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Results are already released for this exam")
        attempt = (
            await db.execute(
                select(ExamAttempt).where(
                    ExamAttempt.id == attempt_id,
                    ExamAttempt.tenant_id == teacher.tenant_id,
                    ExamAttempt.exam_id == exam.id,
                )
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam attempt not found")
        if _value(attempt.status) not in (AttemptStatus.SUBMITTED.value, AttemptStatus.GRADED.value):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Only submitted attempts can be graded")

        now = datetime.now(timezone.utc)
        for grade in payload.grades:
            row = (
                await db.execute(
                    select(Answer, Question)
                    .join(Question, Question.id == Answer.question_id)
                    .where(Answer.id == grade.answer_id, Answer.attempt_id == attempt.id)
                )
            ).first()
            if row is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Answer not found in this attempt")
            answer, question = row
            if grade.score > float(question.marks):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Score cannot exceed {float(question.marks)} for this question",
                )
            answer.score = Decimal(str(grade.score))
            answer.feedback = grade.feedback.strip() if grade.feedback else None
            answer.graded_by = teacher.id
            answer.graded_at = now
        await TeacherService._recompute_attempt(db, attempt, exam)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="GRADE_EXAM_ANSWERS",
            entity="ExamAttempt",
            entity_id=attempt.id,
            tenant_id=teacher.tenant_id,
            new_value={"grades": len(payload.grades)},
        )
        return await TeacherService.attempt_detail(db, teacher, exam_id, attempt_id)

    @staticmethod
    async def _recompute_attempt(db: AsyncSession, attempt: ExamAttempt, exam: Exam) -> None:
        total = (
            await db.execute(
                select(func.coalesce(func.sum(Answer.score), 0)).where(Answer.attempt_id == attempt.id)
            )
        ).scalar()
        unanswered_objective = (
            await db.execute(
                select(func.count(Answer.id))
                .join(Question, Question.id == Answer.question_id)
                .where(Answer.attempt_id == attempt.id, Answer.score.is_(None))
            )
        ).scalar() or 0
        if unanswered_objective:
            # Still waiting on descriptive grading; keep partial total hidden.
            attempt.total_score = Decimal(str(total))
            attempt.percentage = None
            attempt.grade = None
            return
        score = Decimal(str(total))
        percentage = (score * 100 / Decimal(exam.total_marks)).quantize(Decimal("0.01")) if exam.total_marks else None
        attempt.total_score = score
        attempt.percentage = percentage
        attempt.grade = grade_for(float(percentage)) if percentage is not None else None
        attempt.status = AttemptStatus.GRADED

    @staticmethod
    async def release_results(db: AsyncSession, teacher: User, exam_id: uuid.UUID) -> TeacherExamDetail:
        exam = await TeacherService._owned_exam(db, teacher, exam_id)
        state = _value(exam.status) or "DRAFT"
        if state not in (ExamStatus.ONGOING.value, ExamStatus.COMPLETED.value, ExamStatus.PUBLISHED.value):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This exam has no results to release")
        pending = (
            await db.execute(
                select(func.count(Answer.id))
                .join(ExamAttempt, ExamAttempt.id == Answer.attempt_id)
                .join(Question, Question.id == Answer.question_id)
                .where(
                    ExamAttempt.tenant_id == teacher.tenant_id,
                    ExamAttempt.exam_id == exam.id,
                    ExamAttempt.status == AttemptStatus.SUBMITTED,
                    Answer.score.is_(None),
                    Question.question_type.notin_(_OBJECTIVE_QUESTION_TYPES),
                )
            )
        ).scalar() or 0
        if pending:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"{pending} descriptive answers still need grading before results can be released",
            )
        attempts = (
            await db.execute(
                select(ExamAttempt).where(
                    ExamAttempt.tenant_id == teacher.tenant_id,
                    ExamAttempt.exam_id == exam.id,
                    ExamAttempt.status.in_((AttemptStatus.SUBMITTED, AttemptStatus.GRADED)),
                )
            )
        ).scalars().all()
        for attempt in attempts:
            await TeacherService._recompute_attempt(db, attempt, exam)
            attempt.status = AttemptStatus.GRADED
        exam.status = ExamStatus.RESULTS_RELEASED
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="RELEASE_EXAM_RESULTS",
            entity="Exam",
            entity_id=exam.id,
            tenant_id=teacher.tenant_id,
            new_value={"attempts": len(attempts)},
        )
        return await TeacherService.exam_detail(db, teacher, exam_id)

    # ── C-TC-12 … C-TC-16 assignments ────────────────────────────────────────

    @staticmethod
    async def assignments(
        db: AsyncSession,
        teacher: User,
        *,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TeacherAssignmentPage:
        TeacherService._validate_page(limit, offset)
        await TeacherService.scope_for_user(db, teacher)
        tenant_id = teacher.tenant_id
        clauses = [Assignment.tenant_id == tenant_id, Assignment.teacher_id == teacher.id]
        if status_filter and status_filter.strip().upper() != "ALL":
            wanted = status_filter.strip().upper()
            if wanted not in AssignmentStatus.__members__:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown assignment status")
            clauses.append(Assignment.status == AssignmentStatus[wanted])
        total = (await db.execute(select(func.count(Assignment.id)).where(*clauses))).scalar() or 0
        rows = (
            await db.execute(
                select(Assignment, Subject, SchoolClass)
                .join(Subject, Subject.id == Assignment.subject_id)
                .join(SchoolClass, SchoolClass.id == Assignment.class_id)
                .where(*clauses)
                .order_by(Assignment.due_date.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        stats = await TeacherService._assignment_stats(db, tenant_id, [assignment.id for assignment, _s, _c in rows])
        roster_counts = await TeacherService._roster_counts(db, tenant_id, [assignment.class_id for assignment, _s, _c in rows])
        milestone_counts = await TeacherService._milestone_counts(db, [assignment.id for assignment, _s, _c in rows])
        return TeacherAssignmentPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[
                TeacherService._assignment_row(
                    assignment,
                    subject,
                    school_class,
                    stats.get(assignment.id, {}),
                    roster_counts.get(assignment.class_id, 0),
                    milestone_counts.get(assignment.id, 0),
                )
                for assignment, subject, school_class in rows
            ],
        )

    @staticmethod
    async def _assignment_stats(db: AsyncSession, tenant_id: uuid.UUID, assignment_ids: list[uuid.UUID]) -> dict:
        if not assignment_ids:
            return {}
        rows = (
            await db.execute(
                select(
                    Submission.assignment_id,
                    func.count(Submission.student_id.distinct()),
                    func.coalesce(func.sum(case((Submission.status.in_(_PENDING_SUBMISSION_STATUSES), 1), else_=0)), 0),
                    func.coalesce(func.sum(case((Submission.reviewed_at.is_not(None), 1), else_=0)), 0),
                )
                .where(Submission.tenant_id == tenant_id, Submission.assignment_id.in_(assignment_ids))
                .group_by(Submission.assignment_id)
            )
        ).all()
        return {
            assignment_id: {
                "submission_count": int(count or 0),
                "pending_review_count": int(pending or 0),
                "reviewed_count": int(reviewed or 0),
            }
            for assignment_id, count, pending, reviewed in rows
        }

    @staticmethod
    async def _roster_counts(db: AsyncSession, tenant_id: uuid.UUID, class_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not class_ids:
            return {}
        current_year = await TeacherService._current_year(db, tenant_id)
        if current_year is None:
            return {}
        rows = (
            await db.execute(
                select(Enrollment.class_id, func.count(Enrollment.id))
                .where(
                    Enrollment.tenant_id == tenant_id,
                    Enrollment.academic_year_id == current_year.id,
                    Enrollment.class_id.in_(class_ids),
                )
                .group_by(Enrollment.class_id)
            )
        ).all()
        return {class_id: int(count or 0) for class_id, count in rows}

    @staticmethod
    async def _milestone_counts(db: AsyncSession, assignment_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not assignment_ids:
            return {}
        rows = (
            await db.execute(
                select(Milestone.assignment_id, func.count(Milestone.id))
                .where(Milestone.assignment_id.in_(assignment_ids))
                .group_by(Milestone.assignment_id)
            )
        ).all()
        return {assignment_id: int(count or 0) for assignment_id, count in rows}

    @staticmethod
    async def _group_counts(db: AsyncSession, assignment_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not assignment_ids:
            return {}
        rows = (
            await db.execute(
                select(ProjectGroup.assignment_id, func.count(ProjectGroup.id))
                .where(ProjectGroup.assignment_id.in_(assignment_ids))
                .group_by(ProjectGroup.assignment_id)
            )
        ).all()
        return {assignment_id: int(count or 0) for assignment_id, count in rows}

    @staticmethod
    def _assignment_row(
        assignment: Assignment,
        subject: Subject,
        school_class: SchoolClass,
        stats,
        student_count: int,
        milestone_count: int,
        group_count: int = 0,
    ) -> TeacherAssignmentRow:
        return TeacherAssignmentRow(
            id=assignment.id,
            title=assignment.title,
            class_id=assignment.class_id,
            class_name=school_class.name,
            subject_id=assignment.subject_id,
            subject_code=subject.code,
            subject_name=subject.name,
            assignment_type=assignment.assignment_type,
            total_marks=assignment.total_marks,
            due_date=assignment.due_date,
            status=_value(assignment.status) or "DRAFT",
            milestone_count=milestone_count,
            student_count=student_count,
            group_count=group_count,
            submission_count=stats.get("submission_count", 0),
            pending_review_count=stats.get("pending_review_count", 0),
            reviewed_count=stats.get("reviewed_count", 0),
        )

    @staticmethod
    async def create_assignment(db: AsyncSession, teacher: User, payload: TeacherAssignmentCreate) -> TeacherAssignmentDetail:
        scope = await TeacherService.scope_for_user(db, teacher)
        TeacherService._ensure_teaches(scope, payload.subject_id, payload.class_id)
        if payload.passing_marks > payload.total_marks:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="passing_marks cannot exceed total_marks")
        if payload.assignment_type == "GROUP" and payload.min_group_size > payload.max_group_size:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="min_group_size cannot exceed max_group_size")
        current_year = await TeacherService._current_year(db, teacher.tenant_id)
        if current_year is None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="No current academic year is set")
        assignment = Assignment(
            id=uuid.uuid4(),
            tenant_id=teacher.tenant_id,
            title=payload.title.strip(),
            description=payload.description.strip(),
            subject_id=payload.subject_id,
            class_id=payload.class_id,
            academic_year_id=current_year.id,
            teacher_id=teacher.id,
            assignment_type=payload.assignment_type,
            total_marks=payload.total_marks,
            passing_marks=payload.passing_marks,
            due_date=payload.due_date,
            allow_late_submission=payload.allow_late_submission,
            late_penalty_percent=payload.late_penalty_percent,
            max_file_size_mb=payload.max_file_size_mb,
            allowed_file_types=[ext.strip().lower().lstrip(".") for ext in payload.allowed_file_types if ext.strip()] or ["pdf"],
            min_group_size=payload.min_group_size,
            max_group_size=payload.max_group_size,
            instructions_url=payload.instructions_url,
            status=AssignmentStatus.PUBLISHED if payload.publish else AssignmentStatus.DRAFT,
        )
        db.add(assignment)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="CREATE_ASSIGNMENT",
            entity="Assignment",
            entity_id=assignment.id,
            tenant_id=teacher.tenant_id,
            new_value={"title": assignment.title, "status": assignment.status.value, "due_date": str(assignment.due_date)},
        )
        return await TeacherService.assignment_detail(db, teacher, assignment.id)

    @staticmethod
    async def _owned_assignment(db: AsyncSession, teacher: User, assignment_id: uuid.UUID) -> Assignment:
        assignment = (
            await db.execute(
                select(Assignment).where(
                    Assignment.id == assignment_id, Assignment.tenant_id == teacher.tenant_id
                )
            )
        ).scalar_one_or_none()
        if assignment is None or assignment.teacher_id != teacher.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        return assignment

    @staticmethod
    async def assignment_detail(db: AsyncSession, teacher: User, assignment_id: uuid.UUID) -> TeacherAssignmentDetail:
        assignment = await TeacherService._owned_assignment(db, teacher, assignment_id)
        meta = (
            await db.execute(
                select(Subject, SchoolClass)
                .join(SchoolClass, SchoolClass.id == Subject.class_id)
                .where(Subject.id == assignment.subject_id)
            )
        ).one()
        stats = await TeacherService._assignment_stats(db, teacher.tenant_id, [assignment.id])
        roster_counts = await TeacherService._roster_counts(db, teacher.tenant_id, [assignment.class_id])
        group_counts = await TeacherService._group_counts(db, [assignment.id])
        milestones = (
            await db.execute(
                select(Milestone).where(Milestone.assignment_id == assignment.id).order_by(Milestone.sort_order)
            )
        ).scalars().all()
        return TeacherAssignmentDetail(
            **TeacherService._assignment_row(
                assignment, meta[0], meta[1], stats.get(assignment.id, {}),
                roster_counts.get(assignment.class_id, 0), len(milestones),
                group_counts.get(assignment.id, 0),
            ).model_dump(),
            description=assignment.description,
            passing_marks=assignment.passing_marks,
            allow_late_submission=assignment.allow_late_submission,
            late_penalty_percent=assignment.late_penalty_percent,
            max_file_size_mb=assignment.max_file_size_mb,
            allowed_file_types=list(assignment.allowed_file_types or []),
            min_group_size=getattr(assignment, "min_group_size", 2) or 2,
            max_group_size=getattr(assignment, "max_group_size", 6) or 6,
            instructions_url=assignment.instructions_url,
            created_at=assignment.created_at,
            milestones=[
                TeacherMilestoneOut(
                    id=milestone.id,
                    title=milestone.title,
                    description=milestone.description,
                    sort_order=milestone.sort_order,
                    marks=milestone.marks,
                    due_date=milestone.due_date,
                    unlock_after_milestone_id=milestone.unlock_after_milestone_id,
                )
                for milestone in milestones
            ],
        )

    @staticmethod
    async def update_assignment(
        db: AsyncSession, teacher: User, assignment_id: uuid.UUID, payload: TeacherAssignmentUpdate
    ) -> TeacherAssignmentDetail:
        assignment = await TeacherService._owned_assignment(db, teacher, assignment_id)
        state = _value(assignment.status) or "DRAFT"
        if state == AssignmentStatus.CLOSED.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Closed assignments cannot be edited")
        updates = payload.model_dump(exclude_unset=True)
        if "title" in updates and updates["title"] is not None:
            updates["title"] = updates["title"].strip()
        if "description" in updates and updates["description"] is not None:
            updates["description"] = updates["description"].strip()
        next_total = updates.get("total_marks", assignment.total_marks)
        next_passing = updates.get("passing_marks", assignment.passing_marks)
        if next_passing is not None and next_total is not None and next_passing > next_total:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="passing_marks cannot exceed total_marks")
        if "allowed_file_types" in updates and updates["allowed_file_types"] is not None:
            updates["allowed_file_types"] = [
                ext.strip().lower().lstrip(".") for ext in updates["allowed_file_types"] if ext.strip()
            ] or ["pdf"]
        for key, value in updates.items():
            setattr(assignment, key, value)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="UPDATE_ASSIGNMENT",
            entity="Assignment",
            entity_id=assignment.id,
            tenant_id=teacher.tenant_id,
            new_value={key: str(value) for key, value in updates.items()},
        )
        return await TeacherService.assignment_detail(db, teacher, assignment_id)

    @staticmethod
    async def transition_assignment(
        db: AsyncSession,
        teacher: User,
        assignment_id: uuid.UUID,
        action: str,
        *,
        request_resubmission: bool = True,
    ) -> TeacherAssignmentDetail:
        """DRAFT→PUBLISHED, PUBLISHED→CLOSED, CLOSED→PUBLISHED (reopen).

        Reopen additionally hands un-reviewed work back to students: the latest
        SUBMITTED / UNDER_REVIEW submission of every student (per milestone
        scope) is moved to RESUBMIT_REQUESTED so the assignment re-appears in
        their pending list with a resubmit action.  Already-reviewed submissions
        (APPROVED / REJECTED) and older versions are never touched.  Teachers
        who only want to accept work from students who never submitted can pass
        ``request_resubmission=False``.
        """
        assignment = await TeacherService._owned_assignment(db, teacher, assignment_id)
        state = _value(assignment.status) or "DRAFT"
        reopened_submissions: list[uuid.UUID] = []
        notified_students: set[uuid.UUID] = set()
        if action == "publish":
            if state != AssignmentStatus.DRAFT.value:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="Only drafts can be published")
            assignment.status = AssignmentStatus.PUBLISHED
        elif action == "reopen":
            if state != AssignmentStatus.CLOSED.value:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="Only closed assignments can be reopened")
            assignment.status = AssignmentStatus.PUBLISHED
            if request_resubmission:
                # One statement: newest un-reviewed version per (student,
                # milestone) scope — the same scope submit_assignment gates on.
                # DISTINCT ON groups NULL milestone_id with NULL (assignment-
                # level submissions), matching SQL "not distinct" semantics.
                rows = (
                    await db.execute(
                        update(Submission)
                        .where(
                            Submission.id.in_(
                                select(Submission.id)
                                .where(
                                    Submission.tenant_id == teacher.tenant_id,
                                    Submission.assignment_id == assignment.id,
                                    Submission.status.in_(
                                        (SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW)
                                    ),
                                )
                                .distinct(Submission.student_id, Submission.milestone_id)
                                .order_by(
                                    Submission.student_id, Submission.milestone_id, Submission.version.desc()
                                )
                            )
                        )
                        .values(status=SubmissionStatus.RESUBMIT_REQUESTED)
                        .returning(Submission.id, Submission.student_id)
                        .execution_options(synchronize_session=False)
                    )
                ).all()
                reopened_submissions = [row[0] for row in rows]
                notified_students = {row[1] for row in rows}
        else:
            if state != AssignmentStatus.PUBLISHED.value:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="Only published assignments can be closed")
            assignment.status = AssignmentStatus.CLOSED
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action=f"{action.upper()}_ASSIGNMENT",
            entity="Assignment",
            entity_id=assignment.id,
            tenant_id=teacher.tenant_id,
            new_value={
                "status": assignment.status.value,
                **(
                    {"resubmission_requested": len(reopened_submissions)}
                    if action == "reopen"
                    else {}
                ),
            },
        )
        if notified_students:
            # Best-effort nudge — a notification problem must never fail the
            # reopen.  Group submissions notify the lead submitter, mirroring
            # the review notification in review_submission.
            try:
                await PushService.create_in_app_notifications(
                    db,
                    tenant_id=teacher.tenant_id,
                    user_ids=list(notified_students),
                    title="Assignment reopened",
                    body=f'"{assignment.title}" is open again — you may review your work and resubmit.',
                    notif_type="ASSIGNMENT_REOPENED",
                    data={
                        "assignment_id": str(assignment.id),
                        "resubmission": True,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - notification must not fail a reopen
                logger.warning("Failed to notify students after reopening assignment %s: %s", assignment.id, exc)
        return await TeacherService.assignment_detail(db, teacher, assignment_id)

    @staticmethod
    async def add_milestone(
        db: AsyncSession, teacher: User, assignment_id: uuid.UUID, payload: TeacherMilestoneIn
    ) -> TeacherAssignmentDetail:
        assignment = await TeacherService._owned_assignment(db, teacher, assignment_id)
        if (_value(assignment.status) or "DRAFT") == AssignmentStatus.CLOSED.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Closed assignments cannot be edited")
        if payload.unlock_after_milestone_id is not None:
            unlock = (
                await db.execute(
                    select(Milestone.id).where(
                        Milestone.id == payload.unlock_after_milestone_id,
                        Milestone.assignment_id == assignment.id,
                    )
                )
            ).scalar_one_or_none()
            if unlock is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unlock_after_milestone_id must reference a milestone of this assignment")
        existing_marks, count = (
            await db.execute(
                select(func.coalesce(func.sum(Milestone.marks), 0), func.count(Milestone.id)).where(
                    Milestone.assignment_id == assignment.id
                )
            )
        ).one()
        if int(existing_marks or 0) + payload.marks > assignment.total_marks:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Milestone marks exceed the assignment total_marks",
            )
        milestone = Milestone(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else None,
            sort_order=int(count or 0) + 1,
            marks=payload.marks,
            due_date=payload.due_date,
            unlock_after_milestone_id=payload.unlock_after_milestone_id,
        )
        db.add(milestone)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="ADD_MILESTONE",
            entity="Milestone",
            entity_id=milestone.id,
            tenant_id=teacher.tenant_id,
            new_value={"assignment_id": str(assignment.id), "title": milestone.title},
        )
        return await TeacherService.assignment_detail(db, teacher, assignment_id)

    @staticmethod
    async def delete_milestone(db: AsyncSession, teacher: User, assignment_id: uuid.UUID, milestone_id: uuid.UUID) -> TeacherAssignmentDetail:
        assignment = await TeacherService._owned_assignment(db, teacher, assignment_id)
        if (_value(assignment.status) or "DRAFT") == AssignmentStatus.CLOSED.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Closed assignments cannot be edited")
        milestone = (
            await db.execute(
                select(Milestone).where(Milestone.id == milestone_id, Milestone.assignment_id == assignment.id)
            )
        ).scalar_one_or_none()
        if milestone is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Milestone not found")
        has_submissions = (
            await db.execute(
                select(Submission.id).where(
                    Submission.tenant_id == teacher.tenant_id, Submission.milestone_id == milestone.id
                ).limit(1)
            )
        ).scalar_one_or_none()
        if has_submissions is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Students have already submitted against this milestone")
        await db.delete(milestone)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="DELETE_MILESTONE",
            entity="Milestone",
            entity_id=milestone.id,
            tenant_id=teacher.tenant_id,
            old_value={"title": milestone.title},
        )
        return await TeacherService.assignment_detail(db, teacher, assignment_id)

    @staticmethod
    async def update_milestone(
        db: AsyncSession, teacher: User, assignment_id: uuid.UUID, milestone_id: uuid.UUID, payload: TeacherMilestoneUpdateIn
    ) -> TeacherAssignmentDetail:
        assignment = await TeacherService._owned_assignment(db, teacher, assignment_id)
        if (_value(assignment.status) or "DRAFT") == AssignmentStatus.CLOSED.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Closed assignments cannot be edited")
        milestone = (
            await db.execute(
                select(Milestone).where(Milestone.id == milestone_id, Milestone.assignment_id == assignment.id)
            )
        ).scalar_one_or_none()
        if milestone is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Milestone not found")
        if payload.marks is not None and payload.marks != milestone.marks:
            existing_marks = (
                await db.execute(
                    select(func.coalesce(func.sum(Milestone.marks), 0)).where(
                        Milestone.assignment_id == assignment.id,
                        Milestone.id != milestone.id,
                    )
                )
            ).scalar()
            if int(existing_marks or 0) + payload.marks > assignment.total_marks:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Milestone marks exceed the assignment total_marks",
                )
            milestone.marks = payload.marks
        if payload.title is not None:
            milestone.title = payload.title.strip()
        if payload.description is not None:
            milestone.description = payload.description.strip() if payload.description else None
        if payload.due_date is not None or "due_date" in payload.model_fields_set:
            milestone.due_date = payload.due_date
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="UPDATE_MILESTONE",
            entity="Milestone",
            entity_id=milestone.id,
            tenant_id=teacher.tenant_id,
            new_value={"title": milestone.title, "marks": milestone.marks},
        )
        return await TeacherService.assignment_detail(db, teacher, assignment_id)

    # ── Group project management ─────────────────────────────────────────────

    @staticmethod
    async def list_assignment_groups(
        db: AsyncSession,
        teacher: User,
        assignment_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> TeacherGroupPage:
        TeacherService._validate_page(limit, offset)
        assignment = await TeacherService._owned_assignment(db, teacher, assignment_id)
        tenant_id = teacher.tenant_id

        total = (
            await db.execute(
                select(func.count(ProjectGroup.id)).where(
                    ProjectGroup.assignment_id == assignment.id,
                    ProjectGroup.tenant_id == tenant_id,
                )
            )
        ).scalar() or 0

        groups = (
            await db.execute(
                select(ProjectGroup, User)
                .outerjoin(User, and_(User.id == ProjectGroup.created_by, User.tenant_id == tenant_id))
                .where(
                    ProjectGroup.assignment_id == assignment.id,
                    ProjectGroup.tenant_id == tenant_id,
                )
                .order_by(ProjectGroup.created_at.asc())
                .limit(limit)
                .offset(offset)
            )
        ).all()

        if not groups:
            return TeacherGroupPage(total=0, limit=limit, offset=offset, items=[])

        group_ids = [g[0].id for g in groups]

        # Fetch members for all these groups
        members_rows = (
            await db.execute(
                select(ProjectGroupMember, User, Enrollment)
                .join(User, and_(User.id == ProjectGroupMember.student_id, User.tenant_id == tenant_id))
                .outerjoin(
                    Enrollment,
                    and_(
                        Enrollment.student_id == ProjectGroupMember.student_id,
                        Enrollment.class_id == assignment.class_id,
                        Enrollment.academic_year_id == assignment.academic_year_id,
                        Enrollment.tenant_id == tenant_id,
                    ),
                )
                .where(ProjectGroupMember.group_id.in_(group_ids))
                .order_by(ProjectGroupMember.joined_at.asc())
            )
        ).all()

        members_by_group: dict[uuid.UUID, list[TeacherGroupMember]] = {gid: [] for gid in group_ids}
        for member, user, enrollment in members_rows:
            members_by_group[member.group_id].append(
                TeacherGroupMember(
                    student_id=user.id,
                    student_name=user.name,
                    roll_number=(enrollment.roll_number if enrollment and enrollment.roll_number else user.student_roll_no),
                    joined_at=member.joined_at,
                )
            )

        # Check submissions for these groups
        submissions_rows = (
            await db.execute(
                select(Submission.id, Submission.group_id, Submission.student_id)
                .where(
                    Submission.assignment_id == assignment.id,
                    Submission.tenant_id == tenant_id,
                )
            )
        ).all()

        # Map group_id or member student_ids to submissions
        submission_by_group: dict[uuid.UUID, uuid.UUID] = {}
        for sub_id, sub_gid, sub_sid in submissions_rows:
            if sub_gid and sub_gid in group_ids:
                submission_by_group[sub_gid] = sub_id
            else:
                # check if student is in one of the groups
                for gid, mems in members_by_group.items():
                    if any(m.student_id == sub_sid for m in mems):
                        submission_by_group[gid] = sub_id

        # Task counts per group
        tasks_stat_rows = (
            await db.execute(
                select(
                    ProjectGroupTask.group_id,
                    func.count(ProjectGroupTask.id).label("total_tasks"),
                    func.count(case((ProjectGroupTask.status == "DONE", 1))).label("done_tasks"),
                )
                .where(ProjectGroupTask.group_id.in_(group_ids), ProjectGroupTask.tenant_id == tenant_id)
                .group_by(ProjectGroupTask.group_id)
            )
        ).all()
        tasks_by_group = {row[0]: (row[1], row[2]) for row in tasks_stat_rows}

        # Message counts per group
        msgs_stat_rows = (
            await db.execute(
                select(ProjectGroupMessage.group_id, func.count(ProjectGroupMessage.id))
                .where(ProjectGroupMessage.group_id.in_(group_ids), ProjectGroupMessage.tenant_id == tenant_id)
                .group_by(ProjectGroupMessage.group_id)
            )
        ).all()
        msgs_by_group = {row[0]: row[1] for row in msgs_stat_rows}

        # Resource counts per group
        res_stat_rows = (
            await db.execute(
                select(ProjectGroupResource.group_id, func.count(ProjectGroupResource.id))
                .where(ProjectGroupResource.group_id.in_(group_ids), ProjectGroupResource.tenant_id == tenant_id)
                .group_by(ProjectGroupResource.group_id)
            )
        ).all()
        res_by_group = {row[0]: row[1] for row in res_stat_rows}

        items = [
            TeacherGroupRow(
                id=group.id,
                assignment_id=group.assignment_id,
                name=group.name,
                created_by=group.created_by,
                creator_name=creator.name if creator else None,
                created_at=group.created_at,
                member_count=len(members_by_group.get(group.id, [])),
                is_submitted=group.id in submission_by_group,
                submission_id=submission_by_group.get(group.id),
                tasks_count=tasks_by_group.get(group.id, (0, 0))[0],
                tasks_done_count=tasks_by_group.get(group.id, (0, 0))[1],
                messages_count=msgs_by_group.get(group.id, 0),
                resources_count=res_by_group.get(group.id, 0),
                members=members_by_group.get(group.id, []),
            )
            for group, creator in groups
        ]

        return TeacherGroupPage(total=int(total), limit=limit, offset=offset, items=items)

    @staticmethod
    async def get_assignment_group(
        db: AsyncSession,
        teacher: User,
        assignment_id: uuid.UUID,
        group_id: uuid.UUID,
    ) -> TeacherGroupRow:
        assignment = await TeacherService._owned_assignment(db, teacher, assignment_id)
        tenant_id = teacher.tenant_id

        row = (
            await db.execute(
                select(ProjectGroup, User)
                .outerjoin(User, and_(User.id == ProjectGroup.created_by, User.tenant_id == tenant_id))
                .where(
                    ProjectGroup.id == group_id,
                    ProjectGroup.assignment_id == assignment.id,
                    ProjectGroup.tenant_id == tenant_id,
                )
            )
        ).first()

        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Group not found")

        group, creator = row

        members_rows = (
            await db.execute(
                select(ProjectGroupMember, User, Enrollment)
                .join(User, and_(User.id == ProjectGroupMember.student_id, User.tenant_id == tenant_id))
                .outerjoin(
                    Enrollment,
                    and_(
                        Enrollment.student_id == ProjectGroupMember.student_id,
                        Enrollment.class_id == assignment.class_id,
                        Enrollment.academic_year_id == assignment.academic_year_id,
                        Enrollment.tenant_id == tenant_id,
                    ),
                )
                .where(ProjectGroupMember.group_id == group.id)
                .order_by(ProjectGroupMember.joined_at.asc())
            )
        ).all()

        members = [
            TeacherGroupMember(
                student_id=user.id,
                student_name=user.name,
                roll_number=(enrollment.roll_number if enrollment and enrollment.roll_number else user.student_roll_no),
                joined_at=member.joined_at,
            )
            for member, user, enrollment in members_rows
        ]

        sub = (
            await db.execute(
                select(Submission.id).where(
                    Submission.assignment_id == assignment.id,
                    Submission.tenant_id == tenant_id,
                    or_(
                        Submission.group_id == group.id,
                        Submission.student_id.in_([m.student_id for m in members] if members else [uuid.uuid4()]),
                    ),
                )
            )
        ).scalar_one_or_none()

        task_counts = (
            await db.execute(
                select(
                    func.count(ProjectGroupTask.id),
                    func.count(case((ProjectGroupTask.status == "DONE", 1))),
                ).where(ProjectGroupTask.group_id == group.id, ProjectGroupTask.tenant_id == tenant_id)
            )
        ).first()

        msg_count = (
            await db.execute(
                select(func.count(ProjectGroupMessage.id)).where(
                    ProjectGroupMessage.group_id == group.id, ProjectGroupMessage.tenant_id == tenant_id
                )
            )
        ).scalar() or 0

        res_count = (
            await db.execute(
                select(func.count(ProjectGroupResource.id)).where(
                    ProjectGroupResource.group_id == group.id, ProjectGroupResource.tenant_id == tenant_id
                )
            )
        ).scalar() or 0

        return TeacherGroupRow(
            id=group.id,
            assignment_id=group.assignment_id,
            name=group.name,
            created_by=group.created_by,
            creator_name=creator.name if creator else None,
            created_at=group.created_at,
            member_count=len(members),
            is_submitted=sub is not None,
            submission_id=sub,
            tasks_count=task_counts[0] if task_counts else 0,
            tasks_done_count=task_counts[1] if task_counts else 0,
            messages_count=msg_count,
            resources_count=res_count,
            members=members,
        )

    @staticmethod
    async def get_teacher_team_workspace(
        db: AsyncSession,
        teacher: User,
        group_id: uuid.UUID,
    ) -> TeacherTeamWorkspace:
        tenant_id = teacher.tenant_id

        group_row_data = (
            await db.execute(
                select(ProjectGroup, Assignment, SchoolClass, Subject)
                .join(Assignment, Assignment.id == ProjectGroup.assignment_id)
                .join(SchoolClass, SchoolClass.id == Assignment.class_id)
                .join(Subject, Subject.id == Assignment.subject_id)
                .where(
                    ProjectGroup.id == group_id,
                    ProjectGroup.tenant_id == tenant_id,
                )
            )
        ).first()

        if group_row_data is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Group not found")

        group, assignment, school_class, subject = group_row_data

        # Verify teacher has access to this class or assignment
        await TeacherService._owned_assignment(db, teacher, assignment.id)

        group_row = await TeacherService.get_assignment_group(db, teacher, assignment.id, group.id)

        # Tasks
        task_rows = (
            await db.execute(
                select(ProjectGroupTask, User)
                .outerjoin(User, and_(User.id == ProjectGroupTask.assigned_to, User.tenant_id == tenant_id))
                .where(
                    ProjectGroupTask.group_id == group_id,
                    ProjectGroupTask.tenant_id == tenant_id,
                )
                .order_by(ProjectGroupTask.created_at.asc())
            )
        ).all()

        tasks = [
            StudentGroupTaskOut(
                id=task.id,
                group_id=task.group_id,
                title=task.title,
                description=task.description,
                assigned_to=task.assigned_to,
                assignee_name=assignee.name if assignee else None,
                status=task.status,
                due_date=task.due_date,
                created_by=task.created_by,
                creator_name=None,
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
            for task, assignee in task_rows
        ]

        # Messages
        msg_rows = (
            await db.execute(
                select(ProjectGroupMessage, User)
                .join(User, and_(User.id == ProjectGroupMessage.sender_id, User.tenant_id == tenant_id))
                .where(
                    ProjectGroupMessage.group_id == group_id,
                    ProjectGroupMessage.tenant_id == tenant_id,
                )
                .order_by(ProjectGroupMessage.created_at.asc())
            )
        ).all()

        messages = [
            StudentGroupMessageOut(
                id=msg.id,
                group_id=msg.group_id,
                sender_id=msg.sender_id,
                sender_name=sender.name,
                is_me=False,
                message=msg.message,
                created_at=msg.created_at,
            )
            for msg, sender in msg_rows
        ]

        # Resources
        res_rows = (
            await db.execute(
                select(ProjectGroupResource, User)
                .outerjoin(User, and_(User.id == ProjectGroupResource.created_by, User.tenant_id == tenant_id))
                .where(
                    ProjectGroupResource.group_id == group_id,
                    ProjectGroupResource.tenant_id == tenant_id,
                )
                .order_by(ProjectGroupResource.created_at.desc())
            )
        ).all()

        resources = [
            StudentGroupResourceOut(
                id=res.id,
                group_id=res.group_id,
                title=res.title,
                url=res.url,
                resource_type=res.resource_type,
                created_by=res.created_by,
                creator_name=creator.name if creator else None,
                created_at=res.created_at,
            )
            for res, creator in res_rows
        ]

        # Submission detail if submitted
        submission_detail = None
        if group_row.submission_id:
            try:
                submission_detail = await TeacherService.submission_detail(
                    db, teacher, group_row.submission_id
                )
            except Exception:
                submission_detail = None

        return TeacherTeamWorkspace(
            group=group_row,
            assignment_id=assignment.id,
            assignment_title=assignment.title,
            class_name=school_class.name,
            subject_code=subject.code,
            subject_name=subject.name,
            due_date=assignment.due_date,
            tasks=tasks,
            messages=messages,
            resources=resources,
            submission=submission_detail,
        )

    @staticmethod
    async def remove_student_from_group(
        db: AsyncSession,
        teacher: User,
        assignment_id: uuid.UUID,
        group_id: uuid.UUID,
        student_id: uuid.UUID,
    ) -> TeacherGroupRow:
        assignment = await TeacherService._owned_assignment(db, teacher, assignment_id)
        tenant_id = teacher.tenant_id

        member = (
            await db.execute(
                select(ProjectGroupMember).where(
                    ProjectGroupMember.group_id == group_id,
                    ProjectGroupMember.student_id == student_id,
                    ProjectGroupMember.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()

        if member is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student is not a member of this group")

        await db.delete(member)
        await db.flush()

        # Check if group is empty; if so, delete the group
        remaining_count = (
            await db.execute(
                select(func.count(ProjectGroupMember.id)).where(ProjectGroupMember.group_id == group_id)
            )
        ).scalar() or 0

        if remaining_count == 0:
            group = (
                await db.execute(
                    select(ProjectGroup).where(ProjectGroup.id == group_id)
                )
            ).scalar_one_or_none()
            if group:
                await db.delete(group)
                await db.flush()
            AuditService.record(
                db,
                actor=teacher,
                actor_role="TEACHER",
                action="DELETE_EMPTY_GROUP",
                entity="ProjectGroup",
                entity_id=group_id,
                tenant_id=tenant_id,
                old_value={"group_id": str(group_id), "assignment_id": str(assignment_id)},
            )
            # Return placeholder
            return TeacherGroupRow(
                id=group_id,
                assignment_id=assignment_id,
                name="[Deleted]",
                created_at=datetime.now(timezone.utc),
                member_count=0,
                members=[],
            )

        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="REMOVE_STUDENT_FROM_GROUP",
            entity="ProjectGroupMember",
            entity_id=member.id,
            tenant_id=tenant_id,
            old_value={"student_id": str(student_id), "group_id": str(group_id)},
        )

        return await TeacherService.get_assignment_group(db, teacher, assignment_id, group_id)

    # ── C-TC-15 / C-TC-16 submissions review ────────────────────────────────

    @staticmethod
    async def submissions(
        db: AsyncSession,
        teacher: User,
        *,
        assignment_id: uuid.UUID | None = None,
        status_filter: str | None = None,
        milestone_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TeacherSubmissionPage:
        TeacherService._validate_page(limit, offset)
        tenant_id = teacher.tenant_id
        clauses = [Submission.tenant_id == tenant_id, Assignment.teacher_id == teacher.id]
        if assignment_id is not None:
            assignment = await TeacherService._owned_assignment(db, teacher, assignment_id)
            clauses.append(Submission.assignment_id == assignment.id)
        else:
            await TeacherService.scope_for_user(db, teacher)
        if milestone_id is not None:
            clauses.append(Submission.milestone_id == milestone_id)
        if status_filter and status_filter.strip().upper() != "ALL":
            wanted = status_filter.strip().upper()
            if wanted not in SubmissionStatus.__members__:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown submission status")
            clauses.append(Submission.status == SubmissionStatus[wanted])
        total = (
            await db.execute(
                select(func.count(Submission.id)).select_from(Submission)
                .join(Assignment, Assignment.id == Submission.assignment_id)
                .where(*clauses)
            )
        ).scalar() or 0
        rows = (
            await db.execute(
                select(Submission, User, Enrollment, Milestone, ProjectGroup)
                .join(Assignment, Assignment.id == Submission.assignment_id)
                .join(User, and_(User.id == Submission.student_id, User.tenant_id == tenant_id))
                .outerjoin(
                    Enrollment,
                    and_(
                        Enrollment.student_id == Submission.student_id,
                        Enrollment.class_id == Assignment.class_id,
                        Enrollment.academic_year_id == Assignment.academic_year_id,
                        Enrollment.tenant_id == tenant_id,
                    ),
                )
                .outerjoin(Milestone, Milestone.id == Submission.milestone_id)
                .outerjoin(ProjectGroup, ProjectGroup.id == Submission.group_id)
                .where(*clauses)
                .order_by(Submission.submitted_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return TeacherSubmissionPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[
                TeacherService._submission_row(submission, user, enrollment, milestone, project_group)
                for submission, user, enrollment, milestone, project_group in rows
            ],
        )

    @staticmethod
    def _submission_row(
        submission: Submission,
        user: User,
        enrollment,
        milestone: Milestone | None,
        project_group: ProjectGroup | None = None,
    ) -> TeacherSubmissionRow:
        return TeacherSubmissionRow(
            id=submission.id,
            student_id=submission.student_id,
            student_name=user.name,
            roll_number=(enrollment.roll_number if enrollment and enrollment.roll_number else user.student_roll_no),
            group_id=submission.group_id,
            group_name=project_group.name if project_group else None,
            milestone_id=submission.milestone_id,
            milestone_title=milestone.title if milestone else None,
            milestone_marks=milestone.marks if milestone else None,
            submitted_at=submission.submitted_at,
            is_late=submission.is_late,
            late_by_minutes=submission.late_by_minutes,
            status=_value(submission.status) or "SUBMITTED",
            score=float(submission.score) if submission.score is not None else None,
            grade=submission.grade,
            version=submission.version or 1,
        )

    @staticmethod
    async def submission_detail(db: AsyncSession, teacher: User, submission_id: uuid.UUID) -> TeacherSubmissionDetail:
        row = (
            await db.execute(
                select(Submission, Assignment, User, Enrollment, Milestone, ProjectGroup)
                .join(Assignment, Assignment.id == Submission.assignment_id)
                .join(User, and_(User.id == Submission.student_id, User.tenant_id == teacher.tenant_id))
                .outerjoin(
                    Enrollment,
                    and_(
                        Enrollment.student_id == Submission.student_id,
                        Enrollment.class_id == Assignment.class_id,
                        Enrollment.academic_year_id == Assignment.academic_year_id,
                        Enrollment.tenant_id == teacher.tenant_id,
                    ),
                )
                .outerjoin(Milestone, Milestone.id == Submission.milestone_id)
                .outerjoin(ProjectGroup, ProjectGroup.id == Submission.group_id)
                .where(Submission.id == submission_id, Submission.tenant_id == teacher.tenant_id)
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Submission not found")
        submission, assignment, user, enrollment, milestone, project_group = row
        if assignment.teacher_id != teacher.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Submission not found")
        return await TeacherService._submission_detail(
            db, teacher.tenant_id, submission, assignment, user, enrollment, milestone, project_group
        )

    @staticmethod
    async def _submission_detail(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        submission: Submission,
        assignment: Assignment,
        user: User,
        enrollment,
        milestone: Milestone | None,
        project_group: ProjectGroup | None = None,
    ) -> TeacherSubmissionDetail:
        files = (
            await db.execute(
                select(SubmissionFile).where(SubmissionFile.submission_id == submission.id).order_by(SubmissionFile.uploaded_at)
            )
        ).scalars().all()
        reviews = (
            await db.execute(
                select(SubmissionReview, User.name)
                .outerjoin(User, and_(User.id == SubmissionReview.reviewer_id, User.tenant_id == tenant_id))
                .where(SubmissionReview.submission_id == submission.id, SubmissionReview.tenant_id == tenant_id)
                .order_by(SubmissionReview.reviewed_at)
            )
        ).all()
        return TeacherSubmissionDetail(
            **TeacherService._submission_row(submission, user, enrollment, milestone, project_group).model_dump(),
            assignment_id=assignment.id,
            assignment_title=assignment.title,
            total_marks=assignment.total_marks,
            text_response=submission.text_response,
            feedback=submission.feedback,
            files=[
                TeacherSubmissionFileOut(
                    id=file.id,
                    file_name=file.file_name,
                    file_key=file.file_key,
                    file_size_bytes=file.file_size_bytes,
                    mime_type=file.mime_type,
                    uploaded_at=file.uploaded_at,
                )
                for file in files
            ],
            reviews=[
                TeacherReviewHistoryRow(
                    id=review.id,
                    reviewer_name=reviewer_name,
                    decision=_value(review.decision) or "APPROVED",
                    marks_awarded=float(review.marks_awarded) if review.marks_awarded is not None else None,
                    feedback=review.feedback,
                    attempt_number=review.attempt_number,
                    reviewed_at=review.reviewed_at,
                )
                for review, reviewer_name in reviews
            ],
        )

    @staticmethod
    async def review_submission(
        db: AsyncSession, teacher: User, submission_id: uuid.UUID, payload: TeacherSubmissionReviewIn
    ) -> TeacherSubmissionDetail:
        row = (
            await db.execute(
                select(Submission, Assignment, User, Enrollment, Milestone)
                .join(Assignment, Assignment.id == Submission.assignment_id)
                .join(User, and_(User.id == Submission.student_id, User.tenant_id == teacher.tenant_id))
                .outerjoin(
                    Enrollment,
                    and_(
                        Enrollment.student_id == Submission.student_id,
                        Enrollment.class_id == Assignment.class_id,
                        Enrollment.academic_year_id == Assignment.academic_year_id,
                        Enrollment.tenant_id == teacher.tenant_id,
                    ),
                )
                .outerjoin(Milestone, Milestone.id == Submission.milestone_id)
                .where(
                    Submission.id == submission_id,
                    Submission.tenant_id == teacher.tenant_id,
                    Assignment.teacher_id == teacher.id,
                )
                .with_for_update(of=Submission)
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Submission not found")
        submission, assignment, user, enrollment, milestone = row
        if payload.decision == "APPROVED" and payload.score is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A score is required to approve a submission")
        max_allowed = milestone.marks if milestone is not None else assignment.total_marks
        if payload.score is not None and payload.score > max_allowed:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Score cannot exceed {max_allowed}",
            )
        now = datetime.now(timezone.utc)
        decision_map = {
            "APPROVED": SubmissionStatus.APPROVED,
            "REJECTED": SubmissionStatus.REJECTED,
            "CHANGES_REQUESTED": SubmissionStatus.RESUBMIT_REQUESTED,
        }
        old_status = _value(submission.status)
        submission.status = decision_map[payload.decision]
        submission.reviewed_by = teacher.id
        submission.reviewed_at = now
        submission.feedback = payload.feedback.strip() if payload.feedback else None
        if payload.decision == "CHANGES_REQUESTED":
            submission.score = None
            submission.grade = None
        else:
            submission.score = Decimal(str(payload.score)) if payload.score is not None else None
            submission.grade = (
                grade_for(float(payload.score) * 100 / max_allowed) if payload.score is not None else None
            )
        db.add(
            SubmissionReview(
                id=uuid.uuid4(),
                tenant_id=teacher.tenant_id,
                submission_id=submission.id,
                reviewer_id=teacher.id,
                decision=ReviewDecision(payload.decision),
                marks_awarded=Decimal(str(payload.score)) if payload.score is not None else None,
                feedback=payload.feedback.strip() if payload.feedback else None,
                attempt_number=submission.version or 1,
            )
        )
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action=f"REVIEW_SUBMISSION_{payload.decision}",
            entity="Submission",
            entity_id=submission.id,
            tenant_id=teacher.tenant_id,
            old_value={"status": old_status},
            new_value={"status": submission.status.value, "score": payload.score},
        )

        # Notify the submitting student that their work was reviewed. For
        # group submissions the lead submitter is the student_id on the row;
        # milestones/group members already see the status change in-app.
        decision_label = {
            "APPROVED": "approved",
            "REJECTED": "rejected",
            "CHANGES_REQUESTED": "sent back with change requests",
        }.get(payload.decision, payload.decision.lower())
        try:
            await PushService.create_in_app_notifications(
                db,
                tenant_id=teacher.tenant_id,
                user_ids=[submission.student_id],
                title="Your submission was reviewed",
                body=f'Your submission for "{assignment.title}" was {decision_label}.',
                notif_type="ASSIGNMENT_REVIEWED",
                data={
                    "assignment_id": str(assignment.id),
                    "submission_id": str(submission.id),
                    "decision": payload.decision,
                },
            )
        except Exception as exc:  # noqa: BLE001 - notification must not fail a review
            logger.warning("Failed to notify student after review: %s", exc)
        return await TeacherService._submission_detail(
            db, teacher.tenant_id, submission, assignment, user, enrollment, milestone
        )

    # ── C-TC-17 / C-TC-18 content ───────────────────────────────────────────

    @staticmethod
    async def content(
        db: AsyncSession,
        teacher: User,
        *,
        subject_id: uuid.UUID | None = None,
        class_id: uuid.UUID | None = None,
        content_type: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TeacherContentPage:
        TeacherService._validate_page(limit, offset)
        await TeacherService.scope_for_user(db, teacher)
        tenant_id = teacher.tenant_id
        clauses = [
            ContentItem.tenant_id == tenant_id,
            ContentItem.uploaded_by == teacher.id,
            ContentItem.deleted_at.is_(None),
        ]
        if subject_id is not None:
            clauses.append(ContentItem.subject_id == subject_id)
        if class_id is not None:
            clauses.append(ContentItem.class_id == class_id)
        if content_type and content_type.strip().upper() != "ALL":
            wanted = content_type.strip().upper()
            if wanted not in ContentKind.__members__:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown content type")
            clauses.append(ContentItem.content_type == ContentKind[wanted])
        if query and query.strip():
            needle = f"%{query.strip().lower()}%"
            clauses.append(or_(func.lower(ContentItem.title).like(needle), func.lower(ContentItem.chapter).like(needle)))
        total = (await db.execute(select(func.count(ContentItem.id)).where(*clauses))).scalar() or 0
        rows = (
            await db.execute(
                select(ContentItem, Subject, SchoolClass)
                .join(Subject, Subject.id == ContentItem.subject_id)
                .join(SchoolClass, SchoolClass.id == ContentItem.class_id)
                .where(*clauses)
                .order_by(ContentItem.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        tags = await TeacherService._content_tags(db, [item.id for item, _s, _c in rows])
        return TeacherContentPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[
                TeacherService._content_row(item, subject, school_class, tags.get(item.id, []))
                for item, subject, school_class in rows
            ],
        )

    @staticmethod
    async def _content_tags(db: AsyncSession, content_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        if not content_ids:
            return {}
        rows = (
            await db.execute(select(ContentTag).where(ContentTag.content_id.in_(content_ids)))
        ).scalars().all()
        tags: dict[uuid.UUID, list[str]] = {}
        for tag in rows:
            tags.setdefault(tag.content_id, []).append(tag.tag)
        return tags

    @staticmethod
    def _content_row(item: ContentItem, subject: Subject, school_class: SchoolClass, tags: list[str]) -> TeacherContentRow:
        return TeacherContentRow(
            id=item.id,
            title=item.title,
            description=item.description,
            subject_id=item.subject_id,
            subject_code=subject.code,
            subject_name=subject.name,
            class_id=item.class_id,
            class_name=school_class.name,
            content_type=_value(item.content_type) or "PDF",
            file_key=item.file_key,
            external_url=item.external_url,
            file_size_bytes=item.file_size_bytes,
            duration_seconds=item.duration_seconds,
            chapter=item.chapter,
            tags=tags,
            is_visible=item.is_visible,
            download_count=item.download_count,
            view_count=item.view_count,
            created_at=item.created_at,
        )

    @staticmethod
    async def create_content(db: AsyncSession, teacher: User, payload: TeacherContentIn) -> TeacherContentRow:
        scope = await TeacherService.scope_for_user(db, teacher)
        TeacherService._ensure_teaches(scope, payload.subject_id, payload.class_id)
        if not payload.file_key and not payload.external_url:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide a file_key or an external_url")
        item = ContentItem(
            id=uuid.uuid4(),
            tenant_id=teacher.tenant_id,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else None,
            subject_id=payload.subject_id,
            class_id=payload.class_id,
            uploaded_by=teacher.id,
            content_type=ContentKind(payload.content_type),
            file_key=payload.file_key,
            external_url=payload.external_url,
            file_size_bytes=payload.file_size_bytes,
            duration_seconds=payload.duration_seconds,
            chapter=payload.chapter.strip() if payload.chapter else None,
            is_visible=payload.is_visible,
        )
        db.add(item)
        await db.flush()
        await TeacherService._replace_content_tags(db, item.id, payload.tags)
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="UPLOAD_CONTENT",
            entity="ContentItem",
            entity_id=item.id,
            tenant_id=teacher.tenant_id,
            new_value={"title": item.title, "type": payload.content_type},
        )
        return await TeacherService.content_detail(db, teacher, item.id)

    @staticmethod
    async def _replace_content_tags(db: AsyncSession, content_id: uuid.UUID, tags: list[str]) -> list[str]:
        await db.execute(delete(ContentTag).where(ContentTag.content_id == content_id))
        cleaned = []
        for raw in tags or []:
            tag = raw.strip().lower()[:50]
            if tag and tag not in cleaned:
                cleaned.append(tag)
        for tag in cleaned:
            db.add(ContentTag(id=uuid.uuid4(), content_id=content_id, tag=tag))
        await db.flush()
        return cleaned

    @staticmethod
    async def content_detail(db: AsyncSession, teacher: User, content_id: uuid.UUID) -> TeacherContentRow:
        row = (
            await db.execute(
                select(ContentItem, Subject, SchoolClass)
                .join(Subject, Subject.id == ContentItem.subject_id)
                .join(SchoolClass, SchoolClass.id == ContentItem.class_id)
                .where(
                    ContentItem.id == content_id,
                    ContentItem.tenant_id == teacher.tenant_id,
                    ContentItem.deleted_at.is_(None),
                )
            )
        ).first()
        if row is None or row[0].uploaded_by != teacher.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Content not found")
        tags = await TeacherService._content_tags(db, [row[0].id])
        return TeacherService._content_row(row[0], row[1], row[2], tags.get(row[0].id, []))

    @staticmethod
    async def update_content(
        db: AsyncSession, teacher: User, content_id: uuid.UUID, payload: TeacherContentUpdate
    ) -> TeacherContentRow:
        detail = await TeacherService.content_detail(db, teacher, content_id)
        item = (
            await db.execute(
                select(ContentItem).where(ContentItem.id == content_id, ContentItem.tenant_id == teacher.tenant_id)
            )
        ).scalar_one()
        updates = payload.model_dump(exclude_unset=True, exclude={"tags"})
        if "title" in updates and updates["title"] is not None:
            updates["title"] = updates["title"].strip()
        if "content_type" in updates and updates["content_type"] is not None:
            updates["content_type"] = ContentKind(updates["content_type"])
        for key, value in updates.items():
            setattr(item, key, value)
        if payload.tags is not None:
            await TeacherService._replace_content_tags(db, item.id, payload.tags)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="UPDATE_CONTENT",
            entity="ContentItem",
            entity_id=item.id,
            tenant_id=teacher.tenant_id,
            new_value={key: str(value) for key, value in updates.items()},
        )
        del detail
        return await TeacherService.content_detail(db, teacher, item.id)

    @staticmethod
    async def delete_content(db: AsyncSession, teacher: User, content_id: uuid.UUID) -> None:
        item = (
            await db.execute(
                select(ContentItem)
                .where(
                    ContentItem.id == content_id,
                    ContentItem.tenant_id == teacher.tenant_id,
                    ContentItem.deleted_at.is_(None),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if item is None or item.uploaded_by != teacher.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Content not found")
        item.deleted_at = datetime.now(timezone.utc)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="DELETE_CONTENT",
            entity="ContentItem",
            entity_id=item.id,
            tenant_id=teacher.tenant_id,
            old_value={"title": item.title},
        )

    # ── C-TC-19 / C-TC-20 notices ───────────────────────────────────────────

    @staticmethod
    async def _notice_rows(
        db: AsyncSession,
        teacher: User,
        scope: TeacherScope,
        *,
        query: str | None = None,
        notice_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TeacherNoticePage:
        now = datetime.now(timezone.utc)
        visible = or_(
            and_(Notice.target_scope == NoticeScope.INSTITUTION),
            and_(Notice.target_scope == NoticeScope.DEPARTMENT, Notice.target_id.in_(scope.department_ids)),
            and_(Notice.target_scope == NoticeScope.CLASS, Notice.target_id.in_(scope.class_ids)),
        )
        clauses = [
            Notice.tenant_id == teacher.tenant_id,
            Notice.deleted_at.is_(None),
            or_(Notice.expires_at.is_(None), Notice.expires_at > now),
            visible,
        ]
        if query and query.strip():
            needle = f"%{query.strip().lower()}%"
            clauses.append(or_(func.lower(Notice.title).like(needle), func.lower(Notice.body).like(needle)))
        if notice_id is not None:
            clauses.append(Notice.id == notice_id)
        total = (await db.execute(select(func.count(Notice.id)).where(*clauses))).scalar() or 0
        rows = (
            await db.execute(
                select(Notice, User.name)
                .outerjoin(User, and_(User.id == Notice.author_id, User.tenant_id == teacher.tenant_id))
                .where(*clauses)
                .order_by(Notice.is_pinned.desc(), Notice.published_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        target_names = await TeacherService._notice_target_names(db, teacher.tenant_id, [notice for notice, _n in rows])
        items = []
        for notice, author_name in rows:
            scope_value = _value(notice.target_scope) or "INSTITUTION"
            items.append(
                TeacherNoticeRow(
                    id=notice.id,
                    title=notice.title,
                    body=notice.body,
                    author_name=author_name,
                    target_scope=scope_value,
                    target_id=notice.target_id,
                    target_name=target_names.get((scope_value, notice.target_id)),
                    priority=_value(notice.priority) or "NORMAL",
                    is_pinned=notice.is_pinned,
                    published_at=notice.published_at,
                    expires_at=notice.expires_at,
                    mine=notice.author_id == teacher.id,
                )
            )
        return TeacherNoticePage(total=int(total), limit=limit, offset=offset, items=items)

    @staticmethod
    async def _notice_target_names(
        db: AsyncSession, tenant_id: uuid.UUID, notices: list[Notice]
    ) -> dict[tuple[str, uuid.UUID | None], str | None]:
        names: dict[tuple[str, uuid.UUID | None], str | None] = {("INSTITUTION", None): "Institution-wide"}
        department_ids = {
            notice.target_id
            for notice in notices
            if _value(notice.target_scope) == "DEPARTMENT" and notice.target_id is not None
        }
        class_ids = {
            notice.target_id
            for notice in notices
            if _value(notice.target_scope) == "CLASS" and notice.target_id is not None
        }
        if department_ids:
            rows = await db.execute(
                select(Department.id, Department.name).where(
                    Department.tenant_id == tenant_id, Department.id.in_(department_ids)
                )
            )
            names.update({("DEPARTMENT", row[0]): row[1] for row in rows.all()})
        if class_ids:
            rows = await db.execute(
                select(SchoolClass.id, SchoolClass.name).where(
                    SchoolClass.tenant_id == tenant_id, SchoolClass.id.in_(class_ids)
                )
            )
            names.update({("CLASS", row[0]): row[1] for row in rows.all()})
        return names

    @staticmethod
    async def notices(
        db: AsyncSession,
        teacher: User,
        *,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TeacherNoticePage:
        TeacherService._validate_page(limit, offset)
        scope = await TeacherService.scope_for_user(db, teacher)
        return await TeacherService._notice_rows(db, teacher, scope, query=query, limit=limit, offset=offset)

    @staticmethod
    async def notice_detail(db: AsyncSession, teacher: User, notice_id: uuid.UUID) -> TeacherNoticeRow:
        scope = await TeacherService.scope_for_user(db, teacher)
        page = await TeacherService._notice_rows(db, teacher, scope, notice_id=notice_id, limit=1, offset=0)
        if not page.items:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Notice not found")
        notice = page.items[0]
        notice.attachments = await PrincipalService._notice_attachments(db, notice_id)
        return notice

    @staticmethod
    async def notice_targets(db: AsyncSession, teacher: User) -> list[TeacherTargetOption]:
        scope = await TeacherService.scope_for_user(db, teacher)
        class_ids = sorted(scope.class_ids)
        if not class_ids:
            return []
        rows = (
            await db.execute(
                select(SchoolClass.id, SchoolClass.name).where(
                    SchoolClass.tenant_id == teacher.tenant_id, SchoolClass.id.in_(class_ids)
                ).order_by(SchoolClass.name)
            )
        ).all()
        return [TeacherTargetOption(id=row[0], name=row[1]) for row in rows]

    @staticmethod
    async def create_notice(db: AsyncSession, teacher: User, payload: TeacherNoticeCreate) -> TeacherNoticeRow:
        scope = await TeacherService.scope_for_user(db, teacher)
        TeacherService._ensure_class_scope(scope, payload.class_id)
        title = payload.title.strip()
        body = payload.body.strip()
        if payload.expires_at and payload.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="expires_at must be in the future")
        notice = Notice(
            id=uuid.uuid4(),
            tenant_id=teacher.tenant_id,
            title=title,
            body=body,
            author_id=teacher.id,
            target_scope=NoticeScope.CLASS,
            target_id=payload.class_id,
            priority=NoticePriority(payload.priority),
            is_pinned=False,
            published_at=datetime.now(timezone.utc),
            expires_at=payload.expires_at,
        )
        db.add(notice)
        await db.flush()
        await PrincipalService._save_notice_attachments(db, notice.tenant_id, notice.id, payload.attachments)
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="CREATE_NOTICE",
            entity="Notice",
            entity_id=notice.id,
            tenant_id=teacher.tenant_id,
            new_value={"title": title, "target_scope": "CLASS", "target_id": str(payload.class_id)},
        )
        return await TeacherService.notice_detail(db, teacher, notice.id)

    # ── C-TC-21 / C-TC-22 discussion ────────────────────────────────────────

    @staticmethod
    def _thread_visibility(scope: TeacherScope):
        return or_(
            and_(func.upper(DiscussionThread.scope_type) == "CLASS", DiscussionThread.scope_id.in_(scope.class_ids)),
            and_(func.upper(DiscussionThread.scope_type) == "SUBJECT", DiscussionThread.scope_id.in_(scope.subject_ids)),
            and_(
                func.upper(DiscussionThread.scope_type) == "DEPARTMENT",
                DiscussionThread.scope_id.in_(scope.department_ids),
            ),
        )

    @staticmethod
    def _can_moderate(scope: TeacherScope, thread: DiscussionThread, teacher: User) -> bool:
        if thread.author_id == teacher.id:
            return True
        return (
            (thread.scope_type or "").upper() == "SUBJECT" and thread.scope_id in scope.subject_ids
        )

    @staticmethod
    async def discussion(
        db: AsyncSession,
        teacher: User,
        *,
        query: str | None = None,
        scope_type: str | None = None,
        scope_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TeacherThreadPage:
        TeacherService._validate_page(limit, offset)
        scope = await TeacherService.scope_for_user(db, teacher)
        clauses = [
            DiscussionThread.tenant_id == teacher.tenant_id,
            DiscussionThread.deleted_at.is_(None),
            TeacherService._thread_visibility(scope),
        ]
        if scope_type:
            clauses.append(func.upper(DiscussionThread.scope_type) == scope_type.strip().upper())
        if scope_id is not None:
            clauses.append(DiscussionThread.scope_id == scope_id)
        if query and query.strip():
            needle = f"%{query.strip().lower()}%"
            clauses.append(
                or_(func.lower(DiscussionThread.title).like(needle), func.lower(DiscussionThread.body).like(needle))
            )
        total = (
            await db.execute(select(func.count(DiscussionThread.id)).where(*clauses))
        ).scalar() or 0
        rows = (
            await db.execute(
                select(DiscussionThread, User.name)
                .outerjoin(User, and_(User.id == DiscussionThread.author_id, User.tenant_id == teacher.tenant_id))
                .where(*clauses)
                .order_by(DiscussionThread.is_pinned.desc(), DiscussionThread.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        names = await TeacherService._thread_scope_names(db, teacher.tenant_id, [thread for thread, _n in rows])
        return TeacherThreadPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[
                TeacherService._thread_row(thread, author_name, teacher, scope, names)
                for thread, author_name in rows
            ],
        )

    @staticmethod
    async def _thread_scope_names(
        db: AsyncSession, tenant_id: uuid.UUID, threads: list[DiscussionThread]
    ) -> dict[tuple[str, uuid.UUID], str | None]:
        names: dict[tuple[str, uuid.UUID], str | None] = {}
        class_ids = {t.scope_id for t in threads if (t.scope_type or "").upper() == "CLASS"}
        subject_ids = {t.scope_id for t in threads if (t.scope_type or "").upper() == "SUBJECT"}
        department_ids = {t.scope_id for t in threads if (t.scope_type or "").upper() == "DEPARTMENT"}
        if class_ids:
            rows = await db.execute(
                select(SchoolClass.id, SchoolClass.name).where(
                    SchoolClass.tenant_id == tenant_id, SchoolClass.id.in_(class_ids)
                )
            )
            names.update({("CLASS", row[0]): row[1] for row in rows.all()})
        if subject_ids:
            rows = await db.execute(
                select(Subject.id, Subject.code, Subject.name).where(
                    Subject.tenant_id == tenant_id, Subject.id.in_(subject_ids)
                )
            )
            names.update({("SUBJECT", row[0]): f"{row[1]} · {row[2]}" for row in rows.all()})
        if department_ids:
            rows = await db.execute(
                select(Department.id, Department.name).where(
                    Department.tenant_id == tenant_id, Department.id.in_(department_ids)
                )
            )
            names.update({("DEPARTMENT", row[0]): row[1] for row in rows.all()})
        return names

    @staticmethod
    def _thread_row(
        thread: DiscussionThread,
        author_name: str | None,
        teacher: User,
        scope: TeacherScope,
        names: dict[tuple[str, uuid.UUID], str | None],
    ) -> TeacherThreadRow:
        scope_type = (thread.scope_type or "").upper()
        return TeacherThreadRow(
            id=thread.id,
            title=thread.title,
            body=thread.body,
            author_id=thread.author_id,
            author_name=author_name,
            mine=thread.author_id == teacher.id,
            scope_type=scope_type,
            scope_id=thread.scope_id,
            scope_name=names.get((scope_type, thread.scope_id)),
            tags=list(thread.tags or []),
            is_pinned=thread.is_pinned,
            is_locked=thread.is_locked,
            is_resolved=thread.is_resolved,
            reply_count=thread.reply_count,
            upvote_count=thread.upvote_count,
            view_count=thread.view_count,
            can_moderate=TeacherService._can_moderate(scope, thread, teacher),
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )

    @staticmethod
    def _validate_thread_scope(scope: TeacherScope, scope_type: str, scope_id: uuid.UUID) -> None:
        if scope_type == "CLASS" and scope_id in scope.class_ids:
            return
        if scope_type == "SUBJECT" and scope_id in scope.subject_ids:
            return
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="This discussion scope is outside your classes")

    @staticmethod
    async def create_thread(db: AsyncSession, teacher: User, payload: TeacherThreadCreate) -> TeacherThreadDetail:
        scope = await TeacherService.scope_for_user(db, teacher)
        TeacherService._validate_thread_scope(scope, payload.scope_type, payload.scope_id)
        thread = DiscussionThread(
            id=uuid.uuid4(),
            tenant_id=teacher.tenant_id,
            title=payload.title.strip(),
            body=payload.body.strip(),
            author_id=teacher.id,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            tags=[tag.strip().lower() for tag in payload.tags if tag.strip()][:5] or None,
            reply_count=0,
            upvote_count=0,
            view_count=0,
        )
        db.add(thread)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="CREATE_DISCUSSION_THREAD",
            entity="DiscussionThread",
            entity_id=thread.id,
            tenant_id=teacher.tenant_id,
            new_value={"title": thread.title, "scope_type": payload.scope_type},
        )
        return await TeacherService.discussion_detail(db, teacher, thread.id)

    @staticmethod
    async def _visible_thread(db: AsyncSession, teacher: User, scope: TeacherScope, thread_id: uuid.UUID) -> DiscussionThread:
        thread = (
            await db.execute(
                select(DiscussionThread).where(
                    DiscussionThread.id == thread_id,
                    DiscussionThread.tenant_id == teacher.tenant_id,
                    DiscussionThread.deleted_at.is_(None),
                    TeacherService._thread_visibility(scope),
                )
            )
        ).scalar_one_or_none()
        if thread is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Discussion thread not found")
        return thread

    @staticmethod
    async def discussion_detail(db: AsyncSession, teacher: User, thread_id: uuid.UUID) -> TeacherThreadDetail:
        scope = await TeacherService.scope_for_user(db, teacher)
        thread = await TeacherService._visible_thread(db, teacher, scope, thread_id)
        author_name = (
            await db.execute(
                select(User.name).where(User.id == thread.author_id, User.tenant_id == teacher.tenant_id)
            )
        ).scalar_one_or_none()
        names = await TeacherService._thread_scope_names(db, teacher.tenant_id, [thread])
        reply_rows = (
            await db.execute(
                select(DiscussionReply, User.name)
                .outerjoin(User, and_(User.id == DiscussionReply.author_id, User.tenant_id == teacher.tenant_id))
                .where(
                    DiscussionReply.thread_id == thread.id,
                    DiscussionReply.tenant_id == teacher.tenant_id,
                    DiscussionReply.deleted_at.is_(None),
                )
                .order_by(DiscussionReply.is_accepted_answer.desc(), DiscussionReply.created_at)
            )
        ).all()
        return TeacherThreadDetail(
            **TeacherService._thread_row(thread, author_name, teacher, scope, names).model_dump(),
            replies=[
                TeacherReplyRow(
                    id=reply.id,
                    author_id=reply.author_id,
                    author_name=name,
                    mine=reply.author_id == teacher.id,
                    body=reply.body,
                    is_accepted_answer=reply.is_accepted_answer,
                    upvote_count=reply.upvote_count,
                    created_at=reply.created_at,
                )
                for reply, name in reply_rows
            ],
        )

    @staticmethod
    async def reply_thread(
        db: AsyncSession, teacher: User, thread_id: uuid.UUID, payload: TeacherReplyCreate
    ) -> TeacherReplyRow:
        scope = await TeacherService.scope_for_user(db, teacher)
        thread = (
            await db.execute(
                select(DiscussionThread)
                .where(
                    DiscussionThread.id == thread_id,
                    DiscussionThread.tenant_id == teacher.tenant_id,
                    DiscussionThread.deleted_at.is_(None),
                    TeacherService._thread_visibility(scope),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if thread is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Discussion thread not found")
        if thread.is_locked:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This thread is locked")
        reply = DiscussionReply(
            id=uuid.uuid4(),
            tenant_id=teacher.tenant_id,
            thread_id=thread.id,
            author_id=teacher.id,
            body=payload.body.strip(),
        )
        db.add(reply)
        thread.reply_count = (thread.reply_count or 0) + 1
        await db.flush()
        return TeacherReplyRow(
            id=reply.id,
            author_id=teacher.id,
            author_name=teacher.name,
            mine=True,
            body=reply.body,
            is_accepted_answer=False,
            upvote_count=0,
            created_at=reply.created_at,
        )

    @staticmethod
    async def moderate_thread(
        db: AsyncSession, teacher: User, thread_id: uuid.UUID, payload: TeacherThreadModeration
    ) -> TeacherThreadDetail:
        scope = await TeacherService.scope_for_user(db, teacher)
        thread = (
            await db.execute(
                select(DiscussionThread)
                .where(
                    DiscussionThread.id == thread_id,
                    DiscussionThread.tenant_id == teacher.tenant_id,
                    DiscussionThread.deleted_at.is_(None),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if thread is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Discussion thread not found")
        if not TeacherService._can_moderate(scope, thread, teacher):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You can only moderate threads in your own subjects")
        before = {"is_pinned": thread.is_pinned, "is_locked": thread.is_locked}
        if payload.action == "PIN":
            thread.is_pinned = True
        elif payload.action == "UNPIN":
            thread.is_pinned = False
        elif payload.action == "LOCK":
            thread.is_locked = True
        elif payload.action == "UNLOCK":
            thread.is_locked = False
        else:
            thread.deleted_at = datetime.now(timezone.utc)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action=f"MODERATE_DISCUSSION_{payload.action}",
            entity="DiscussionThread",
            entity_id=thread.id,
            tenant_id=teacher.tenant_id,
            old_value=before,
            new_value={
                "is_pinned": thread.is_pinned,
                "is_locked": thread.is_locked,
                "deleted": thread.deleted_at is not None,
            },
        )
        if thread.deleted_at is not None:
            return TeacherThreadDetail(
                **TeacherService._thread_row(thread, None, teacher, scope, {}).model_dump(), replies=[]
            )
        return await TeacherService.discussion_detail(db, teacher, thread_id)

    @staticmethod
    async def accept_reply(db: AsyncSession, teacher: User, reply_id: uuid.UUID) -> TeacherThreadDetail:
        scope = await TeacherService.scope_for_user(db, teacher)
        reply = (
            await db.execute(
                select(DiscussionReply)
                .where(
                    DiscussionReply.id == reply_id,
                    DiscussionReply.tenant_id == teacher.tenant_id,
                    DiscussionReply.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if reply is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Reply not found")
        thread = (
            await db.execute(
                select(DiscussionThread)
                .where(DiscussionThread.id == reply.thread_id, DiscussionThread.tenant_id == teacher.tenant_id)
                .with_for_update()
            )
        ).scalar_one()
        # Same rule the thread page advertises via can_moderate: the author of
        # an in-scope thread or any teacher of the owning subject may accept.
        if not TeacherService._can_moderate(scope, thread, teacher):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You can accept answers only in your own subjects")
        await db.execute(
            update(DiscussionReply)
            .where(DiscussionReply.thread_id == thread.id, DiscussionReply.id != reply.id)
            .values(is_accepted_answer=False)
        )
        reply.is_accepted_answer = True
        thread.is_resolved = True
        thread.resolved_by = teacher.id
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="ACCEPT_DISCUSSION_ANSWER",
            entity="DiscussionReply",
            entity_id=reply.id,
            tenant_id=teacher.tenant_id,
            new_value={"thread_id": str(thread.id)},
        )
        return await TeacherService.discussion_detail(db, teacher, thread.id)
