"""Student console workflows (C-ST-01 … C-ST-20).

The caller *is* the scope: every query filters by the signed-in student's own
id and their active enrollment in the current academic year.  No route accepts
a student id, so one student can never read another student's row by swapping
an identifier in the URL.

Sensitive data boundaries enforced here:

* exam questions ship **without** correct answers until results are released;
* results/grade cards only appear once the publication is visible and
  approved (or the teacher released the exam, per-exam review flags allowing);
* content hides ``is_visible = FALSE`` uploads and soft-deleted rows.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic import AcademicYear, Department, SchoolClass, Subject
from app.models.enrollment import Enrollment
from app.models.exam_controller import (
    ExamControllerGradeCard,
    ExamControllerGradeCardStatus,
)
from app.models.hod import Assignment, AssignmentStatus, AttendanceRecord, DiscussionThread, Submission, \
    SubmissionStatus
from app.models.lms import (
    Answer,
    AttendanceLeave,
    ContentAccessLog,
    ContentItem,
    ContentKind,
    ContentTag,
    DiscussionReply,
    DiscussionVote,
    FeeInstallment,
    FeePayment,
    LeaveStatus,
    Milestone,
    ProjectGroup,
    ProjectGroupInvitation,
    ProjectGroupMember,
    ProjectGroupMessage,
    ProjectGroupResource,
    ProjectGroupTask,
    Question,
    QuestionOption,
    QuestionType,
    Scholarship,
    ScholarshipGrant,
    StudentFeeAccount,
    SubmissionFile,
)
from app.models.principal import (
    AttendanceSession,
    AttendanceStatus,
    Exam,
    ExamAttempt,
    ExamStatus,
    AttemptStatus,
    Notice,
    NoticeRead,
    NoticeScope,
    ResultPublication,
    StudentResult,
    TimetableSlot,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.student import (
    StudentAnswerSave,
    StudentAssignmentDetail,
    StudentAssignmentPage,
    StudentAssignmentRow,
    StudentAttemptOption,
    StudentAttemptPaper,
    StudentAttemptQuestion,
    StudentAttemptState,
    StudentAttendanceCalendar,
    StudentAttendanceDay,
    StudentAttendanceEntry,
    StudentAttendanceSummary,
    StudentClassInfo,
    StudentContentPage,
    StudentContentRow,
    StudentDashboard,
    StudentDiscussionScope,
    StudentEligibleClassmateOut,
    StudentExamDetail,
    StudentExamPage,
    StudentExamResult,
    StudentExamRow,
    StudentFeeAccount as StudentFeeAccountOut,
    StudentFeeInstallment,
    StudentFeePayment,
    StudentGroupCreate,
    StudentGroupInviteIn,
    StudentGroupInviteOut,
    StudentGroupInviteResponseIn,
    StudentGroupListOut,
    StudentGroupMember,
    StudentGroupMessageIn,
    StudentGroupMessageOut,
    StudentGroupResourceIn,
    StudentGroupResourceOut,
    StudentGroupReuseIn,
    StudentGroupRow,
    StudentGroupTaskIn,
    StudentGroupTaskOut,
    StudentGroupTaskUpdateIn,
    StudentLeaveCreate,
    StudentLeavePage,
    StudentLeaveRow,
    StudentMilestoneProgress,
    StudentMyTeamDetail,
    StudentMyTeamSummary,
    StudentNextExam,
    StudentNoticePage,
    StudentNoticeRow,
    StudentPendingAssignment,
    StudentPreviousGroupOption,
    StudentProfile,
    StudentProfileUpdate,
    StudentReplyCreate,
    StudentReplyRow,
    StudentResultAnswer,
    StudentResultDetail,
    StudentResultRow,
    StudentScholarshipGrant,
    StudentSubjectAttendance,
    StudentSubjectScore,
    StudentSubmissionCreate,
    StudentSubmissionFileOut,
    StudentSubmissionOut,
    StudentThreadCreate,
    StudentThreadDetail,
    StudentThreadPage,
    StudentThreadRow,
    StudentTabSwitch,
    StudentTimetable,
    StudentTimetableSlot,
    StudentVoteToggle,
)
from app.services.audit_service import AuditService
from app.services.principal_service import PrincipalService, _value
from app.services.push_service import PushService
from app.services.teacher_service import grade_for


_OBJECTIVE_QUESTION_TYPES = (QuestionType.MCQ, QuestionType.TRUE_FALSE)
_AUTO_SUBMIT_GRACE = timedelta(minutes=5)


@dataclass(frozen=True)
class StudentContext:
    """The fence every student query is filtered through."""

    enrollment: Enrollment
    school_class: SchoolClass
    department: Department | None
    academic_year: AcademicYear

    @property
    def class_info(self) -> StudentClassInfo:
        return StudentClassInfo(
            class_id=self.school_class.id,
            class_name=self.school_class.name,
            department_id=self.department.id if self.department else None,
            department_name=self.department.name if self.department else None,
            academic_year_id=self.academic_year.id,
            academic_year=self.academic_year.name,
            roll_number=self.enrollment.roll_number,
        )


logger = logging.getLogger(__name__)


class StudentService:
    # ── Scope ───────────────────────────────────────────────────────────────

    @staticmethod
    async def context_for_user(db: AsyncSession, student: User) -> StudentContext:
        row = (
            await db.execute(
                select(Enrollment, SchoolClass, Department, AcademicYear)
                .join(
                    SchoolClass,
                    and_(SchoolClass.id == Enrollment.class_id, SchoolClass.tenant_id == student.tenant_id),
                )
                .outerjoin(
                    Department,
                    and_(Department.id == SchoolClass.department_id, Department.tenant_id == student.tenant_id),
                )
                .join(
                    AcademicYear,
                    and_(
                        AcademicYear.id == Enrollment.academic_year_id,
                        AcademicYear.tenant_id == student.tenant_id,
                        AcademicYear.is_current.is_(True),
                    ),
                )
                .where(
                    Enrollment.tenant_id == student.tenant_id,
                    Enrollment.student_id == student.id,
                )
                .order_by(Enrollment.created_at.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="No active enrollment found for the current academic year. Contact your institution admin.",
            )
        enrollment, school_class, department, academic_year = row
        if (_value(enrollment.status) or "ACTIVE") != "ACTIVE":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Your enrollment is no longer active. Contact your institution admin.",
            )
        return StudentContext(enrollment, school_class, department, academic_year)

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        if not 1 <= limit <= 100 or offset < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid pagination")

    # ── C-ST-01 dashboard ───────────────────────────────────────────────────

    @staticmethod
    async def dashboard(db: AsyncSession, student: User) -> StudentDashboard:
        ctx = await StudentService.context_for_user(db, student)
        tenant_id = student.tenant_id
        today = await PrincipalService._tenant_today(db, tenant_id)
        now = datetime.now(timezone.utc)

        marks = (
            await db.execute(
                select(
                    func.count(AttendanceRecord.id),
                    func.coalesce(
                        func.sum(case((AttendanceRecord.status != AttendanceStatus.ABSENT, 1), else_=0)), 0
                    ),
                )
                .where(AttendanceRecord.tenant_id == tenant_id, AttendanceRecord.student_id == student.id)
            )
        ).one()
        total_marks = int(marks[0] or 0)
        percentage = round(int(marks[1] or 0) * 100 / total_marks, 2) if total_marks else None

        next_exam_row = (
            await db.execute(
                select(Exam, Subject)
                .join(Subject, Subject.id == Exam.subject_id)
                .where(
                    Exam.tenant_id == tenant_id,
                    Exam.class_id == ctx.school_class.id,
                    Exam.scheduled_at >= now,
                    Exam.status.in_((ExamStatus.PUBLISHED, ExamStatus.ONGOING)),
                )
                .order_by(Exam.scheduled_at)
                .limit(1)
            )
        ).first()
        upcoming_exam_count = (
            await db.execute(
                select(func.count(Exam.id)).where(
                    Exam.tenant_id == tenant_id,
                    Exam.class_id == ctx.school_class.id,
                    Exam.scheduled_at >= now,
                    Exam.status.in_((ExamStatus.PUBLISHED, ExamStatus.ONGOING)),
                )
            )
        ).scalar() or 0

        pending_assignments = await StudentService._pending_assignments(db, student, ctx, limit=5)
        pending_count = await StudentService._pending_assignment_count(db, student, ctx)

        today_slots = await StudentService._timetable_slots(
            db, tenant_id, ctx, day=today, for_day_only=True
        )
        notices = await StudentService._notice_page(db, student, ctx, limit=5, offset=0)

        fee_balance = (
            await db.execute(
                select(StudentFeeAccount.balance_due).where(
                    StudentFeeAccount.tenant_id == tenant_id,
                    StudentFeeAccount.student_id == student.id,
                    StudentFeeAccount.academic_year_id == ctx.academic_year.id,
                )
            )
        ).scalar_one_or_none()

        return StudentDashboard(
            student_name=student.name,
            class_info=ctx.class_info,
            attendance_percentage=percentage,
            attendance_marks=total_marks,
            next_exam=(
                StudentNextExam(
                    id=next_exam_row[0].id,
                    title=next_exam_row[0].title,
                    subject_name=next_exam_row[1].name,
                    subject_code=next_exam_row[1].code,
                    scheduled_at=next_exam_row[0].scheduled_at,
                    total_marks=next_exam_row[0].total_marks,
                    duration_minutes=next_exam_row[0].duration_minutes,
                    status=_value(next_exam_row[0].status) or "PUBLISHED",
                )
                if next_exam_row
                else None
            ),
            upcoming_exam_count=int(upcoming_exam_count),
            pending_assignment_count=pending_count,
            pending_assignments=pending_assignments,
            today_periods=today_slots,
            recent_notices=notices.items,
            fee_balance_due=float(fee_balance) if fee_balance is not None else None,
        )

    @staticmethod
    async def _pending_assignments(
        db: AsyncSession, student: User, ctx: StudentContext, *, limit: int
    ) -> list[StudentPendingAssignment]:
        submitted = select(Submission.assignment_id).where(
            Submission.tenant_id == student.tenant_id,
            Submission.student_id == student.id,
            Submission.status.in_((SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW, SubmissionStatus.APPROVED)),
        )
        rows = (
            await db.execute(
                select(Assignment, Subject)
                .join(Subject, Subject.id == Assignment.subject_id)
                .where(
                    Assignment.tenant_id == student.tenant_id,
                    Assignment.class_id == ctx.school_class.id,
                    Assignment.status == AssignmentStatus.PUBLISHED,
                    Assignment.id.notin_(submitted),
                )
                .order_by(Assignment.due_date)
                .limit(limit)
            )
        ).all()
        return [
            StudentPendingAssignment(
                id=assignment.id,
                title=assignment.title,
                subject_name=subject.name,
                due_date=assignment.due_date,
                total_marks=assignment.total_marks,
            )
            for assignment, subject in rows
        ]

    @staticmethod
    async def _pending_assignment_count(db: AsyncSession, student: User, ctx: StudentContext) -> int:
        submitted = select(Submission.assignment_id).where(
            Submission.tenant_id == student.tenant_id,
            Submission.student_id == student.id,
            Submission.status.in_((SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW, SubmissionStatus.APPROVED)),
        )
        return int(
            (
                await db.execute(
                    select(func.count(Assignment.id)).where(
                        Assignment.tenant_id == student.tenant_id,
                        Assignment.class_id == ctx.school_class.id,
                        Assignment.status == AssignmentStatus.PUBLISHED,
                        Assignment.id.notin_(submitted),
                    )
                )
            ).scalar()
            or 0
        )

    # ── C-ST-02 profile ─────────────────────────────────────────────────────

    @staticmethod
    async def profile(db: AsyncSession, student: User) -> StudentProfile:
        ctx = await StudentService.context_for_user(db, student)
        class_teacher = None
        if ctx.school_class.class_teacher_id:
            class_teacher = (
                await db.execute(
                    select(User.name).where(
                        User.id == ctx.school_class.class_teacher_id, User.tenant_id == student.tenant_id
                    )
                )
            ).scalar_one_or_none()
        return StudentProfile(
            id=student.id,
            name=student.name,
            email=student.email,
            phone=student.phone,
            avatar_url=student.avatar_url,
            date_of_birth=student.date_of_birth,
            gender=_value(student.gender),
            student_roll_no=student.student_roll_no,
            class_info=ctx.class_info,
            class_teacher_name=class_teacher,
        )

    @staticmethod
    async def update_profile(db: AsyncSession, student: User, payload: StudentProfileUpdate) -> StudentProfile:
        """C-RB-04: a student may edit their own name, phone and avatar only."""
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return await StudentService.profile(db, student)
        before: dict = {}
        if "name" in updates and updates["name"] is not None:
            name = updates["name"].strip()
            if not name:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name cannot be blank")
            before["name"] = student.name
            student.name = name
        if "phone" in updates:
            before["phone"] = student.phone
            student.phone = updates["phone"].strip() if updates["phone"] else None
        if "avatar_url" in updates:
            before["avatar_url"] = student.avatar_url
            student.avatar_url = updates["avatar_url"]
        await db.flush()
        AuditService.record(
            db,
            actor=student,
            actor_role="STUDENT",
            action="UPDATE_PROFILE",
            entity="User",
            entity_id=student.id,
            tenant_id=student.tenant_id,
            old_value=before,
            new_value={key: str(value) for key, value in updates.items()},
        )
        return await StudentService.profile(db, student)

    # ── C-ST-03 / C-ST-04 attendance ────────────────────────────────────────

    @staticmethod
    async def attendance(db: AsyncSession, student: User) -> StudentAttendanceSummary:
        await StudentService.context_for_user(db, student)
        rows = (
            await db.execute(
                select(
                    Subject.id,
                    Subject.code,
                    Subject.name,
                    func.coalesce(func.sum(case((AttendanceRecord.status == AttendanceStatus.PRESENT, 1), else_=0)), 0),
                    func.coalesce(func.sum(case((AttendanceRecord.status == AttendanceStatus.ABSENT, 1), else_=0)), 0),
                    func.coalesce(func.sum(case((AttendanceRecord.status == AttendanceStatus.LATE, 1), else_=0)), 0),
                    func.coalesce(func.sum(case((AttendanceRecord.status == AttendanceStatus.EXCUSED, 1), else_=0)), 0),
                )
                .select_from(AttendanceRecord)
                .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
                .join(Subject, Subject.id == AttendanceSession.subject_id)
                .where(
                    AttendanceRecord.tenant_id == student.tenant_id,
                    AttendanceRecord.student_id == student.id,
                )
                .group_by(Subject.id, Subject.code, Subject.name)
                .order_by(Subject.code)
            )
        ).all()
        subjects = []
        total_present = total_absent = total_late = total_excused = 0
        for subject_id, code, name, present, absent, late, excused in rows:
            present, absent, late, excused = int(present), int(absent), int(late), int(excused)
            total = present + absent + late + excused
            subjects.append(
                StudentSubjectAttendance(
                    subject_id=subject_id,
                    subject_code=code,
                    subject_name=name,
                    present_count=present,
                    absent_count=absent,
                    late_count=late,
                    excused_count=excused,
                    total_marks=total,
                    attendance_percentage=round((present + late + excused) * 100 / total, 2) if total else None,
                )
            )
            total_present += present
            total_absent += absent
            total_late += late
            total_excused += excused
        total_marks = total_present + total_absent + total_late + total_excused
        return StudentAttendanceSummary(
            attendance_percentage=(
                round((total_present + total_late + total_excused) * 100 / total_marks, 2) if total_marks else None
            ),
            total_marks=total_marks,
            present_count=total_present,
            absent_count=total_absent,
            late_count=total_late,
            excused_count=total_excused,
            subjects=subjects,
        )

    @staticmethod
    async def attendance_calendar(db: AsyncSession, student: User, *, month: str) -> StudentAttendanceCalendar:
        try:
            year, month_number = (int(part) for part in month.split("-", 1))
            first = date(year, month_number, 1)
        except (ValueError, TypeError):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="month must be YYYY-MM")
        last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        rows = (
            await db.execute(
                select(AttendanceSession.date, AttendanceSession.period_label, Subject, AttendanceRecord.status)
                .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
                .join(Subject, Subject.id == AttendanceSession.subject_id)
                .where(
                    AttendanceRecord.tenant_id == student.tenant_id,
                    AttendanceRecord.student_id == student.id,
                    AttendanceSession.date >= first,
                    AttendanceSession.date <= last,
                )
                .order_by(AttendanceSession.date, AttendanceSession.period_label)
            )
        ).all()
        by_day: dict[date, list[StudentAttendanceEntry]] = {}
        for day, period_label, subject, record_status in rows:
            by_day.setdefault(day, []).append(
                StudentAttendanceEntry(
                    status=_value(record_status) or "PRESENT",
                    subject_code=subject.code,
                    subject_name=subject.name,
                    period_label=period_label,
                )
            )
        return StudentAttendanceCalendar(
            month=f"{year:04d}-{month_number:02d}",
            days=[StudentAttendanceDay(date=day, entries=entries) for day, entries in sorted(by_day.items())],
        )

    # ── C-ST-05 leave applications ──────────────────────────────────────────

    @staticmethod
    async def leaves(db: AsyncSession, student: User, *, limit: int = 50, offset: int = 0) -> StudentLeavePage:
        StudentService._validate_page(limit, offset)
        await StudentService.context_for_user(db, student)
        clauses = [
            AttendanceLeave.tenant_id == student.tenant_id,
            AttendanceLeave.student_id == student.id,
        ]
        total = (await db.execute(select(func.count(AttendanceLeave.id)).where(*clauses))).scalar() or 0
        rows = (
            await db.execute(
                select(AttendanceLeave).where(*clauses).order_by(AttendanceLeave.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return StudentLeavePage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[StudentService._leave_row(leave) for leave in rows],
        )

    @staticmethod
    def _leave_row(leave: AttendanceLeave) -> StudentLeaveRow:
        return StudentLeaveRow(
            id=leave.id,
            from_date=leave.from_date,
            to_date=leave.to_date,
            reason=leave.reason,
            document_url=leave.document_url,
            status=_value(leave.status) or "PENDING",
            reviewed_at=leave.reviewed_at,
            created_at=leave.created_at,
        )

    @staticmethod
    async def apply_leave(db: AsyncSession, student: User, payload: StudentLeaveCreate) -> StudentLeaveRow:
        ctx = await StudentService.context_for_user(db, student)
        if payload.to_date < payload.from_date:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="to_date must be on or after from_date")
        if (payload.to_date - payload.from_date).days > 30:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Leave cannot exceed 30 days")
        overlap = (
            await db.execute(
                select(AttendanceLeave.id).where(
                    AttendanceLeave.tenant_id == student.tenant_id,
                    AttendanceLeave.student_id == student.id,
                    AttendanceLeave.status.in_((LeaveStatus.PENDING, LeaveStatus.APPROVED)),
                    AttendanceLeave.from_date <= payload.to_date,
                    AttendanceLeave.to_date >= payload.from_date,
                )
            )
        ).scalar_one_or_none()
        if overlap is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="A leave request already covers these dates")
        leave = AttendanceLeave(
            id=uuid.uuid4(),
            tenant_id=student.tenant_id,
            student_id=student.id,
            class_id=ctx.school_class.id,
            from_date=payload.from_date,
            to_date=payload.to_date,
            reason=payload.reason.strip(),
            document_url=payload.document_url,
        )
        db.add(leave)
        await db.flush()
        AuditService.record(
            db,
            actor=student,
            actor_role="STUDENT",
            action="APPLY_LEAVE",
            entity="AttendanceLeave",
            entity_id=leave.id,
            tenant_id=student.tenant_id,
            new_value={"from_date": str(leave.from_date), "to_date": str(leave.to_date)},
        )
        return StudentService._leave_row(leave)

    @staticmethod
    async def cancel_leave(db: AsyncSession, student: User, leave_id: uuid.UUID) -> StudentLeaveRow:
        leave = (
            await db.execute(
                select(AttendanceLeave)
                .where(
                    AttendanceLeave.id == leave_id,
                    AttendanceLeave.tenant_id == student.tenant_id,
                    AttendanceLeave.student_id == student.id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if leave is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Leave request not found")
        if leave.status != LeaveStatus.PENDING:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Only pending leave requests can be cancelled")
        leave.status = LeaveStatus.CANCELLED
        await db.flush()
        AuditService.record(
            db,
            actor=student,
            actor_role="STUDENT",
            action="CANCEL_LEAVE",
            entity="AttendanceLeave",
            entity_id=leave.id,
            tenant_id=student.tenant_id,
        )
        return StudentService._leave_row(leave)

    # ── C-ST-06 timetable ───────────────────────────────────────────────────

    @staticmethod
    async def _timetable_slots(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        ctx: StudentContext,
        *,
        day: date | None = None,
        for_day_only: bool = False,
    ) -> list[StudentTimetableSlot]:
        today = day or await PrincipalService._tenant_today(db, tenant_id)
        clauses = [
            TimetableSlot.tenant_id == tenant_id,
            TimetableSlot.class_id == ctx.school_class.id,
            TimetableSlot.academic_year_id == ctx.academic_year.id,
            TimetableSlot.effective_from <= today,
            or_(TimetableSlot.effective_to.is_(None), TimetableSlot.effective_to >= today),
        ]
        if for_day_only and day is not None:
            clauses.append(TimetableSlot.day_of_week == day.isoweekday())
        rows = (
            await db.execute(
                select(TimetableSlot, Subject, User)
                .outerjoin(Subject, Subject.id == TimetableSlot.subject_id)
                .outerjoin(User, and_(User.id == TimetableSlot.teacher_id, User.tenant_id == tenant_id))
                .where(*clauses)
                .order_by(TimetableSlot.day_of_week, TimetableSlot.period_number)
            )
        ).all()
        return [
            StudentTimetableSlot(
                id=slot.id,
                day_of_week=slot.day_of_week,
                period_number=slot.period_number,
                start_time=slot.start_time,
                end_time=slot.end_time,
                subject_id=subject.id if subject else None,
                subject_code=subject.code if subject else None,
                subject_name=subject.name if subject else None,
                teacher_name=teacher.name if teacher else None,
                room_no=slot.room_no,
                slot_type=_value(slot.slot_type) or "CLASS",
            )
            for slot, subject, teacher in rows
        ]

    @staticmethod
    async def timetable(db: AsyncSession, student: User) -> StudentTimetable:
        ctx = await StudentService.context_for_user(db, student)
        slots = await StudentService._timetable_slots(db, student.tenant_id, ctx)
        return StudentTimetable(class_info=ctx.class_info, slots=slots)

    # ── C-ST-07 … C-ST-09 examinations ───────────────────────────────────────

    @staticmethod
    async def examinations(
        db: AsyncSession,
        student: User,
        *,
        when: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StudentExamPage:
        StudentService._validate_page(limit, offset)
        ctx = await StudentService.context_for_user(db, student)
        tenant_id = student.tenant_id
        now = datetime.now(timezone.utc)
        if when not in (None, "", "all", "upcoming", "completed"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="when must be upcoming, completed or all")

        base_clauses = [
            Exam.tenant_id == tenant_id,
            Exam.class_id == ctx.school_class.id,
            Exam.status.in_((ExamStatus.PUBLISHED, ExamStatus.ONGOING, ExamStatus.COMPLETED, ExamStatus.RESULTS_RELEASED)),
        ]
        all_rows = (
            await db.execute(
                select(Exam, Subject)
                .join(Subject, Subject.id == Exam.subject_id)
                .where(*base_clauses)
                .order_by(Exam.scheduled_at.desc())
            )
        ).all()
        attempts = await StudentService._attempts_by_exam(db, tenant_id, student.id, [exam.id for exam, _s in all_rows])

        filtered_items: list[StudentExamRow] = []
        for exam, subject in all_rows:
            attempt = attempts.get(exam.id)
            row = StudentService._exam_row(exam, subject, attempt, now)

            window_end = exam.window_end_at or (exam.scheduled_at + timedelta(minutes=exam.duration_minutes))
            has_submitted = attempt is not None and _value(attempt.status) in (
                AttemptStatus.SUBMITTED.value,
                AttemptStatus.GRADED.value,
                AttemptStatus.MALPRACTICE.value,
            )
            is_past = (
                now > window_end
                or _value(exam.status) in (ExamStatus.COMPLETED.value, ExamStatus.RESULTS_RELEASED.value)
                or has_submitted
            )

            if when == "upcoming" and is_past:
                continue
            if when == "completed" and not is_past:
                continue

            filtered_items.append(row)

        total = len(filtered_items)
        paged_items = filtered_items[offset : offset + limit]
        return StudentExamPage(
            total=total,
            limit=limit,
            offset=offset,
            items=paged_items,
        )

    @staticmethod
    async def _attempts_by_exam(
        db: AsyncSession, tenant_id: uuid.UUID, student_id: uuid.UUID, exam_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ExamAttempt]:
        if not exam_ids:
            return {}
        rows = (
            await db.execute(
                select(ExamAttempt).where(
                    ExamAttempt.tenant_id == tenant_id,
                    ExamAttempt.student_id == student_id,
                    ExamAttempt.exam_id.in_(exam_ids),
                )
            )
        ).scalars().all()
        return {attempt.exam_id: attempt for attempt in rows}

    @staticmethod
    def _exam_row(exam: Exam, subject: Subject, attempt: ExamAttempt | None, now: datetime) -> StudentExamRow:
        state = _value(exam.status) or "DRAFT"
        mode = _value(exam.mode) or "ONLINE"
        result_available = state == ExamStatus.RESULTS_RELEASED.value or (
            attempt is not None
            and _value(attempt.status) in (AttemptStatus.SUBMITTED.value, AttemptStatus.GRADED.value)
            and (exam.show_score_immediately or exam.allow_review)
        )
        window_end = exam.window_end_at or (exam.scheduled_at + timedelta(minutes=exam.duration_minutes))
        can_attempt = (
            mode == "ONLINE"
            and state in (ExamStatus.PUBLISHED.value, ExamStatus.ONGOING.value)
            and attempt is None
            and exam.scheduled_at <= now <= window_end
        )
        my_attempt_status = _value(attempt.status) if attempt else None
        if (attempt is None or my_attempt_status == AttemptStatus.NOT_STARTED.value) and (
            now > window_end or state in (ExamStatus.COMPLETED.value, ExamStatus.RESULTS_RELEASED.value)
        ):
            my_attempt_status = "NOT_ATTEMPTED"

        return StudentExamRow(
            id=exam.id,
            title=exam.title,
            subject_name=subject.name,
            subject_code=subject.code,
            exam_type=_value(exam.exam_type) or "MIXED",
            mode=mode,
            total_marks=exam.total_marks,
            passing_marks=exam.passing_marks,
            duration_minutes=exam.duration_minutes,
            scheduled_at=exam.scheduled_at,
            window_end_at=exam.window_end_at,
            status=state,
            my_attempt_status=my_attempt_status,
            my_score=float(attempt.total_score) if attempt and attempt.total_score is not None and result_available else None,
            can_attempt=can_attempt,
            result_available=result_available,
        )

    @staticmethod
    async def exam_detail(db: AsyncSession, student: User, exam_id: uuid.UUID) -> StudentExamDetail:
        ctx = await StudentService.context_for_user(db, student)
        exam, subject = await StudentService._visible_exam(db, student, ctx, exam_id)
        attempt = (
            await db.execute(
                select(ExamAttempt).where(
                    ExamAttempt.tenant_id == student.tenant_id,
                    ExamAttempt.exam_id == exam.id,
                    ExamAttempt.student_id == student.id,
                )
            )
        ).scalar_one_or_none()
        question_count = (
            await db.execute(select(func.count(Question.id)).where(Question.exam_id == exam.id))
        ).scalar() or 0
        now = datetime.now(timezone.utc)
        return StudentExamDetail(
            **StudentService._exam_row(exam, subject, attempt, now).model_dump(),
            instructions=exam.instructions,
            question_count=int(question_count),
            allow_review=exam.allow_review,
            show_score_immediately=exam.show_score_immediately,
            attempt_id=attempt.id if attempt else None,
            attempt_started_at=attempt.started_at if attempt else None,
            attempt_submitted_at=attempt.submitted_at if attempt else None,
        )

    @staticmethod
    async def _visible_exam(db: AsyncSession, student: User, ctx: StudentContext, exam_id: uuid.UUID):
        row = (
            await db.execute(
                select(Exam, Subject)
                .join(Subject, Subject.id == Exam.subject_id)
                .where(
                    Exam.id == exam_id,
                    Exam.tenant_id == student.tenant_id,
                    Exam.class_id == ctx.school_class.id,
                    Exam.status.in_(
                        (ExamStatus.PUBLISHED, ExamStatus.ONGOING, ExamStatus.COMPLETED, ExamStatus.RESULTS_RELEASED)
                    ),
                )
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam not found")
        return row

    # ── C-ST-08 attempt flow ────────────────────────────────────────────────

    @staticmethod
    def _attempt_ends_at(exam: Exam, attempt_started: datetime) -> datetime:
        deadline = attempt_started + timedelta(minutes=exam.duration_minutes)
        if exam.window_end_at and exam.window_end_at < deadline:
            deadline = exam.window_end_at
        return deadline

    @staticmethod
    async def start_attempt(db: AsyncSession, student: User, exam_id: uuid.UUID) -> StudentAttemptState:
        ctx = await StudentService.context_for_user(db, student)
        exam, _subject = await StudentService._visible_exam(db, student, ctx, exam_id)
        if (_value(exam.mode) or "ONLINE") != "ONLINE":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This is an offline exam; no online attempt is available")
        state = _value(exam.status) or "PUBLISHED"
        if state not in (ExamStatus.PUBLISHED.value, ExamStatus.ONGOING.value):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This exam is not open for attempts")
        now = datetime.now(timezone.utc)
        window_end = exam.window_end_at or (exam.scheduled_at + timedelta(minutes=exam.duration_minutes))
        if now < exam.scheduled_at:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This exam has not started yet")
        if now > window_end:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="The exam window has closed")
        existing = (
            await db.execute(
                select(ExamAttempt).where(
                    ExamAttempt.tenant_id == student.tenant_id,
                    ExamAttempt.exam_id == exam.id,
                    ExamAttempt.student_id == student.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if _value(existing.status) == AttemptStatus.IN_PROGRESS.value:
                return StudentService._attempt_state(exam, existing)
            raise HTTPException(status.HTTP_409_CONFLICT, detail="You have already attempted this exam")
        attempt = ExamAttempt(
            id=uuid.uuid4(),
            tenant_id=student.tenant_id,
            exam_id=exam.id,
            student_id=student.id,
            started_at=now,
            status=AttemptStatus.IN_PROGRESS,
        )
        db.add(attempt)
        if state == ExamStatus.PUBLISHED.value:
            exam.status = ExamStatus.ONGOING
        await db.flush()
        AuditService.record(
            db,
            actor=student,
            actor_role="STUDENT",
            action="START_EXAM_ATTEMPT",
            entity="ExamAttempt",
            entity_id=attempt.id,
            tenant_id=student.tenant_id,
            new_value={"exam_id": str(exam.id)},
        )
        return StudentService._attempt_state(exam, attempt)

    @staticmethod
    def _attempt_state(exam: Exam, attempt: ExamAttempt) -> StudentAttemptState:
        return StudentAttemptState(
            attempt_id=attempt.id,
            exam_id=attempt.exam_id,
            started_at=attempt.started_at,
            duration_minutes=exam.duration_minutes,
            ends_at=StudentService._attempt_ends_at(exam, attempt.started_at),
            status=_value(attempt.status) or "IN_PROGRESS",
        )

    @staticmethod
    async def _in_progress_attempt(db: AsyncSession, student: User, ctx: StudentContext, exam_id: uuid.UUID):
        exam, subject = await StudentService._visible_exam(db, student, ctx, exam_id)
        attempt = (
            await db.execute(
                select(ExamAttempt).where(
                    ExamAttempt.tenant_id == student.tenant_id,
                    ExamAttempt.exam_id == exam.id,
                    ExamAttempt.student_id == student.id,
                )
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Start the exam attempt first")
        if _value(attempt.status) != AttemptStatus.IN_PROGRESS.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This attempt is already submitted")
        ends_at = StudentService._attempt_ends_at(exam, attempt.started_at)
        if datetime.now(timezone.utc) > ends_at + _AUTO_SUBMIT_GRACE:
            # Hard stop: treat as auto-submitted with whatever is saved.
            await StudentService._finalise_attempt(db, exam, attempt, auto=True)
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Time expired; the attempt was auto-submitted")
        return exam, subject, attempt

    @staticmethod
    async def attempt_paper(db: AsyncSession, student: User, exam_id: uuid.UUID) -> StudentAttemptPaper:
        ctx = await StudentService.context_for_user(db, student)
        exam, _subject, attempt = await StudentService._in_progress_attempt(db, student, ctx, exam_id)
        questions = (
            await db.execute(
                select(Question).where(Question.exam_id == exam.id).order_by(Question.sort_order, Question.id)
            )
        ).scalars().all()
        options = (
            await db.execute(
                select(QuestionOption)
                .where(QuestionOption.question_id.in_([q.id for q in questions]))
                .order_by(QuestionOption.sort_order, QuestionOption.id)
            )
        ).scalars().all() if questions else []
        my_answers = (
            await db.execute(select(Answer).where(Answer.attempt_id == attempt.id))
        ).scalars().all()
        answer_by_question = {answer.question_id: answer for answer in my_answers}
        options_by_question: dict[uuid.UUID, list[QuestionOption]] = {}
        for option in options:
            options_by_question.setdefault(option.question_id, []).append(option)
        ordered = list(questions)
        if exam.shuffle_questions:
            # Deterministic per-attempt shuffle so refreshes keep the same order.
            ordered = sorted(
                questions, key=lambda q: uuid.uuid5(uuid.NAMESPACE_URL, f"{attempt.id}:{q.id}").int
            )
        return StudentAttemptPaper(
            attempt=StudentService._attempt_state(exam, attempt),
            questions=[
                StudentAttemptQuestion(
                    id=question.id,
                    text=question.text,
                    question_type=_value(question.question_type) or "MCQ",
                    marks=float(question.marks),
                    image_url=question.image_url,
                    sort_order=question.sort_order,
                    options=[
                        StudentAttemptOption(
                            id=option.id, text=option.text, image_url=option.image_url, sort_order=option.sort_order
                        )
                        for option in options_by_question.get(question.id, [])
                    ],
                    my_selected_option_id=(
                        answer_by_question[question.id].selected_option_id if question.id in answer_by_question else None
                    ),
                    my_text_answer=(
                        answer_by_question[question.id].text_answer if question.id in answer_by_question else None
                    ),
                )
                for question in ordered
            ],
        )

    @staticmethod
    async def save_answer(db: AsyncSession, student: User, exam_id: uuid.UUID, payload: StudentAnswerSave) -> StudentAttemptPaper:
        ctx = await StudentService.context_for_user(db, student)
        exam, _subject, attempt = await StudentService._in_progress_attempt(db, student, ctx, exam_id)
        question = (
            await db.execute(select(Question).where(Question.id == payload.question_id, Question.exam_id == exam.id))
        ).scalar_one_or_none()
        if question is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found in this exam")
        kind = _value(question.question_type) or "MCQ"
        if kind in (QuestionType.MCQ.value, QuestionType.TRUE_FALSE.value):
            if payload.selected_option_id is None and payload.text_answer:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select an option for objective questions")
            if payload.selected_option_id is not None:
                valid = (
                    await db.execute(
                        select(QuestionOption.id).where(
                            QuestionOption.id == payload.selected_option_id,
                            QuestionOption.question_id == question.id,
                        )
                    )
                ).scalar_one_or_none()
                if valid is None:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Option does not belong to this question")
        answer = (
            await db.execute(
                select(Answer).where(Answer.attempt_id == attempt.id, Answer.question_id == question.id)
            )
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if answer is None:
            answer = Answer(id=uuid.uuid4(), attempt_id=attempt.id, question_id=question.id)
            db.add(answer)
        answer.selected_option_id = payload.selected_option_id if kind in (QuestionType.MCQ.value, QuestionType.TRUE_FALSE.value) else None
        answer.text_answer = payload.text_answer.strip() if payload.text_answer and kind not in (QuestionType.MCQ.value, QuestionType.TRUE_FALSE.value) else None
        answer.answered_at = now
        await db.flush()
        return await StudentService.attempt_paper(db, student, exam_id)

    @staticmethod
    async def submit_attempt(db: AsyncSession, student: User, exam_id: uuid.UUID) -> StudentAttemptState:
        ctx = await StudentService.context_for_user(db, student)
        exam, _subject = await StudentService._visible_exam(db, student, ctx, exam_id)
        attempt = (
            await db.execute(
                select(ExamAttempt)
                .where(
                    ExamAttempt.tenant_id == student.tenant_id,
                    ExamAttempt.exam_id == exam.id,
                    ExamAttempt.student_id == student.id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Start the exam attempt first")
        if _value(attempt.status) != AttemptStatus.IN_PROGRESS.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This attempt is already submitted")
        await StudentService._finalise_attempt(db, exam, attempt, auto=False)
        AuditService.record(
            db,
            actor=student,
            actor_role="STUDENT",
            action="SUBMIT_EXAM_ATTEMPT",
            entity="ExamAttempt",
            entity_id=attempt.id,
            tenant_id=student.tenant_id,
            new_value={"exam_id": str(exam.id), "score": str(attempt.total_score)},
        )
        return StudentService._attempt_state(exam, attempt)

    @staticmethod
    async def record_tab_switch(db: AsyncSession, student: User, exam_id: uuid.UUID) -> StudentTabSwitch:
        """C-ST-08 anti-cheat signal: the attempt screen reports each time the
        student leaves the exam tab.  Server-side increment so the count can
        only grow; a closed attempt simply reports its frozen count (the
        frontend can fire a final beacon as the timer auto-submits)."""
        ctx = await StudentService.context_for_user(db, student)
        exam, _subject = await StudentService._visible_exam(db, student, ctx, exam_id)
        attempt = (
            await db.execute(
                select(ExamAttempt)
                .where(
                    ExamAttempt.tenant_id == student.tenant_id,
                    ExamAttempt.exam_id == exam.id,
                    ExamAttempt.student_id == student.id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Start the exam attempt first")
        if _value(attempt.status) != AttemptStatus.IN_PROGRESS.value:
            return StudentTabSwitch(tab_switch_count=attempt.tab_switch_count or 0)
        attempt.tab_switch_count = (attempt.tab_switch_count or 0) + 1
        await db.flush()
        return StudentTabSwitch(tab_switch_count=attempt.tab_switch_count)

    @staticmethod
    async def _finalise_attempt(db: AsyncSession, exam: Exam, attempt: ExamAttempt, *, auto: bool) -> None:
        """Auto-grade objective answers; descriptive answers wait for C-TC-11."""
        rows = (
            await db.execute(
                select(Question, Answer, QuestionOption)
                .outerjoin(
                    Answer, and_(Answer.question_id == Question.id, Answer.attempt_id == attempt.id)
                )
                .outerjoin(
                    QuestionOption,
                    and_(
                        QuestionOption.question_id == Question.id,
                        QuestionOption.is_correct.is_(True),
                    ),
                )
                .where(Question.exam_id == exam.id)
                .order_by(Question.sort_order)
            )
        ).all()
        now = datetime.now(timezone.utc)
        total = Decimal("0")
        for question, answer, correct_option in rows:
            kind = _value(question.question_type) or "MCQ"
            if kind not in (QuestionType.MCQ.value, QuestionType.TRUE_FALSE.value):
                continue
            if answer is None:
                answer = Answer(id=uuid.uuid4(), attempt_id=attempt.id, question_id=question.id)
                db.add(answer)
            selected_correct = (
                answer.selected_option_id is not None
                and correct_option is not None
                and answer.selected_option_id == correct_option.id
            )
            if selected_correct:
                answer.score = question.marks
            elif answer.selected_option_id is not None:
                answer.score = -question.negative_marks if question.negative_marks else Decimal("0")
                if answer.score > 0:
                    answer.score = Decimal("0")
            else:
                answer.score = Decimal("0")
            answer.is_auto_graded = True
            answer.graded_at = now
            total += answer.score
        attempt.total_score = total if total >= 0 else Decimal("0")
        attempt.submitted_at = now
        attempt.auto_submitted = auto
        if exam.show_score_immediately and exam.total_marks:
            attempt.percentage = (attempt.total_score * 100 / Decimal(exam.total_marks)).quantize(Decimal("0.01"))
            attempt.grade = grade_for(float(attempt.percentage))
        attempt.status = AttemptStatus.SUBMITTED
        await db.flush()

    # ── C-ST-09 exam result ─────────────────────────────────────────────────

    @staticmethod
    async def exam_result(db: AsyncSession, student: User, exam_id: uuid.UUID) -> StudentExamResult:
        """C-ST-09 — the student's result for one exam, with a typed state.

        The endpoint answers "what state is my result in?" instead of raising
        prose 404s the UI would have to string-match: NOT_ATTEMPTED /
        IN_PROGRESS / UNDER_EVALUATION / AVAILABLE (see StudentExamResult).
        Only a genuinely invisible exam still raises 404.
        """
        ctx = await StudentService.context_for_user(db, student)
        exam, subject = await StudentService._visible_exam(db, student, ctx, exam_id)
        attempt = (
            await db.execute(
                select(ExamAttempt).where(
                    ExamAttempt.tenant_id == student.tenant_id,
                    ExamAttempt.exam_id == exam.id,
                    ExamAttempt.student_id == student.id,
                )
            )
        ).scalar_one_or_none()

        def header(state: str) -> StudentExamResult:
            return StudentExamResult(
                exam_id=exam.id,
                title=exam.title,
                subject_name=subject.name,
                total_marks=exam.total_marks,
                passing_marks=exam.passing_marks,
                status=_value(exam.status) or "COMPLETED",
                result_state=state,
                submitted_at=attempt.submitted_at if attempt else None,
            )

        if attempt is None:
            return header(StudentExamResult.RESULT_NOT_ATTEMPTED)
        if _value(attempt.status) in (None, AttemptStatus.IN_PROGRESS.value):
            return header(StudentExamResult.RESULT_IN_PROGRESS)
        released = (_value(exam.status) or "") == ExamStatus.RESULTS_RELEASED.value
        # show_score_immediately is the teacher's explicit "quiz mode" opt-in
        # for a score right after submit. allow_review deliberately does NOT
        # bypass the release gate: it only widens what a *released* result
        # includes (see show_answers below) — the integration suite pins
        # "gated until the teacher releases it" as the product rule.
        immediate = exam.show_score_immediately and _value(attempt.status) in (
            AttemptStatus.SUBMITTED.value,
            AttemptStatus.GRADED.value,
        )
        if not (released or immediate):
            return header(StudentExamResult.RESULT_UNDER_EVALUATION)
        show_answers = released or exam.allow_review
        answers: list[StudentResultAnswer] = []
        if show_answers or immediate:
            rows = (
                await db.execute(
                    select(Question, Answer)
                    .outerjoin(Answer, and_(Answer.question_id == Question.id, Answer.attempt_id == attempt.id))
                    .where(Question.exam_id == exam.id)
                    .order_by(Question.sort_order)
                )
            ).all()
            option_rows = (
                await db.execute(
                    select(QuestionOption).where(QuestionOption.question_id.in_([q.id for q, _a in rows]))
                )
            ).scalars().all() if rows else []
            options_by_id = {option.id: option for option in option_rows}
            correct_by_question = {
                option.question_id: option for option in option_rows if option.is_correct
            }
            for question, answer in rows:
                selected = options_by_id.get(answer.selected_option_id) if answer and answer.selected_option_id else None
                correct = correct_by_question.get(question.id)
                answers.append(
                    StudentResultAnswer(
                        question_id=question.id,
                        question_text=question.text,
                        question_type=_value(question.question_type) or "MCQ",
                        marks=float(question.marks),
                        selected_option_id=selected.id if selected else None,
                        selected_option_text=selected.text if selected else None,
                        # Correct options are exposed only after official release.
                        correct_option_id=correct.id if (correct and show_answers) else None,
                        correct_option_text=correct.text if (correct and show_answers) else None,
                        text_answer=answer.text_answer if answer else None,
                        score=float(answer.score) if answer and answer.score is not None else None,
                        feedback=answer.feedback if answer else None,
                    )
                )
        return StudentExamResult(
            exam_id=exam.id,
            title=exam.title,
            subject_name=subject.name,
            total_marks=exam.total_marks,
            passing_marks=exam.passing_marks,
            status=_value(exam.status) or "COMPLETED",
            result_state=StudentExamResult.RESULT_AVAILABLE,
            total_score=float(attempt.total_score) if attempt.total_score is not None else None,
            percentage=float(attempt.percentage) if attempt.percentage is not None else (
                round(float(attempt.total_score) * 100 / exam.total_marks, 2)
                if attempt.total_score is not None and exam.total_marks
                else None
            ),
            grade=attempt.grade,
            submitted_at=attempt.submitted_at,
            show_answers=show_answers,
            answers=answers,
        )

    # ── C-ST-10 … C-ST-12 assignments ────────────────────────────────────────

    @staticmethod
    async def assignments(
        db: AsyncSession,
        student: User,
        *,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StudentAssignmentPage:
        StudentService._validate_page(limit, offset)
        ctx = await StudentService.context_for_user(db, student)
        tenant_id = student.tenant_id
        clauses = [
            Assignment.tenant_id == tenant_id,
            Assignment.class_id == ctx.school_class.id,
            Assignment.status.in_((AssignmentStatus.PUBLISHED, AssignmentStatus.CLOSED)),
        ]
        total = (await db.execute(select(func.count(Assignment.id)).where(*clauses))).scalar() or 0
        rows = (
            await db.execute(
                select(Assignment, Subject, User)
                .join(Subject, Subject.id == Assignment.subject_id)
                .outerjoin(User, and_(User.id == Assignment.teacher_id, User.tenant_id == tenant_id))
                .where(*clauses)
                .order_by(Assignment.due_date)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        my_submissions = await StudentService._my_latest_submissions(
            db, tenant_id, student.id, [assignment.id for assignment, _s, _t in rows]
        )
        items = [
            StudentService._assignment_row(assignment, subject, teacher, my_submissions.get(assignment.id))
            for assignment, subject, teacher in rows
        ]
        if status_filter:
            wanted = status_filter.strip().upper()
            items = [item for item in items if item.my_status == wanted]
        return StudentAssignmentPage(total=int(total), limit=limit, offset=offset, items=items)

    @staticmethod
    async def _my_latest_submissions(
        db: AsyncSession, tenant_id: uuid.UUID, student_id: uuid.UUID, assignment_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Submission]:
        if not assignment_ids:
            return {}
        rows = (
            await db.execute(
                select(Submission)
                .where(
                    Submission.tenant_id == tenant_id,
                    Submission.student_id == student_id,
                    Submission.assignment_id.in_(assignment_ids),
                )
                .order_by(Submission.submitted_at.desc())
            )
        ).scalars().all()
        latest: dict[uuid.UUID, Submission] = {}
        for submission in rows:
            latest.setdefault(submission.assignment_id, submission)
        return latest

    @staticmethod
    def _assignment_row(
        assignment: Assignment, subject: Subject, teacher: User | None, my: Submission | None
    ) -> StudentAssignmentRow:
        return StudentAssignmentRow(
            id=assignment.id,
            title=assignment.title,
            subject_name=subject.name,
            subject_code=subject.code,
            teacher_name=teacher.name if teacher else None,
            assignment_type=assignment.assignment_type,
            total_marks=assignment.total_marks,
            due_date=assignment.due_date,
            status=_value(assignment.status) or "PUBLISHED",
            my_status=(_value(my.status) if my else "PENDING") or "PENDING",
            my_score=float(my.score) if my and my.score is not None else None,
            my_submitted_at=my.submitted_at if my else None,
            is_late=bool(my.is_late) if my else False,
        )

    @staticmethod
    async def _get_student_group_for_assignment(
        db: AsyncSession, tenant_id: uuid.UUID, student_id: uuid.UUID, assignment_id: uuid.UUID
    ) -> StudentGroupRow | None:
        member_row = (
            await db.execute(
                select(ProjectGroupMember.group_id)
                .join(ProjectGroup, ProjectGroup.id == ProjectGroupMember.group_id)
                .where(
                    ProjectGroupMember.student_id == student_id,
                    ProjectGroupMember.tenant_id == tenant_id,
                    ProjectGroup.assignment_id == assignment_id,
                )
            )
        ).scalar_one_or_none()
        if member_row is None:
            return None
        return await StudentService._build_student_group_row(db, tenant_id, member_row, student_id)

    @staticmethod
    async def _build_student_group_row(
        db: AsyncSession, tenant_id: uuid.UUID, group_id: uuid.UUID, current_student_id: uuid.UUID
    ) -> StudentGroupRow | None:
        row = (
            await db.execute(
                select(ProjectGroup, User)
                .outerjoin(User, and_(User.id == ProjectGroup.created_by, User.tenant_id == tenant_id))
                .where(ProjectGroup.id == group_id, ProjectGroup.tenant_id == tenant_id)
            )
        ).first()
        if row is None:
            return None
        group, creator = row

        members_rows = (
            await db.execute(
                select(ProjectGroupMember, User, Enrollment)
                .join(User, and_(User.id == ProjectGroupMember.student_id, User.tenant_id == tenant_id))
                .outerjoin(
                    Enrollment,
                    and_(
                        Enrollment.student_id == ProjectGroupMember.student_id,
                        Enrollment.tenant_id == tenant_id,
                    ),
                )
                .where(ProjectGroupMember.group_id == group.id)
                .order_by(ProjectGroupMember.joined_at.asc())
            )
        ).all()

        members = [
            StudentGroupMember(
                student_id=user.id,
                student_name=user.name,
                roll_number=(enrollment.roll_number if enrollment and enrollment.roll_number else user.student_roll_no),
                is_me=(user.id == current_student_id),
                joined_at=member.joined_at,
            )
            for member, user, enrollment in members_rows
        ]

        sub = (
            await db.execute(
                select(Submission.id).where(
                    Submission.assignment_id == group.assignment_id,
                    Submission.tenant_id == tenant_id,
                    or_(
                        Submission.group_id == group.id,
                        Submission.student_id.in_([m.student_id for m in members] if members else [uuid.uuid4()]),
                    ),
                )
            )
        ).scalar_one_or_none()

        return StudentGroupRow(
            id=group.id,
            assignment_id=group.assignment_id,
            name=group.name,
            created_by=group.created_by,
            creator_name=creator.name if creator else None,
            member_count=len(members),
            is_my_group=any(m.student_id == current_student_id for m in members),
            is_submitted=sub is not None,
            members=members,
        )

    @staticmethod
    async def assignment_detail(db: AsyncSession, student: User, assignment_id: uuid.UUID) -> StudentAssignmentDetail:
        ctx = await StudentService.context_for_user(db, student)
        row = (
            await db.execute(
                select(Assignment, Subject, User)
                .join(Subject, Subject.id == Assignment.subject_id)
                .outerjoin(User, and_(User.id == Assignment.teacher_id, User.tenant_id == student.tenant_id))
                .where(
                    Assignment.id == assignment_id,
                    Assignment.tenant_id == student.tenant_id,
                    Assignment.class_id == ctx.school_class.id,
                    Assignment.status.in_((AssignmentStatus.PUBLISHED, AssignmentStatus.CLOSED)),
                )
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        assignment, subject, teacher = row

        my_group: StudentGroupRow | None = None
        if assignment.assignment_type == "GROUP":
            my_group = await StudentService._get_student_group_for_assignment(
                db, student.tenant_id, student.id, assignment.id
            )

        milestones = (
            await db.execute(
                select(Milestone).where(Milestone.assignment_id == assignment.id).order_by(Milestone.sort_order)
            )
        ).scalars().all()

        submission_clauses = [
            Submission.tenant_id == student.tenant_id,
            Submission.assignment_id == assignment.id,
        ]
        if my_group:
            submission_clauses.append(
                or_(
                    Submission.group_id == my_group.id,
                    Submission.student_id == student.id,
                )
            )
        else:
            submission_clauses.append(Submission.student_id == student.id)

        my_submissions = (
            await db.execute(
                select(Submission)
                .where(*submission_clauses)
                .order_by(Submission.submitted_at.desc())
            )
        ).scalars().all()
        latest = my_submissions[0] if my_submissions else None
        latest_by_milestone: dict[uuid.UUID | None, Submission] = {}
        for submission in my_submissions:
            latest_by_milestone.setdefault(submission.milestone_id, submission)
        approved_milestones = {
            submission.milestone_id
            for submission in my_submissions
            if _value(submission.status) == SubmissionStatus.APPROVED.value and submission.milestone_id
        }
        milestone_progress = []
        for milestone in milestones:
            gate_ok = (
                milestone.unlock_after_milestone_id is None
                or milestone.unlock_after_milestone_id in approved_milestones
            )
            mine = latest_by_milestone.get(milestone.id)
            milestone_progress.append(
                StudentMilestoneProgress(
                    id=milestone.id,
                    title=milestone.title,
                    description=milestone.description,
                    sort_order=milestone.sort_order,
                    marks=milestone.marks,
                    due_date=milestone.due_date,
                    unlocked=gate_ok,
                    my_status=_value(mine.status) if mine else None,
                    my_score=float(mine.score) if mine and mine.score is not None else None,
                    my_submitted_at=mine.submitted_at if mine else None,
                )
            )
        files = await StudentService._submission_files(db, [s.id for s in my_submissions])
        return StudentAssignmentDetail(
            **StudentService._assignment_row(assignment, subject, teacher, latest).model_dump(),
            description=assignment.description,
            passing_marks=assignment.passing_marks,
            allow_late_submission=assignment.allow_late_submission,
            max_file_size_mb=assignment.max_file_size_mb,
            allowed_file_types=list(assignment.allowed_file_types or []),
            min_group_size=getattr(assignment, "min_group_size", 2) or 2,
            max_group_size=getattr(assignment, "max_group_size", 6) or 6,
            my_group=my_group,
            instructions_url=assignment.instructions_url,
            milestones=milestone_progress,
            my_submissions=[
                StudentSubmissionOut(
                    id=submission.id,
                    milestone_id=submission.milestone_id,
                    group_id=submission.group_id,
                    group_name=my_group.name if my_group and submission.group_id == my_group.id else None,
                    submitted_at=submission.submitted_at,
                    is_late=submission.is_late,
                    status=_value(submission.status) or "SUBMITTED",
                    score=float(submission.score) if submission.score is not None else None,
                    grade=submission.grade,
                    feedback=submission.feedback,
                    reviewed_at=submission.reviewed_at,
                    version=submission.version or 1,
                    text_response=submission.text_response,
                    files=files.get(submission.id, []),
                )
                for submission in my_submissions
            ],
        )

    @staticmethod
    async def _submission_files(
        db: AsyncSession, submission_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[StudentSubmissionFileOut]]:
        if not submission_ids:
            return {}
        rows = (
            await db.execute(
                select(SubmissionFile).where(SubmissionFile.submission_id.in_(submission_ids)).order_by(SubmissionFile.uploaded_at)
            )
        ).scalars().all()
        grouped: dict[uuid.UUID, list[StudentSubmissionFileOut]] = {}
        for file in rows:
            grouped.setdefault(file.submission_id, []).append(
                StudentSubmissionFileOut(
                    id=file.id,
                    file_name=file.file_name,
                    file_key=file.file_key,
                    file_size_bytes=file.file_size_bytes,
                    mime_type=file.mime_type,
                    uploaded_at=file.uploaded_at,
                )
            )
        return grouped

    @staticmethod
    async def submit_assignment(
        db: AsyncSession, student: User, assignment_id: uuid.UUID, payload: StudentSubmissionCreate
    ) -> StudentSubmissionOut:
        ctx = await StudentService.context_for_user(db, student)
        row = (
            await db.execute(
                select(Assignment).where(
                    Assignment.id == assignment_id,
                    Assignment.tenant_id == student.tenant_id,
                    Assignment.class_id == ctx.school_class.id,
                    Assignment.status.in_((AssignmentStatus.PUBLISHED, AssignmentStatus.CLOSED)),
                )
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        assignment = row[0]
        if (_value(assignment.status) or "") == AssignmentStatus.CLOSED.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This assignment is closed")

        milestone: Milestone | None = None
        if payload.milestone_id is not None:
            milestone = (
                await db.execute(
                    select(Milestone).where(
                        Milestone.id == payload.milestone_id, Milestone.assignment_id == assignment.id
                    )
                )
            ).scalar_one_or_none()
            if milestone is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Milestone not found")
            if milestone.unlock_after_milestone_id is not None:
                gate = (
                    await db.execute(
                        select(Submission.id).where(
                            Submission.tenant_id == student.tenant_id,
                            Submission.student_id == student.id,
                            Submission.milestone_id == milestone.unlock_after_milestone_id,
                            Submission.status == SubmissionStatus.APPROVED,
                        )
                    )
                ).scalar_one_or_none()
                if gate is None:
                    raise HTTPException(status.HTTP_409_CONFLICT, detail="Complete the previous milestone first")

        now = datetime.now(timezone.utc)
        due = milestone.due_date if milestone and milestone.due_date else assignment.due_date
        is_late = now > due
        if is_late and not assignment.allow_late_submission:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="The due date has passed and late submissions are not allowed")

        if not payload.text_response and not payload.files:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Add a response or at least one file")
        allowed = {ext.lower() for ext in (assignment.allowed_file_types or [])}
        for file in payload.files:
            ext = file.file_name.rsplit(".", 1)[-1].lower() if "." in file.file_name else ""
            if allowed and ext not in allowed:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f".{ext or 'unknown'} files are not allowed for this assignment",
                )
            if file.file_size_bytes > assignment.max_file_size_mb * 1024 * 1024:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{file.file_name} exceeds the {assignment.max_file_size_mb} MB limit",
                )

        my_group_for_sub: StudentGroupRow | None = None
        if assignment.assignment_type == "GROUP":
            my_group_for_sub = await StudentService._get_student_group_for_assignment(
                db, student.tenant_id, student.id, assignment.id
            )
            if not my_group_for_sub:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="You must create or join a group before submitting this group assignment",
                )
            min_size = getattr(assignment, "min_group_size", 2) or 2
            if my_group_for_sub.member_count < min_size:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Your group has {my_group_for_sub.member_count} member(s). A minimum of {min_size} members is required to submit.",
                )

        group_id_val = my_group_for_sub.id if my_group_for_sub else None

        sub_check_clauses = [
            Submission.tenant_id == student.tenant_id,
            Submission.assignment_id == assignment.id,
            (Submission.milestone_id == payload.milestone_id)
            if payload.milestone_id
            else Submission.milestone_id.is_(None),
        ]
        if group_id_val:
            sub_check_clauses.append(
                or_(
                    Submission.group_id == group_id_val,
                    Submission.student_id == student.id,
                )
            )
        else:
            sub_check_clauses.append(Submission.student_id == student.id)

        previous_versions = (
            await db.execute(
                select(func.coalesce(func.max(Submission.version), 0), func.count(Submission.id))
                .where(*sub_check_clauses)
            )
        ).one()
        count = int(previous_versions[1] or 0)
        if count:
            latest = (
                await db.execute(
                    select(Submission)
                    .where(*sub_check_clauses)
                    .order_by(Submission.version.desc())
                    .limit(1)
                )
            ).scalar_one()
            state = _value(latest.status) or "SUBMITTED"
            if state == SubmissionStatus.APPROVED.value:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail="This submission has already been approved and cannot be resubmitted",
                )
            if state == SubmissionStatus.REJECTED.value:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="This submission was rejected")
        submission = Submission(
            id=uuid.uuid4(),
            tenant_id=student.tenant_id,
            assignment_id=assignment.id,
            milestone_id=payload.milestone_id,
            student_id=student.id,
            group_id=group_id_val,
            text_response=payload.text_response.strip() if payload.text_response else None,
            submitted_at=now,
            is_late=is_late,
            late_by_minutes=int((now - due).total_seconds() // 60) if is_late else None,
            status=SubmissionStatus.SUBMITTED,
            version=int(previous_versions[0] or 0) + 1,
        )
        db.add(submission)
        await db.flush()
        for file in payload.files:
            db.add(
                SubmissionFile(
                    id=uuid.uuid4(),
                    submission_id=submission.id,
                    file_name=file.file_name,
                    file_key=file.file_key,
                    file_size_bytes=file.file_size_bytes,
                    mime_type=file.mime_type,
                )
            )
        await db.flush()
        AuditService.record(
            db,
            actor=student,
            actor_role="STUDENT",
            action="SUBMIT_ASSIGNMENT",
            entity="Submission",
            entity_id=submission.id,
            tenant_id=student.tenant_id,
            new_value={
                "assignment_id": str(assignment.id),
                "milestone_id": str(payload.milestone_id) if payload.milestone_id else None,
                "group_id": str(group_id_val) if group_id_val else None,
                "version": submission.version,
                "files": len(payload.files),
            },
        )
        # Let the assignment's teacher know a (new) attempt arrived. Wrapped in
        # try/except so a notification problem can never fail the submission.
        try:
            await PushService.create_in_app_notifications(
                db,
                tenant_id=student.tenant_id,
                user_ids=[assignment.teacher_id],
                title="New assignment submission",
                body=f"{student.name} submitted \"{assignment.title}\" (v{submission.version}).",
                notif_type="SUBMISSION_RECEIVED",
                data={
                    "assignment_id": str(assignment.id),
                    "submission_id": str(submission.id),
                    "student_id": str(student.id),
                    "version": int(submission.version or 1),
                },
            )
        except Exception as exc:  # noqa: BLE001 - best-effort; never block submission
            logger.warning("Could not notify teacher of submission %s: %s", submission.id, exc)
        files = await StudentService._submission_files(db, [submission.id])
        return StudentSubmissionOut(
            id=submission.id,
            milestone_id=submission.milestone_id,
            group_id=submission.group_id,
            group_name=my_group_for_sub.name if my_group_for_sub else None,
            submitted_at=submission.submitted_at,
            is_late=submission.is_late,
            status=_value(submission.status) or "SUBMITTED",
            score=None,
            grade=None,
            feedback=None,
            reviewed_at=None,
            version=submission.version,
            text_response=submission.text_response,
            files=files.get(submission.id, []),
        )

    # ── Group project workflows (Student) ───────────────────────────────────

    @staticmethod
    async def assignment_groups(
        db: AsyncSession, student: User, assignment_id: uuid.UUID
    ) -> StudentGroupListOut:
        ctx = await StudentService.context_for_user(db, student)
        assignment = (
            await db.execute(
                select(Assignment).where(
                    Assignment.id == assignment_id,
                    Assignment.tenant_id == student.tenant_id,
                    Assignment.class_id == ctx.school_class.id,
                    Assignment.status.in_((AssignmentStatus.PUBLISHED, AssignmentStatus.CLOSED)),
                )
            )
        ).scalar_one_or_none()
        if assignment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")

        groups = (
            await db.execute(
                select(ProjectGroup)
                .where(
                    ProjectGroup.assignment_id == assignment.id,
                    ProjectGroup.tenant_id == student.tenant_id,
                )
                .order_by(ProjectGroup.created_at.asc())
            )
        ).scalars().all()

        group_rows: list[StudentGroupRow] = []
        my_group: StudentGroupRow | None = None

        for group in groups:
            row = await StudentService._build_student_group_row(
                db, student.tenant_id, group.id, student.id
            )
            if row:
                group_rows.append(row)
                if row.is_my_group:
                    my_group = row

        # Find previous groups this student belonged to across other assignments in the same class
        previous_groups: list[StudentPreviousGroupOption] = []
        prev_group_memberships = (
            await db.execute(
                select(ProjectGroup, Assignment, Subject)
                .join(ProjectGroupMember, ProjectGroupMember.group_id == ProjectGroup.id)
                .join(Assignment, Assignment.id == ProjectGroup.assignment_id)
                .join(Subject, Subject.id == Assignment.subject_id)
                .where(
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                    ProjectGroup.assignment_id != assignment.id,
                    Assignment.class_id == ctx.school_class.id,
                )
                .order_by(ProjectGroup.created_at.desc())
                .limit(10)
            )
        ).all()

        seen_prev_names: set[str] = set()
        for prev_group, prev_assignment, prev_subject in prev_group_memberships:
            if prev_group.name.lower() in seen_prev_names:
                continue
            seen_prev_names.add(prev_group.name.lower())

            prev_members_rows = (
                await db.execute(
                    select(ProjectGroupMember, User, Enrollment)
                    .join(User, and_(User.id == ProjectGroupMember.student_id, User.tenant_id == student.tenant_id))
                    .outerjoin(
                        Enrollment,
                        and_(
                            Enrollment.student_id == ProjectGroupMember.student_id,
                            Enrollment.tenant_id == student.tenant_id,
                        ),
                    )
                    .where(ProjectGroupMember.group_id == prev_group.id)
                    .order_by(ProjectGroupMember.joined_at.asc())
                )
            ).all()

            prev_members = [
                StudentGroupMember(
                    student_id=user.id,
                    student_name=user.name,
                    roll_number=(enrollment.roll_number if enrollment and enrollment.roll_number else user.student_roll_no),
                    is_me=(user.id == student.id),
                    joined_at=pm.joined_at,
                )
                for pm, user, enrollment in prev_members_rows
            ]

            previous_groups.append(
                StudentPreviousGroupOption(
                    group_id=prev_group.id,
                    group_name=prev_group.name,
                    assignment_title=prev_assignment.title,
                    subject_name=prev_subject.name,
                    member_count=len(prev_members),
                    members=prev_members,
                )
            )

        return StudentGroupListOut(
            min_group_size=getattr(assignment, "min_group_size", 2) or 2,
            max_group_size=getattr(assignment, "max_group_size", 6) or 6,
            my_group=my_group,
            groups=group_rows,
            previous_groups=previous_groups,
        )

    @staticmethod
    async def reuse_previous_group(
        db: AsyncSession, student: User, assignment_id: uuid.UUID, payload: StudentGroupReuseIn
    ) -> StudentGroupRow:
        ctx = await StudentService.context_for_user(db, student)
        assignment = (
            await db.execute(
                select(Assignment).where(
                    Assignment.id == assignment_id,
                    Assignment.tenant_id == student.tenant_id,
                    Assignment.class_id == ctx.school_class.id,
                )
            )
        ).scalar_one_or_none()
        if assignment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        if (_value(assignment.status) or "") == AssignmentStatus.CLOSED.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This assignment is closed")
        if assignment.assignment_type != "GROUP":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This is not a group assignment")

        # Check if student is already in a group for this assignment
        existing_membership = (
            await db.execute(
                select(ProjectGroupMember)
                .join(ProjectGroup, ProjectGroup.id == ProjectGroupMember.group_id)
                .where(
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                    ProjectGroup.assignment_id == assignment.id,
                )
            )
        ).scalar_one_or_none()
        if existing_membership is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="You are already in a group for this assignment. Leave your current group first.",
            )

        prev_group = (
            await db.execute(
                select(ProjectGroup).where(
                    ProjectGroup.id == payload.previous_group_id,
                    ProjectGroup.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if prev_group is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Previous group not found")

        was_member = (
            await db.execute(
                select(ProjectGroupMember).where(
                    ProjectGroupMember.group_id == prev_group.id,
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if was_member is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You were not a member of that group")

        prev_member_ids = (
            await db.execute(
                select(ProjectGroupMember.student_id).where(
                    ProjectGroupMember.group_id == prev_group.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
            )
        ).scalars().all()

        base_name = prev_group.name.strip()
        new_name = base_name
        existing_names = set(
            (
                await db.execute(
                    select(func.lower(ProjectGroup.name)).where(
                        ProjectGroup.assignment_id == assignment.id,
                        ProjectGroup.tenant_id == student.tenant_id,
                    )
                )
            ).scalars().all()
        )
        suffix = 1
        while new_name.lower() in existing_names:
            suffix += 1
            new_name = f"{base_name} ({suffix})"

        new_group = ProjectGroup(
            id=uuid.uuid4(),
            tenant_id=student.tenant_id,
            assignment_id=assignment.id,
            name=new_name,
            created_by=student.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(new_group)
        await db.flush()

        db.add(
            ProjectGroupMember(
                id=uuid.uuid4(),
                tenant_id=student.tenant_id,
                group_id=new_group.id,
                student_id=student.id,
                joined_at=datetime.now(timezone.utc),
            )
        )

        already_grouped = set(
            (
                await db.execute(
                    select(ProjectGroupMember.student_id)
                    .join(ProjectGroup, ProjectGroup.id == ProjectGroupMember.group_id)
                    .where(
                        ProjectGroup.assignment_id == assignment.id,
                        ProjectGroup.tenant_id == student.tenant_id,
                    )
                )
            ).scalars().all()
        )

        max_size = getattr(assignment, "max_group_size", 6) or 6
        added_count = 1
        for member_id in prev_member_ids:
            if member_id == student.id:
                continue
            if member_id in already_grouped:
                continue
            if added_count >= max_size:
                break
            db.add(
                ProjectGroupMember(
                    id=uuid.uuid4(),
                    tenant_id=student.tenant_id,
                    group_id=new_group.id,
                    student_id=member_id,
                    joined_at=datetime.now(timezone.utc),
                )
            )
            added_count += 1

        await db.flush()
        AuditService.record(
            db,
            actor=student,
            actor_role="STUDENT",
            action="REUSE_PROJECT_GROUP",
            entity="ProjectGroup",
            entity_id=new_group.id,
            tenant_id=student.tenant_id,
            new_value={"name": new_group.name, "assignment_id": str(assignment.id), "from_group_id": str(prev_group.id)},
        )
        row = await StudentService._build_student_group_row(db, student.tenant_id, new_group.id, student.id)
        if row is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created group")
        return row

    @staticmethod
    async def create_group(
        db: AsyncSession, student: User, assignment_id: uuid.UUID, payload: StudentGroupCreate
    ) -> StudentGroupRow:
        ctx = await StudentService.context_for_user(db, student)
        assignment = (
            await db.execute(
                select(Assignment).where(
                    Assignment.id == assignment_id,
                    Assignment.tenant_id == student.tenant_id,
                    Assignment.class_id == ctx.school_class.id,
                )
            )
        ).scalar_one_or_none()
        if assignment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        if (_value(assignment.status) or "") == AssignmentStatus.CLOSED.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This assignment is closed")
        if assignment.assignment_type != "GROUP":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This is not a group assignment")

        clean_name = payload.name.strip()
        if not clean_name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Group name is required")

        # Check if student is already in a group for this assignment
        existing_membership = (
            await db.execute(
                select(ProjectGroupMember)
                .join(ProjectGroup, ProjectGroup.id == ProjectGroupMember.group_id)
                .where(
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                    ProjectGroup.assignment_id == assignment.id,
                )
            )
        ).scalar_one_or_none()
        if existing_membership is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="You are already in a group for this assignment. Leave your current group first.",
            )

        # Check if name is already taken for this assignment
        existing_name = (
            await db.execute(
                select(ProjectGroup).where(
                    ProjectGroup.assignment_id == assignment.id,
                    ProjectGroup.tenant_id == student.tenant_id,
                    func.lower(ProjectGroup.name) == clean_name.lower(),
                )
            )
        ).scalar_one_or_none()
        if existing_name is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"A group named '{clean_name}' already exists for this assignment",
            )

        group = ProjectGroup(
            id=uuid.uuid4(),
            tenant_id=student.tenant_id,
            assignment_id=assignment.id,
            name=clean_name,
            created_by=student.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(group)
        await db.flush()

        member = ProjectGroupMember(
            id=uuid.uuid4(),
            tenant_id=student.tenant_id,
            group_id=group.id,
            student_id=student.id,
            joined_at=datetime.now(timezone.utc),
        )
        db.add(member)
        await db.flush()

        AuditService.record(
            db,
            actor=student,
            actor_role="STUDENT",
            action="CREATE_PROJECT_GROUP",
            entity="ProjectGroup",
            entity_id=group.id,
            tenant_id=student.tenant_id,
            new_value={"name": group.name, "assignment_id": str(assignment.id)},
        )

        res = await StudentService._build_student_group_row(db, student.tenant_id, group.id, student.id)
        if res is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load created group")
        return res

    @staticmethod
    async def join_group(
        db: AsyncSession, student: User, assignment_id: uuid.UUID, group_id: uuid.UUID
    ) -> StudentGroupRow:
        ctx = await StudentService.context_for_user(db, student)
        assignment = (
            await db.execute(
                select(Assignment).where(
                    Assignment.id == assignment_id,
                    Assignment.tenant_id == student.tenant_id,
                    Assignment.class_id == ctx.school_class.id,
                )
            )
        ).scalar_one_or_none()
        if assignment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        if (_value(assignment.status) or "") == AssignmentStatus.CLOSED.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This assignment is closed")
        if assignment.assignment_type != "GROUP":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This is not a group assignment")

        # Check if student is already in a group for this assignment
        existing_membership = (
            await db.execute(
                select(ProjectGroupMember)
                .join(ProjectGroup, ProjectGroup.id == ProjectGroupMember.group_id)
                .where(
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                    ProjectGroup.assignment_id == assignment.id,
                )
            )
        ).scalar_one_or_none()
        if existing_membership is not None:
            if existing_membership.group_id == group_id:
                return (await StudentService._build_student_group_row(db, student.tenant_id, group_id, student.id)) or StudentGroupRow(
                    id=group_id, assignment_id=assignment_id, name="", created_at=datetime.now(timezone.utc)
                )
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="You must leave your current group before joining another group",
            )

        group = (
            await db.execute(
                select(ProjectGroup).where(
                    ProjectGroup.id == group_id,
                    ProjectGroup.assignment_id == assignment.id,
                    ProjectGroup.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if group is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Group not found")

        # Check member count limit
        max_size = getattr(assignment, "max_group_size", 6) or 6
        current_count = (
            await db.execute(
                select(func.count(ProjectGroupMember.id)).where(ProjectGroupMember.group_id == group.id)
            )
        ).scalar() or 0
        if current_count >= max_size:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"This group is full (maximum {max_size} members allowed)",
            )

        # Check if group already submitted
        has_sub = (
            await db.execute(
                select(Submission.id).where(
                    Submission.group_id == group.id,
                    Submission.assignment_id == assignment.id,
                    Submission.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if has_sub is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Cannot join a group that has already submitted the assignment",
            )

        member = ProjectGroupMember(
            id=uuid.uuid4(),
            tenant_id=student.tenant_id,
            group_id=group.id,
            student_id=student.id,
            joined_at=datetime.now(timezone.utc),
        )
        db.add(member)
        await db.flush()

        AuditService.record(
            db,
            actor=student,
            actor_role="STUDENT",
            action="JOIN_PROJECT_GROUP",
            entity="ProjectGroupMember",
            entity_id=member.id,
            tenant_id=student.tenant_id,
            new_value={"group_id": str(group.id), "assignment_id": str(assignment.id)},
        )

        res = await StudentService._build_student_group_row(db, student.tenant_id, group.id, student.id)
        if res is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load group")
        return res

    @staticmethod
    async def leave_group(db: AsyncSession, student: User, assignment_id: uuid.UUID) -> None:
        ctx = await StudentService.context_for_user(db, student)
        assignment = (
            await db.execute(
                select(Assignment).where(
                    Assignment.id == assignment_id,
                    Assignment.tenant_id == student.tenant_id,
                    Assignment.class_id == ctx.school_class.id,
                )
            )
        ).scalar_one_or_none()
        if assignment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        if (_value(assignment.status) or "") == AssignmentStatus.CLOSED.value:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This assignment is closed")

        member = (
            await db.execute(
                select(ProjectGroupMember, ProjectGroup)
                .join(ProjectGroup, ProjectGroup.id == ProjectGroupMember.group_id)
                .where(
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                    ProjectGroup.assignment_id == assignment.id,
                )
            )
        ).first()
        if member is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="You are not in a group for this assignment")

        group_member, group = member

        # Check if group already submitted
        has_sub = (
            await db.execute(
                select(Submission.id).where(
                    Submission.group_id == group.id,
                    Submission.assignment_id == assignment.id,
                    Submission.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if has_sub is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Cannot leave a group that has already submitted the assignment",
            )

        await db.delete(group_member)
        await db.flush()

        remaining_count = (
            await db.execute(
                select(func.count(ProjectGroupMember.id)).where(ProjectGroupMember.group_id == group.id)
            )
        ).scalar() or 0

        if remaining_count == 0:
            await db.delete(group)
            await db.flush()

        AuditService.record(
            db,
            actor=student,
            actor_role="STUDENT",
            action="LEAVE_PROJECT_GROUP",
            entity="ProjectGroupMember",
            entity_id=group_member.id,
            tenant_id=student.tenant_id,
            old_value={"group_id": str(group.id), "assignment_id": str(assignment.id)},
        )

    @staticmethod
    async def list_my_teams(db: AsyncSession, student: User) -> list[StudentMyTeamSummary]:
        ctx = await StudentService.context_for_user(db, student)

        memberships = (
            await db.execute(
                select(ProjectGroup, Assignment, Subject, User)
                .join(ProjectGroupMember, ProjectGroupMember.group_id == ProjectGroup.id)
                .join(Assignment, Assignment.id == ProjectGroup.assignment_id)
                .join(Subject, Subject.id == Assignment.subject_id)
                .outerjoin(User, and_(User.id == Assignment.teacher_id, User.tenant_id == student.tenant_id))
                .where(
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
                .order_by(Assignment.due_date.asc())
            )
        ).all()

        results: list[StudentMyTeamSummary] = []
        for group, assignment, subject, teacher in memberships:
            group_row = await StudentService._build_student_group_row(
                db, student.tenant_id, group.id, student.id
            )
            if not group_row:
                continue

            sub = (
                await db.execute(
                    select(Submission)
                    .where(
                        Submission.assignment_id == assignment.id,
                        Submission.tenant_id == student.tenant_id,
                        or_(
                            Submission.group_id == group.id,
                            Submission.student_id.in_([m.student_id for m in group_row.members] if group_row.members else [uuid.uuid4()]),
                        ),
                    )
                    .order_by(Submission.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            results.append(
                StudentMyTeamSummary(
                    group_id=group.id,
                    assignment_id=assignment.id,
                    group_name=group.name,
                    assignment_title=assignment.title,
                    subject_code=subject.code,
                    subject_name=subject.name,
                    teacher_name=teacher.name if teacher else None,
                    due_date=assignment.due_date,
                    is_leader=(group.created_by == student.id),
                    member_count=group_row.member_count,
                    min_group_size=getattr(assignment, "min_group_size", 2) or 2,
                    max_group_size=getattr(assignment, "max_group_size", 6) or 6,
                    is_submitted=sub is not None,
                    submission_status=_value(sub.status) if sub else None,
                    score=sub.score if sub else None,
                    total_marks=assignment.total_marks,
                    members=group_row.members,
                )
            )

        return results

    @staticmethod
    async def get_team_workspace(
        db: AsyncSession, student: User, group_id: uuid.UUID
    ) -> StudentMyTeamDetail:
        membership = (
            await db.execute(
                select(ProjectGroupMember).where(
                    ProjectGroupMember.group_id == group_id,
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team / Group not found or you are not a member")

        group_row = await StudentService._build_student_group_row(
            db, student.tenant_id, group_id, student.id
        )
        if group_row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Group not found")

        assignment_detail = await StudentService.assignment_detail(
            db, student, group_row.assignment_id
        )

        task_rows = (
            await db.execute(
                select(ProjectGroupTask, User)
                .outerjoin(User, and_(User.id == ProjectGroupTask.assigned_to, User.tenant_id == student.tenant_id))
                .where(
                    ProjectGroupTask.group_id == group_id,
                    ProjectGroupTask.tenant_id == student.tenant_id,
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

        msg_rows = (
            await db.execute(
                select(ProjectGroupMessage, User)
                .join(User, and_(User.id == ProjectGroupMessage.sender_id, User.tenant_id == student.tenant_id))
                .where(
                    ProjectGroupMessage.group_id == group_id,
                    ProjectGroupMessage.tenant_id == student.tenant_id,
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
                is_me=(msg.sender_id == student.id),
                message=msg.message,
                created_at=msg.created_at,
            )
            for msg, sender in msg_rows
        ]

        res_rows = (
            await db.execute(
                select(ProjectGroupResource, User)
                .outerjoin(User, and_(User.id == ProjectGroupResource.created_by, User.tenant_id == student.tenant_id))
                .where(
                    ProjectGroupResource.group_id == group_id,
                    ProjectGroupResource.tenant_id == student.tenant_id,
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

        # Pending Invitations for this team
        invite_rows = (
            await db.execute(
                select(ProjectGroupInvitation, User, Enrollment, ProjectGroup, Assignment, Subject)
                .join(User, and_(User.id == ProjectGroupInvitation.student_id, User.tenant_id == student.tenant_id))
                .outerjoin(
                    Enrollment,
                    and_(
                        Enrollment.student_id == ProjectGroupInvitation.student_id,
                        Enrollment.tenant_id == student.tenant_id,
                    ),
                )
                .join(ProjectGroup, ProjectGroup.id == ProjectGroupInvitation.group_id)
                .join(Assignment, Assignment.id == ProjectGroup.assignment_id)
                .join(Subject, Subject.id == Assignment.subject_id)
                .where(
                    ProjectGroupInvitation.group_id == group_id,
                    ProjectGroupInvitation.tenant_id == student.tenant_id,
                    ProjectGroupInvitation.status == "PENDING",
                )
                .order_by(ProjectGroupInvitation.created_at.desc())
            )
        ).all()

        invitations = [
            StudentGroupInviteOut(
                id=inv.id,
                group_id=inv.group_id,
                group_name=grp.name,
                assignment_id=asgn.id,
                assignment_title=asgn.title,
                subject_name=subj.name,
                student_id=target_user.id,
                student_name=target_user.name,
                student_roll_number=enroll.roll_number if enroll and enroll.roll_number else target_user.student_roll_no,
                invited_by=inv.invited_by,
                inviter_name=student.name,
                status=inv.status,
                created_at=inv.created_at,
            )
            for inv, target_user, enroll, grp, asgn, subj in invite_rows
        ]

        return StudentMyTeamDetail(
            group=group_row,
            assignment=assignment_detail,
            tasks=tasks,
            messages=messages,
            resources=resources,
            pending_invitations=invitations,
        )

    @staticmethod
    async def create_team_task(
        db: AsyncSession, student: User, group_id: uuid.UUID, payload: StudentGroupTaskIn
    ) -> StudentGroupTaskOut:
        membership = (
            await db.execute(
                select(ProjectGroupMember).where(
                    ProjectGroupMember.group_id == group_id,
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You are not a member of this team")

        task = ProjectGroupTask(
            id=uuid.uuid4(),
            tenant_id=student.tenant_id,
            group_id=group_id,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else None,
            assigned_to=payload.assigned_to,
            status="TODO",
            due_date=payload.due_date,
            created_by=student.id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(task)
        await db.flush()

        assignee_name: str | None = None
        if task.assigned_to:
            assignee = (
                await db.execute(select(User.name).where(User.id == task.assigned_to))
            ).scalar_one_or_none()
            assignee_name = assignee

        return StudentGroupTaskOut(
            id=task.id,
            group_id=task.group_id,
            title=task.title,
            description=task.description,
            assigned_to=task.assigned_to,
            assignee_name=assignee_name,
            status=task.status,
            due_date=task.due_date,
            created_by=task.created_by,
            creator_name=student.name,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    @staticmethod
    async def update_team_task(
        db: AsyncSession, student: User, group_id: uuid.UUID, task_id: uuid.UUID, payload: StudentGroupTaskUpdateIn
    ) -> StudentGroupTaskOut:
        membership = (
            await db.execute(
                select(ProjectGroupMember).where(
                    ProjectGroupMember.group_id == group_id,
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You are not a member of this team")

        task = (
            await db.execute(
                select(ProjectGroupTask).where(
                    ProjectGroupTask.id == task_id,
                    ProjectGroupTask.group_id == group_id,
                    ProjectGroupTask.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if task is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")

        if payload.title is not None:
            task.title = payload.title.strip()
        if payload.description is not None:
            task.description = payload.description.strip() if payload.description else None
        if payload.assigned_to is not None:
            task.assigned_to = payload.assigned_to
        if payload.status is not None:
            task.status = payload.status
        if payload.due_date is not None:
            task.due_date = payload.due_date
        task.updated_at = datetime.now(timezone.utc)
        await db.flush()

        assignee_name: str | None = None
        if task.assigned_to:
            assignee = (
                await db.execute(select(User.name).where(User.id == task.assigned_to))
            ).scalar_one_or_none()
            assignee_name = assignee

        return StudentGroupTaskOut(
            id=task.id,
            group_id=task.group_id,
            title=task.title,
            description=task.description,
            assigned_to=task.assigned_to,
            assignee_name=assignee_name,
            status=task.status,
            due_date=task.due_date,
            created_by=task.created_by,
            creator_name=None,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    @staticmethod
    async def delete_team_task(
        db: AsyncSession, student: User, group_id: uuid.UUID, task_id: uuid.UUID
    ) -> None:
        membership = (
            await db.execute(
                select(ProjectGroupMember).where(
                    ProjectGroupMember.group_id == group_id,
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You are not a member of this team")

        task = (
            await db.execute(
                select(ProjectGroupTask).where(
                    ProjectGroupTask.id == task_id,
                    ProjectGroupTask.group_id == group_id,
                    ProjectGroupTask.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if task is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")

        await db.delete(task)
        await db.flush()

    @staticmethod
    async def post_team_message(
        db: AsyncSession, student: User, group_id: uuid.UUID, payload: StudentGroupMessageIn
    ) -> StudentGroupMessageOut:
        membership = (
            await db.execute(
                select(ProjectGroupMember).where(
                    ProjectGroupMember.group_id == group_id,
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You are not a member of this team")

        msg = ProjectGroupMessage(
            id=uuid.uuid4(),
            tenant_id=student.tenant_id,
            group_id=group_id,
            sender_id=student.id,
            message=payload.message.strip(),
            created_at=datetime.now(timezone.utc),
        )
        db.add(msg)
        await db.flush()

        return StudentGroupMessageOut(
            id=msg.id,
            group_id=msg.group_id,
            sender_id=msg.sender_id,
            sender_name=student.name,
            is_me=True,
            message=msg.message,
            created_at=msg.created_at,
        )

    @staticmethod
    async def add_team_resource(
        db: AsyncSession, student: User, group_id: uuid.UUID, payload: StudentGroupResourceIn
    ) -> StudentGroupResourceOut:
        membership = (
            await db.execute(
                select(ProjectGroupMember).where(
                    ProjectGroupMember.group_id == group_id,
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You are not a member of this team")

        resource = ProjectGroupResource(
            id=uuid.uuid4(),
            tenant_id=student.tenant_id,
            group_id=group_id,
            title=payload.title.strip(),
            url=payload.url.strip(),
            resource_type=payload.resource_type.upper() if payload.resource_type else "LINK",
            created_by=student.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(resource)
        await db.flush()

        return StudentGroupResourceOut(
            id=resource.id,
            group_id=resource.group_id,
            title=resource.title,
            url=resource.url,
            resource_type=resource.resource_type,
            created_by=resource.created_by,
            creator_name=student.name,
            created_at=resource.created_at,
        )

    @staticmethod
    async def delete_team_resource(
        db: AsyncSession, student: User, group_id: uuid.UUID, resource_id: uuid.UUID
    ) -> None:
        membership = (
            await db.execute(
                select(ProjectGroupMember).where(
                    ProjectGroupMember.group_id == group_id,
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You are not a member of this team")

        resource = (
            await db.execute(
                select(ProjectGroupResource).where(
                    ProjectGroupResource.id == resource_id,
                    ProjectGroupResource.group_id == group_id,
                    ProjectGroupResource.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if resource is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resource not found")

        await db.delete(resource)
        await db.flush()

    @staticmethod
    async def list_eligible_classmates_to_invite(
        db: AsyncSession, student: User, group_id: uuid.UUID
    ) -> list[StudentEligibleClassmateOut]:
        group = (
            await db.execute(
                select(ProjectGroup).where(
                    ProjectGroup.id == group_id,
                    ProjectGroup.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if not group:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Group not found")

        assignment = (
            await db.execute(
                select(Assignment).where(
                    Assignment.id == group.assignment_id,
                    Assignment.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if not assignment:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")

        # Students enrolled in this class
        enrolled_students = (
            await db.execute(
                select(User, Enrollment)
                .join(Enrollment, and_(Enrollment.student_id == User.id, Enrollment.tenant_id == student.tenant_id))
                .where(
                    Enrollment.class_id == assignment.class_id,
                    Enrollment.status == "ACTIVE",
                    User.tenant_id == student.tenant_id,
                    User.id != student.id,
                )
                .order_by(User.name.asc())
            )
        ).all()

        # Students already in any group for this assignment
        grouped_student_ids = set(
            (
                await db.execute(
                    select(ProjectGroupMember.student_id)
                    .join(ProjectGroup, ProjectGroup.id == ProjectGroupMember.group_id)
                    .where(
                        ProjectGroup.assignment_id == assignment.id,
                        ProjectGroupMember.tenant_id == student.tenant_id,
                    )
                )
            ).scalars().all()
        )

        # Students with pending invites for THIS group
        invited_student_ids = set(
            (
                await db.execute(
                    select(ProjectGroupInvitation.student_id).where(
                        ProjectGroupInvitation.group_id == group_id,
                        ProjectGroupInvitation.tenant_id == student.tenant_id,
                        ProjectGroupInvitation.status == "PENDING",
                    )
                )
            ).scalars().all()
        )

        results: list[StudentEligibleClassmateOut] = []
        for user, enrollment in enrolled_students:
            results.append(
                StudentEligibleClassmateOut(
                    student_id=user.id,
                    student_name=user.name,
                    roll_number=enrollment.roll_number if enrollment and enrollment.roll_number else user.student_roll_no,
                    already_in_group=(user.id in grouped_student_ids),
                    has_pending_invite=(user.id in invited_student_ids),
                )
            )
        return results

    @staticmethod
    async def invite_team_member(
        db: AsyncSession, student: User, group_id: uuid.UUID, payload: StudentGroupInviteIn
    ) -> StudentGroupInviteOut:
        group = (
            await db.execute(
                select(ProjectGroup).where(
                    ProjectGroup.id == group_id,
                    ProjectGroup.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if not group:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Group not found")

        if group.created_by != student.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the team leader can invite members")

        assignment_row = (
            await db.execute(
                select(Assignment, Subject)
                .join(Subject, Subject.id == Assignment.subject_id)
                .where(
                    Assignment.id == group.assignment_id,
                    Assignment.tenant_id == student.tenant_id,
                )
            )
        ).first()
        if not assignment_row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        asgn, subj = assignment_row

        # Check max group size
        current_member_count = (
            await db.execute(
                select(func.count(ProjectGroupMember.id)).where(
                    ProjectGroupMember.group_id == group_id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
            )
        ).scalar() or 0

        max_size = getattr(asgn, "max_group_size", 6) or 6
        if current_member_count >= max_size:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Team is already full (maximum {max_size} members)")

        # Target student
        target_row = (
            await db.execute(
                select(User, Enrollment)
                .outerjoin(
                    Enrollment,
                    and_(
                        Enrollment.student_id == User.id,
                        Enrollment.tenant_id == student.tenant_id,
                        Enrollment.class_id == asgn.class_id,
                    ),
                )
                .where(
                    User.id == payload.student_id,
                    User.tenant_id == student.tenant_id,
                )
            )
        ).first()
        if not target_row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found in this class")
        t_user, t_enroll = target_row

        # Check if already in ANY group for this assignment
        existing_group_member = (
            await db.execute(
                select(ProjectGroupMember)
                .join(ProjectGroup, ProjectGroup.id == ProjectGroupMember.group_id)
                .where(
                    ProjectGroup.assignment_id == asgn.id,
                    ProjectGroupMember.student_id == payload.student_id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if existing_group_member:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This student is already a member of a team for this project")

        # Check if already invited
        existing_invite = (
            await db.execute(
                select(ProjectGroupInvitation).where(
                    ProjectGroupInvitation.group_id == group_id,
                    ProjectGroupInvitation.student_id == payload.student_id,
                    ProjectGroupInvitation.tenant_id == student.tenant_id,
                    ProjectGroupInvitation.status == "PENDING",
                )
            )
        ).scalar_one_or_none()
        if existing_invite:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="An invitation is already pending for this student")

        invitation = ProjectGroupInvitation(
            tenant_id=student.tenant_id,
            group_id=group_id,
            student_id=payload.student_id,
            invited_by=student.id,
            status="PENDING",
        )
        db.add(invitation)
        await db.commit()
        await db.refresh(invitation)

        return StudentGroupInviteOut(
            id=invitation.id,
            group_id=group.id,
            group_name=group.name,
            assignment_id=asgn.id,
            assignment_title=asgn.title,
            subject_name=subj.name,
            student_id=t_user.id,
            student_name=t_user.name,
            student_roll_number=t_enroll.roll_number if t_enroll and t_enroll.roll_number else t_user.student_roll_no,
            invited_by=student.id,
            inviter_name=student.name,
            status=invitation.status,
            created_at=invitation.created_at,
        )

    @staticmethod
    async def cancel_team_invitation(
        db: AsyncSession, student: User, group_id: uuid.UUID, invite_id: uuid.UUID
    ) -> None:
        group = (
            await db.execute(
                select(ProjectGroup).where(
                    ProjectGroup.id == group_id,
                    ProjectGroup.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if not group:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Group not found")

        if group.created_by != student.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the team leader can cancel invitations")

        invite = (
            await db.execute(
                select(ProjectGroupInvitation).where(
                    ProjectGroupInvitation.id == invite_id,
                    ProjectGroupInvitation.group_id == group_id,
                    ProjectGroupInvitation.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if not invite:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invitation not found")

        invite.status = "CANCELLED"
        invite.responded_at = datetime.now(timezone.utc)
        await db.commit()

    @staticmethod
    async def list_my_team_invitations(
        db: AsyncSession, student: User
    ) -> list[StudentGroupInviteOut]:
        invitations_raw = (
            await db.execute(
                select(ProjectGroupInvitation, ProjectGroup, Assignment, Subject, User)
                .join(ProjectGroup, ProjectGroup.id == ProjectGroupInvitation.group_id)
                .join(Assignment, Assignment.id == ProjectGroup.assignment_id)
                .join(Subject, Subject.id == Assignment.subject_id)
                .join(User, and_(User.id == ProjectGroupInvitation.invited_by, User.tenant_id == student.tenant_id))
                .where(
                    ProjectGroupInvitation.student_id == student.id,
                    ProjectGroupInvitation.tenant_id == student.tenant_id,
                    ProjectGroupInvitation.status == "PENDING",
                )
                .order_by(ProjectGroupInvitation.created_at.desc())
            )
        ).all()

        results: list[StudentGroupInviteOut] = []
        for inv, grp, asgn, subj, inviter in invitations_raw:
            results.append(
                StudentGroupInviteOut(
                    id=inv.id,
                    group_id=grp.id,
                    group_name=grp.name,
                    assignment_id=asgn.id,
                    assignment_title=asgn.title,
                    subject_name=subj.name,
                    student_id=student.id,
                    student_name=student.name,
                    student_roll_number=student.student_roll_no,
                    invited_by=inviter.id,
                    inviter_name=inviter.name,
                    status=inv.status,
                    created_at=inv.created_at,
                )
            )
        return results

    @staticmethod
    async def respond_to_team_invitation(
        db: AsyncSession, student: User, invite_id: uuid.UUID, payload: StudentGroupInviteResponseIn
    ) -> str:
        invite = (
            await db.execute(
                select(ProjectGroupInvitation, ProjectGroup, Assignment)
                .join(ProjectGroup, ProjectGroup.id == ProjectGroupInvitation.group_id)
                .join(Assignment, Assignment.id == ProjectGroup.assignment_id)
                .where(
                    ProjectGroupInvitation.id == invite_id,
                    ProjectGroupInvitation.student_id == student.id,
                    ProjectGroupInvitation.tenant_id == student.tenant_id,
                    ProjectGroupInvitation.status == "PENDING",
                )
            )
        ).first()
        if not invite:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invitation not found or already processed")

        invitation, group, assignment = invite

        if payload.action == "REJECT":
            invitation.status = "REJECTED"
            invitation.responded_at = datetime.now(timezone.utc)
            await db.commit()
            return "Invitation declined"

        # Action is ACCEPT
        # Check current member count
        member_count = (
            await db.execute(
                select(func.count(ProjectGroupMember.id)).where(
                    ProjectGroupMember.group_id == group.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
            )
        ).scalar() or 0

        max_size = getattr(assignment, "max_group_size", 6) or 6
        if member_count >= max_size:
            invitation.status = "CANCELLED"
            invitation.responded_at = datetime.now(timezone.utc)
            await db.commit()
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This team has already reached its maximum capacity")

        # Check if student is already in another group for this assignment
        existing_membership = (
            await db.execute(
                select(ProjectGroupMember)
                .join(ProjectGroup, ProjectGroup.id == ProjectGroupMember.group_id)
                .where(
                    ProjectGroup.assignment_id == assignment.id,
                    ProjectGroupMember.student_id == student.id,
                    ProjectGroupMember.tenant_id == student.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if existing_membership:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="You are already in a team for this project. Please leave your current team first.",
            )

        # Add member to group
        new_member = ProjectGroupMember(
            tenant_id=student.tenant_id,
            group_id=group.id,
            student_id=student.id,
        )
        db.add(new_member)
        invitation.status = "ACCEPTED"
        invitation.responded_at = datetime.now(timezone.utc)

        # Cancel any other pending invitations for this student on this assignment
        other_invites = (
            await db.execute(
                select(ProjectGroupInvitation)
                .join(ProjectGroup, ProjectGroup.id == ProjectGroupInvitation.group_id)
                .where(
                    ProjectGroup.assignment_id == assignment.id,
                    ProjectGroupInvitation.student_id == student.id,
                    ProjectGroupInvitation.tenant_id == student.tenant_id,
                    ProjectGroupInvitation.status == "PENDING",
                    ProjectGroupInvitation.id != invitation.id,
                )
            )
        ).scalars().all()

        for oi in other_invites:
            oi.status = "CANCELLED"
            oi.responded_at = datetime.now(timezone.utc)

        await db.commit()
        return "Joined team successfully"

    # ── C-ST-13 / C-ST-14 content ───────────────────────────────────────────

    @staticmethod
    async def content(
        db: AsyncSession,
        student: User,
        *,
        subject_id: uuid.UUID | None = None,
        chapter: str | None = None,
        content_type: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StudentContentPage:
        StudentService._validate_page(limit, offset)
        ctx = await StudentService.context_for_user(db, student)
        tenant_id = student.tenant_id
        clauses = [
            ContentItem.tenant_id == tenant_id,
            ContentItem.class_id == ctx.school_class.id,
            ContentItem.is_visible.is_(True),
            ContentItem.deleted_at.is_(None),
        ]
        if subject_id is not None:
            clauses.append(ContentItem.subject_id == subject_id)
        if chapter and chapter.strip():
            clauses.append(func.lower(ContentItem.chapter) == chapter.strip().lower())
        if content_type and content_type.strip().upper() != "ALL":
            wanted = content_type.strip().upper()
            if wanted not in ContentKind.__members__:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown content type")
            clauses.append(ContentItem.content_type == ContentKind[wanted])
        if query and query.strip():
            needle = f"%{query.strip().lower()}%"
            clauses.append(func.lower(ContentItem.title).like(needle))
        total = (await db.execute(select(func.count(ContentItem.id)).where(*clauses))).scalar() or 0
        rows = (
            await db.execute(
                select(ContentItem, Subject, User)
                .join(Subject, Subject.id == ContentItem.subject_id)
                .outerjoin(User, and_(User.id == ContentItem.uploaded_by, User.tenant_id == tenant_id))
                .where(*clauses)
                .order_by(ContentItem.chapter, ContentItem.sort_order, ContentItem.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        chapter_rows = (
            await db.execute(
                select(func.distinct(ContentItem.chapter)).where(
                    ContentItem.tenant_id == tenant_id,
                    ContentItem.class_id == ctx.school_class.id,
                    ContentItem.is_visible.is_(True),
                    ContentItem.deleted_at.is_(None),
                    ContentItem.chapter.is_not(None),
                )
            )
        ).scalars().all()
        tags = await StudentService._content_tags(db, [item.id for item, _s, _u in rows])
        return StudentContentPage(
            total=int(total),
            limit=limit,
            offset=offset,
            chapters=sorted(chapter for chapter in chapter_rows if chapter),
            items=[
                StudentService._content_row(item, subject, uploader, tags.get(item.id, []))
                for item, subject, uploader in rows
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
    def _content_row(item: ContentItem, subject: Subject, uploader: User | None, tags: list[str]) -> StudentContentRow:
        return StudentContentRow(
            id=item.id,
            title=item.title,
            description=item.description,
            subject_id=item.subject_id,
            subject_code=subject.code,
            subject_name=subject.name,
            uploader_name=uploader.name if uploader else None,
            content_type=_value(item.content_type) or "PDF",
            file_key=item.file_key,
            external_url=item.external_url,
            file_size_bytes=item.file_size_bytes,
            duration_seconds=item.duration_seconds,
            chapter=item.chapter,
            tags=tags,
            view_count=item.view_count,
            download_count=item.download_count,
            created_at=item.created_at,
        )

    @staticmethod
    async def content_detail(db: AsyncSession, student: User, content_id: uuid.UUID) -> StudentContentRow:
        ctx = await StudentService.context_for_user(db, student)
        row = (
            await db.execute(
                select(ContentItem, Subject, User)
                .join(Subject, Subject.id == ContentItem.subject_id)
                .outerjoin(User, and_(User.id == ContentItem.uploaded_by, User.tenant_id == student.tenant_id))
                .where(
                    ContentItem.id == content_id,
                    ContentItem.tenant_id == student.tenant_id,
                    ContentItem.class_id == ctx.school_class.id,
                    ContentItem.is_visible.is_(True),
                    ContentItem.deleted_at.is_(None),
                )
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Content not found")
        item, subject, uploader = row
        item.view_count = (item.view_count or 0) + 1
        db.add(ContentAccessLog(id=uuid.uuid4(), content_id=item.id, user_id=student.id, action="VIEW"))
        await db.flush()
        tags = await StudentService._content_tags(db, [item.id])
        return StudentService._content_row(item, subject, uploader, tags.get(item.id, []))

    # ── C-ST-15 … C-ST-17 results & grade cards ─────────────────────────────

    @staticmethod
    async def results(db: AsyncSession, student: User) -> list[StudentResultRow]:
        await StudentService.context_for_user(db, student)
        rows = (
            await db.execute(
                select(StudentResult, ResultPublication, AcademicYear, SchoolClass)
                .join(ResultPublication, ResultPublication.id == StudentResult.publication_id)
                .outerjoin(
                    AcademicYear,
                    and_(
                        AcademicYear.id == ResultPublication.academic_year_id,
                        AcademicYear.tenant_id == student.tenant_id,
                    ),
                )
                .outerjoin(
                    SchoolClass,
                    and_(SchoolClass.id == StudentResult.class_id, SchoolClass.tenant_id == student.tenant_id),
                )
                .where(
                    StudentResult.tenant_id == student.tenant_id,
                    StudentResult.student_id == student.id,
                    ResultPublication.tenant_id == student.tenant_id,
                    ResultPublication.is_visible_to_students.is_(True),
                    ResultPublication.approval_status == "APPROVED",
                )
                .order_by(ResultPublication.published_at.desc())
            )
        ).all()
        cards = await StudentService._grade_cards_by_publication(db, student)
        return [
            StudentResultRow(
                publication_id=publication.id,
                title=publication.title,
                academic_year=year.name if year else None,
                class_name=school_class.name if school_class else None,
                published_at=publication.published_at,
                total_marks_obtained=float(result.total_marks_obtained),
                total_marks_possible=float(result.total_marks_possible),
                percentage=float(result.percentage),
                grade=result.grade,
                rank=result.rank,
                result=_value(result.result) or "PASS",
                has_grade_card=publication.id in cards,
            )
            for result, publication, year, school_class in rows
        ]

    @staticmethod
    async def _grade_cards_by_publication(db: AsyncSession, student: User) -> dict[uuid.UUID, ExamControllerGradeCard]:
        rows = (
            await db.execute(
                select(ExamControllerGradeCard).where(
                    ExamControllerGradeCard.tenant_id == student.tenant_id,
                    ExamControllerGradeCard.student_id == student.id,
                    ExamControllerGradeCard.status == ExamControllerGradeCardStatus.PUBLISHED,
                )
            )
        ).scalars().all()
        return {card.publication_id: card for card in rows}

    @staticmethod
    async def result_detail(db: AsyncSession, student: User, publication_id: uuid.UUID) -> StudentResultDetail:
        await StudentService.context_for_user(db, student)
        row = (
            await db.execute(
                select(StudentResult, ResultPublication, AcademicYear, SchoolClass)
                .join(ResultPublication, ResultPublication.id == StudentResult.publication_id)
                .outerjoin(
                    AcademicYear,
                    and_(
                        AcademicYear.id == ResultPublication.academic_year_id,
                        AcademicYear.tenant_id == student.tenant_id,
                    ),
                )
                .outerjoin(
                    SchoolClass,
                    and_(SchoolClass.id == StudentResult.class_id, SchoolClass.tenant_id == student.tenant_id),
                )
                .where(
                    StudentResult.tenant_id == student.tenant_id,
                    StudentResult.student_id == student.id,
                    StudentResult.publication_id == publication_id,
                    ResultPublication.is_visible_to_students.is_(True),
                    ResultPublication.approval_status == "APPROVED",
                )
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Result not found")
        result, publication, year, school_class = row
        tenant_name = (
            await db.execute(select(Tenant.name).where(Tenant.id == student.tenant_id))
        ).scalar_one_or_none()
        raw_scores = result.subject_scores if isinstance(result.subject_scores, list) else []
        subject_scores = [
            StudentSubjectScore(
                subject_name=str(score.get("subject_name") or score.get("subject") or "Subject"),
                marks_obtained=float(score.get("marks_obtained") or score.get("marks") or 0),
                marks_possible=float(score.get("marks_possible") or score.get("max_marks") or 0),
                grade=score.get("grade"),
            )
            for score in raw_scores
            if isinstance(score, dict)
        ]
        cards = await StudentService._grade_cards_by_publication(db, student)
        return StudentResultDetail(
            publication_id=publication.id,
            title=publication.title,
            academic_year=year.name if year else None,
            class_name=school_class.name if school_class else None,
            published_at=publication.published_at,
            total_marks_obtained=float(result.total_marks_obtained),
            total_marks_possible=float(result.total_marks_possible),
            percentage=float(result.percentage),
            grade=result.grade,
            rank=result.rank,
            result=_value(result.result) or "PASS",
            has_grade_card=publication.id in cards,
            subject_scores=subject_scores,
            remarks=result.remarks,
            institution_name=tenant_name,
        )

    # ── C-ST-18 notices ─────────────────────────────────────────────────────

    @staticmethod
    async def _notice_page(
        db: AsyncSession,
        student: User,
        ctx: StudentContext,
        *,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StudentNoticePage:
        now = datetime.now(timezone.utc)
        visible = or_(
            Notice.target_scope == NoticeScope.INSTITUTION,
            and_(
                Notice.target_scope == NoticeScope.DEPARTMENT,
                Notice.target_id == (ctx.department.id if ctx.department else None),
            ),
            and_(Notice.target_scope == NoticeScope.CLASS, Notice.target_id == ctx.school_class.id),
        )
        clauses = [
            Notice.tenant_id == student.tenant_id,
            Notice.deleted_at.is_(None),
            or_(Notice.expires_at.is_(None), Notice.expires_at > now),
            visible,
        ]
        if ctx.department is None:
            clauses[-1] = or_(
                Notice.target_scope == NoticeScope.INSTITUTION,
                and_(Notice.target_scope == NoticeScope.CLASS, Notice.target_id == ctx.school_class.id),
            )
        if query and query.strip():
            needle = f"%{query.strip().lower()}%"
            clauses.append(or_(func.lower(Notice.title).like(needle), func.lower(Notice.body).like(needle)))
        total = (await db.execute(select(func.count(Notice.id)).where(*clauses))).scalar() or 0
        rows = (
            await db.execute(
                select(Notice, User.name, NoticeRead.id)
                .outerjoin(User, and_(User.id == Notice.author_id, User.tenant_id == student.tenant_id))
                .outerjoin(
                    NoticeRead,
                    and_(NoticeRead.notice_id == Notice.id, NoticeRead.user_id == student.id),
                )
                .where(*clauses)
                .order_by(Notice.is_pinned.desc(), Notice.published_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        unread = (
            await db.execute(
                select(func.count(Notice.id))
                .outerjoin(
                    NoticeRead,
                    and_(NoticeRead.notice_id == Notice.id, NoticeRead.user_id == student.id),
                )
                .where(*clauses, NoticeRead.id.is_(None))
            )
        ).scalar() or 0
        target_names = await StudentService._notice_target_names(db, student.tenant_id, ctx, [n for n, _a, _r in rows])
        return StudentNoticePage(
            total=int(total),
            limit=limit,
            offset=offset,
            unread_count=int(unread),
            items=[
                StudentNoticeRow(
                    id=notice.id,
                    title=notice.title,
                    body=notice.body,
                    author_name=author_name,
                    target_scope=_value(notice.target_scope) or "INSTITUTION",
                    target_name=target_names.get((_value(notice.target_scope) or "INSTITUTION", notice.target_id)),
                    priority=_value(notice.priority) or "NORMAL",
                    is_pinned=notice.is_pinned,
                    published_at=notice.published_at,
                    expires_at=notice.expires_at,
                    is_read=read_id is not None,
                )
                for notice, author_name, read_id in rows
            ],
        )

    @staticmethod
    async def _notice_target_names(
        db: AsyncSession, tenant_id: uuid.UUID, ctx: StudentContext, notices: list[Notice]
    ) -> dict[tuple[str, uuid.UUID | None], str | None]:
        return {
            ("INSTITUTION", None): "Institution-wide",
            ("DEPARTMENT", ctx.department.id if ctx.department else None): ctx.department.name if ctx.department else None,
            ("CLASS", ctx.school_class.id): ctx.school_class.name,
        }

    @staticmethod
    async def notices(
        db: AsyncSession,
        student: User,
        *,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StudentNoticePage:
        StudentService._validate_page(limit, offset)
        ctx = await StudentService.context_for_user(db, student)
        return await StudentService._notice_page(db, student, ctx, query=query, limit=limit, offset=offset)

    @staticmethod
    async def mark_notice_read(db: AsyncSession, student: User, notice_id: uuid.UUID) -> StudentNoticeRow:
        ctx = await StudentService.context_for_user(db, student)
        page = await StudentService._notice_page(db, student, ctx, limit=100, offset=0)
        hits = await db.execute(
            select(Notice, User.name).outerjoin(
                User, and_(User.id == Notice.author_id, User.tenant_id == student.tenant_id)
            ).where(Notice.id == notice_id, Notice.tenant_id == student.tenant_id, Notice.deleted_at.is_(None))
        )
        row = hits.first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Notice not found")
        notice, author_name = row
        scope_value = _value(notice.target_scope) or "INSTITUTION"
        allowed = (
            scope_value == "INSTITUTION"
            or (scope_value == "CLASS" and notice.target_id == ctx.school_class.id)
            or (scope_value == "DEPARTMENT" and ctx.department is not None and notice.target_id == ctx.department.id)
        )
        if not allowed:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Notice not found")
        existing = (
            await db.execute(
                select(NoticeRead).where(NoticeRead.notice_id == notice.id, NoticeRead.user_id == student.id)
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(NoticeRead(id=uuid.uuid4(), notice_id=notice.id, user_id=student.id))
            await db.flush()
        target_names = await StudentService._notice_target_names(db, student.tenant_id, ctx, [notice])
        del page
        return StudentNoticeRow(
            id=notice.id,
            title=notice.title,
            body=notice.body,
            author_name=author_name,
            target_scope=scope_value,
            target_name=target_names.get((scope_value, notice.target_id)),
            priority=_value(notice.priority) or "NORMAL",
            is_pinned=notice.is_pinned,
            published_at=notice.published_at,
            expires_at=notice.expires_at,
            is_read=True,
        )

    # ── C-ST-19 discussion ──────────────────────────────────────────────────

    @staticmethod
    async def discussion_scopes(db: AsyncSession, student: User) -> list[StudentDiscussionScope]:
        ctx = await StudentService.context_for_user(db, student)
        scopes = [StudentDiscussionScope(scope_type="CLASS", scope_id=ctx.school_class.id, name=ctx.school_class.name)]
        subjects = (
            await db.execute(
                select(Subject).where(
                    Subject.tenant_id == student.tenant_id,
                    Subject.class_id == ctx.school_class.id,
                    Subject.is_active.is_(True),
                ).order_by(Subject.code)
            )
        ).scalars().all()
        scopes.extend(
            StudentDiscussionScope(scope_type="SUBJECT", scope_id=subject.id, name=f"{subject.code} · {subject.name}")
            for subject in subjects
        )
        return scopes

    @staticmethod
    def _visibility(ctx: StudentContext):
        return or_(
            and_(func.upper(DiscussionThread.scope_type) == "CLASS", DiscussionThread.scope_id == ctx.school_class.id),
            *(
                [
                    and_(
                        func.upper(DiscussionThread.scope_type) == "DEPARTMENT",
                        DiscussionThread.scope_id == ctx.department.id,
                    )
                ]
                if ctx.department
                else []
            ),
            and_(
                func.upper(DiscussionThread.scope_type) == "SUBJECT",
                DiscussionThread.scope_id.in_(
                    select(Subject.id).where(
                        Subject.tenant_id == ctx.enrollment.tenant_id,
                        Subject.class_id == ctx.school_class.id,
                    )
                ),
            ),
        )

    @staticmethod
    async def discussion(
        db: AsyncSession,
        student: User,
        *,
        scope_id: uuid.UUID | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StudentThreadPage:
        StudentService._validate_page(limit, offset)
        ctx = await StudentService.context_for_user(db, student)
        clauses = [
            DiscussionThread.tenant_id == student.tenant_id,
            DiscussionThread.deleted_at.is_(None),
            StudentService._visibility(ctx),
        ]
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
                .outerjoin(User, and_(User.id == DiscussionThread.author_id, User.tenant_id == student.tenant_id))
                .where(*clauses)
                .order_by(DiscussionThread.is_pinned.desc(), DiscussionThread.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        my_votes = await StudentService._my_votes(db, student, "THREAD", [thread.id for thread, _n in rows])
        names = await StudentService._thread_scope_names(db, student, ctx, [thread for thread, _n in rows])
        return StudentThreadPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[
                StudentService._thread_row(thread, author_name, student, my_votes, names)
                for thread, author_name in rows
            ],
        )

    @staticmethod
    async def _my_votes(
        db: AsyncSession, student: User, target_type: str, target_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not target_ids:
            return set()
        rows = (
            await db.execute(
                select(DiscussionVote.target_id).where(
                    DiscussionVote.user_id == student.id,
                    DiscussionVote.target_type == target_type,
                    DiscussionVote.target_id.in_(target_ids),
                )
            )
        ).scalars().all()
        return set(rows)

    @staticmethod
    async def _thread_scope_names(
        db: AsyncSession, student: User, ctx: StudentContext, threads: list[DiscussionThread]
    ) -> dict[tuple[str, uuid.UUID], str | None]:
        names: dict[tuple[str, uuid.UUID], str | None] = {
            ("CLASS", ctx.school_class.id): ctx.school_class.name,
        }
        if ctx.department:
            names[("DEPARTMENT", ctx.department.id)] = ctx.department.name
        subject_ids = {t.scope_id for t in threads if (t.scope_type or "").upper() == "SUBJECT"}
        if subject_ids:
            rows = await db.execute(
                select(Subject.id, Subject.code, Subject.name).where(
                    Subject.tenant_id == student.tenant_id, Subject.id.in_(subject_ids)
                )
            )
            names.update({("SUBJECT", row[0]): f"{row[1]} · {row[2]}" for row in rows.all()})
        return names

    @staticmethod
    def _thread_row(
        thread: DiscussionThread,
        author_name: str | None,
        student: User,
        my_votes: set[uuid.UUID],
        names: dict[tuple[str, uuid.UUID], str | None],
    ) -> StudentThreadRow:
        scope_type = (thread.scope_type or "").upper()
        return StudentThreadRow(
            id=thread.id,
            title=thread.title,
            body=thread.body,
            author_name=author_name,
            mine=thread.author_id == student.id,
            scope_type=scope_type,
            scope_name=names.get((scope_type, thread.scope_id)),
            tags=list(thread.tags or []),
            is_pinned=thread.is_pinned,
            is_locked=thread.is_locked,
            is_resolved=thread.is_resolved,
            reply_count=thread.reply_count,
            upvote_count=thread.upvote_count,
            my_vote=thread.id in my_votes,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )

    @staticmethod
    async def create_thread(db: AsyncSession, student: User, payload: StudentThreadCreate) -> StudentThreadDetail:
        ctx = await StudentService.context_for_user(db, student)
        if payload.scope_type == "CLASS":
            if payload.scope_id != ctx.school_class.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You can only post in your own class")
        else:
            valid = (
                await db.execute(
                    select(Subject.id).where(
                        Subject.id == payload.scope_id,
                        Subject.tenant_id == student.tenant_id,
                        Subject.class_id == ctx.school_class.id,
                        Subject.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if valid is None:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You can only post in your own subjects")
        thread = DiscussionThread(
            id=uuid.uuid4(),
            tenant_id=student.tenant_id,
            title=payload.title.strip(),
            body=payload.body.strip(),
            author_id=student.id,
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
            actor=student,
            actor_role="STUDENT",
            action="CREATE_DISCUSSION_THREAD",
            entity="DiscussionThread",
            entity_id=thread.id,
            tenant_id=student.tenant_id,
            new_value={"title": thread.title, "scope_type": payload.scope_type},
        )
        return await StudentService.discussion_detail(db, student, thread.id)

    @staticmethod
    async def discussion_detail(db: AsyncSession, student: User, thread_id: uuid.UUID) -> StudentThreadDetail:
        ctx = await StudentService.context_for_user(db, student)
        thread = (
            await db.execute(
                select(DiscussionThread).where(
                    DiscussionThread.id == thread_id,
                    DiscussionThread.tenant_id == student.tenant_id,
                    DiscussionThread.deleted_at.is_(None),
                    StudentService._visibility(ctx),
                )
            )
        ).scalar_one_or_none()
        if thread is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Discussion thread not found")
        author_name = (
            await db.execute(
                select(User.name).where(User.id == thread.author_id, User.tenant_id == student.tenant_id)
            )
        ).scalar_one_or_none()
        reply_rows = (
            await db.execute(
                select(DiscussionReply, User.name)
                .outerjoin(User, and_(User.id == DiscussionReply.author_id, User.tenant_id == student.tenant_id))
                .where(
                    DiscussionReply.thread_id == thread.id,
                    DiscussionReply.tenant_id == student.tenant_id,
                    DiscussionReply.deleted_at.is_(None),
                )
                .order_by(DiscussionReply.is_accepted_answer.desc(), DiscussionReply.created_at)
            )
        ).all()
        thread_votes = await StudentService._my_votes(db, student, "THREAD", [thread.id])
        reply_votes = await StudentService._my_votes(db, student, "REPLY", [reply.id for reply, _n in reply_rows])
        names = await StudentService._thread_scope_names(db, student, ctx, [thread])
        return StudentThreadDetail(
            **StudentService._thread_row(thread, author_name, student, thread_votes, names).model_dump(),
            replies=[
                StudentReplyRow(
                    id=reply.id,
                    author_name=name,
                    mine=reply.author_id == student.id,
                    body=reply.body,
                    is_accepted_answer=reply.is_accepted_answer,
                    upvote_count=reply.upvote_count,
                    my_vote=reply.id in reply_votes,
                    created_at=reply.created_at,
                )
                for reply, name in reply_rows
            ],
        )

    @staticmethod
    async def reply_thread(db: AsyncSession, student: User, thread_id: uuid.UUID, payload: StudentReplyCreate) -> StudentThreadDetail:
        ctx = await StudentService.context_for_user(db, student)
        thread = (
            await db.execute(
                select(DiscussionThread)
                .where(
                    DiscussionThread.id == thread_id,
                    DiscussionThread.tenant_id == student.tenant_id,
                    DiscussionThread.deleted_at.is_(None),
                    StudentService._visibility(ctx),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if thread is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Discussion thread not found")
        if thread.is_locked:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This thread is locked")
        db.add(
            DiscussionReply(
                id=uuid.uuid4(),
                tenant_id=student.tenant_id,
                thread_id=thread.id,
                author_id=student.id,
                body=payload.body.strip(),
            )
        )
        thread.reply_count = (thread.reply_count or 0) + 1
        await db.flush()
        return await StudentService.discussion_detail(db, student, thread.id)

    @staticmethod
    async def toggle_vote(db: AsyncSession, student: User, payload: StudentVoteToggle) -> StudentThreadDetail:
        ctx = await StudentService.context_for_user(db, student)
        if payload.target_type == "THREAD":
            thread = (
                await db.execute(
                    select(DiscussionThread)
                    .where(
                        DiscussionThread.id == payload.target_id,
                        DiscussionThread.tenant_id == student.tenant_id,
                        DiscussionThread.deleted_at.is_(None),
                        StudentService._visibility(ctx),
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if thread is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Discussion thread not found")
        else:
            reply = (
                await db.execute(
                    select(DiscussionReply)
                    .where(
                        DiscussionReply.id == payload.target_id,
                        DiscussionReply.tenant_id == student.tenant_id,
                        DiscussionReply.deleted_at.is_(None),
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if reply is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Reply not found")
            thread = (
                await db.execute(
                    select(DiscussionThread)
                    .where(
                        DiscussionThread.id == reply.thread_id,
                        DiscussionThread.tenant_id == student.tenant_id,
                        DiscussionThread.deleted_at.is_(None),
                        StudentService._visibility(ctx),
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if thread is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Discussion thread not found")

        existing = (
            await db.execute(
                select(DiscussionVote).where(
                    DiscussionVote.user_id == student.id,
                    DiscussionVote.target_type == payload.target_type,
                    DiscussionVote.target_id == payload.target_id,
                )
            )
        ).scalar_one_or_none()
        target = thread if payload.target_type == "THREAD" else reply
        if existing is None:
            db.add(
                DiscussionVote(
                    id=uuid.uuid4(),
                    user_id=student.id,
                    target_type=payload.target_type,
                    target_id=payload.target_id,
                )
            )
            target.upvote_count = (target.upvote_count or 0) + 1
        else:
            await db.delete(existing)
            target.upvote_count = max((target.upvote_count or 1) - 1, 0)
        await db.flush()
        return await StudentService.discussion_detail(db, student, thread.id)

    # ── C-ST-20 fees ────────────────────────────────────────────────────────

    @staticmethod
    async def fees(db: AsyncSession, student: User) -> StudentFeeAccountOut:
        ctx = await StudentService.context_for_user(db, student)
        tenant_id = student.tenant_id
        account = (
            await db.execute(
                select(StudentFeeAccount).where(
                    StudentFeeAccount.tenant_id == tenant_id,
                    StudentFeeAccount.student_id == student.id,
                    StudentFeeAccount.academic_year_id == ctx.academic_year.id,
                )
            )
        ).scalar_one_or_none()
        if account is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No fee account found for this academic year")
        installments = (
            await db.execute(
                select(FeeInstallment)
                .where(FeeInstallment.fee_account_id == account.id, FeeInstallment.tenant_id == tenant_id)
                .order_by(FeeInstallment.installment_number)
            )
        ).scalars().all()
        payments = (
            await db.execute(
                select(FeePayment)
                .where(
                    FeePayment.fee_account_id == account.id,
                    FeePayment.tenant_id == tenant_id,
                    FeePayment.student_id == student.id,
                )
                .order_by(FeePayment.payment_date.desc())
            )
        ).scalars().all()
        grants = (
            await db.execute(
                select(ScholarshipGrant, Scholarship.name)
                .join(Scholarship, Scholarship.id == ScholarshipGrant.scholarship_id)
                .where(
                    ScholarshipGrant.tenant_id == tenant_id,
                    ScholarshipGrant.fee_account_id == account.id,
                    ScholarshipGrant.student_id == student.id,
                )
                .order_by(ScholarshipGrant.granted_at)
            )
        ).all()
        return StudentFeeAccountOut(
            academic_year=ctx.academic_year.name,
            total_fee=float(account.total_fee),
            concession_amount=float(account.concession_amount),
            scholarship_amount=float(account.scholarship_amount),
            net_payable=float(account.net_payable),
            total_paid=float(account.total_paid),
            balance_due=float(account.balance_due),
            status=_value(account.status) or "UNPAID",
            installments=[
                StudentFeeInstallment(
                    id=installment.id,
                    installment_number=installment.installment_number,
                    label=installment.label,
                    amount=float(installment.amount),
                    due_date=installment.due_date,
                    paid_amount=float(installment.paid_amount),
                    status=_value(installment.status) or "PENDING",
                    late_fine=float(installment.late_fine),
                )
                for installment in installments
            ],
            payments=[
                StudentFeePayment(
                    id=payment.id,
                    amount=float(payment.amount),
                    payment_mode=_value(payment.payment_mode) or "CASH",
                    transaction_reference=payment.transaction_reference,
                    payment_date=payment.payment_date,
                    receipt_number=payment.receipt_number,
                    notes=payment.notes,
                )
                for payment in payments
            ],
            grants=[
                StudentScholarshipGrant(
                    id=grant.id,
                    scholarship_name=name,
                    amount_granted=float(grant.amount_granted),
                    granted_at=grant.granted_at,
                    remarks=grant.remarks,
                )
                for grant, name in grants
            ],
        )
