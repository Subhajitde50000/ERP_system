"""Shared leadership read-models for Principal and Vice Principal consoles.

This service owns the academic aggregates once. It reads operational tables
straight from the tenant, accepts an optional department fence for delegated
leaders, and records Principal-only approval decisions in the same transaction
as the state change.

It does *not* duplicate attendance, examination or result data in a reporting
table.  That keeps the dashboard, exports and operational screens consistent.
"""

from __future__ import annotations

import csv
import io
import uuid
import base64
import binascii
from pathlib import Path
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic import AcademicYear, Department, SchoolClass, Subject
from app.models.enrollment import Enrollment
from app.models.principal import (
    AttendanceSession,
    Exam,
    ExamStatus,
    Notice,
    NoticeAttachment,
    NoticePriority,
    NoticeRead,
    NoticeScope,
    ResultOutcome,
    ResultPublication,
    StaffLeaveRequest,
    StaffProfile,
    StudentResult,
    TimetableSlot,
)
from app.models.role import Role, RoleAssignment
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.principal import (
    AttendanceClassSummary,
    AttendanceDepartmentSummary,
    NoticeReader,
    NoticeAttachment as NoticeAttachmentOut,
    PrincipalAttendanceOverview,
    PrincipalDashboard,
    PrincipalExamPage,
    PrincipalExamRow,
    PrincipalNoticeCreate,
    PrincipalNoticeDetail,
    PrincipalNoticePage,
    PrincipalNoticeRow,
    PrincipalNoticeTargets,
    PrincipalPerformanceRow,
    PrincipalPublicationRow,
    PrincipalReports,
    PrincipalResultGroup,
    PrincipalResultsOverview,
    PrincipalStaffDetail,
    PrincipalStaffPage,
    PrincipalStaffRow,
    PrincipalStudentDetail,
    PrincipalStudentEnrollment,
    PrincipalStudentPage,
    PrincipalStudentRow,
    PrincipalTargetOption,
    PrincipalTimetable,
    PrincipalTimetableSlot,
    PrincipalUpcomingExam,
    ResultApprovalRequest,
    ScheduleApprovalRequest,
)
from app.services.audit_service import AuditService
from app.services.storage_service import storage


_APPROVAL_STATES = {"PENDING", "APPROVED", "REJECTED"}
# ``None`` means institution-wide (Principal); an empty set deliberately means
# no access. Vice Principal callers always receive a non-empty, database-checked
# department set from VicePrincipalService.
DepartmentScope = frozenset[uuid.UUID] | None

_EXAM_FINAL_STATUSES = {
    ExamStatus.ONGOING,
    ExamStatus.COMPLETED,
    ExamStatus.RESULTS_RELEASED,
    ExamStatus.CANCELLED,
}

_NOTICE_MAX_FILE_BYTES = 10 * 1024 * 1024
_NOTICE_ALLOWED_MIME_TYPES = {
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip",
    "application/x-zip-compressed",
    "image/jpeg", "image/png", "image/webp",
}


def _value(value: object | None) -> str | None:
    """Return the wire value for a Python Enum or a plain database string."""
    if value is None:
        return None
    candidate = getattr(value, "value", value)
    return str(candidate)


def _number(value: Decimal | float | int | None) -> float | None:
    return round(float(value), 2) if value is not None else None


def _approval_state(value: str | None) -> str:
    """Normalise legacy NULL rows without ever leaking an unknown state."""
    return value if value in _APPROVAL_STATES else "PENDING"


def _page_bounds(limit: int, offset: int) -> tuple[int, int]:
    if not 1 <= limit <= 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="offset must be zero or greater")
    return limit, offset


def _date_window(
    from_date: date | None,
    to_date: date | None,
    *,
    default_end: date | None = None,
) -> tuple[date, date]:
    """Validate a bounded reporting window; an unbounded report is a DoS risk."""
    end_of_default_window = default_end or datetime.now(timezone.utc).date()
    start = from_date or end_of_default_window - timedelta(days=30)
    end = to_date or end_of_default_window
    if start > end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="from_date must be on or before to_date")
    if (end - start).days > 366:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Report date range cannot exceed 366 days")
    return start, end


