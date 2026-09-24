"""Department-scoped HOD workflows (C-HD-01 … C-HD-12).

HOD reads reuse the leadership aggregates in ``PrincipalService`` with a
validated department fence.  HOD-specific actions — subject staffing, mentor
allocation and discussion moderation — operate directly on the canonical ERP
rows and verify that *every* referenced person/class/subject belongs to the
HOD's active departments before a write occurs.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic import AcademicYear, Department, SchoolClass, Subject
from app.models.billing import TenantSetting
from app.models.enrollment import Enrollment, TeacherSubject
from app.models.hod import (
    Assignment,
    AssignmentStatus,
    AttendanceRecord,
    DiscussionThread,
    MentorAssignment,
    MentorScopeType,
    Submission,
    SubmissionStatus,
)
from app.models.principal import AttendanceSession, AttendanceStatus, StaffProfile
from app.models.role import Role, RoleAssignment
from app.models.user import User
from app.schemas.hod import (
    HodAssignmentRow,
    HodAssignmentsOverview,
    HodAttendanceDetailPage,
    HodAttendanceDetailRow,
    HodDashboard,
    HodDiscussionModeration,
    HodDiscussionPage,
    HodDiscussionThread,
    HodMentorAssign,
    HodMentorBoard,
    HodMentorCandidate,
    HodMentorGroup,
    HodMentorMentee,
    HodSubjectOption,
    HodTeacherRow,
    HodTeachersBoard,
    HodTeacherSubject,
    HodTeacherSubjectAssign,
)
from app.schemas.principal import (
    LeadershipNoticeRow,
    PrincipalAttendanceOverview,
    PrincipalExamPage,
    PrincipalNoticeCreate,
    PrincipalNoticeTargets,
    PrincipalResultsOverview,
    PrincipalTargetOption,
    PrincipalTimetable,
)
from app.services.audit_service import AuditService
from app.services.department_scope_service import DepartmentScope, DepartmentScopeService
from app.services.mentor_assignment_service import MentorAssignmentService, MentorTarget
from app.services.principal_service import PrincipalService, _date_window, _value


_PENDING_SUBMISSION_STATUSES = {
    SubmissionStatus.SUBMITTED,
    SubmissionStatus.UNDER_REVIEW,
    SubmissionStatus.RESUBMIT_REQUESTED,
}
_TEACHING_ROLES = {"TEACHER", "HOD", "MENTOR"}


class HodService:
    # ── Scope / common helpers ──────────────────────────────────────────────

    @staticmethod
    async def scope_for_user(db: AsyncSession, hod: User) -> DepartmentScope:
        return await DepartmentScopeService.resolve(
            db,
            hod,
            role_name="HOD",
            include_department_head=True,
            missing_message=(
                "No active department is assigned to this HOD. "
                "Assign the HOD role with a department scope or select the user as a department head."
            ),
        )

    @staticmethod
    def _department_options(scope: DepartmentScope) -> list[PrincipalTargetOption]:
        return [
            PrincipalTargetOption(id=department.id, name=department.name)
            for department in scope.departments
        ]

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
    async def _attendance_threshold(db: AsyncSession, tenant_id: uuid.UUID) -> int | None:
        value = (
            await db.execute(
                select(TenantSetting.value).where(
                    TenantSetting.tenant_id == tenant_id,
                    TenantSetting.key == "attendance_threshold",
                )
            )
        ).scalar_one_or_none()
        try:
            threshold = int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
        return threshold if threshold is not None and 0 <= threshold <= 100 else None

    @staticmethod
    def _scope_classes(tenant_id: uuid.UUID, scope: DepartmentScope):
        return PrincipalService._scoped_class_ids(tenant_id, scope.department_ids)

    # ── C-HD-01 dashboard ───────────────────────────────────────────────────

    @staticmethod
    async def dashboard(db: AsyncSession, hod: User) -> HodDashboard:
        scope = await HodService.scope_for_user(db, hod)
        dashboard = await PrincipalService.dashboard(
            db, hod.tenant_id, department_ids=scope.department_ids
        )
        assignments = await HodService._assignments_overview(db, hod.tenant_id, scope)
        return HodDashboard(
            **dashboard.model_dump(),
            departments=HodService._department_options(scope),
            active_assignments=assignments.active_assignments,
            pending_assignment_reviews=assignments.pending_reviews,
            overdue_assignments=assignments.overdue_assignments,
        )

    # ── C-HD-02 / C-HD-03 attendance ───────────────────────────────────────

    @staticmethod
    async def attendance(
        db: AsyncSession,
        hod: User,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> PrincipalAttendanceOverview:
        scope = await HodService.scope_for_user(db, hod)
        return await PrincipalService.attendance(
            db,
            hod.tenant_id,
            from_date,
            to_date,
            department_ids=scope.department_ids,
        )

    @staticmethod
    async def attendance_detail(
        db: AsyncSession,
        hod: User,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        class_id: uuid.UUID | None = None,
        student_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> HodAttendanceDetailPage:
        if not 1 <= limit <= 100:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="limit must be between 1 and 100")
        if offset < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="offset must be zero or greater")
        scope = await HodService.scope_for_user(db, hod)
        start, end = _date_window(
            from_date,
            to_date,
            default_end=await PrincipalService._tenant_today(db, hod.tenant_id),
        )
        if class_id is not None:
            school_class = await PrincipalService._ensure_class(db, hod.tenant_id, class_id)
            if school_class.department_id not in scope.department_ids:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Class not found")
        statement = HodService._attendance_detail_statement(
            hod.tenant_id,
            scope,
            start,
            end,
            class_id=class_id,
            student_id=student_id,
        )
        total = (
            await db.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar() or 0
        rows = await db.execute(
            statement.order_by(User.name, SchoolClass.name, Subject.code).limit(limit).offset(offset)
        )
        return HodAttendanceDetailPage(
            total=int(total),
            limit=limit,
            offset=offset,
            from_date=start,
            to_date=end,
            items=[HodService._attendance_detail_row(row) for row in rows.all()],
        )

    @staticmethod
    def _attendance_detail_statement(
        tenant_id: uuid.UUID,
        scope: DepartmentScope,
        start: date,
        end: date,
        *,
        class_id: uuid.UUID | None = None,
        student_id: uuid.UUID | None = None,
    ):
        clauses = [
            AttendanceRecord.tenant_id == tenant_id,
            AttendanceSession.tenant_id == tenant_id,
            AttendanceSession.date >= start,
            AttendanceSession.date <= end,
            Department.id.in_(scope.department_ids),
        ]
        if class_id is not None:
            clauses.append(AttendanceSession.class_id == class_id)
        if student_id is not None:
            clauses.append(AttendanceRecord.student_id == student_id)
        return (
            select(
                User.id.label("student_id"),
                User.name.label("student_name"),
                func.coalesce(Enrollment.roll_number, User.student_roll_no).label("roll_number"),
                SchoolClass.id.label("class_id"),
                SchoolClass.name.label("class_name"),
                Subject.id.label("subject_id"),
                Subject.code.label("subject_code"),
                Subject.name.label("subject_name"),
                func.coalesce(
                    func.sum(case((AttendanceRecord.status == AttendanceStatus.PRESENT, 1), else_=0)), 0
                ).label("present_count"),
                func.coalesce(
                    func.sum(case((AttendanceRecord.status == AttendanceStatus.ABSENT, 1), else_=0)), 0
                ).label("absent_count"),
                func.coalesce(
                    func.sum(case((AttendanceRecord.status == AttendanceStatus.LATE, 1), else_=0)), 0
                ).label("late_count"),
                func.coalesce(
                    func.sum(case((AttendanceRecord.status == AttendanceStatus.EXCUSED, 1), else_=0)), 0
                ).label("excused_count"),
            )
            .select_from(AttendanceRecord)
            .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
            .join(Subject, and_(Subject.id == AttendanceSession.subject_id, Subject.tenant_id == tenant_id))
            .join(SchoolClass, and_(SchoolClass.id == AttendanceSession.class_id, SchoolClass.tenant_id == tenant_id))
            .join(Department, and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id))
            .join(User, and_(User.id == AttendanceRecord.student_id, User.tenant_id == tenant_id))
            .outerjoin(
                Enrollment,
                and_(
                    Enrollment.student_id == AttendanceRecord.student_id,
                    Enrollment.class_id == AttendanceSession.class_id,
                    Enrollment.academic_year_id == AttendanceSession.academic_year_id,
                    Enrollment.tenant_id == tenant_id,
                ),
            )
            .where(*clauses)
            .group_by(
                User.id,
                User.name,
                Enrollment.roll_number,
                User.student_roll_no,
                SchoolClass.id,
                SchoolClass.name,
                Subject.id,
                Subject.code,
                Subject.name,
            )
        )

    @staticmethod
    def _attendance_detail_row(row) -> HodAttendanceDetailRow:
        present = int(row.present_count or 0)
        absent = int(row.absent_count or 0)
        late = int(row.late_count or 0)
        excused = int(row.excused_count or 0)
        total = present + absent + late + excused
        return HodAttendanceDetailRow(
            student_id=row.student_id,
            student_name=row.student_name,
            roll_number=row.roll_number,
            class_id=row.class_id,
            class_name=row.class_name,
            subject_id=row.subject_id,
            subject_code=row.subject_code,
            subject_name=row.subject_name,
            present_count=present,
            absent_count=absent,
            late_count=late,
            excused_count=excused,
            attendance_percentage=round((present + late + excused) * 100 / total, 2) if total else None,
        )

    @staticmethod
    async def attendance_export_rows(
        db: AsyncSession,
        hod: User,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        class_id: uuid.UUID | None = None,
    ) -> tuple[str, list[str], list[list[object | None]]]:
        scope = await HodService.scope_for_user(db, hod)
        start, end = _date_window(
            from_date,
            to_date,
            default_end=await PrincipalService._tenant_today(db, hod.tenant_id),
        )
        if class_id is not None:
            school_class = await PrincipalService._ensure_class(db, hod.tenant_id, class_id)
            if school_class.department_id not in scope.department_ids:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Class not found")
        rows = await db.execute(
            HodService._attendance_detail_statement(hod.tenant_id, scope, start, end, class_id=class_id)
            .order_by(User.name, SchoolClass.name, Subject.code)
        )
        detail_rows = [HodService._attendance_detail_row(row) for row in rows.all()]
        return (
            "department-attendance-detail",
            ["Student", "Roll number", "Class", "Subject", "Present", "Absent", "Late", "Excused", "Attendance %"],
            [
                [
                    item.student_name,
                    item.roll_number,
                    item.class_name,
                    f"{item.subject_code} · {item.subject_name}",
                    item.present_count,
                    item.absent_count,
                    item.late_count,
                    item.excused_count,
                    item.attendance_percentage,
                ]
                for item in detail_rows
            ],
        )

    # ── C-HD-04 examinations / C-HD-06 results ─────────────────────────────

    @staticmethod
    async def examinations(db: AsyncSession, hod: User, **filters) -> PrincipalExamPage:
        scope = await HodService.scope_for_user(db, hod)
        return await PrincipalService.examinations(
            db,
            hod.tenant_id,
            department_ids=scope.department_ids,
            **filters,
        )

    @staticmethod
    async def results(db: AsyncSession, hod: User) -> PrincipalResultsOverview:
        scope = await HodService.scope_for_user(db, hod)
        return await PrincipalService.results(
            db, hod.tenant_id, department_ids=scope.department_ids
        )

    # ── C-HD-05 assignments ─────────────────────────────────────────────────

    @staticmethod
    async def assignments(db: AsyncSession, hod: User) -> HodAssignmentsOverview:
        scope = await HodService.scope_for_user(db, hod)
        return await HodService._assignments_overview(db, hod.tenant_id, scope)

    @staticmethod
    async def _assignments_overview(
        db: AsyncSession, tenant_id: uuid.UUID, scope: DepartmentScope
    ) -> HodAssignmentsOverview:
        now = datetime.now(timezone.utc)
        rows = await db.execute(
            select(
                Assignment,
                Subject.code.label("subject_code"),
                Subject.name.label("subject_name"),
                SchoolClass.name.label("class_name"),
                User.name.label("teacher_name"),
                func.count(Submission.id).label("submission_count"),
                func.coalesce(
                    func.sum(
                        case((Submission.status.in_(_PENDING_SUBMISSION_STATUSES), 1), else_=0)
                    ),
                    0,
                ).label("pending_review_count"),
                func.coalesce(
                    func.sum(case((Submission.reviewed_at.is_not(None), 1), else_=0)), 0
                ).label("reviewed_count"),
            )
            .select_from(Assignment)
            .join(Subject, and_(Subject.id == Assignment.subject_id, Subject.tenant_id == tenant_id))
            .join(SchoolClass, and_(SchoolClass.id == Assignment.class_id, SchoolClass.tenant_id == tenant_id))
            .join(Department, and_(Department.id == SchoolClass.department_id, Department.tenant_id == tenant_id))
            .outerjoin(User, and_(User.id == Assignment.teacher_id, User.tenant_id == tenant_id))
            .outerjoin(
                Submission,
                and_(Submission.assignment_id == Assignment.id, Submission.tenant_id == tenant_id),
            )
            .where(
                Assignment.tenant_id == tenant_id,
                Department.id.in_(scope.department_ids),
            )
            .group_by(Assignment.id, Subject.code, Subject.name, SchoolClass.name, User.name)
            .order_by(Assignment.due_date.desc())
        )
        output = []
        for assignment, subject_code, subject_name, class_name, teacher_name, submissions, pending, reviewed in rows.all():
            output.append(
                HodAssignmentRow(
                    id=assignment.id,
                    title=assignment.title,
                    class_id=assignment.class_id,
                    class_name=class_name,
                    subject_id=assignment.subject_id,
                    subject_code=subject_code,
                    subject_name=subject_name,
                    teacher_id=assignment.teacher_id,
                    teacher_name=teacher_name,
                    due_date=assignment.due_date,
                    status=_value(assignment.status) or "DRAFT",
                    total_marks=assignment.total_marks,
                    submission_count=int(submissions or 0),
                    pending_review_count=int(pending or 0),
                    reviewed_count=int(reviewed or 0),
                )
            )
        active = [item for item in output if item.status == AssignmentStatus.PUBLISHED.value]
        return HodAssignmentsOverview(
            active_assignments=len(active),
            pending_reviews=sum(item.pending_review_count for item in output),
            overdue_assignments=sum(item.due_date < now for item in active),
            rows=output,
        )

    # ── C-HD-07 teacher / subject staffing ──────────────────────────────────

    @staticmethod
    def _teacher_ids_statement(tenant_id: uuid.UUID, scope: DepartmentScope):
        scoped_classes = HodService._scope_classes(tenant_id, scope)
        scoped_role_teachers = (
            select(RoleAssignment.user_id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                RoleAssignment.tenant_id == tenant_id,
                RoleAssignment.scope_id.in_(scope.department_ids),
                func.upper(RoleAssignment.scope_type) == "DEPARTMENT",
                Role.name.in_(_TEACHING_ROLES),
                PrincipalService._active_role_clause(),
            )
        )
        subject_teachers = (
            select(TeacherSubject.teacher_id)
            .join(Subject, and_(Subject.id == TeacherSubject.subject_id, Subject.tenant_id == tenant_id))
            .join(SchoolClass, and_(SchoolClass.id == Subject.class_id, SchoolClass.tenant_id == tenant_id))
            .where(
                TeacherSubject.tenant_id == tenant_id,
                SchoolClass.id.in_(scoped_classes),
            )
        )
        return scoped_role_teachers.union(subject_teachers)

    @staticmethod
    async def teachers(db: AsyncSession, hod: User) -> HodTeachersBoard:
        scope = await HodService.scope_for_user(db, hod)
        return await HodService._teachers_board_for_scope(db, hod.tenant_id, scope)

    @staticmethod
    async def _teachers_board_for_scope(
        db: AsyncSession, tenant_id: uuid.UUID, scope: DepartmentScope
    ) -> HodTeachersBoard:
        teacher_ids = list(
            (await db.execute(HodService._teacher_ids_statement(tenant_id, scope))).scalars().all()
        )
        teacher_rows = []
        if teacher_ids:
            teacher_rows = (
                await db.execute(
                    select(User, StaffProfile, Department.name.label("department_name"))
                    .outerjoin(
                        StaffProfile,
                        and_(StaffProfile.user_id == User.id, StaffProfile.tenant_id == tenant_id),
                    )
                    .outerjoin(
                        Department,
                        and_(Department.id == StaffProfile.department_id, Department.tenant_id == tenant_id),
                    )
                    .where(User.id.in_(teacher_ids), User.tenant_id == tenant_id, User.deleted_at.is_(None))
                    .order_by(User.name)
                )
            ).all()
        roles = await PrincipalService._roles_for_users(
            db, tenant_id, [user.id for user, _profile, _department in teacher_rows]
        )
        scope_departments = await PrincipalService._staff_department_scopes(
            db,
            tenant_id,
            [user.id for user, _profile, _department in teacher_rows],
            department_ids=scope.department_ids,
        )
        assignments_by_teacher: dict[uuid.UUID, list[HodTeacherSubject]] = defaultdict(list)
        if teacher_ids:
            subject_rows = await db.execute(
                select(TeacherSubject, Subject, SchoolClass)
                .join(Subject, and_(Subject.id == TeacherSubject.subject_id, Subject.tenant_id == tenant_id))
                .join(SchoolClass, and_(SchoolClass.id == Subject.class_id, SchoolClass.tenant_id == tenant_id))
                .where(
                    TeacherSubject.tenant_id == tenant_id,
                    TeacherSubject.teacher_id.in_(teacher_ids),
                    SchoolClass.department_id.in_(scope.department_ids),
                )
                .order_by(Subject.code)
            )
            for teacher_subject, subject, school_class in subject_rows.all():
                assignments_by_teacher[teacher_subject.teacher_id].append(
                    HodTeacherSubject(
                        teacher_subject_id=teacher_subject.id,
                        subject_id=subject.id,
                        subject_code=subject.code,
                        subject_name=subject.name,
                        class_id=school_class.id,
                        class_name=school_class.name,
                        role_in_subject=teacher_subject.role_in_subject,
                    )
                )
        current_year = await HodService._current_year(db, tenant_id)
        mentor_counts: dict[uuid.UUID, int] = {}
        if current_year and teacher_ids:
            counts = await db.execute(
                select(MentorAssignment.mentor_id, func.count(MentorAssignment.id))
                .where(
                    MentorAssignment.tenant_id == tenant_id,
                    MentorAssignment.academic_year_id == current_year.id,
                    MentorAssignment.is_active.is_(True),
                    MentorAssignment.mentor_id.in_(teacher_ids),
                )
                .group_by(MentorAssignment.mentor_id)
            )
            mentor_counts = {mentor_id: int(count) for mentor_id, count in counts.all()}

        teachers = []
        for user, profile, department_name in teacher_rows:
            subjects = assignments_by_teacher.get(user.id, [])
            fallback = scope_departments.get(user.id)
            department_id = profile.department_id if profile else (fallback[0] if fallback else None)
            name = department_name if profile else (fallback[1] if fallback else None)
            if department_id is None or name is None:
                # `_teacher_ids_statement` only yields scoped teachers; this is
                # defensive against a concurrent scope revocation.
                continue
            teachers.append(
                HodTeacherRow(
                    id=user.id,
                    name=user.name,
                    email=user.email,
                    employee_code=profile.employee_code if profile else user.employee_code,
                    designation=profile.designation if profile else None,
                    department_id=department_id,
                    department_name=name,
                    roles=roles.get(user.id, []),
                    is_active=user.is_active and (profile.is_active if profile else True),
                    subjects=subjects,
                    primary_subject_count=sum(item.role_in_subject == "TEACHER" for item in subjects),
                    total_subject_count=len(subjects),
                    class_count=len({item.class_id for item in subjects}),
                    mentor_count=mentor_counts.get(user.id, 0),
                )
            )

        subject_rows = await db.execute(
            select(
                Subject,
                SchoolClass.name.label("class_name"),
                func.count(TeacherSubject.id).label("assigned_teacher_count"),
            )
            .join(SchoolClass, and_(SchoolClass.id == Subject.class_id, SchoolClass.tenant_id == tenant_id))
            .outerjoin(
                TeacherSubject,
                and_(TeacherSubject.subject_id == Subject.id, TeacherSubject.tenant_id == tenant_id),
            )
            .where(Subject.tenant_id == tenant_id, SchoolClass.department_id.in_(scope.department_ids))
            .group_by(Subject.id, SchoolClass.name)
            .order_by(SchoolClass.name, Subject.code)
        )
        subjects = [
            HodSubjectOption(
                id=subject.id,
                code=subject.code,
                name=subject.name,
                class_id=subject.class_id,
                class_name=class_name,
                assigned_teacher_count=int(teacher_count or 0),
            )
            for subject, class_name, teacher_count in subject_rows.all()
        ]
        return HodTeachersBoard(
            departments=HodService._department_options(scope),
            teachers=teachers,
            subjects=subjects,
            unstaffed_subjects=[item for item in subjects if item.assigned_teacher_count == 0],
        )

    @staticmethod

    async def assign_teacher_subject(
        db: AsyncSession,
        hod: User,
        payload: HodTeacherSubjectAssign,
    ) -> HodTeachersBoard:
        scope = await HodService.scope_for_user(db, hod)
        subject = await HodService._subject_in_scope(db, hod.tenant_id, scope, payload.subject_id)
        if not await HodService._teacher_in_scope(db, hod.tenant_id, scope, payload.teacher_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Teacher not found")
        existing = (
            await db.execute(
                select(TeacherSubject).where(
                    TeacherSubject.tenant_id == hod.tenant_id,
                    TeacherSubject.teacher_id == payload.teacher_id,
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.role_in_subject == payload.role_in_subject.strip().upper(),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            link = TeacherSubject(
                id=uuid.uuid4(),
                tenant_id=hod.tenant_id,
                teacher_id=payload.teacher_id,
                subject_id=subject.id,
                role_in_subject=payload.role_in_subject.strip().upper(),
                assigned_by=hod.id,
            )
            db.add(link)
            try:
                await db.flush()
            except IntegrityError:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="This subject assignment already exists")
            AuditService.record(
                db,
                actor=hod,
                actor_role="HOD",
                action="ASSIGN_TEACHER_SUBJECT",
                entity="TeacherSubject",
                entity_id=link.id,
                tenant_id=hod.tenant_id,
                new_value={"teacher_id": str(payload.teacher_id), "subject_id": str(subject.id), "role": link.role_in_subject},
            )
        return await HodService.teachers(db, hod)

    @staticmethod
    async def remove_teacher_subject(
        db: AsyncSession, hod: User, teacher_subject_id: uuid.UUID
    ) -> HodTeachersBoard:
        scope = await HodService.scope_for_user(db, hod)
        link = (
            await db.execute(
                select(TeacherSubject)
                .join(Subject, Subject.id == TeacherSubject.subject_id)
                .join(SchoolClass, SchoolClass.id == Subject.class_id)
                .where(
                    TeacherSubject.id == teacher_subject_id,
                    TeacherSubject.tenant_id == hod.tenant_id,
                    Subject.tenant_id == hod.tenant_id,
                    SchoolClass.department_id.in_(scope.department_ids),
                )
            )
        ).scalar_one_or_none()
        if link is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Teacher subject assignment not found")
        await db.delete(link)
        AuditService.record(
            db,
            actor=hod,
            actor_role="HOD",
            action="REMOVE_TEACHER_SUBJECT",
            entity="TeacherSubject",
            entity_id=link.id,
            tenant_id=hod.tenant_id,
            old_value={"teacher_id": str(link.teacher_id), "subject_id": str(link.subject_id), "role": link.role_in_subject},
        )
        return await HodService.teachers(db, hod)

    @staticmethod
    async def _subject_in_scope(
        db: AsyncSession, tenant_id: uuid.UUID, scope: DepartmentScope, subject_id: uuid.UUID
    ) -> Subject:
        subject = (
            await db.execute(
                select(Subject)
                .join(SchoolClass, SchoolClass.id == Subject.class_id)
                .where(
                    Subject.id == subject_id,
                    Subject.tenant_id == tenant_id,
                    SchoolClass.tenant_id == tenant_id,
                    SchoolClass.department_id.in_(scope.department_ids),
                )
            )
        ).scalar_one_or_none()
        if subject is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Subject not found")
        return subject

    @staticmethod
    async def _teacher_in_scope(
        db: AsyncSession, tenant_id: uuid.UUID, scope: DepartmentScope, teacher_id: uuid.UUID
    ) -> bool:
        result = await db.execute(
            select(User.id)
            .where(
                User.id == teacher_id,
                User.tenant_id == tenant_id,
                User.deleted_at.is_(None),
                User.id.in_(HodService._teacher_ids_statement(tenant_id, scope)),
            )
        )
        return result.scalar_one_or_none() is not None

    # ── C-HD-08 mentor assignments ──────────────────────────────────────────

    @staticmethod
    async def mentors(db: AsyncSession, hod: User) -> HodMentorBoard:
        scope = await HodService.scope_for_user(db, hod)
        return await HodService._mentor_board(db, hod.tenant_id, scope)

    @staticmethod
    async def _mentor_board(
        db: AsyncSession, tenant_id: uuid.UUID, scope: DepartmentScope
    ) -> HodMentorBoard:
        current_year = await HodService._current_year(db, tenant_id)
        teachers_board = await HodService._teachers_for_scope(db, tenant_id, scope, current_year)
        mentors = [teacher for teacher in teachers_board if "MENTOR" in teacher.roles and teacher.is_active]
        threshold = await HodService._attendance_threshold(db, tenant_id)
        students = await HodService._students_for_scope(db, tenant_id, scope, current_year)
        attendance = await HodService._student_attendance(db, tenant_id, scope)

        mentor_ids = {mentor.id for mentor in mentors}
        student_by_id = {student[0].id: student for student in students}
        assignments = []
        if current_year and student_by_id:
            assignments = (
                await db.execute(
                    select(MentorAssignment)
                    .where(
                        MentorAssignment.tenant_id == tenant_id,
                        MentorAssignment.academic_year_id == current_year.id,
                        MentorAssignment.is_active.is_(True),
                        MentorAssignment.student_id.in_(student_by_id),
                    )
                )
            ).scalars().all()
        grouped: dict[uuid.UUID, list[MentorAssignment]] = defaultdict(list)
        for assignment in assignments:
            if assignment.mentor_id in mentor_ids and assignment.student_id in student_by_id:
                grouped[assignment.mentor_id].append(assignment)

        groups = []
        assigned_student_ids: set[uuid.UUID] = set()
        for mentor in mentors:
            mentees = []
            for assignment in sorted(grouped.get(mentor.id, []), key=lambda item: student_by_id[item.student_id][0].name.casefold()):
                student, enrollment, school_class = student_by_id[assignment.student_id]
                percentage = attendance.get(student.id)
                mentees.append(
                    HodMentorMentee(
                        mentor_assignment_id=assignment.id,
                        student_id=student.id,
                        student_name=student.name,
                        roll_number=enrollment.roll_number or student.student_roll_no,
                        class_id=school_class.id,
                        class_name=school_class.name,
                        assigned_at=assignment.assigned_at,
                        attendance_percentage=percentage,
                    )
                )
                assigned_student_ids.add(student.id)
            groups.append(
                HodMentorGroup(
                    mentor_id=mentor.id,
                    mentor_name=mentor.name,
                    designation=mentor.designation,
                    email=mentor.email,
                    mentees=mentees,
                    at_risk_count=sum(
                        1
                        for mentee in mentees
                        if threshold is not None
                        and mentee.attendance_percentage is not None
                        and mentee.attendance_percentage < threshold
                    ),
                )
            )

        unassigned = []
        for student, enrollment, school_class in students:
            if student.id in assigned_student_ids:
                continue
            unassigned.append(
                HodMentorMentee(
                    student_id=student.id,
                    student_name=student.name,
                    roll_number=enrollment.roll_number or student.student_roll_no,
                    class_id=school_class.id,
                    class_name=school_class.name,
                    assigned_at=None,
                    attendance_percentage=attendance.get(student.id),
                )
            )
        return HodMentorBoard(
            departments=HodService._department_options(scope),
            academic_year=current_year.name if current_year else None,
            attendance_threshold=threshold,
            mentor_role_in_use=bool(mentors),
            groups=groups,
            unassigned_students=sorted(unassigned, key=lambda item: item.student_name.casefold()),
            eligible_teachers=[
                HodMentorCandidate(
                    id=teacher.id,
                    name=teacher.name,
                    designation=teacher.designation,
                    is_mentor="MENTOR" in teacher.roles,
                )
                for teacher in teachers_board
            ],
        )

    @staticmethod
    async def assign_mentor(
        db: AsyncSession, hod: User, payload: HodMentorAssign
    ) -> HodMentorBoard:
        """Student-scope assignment inside the HOD's departments.

        The HOD cannot grant roles, so the mentor must already hold MENTOR.
        Team / class scopes are owned by the Academic Coordinator and
        Institution Admin (``/institution/mentors``); all three consoles share
        ``MentorAssignmentService`` so the one-active-mentor rule is identical.
        """
        scope = await HodService.scope_for_user(db, hod)
        current_year = await MentorAssignmentService.require_current_year(db, hod.tenant_id)
        student_rows = await HodService._students_for_scope(db, hod.tenant_id, scope, current_year, student_id=payload.student_id)
        if not student_rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
        teachers = await HodService._teachers_for_scope(db, hod.tenant_id, scope, current_year)
        if not any(teacher.id == payload.mentor_id and "MENTOR" in teacher.roles and teacher.is_active for teacher in teachers):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Active mentor not found")
        mentor, _roles = await MentorAssignmentService.mentor_candidate(db, hod.tenant_id, payload.mentor_id, require_mentor_role=True)
        student, _enrollment, school_class = student_rows[0]
        target = MentorTarget(MentorScopeType.STUDENT, student.id, student.name, school_class.id, school_class.name, (student.id,))
        await MentorAssignmentService.assign(
            db, tenant_id=hod.tenant_id, year=current_year, mentor=mentor, target=target,
            notes=payload.notes, actor=hod, actor_role="HOD",
        )
        return await HodService._mentor_board(db, hod.tenant_id, scope)

    @staticmethod
    async def remove_mentor_assignment(
        db: AsyncSession, hod: User, assignment_id: uuid.UUID
    ) -> HodMentorBoard:
        scope = await HodService.scope_for_user(db, hod)
        current_year = await HodService._current_year(db, hod.tenant_id)
        if current_year is None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="No current academic year")
        assignment = (
            await db.execute(
                select(MentorAssignment)
                .join(Enrollment, Enrollment.student_id == MentorAssignment.student_id)
                .join(SchoolClass, SchoolClass.id == Enrollment.class_id)
                .where(
                    MentorAssignment.id == assignment_id,
                    MentorAssignment.tenant_id == hod.tenant_id,
                    MentorAssignment.academic_year_id == current_year.id,
                    MentorAssignment.is_active.is_(True),
                    Enrollment.tenant_id == hod.tenant_id,
                    Enrollment.academic_year_id == current_year.id,
                    SchoolClass.department_id.in_(scope.department_ids),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if assignment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mentor assignment not found")
        await MentorAssignmentService.remove(db, assignment=assignment, actor=hod, actor_role="HOD")
        return await HodService._mentor_board(db, hod.tenant_id, scope)

    @staticmethod
    async def _teachers_for_scope(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        scope: DepartmentScope,
        current_year: AcademicYear | None,
    ) -> list[HodTeacherRow]:
        # The board is the canonical teacher query. Mentor logic only needs
        # identities/roles, so it selects the already scoped teacher rows.
        del current_year
        return (await HodService._teachers_board_for_scope(db, tenant_id, scope)).teachers

    @staticmethod
    async def _students_for_scope(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        scope: DepartmentScope,
        current_year: AcademicYear | None,
        *,
        student_id: uuid.UUID | None = None,
    ):
        if current_year is None:
            return []
        clauses = [
            Enrollment.tenant_id == tenant_id,
            Enrollment.academic_year_id == current_year.id,
            SchoolClass.department_id.in_(scope.department_ids),
        ]
        if student_id:
            clauses.append(Enrollment.student_id == student_id)
        rows = await db.execute(
            select(User, Enrollment, SchoolClass)
            .join(Enrollment, and_(Enrollment.student_id == User.id, Enrollment.tenant_id == tenant_id))
            .join(SchoolClass, and_(SchoolClass.id == Enrollment.class_id, SchoolClass.tenant_id == tenant_id))
            .where(*clauses)
            .order_by(User.name)
        )
        # `student_enrollments.status` is an enum in the raw PostgreSQL schema
        # but VARCHAR in the migration path. Filter after the tenant/class fence
        # instead of binding a mismatched enum literal at the database edge.
        return [row for row in rows.all() if _value(row[1].status) == "ACTIVE"]

    @staticmethod
    async def _student_attendance(
        db: AsyncSession, tenant_id: uuid.UUID, scope: DepartmentScope
    ) -> dict[uuid.UUID, float]:
        rows = await db.execute(
            select(
                AttendanceRecord.student_id,
                func.coalesce(
                    func.sum(case((AttendanceRecord.status != AttendanceStatus.ABSENT, 1), else_=0)), 0
                ).label("attended"),
                func.count(AttendanceRecord.id).label("total"),
            )
            .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
            .join(SchoolClass, SchoolClass.id == AttendanceSession.class_id)
            .where(
                AttendanceRecord.tenant_id == tenant_id,
                AttendanceSession.tenant_id == tenant_id,
                SchoolClass.tenant_id == tenant_id,
                SchoolClass.department_id.in_(scope.department_ids),
            )
            .group_by(AttendanceRecord.student_id)
        )
        return {
            student_id: round(int(attended or 0) * 100 / int(total), 2)
            for student_id, attended, total in rows.all()
            if total
        }

    # ── C-HD-09 / C-HD-10 notices ───────────────────────────────────────────

    @staticmethod
    async def notices(db: AsyncSession, hod: User, **filters):
        scope = await HodService.scope_for_user(db, hod)
        page = await PrincipalService.notices(
            db,
            hod.tenant_id,
            department_ids=scope.department_ids,
            **filters,
        )
        from app.schemas.hod import HodNoticePage
        return HodNoticePage(
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            items=[
                LeadershipNoticeRow.model_validate(item.model_dump(exclude={"read_count"}))
                for item in page.items
            ],
        )

    @staticmethod
    async def notice_detail(db: AsyncSession, hod: User, notice_id: uuid.UUID):
        scope = await HodService.scope_for_user(db, hod)
        detail = await PrincipalService.notice_detail(
            db,
            hod.tenant_id,
            notice_id,
            department_ids=scope.department_ids,
            include_readers=False,
        )
        from app.schemas.hod import HodNoticeDetail
        return HodNoticeDetail.model_validate(detail.model_dump(exclude={"read_count", "readers"}))

    @staticmethod
    async def create_notice(db: AsyncSession, hod: User, payload: PrincipalNoticeCreate):
        if payload.is_pinned:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the Principal can pin notices")
        scope = await HodService.scope_for_user(db, hod)
        detail = await PrincipalService.create_notice(
            db,
            hod.tenant_id,
            hod,
            payload,
            department_ids=scope.department_ids,
            allow_institution=False,
            actor_role="HOD",
        )
        from app.schemas.hod import HodNoticeDetail
        return HodNoticeDetail.model_validate(detail.model_dump(exclude={"read_count", "readers"}))

    @staticmethod
    async def notice_targets(db: AsyncSession, hod: User) -> PrincipalNoticeTargets:
        scope = await HodService.scope_for_user(db, hod)
        return await PrincipalService.notice_targets(
            db, hod.tenant_id, department_ids=scope.department_ids
        )

    # ── C-HD-11 discussion moderation ───────────────────────────────────────

    @staticmethod
    def _discussion_scope_clause(tenant_id: uuid.UUID, scope: DepartmentScope):
        class_ids = HodService._scope_classes(tenant_id, scope)
        subject_ids = (
            select(Subject.id)
            .join(SchoolClass, and_(SchoolClass.id == Subject.class_id, SchoolClass.tenant_id == tenant_id))
            .where(Subject.tenant_id == tenant_id, SchoolClass.department_id.in_(scope.department_ids))
        )
        return or_(
            and_(func.upper(DiscussionThread.scope_type) == "DEPARTMENT", DiscussionThread.scope_id.in_(scope.department_ids)),
            and_(func.upper(DiscussionThread.scope_type) == "CLASS", DiscussionThread.scope_id.in_(class_ids)),
            and_(func.upper(DiscussionThread.scope_type) == "SUBJECT", DiscussionThread.scope_id.in_(subject_ids)),
        )

    @staticmethod
    async def discussion(
        db: AsyncSession,
        hod: User,
        *,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> HodDiscussionPage:
        if not 1 <= limit <= 100 or offset < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid pagination")
        scope = await HodService.scope_for_user(db, hod)
        clauses = [
            DiscussionThread.tenant_id == hod.tenant_id,
            DiscussionThread.deleted_at.is_(None),
            HodService._discussion_scope_clause(hod.tenant_id, scope),
        ]
        if query and query.strip():
            needle = f"%{query.strip().lower()}%"
            clauses.append(or_(func.lower(DiscussionThread.title).like(needle), func.lower(DiscussionThread.body).like(needle)))
        total = (
            await db.execute(select(func.count(DiscussionThread.id)).where(*clauses))
        ).scalar() or 0
        rows = await db.execute(
            select(DiscussionThread, User.name.label("author_name"))
            .outerjoin(User, and_(User.id == DiscussionThread.author_id, User.tenant_id == hod.tenant_id))
            .where(*clauses)
            .order_by(DiscussionThread.is_pinned.desc(), DiscussionThread.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return HodDiscussionPage(
            total=int(total),
            limit=limit,
            offset=offset,
            items=[
                HodDiscussionThread(
                    id=thread.id,
                    title=thread.title,
                    body=thread.body,
                    author_name=author_name,
                    scope_type=thread.scope_type,
                    scope_id=thread.scope_id,
                    tags=thread.tags or [],
                    is_pinned=thread.is_pinned,
                    is_locked=thread.is_locked,
                    is_resolved=thread.is_resolved,
                    reply_count=thread.reply_count,
                    upvote_count=thread.upvote_count,
                    created_at=thread.created_at,
                    updated_at=thread.updated_at,
                )
                for thread, author_name in rows.all()
            ],
        )

    @staticmethod
    async def moderate_discussion(
        db: AsyncSession,
        hod: User,
        thread_id: uuid.UUID,
        payload: HodDiscussionModeration,
    ) -> HodDiscussionThread:
        scope = await HodService.scope_for_user(db, hod)
        thread = (
            await db.execute(
                select(DiscussionThread)
                .where(
                    DiscussionThread.id == thread_id,
                    DiscussionThread.tenant_id == hod.tenant_id,
                    DiscussionThread.deleted_at.is_(None),
                    HodService._discussion_scope_clause(hod.tenant_id, scope),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if thread is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Discussion thread not found")
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
            actor=hod,
            actor_role="HOD",
            action=f"MODERATE_DISCUSSION_{payload.action}",
            entity="DiscussionThread",
            entity_id=thread.id,
            tenant_id=hod.tenant_id,
            old_value=before,
            new_value={
                "is_pinned": thread.is_pinned,
                "is_locked": thread.is_locked,
                "deleted": thread.deleted_at is not None,
            },
        )
        return HodDiscussionThread(
            id=thread.id,
            title=thread.title,
            body=thread.body,
            author_name=None,
            scope_type=thread.scope_type,
            scope_id=thread.scope_id,
            tags=thread.tags or [],
            is_pinned=thread.is_pinned,
            is_locked=thread.is_locked,
            is_resolved=thread.is_resolved,
            reply_count=thread.reply_count,
            upvote_count=thread.upvote_count,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )

    # ── C-HD-12 timetable ───────────────────────────────────────────────────

    @staticmethod
    async def timetable(db: AsyncSession, hod: User) -> PrincipalTimetable:
        scope = await HodService.scope_for_user(db, hod)
        return await PrincipalService.timetable(
            db, hod.tenant_id, department_ids=scope.department_ids
        )

    # ── Scoped CSV exports ─────────────────────────────────────────────────

    @staticmethod
    async def export_rows(
        db: AsyncSession,
        hod: User,
        kind: str,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[str, list[str], list[list[object | None]]]:
        scope = await HodService.scope_for_user(db, hod)
        return await PrincipalService.export_rows(
            db,
            hod.tenant_id,
            kind,
            from_date=from_date,
            to_date=to_date,
            department_ids=scope.department_ids,
        )