class PrincipalService:
    # ── Common tenant / aggregate helpers ───────────────────────────────────

    @staticmethod
    async def _tenant_today(db: AsyncSession, tenant_id: uuid.UUID) -> date:
        timezone_name = (
            await db.execute(select(Tenant.timezone).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()
        try:
            return datetime.now(ZoneInfo(timezone_name or "UTC")).date()
        except (ValueError, TypeError, KeyError):
            # Tenant timezone is admin-controlled.  A bad legacy value must not
            # break every Principal page, but it must not alter tenant scoping.
            # KeyError covers ZoneInfoNotFoundError (Windows: missing tzdata).
            return datetime.now(timezone.utc).date()

    @staticmethod
    async def _current_year_name(db: AsyncSession, tenant_id: uuid.UUID) -> str | None:
        return (
            await db.execute(
                select(AcademicYear.name)
                .where(AcademicYear.tenant_id == tenant_id, AcademicYear.is_current.is_(True))
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    def _active_role_clause() -> object:
        now = datetime.now(timezone.utc)
        return and_(
            RoleAssignment.is_active.is_(True),
            or_(RoleAssignment.expires_at.is_(None), RoleAssignment.expires_at > now),
        )

    @staticmethod
    def _scoped_class_ids(tenant_id: uuid.UUID, department_ids: DepartmentScope):
        """A tenant-bound class subquery for a delegated department scope.

        Keeping this at the data boundary prevents every leadership view from
        reimplementing a fragile class→department join. ``None`` is the
        Principal's institution-wide scope; an empty set intentionally yields
        no class ids.
        """
        stmt = select(SchoolClass.id).where(SchoolClass.tenant_id == tenant_id)
        if department_ids is not None:
            stmt = stmt.where(SchoolClass.department_id.in_(department_ids))
        return stmt

    @staticmethod
    def _scoped_staff_user_ids(tenant_id: uuid.UUID, department_ids: DepartmentScope):
        """Users with a live department-scoped role in the requested scope."""
        stmt = (
            select(RoleAssignment.user_id)
            .where(
                RoleAssignment.tenant_id == tenant_id,
                func.upper(RoleAssignment.scope_type) == "DEPARTMENT",
                PrincipalService._active_role_clause(),
            )
            .distinct()
        )
        if department_ids is not None:
            stmt = stmt.where(RoleAssignment.scope_id.in_(department_ids))
        return stmt

    @staticmethod
    def _apply_department_scope(statement, department_ids: DepartmentScope):
        """Append the department fence when a delegated scope is present."""
        if department_ids is None:
            return statement
        return statement.where(Department.id.in_(department_ids))

    @staticmethod
    async def _attendance_overview(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        from_date: date | None = None,
        to_date: date | None = None,
        *,
        department_ids: DepartmentScope = None,
    ) -> PrincipalAttendanceOverview:
        """One grouped query for every department/class, then safe percentages.

        Percentage is calculated from summed present/absent marks, never by
        averaging class percentages.  A ten-student class therefore cannot
        outweigh a five-hundred-student class.
        """
        start, end = _date_window(
            from_date,
            to_date,
            default_end=await PrincipalService._tenant_today(db, tenant_id),
        )
        department_filters = [
            Department.tenant_id == tenant_id,
            Department.is_active.is_(True),
        ]
        if department_ids is not None:
            department_filters.append(Department.id.in_(department_ids))
        rows = await db.execute(
            select(
                Department.id.label("department_id"),
                Department.name.label("department_name"),
                SchoolClass.id.label("class_id"),
                SchoolClass.name.label("class_name"),
                func.coalesce(func.sum(AttendanceSession.total_present), 0).label("present"),
                func.coalesce(func.sum(AttendanceSession.total_absent), 0).label("absent"),
            )
            .select_from(Department)
            .outerjoin(
                SchoolClass,
                and_(
                    SchoolClass.department_id == Department.id,
                    SchoolClass.tenant_id == tenant_id,
                    SchoolClass.is_active.is_(True),
                ),
            )
            .outerjoin(
                AttendanceSession,
                and_(
                    AttendanceSession.class_id == SchoolClass.id,
                    AttendanceSession.tenant_id == tenant_id,
                    AttendanceSession.date >= start,
                    AttendanceSession.date <= end,
                ),
            )
            .where(*department_filters)
            .group_by(Department.id, Department.name, SchoolClass.id, SchoolClass.name)
            .order_by(Department.name, SchoolClass.name)
        )

        grouped: dict[uuid.UUID, dict] = {}
        total_present = 0
        total_absent = 0
        for row in rows.all():
            department = grouped.setdefault(
                row.department_id,
                {
                    "id": row.department_id,
                    "name": row.department_name,
                    "present": 0,
                    "absent": 0,
                    "classes": [],
                },
            )
            present, absent = int(row.present or 0), int(row.absent or 0)
            department["present"] += present
            department["absent"] += absent
            total_present += present
            total_absent += absent
            if row.class_id is not None:
                marks = present + absent
                department["classes"].append(
                    AttendanceClassSummary(
                        id=row.class_id,
                        name=row.class_name,
                        attendance_percentage=round(present * 100 / marks, 2) if marks else None,
                        total_present=present,
                        total_absent=absent,
                        attendance_marks=marks,
                    )
                )

        departments = []
        for aggregate in grouped.values():
            present, absent = aggregate["present"], aggregate["absent"]
            marks = present + absent
            departments.append(
                AttendanceDepartmentSummary(
                    id=aggregate["id"],
                    name=aggregate["name"],
                    attendance_percentage=round(present * 100 / marks, 2) if marks else None,
                    total_present=present,
                    total_absent=absent,
                    attendance_marks=marks,
                    # Per-student percentages are intentionally not guessed
                    # from aggregate session counts. A separate alert job owns
                    # that metric once attendance-record data is available.
                    classes=aggregate["classes"],
                )
            )

        marks = total_present + total_absent
        return PrincipalAttendanceOverview(
            from_date=start,
            to_date=end,
            attendance_percentage=round(total_present * 100 / marks, 2) if marks else None,
            total_present=total_present,
            total_absent=total_absent,
            attendance_marks=marks,
            departments=departments,
        )

    @staticmethod
    async def _result_groups(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        department_ids: DepartmentScope = None,
    ) -> tuple[list[PrincipalResultGroup], list[PrincipalResultGroup]]:
        """Return weighted department and class result roll-ups.

        ``student_results`` has its own tenant id, and joins are also fenced by
        the tenant-bound class/department rows.  That redundancy is deliberate
        for a high-value institution-wide read.
        """
        aggregate_columns = (
            func.count(StudentResult.id).label("student_count"),
            func.coalesce(
                func.sum(case((StudentResult.result == ResultOutcome.PASS, 1), else_=0)), 0
            ).label("pass_count"),
            func.coalesce(
                func.sum(case((StudentResult.result == ResultOutcome.FAIL, 1), else_=0)), 0
            ).label("fail_count"),
            func.coalesce(
                func.sum(case((StudentResult.result == ResultOutcome.WITHHELD, 1), else_=0)), 0
            ).label("withheld_count"),
            func.coalesce(
                func.sum(case((StudentResult.result == ResultOutcome.ABSENT, 1), else_=0)), 0
            ).label("absent_count"),
            func.avg(StudentResult.percentage).label("average_percentage"),
        )
        common = (
            select(
                SchoolClass.id.label("class_id"),
                SchoolClass.name.label("class_name"),
                Department.id.label("department_id"),
                Department.name.label("department_name"),
                *aggregate_columns,
            )
            .select_from(StudentResult)
            .join(
                SchoolClass,
                and_(SchoolClass.id == StudentResult.class_id, SchoolClass.tenant_id == tenant_id),
            )
            .join(
                Department,
                and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id),
            )
            .where(StudentResult.tenant_id == tenant_id)
        )
        common = PrincipalService._apply_department_scope(common, department_ids)

        class_rows = await db.execute(
            common.group_by(
                SchoolClass.id, SchoolClass.name, Department.id, Department.name
            ).order_by(Department.name, SchoolClass.name)
        )
        department_rows = await db.execute(
            common.with_only_columns(
                Department.id.label("department_id"),
                Department.name.label("department_name"),
                *aggregate_columns,
            ).group_by(Department.id, Department.name).order_by(Department.name)
        )

        def output(row, identifier: uuid.UUID, name: str) -> PrincipalResultGroup:
            count = int(row.student_count or 0)
            passed = int(row.pass_count or 0)
            return PrincipalResultGroup(
                id=identifier,
                name=name,
                student_count=count,
                pass_count=passed,
                fail_count=int(row.fail_count or 0),
                withheld_count=int(row.withheld_count or 0),
                absent_count=int(row.absent_count or 0),
                pass_percentage=round(passed * 100 / count, 2) if count else None,
                average_percentage=_number(row.average_percentage),
            )

        classes = [output(row, row.class_id, row.class_name) for row in class_rows.all()]
        departments = [
            output(row, row.department_id, row.department_name)
            for row in department_rows.all()
        ]
        return departments, classes

    @staticmethod
    async def _publication_rows(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        department_ids: DepartmentScope = None,
    ) -> list[PrincipalPublicationRow]:
        """Publication summaries, optionally reduced to delegated departments.

        Institution-wide publications may contain results for many classes. A
        delegated leader sees only the result rows and publication metadata
        reachable through their department classes; a class name outside that
        scope is never serialised.
        """
        publication_filters = [ResultPublication.tenant_id == tenant_id]
        publication_class_join = [
            SchoolClass.id == ResultPublication.class_id,
            SchoolClass.tenant_id == tenant_id,
        ]
        student_result_join = [
            StudentResult.publication_id == ResultPublication.id,
            StudentResult.tenant_id == tenant_id,
        ]
        if department_ids is not None:
            scoped_class_ids = PrincipalService._scoped_class_ids(tenant_id, department_ids)
            publication_class_join.append(SchoolClass.department_id.in_(department_ids))
            student_result_join.append(StudentResult.class_id.in_(scoped_class_ids))
            scoped_publication_ids = select(StudentResult.publication_id).where(
                StudentResult.tenant_id == tenant_id,
                StudentResult.class_id.in_(scoped_class_ids),
            )
            publication_filters.append(
                or_(
                    ResultPublication.class_id.in_(scoped_class_ids),
                    ResultPublication.id.in_(scoped_publication_ids),
                )
            )

        rows = await db.execute(
            select(
                ResultPublication,
                AcademicYear.name.label("academic_year_name"),
                SchoolClass.name.label("class_name"),
                User.name.label("publisher_name"),
                func.count(StudentResult.id).label("student_count"),
                func.coalesce(
                    func.sum(case((StudentResult.result == ResultOutcome.PASS, 1), else_=0)), 0
                ).label("pass_count"),
                func.avg(StudentResult.percentage).label("average_percentage"),
            )
            .outerjoin(
                AcademicYear,
                and_(
                    AcademicYear.id == ResultPublication.academic_year_id,
                    AcademicYear.tenant_id == tenant_id,
                ),
            )
            .outerjoin(SchoolClass, and_(*publication_class_join))
            .outerjoin(
                User,
                and_(User.id == ResultPublication.published_by, User.tenant_id == tenant_id),
            )
            .outerjoin(StudentResult, and_(*student_result_join))
            .where(*publication_filters)
            .group_by(ResultPublication.id, AcademicYear.name, SchoolClass.name, User.name)
            .order_by(ResultPublication.published_at.desc())
        )
        output = []
        for publication, year_name, class_name, publisher_name, count, passed, average in rows.all():
            count = int(count or 0)
            output.append(
                PrincipalPublicationRow(
                    id=publication.id,
                    title=publication.title,
                    academic_year=year_name,
                    class_name=class_name,
                    published_at=publication.published_at,
                    published_by_name=publisher_name,
                    exam_count=len(publication.exam_ids or []),
                    student_count=count,
                    pass_percentage=round(int(passed or 0) * 100 / count, 2) if count else None,
                    average_percentage=_number(average),
                    is_visible_to_students=publication.is_visible_to_students,
                    approval_status=_approval_state(publication.approval_status),
                    approved_at=publication.approved_at,
                    approval_note=publication.approval_note,
                )
            )
        return output

    # ── C-PR-01 dashboard ───────────────────────────────────────────────────

    @staticmethod
    async def dashboard(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        department_ids: DepartmentScope = None,
    ) -> PrincipalDashboard:
        attendance = await PrincipalService._attendance_overview(
            db, tenant_id, department_ids=department_ids
        )
        departments, _classes = await PrincipalService._result_groups(
            db, tenant_id, department_ids=department_ids
        )
        now = datetime.now(timezone.utc)
        today = await PrincipalService._tenant_today(db, tenant_id)
        scoped_class_ids = PrincipalService._scoped_class_ids(tenant_id, department_ids)

        exam_join = [Exam.tenant_id == Tenant.id]
        if department_ids is not None:
            exam_join.append(Exam.class_id.in_(scoped_class_ids))
        counts = await db.execute(
            select(
                func.count(Exam.id).filter(Exam.status == ExamStatus.ONGOING).label("ongoing_exams"),
                func.count(Exam.id)
                .filter(
                    Exam.scheduled_at >= now,
                    Exam.status.not_in(
                        [ExamStatus.CANCELLED, ExamStatus.COMPLETED, ExamStatus.RESULTS_RELEASED]
                    ),
                )
                .label("upcoming_exams"),
            )
            .select_from(Tenant)
            .outerjoin(Exam, and_(*exam_join))
            .where(Tenant.id == tenant_id)
        )
        count_row = counts.one()

        # The publication projection already applies any delegated class fence;
        # using it here prevents a dashboard count from disclosing another
        # department's pending result publication.
        publications = await PrincipalService._publication_rows(
            db, tenant_id, department_ids=department_ids
        )
        pending_results = sum(
            publication.approval_status == "PENDING" for publication in publications
        )

        notice_filters = [Notice.tenant_id == tenant_id, Notice.deleted_at.is_(None)]
        if department_ids is not None:
            notice_filters.append(
                PrincipalService._notice_visibility_clause(tenant_id, department_ids)
            )
        total_notices = (
            await db.execute(select(func.count(Notice.id)).where(*notice_filters))
        ).scalar() or 0

        staff_stmt = (
            select(func.count(func.distinct(User.id)))
            .select_from(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                User.tenant_id == tenant_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
                RoleAssignment.tenant_id == tenant_id,
                PrincipalService._active_role_clause(),
                Role.name.not_in(["STUDENT", "PARENT"]),
            )
        )
        if department_ids is not None:
            staff_stmt = staff_stmt.outerjoin(
                StaffProfile,
                and_(StaffProfile.user_id == User.id, StaffProfile.tenant_id == tenant_id),
            ).where(
                or_(
                    StaffProfile.department_id.in_(department_ids),
                    User.id.in_(PrincipalService._scoped_staff_user_ids(tenant_id, department_ids)),
                )
            )
        staff_count = (await db.execute(staff_stmt)).scalar() or 0

        leave_stmt = select(func.count(func.distinct(StaffLeaveRequest.staff_id))).where(
            StaffLeaveRequest.tenant_id == tenant_id,
            StaffLeaveRequest.status == "APPROVED",
            StaffLeaveRequest.from_date <= today,
            StaffLeaveRequest.to_date >= today,
        )
        if department_ids is not None:
            leave_stmt = leave_stmt.outerjoin(
                StaffProfile,
                and_(
                    StaffProfile.user_id == StaffLeaveRequest.staff_id,
                    StaffProfile.tenant_id == tenant_id,
                ),
            ).where(
                or_(
                    StaffProfile.department_id.in_(department_ids),
                    StaffLeaveRequest.staff_id.in_(
                        PrincipalService._scoped_staff_user_ids(tenant_id, department_ids)
                    ),
                )
            )
        staff_on_leave = (await db.execute(leave_stmt)).scalar() or 0

        upcoming_filters = [
            Exam.tenant_id == tenant_id,
            Exam.scheduled_at >= now,
            Exam.status.not_in(
                [ExamStatus.CANCELLED, ExamStatus.COMPLETED, ExamStatus.RESULTS_RELEASED]
            ),
        ]
        if department_ids is not None:
            upcoming_filters.append(Department.id.in_(department_ids))
        upcoming = await db.execute(
            select(Exam, SchoolClass.name, Subject.name, Department.name)
            .join(
                SchoolClass,
                and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id),
            )
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .outerjoin(
                Department,
                and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id),
            )
            .where(*upcoming_filters)
            .order_by(Exam.scheduled_at)
            .limit(5)
        )

        total_result_students = sum(group.student_count for group in departments)
        total_passed = sum(group.pass_count for group in departments)

        return PrincipalDashboard(
            academic_year=await PrincipalService._current_year_name(db, tenant_id),
            attendance_percentage=attendance.attendance_percentage,
            attendance_marks=attendance.attendance_marks,
            attendance_departments=attendance.departments,
            ongoing_exams=int(count_row.ongoing_exams or 0),
            upcoming_exams=int(count_row.upcoming_exams or 0),
            upcoming_exam_items=[
                PrincipalUpcomingExam(
                    id=exam.id,
                    title=exam.title,
                    scheduled_at=exam.scheduled_at,
                    class_name=class_name,
                    subject_name=subject_name,
                    department_name=department_name,
                    status=_value(exam.status) or "DRAFT",
                )
                for exam, class_name, subject_name, department_name in upcoming.all()
            ],
            pending_result_approvals=int(pending_results),
            result_pass_percentage=(
                round(total_passed * 100 / total_result_students, 2)
                if total_result_students
                else None
            ),
            staff_on_leave_today=int(staff_on_leave),
            staff_count=int(staff_count),
            total_notices=int(total_notices),
        )

    @staticmethod
    async def attendance(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        from_date: date | None = None,
        to_date: date | None = None,
        *,
        department_ids: DepartmentScope = None,
    ) -> PrincipalAttendanceOverview:
        return await PrincipalService._attendance_overview(
            db,
            tenant_id,
            from_date,
            to_date,
            department_ids=department_ids,
        )

    # ── C-PR-03 examination schedule and approval ───────────────────────────

    @staticmethod
    async def examinations(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        status_filter: str | None = None,
        approval_status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
        department_ids: DepartmentScope = None,
    ) -> PrincipalExamPage:
        limit, offset = _page_bounds(limit, offset)
        if status_filter and status_filter not in {s.value for s in ExamStatus}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown exam status")
        if approval_status and approval_status not in _APPROVAL_STATES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown approval status")
        if from_date and to_date:
            _date_window(from_date, to_date)

        clauses = [Exam.tenant_id == tenant_id]
        if department_ids is not None:
            clauses.append(
                Exam.class_id.in_(PrincipalService._scoped_class_ids(tenant_id, department_ids))
            )
        if status_filter:
            clauses.append(Exam.status == ExamStatus(status_filter))
        if approval_status:
            clauses.append(Exam.schedule_approval_status == approval_status)
        if from_date:
            clauses.append(Exam.scheduled_at >= datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc))
        if to_date:
            clauses.append(Exam.scheduled_at < datetime.combine(to_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))

        total = (
            await db.execute(select(func.count(Exam.id)).where(*clauses))
        ).scalar() or 0
        rows = await db.execute(
            select(Exam, SchoolClass.name, Subject.name, Subject.code, Department.name)
            .join(
                SchoolClass,
                and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id),
            )
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .outerjoin(
                Department,
                and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id),
            )
            .where(*clauses)
            .order_by(Exam.scheduled_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return PrincipalExamPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[
                PrincipalService._exam_row(exam, class_name, subject_name, subject_code, department_name)
                for exam, class_name, subject_name, subject_code, department_name in rows.all()
            ],
        )

    @staticmethod
    def _exam_row(
        exam: Exam,
        class_name: str,
        subject_name: str,
        subject_code: str,
        department_name: str | None,
    ) -> PrincipalExamRow:
        return PrincipalExamRow(
            id=exam.id,
            title=exam.title,
            class_id=exam.class_id,
            class_name=class_name,
            department_name=department_name,
            subject_id=exam.subject_id,
            subject_name=subject_name,
            subject_code=subject_code,
            scheduled_at=exam.scheduled_at,
            window_end_at=exam.window_end_at,
            duration_minutes=exam.duration_minutes,
            total_marks=exam.total_marks,
            passing_marks=exam.passing_marks,
            mode=exam.mode,
            status=_value(exam.status) or "DRAFT",
            schedule_approval_status=_approval_state(exam.schedule_approval_status),
            schedule_approved_at=exam.schedule_approved_at,
            schedule_approval_note=exam.schedule_approval_note,
        )

    @staticmethod
    async def approve_schedule(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        principal: User,
        exam_id: uuid.UUID,
        payload: ScheduleApprovalRequest,
    ) -> PrincipalExamRow:
        row = await db.execute(
            select(Exam, SchoolClass.name, Subject.name, Subject.code, Department.name)
            .join(
                SchoolClass,
                and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id),
            )
            .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
            .outerjoin(
                Department,
                and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id),
            )
            .where(Exam.id == exam_id, Exam.tenant_id == tenant_id)
            .with_for_update()
        )
        loaded = row.one_or_none()
        if loaded is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam not found")
        exam, class_name, subject_name, subject_code, department_name = loaded

        if _approval_state(exam.schedule_approval_status) != "PENDING":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This exam schedule has already been decided")
        if exam.status in _EXAM_FINAL_STATUSES or exam.scheduled_at <= datetime.now(timezone.utc):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Only a future, unscheduled exam can be approved")

        before = {
            "schedule_approval_status": _approval_state(exam.schedule_approval_status),
            "schedule_approval_note": exam.schedule_approval_note,
        }
        exam.schedule_approval_status = "APPROVED" if payload.decision == "APPROVE" else "REJECTED"
        exam.schedule_approved_by = principal.id
        exam.schedule_approved_at = datetime.now(timezone.utc)
        exam.schedule_approval_note = payload.note.strip() if payload.note else None
        await db.flush()
        AuditService.record(
            db,
            actor=principal,
            actor_role="PRINCIPAL",
            action="APPROVE_EXAM_SCHEDULE" if payload.decision == "APPROVE" else "REJECT_EXAM_SCHEDULE",
            entity="Exam",
            entity_id=exam.id,
            tenant_id=tenant_id,
            old_value=before,
            new_value={
                "title": exam.title,
                "schedule_approval_status": exam.schedule_approval_status,
                "schedule_approval_note": exam.schedule_approval_note,
            },
        )
        return PrincipalService._exam_row(exam, class_name, subject_name, subject_code, department_name)

    # ── C-PR-04 results and two-person approval ─────────────────────────────

    @staticmethod
    async def results(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        department_ids: DepartmentScope = None,
    ) -> PrincipalResultsOverview:
        departments, classes = await PrincipalService._result_groups(
            db, tenant_id, department_ids=department_ids
        )
        total_students = sum(item.student_count for item in departments)
        if total_students:
            overall = PrincipalResultGroup(
                id=tenant_id,
                name="Institution",
                student_count=total_students,
                pass_count=sum(item.pass_count for item in departments),
                fail_count=sum(item.fail_count for item in departments),
                withheld_count=sum(item.withheld_count for item in departments),
                absent_count=sum(item.absent_count for item in departments),
                pass_percentage=round(
                    sum(item.pass_count for item in departments) * 100 / total_students, 2
                ),
                average_percentage=round(
                    sum((item.average_percentage or 0) * item.student_count for item in departments)
                    / total_students,
                    2,
                ),
            )
        else:
            overall = None
        return PrincipalResultsOverview(
            overall=overall,
            departments=departments,
            classes=classes,
            publications=await PrincipalService._publication_rows(
                db, tenant_id, department_ids=department_ids
            ),
        )

    @staticmethod
    async def approve_result_publication(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        principal: User,
        publication_id: uuid.UUID,
        payload: ResultApprovalRequest,
    ) -> PrincipalPublicationRow:
        publication = (
            await db.execute(
                select(ResultPublication)
                .where(ResultPublication.id == publication_id, ResultPublication.tenant_id == tenant_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if publication is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Result publication not found")
        if _approval_state(publication.approval_status) != "PENDING":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This result publication has already been decided")
        if publication.is_visible_to_students:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="A visible result publication cannot be re-approved")

        before = {
            "approval_status": _approval_state(publication.approval_status),
            "approval_note": publication.approval_note,
        }
        publication.approval_status = "APPROVED" if payload.decision == "APPROVE" else "REJECTED"
        publication.approved_by = principal.id
        publication.approved_at = datetime.now(timezone.utc)
        publication.approval_note = payload.note.strip() if payload.note else None
        await db.flush()
        AuditService.record(
            db,
            actor=principal,
            actor_role="PRINCIPAL",
            action="APPROVE_RESULT_PUBLICATION" if payload.decision == "APPROVE" else "REJECT_RESULT_PUBLICATION",
            entity="ResultPublication",
            entity_id=publication.id,
            tenant_id=tenant_id,
            old_value=before,
            new_value={
                "title": publication.title,
                "approval_status": publication.approval_status,
                "approval_note": publication.approval_note,
            },
        )
        # Return exactly the same projection used by the list; callers never
        # receive fields that are absent from the ordinary read path.
        rows = await PrincipalService._publication_rows(db, tenant_id)
        return next(item for item in rows if item.id == publication.id)

    # ── C-PR-05 / C-PR-06 read-only directories ─────────────────────────────

    @staticmethod
    async def staff(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        query: str | None = None,
        department_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
        department_ids: DepartmentScope = None,
    ) -> PrincipalStaffPage:
        limit, offset = _page_bounds(limit, offset)
        if department_id is not None:
            await PrincipalService._ensure_department(db, tenant_id, department_id)
            if department_ids is not None and department_id not in department_ids:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Department not found")

        staff_ids = (
            select(RoleAssignment.user_id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                RoleAssignment.tenant_id == tenant_id,
                PrincipalService._active_role_clause(),
                Role.name.not_in(["STUDENT", "PARENT"]),
            )
            .distinct()
        )
        clauses = [
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
            User.id.in_(staff_ids),
        ]
        if department_ids is not None:
            clauses.append(
                or_(
                    StaffProfile.department_id.in_(department_ids),
                    User.id.in_(PrincipalService._scoped_staff_user_ids(tenant_id, department_ids)),
                )
            )
        if department_id is not None:
            clauses.append(
                or_(
                    StaffProfile.department_id == department_id,
                    User.id.in_(
                        PrincipalService._scoped_staff_user_ids(
                            tenant_id, frozenset({department_id})
                        )
                    ),
                )
            )
        if query and query.strip():
            needle = f"%{query.strip().lower()}%"
            clauses.append(
                or_(
                    func.lower(User.name).like(needle),
                    func.lower(func.coalesce(User.email, "")).like(needle),
                    func.lower(func.coalesce(User.employee_code, "")).like(needle),
                    func.lower(func.coalesce(StaffProfile.employee_code, "")).like(needle),
                )
            )

        total = (
            await db.execute(
                select(func.count(func.distinct(User.id)))
                .select_from(User)
                .outerjoin(
                    StaffProfile,
                    and_(StaffProfile.user_id == User.id, StaffProfile.tenant_id == tenant_id),
                )
                .where(*clauses)
            )
        ).scalar() or 0
        rows = await db.execute(
            select(User, StaffProfile, Department.name.label("department_name"))
            .outerjoin(
                StaffProfile,
                and_(StaffProfile.user_id == User.id, StaffProfile.tenant_id == tenant_id),
            )
            .outerjoin(
                Department,
                and_(Department.id == StaffProfile.department_id, Department.tenant_id == tenant_id),
            )
            .where(*clauses)
            .order_by(User.name)
            .limit(limit)
            .offset(offset)
        )
        loaded = rows.all()
        user_ids = [user.id for user, _profile, _department in loaded]
        role_map = await PrincipalService._roles_for_users(db, tenant_id, user_ids)
        scoped_departments = await PrincipalService._staff_department_scopes(
            db, tenant_id, user_ids, department_ids=department_ids
        )
        return PrincipalStaffPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[
                PrincipalService._staff_row(
                    user,
                    profile,
                    department_name,
                    role_map.get(user.id, []),
                    scoped_departments.get(user.id),
                )
                for user, profile, department_name in loaded
            ],
        )

    @staticmethod
    async def staff_detail(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        department_ids: DepartmentScope = None,
    ) -> PrincipalStaffDetail:
        # This precise query has the same role fence as the list and returns a
        # 404 outside that audience, so identifiers cannot be used to probe
        # another tenant's users.
        staff_ids = (
            select(RoleAssignment.user_id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                RoleAssignment.tenant_id == tenant_id,
                PrincipalService._active_role_clause(),
                Role.name.not_in(["STUDENT", "PARENT"]),
            )
            .distinct()
        )
        detail_filters = [
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
            User.id.in_(staff_ids),
        ]
        if department_ids is not None:
            detail_filters.append(
                or_(
                    StaffProfile.department_id.in_(department_ids),
                    User.id.in_(PrincipalService._scoped_staff_user_ids(tenant_id, department_ids)),
                )
            )
        row = await db.execute(
            select(User, StaffProfile, Department.name.label("department_name"))
            .outerjoin(
                StaffProfile,
                and_(StaffProfile.user_id == User.id, StaffProfile.tenant_id == tenant_id),
            )
            .outerjoin(
                Department,
                and_(Department.id == StaffProfile.department_id, Department.tenant_id == tenant_id),
            )
            .where(*detail_filters)
        )
        loaded = row.one_or_none()
        if loaded is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Staff member not found")
        user, profile, department_name = loaded
        roles = await PrincipalService._roles_for_users(db, tenant_id, [user.id])
        scoped_departments = await PrincipalService._staff_department_scopes(
            db, tenant_id, [user.id], department_ids=department_ids
        )
        base = PrincipalService._staff_row(
            user,
            profile,
            department_name,
            roles.get(user.id, []),
            scoped_departments.get(user.id),
        )
        return PrincipalStaffDetail(
            **base.model_dump(),
            qualification=profile.qualification if profile else None,
            experience_years=profile.experience_years if profile else None,
        )

    @staticmethod
    def _staff_row(
        user: User,
        profile: StaffProfile | None,
        department_name: str | None,
        roles: list[str],
        scoped_department: tuple[uuid.UUID, str] | None = None,
    ) -> PrincipalStaffRow:
        department_id = profile.department_id if profile else (
            scoped_department[0] if scoped_department else None
        )
        resolved_department_name = department_name if profile else (
            scoped_department[1] if scoped_department else None
        )
        return PrincipalStaffRow(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            avatar_url=user.avatar_url,
            employee_code=(profile.employee_code if profile else user.employee_code),
            designation=profile.designation if profile else None,
            department_id=department_id,
            department_name=resolved_department_name,
            employment_type=profile.employment_type if profile else None,
            date_of_joining=profile.date_of_joining if profile else None,
            roles=roles,
            is_active=user.is_active and (profile.is_active if profile else True),
        )

    @staticmethod
    async def students(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        query: str | None = None,
        class_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PrincipalStudentPage:
        limit, offset = _page_bounds(limit, offset)
        if class_id is not None:
            await PrincipalService._ensure_class(db, tenant_id, class_id)

        student_ids = (
            select(RoleAssignment.user_id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                RoleAssignment.tenant_id == tenant_id,
                PrincipalService._active_role_clause(),
                Role.name == "STUDENT",
            )
            .distinct()
        )
        clauses = [User.tenant_id == tenant_id, User.deleted_at.is_(None), User.id.in_(student_ids)]
        if query and query.strip():
            needle = f"%{query.strip().lower()}%"
            clauses.append(
                or_(
                    func.lower(User.name).like(needle),
                    func.lower(func.coalesce(User.email, "")).like(needle),
                    func.lower(func.coalesce(User.student_roll_no, "")).like(needle),
                )
            )
        if class_id is not None:
            enrolled_ids = select(Enrollment.student_id).where(
                Enrollment.tenant_id == tenant_id,
                Enrollment.class_id == class_id,
            )
            clauses.append(User.id.in_(enrolled_ids))

        total = (await db.execute(select(func.count(User.id)).where(*clauses))).scalar() or 0
        users = (
            await db.execute(select(User).where(*clauses).order_by(User.name).limit(limit).offset(offset))
        ).scalars().all()
        enrollments = await PrincipalService._enrollments_for_students(
            db, tenant_id, [user.id for user in users]
        )
        return PrincipalStudentPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[
                PrincipalStudentRow(
                    id=user.id,
                    name=user.name,
                    email=user.email,
                    phone=user.phone,
                    avatar_url=user.avatar_url,
                    roll_no=user.student_roll_no,
                    is_active=user.is_active,
                    enrollment=enrollments.get(user.id),
                )
                for user in users
            ],
        )

    @staticmethod
    async def student_detail(
        db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> PrincipalStudentDetail:
        student_ids = (
            select(RoleAssignment.user_id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                RoleAssignment.tenant_id == tenant_id,
                PrincipalService._active_role_clause(),
                Role.name == "STUDENT",
            )
            .distinct()
        )
        user = (
            await db.execute(
                select(User).where(
                    User.id == user_id,
                    User.tenant_id == tenant_id,
                    User.deleted_at.is_(None),
                    User.id.in_(student_ids),
                )
            )
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
        enrollments = await PrincipalService._enrollments_for_students(db, tenant_id, [user.id])
        return PrincipalStudentDetail(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            avatar_url=user.avatar_url,
            roll_no=user.student_roll_no,
            is_active=user.is_active,
            enrollment=enrollments.get(user.id),
            date_of_birth=user.date_of_birth,
            gender=_value(user.gender),
        )

    @staticmethod
    async def _staff_department_scopes(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_ids: Iterable[uuid.UUID],
        *,
        department_ids: DepartmentScope = None,
    ) -> dict[uuid.UUID, tuple[uuid.UUID, str]]:
        """One safe department label per staff user from live role scopes.

        HR profiles are optional, while staff invitations already carry a
        department-scoped role assignment. This fallback keeps leadership
        directories useful without treating missing HR data as no department.
        """
        ids = list(user_ids)
        if not ids:
            return {}
        filters = [
            RoleAssignment.tenant_id == tenant_id,
            RoleAssignment.user_id.in_(ids),
            func.upper(RoleAssignment.scope_type) == "DEPARTMENT",
            PrincipalService._active_role_clause(),
            Department.tenant_id == tenant_id,
        ]
        if department_ids is not None:
            filters.append(Department.id.in_(department_ids))
        rows = await db.execute(
            select(RoleAssignment.user_id, Department.id, Department.name)
            .join(Department, Department.id == RoleAssignment.scope_id)
            .where(*filters)
            .order_by(Department.name)
        )
        output: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
        for user_id, department_id, department_name in rows.all():
            output.setdefault(user_id, (department_id, department_name))
        return output

    @staticmethod
    async def _roles_for_users(
        db: AsyncSession, tenant_id: uuid.UUID, user_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, list[str]]:
        ids = list(user_ids)
        if not ids:
            return {}
        rows = await db.execute(
            select(RoleAssignment.user_id, Role.name)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                RoleAssignment.tenant_id == tenant_id,
                RoleAssignment.user_id.in_(ids),
                PrincipalService._active_role_clause(),
            )
            .order_by(Role.name)
        )
        grouped: dict[uuid.UUID, list[str]] = defaultdict(list)
        for user_id, role_name in rows.all():
            grouped[user_id].append(role_name)
        return grouped

    @staticmethod
    async def _enrollments_for_students(
        db: AsyncSession, tenant_id: uuid.UUID, student_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, PrincipalStudentEnrollment]:
        ids = list(student_ids)
        if not ids:
            return {}
        rows = await db.execute(
            select(
                Enrollment,
                SchoolClass.name.label("class_name"),
                Department.name.label("department_name"),
                AcademicYear.name.label("year_name"),
                AcademicYear.is_current.label("year_is_current"),
            )
            .join(
                SchoolClass,
                and_(SchoolClass.id == Enrollment.class_id, SchoolClass.tenant_id == tenant_id),
            )
            .join(
                Department,
                and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id),
            )
            .join(
                AcademicYear,
                and_(AcademicYear.id == Enrollment.academic_year_id, AcademicYear.tenant_id == tenant_id),
            )
            .where(Enrollment.tenant_id == tenant_id, Enrollment.student_id.in_(ids))
            .order_by(AcademicYear.is_current.desc(), Enrollment.enrollment_date.desc())
        )
        best: dict[uuid.UUID, PrincipalStudentEnrollment] = {}
        for enrollment, class_name, department_name, year_name, _is_current in rows.all():
            if enrollment.student_id not in best:
                best[enrollment.student_id] = PrincipalStudentEnrollment(
                    class_id=enrollment.class_id,
                    class_name=class_name,
                    department_name=department_name,
                    academic_year_name=year_name,
                    roll_number=enrollment.roll_number,
                    status=enrollment.status,
                    enrollment_date=enrollment.enrollment_date,
                )
        return best

    # ── C-PR-07 / C-PR-08 notice board ──────────────────────────────────────

    @staticmethod
    def _notice_visibility_clause(
        tenant_id: uuid.UUID, department_ids: frozenset[uuid.UUID]
    ):
        """Institution notices plus the delegated department/class audience."""
        scoped_class_ids = PrincipalService._scoped_class_ids(tenant_id, department_ids)
        return or_(
            Notice.target_scope == NoticeScope.INSTITUTION,
            and_(
                Notice.target_scope == NoticeScope.DEPARTMENT,
                Notice.target_id.in_(department_ids),
            ),
            and_(
                Notice.target_scope == NoticeScope.CLASS,
                Notice.target_id.in_(scoped_class_ids),
            ),
        )

    @staticmethod
    async def notices(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        query: str | None = None,
        scope: str | None = None,
        include_expired: bool = False,
        limit: int = 50,
        offset: int = 0,
        department_ids: DepartmentScope = None,
    ) -> PrincipalNoticePage:
        limit, offset = _page_bounds(limit, offset)
        if scope and scope not in {"INSTITUTION", "DEPARTMENT", "CLASS"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown notice scope")
        now = datetime.now(timezone.utc)
        clauses = [Notice.tenant_id == tenant_id, Notice.deleted_at.is_(None)]
        if department_ids is not None:
            clauses.append(PrincipalService._notice_visibility_clause(tenant_id, department_ids))
        if scope:
            clauses.append(Notice.target_scope == NoticeScope(scope))
        if not include_expired:
            clauses.append(or_(Notice.expires_at.is_(None), Notice.expires_at > now))
        if query and query.strip():
            needle = f"%{query.strip().lower()}%"
            clauses.append(
                or_(func.lower(Notice.title).like(needle), func.lower(Notice.body).like(needle))
            )

        total = (await db.execute(select(func.count(Notice.id)).where(*clauses))).scalar() or 0
        read_counts = (
            select(NoticeRead.notice_id.label("notice_id"), func.count(NoticeRead.id).label("read_count"))
            .group_by(NoticeRead.notice_id)
            .subquery()
        )
        rows = await db.execute(
            select(Notice, User.name.label("author_name"), func.coalesce(read_counts.c.read_count, 0))
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
        target_names = await PrincipalService._notice_target_names(
            db, tenant_id, [notice for notice, _author, _reads in notices]
        )
        return PrincipalNoticePage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[
                PrincipalService._notice_row(
                    notice,
                    author_name,
                    int(read_count or 0),
                    target_names.get((notice.target_scope.value, notice.target_id)),
                )
                for notice, author_name, read_count in notices
            ],
        )

    @staticmethod
    async def notice_detail(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        notice_id: uuid.UUID,
        *,
        department_ids: DepartmentScope = None,
        include_readers: bool = True,
    ) -> PrincipalNoticeDetail:
        notice_filters = [
            Notice.id == notice_id,
            Notice.tenant_id == tenant_id,
            Notice.deleted_at.is_(None),
        ]
        if department_ids is not None:
            notice_filters.append(
                PrincipalService._notice_visibility_clause(tenant_id, department_ids)
            )
        notice = (
            await db.execute(select(Notice).where(*notice_filters))
        ).scalar_one_or_none()
        if notice is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Notice not found")
        author_name = (
            await db.execute(
                select(User.name).where(User.id == notice.author_id, User.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        readers: list[NoticeReader] = []
        if include_readers:
            read_rows = await db.execute(
                select(NoticeRead, User.name)
                .join(User, and_(User.id == NoticeRead.user_id, User.tenant_id == tenant_id))
                .where(NoticeRead.notice_id == notice.id)
                .order_by(NoticeRead.read_at.desc())
            )
            readers = [
                NoticeReader(id=read.user_id, name=name, read_at=read.read_at)
                for read, name in read_rows.all()
            ]
        target_names = await PrincipalService._notice_target_names(db, tenant_id, [notice])
        base = PrincipalService._notice_row(
            notice,
            author_name,
            len(readers),
            target_names.get((notice.target_scope.value, notice.target_id)),
        )
        return PrincipalNoticeDetail(
            # LeadershipNoticeRow already carries an `attachments` default —
            # exclude it or the explicit kwarg below collides (TypeError).
            **base.model_dump(exclude={"attachments"}),
            readers=readers,
            attachments=await PrincipalService._notice_attachments(db, notice.id),
        )

    @staticmethod
    async def create_notice(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        principal: User,
        payload: PrincipalNoticeCreate,
        *,
        department_ids: DepartmentScope = None,
        allow_institution: bool = True,
        actor_role: str = "PRINCIPAL",
    ) -> PrincipalNoticeDetail:
        title = payload.title.strip()
        body = payload.body.strip()
        if not title or not body:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Notice title and body cannot be blank")
        if payload.expires_at and payload.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="expires_at must be in the future")
        if payload.target_scope == "INSTITUTION" and not allow_institution:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Vice Principals cannot publish institution-wide notices",
            )
        if payload.target_scope == "DEPARTMENT":
            department = await PrincipalService._ensure_department(db, tenant_id, payload.target_id)
            if department_ids is not None and department.id not in department_ids:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Department not found")
        elif payload.target_scope == "CLASS":
            school_class = await PrincipalService._ensure_class(db, tenant_id, payload.target_id)
            if department_ids is not None and school_class.department_id not in department_ids:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Class not found")

        notice = Notice(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            title=title,
            body=body,
            author_id=principal.id,
            target_scope=NoticeScope(payload.target_scope),
            target_id=payload.target_id,
            priority=NoticePriority(payload.priority),
            is_pinned=payload.is_pinned,
            published_at=datetime.now(timezone.utc),
            expires_at=payload.expires_at,
        )
        db.add(notice)
        await db.flush()
        attachments = await PrincipalService._save_notice_attachments(
            db, notice.tenant_id, notice.id, payload.attachments
        )
        AuditService.record(
            db,
            actor=principal,
            actor_role=actor_role,
            action="CREATE_NOTICE",
            entity="Notice",
            entity_id=notice.id,
            tenant_id=tenant_id,
            new_value={
                "title": notice.title,
                "target_scope": payload.target_scope,
                "target_id": str(payload.target_id) if payload.target_id else None,
                "priority": payload.priority,
                "is_pinned": payload.is_pinned,
            },
        )
        targets = await PrincipalService._notice_target_names(db, tenant_id, [notice])
        base = PrincipalService._notice_row(
            notice,
            principal.name,
            0,
            targets.get((notice.target_scope.value, notice.target_id)),
        )
        return PrincipalNoticeDetail(
            # LeadershipNoticeRow already carries an `attachments` default —
            # exclude it or the explicit kwarg below collides (TypeError).
            **base.model_dump(exclude={"attachments"}),
            readers=[],
            attachments=attachments,
        )

    @staticmethod
    async def _save_notice_attachments(
        db: AsyncSession, tenant_id: uuid.UUID, notice_id: uuid.UUID, attachments: list
    ) -> list[NoticeAttachmentOut]:
        saved: list[NoticeAttachmentOut] = []
        for item in attachments:
            if item.external_url:
                row = NoticeAttachment(
                    id=uuid.uuid4(), notice_id=notice_id, file_name=item.file_name,
                    file_key=None, file_size_bytes=0, mime_type="text/uri-list", external_url=item.external_url,
                )
                db.add(row)
                saved.append(NoticeAttachmentOut(id=row.id, file_name=row.file_name, file_size_bytes=0, mime_type=row.mime_type, url=item.external_url, is_image=False, is_link=True))
                continue
            if item.mime_type not in _NOTICE_ALLOWED_MIME_TYPES:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported notice attachment type")
            try:
                encoded = item.data_url.split(",", 1)[1]
                content = base64.b64decode(encoded, validate=True)
            except (IndexError, ValueError, binascii.Error):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid attachment data") from None
            if not content or len(content) > _NOTICE_MAX_FILE_BYTES:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Each attachment must be at most 10 MB")
            stored = await storage.save(
                tenant_id,
                f"notices/{notice_id}",
                item.file_name,
                content,
                item.mime_type,
                max_bytes=_NOTICE_MAX_FILE_BYTES,
            )
            file_key = stored.key
            row = NoticeAttachment(id=uuid.uuid4(), notice_id=notice_id, file_name=Path(item.file_name).name[:255], file_key=file_key, file_size_bytes=stored.size, mime_type=stored.mime)
            db.add(row)
            saved.append(NoticeAttachmentOut(id=row.id, file_name=row.file_name, file_size_bytes=row.file_size_bytes, mime_type=row.mime_type, url=storage.signed_url(file_key), is_image=row.mime_type.startswith("image/"), is_link=False))
        await db.flush()
        return saved

    @staticmethod
    async def _notice_attachments(db: AsyncSession, notice_id: uuid.UUID) -> list[NoticeAttachmentOut]:
        rows = (await db.execute(select(NoticeAttachment).where(NoticeAttachment.notice_id == notice_id).order_by(NoticeAttachment.created_at))).scalars().all()
        return [NoticeAttachmentOut(id=row.id, file_name=row.file_name, file_size_bytes=row.file_size_bytes, mime_type=row.mime_type, url=row.external_url or (storage.signed_url(row.file_key) if row.file_key else ""), is_image=row.mime_type.startswith("image/"), is_link=bool(row.external_url)) for row in rows]

    @staticmethod
    def _notice_row(
        notice: Notice,
        author_name: str | None,
        read_count: int,
        target_name: str | None,
    ) -> PrincipalNoticeRow:
        scope = _value(notice.target_scope) or "INSTITUTION"
        priority = _value(notice.priority) or "NORMAL"
        return PrincipalNoticeRow(
            id=notice.id,
            title=notice.title,
            body=notice.body,
            author_name=author_name,
            target_scope=scope,  # validated by our enum/model
            target_id=notice.target_id,
            target_name=target_name,
            priority=priority,
            is_pinned=notice.is_pinned,
            published_at=notice.published_at,
            expires_at=notice.expires_at,
            read_count=read_count,
        )

    @staticmethod
    async def notice_targets(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        department_ids: DepartmentScope = None,
    ) -> PrincipalNoticeTargets:
        department_filters = [
            Department.tenant_id == tenant_id,
            Department.is_active.is_(True),
        ]
        class_filters = [
            SchoolClass.tenant_id == tenant_id,
            SchoolClass.is_active.is_(True),
        ]
        if department_ids is not None:
            department_filters.append(Department.id.in_(department_ids))
            class_filters.append(Department.id.in_(department_ids))
        departments = (
            await db.execute(select(Department).where(*department_filters).order_by(Department.name))
        ).scalars().all()
        classes = await db.execute(
            select(SchoolClass, Department.name)
            .join(
                Department,
                and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id),
            )
            .where(*class_filters)
            .order_by(Department.name, SchoolClass.name)
        )
        return PrincipalNoticeTargets(
            departments=[PrincipalTargetOption(id=dept.id, name=dept.name) for dept in departments],
            classes=[
                PrincipalTargetOption(
                    id=school_class.id,
                    name=school_class.name,
                    department_id=school_class.department_id,
                    department_name=department_name,
                )
                for school_class, department_name in classes.all()
            ],
        )

    @staticmethod
    async def _notice_target_names(
        db: AsyncSession, tenant_id: uuid.UUID, notices: Iterable[Notice]
    ) -> dict[tuple[str, uuid.UUID | None], str | None]:
        notices = list(notices)
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
        names: dict[tuple[str, uuid.UUID | None], str | None] = {
            ("INSTITUTION", None): "Institution-wide"
        }
        if department_ids:
            rows = await db.execute(
                select(Department.id, Department.name).where(
                    Department.tenant_id == tenant_id, Department.id.in_(department_ids)
                )
            )
            names.update({("DEPARTMENT", identifier): name for identifier, name in rows.all()})
        if class_ids:
            rows = await db.execute(
                select(SchoolClass.id, SchoolClass.name).where(
                    SchoolClass.tenant_id == tenant_id, SchoolClass.id.in_(class_ids)
                )
            )
            names.update({("CLASS", identifier): name for identifier, name in rows.all()})
        return names

    # ── C-PR-09 timetable ───────────────────────────────────────────────────

    @staticmethod
    async def timetable(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        class_id: uuid.UUID | None = None,
        *,
        department_ids: DepartmentScope = None,
    ) -> PrincipalTimetable:
        if class_id is not None:
            school_class = await PrincipalService._ensure_class(db, tenant_id, class_id)
            if department_ids is not None and school_class.department_id not in department_ids:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Class not found")
        today = await PrincipalService._tenant_today(db, tenant_id)
        class_rows = await db.execute(
            select(SchoolClass, Department.name)
            .join(
                Department,
                and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id),
            )
            .where(
                SchoolClass.tenant_id == tenant_id,
                SchoolClass.is_active.is_(True),
                *(
                    [SchoolClass.department_id.in_(department_ids)]
                    if department_ids is not None
                    else []
                ),
            )
            .order_by(Department.name, SchoolClass.name)
        )
        classes = [
            PrincipalTargetOption(
                id=school_class.id,
                name=school_class.name,
                department_id=school_class.department_id,
                department_name=department_name,
            )
            for school_class, department_name in class_rows.all()
        ]
        clauses = [
            TimetableSlot.tenant_id == tenant_id,
            TimetableSlot.effective_from <= today,
            or_(TimetableSlot.effective_to.is_(None), TimetableSlot.effective_to >= today),
        ]
        if department_ids is not None:
            clauses.append(
                TimetableSlot.class_id.in_(PrincipalService._scoped_class_ids(tenant_id, department_ids))
            )
        if class_id:
            clauses.append(TimetableSlot.class_id == class_id)
        rows = await db.execute(
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
                and_(SchoolClass.id == TimetableSlot.class_id, SchoolClass.tenant_id == tenant_id),
            )
            .outerjoin(
                Department,
                and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id),
            )
            .outerjoin(
                Subject,
                and_(Subject.id == TimetableSlot.subject_id, Subject.tenant_id == tenant_id),
            )
            .outerjoin(User, and_(User.id == TimetableSlot.teacher_id, User.tenant_id == tenant_id))
            .where(*clauses)
            .order_by(SchoolClass.name, TimetableSlot.day_of_week, TimetableSlot.period_number)
        )
        return PrincipalTimetable(
            classes=classes,
            slots=[
                PrincipalTimetableSlot(
                    id=slot.id,
                    class_id=slot.class_id,
                    class_name=class_name,
                    department_name=department_name,
                    day_of_week=slot.day_of_week,
                    period_number=slot.period_number,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    subject_name=subject_name,
                    subject_code=subject_code,
                    teacher_name=teacher_name,
                    room_no=slot.room_no,
                    slot_type=slot.slot_type,
                )
                for slot, class_name, department_name, subject_name, subject_code, teacher_name in rows.all()
            ],
        )

    # ── C-PR-10 reports / safe CSV export ───────────────────────────────────

    @staticmethod
    async def reports(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        department_ids: DepartmentScope = None,
    ) -> PrincipalReports:
        attendance = await PrincipalService._attendance_overview(
            db, tenant_id, from_date, to_date, department_ids=department_ids
        )
        results = await PrincipalService.results(
            db, tenant_id, department_ids=department_ids
        )
        # Department code is unique but name is not constrained by the schema;
        # merge by immutable id so two similarly named departments cannot erase
        # one another in a leadership report.
        attendance_by_id = {row.id: row for row in attendance.departments}
        result_by_id = {row.id: row for row in results.departments}
        department_ids = set(attendance_by_id) | set(result_by_id)
        performance = []
        for department_id in sorted(
            department_ids,
            key=lambda identifier: (
                attendance_by_id.get(identifier) or result_by_id[identifier]
            ).name.casefold(),
        ):
            attendance_row = attendance_by_id.get(department_id)
            result_row = result_by_id.get(department_id)
            source = attendance_row or result_row
            if source is None:  # defensive; id is sourced from one of the maps
                continue
            performance.append(
                PrincipalPerformanceRow(
                    department_id=department_id,
                    department_name=source.name,
                    attendance_percentage=(attendance_row.attendance_percentage if attendance_row else None),
                    pass_percentage=(result_row.pass_percentage if result_row else None),
                    average_percentage=(result_row.average_percentage if result_row else None),
                    student_count=(result_row.student_count if result_row else 0),
                )
            )
        return PrincipalReports(attendance=attendance, results=results, performance=performance)

    @staticmethod
    async def export_rows(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        kind: str,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        department_ids: DepartmentScope = None,
    ) -> tuple[str, list[str], list[list[object | None]]]:
        """Produce aggregate rows for a synchronous, bounded CSV export."""
        if kind not in {"attendance", "results", "performance", "timetable", "examinations"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown report type")
        if kind == "attendance":
            overview = await PrincipalService._attendance_overview(
                db, tenant_id, from_date, to_date, department_ids=department_ids
            )
            return (
                "attendance-report",
                ["Department", "Attendance %", "Present marks", "Absent marks", "Total marks"],
                [
                    [
                        item.name,
                        item.attendance_percentage,
                        item.total_present,
                        item.total_absent,
                        item.attendance_marks,
                    ]
                    for item in overview.departments
                ],
            )
        if kind == "results":
            overview = await PrincipalService.results(
                db, tenant_id, department_ids=department_ids
            )
            return (
                "results-report",
                ["Department", "Students", "Pass", "Fail", "Withheld", "Absent", "Pass %", "Average %"],
                [
                    [
                        item.name,
                        item.student_count,
                        item.pass_count,
                        item.fail_count,
                        item.withheld_count,
                        item.absent_count,
                        item.pass_percentage,
                        item.average_percentage,
                    ]
                    for item in overview.departments
                ],
            )
        if kind == "performance":
            overview = await PrincipalService.reports(
                db,
                tenant_id,
                from_date=from_date,
                to_date=to_date,
                department_ids=department_ids,
            )
            return (
                "academic-performance-report",
                ["Department", "Students", "Attendance %", "Pass %", "Average %"],
                [
                    [
                        item.department_name,
                        item.student_count,
                        item.attendance_percentage,
                        item.pass_percentage,
                        item.average_percentage,
                    ]
                    for item in overview.performance
                ],
            )
        if kind == "examinations":
            rows = await db.execute(
                select(Exam, SchoolClass.name, Subject.name, Subject.code, Department.name)
                .join(
                    SchoolClass,
                    and_(SchoolClass.id == Exam.class_id, SchoolClass.tenant_id == tenant_id),
                )
                .join(Subject, and_(Subject.id == Exam.subject_id, Subject.tenant_id == tenant_id))
                .outerjoin(
                    Department,
                    and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id),
                )
                .where(
                    Exam.tenant_id == tenant_id,
                    *(
                        [Exam.class_id.in_(PrincipalService._scoped_class_ids(tenant_id, department_ids))]
                        if department_ids is not None
                        else []
                    ),
                )
                .order_by(Exam.scheduled_at.desc())
            )
            return (
                "exam-schedule-report",
                [
                    "Exam",
                    "Department",
                    "Class",
                    "Subject code",
                    "Subject",
                    "Scheduled at",
                    "Duration (minutes)",
                    "Mode",
                    "Exam status",
                    "Schedule approval",
                ],
                [
                    [
                        exam.title,
                        department_name,
                        class_name,
                        subject_code,
                        subject_name,
                        exam.scheduled_at,
                        exam.duration_minutes,
                        exam.mode,
                        _value(exam.status),
                        _approval_state(exam.schedule_approval_status),
                    ]
                    for exam, class_name, subject_name, subject_code, department_name in rows.all()
                ],
            )
        timetable = await PrincipalService.timetable(
            db, tenant_id, department_ids=department_ids
        )
        return (
            "timetable-report",
            ["Class", "Department", "Day", "Period", "Start", "End", "Subject", "Teacher", "Room", "Type"],
            [
                [
                    item.class_name,
                    item.department_name,
                    item.day_of_week,
                    item.period_number,
                    item.start_time.isoformat(),
                    item.end_time.isoformat(),
                    item.subject_name,
                    item.teacher_name,
                    item.room_no,
                    item.slot_type,
                ]
                for item in timetable.slots
            ],
        )

    @staticmethod
    def csv_content(headers: list[str], rows: list[list[object | None]]) -> str:
        """Create a UTF-8 CSV while neutralising spreadsheet formula injection."""
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([PrincipalService._csv_cell(value) for value in row])
        return stream.getvalue()

    @staticmethod
    def _csv_cell(value: object | None) -> object:
        if value is None:
            return ""
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        text = str(value)
        # Values such as names and department labels are user-authored.  Prefix
        # formula-shaped strings so opening an export cannot execute a formula.
        return f"'{text}" if text[:1] in {"=", "+", "-", "@"} else text

    # ── Tenant-scoped target validators ─────────────────────────────────────

    @staticmethod
    async def _ensure_department(
        db: AsyncSession, tenant_id: uuid.UUID, department_id: uuid.UUID | None
    ) -> Department:
        if department_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Department target is required")
        department = (
            await db.execute(
                select(Department).where(Department.id == department_id, Department.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if department is None:
            # 404 avoids confirming another tenant's identifier.
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Department not found")
        return department

    @staticmethod
    async def _ensure_class(
        db: AsyncSession, tenant_id: uuid.UUID, class_id: uuid.UUID | None
    ) -> SchoolClass:
        if class_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Class target is required")
        school_class = (
            await db.execute(
                select(SchoolClass).where(SchoolClass.id == class_id, SchoolClass.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if school_class is None:
            # 404 avoids confirming another tenant's identifier.
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Class not found")
        return school_class
