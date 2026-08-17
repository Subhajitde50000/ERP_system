"""
Services — Institution Admin management

The day-to-day API behind the institution admin role: dashboard counts,
academic structure (years, departments, classes, subjects), people
(staff/users, students, enrollments), modules, settings and the institution
profile. Everything is scoped to the admin's tenant and reads RBAC from
`role_assignments`.

Staff/student invites use the existing reset-token flow (SYSTEM-FLOW §4.1):
the new user is created with no password and a one-time reset token, and a
"set your password" email is queued in the outbox. The platform never knows
anyone's password.
"""

import csv
import io
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings as get_app_settings
from app.models.academic import AcademicYear, Department, SchoolClass, Subject, ClassGrade, ClassProgram
from app.models.billing import Subscription, TenantModule, TenantSetting
from app.models.principal import StaffProfile
from app.models.catalog import Module, Plan
from app.models.enrollment import Enrollment, TeacherSubject
from app.models.role import Role, RoleAssignment
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.institution import (
    AcademicYearCreate,
    AcademicYearOut,
    AcademicYearUpdate,
    BulkUploadResult,
    BulkUploadRowIssue,
    ClassCreate,
    ClassGradeCreate,
    ClassGradeOut,
    ClassOut,
    ClassProgramCreate,
    ClassProgramOut,
    ClassUpdate,
    DashboardSummary,
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    EnrollmentCreate,
    EnrollmentOut,
    InstitutionProfileOut,
    InstitutionProfileUpdate,
    ModuleOut,
    SectionOut,
    SettingsOut,
    SettingsUpdate,
    StaffInvite,
    StaffOut,
    StaffUpdate,
    StudentCreate,
    StudentOut,
    StudentUpdate,
    SubjectCreate,
    SubjectOut,
    SubjectUpdate,
)
from app.services.audit_service import AuditService
from app.services.mailer import queue_email
from app.utils.security import generate_secure_token, hash_password, hash_token

ONBOARDING_KEY = "onboarding"
ONBOARDING_DONE_KEY = "onboarding.completed"

# Bulk student import limits — 2 MB / 10 000 rows keeps one upload bounded.
BULK_MAX_FILE_BYTES = 2 * 1024 * 1024
BULK_MAX_ROWS = 10_000

# Default password for newly added staff members
DEFAULT_STAFF_PASSWORD = "password1234!"

# SECURITY: Do NOT use a shared constant for student initial passwords.
# Each account receives a unique cryptographically-random password so that
# knowing one student's roll number does not grant access to any account.
# Credentials are distributed out-of-band (printed card, SMS, etc.).
# Students change their password via the forgot-password / reset flow.
def _random_student_password() -> str:
    """Return a per-user unguessable initial password (never shared across accounts)."""
    return generate_secure_token(32)

# Roles an Institution Admin may NOT invite or grant: platform roles
# (SUPER_ADMIN & co) are out of scope, INSTITUTION_ADMIN is the console owner,
# and STUDENT/PARENT have their own non-staff flows.
NON_INVITABLE_ROLES = frozenset({"INSTITUTION_ADMIN", "STUDENT", "PARENT"})

class InstitutionService:
    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    async def _tenant(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
        res = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = res.scalar_one_or_none()
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        return tenant

    @staticmethod
    async def _flush_unique(db: AsyncSession, message: str) -> None:
        """Flush, translating a unique-constraint violation into a 409 Conflict
        so duplicates return a clean error instead of a 500."""
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, detail=message)

    @staticmethod
    async def _current_year(db: AsyncSession, tenant_id: uuid.UUID) -> AcademicYear | None:
        res = await db.execute(
            select(AcademicYear)
            .where(AcademicYear.tenant_id == tenant_id)
            .order_by(AcademicYear.is_current.desc(), AcademicYear.start_date.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def _enabled_modules(db: AsyncSession, tenant_id: uuid.UUID) -> list[str]:
        """Enabled module keys. Core modules are always on even when no
        tenant_modules row exists yet (consistent with list_modules)."""
        cat_res = await db.execute(select(Module.key, Module.is_core))
        catalog = {row[0]: row[1] for row in cat_res.all()}
        res = await db.execute(
            select(TenantModule.module_key, TenantModule.is_enabled).where(
                TenantModule.tenant_id == tenant_id
            )
        )
        tm = {row[0]: row[1] for row in res.all()}
        return [key for key, is_core in catalog.items() if tm.get(key, is_core)]

    @staticmethod
    async def _counts(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, int]:
        async def count(stmt) -> int:
            res = await db.execute(stmt)
            return res.scalar() or 0

        return {
            "academic_years": await count(select(func.count(AcademicYear.id)).where(AcademicYear.tenant_id == tenant_id)),
            "departments": await count(select(func.count(Department.id)).where(Department.tenant_id == tenant_id, Department.is_active == True)),  # noqa: E712
            "classes": await count(select(func.count(SchoolClass.id)).where(SchoolClass.tenant_id == tenant_id, SchoolClass.is_active == True)),  # noqa: E712
            "subjects": await count(select(func.count(Subject.id)).where(Subject.tenant_id == tenant_id, Subject.is_active == True)),  # noqa: E712
            "staff": await count(
                select(func.count(User.id.distinct()))
                .select_from(User)
                .join(RoleAssignment, RoleAssignment.user_id == User.id)
                .join(Role, Role.id == RoleAssignment.role_id)
                .where(User.tenant_id == tenant_id, User.deleted_at == None, Role.name != "STUDENT")  # noqa: E712
            ),
            "students": await count(
                select(func.count(User.id.distinct()))
                .select_from(User)
                .join(RoleAssignment, RoleAssignment.user_id == User.id)
                .join(Role, Role.id == RoleAssignment.role_id)
                .where(User.tenant_id == tenant_id, User.deleted_at == None, Role.name == "STUDENT")  # noqa: E712
            ),
        }

    # ── Dashboard ────────────────────────────────────────────────────────────

    @staticmethod
    async def dashboard(db: AsyncSession, tenant_id: uuid.UUID) -> DashboardSummary:
        tenant = await InstitutionService._tenant(db, tenant_id)
        year = await InstitutionService._current_year(db, tenant_id)
        modules = await InstitutionService._enabled_modules(db, tenant_id)
        done = await InstitutionService._is_onboarded(db, tenant_id)
        return DashboardSummary(
            tenant_id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            type=tenant.type.value,
            academic_year=year.name if year else None,
            counts=await InstitutionService._counts(db, tenant_id),
            enabled_modules=modules,
            onboarding_complete=done,
        )

    @staticmethod
    async def _is_onboarded(db: AsyncSession, tenant_id: uuid.UUID) -> bool:
        res = await db.execute(
            select(TenantSetting.value).where(
                TenantSetting.tenant_id == tenant_id,
                TenantSetting.key == ONBOARDING_DONE_KEY,
            )
        )
        return (res.scalar() or "").lower() == "true"

    # ── Academic years ───────────────────────────────────────────────────────

    @staticmethod
    async def list_years(db: AsyncSession, tenant_id: uuid.UUID) -> list[AcademicYearOut]:
        res = await db.execute(
            select(AcademicYear)
            .where(AcademicYear.tenant_id == tenant_id)
            .order_by(AcademicYear.start_date.desc())
        )
        return [_year_out(y) for y in res.scalars().all()]

    @staticmethod
    async def create_year(db: AsyncSession, tenant_id: uuid.UUID, payload: AcademicYearCreate) -> AcademicYearOut:
        if payload.start_date >= payload.end_date:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="start_date must be before end_date")
        # Exactly one current year per tenant.
        if payload.is_current:
            await InstitutionService._unset_current_year(db, tenant_id)
        year = AcademicYear(
            id=uuid.uuid4(), tenant_id=tenant_id, name=payload.name,
            start_date=payload.start_date, end_date=payload.end_date, is_current=payload.is_current,
        )
        db.add(year)
        await InstitutionService._flush_unique(db, "An academic year with this name already exists")
        return _year_out(year)

    @staticmethod
    async def update_year(db: AsyncSession, tenant_id: uuid.UUID, year_id: uuid.UUID, payload: AcademicYearUpdate) -> AcademicYearOut:
        year = await InstitutionService._load_year(db, tenant_id, year_id)
        if payload.start_date and payload.end_date and payload.start_date >= payload.end_date:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="start_date must be before end_date")
        for f in ("name", "start_date", "end_date"):
            v = getattr(payload, f)
            if v is not None:
                setattr(year, f, v)
        if payload.is_current:
            await InstitutionService._unset_current_year(db, tenant_id, except_id=year.id)
            year.is_current = True
        elif payload.is_current is False:
            year.is_current = False
        await db.flush()
        return _year_out(year)

    @staticmethod
    async def delete_year(db: AsyncSession, tenant_id: uuid.UUID, year_id: uuid.UUID) -> None:
        year = await InstitutionService._load_year(db, tenant_id, year_id)
        if year.is_current:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Cannot delete the current academic year")
        await db.delete(year)

    @staticmethod
    async def _load_year(db, tenant_id, year_id) -> AcademicYear:
        res = await db.execute(select(AcademicYear).where(AcademicYear.id == year_id, AcademicYear.tenant_id == tenant_id))
        year = res.scalar_one_or_none()
        if year is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Academic year not found")
        return year

    @staticmethod
    async def _unset_current_year(db, tenant_id, except_id=None) -> None:
        res = await db.execute(select(AcademicYear).where(AcademicYear.tenant_id == tenant_id, AcademicYear.is_current == True))  # noqa: E712
        for y in res.scalars().all():
            if except_id and y.id == except_id:
                continue
            y.is_current = False

    # ── Departments ──────────────────────────────────────────────────────────

    @staticmethod
    async def list_departments(db: AsyncSession, tenant_id: uuid.UUID) -> list[DepartmentOut]:
        res = await db.execute(
            select(Department).where(Department.tenant_id == tenant_id).order_by(Department.name)
        )
        departments = list(res.scalars().all())
        names = await InstitutionService._user_names(db, [d.hod_id for d in departments if d.hod_id])
        class_counts = await InstitutionService._count_classes_by_dept(db, tenant_id)
        staff_counts = await InstitutionService._count_staff_by_dept(db, tenant_id)
        return [
            DepartmentOut(
                id=d.id, name=d.name, code=d.code, description=d.description,
                hod_id=d.hod_id, hod_name=names.get(d.hod_id), is_active=d.is_active,
                class_count=class_counts.get(d.id, 0), staff_count=staff_counts.get(d.id, 0),
            )
            for d in departments
        ]

    @staticmethod
    async def create_department(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        payload: DepartmentCreate,
        *,
        actor: User | None = None,
    ) -> DepartmentOut:
        if payload.hod_id is not None:
            await InstitutionService._assert_user_in_tenant(db, tenant_id, payload.hod_id)
        dept = Department(
            id=uuid.uuid4(), tenant_id=tenant_id, name=payload.name, code=payload.code.upper(),
            description=payload.description, hod_id=payload.hod_id, is_active=True,
        )
        db.add(dept)
        await InstitutionService._flush_unique(db, "A department with this code already exists")
        if dept.hod_id is not None:
            await InstitutionService._ensure_hod_department_scope(
                db, tenant_id, dept.hod_id, dept.id, actor=actor
            )
        return (await InstitutionService.list_departments(db, tenant_id))[0]

    @staticmethod
    async def update_department(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        dept_id: uuid.UUID,
        payload: DepartmentUpdate,
        *,
        actor: User | None = None,
    ) -> DepartmentOut:
        res = await db.execute(select(Department).where(Department.id == dept_id, Department.tenant_id == tenant_id))
        dept = res.scalar_one_or_none()
        if dept is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Department not found")
        previous_hod_id = dept.hod_id
        if "hod_id" in payload.model_fields_set:
            if payload.hod_id is not None:
                await InstitutionService._assert_user_in_tenant(db, tenant_id, payload.hod_id)
            dept.hod_id = payload.hod_id
        for f in ("name", "code", "description", "is_active"):
            v = getattr(payload, f)
            if v is not None:
                if f == "code":
                    v = v.upper()
                setattr(dept, f, v)
        await db.flush()
        if previous_hod_id is not None and previous_hod_id != dept.hod_id:
            await InstitutionService._deactivate_hod_department_scope(
                db, tenant_id, previous_hod_id, dept.id, actor=actor
            )
        if dept.hod_id is not None:
            await InstitutionService._ensure_hod_department_scope(
                db, tenant_id, dept.hod_id, dept.id, actor=actor
            )
        rows = await InstitutionService.list_departments(db, tenant_id)
        return next((r for r in rows if r.id == dept_id), rows[0])

    @staticmethod
    async def delete_department(db: AsyncSession, tenant_id: uuid.UUID, dept_id: uuid.UUID) -> None:
        res = await db.execute(select(Department).where(Department.id == dept_id, Department.tenant_id == tenant_id))
        dept = res.scalar_one_or_none()
        if dept is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Department not found")
        cls = await db.execute(select(SchoolClass.id).where(SchoolClass.department_id == dept_id).limit(1))
        if cls.scalar_one_or_none() is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Cannot delete department: classes are still attached to this department. Move or delete them first.")
        prog = await db.execute(select(ClassProgram.id).where(ClassProgram.department_id == dept_id).limit(1))
        if prog.scalar_one_or_none() is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Cannot delete department: academic programs are still attached to this department. Move or delete them first.")
        await db.delete(dept)

    # ── Classes ──────────────────────────────────────────────────────────────

    @staticmethod
    async def list_classes(db: AsyncSession, tenant_id: uuid.UUID) -> list[ClassOut]:
        res = await db.execute(
            select(SchoolClass).where(SchoolClass.tenant_id == tenant_id).order_by(SchoolClass.name)
        )
        classes = list(res.scalars().all())
        dept_names = await InstitutionService._entity_names(db, Department, [c.department_id for c in classes])
        year_names = await InstitutionService._entity_names(db, AcademicYear, [c.academic_year_id for c in classes])
        teacher_names = await InstitutionService._user_names(db, [c.class_teacher_id for c in classes if c.class_teacher_id])
        enrolled = await InstitutionService._count_enrolled_by_class(db, tenant_id)
        subject_counts = await InstitutionService._count_subjects_by_class(db, tenant_id)
        return [
            ClassOut(
                id=c.id, name=c.name, code=c.code, department_id=c.department_id,
                department_name=dept_names.get(c.department_id), academic_year_id=c.academic_year_id,
                academic_year_name=year_names.get(c.academic_year_id), max_strength=c.max_strength,
                room_no=c.room_no, class_teacher_id=c.class_teacher_id,
                class_teacher_name=teacher_names.get(c.class_teacher_id), is_active=c.is_active,
                enrolled_count=enrolled.get(c.id, 0), subject_count=subject_counts.get(c.id, 0),
                grade_id=c.grade_id, program_id=c.program_id, section_label=c.section_label,
            )
            for c in classes
        ]

    @staticmethod
    async def create_class(db: AsyncSession, tenant_id: uuid.UUID, payload: ClassCreate) -> ClassOut:
        await InstitutionService._assert_dept(db, tenant_id, payload.department_id)
        await InstitutionService._assert_year(db, tenant_id, payload.academic_year_id)
        if payload.class_teacher_id is not None:
            await InstitutionService._assert_user_in_tenant(db, tenant_id, payload.class_teacher_id)
        cls = SchoolClass(
            id=uuid.uuid4(), tenant_id=tenant_id, name=payload.name, code=payload.code.upper(),
            department_id=payload.department_id, academic_year_id=payload.academic_year_id,
            max_strength=payload.max_strength, room_no=payload.room_no, class_teacher_id=payload.class_teacher_id,
            is_active=True,
        )
        db.add(cls)
        await InstitutionService._flush_unique(db, "A class with this code already exists")
        rows = await InstitutionService.list_classes(db, tenant_id)
        return next((r for r in rows if r.name == payload.name and r.code == payload.code.upper()), rows[0])

    @staticmethod
    async def update_class(db: AsyncSession, tenant_id: uuid.UUID, class_id: uuid.UUID, payload: ClassUpdate) -> ClassOut:
        res = await db.execute(select(SchoolClass).where(SchoolClass.id == class_id, SchoolClass.tenant_id == tenant_id))
        cls = res.scalar_one_or_none()
        if cls is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Class not found")
        if payload.class_teacher_id is not None:
            await InstitutionService._assert_user_in_tenant(db, tenant_id, payload.class_teacher_id)
            cls.class_teacher_id = payload.class_teacher_id
        for f in ("name", "max_strength", "room_no", "is_active"):
            v = getattr(payload, f)
            if v is not None:
                setattr(cls, f, v)
        await db.flush()
        rows = await InstitutionService.list_classes(db, tenant_id)
        return next((r for r in rows if r.id == class_id), rows[0])

    @staticmethod
    async def delete_class(db: AsyncSession, tenant_id: uuid.UUID, class_id: uuid.UUID) -> None:
        res = await db.execute(select(SchoolClass).where(SchoolClass.id == class_id, SchoolClass.tenant_id == tenant_id))
        cls = res.scalar_one_or_none()
        if cls is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Class not found")
        await db.delete(cls)

    # ── Subjects ─────────────────────────────────────────────────────────────

    @staticmethod
    async def list_subjects(db: AsyncSession, tenant_id: uuid.UUID) -> list[SubjectOut]:
        res = await db.execute(
            select(Subject).where(Subject.tenant_id == tenant_id).order_by(Subject.name)
        )
        subjects = list(res.scalars().all())
        class_names = await InstitutionService._entity_names(db, SchoolClass, [s.class_id for s in subjects])
        teachers = await InstitutionService._subject_teachers(db, tenant_id)
        return [
            SubjectOut(
                id=s.id, name=s.name, code=s.code, class_id=s.class_id,
                class_name=class_names.get(s.class_id), subject_type=s.subject_type,
                credits=s.credits, max_marks=s.max_marks, passing_marks=s.passing_marks,
                is_active=s.is_active, teachers=teachers.get(s.id, []),
            )
            for s in subjects
        ]

    @staticmethod
    async def create_subject(db: AsyncSession, tenant_id: uuid.UUID, payload: SubjectCreate) -> SubjectOut:
        await InstitutionService._assert_class(db, tenant_id, payload.class_id)
        subj = Subject(
            id=uuid.uuid4(), tenant_id=tenant_id, name=payload.name, code=payload.code.upper(),
            class_id=payload.class_id, subject_type=payload.subject_type, credits=payload.credits,
            max_marks=payload.max_marks, passing_marks=payload.passing_marks, is_active=True,
        )
        db.add(subj)
        await InstitutionService._flush_unique(db, "A subject with this code already exists")
        rows = await InstitutionService.list_subjects(db, tenant_id)
        return next((r for r in rows if r.code == payload.code.upper()), rows[0])

    @staticmethod
    async def update_subject(db: AsyncSession, tenant_id: uuid.UUID, subject_id: uuid.UUID, payload: SubjectUpdate) -> SubjectOut:
        res = await db.execute(select(Subject).where(Subject.id == subject_id, Subject.tenant_id == tenant_id))
        subj = res.scalar_one_or_none()
        if subj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Subject not found")
        for f in ("name", "subject_type", "credits", "max_marks", "passing_marks", "is_active"):
            v = getattr(payload, f)
            if v is not None:
                setattr(subj, f, v)
        await db.flush()
        rows = await InstitutionService.list_subjects(db, tenant_id)
        return next((r for r in rows if r.id == subject_id), rows[0])

    @staticmethod
    async def delete_subject(db: AsyncSession, tenant_id: uuid.UUID, subject_id: uuid.UUID) -> None:
        res = await db.execute(select(Subject).where(Subject.id == subject_id, Subject.tenant_id == tenant_id))
        subj = res.scalar_one_or_none()
        if subj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Subject not found")
        await db.delete(subj)

    # ── Class Grades (School wizard) ────────────────────────────────────

    @staticmethod
    async def list_grades(
        db: AsyncSession, tenant_id: uuid.UUID,
        academic_year_id: uuid.UUID | None = None,
    ) -> list[ClassGradeOut]:
        """Return all school grade groups with their sections."""
        stmt = select(ClassGrade).where(ClassGrade.tenant_id == tenant_id)
        if academic_year_id:
            stmt = stmt.where(ClassGrade.academic_year_id == academic_year_id)
        stmt = stmt.order_by(ClassGrade.grade_number, ClassGrade.stream)
        grades = list((await db.execute(stmt)).scalars().all())

        year_names = await InstitutionService._entity_names(db, AcademicYear, [g.academic_year_id for g in grades])
        dept_names = await InstitutionService._entity_names(db, Department, [g.academic_year_id for g in grades])

        # Load all sections that belong to any of these grades in one query
        grade_ids = [g.id for g in grades]
        teacher_name_cache: dict[uuid.UUID, str] = {}
        enrolled_counts = await InstitutionService._count_enrolled_by_class(db, tenant_id)
        subject_counts = await InstitutionService._count_subjects_by_class(db, tenant_id)

        results: list[ClassGradeOut] = []
        for grade in grades:
            sec_res = await db.execute(
                select(SchoolClass).where(
                    SchoolClass.grade_id == grade.id,
                    SchoolClass.tenant_id == tenant_id,
                ).order_by(SchoolClass.section_label)
            )
            sections_orm = list(sec_res.scalars().all())

            # Batch-collect teacher names we haven't seen yet
            missing = [s.class_teacher_id for s in sections_orm if s.class_teacher_id and s.class_teacher_id not in teacher_name_cache]
            if missing:
                new_names = await InstitutionService._user_names(db, missing)
                teacher_name_cache.update(new_names)

            # Resolve the dept_name from the sections (they share the same department)
            dept_id = sections_orm[0].department_id if sections_orm else None
            dept_name = None
            if dept_id:
                dn = await db.execute(select(Department.name).where(Department.id == dept_id))
                dept_name = dn.scalar_one_or_none()

            results.append(ClassGradeOut(
                id=grade.id,
                academic_year_id=grade.academic_year_id,
                academic_year_name=year_names.get(grade.academic_year_id),
                department_id=dept_id or uuid.UUID(int=0),
                department_name=dept_name,
                name=grade.name,
                grade_number=grade.grade_number,
                stream=grade.stream,
                is_active=grade.is_active,
                sections=[
                    SectionOut(
                        id=s.id, name=s.name, code=s.code,
                        section_label=s.section_label,
                        class_teacher_id=s.class_teacher_id,
                        class_teacher_name=teacher_name_cache.get(s.class_teacher_id) if s.class_teacher_id else None,
                        enrolled_count=enrolled_counts.get(s.id, 0),
                        subject_count=subject_counts.get(s.id, 0),
                        room_no=s.room_no,
                        is_active=s.is_active,
                    )
                    for s in sections_orm
                ],
            ))
        return results

    @staticmethod
    async def create_grade_with_sections(
        db: AsyncSession, tenant_id: uuid.UUID, payload: ClassGradeCreate,
    ) -> ClassGradeOut:
        """School wizard: create one ClassGrade row + one SchoolClass per section."""
        await InstitutionService._assert_dept(db, tenant_id, payload.department_id)
        await InstitutionService._assert_year(db, tenant_id, payload.academic_year_id)
        if payload.class_teacher_id is not None:
            await InstitutionService._assert_user_in_tenant(db, tenant_id, payload.class_teacher_id)
        if not payload.sections:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one section is required")
        # Deduplicate and uppercase section labels
        seen: set[str] = set()
        unique_sections: list[str] = []
        for s in payload.sections:
            label = s.strip().upper()
            if not label:
                continue
            if label in seen:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Duplicate section label: {label}")
            seen.add(label)
            unique_sections.append(label)

        # Build display name and stream label
        grade_name = f"Class {payload.grade_number}"
        stream_suffix = f" - {payload.stream}" if payload.stream else ""

        grade = ClassGrade(
            id=uuid.uuid4(), tenant_id=tenant_id,
            academic_year_id=payload.academic_year_id,
            name=grade_name,
            grade_number=payload.grade_number,
            stream=payload.stream,
            is_active=True,
        )
        db.add(grade)
        await InstitutionService._flush_unique(
            db, f"Grade {payload.grade_number}{stream_suffix} already exists for this year"
        )

        # Create one SchoolClass (Academic Group) per section
        for section_label in unique_sections:
            # Code pattern: e.g. "11-A", "11-SCI-A" (if stream)
            stream_code = ""
            if payload.stream:
                stream_code = f"-{payload.stream[:3].upper()}"
            class_code = f"{payload.grade_number}{stream_code}-{section_label}"
            class_name = f"Class {payload.grade_number}{stream_suffix} - Section {section_label}"
            cls = SchoolClass(
                id=uuid.uuid4(), tenant_id=tenant_id,
                department_id=payload.department_id,
                academic_year_id=payload.academic_year_id,
                name=class_name,
                code=class_code,
                max_strength=payload.max_strength,
                class_teacher_id=payload.class_teacher_id,
                is_active=True,
                grade_id=grade.id,
                section_label=section_label,
            )
            db.add(cls)

        await InstitutionService._flush_unique(db, "A section with this code already exists in this year")
        rows = await InstitutionService.list_grades(db, tenant_id, payload.academic_year_id)
        created = next((g for g in rows if g.id == grade.id), None)
        if created is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Grade created but could not be fetched")
        return created

    @staticmethod
    async def delete_grade(db: AsyncSession, tenant_id: uuid.UUID, grade_id: uuid.UUID) -> None:
        """Delete a grade group. Only allowed when all its sections are empty."""
        res = await db.execute(select(ClassGrade).where(ClassGrade.id == grade_id, ClassGrade.tenant_id == tenant_id))
        grade = res.scalar_one_or_none()
        if grade is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Grade not found")
        # Check all sections are empty
        sec_res = await db.execute(
            select(SchoolClass).where(SchoolClass.grade_id == grade_id, SchoolClass.tenant_id == tenant_id)
        )
        sections = list(sec_res.scalars().all())
        enrolled_counts = await InstitutionService._count_enrolled_by_class(db, tenant_id)
        total_enrolled = sum(enrolled_counts.get(s.id, 0) for s in sections)
        if total_enrolled > 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"{total_enrolled} student(s) enrolled in sections of this grade. Transfer them first."
            )
        subject_counts = await InstitutionService._count_subjects_by_class(db, tenant_id)
        total_subjects = sum(subject_counts.get(s.id, 0) for s in sections)
        if total_subjects > 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"{total_subjects} subject(s) attached. Delete them first."
            )
        for s in sections:
            await db.delete(s)
        await db.flush()
        await db.delete(grade)

    # ── Class Programs (College wizard) ────────────────────────────────

    @staticmethod
    async def list_programs(
        db: AsyncSession, tenant_id: uuid.UUID,
        department_id: uuid.UUID | None = None,
        academic_year_id: uuid.UUID | None = None,
    ) -> list[ClassProgramOut]:
        """Return all college program+semester groups with their batches."""
        stmt = select(ClassProgram).where(ClassProgram.tenant_id == tenant_id)
        if department_id:
            stmt = stmt.where(ClassProgram.department_id == department_id)
        if academic_year_id:
            stmt = stmt.where(ClassProgram.academic_year_id == academic_year_id)
        stmt = stmt.order_by(ClassProgram.program_code, ClassProgram.semester_number)
        programs = list((await db.execute(stmt)).scalars().all())

        year_names = await InstitutionService._entity_names(db, AcademicYear, [p.academic_year_id for p in programs])
        dept_names = await InstitutionService._entity_names(db, Department, [p.department_id for p in programs])
        enrolled_counts = await InstitutionService._count_enrolled_by_class(db, tenant_id)
        subject_counts = await InstitutionService._count_subjects_by_class(db, tenant_id)
        teacher_name_cache: dict[uuid.UUID, str] = {}

        results: list[ClassProgramOut] = []
        for program in programs:
            bat_res = await db.execute(
                select(SchoolClass).where(
                    SchoolClass.program_id == program.id,
                    SchoolClass.tenant_id == tenant_id,
                ).order_by(SchoolClass.section_label)
            )
            batches_orm = list(bat_res.scalars().all())

            missing = [b.class_teacher_id for b in batches_orm if b.class_teacher_id and b.class_teacher_id not in teacher_name_cache]
            if missing:
                new_names = await InstitutionService._user_names(db, missing)
                teacher_name_cache.update(new_names)

            results.append(ClassProgramOut(
                id=program.id,
                academic_year_id=program.academic_year_id,
                academic_year_name=year_names.get(program.academic_year_id),
                department_id=program.department_id,
                department_name=dept_names.get(program.department_id),
                program_name=program.program_name,
                program_code=program.program_code,
                semester_number=program.semester_number,
                is_active=program.is_active,
                batches=[
                    SectionOut(
                        id=b.id, name=b.name, code=b.code,
                        section_label=b.section_label,
                        class_teacher_id=b.class_teacher_id,
                        class_teacher_name=teacher_name_cache.get(b.class_teacher_id) if b.class_teacher_id else None,
                        enrolled_count=enrolled_counts.get(b.id, 0),
                        subject_count=subject_counts.get(b.id, 0),
                        room_no=b.room_no,
                        is_active=b.is_active,
                    )
                    for b in batches_orm
                ],
            ))
        return results

    @staticmethod
    async def create_program_with_batches(
        db: AsyncSession, tenant_id: uuid.UUID, payload: ClassProgramCreate,
    ) -> ClassProgramOut:
        """College wizard: create one ClassProgram row + one SchoolClass per batch."""
        await InstitutionService._assert_dept(db, tenant_id, payload.department_id)
        await InstitutionService._assert_year(db, tenant_id, payload.academic_year_id)
        if payload.class_teacher_id is not None:
            await InstitutionService._assert_user_in_tenant(db, tenant_id, payload.class_teacher_id)
        if not payload.batches:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one batch is required")

        seen: set[str] = set()
        unique_batches: list[str] = []
        for b in payload.batches:
            label = b.strip().upper()
            if not label:
                continue
            if label in seen:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Duplicate batch label: {label}")
            seen.add(label)
            unique_batches.append(label)

        program = ClassProgram(
            id=uuid.uuid4(), tenant_id=tenant_id,
            department_id=payload.department_id,
            academic_year_id=payload.academic_year_id,
            program_name=payload.program_name,
            program_code=payload.program_code.upper(),
            semester_number=payload.semester_number,
            is_active=True,
        )
        db.add(program)
        await InstitutionService._flush_unique(
            db, f"{payload.program_code} Semester {payload.semester_number} already exists for this dept and year"
        )

        for batch_label in unique_batches:
            # Code pattern: "BTCSE-3-A"
            class_code = f"{payload.program_code.upper()}-{payload.semester_number}-{batch_label}"
            class_name = f"{payload.program_name} Sem {payload.semester_number} - {batch_label}"
            cls = SchoolClass(
                id=uuid.uuid4(), tenant_id=tenant_id,
                department_id=payload.department_id,
                academic_year_id=payload.academic_year_id,
                name=class_name,
                code=class_code,
                max_strength=payload.max_strength,
                class_teacher_id=payload.class_teacher_id,
                is_active=True,
                program_id=program.id,
                section_label=batch_label,
            )
            db.add(cls)

        await InstitutionService._flush_unique(db, "A batch with this code already exists in this dept and year")
        rows = await InstitutionService.list_programs(db, tenant_id, payload.department_id, payload.academic_year_id)
        created = next((p for p in rows if p.id == program.id), None)
        if created is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Program created but could not be fetched")
        return created

    @staticmethod
    async def delete_program(db: AsyncSession, tenant_id: uuid.UUID, program_id: uuid.UUID) -> None:
        """Delete a program group. Only allowed when all its batches are empty."""
        res = await db.execute(select(ClassProgram).where(ClassProgram.id == program_id, ClassProgram.tenant_id == tenant_id))
        program = res.scalar_one_or_none()
        if program is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")
        bat_res = await db.execute(
            select(SchoolClass).where(SchoolClass.program_id == program_id, SchoolClass.tenant_id == tenant_id)
        )
        batches = list(bat_res.scalars().all())
        enrolled_counts = await InstitutionService._count_enrolled_by_class(db, tenant_id)
        total_enrolled = sum(enrolled_counts.get(b.id, 0) for b in batches)
        if total_enrolled > 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"{total_enrolled} student(s) enrolled in batches of this program. Transfer them first."
            )
        subject_counts = await InstitutionService._count_subjects_by_class(db, tenant_id)
        total_subjects = sum(subject_counts.get(b.id, 0) for b in batches)
        if total_subjects > 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"{total_subjects} subject(s) attached. Delete them first."
            )
        for b in batches:
            await db.delete(b)
        await db.flush()
        await db.delete(program)

    # ── People: staff ────────────────────────────────────────────────────────

    @staticmethod
    async def list_staff(db: AsyncSession, tenant_id: uuid.UUID) -> list[StaffOut]:
        res = await db.execute(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(User.tenant_id == tenant_id, User.deleted_at == None, Role.name != "STUDENT")  # noqa: E712
            .order_by(User.name)
        )
        users = list({u.id: u for u in res.scalars().all()}.values())
        return [await InstitutionService._staff_out(db, tenant_id, u) for u in users]

    @staticmethod
    async def invite_staff(
        db: AsyncSession,
        tenant: Tenant,
        payload: StaffInvite,
        *,
        actor: User | None = None,
    ) -> StaffOut:
        email = str(payload.email).lower()
        existing = await db.execute(select(User).where(User.tenant_id == tenant.id, User.email == email))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="A user with this email already exists")
        role = await InstitutionService._role_by_name(db, payload.role)
        if role is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown role '{payload.role}'")
        InstitutionService._assert_assignable_role(role)
        if payload.department_id is not None:
            await InstitutionService._assert_dept(db, tenant.id, payload.department_id)
        if role.name in ("VICE_PRINCIPAL", "HOD") and payload.department_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"An {role.name} must be assigned a department",
            )

        raw_token = generate_secure_token(32)
        user = User(
            id=uuid.uuid4(), tenant_id=tenant.id, name=payload.name, email=email, phone=payload.phone,
            password_hash=hash_password(DEFAULT_STAFF_PASSWORD), is_active=True,
            password_reset_token=hash_token(raw_token),
            password_reset_expires=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(user)
        await db.flush()
        assignment = RoleAssignment(
            id=uuid.uuid4(), user_id=user.id, role_id=role.id, tenant_id=tenant.id,
            scope_id=payload.department_id, scope_type="DEPARTMENT" if payload.department_id else None,
            assigned_by=actor.id if actor else None,
            assigned_at=datetime.now(timezone.utc), is_active=True,
        )
        db.add(assignment)

        if role.name == "HOD" and payload.department_id is not None:
            dept_res = await db.execute(select(Department).where(Department.id == payload.department_id, Department.tenant_id == tenant.id))
            dept = dept_res.scalar_one_or_none()
            if dept is not None:
                previous_hod_id = dept.hod_id
                dept.hod_id = user.id
                if previous_hod_id is not None and previous_hod_id != user.id:
                    await InstitutionService._deactivate_hod_department_scope(db, tenant.id, previous_hod_id, dept.id, actor=actor)

        await InstitutionService._queue_invite_email(db, tenant, user, raw_token)
        await db.flush()
        if actor is not None:
            AuditService.record(
                db,
                actor=actor,
                actor_role="INSTITUTION_ADMIN",
                action="INVITE_STAFF",
                entity="User",
                entity_id=user.id,
                tenant_id=tenant.id,
                new_value={
                    "name": user.name,
                    "email": user.email,
                    "role_name": role.name,
                    "department_id": str(payload.department_id) if payload.department_id else None,
                },
            )
        return await InstitutionService._staff_out(db, tenant.id, user)

    @staticmethod
    async def assign_role(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        role_name: str,
        by: User,
        *,
        department_id: uuid.UUID | None = None,
    ) -> StaffOut:
        user = await InstitutionService._load_user(db, tenant_id, user_id)
        role = await InstitutionService._role_by_name(db, role_name)
        if role is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown role '{role_name}'")
        InstitutionService._assert_assignable_role(role)
        if department_id is not None:
            await InstitutionService._assert_dept(db, tenant_id, department_id)
        if role.name in ("VICE_PRINCIPAL", "HOD") and department_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"An {role.name} must be assigned a department",
            )

        if role.name == "HOD" and department_id is not None:
            dept_res = await db.execute(select(Department).where(Department.id == department_id, Department.tenant_id == tenant_id))
            dept = dept_res.scalar_one_or_none()
            if dept is not None:
                previous_hod_id = dept.hod_id
                dept.hod_id = user_id
                if previous_hod_id is not None and previous_hod_id != user_id:
                    await InstitutionService._deactivate_hod_department_scope(db, tenant_id, previous_hod_id, dept.id, actor=by)

        scope_filter = (
            RoleAssignment.scope_id == department_id
            if department_id is not None
            else RoleAssignment.scope_id.is_(None)
        )
        exists = (
            await db.execute(
                select(RoleAssignment).where(
                    RoleAssignment.user_id == user_id,
                    RoleAssignment.role_id == role.id,
                    RoleAssignment.tenant_id == tenant_id,
                    scope_filter,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            assignment = RoleAssignment(
                id=uuid.uuid4(),
                user_id=user_id,
                role_id=role.id,
                tenant_id=tenant_id,
                scope_id=department_id,
                scope_type="DEPARTMENT" if department_id is not None else None,
                assigned_by=by.id,
                assigned_at=datetime.now(timezone.utc),
                is_active=True,
            )
            db.add(assignment)
            await db.flush()
            AuditService.record(
                db,
                actor=by,
                actor_role="INSTITUTION_ADMIN",
                action="ASSIGN_ROLE",
                entity="RoleAssignment",
                entity_id=assignment.id,
                tenant_id=tenant_id,
                new_value={
                    "user_id": str(user_id),
                    "role_name": role.name,
                    "department_id": str(department_id) if department_id else None,
                },
            )
        elif not exists.is_active:
            exists.is_active = True
            exists.assigned_by = by.id
            exists.assigned_at = datetime.now(timezone.utc)
            await db.flush()
            AuditService.record(
                db,
                actor=by,
                actor_role="INSTITUTION_ADMIN",
                action="ASSIGN_ROLE",
                entity="RoleAssignment",
                entity_id=exists.id,
                tenant_id=tenant_id,
                new_value={
                    "user_id": str(user_id),
                    "role_name": role.name,
                    "department_id": str(department_id) if department_id else None,
                },
            )
        return await InstitutionService._staff_out(db, tenant_id, user)

    @staticmethod
    async def revoke_role(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        role_name: str,
        actor: User,
        *,
        department_id: uuid.UUID | None = None,
    ) -> StaffOut:
        """Deactivate one role grant without deleting its audit history.

        Vice Principal grants are department-scoped; revoking one department
        must not accidentally remove a separate delegated department.
        """
        user = await InstitutionService._load_user(db, tenant_id, user_id)
        role = await InstitutionService._role_by_name(db, role_name)
        if role is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Role not found")
        if role.name in ("VICE_PRINCIPAL", "HOD") and department_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"A department is required to revoke an {role.name} scope",
            )
        if department_id is not None:
            await InstitutionService._assert_dept(db, tenant_id, department_id)
        scope_filter = (
            RoleAssignment.scope_id == department_id
            if department_id is not None
            else RoleAssignment.scope_id.is_(None)
        )
        assignment = (
            await db.execute(
                select(RoleAssignment).where(
                    RoleAssignment.user_id == user_id,
                    RoleAssignment.role_id == role.id,
                    RoleAssignment.tenant_id == tenant_id,
                    RoleAssignment.is_active.is_(True),
                    scope_filter,
                )
            )
        ).scalar_one_or_none()
        if assignment is None:
            # 404 keeps other scope identifiers indistinguishable from absent.
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Active role assignment not found")
        assignment.is_active = False

        if role.name == "HOD" and department_id is not None:
            dept_res = await db.execute(select(Department).where(Department.id == department_id, Department.tenant_id == tenant_id, Department.hod_id == user_id))
            dept = dept_res.scalar_one_or_none()
            if dept is not None:
                dept.hod_id = None

        await db.flush()
        AuditService.record(
            db,
            actor=actor,
            actor_role="INSTITUTION_ADMIN",
            action="REVOKE_ROLE",
            entity="RoleAssignment",
            entity_id=assignment.id,
            tenant_id=tenant_id,
            old_value={
                "user_id": str(user_id),
                "role_name": role.name,
                "department_id": str(department_id) if department_id else None,
            },
        )
        return await InstitutionService._staff_out(db, tenant_id, user)


    @staticmethod
    async def set_user_active(db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, active: bool) -> StaffOut:
        user = await InstitutionService._load_user(db, tenant_id, user_id)
        user.is_active = active
        await db.flush()
        return await InstitutionService._staff_out(db, tenant_id, user)

    @staticmethod
    async def update_staff(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: StaffUpdate,
        *,
        actor: User | None = None,
    ) -> StaffOut:
        user = await InstitutionService._load_user(db, tenant_id, user_id)
        if payload.name is not None:
            user.name = payload.name.strip()
        if payload.phone is not None:
            user.phone = payload.phone.strip() if payload.phone else None
        if payload.email is not None and payload.email.lower() != (user.email or "").lower():
            new_email = payload.email.lower().strip()
            existing = await db.execute(
                select(User).where(User.tenant_id == tenant_id, User.email == new_email, User.id != user_id)
            )
            if existing.scalar_one_or_none() is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="A user with this email already exists")
            user.email = new_email

        if payload.department_id is not None:
            await InstitutionService._assert_dept(db, tenant_id, payload.department_id)
            sp_res = await db.execute(
                select(StaffProfile).where(StaffProfile.user_id == user_id, StaffProfile.tenant_id == tenant_id)
            )
            sp = sp_res.scalar_one_or_none()
            if sp:
                sp.department_id = payload.department_id
            else:
                sp = StaffProfile(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    tenant_id=tenant_id,
                    employee_code=f"EMP-{user_id.hex[:6].upper()}",
                    designation="Staff Member",
                    department_id=payload.department_id,
                    employment_type="FULL_TIME",
                    date_of_joining=date.today(),
                    is_active=True,
                )
                db.add(sp)

        await db.flush()
        if actor is not None:
            AuditService.record(
                db,
                actor=actor,
                actor_role="INSTITUTION_ADMIN",
                action="UPDATE_STAFF",
                entity="User",
                entity_id=user.id,
                tenant_id=tenant_id,
                new_value={
                    "name": user.name,
                    "email": user.email,
                    "phone": user.phone,
                    "department_id": str(payload.department_id) if payload.department_id else None,
                },
            )
        return await InstitutionService._staff_out(db, tenant_id, user)

    @staticmethod
    async def delete_staff(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        actor: User | None = None,
    ) -> None:
        user = await InstitutionService._load_user(db, tenant_id, user_id)
        if actor is not None and actor.id == user_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")
        user.is_active = False
        user.deleted_at = datetime.now(timezone.utc)
        await db.flush()
        if actor is not None:
            AuditService.record(
                db,
                actor=actor,
                actor_role="INSTITUTION_ADMIN",
                action="DELETE_STAFF",
                entity="User",
                entity_id=user.id,
                tenant_id=tenant_id,
            )


    @staticmethod
    async def bulk_create_staff(db: AsyncSession, tenant: Tenant, content: bytes) -> BulkUploadResult:
        """Import staff from a CSV upload.

        Expected headers: ``name, email, role`` (required) and ``phone,
        department_code`` (optional; the department code, e.g. ``CS``).
        Every row runs in its own savepoint, so one bad row is reported and
        skipped without rolling back the staff already imported. Each created
        member gets the standard set-password invite email.
        """
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The file must be UTF-8 CSV (Excel: save as 'CSV UTF-8')")

        reader = csv.DictReader(io.StringIO(text))
        missing = {"name", "email", "role"} - {h.strip().lower() for h in (reader.fieldnames or []) if h}
        if missing:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"The CSV must have headers: {', '.join(sorted(missing))} (optional: phone, department_code)",
            )
        rows = [r for r in reader if any((v or "").strip() for v in r.values())]
        if len(rows) > BULK_MAX_ROWS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Too many rows — max {BULK_MAX_ROWS} per file")

        existing_emails = {
            e.lower()
            for e in (await db.scalars(
                select(User.email).where(User.tenant_id == tenant.id, User.email.is_not(None))
            )).all()
        }
        departments = {d.code: d for d in (await db.scalars(select(Department).where(Department.tenant_id == tenant.id))).all()}

        created, seen, errors, warnings = 0, set(), [], []
        for row_no, raw in enumerate(rows, start=2):
            row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            email = row.get("email", "").lower()
            if email in seen:
                errors.append(BulkUploadRowIssue(row=row_no, message="Duplicate email in this file"))
                continue
            if email in existing_emails:
                errors.append(BulkUploadRowIssue(row=row_no, message="A user with this email already exists"))
                continue
            try:
                async with db.begin_nested():
                    warning = await InstitutionService._bulk_staff_row(db, tenant, row, departments)
                created += 1
                seen.add(email)
                existing_emails.add(email)
                if warning:
                    warnings.append(BulkUploadRowIssue(row=row_no, message=warning))
            except HTTPException as exc:
                errors.append(BulkUploadRowIssue(row=row_no, message=str(exc.detail)))
            except Exception:
                errors.append(BulkUploadRowIssue(row=row_no, message="Unexpected error — row skipped"))

        return BulkUploadResult(total=len(rows), created=created, errors=errors, warnings=warnings)

    @staticmethod
    async def _bulk_staff_row(db, tenant, row: dict, departments: dict) -> str | None:
        """Create one staff member from a parsed CSV row; raise HTTPException on bad data.

        Returns a warning message when the member was created but could not be
        scoped to the requested department code (never blocks the import).
        """
        name = row.get("name", "")
        email = row.get("email", "").lower()
        role_name = row.get("role", "").upper()
        if len(name) < 2:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required (at least 2 characters)")
        if "@" not in email:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="email is required and must be a valid address")
        role = await InstitutionService._role_by_name(db, role_name)
        if role is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown role '{role_name}'")
        InstitutionService._assert_assignable_role(role)

        department = None
        if row.get("department_code"):
            department = departments.get(row["department_code"])
            if department is None:
                if role.name == "VICE_PRINCIPAL":
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Department code '{row['department_code']}' not found (required for Vice Principal)",
                    )
        if role.name == "VICE_PRINCIPAL" and department is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A Vice Principal must be assigned at least one delegated department",
            )

        raw_token = generate_secure_token(32)
        user = User(
            id=uuid.uuid4(), tenant_id=tenant.id, name=name, email=email,
            phone=row.get("phone") or None, password_hash=hash_password(DEFAULT_STAFF_PASSWORD), is_active=True,
            password_reset_token=hash_token(raw_token),
            password_reset_expires=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(user)
        await db.flush()
        assignment = RoleAssignment(
            id=uuid.uuid4(), user_id=user.id, role_id=role.id, tenant_id=tenant.id,
            scope_id=department.id if department else None,
            scope_type="DEPARTMENT" if department else None,
            assigned_at=datetime.now(timezone.utc), is_active=True,
        )
        db.add(assignment)
        await db.flush()
        await InstitutionService._queue_invite_email(db, tenant, user, raw_token)
        if department is None and row.get("department_code"):
            return f"Created, but not assigned: department code '{row['department_code']}' not found"
        return None

    # ── People: students ─────────────────────────────────────────────────────

    @staticmethod
    async def list_students(db: AsyncSession, tenant_id: uuid.UUID) -> list[StudentOut]:
        res = await db.execute(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(User.tenant_id == tenant_id, User.deleted_at == None, Role.name == "STUDENT")  # noqa: E712
            .order_by(User.name)
        )
        students = list({u.id: u for u in res.scalars().all()}.values())
        enrollments = await InstitutionService._active_enrollments(db, tenant_id, [s.id for s in students])
        return [
            StudentOut(
                id=s.id, name=s.name, email=s.email, roll_no=s.student_roll_no,
                gender=s.gender.value if s.gender else None, is_active=s.is_active,
                enrollment=enrollments.get(s.id),
            )
            for s in students
        ]

    @staticmethod
    async def create_student(db: AsyncSession, tenant: Tenant, payload: StudentCreate) -> StudentOut:
        existing = await db.execute(
            select(User).where(User.tenant_id == tenant.id, User.student_roll_no == payload.roll_no)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="A student with this roll number already exists")
        role = await InstitutionService._role_by_name(db, "STUDENT")

        from app.models.user import Gender
        user = User(
            id=uuid.uuid4(), tenant_id=tenant.id, name=payload.name,
            email=str(payload.email).lower() if payload.email else None,
            student_roll_no=payload.roll_no, gender=Gender(payload.gender) if payload.gender else None,
            date_of_birth=payload.date_of_birth,
            password_hash=hash_password(_random_student_password()), is_active=True,
        )
        db.add(user)
        await db.flush()
        if role is not None:
            db.add(RoleAssignment(
                id=uuid.uuid4(), user_id=user.id, role_id=role.id, tenant_id=tenant.id,
                assigned_at=datetime.now(timezone.utc), is_active=True,
            ))

        enrollment = None
        if payload.class_id is not None:
            await InstitutionService._assert_class(db, tenant.id, payload.class_id)
            year = await InstitutionService._current_year(db, tenant.id)
            if year is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Create an academic year before enrolling students")
            enrollment = await InstitutionService._enroll(db, tenant.id, user.id, payload.class_id, year.id, payload.roll_no)
        await db.flush()
        return StudentOut(
            id=user.id, name=user.name, email=user.email, roll_no=user.student_roll_no,
            gender=user.gender.value if user.gender else None, is_active=user.is_active, enrollment=enrollment,
        )

    @staticmethod
    async def update_student(
        db: AsyncSession, tenant_id: uuid.UUID, student_id: uuid.UUID, payload: StudentUpdate,
    ) -> StudentOut:
        res = await db.execute(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(User.id == student_id, User.tenant_id == tenant_id, User.deleted_at == None, Role.name == "STUDENT")  # noqa: E712
        )
        student = res.scalar_one_or_none()
        if student is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")

        if payload.roll_no is not None and payload.roll_no != student.student_roll_no:
            existing = await db.execute(
                select(User).where(User.tenant_id == tenant_id, User.student_roll_no == payload.roll_no, User.id != student_id)
            )
            if existing.scalar_one_or_none() is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="A student with this roll number already exists")
            student.student_roll_no = payload.roll_no

        if payload.name is not None:
            student.name = payload.name
        if payload.email is not None:
            student.email = str(payload.email).lower() if payload.email else None
        if payload.gender is not None:
            from app.models.user import Gender
            student.gender = Gender(payload.gender) if payload.gender else None
        if payload.date_of_birth is not None:
            student.date_of_birth = payload.date_of_birth
        if payload.is_active is not None:
            student.is_active = payload.is_active

        if payload.class_id is not None:
            await InstitutionService._assert_class(db, tenant_id, payload.class_id)
            year = await InstitutionService._current_year(db, tenant_id)
            if year is not None:
                active_enr = (await db.execute(
                    select(Enrollment).where(
                        Enrollment.student_id == student_id,
                        Enrollment.tenant_id == tenant_id,
                        Enrollment.status == "ACTIVE",
                    )
                )).scalar_one_or_none()
                if active_enr is not None:
                    active_enr.class_id = payload.class_id
                    if payload.roll_no:
                        active_enr.roll_number = payload.roll_no
                else:
                    await InstitutionService._enroll(db, tenant_id, student.id, payload.class_id, year.id, student.student_roll_no or "")

        await db.flush()
        students = await InstitutionService.list_students(db, tenant_id)
        return next((s for s in students if s.id == student_id), students[0])

    @staticmethod
    async def delete_student(db: AsyncSession, tenant_id: uuid.UUID, student_id: uuid.UUID) -> None:
        res = await db.execute(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(User.id == student_id, User.tenant_id == tenant_id, User.deleted_at == None, Role.name == "STUDENT")  # noqa: E712
        )
        student = res.scalar_one_or_none()
        if student is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")

        student.deleted_at = datetime.now(timezone.utc)
        student.is_active = False

        enr_res = await db.execute(
            select(Enrollment).where(Enrollment.student_id == student_id, Enrollment.tenant_id == tenant_id)
        )
        for enr in enr_res.scalars().all():
            enr.status = "DROPPED"
        await db.flush()

    @staticmethod
    async def bulk_create_students(db: AsyncSession, tenant: Tenant, content: bytes) -> BulkUploadResult:
        """Import students from a CSV upload.

        Expected headers: ``name, roll_no`` (required) and ``email, gender,
        date_of_birth, class_code`` (optional). Every row is processed inside
        its own savepoint, so one bad row is reported and skipped without
        rolling back the students that were already imported.
        """
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The file must be UTF-8 CSV (Excel: save as 'CSV UTF-8')")

        reader = csv.DictReader(io.StringIO(text))
        missing = {"name", "roll_no"} - {h.strip().lower() for h in (reader.fieldnames or []) if h}
        if missing:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"The CSV must have headers: {', '.join(sorted(missing))} (optional: email, gender, date_of_birth, class_code)",
            )
        rows = [r for r in reader if any((v or "").strip() for v in r.values())]
        if len(rows) > BULK_MAX_ROWS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Too many rows — max {BULK_MAX_ROWS} per file")

        existing_rolls = set(
            (await db.scalars(
                select(User.student_roll_no).where(User.tenant_id == tenant.id, User.student_roll_no.is_not(None))
            )).all()
        )
        classes = {c.code: c for c in (await db.scalars(select(SchoolClass).where(SchoolClass.tenant_id == tenant.id))).all()}
        year = await InstitutionService._current_year(db, tenant.id)
        role = await InstitutionService._role_by_name(db, "STUDENT")

        created, seen, errors, warnings = 0, set(), [], []
        for row_no, raw in enumerate(rows, start=2):
            row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            roll_no = row.get("roll_no", "")
            if roll_no and roll_no in seen:
                errors.append(BulkUploadRowIssue(row=row_no, message="Duplicate roll number in this file"))
                continue
            if roll_no and roll_no in existing_rolls:
                errors.append(BulkUploadRowIssue(row=row_no, message="A student with this roll number already exists"))
                continue
            try:
                async with db.begin_nested():
                    warning = await InstitutionService._bulk_student_row(db, tenant, role, row, classes, year)
                created += 1
                seen.add(roll_no)
                existing_rolls.add(roll_no)
                if warning:
                    warnings.append(BulkUploadRowIssue(row=row_no, message=warning))
            except HTTPException as exc:
                errors.append(BulkUploadRowIssue(row=row_no, message=str(exc.detail)))
            except Exception:
                errors.append(BulkUploadRowIssue(row=row_no, message="Unexpected error — row skipped"))

        return BulkUploadResult(total=len(rows), created=created, errors=errors, warnings=warnings)

    @staticmethod
    async def _bulk_student_row(db, tenant, role, row: dict, classes: dict, year) -> str | None:
        """Create one student from a parsed CSV row; raise HTTPException on bad data.

        Returns a warning message when the student was created but could not be
        enrolled (unknown class code / no current academic year).
        """
        name = row.get("name", "")
        roll_no = row.get("roll_no", "")
        if len(name) < 2:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required (at least 2 characters)")
        if not roll_no:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="roll_no is required")

        gender = None
        if row.get("gender"):
            gender = row["gender"].upper()
            if gender not in {"MALE", "FEMALE", "OTHER"}:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="gender must be MALE, FEMALE or OTHER")

        dob = None
        if row.get("date_of_birth"):
            try:
                dob = date.fromisoformat(row["date_of_birth"])
            except ValueError:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="date_of_birth must be YYYY-MM-DD")

        email = row.get("email") or None
        if email and "@" not in email:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="email is not a valid address")
        email = email.lower() if email else None

        from app.models.user import Gender
        user = User(
            id=uuid.uuid4(), tenant_id=tenant.id, name=name, email=email,
            student_roll_no=roll_no, gender=Gender(gender) if gender else None,
            date_of_birth=dob,
            password_hash=hash_password(_random_student_password()), is_active=True,
        )
        db.add(user)
        await db.flush()
        if role is not None:
            db.add(RoleAssignment(
                id=uuid.uuid4(), user_id=user.id, role_id=role.id, tenant_id=tenant.id,
                assigned_at=datetime.now(timezone.utc), is_active=True,
            ))
            await db.flush()

        class_code = row.get("class_code", "")
        if class_code:
            cls = classes.get(class_code)
            if cls is None:
                return f"Created, but not enrolled: class code '{class_code}' not found"
            if year is None:
                return "Created, but not enrolled: no current academic year"
            await InstitutionService._enroll(db, tenant.id, user.id, cls.id, year.id, roll_no)
        return None

    # ── Enrollments ──────────────────────────────────────────────────────────

    @staticmethod
    async def list_enrollments(db: AsyncSession, tenant_id: uuid.UUID) -> list[EnrollmentOut]:
        res = await db.execute(
            select(Enrollment).where(Enrollment.tenant_id == tenant_id).order_by(Enrollment.enrollment_date.desc())
        )
        rows = list(res.scalars().all())
        student_names = await InstitutionService._user_names(db, [r.student_id for r in rows])
        class_names = await InstitutionService._entity_names(db, SchoolClass, [r.class_id for r in rows])
        year_names = await InstitutionService._entity_names(db, AcademicYear, [r.academic_year_id for r in rows])
        return [
            EnrollmentOut(
                id=r.id, student_id=r.student_id, student_name=student_names.get(r.student_id, "—"),
                class_id=r.class_id, class_name=class_names.get(r.class_id, "—"),
                academic_year_id=r.academic_year_id, academic_year_name=year_names.get(r.academic_year_id, "—"),
                roll_number=r.roll_number, status=r.status, enrollment_date=r.enrollment_date,
            )
            for r in rows
        ]

    @staticmethod
    async def create_enrollment(db: AsyncSession, tenant_id: uuid.UUID, payload: EnrollmentCreate) -> EnrollmentOut:
        await InstitutionService._assert_user_in_tenant(db, tenant_id, payload.student_id)
        await InstitutionService._assert_class(db, tenant_id, payload.class_id)
        year_id = payload.academic_year_id
        if year_id is None:
            year = await InstitutionService._current_year(db, tenant_id)
            if year is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No current academic year")
            year_id = year.id
        else:
            await InstitutionService._assert_year(db, tenant_id, year_id)
        enr = await InstitutionService._enroll(db, tenant_id, payload.student_id, payload.class_id, year_id, payload.roll_number)
        await db.flush()
        rows = await InstitutionService.list_enrollments(db, tenant_id)
        return next((r for r in rows if r.student_id == payload.student_id and r.class_id == payload.class_id), rows[0])

    @staticmethod
    async def _enroll(db, tenant_id, student_id, class_id, year_id, roll_number) -> dict:
        existing = await db.execute(
            select(Enrollment).where(
                Enrollment.student_id == student_id, Enrollment.class_id == class_id,
                Enrollment.academic_year_id == year_id,
            )
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Student is already enrolled in this class for the year")
        enr = Enrollment(
            id=uuid.uuid4(), tenant_id=tenant_id, student_id=student_id, class_id=class_id,
            academic_year_id=year_id, roll_number=roll_number, status="ACTIVE",
        )
        db.add(enr)
        await db.flush()
        cls_res = await db.execute(select(SchoolClass.name).where(SchoolClass.id == class_id))
        class_name = cls_res.scalar_one_or_none() or "—"
        return {
            "id": str(enr.id), "class_id": str(class_id), "class_name": class_name,
            "roll_number": roll_number, "status": enr.status,
        }

    # ── Modules ──────────────────────────────────────────────────────────────

    @staticmethod
    async def list_modules(db: AsyncSession, tenant_id: uuid.UUID) -> list[ModuleOut]:
        tenant = await InstitutionService._tenant(db, tenant_id)
        catalog = await db.execute(select(Module).order_by(Module.sort_order))
        catalog_rows = list(catalog.scalars().all())
        enabled = await db.execute(select(TenantModule).where(TenantModule.tenant_id == tenant_id))
        enabled_map = {tm.module_key: tm.is_enabled for tm in enabled.scalars().all()}
        return [
            ModuleOut(
                key=m.key, name=m.name, is_core=m.is_core,
                is_enabled=enabled_map.get(m.key, m.is_core),
                price_monthly=float(m.price_monthly or 0),
            )
            for m in catalog_rows
        ]

    @staticmethod
    async def toggle_module(db: AsyncSession, tenant: Tenant, module_key: str, enabled: bool) -> ModuleOut:
        """Plan-gated: a non-core module cannot be enabled beyond the plan."""
        mod_res = await db.execute(select(Module).where(Module.key == module_key))
        module = mod_res.scalar_one_or_none()
        if module is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")
        if module.is_core and not enabled:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Core modules cannot be disabled")

        if enabled and not module.is_core:
            plan_res = await db.execute(select(Plan).where(Plan.id == tenant.plan_id))
            plan = plan_res.scalar_one_or_none()
            allowed = set(plan.allowed_modules or []) if plan else set()
            if module.key not in allowed:
                raise HTTPException(
                    status.HTTP_402_PAYMENT_REQUIRED,
                    detail=f"{module.name} is not included in your plan. Upgrade to enable it.",
                )

        res = await db.execute(select(TenantModule).where(TenantModule.tenant_id == tenant.id, TenantModule.module_key == module_key))
        row = res.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if row is None:
            row = TenantModule(tenant_id=tenant.id, module_key=module_key, is_enabled=enabled, enabled_at=now)
            db.add(row)
        else:
            row.is_enabled = enabled
            if enabled:
                row.enabled_at = now
            else:
                row.disabled_at = now
        await db.flush()
        return ModuleOut(key=module.key, name=module.name, is_core=module.is_core, is_enabled=enabled, price_monthly=float(module.price_monthly or 0))

    # ── Settings + profile ───────────────────────────────────────────────────

    @staticmethod
    async def get_settings(db: AsyncSession, tenant_id: uuid.UUID) -> SettingsOut:
        res = await db.execute(select(TenantSetting).where(TenantSetting.tenant_id == tenant_id, TenantSetting.key.in_(["timezone", "currency"])))
        rows = {r.key: r.value for r in res.scalars().all()}
        return SettingsOut(
            timezone=rows.get("timezone", "Asia/Kolkata"),
            currency=rows.get("currency", "INR"),
            onboarding_complete=await InstitutionService._is_onboarded(db, tenant_id),
        )

    @staticmethod
    async def update_settings(db: AsyncSession, tenant_id: uuid.UUID, payload: SettingsUpdate) -> SettingsOut:
        for key, value in (("timezone", payload.timezone), ("currency", payload.currency)):
            if value is None:
                continue
            res = await db.execute(select(TenantSetting).where(TenantSetting.tenant_id == tenant_id, TenantSetting.key == key))
            row = res.scalar_one_or_none()
            if row is None:
                db.add(TenantSetting(tenant_id=tenant_id, key=key, value=value))
            else:
                row.value = value
        await db.flush()
        return await InstitutionService.get_settings(db, tenant_id)

    @staticmethod
    async def get_profile(db: AsyncSession, tenant_id: uuid.UUID) -> InstitutionProfileOut:
        tenant = await InstitutionService._tenant(db, tenant_id)
        plan_name = await InstitutionService._plan_name(db, tenant)
        sub_status = await InstitutionService._subscription_status(db, tenant_id)
        return InstitutionProfileOut(
            id=tenant.id, name=tenant.name, slug=tenant.slug, type=tenant.type.value,
            email=tenant.email, phone=tenant.phone, address=tenant.address, city=tenant.city,
            state=tenant.state, country=tenant.country, pincode=tenant.pincode, website=tenant.website,
            logo_url=tenant.logo_url, timezone=tenant.timezone, plan_name=plan_name, subscription_status=sub_status,
        )

    @staticmethod
    async def update_profile(db: AsyncSession, tenant_id: uuid.UUID, payload: InstitutionProfileUpdate) -> InstitutionProfileOut:
        tenant = await InstitutionService._tenant(db, tenant_id)
        for f in ("name", "email", "phone", "address", "city", "state", "pincode", "website", "logo_url"):
            v = getattr(payload, f)
            if v is not None:
                setattr(tenant, f, v)
        await db.flush()
        return await InstitutionService.get_profile(db, tenant_id)

    # ── small lookup helpers ─────────────────────────────────────────────────

    @staticmethod
    async def _user_names(db, ids: list[uuid.UUID]) -> dict:
        ids = [i for i in ids if i]
        if not ids:
            return {}
        res = await db.execute(select(User.id, User.name).where(User.id.in_(ids)))
        return {uid: name for uid, name in res.all()}

    @staticmethod
    async def _entity_names(db, model, ids: list[uuid.UUID]) -> dict:
        ids = [i for i in ids if i]
        if not ids:
            return {}
        res = await db.execute(select(model.id, model.name).where(model.id.in_(ids)))
        return {row[0]: row[1] for row in res.all()}

    @staticmethod
    async def _count_classes_by_dept(db, tenant_id) -> dict:
        res = await db.execute(select(SchoolClass.department_id, func.count(SchoolClass.id)).where(SchoolClass.tenant_id == tenant_id).group_by(SchoolClass.department_id))
        return {row[0]: row[1] for row in res.all()}

    @staticmethod
    async def _count_staff_by_dept(db, tenant_id) -> dict:
        res = await db.execute(
            select(RoleAssignment.scope_id, func.count(RoleAssignment.user_id.distinct()))
            .where(RoleAssignment.tenant_id == tenant_id, RoleAssignment.scope_type == "DEPARTMENT", RoleAssignment.is_active == True)  # noqa: E712
            .group_by(RoleAssignment.scope_id)
        )
        return {row[0]: row[1] for row in res.all()}

    @staticmethod
    async def _count_enrolled_by_class(db, tenant_id) -> dict:
        res = await db.execute(
            select(Enrollment.class_id, func.count(Enrollment.id))
            .where(Enrollment.tenant_id == tenant_id, Enrollment.status == "ACTIVE")
            .group_by(Enrollment.class_id)
        )
        return {row[0]: row[1] for row in res.all()}

    @staticmethod
    async def _count_subjects_by_class(db, tenant_id) -> dict:
        res = await db.execute(
            select(Subject.class_id, func.count(Subject.id))
            .where(Subject.tenant_id == tenant_id, Subject.is_active == True)  # noqa: E712
            .group_by(Subject.class_id)
        )
        return {row[0]: row[1] for row in res.all()}

    @staticmethod
    async def _subject_teachers(db, tenant_id) -> dict:
        res = await db.execute(
            select(TeacherSubject, User)
            .join(User, User.id == TeacherSubject.teacher_id)
            .where(TeacherSubject.tenant_id == tenant_id)
        )
        out: dict = {}
        for ts, teacher in res.all():
            out.setdefault(ts.subject_id, []).append(
                {"teacher_id": str(teacher.id), "teacher_name": teacher.name, "role": ts.role_in_subject}
            )
        return out

    @staticmethod
    async def _active_enrollments(db, tenant_id, student_ids) -> dict:
        if not student_ids:
            return {}
        res = await db.execute(
            select(Enrollment, SchoolClass).join(SchoolClass, SchoolClass.id == Enrollment.class_id)
            .where(Enrollment.tenant_id == tenant_id, Enrollment.student_id.in_(student_ids), Enrollment.status == "ACTIVE")
        )
        out: dict = {}
        for enr, cls in res.all():
            out[enr.student_id] = {"id": str(enr.id), "class_id": str(cls.id), "class_name": cls.name, "roll_number": enr.roll_number}
        return out

    @staticmethod
    async def _deactivate_hod_department_scope(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        hod_id: uuid.UUID,
        department_id: uuid.UUID,
        *,
        actor: User | None = None,
    ) -> None:
        role = await InstitutionService._role_by_name(db, "HOD")
        if role is None:
            return
        assignments = (
            await db.execute(
                select(RoleAssignment).where(
                    RoleAssignment.user_id == hod_id,
                    RoleAssignment.role_id == role.id,
                    RoleAssignment.tenant_id == tenant_id,
                    RoleAssignment.scope_id == department_id,
                    RoleAssignment.is_active.is_(True),
                )
            )
        ).scalars().all()
        for assignment in assignments:
            assignment.is_active = False
            if actor is not None:
                AuditService.record(
                    db,
                    actor=actor,
                    actor_role="INSTITUTION_ADMIN",
                    action="REVOKE_HOD_SCOPE",
                    entity="RoleAssignment",
                    entity_id=assignment.id,
                    tenant_id=tenant_id,
                    old_value={"hod_id": str(hod_id), "department_id": str(department_id)},
                )
        if assignments:
            await db.flush()

    @staticmethod
    async def _ensure_hod_department_scope(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        hod_id: uuid.UUID,
        department_id: uuid.UUID,
        *,
        actor: User | None = None,
    ) -> None:
        """Keep department.hod_id and the HOD role scope consistent."""
        role = await InstitutionService._role_by_name(db, "HOD")
        if role is None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="HOD role is not configured")

        sp_res = await db.execute(
            select(StaffProfile).where(StaffProfile.user_id == hod_id, StaffProfile.tenant_id == tenant_id)
        )
        sp = sp_res.scalar_one_or_none()
        if sp is not None and sp.department_id != department_id:
            sp.department_id = department_id

        existing = (
            await db.execute(
                select(RoleAssignment).where(
                    RoleAssignment.user_id == hod_id,
                    RoleAssignment.role_id == role.id,
                    RoleAssignment.tenant_id == tenant_id,
                    RoleAssignment.scope_id == department_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            assignment = RoleAssignment(
                id=uuid.uuid4(),
                user_id=hod_id,
                role_id=role.id,
                tenant_id=tenant_id,
                scope_id=department_id,
                scope_type="DEPARTMENT",
                assigned_by=actor.id if actor else None,
                assigned_at=datetime.now(timezone.utc),
                is_active=True,
            )
            db.add(assignment)
            await db.flush()
            if actor is not None:
                AuditService.record(
                    db,
                    actor=actor,
                    actor_role="INSTITUTION_ADMIN",
                    action="ASSIGN_HOD_SCOPE",
                    entity="RoleAssignment",
                    entity_id=assignment.id,
                    tenant_id=tenant_id,
                    new_value={"hod_id": str(hod_id), "department_id": str(department_id)},
                )
        elif not existing.is_active:
            existing.is_active = True
            existing.assigned_by = actor.id if actor else None
            existing.assigned_at = datetime.now(timezone.utc)
            await db.flush()
            if actor is not None:
                AuditService.record(
                    db,
                    actor=actor,
                    actor_role="INSTITUTION_ADMIN",
                    action="ASSIGN_HOD_SCOPE",
                    entity="RoleAssignment",
                    entity_id=existing.id,
                    tenant_id=tenant_id,
                    new_value={"hod_id": str(hod_id), "department_id": str(department_id)},
                )

    @staticmethod
    async def _role_by_name(db, name: str) -> Role | None:
        res = await db.execute(select(Role).where(Role.name == name.upper()))
        return res.scalar_one_or_none()

    @staticmethod
    def _assert_assignable_role(role: Role) -> None:
        """Reject platform roles and non-staff audiences on grant paths.

        The invite dropdown derives from the same rule, but the API must
        enforce it itself — otherwise a direct call could self-escalate to
        SUPER_ADMIN.
        """
        if role.is_platform or role.name in NON_INVITABLE_ROLES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role.name}' cannot be assigned from the institution console",
            )

    @staticmethod
    async def _load_user(db, tenant_id, user_id) -> User:
        res = await db.execute(select(User).where(User.id == user_id, User.tenant_id == tenant_id, User.deleted_at == None))  # noqa: E712
        user = res.scalar_one_or_none()
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    @staticmethod
    async def _assert_user_in_tenant(db, tenant_id, user_id) -> None:
        await InstitutionService._load_user(db, tenant_id, user_id)

    @staticmethod
    async def _assert_dept(db, tenant_id, dept_id) -> None:
        res = await db.execute(select(Department.id).where(Department.id == dept_id, Department.tenant_id == tenant_id))
        if res.scalar_one_or_none() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Department not found")

    @staticmethod
    async def _assert_year(db, tenant_id, year_id) -> None:
        res = await db.execute(select(AcademicYear.id).where(AcademicYear.id == year_id, AcademicYear.tenant_id == tenant_id))
        if res.scalar_one_or_none() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Academic year not found")

    @staticmethod
    async def _assert_class(db, tenant_id, class_id) -> None:
        res = await db.execute(select(SchoolClass.id).where(SchoolClass.id == class_id, SchoolClass.tenant_id == tenant_id))
        if res.scalar_one_or_none() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Class not found")

    @staticmethod
    async def _staff_out(db, tenant_id, user: User) -> StaffOut:
        roles_res = await db.execute(
            select(Role.name)
            .select_from(RoleAssignment)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(RoleAssignment.user_id == user.id, RoleAssignment.tenant_id == tenant_id, RoleAssignment.is_active == True)  # noqa: E712
        )
        roles = list(set(roles_res.scalars().all()))
        dept_res = await db.execute(
            select(RoleAssignment.scope_id).where(
                RoleAssignment.user_id == user.id, RoleAssignment.tenant_id == tenant_id,
                RoleAssignment.scope_type == "DEPARTMENT", RoleAssignment.is_active == True,  # noqa: E712
            ).limit(1)
        )
        dept_id = dept_res.scalar_one_or_none()
        if dept_id is None:
            sp_res = await db.execute(
                select(StaffProfile.department_id).where(
                    StaffProfile.user_id == user.id, StaffProfile.tenant_id == tenant_id
                )
            )
            dept_id = sp_res.scalar_one_or_none()
        dept_name = None
        if dept_id:
            dn = await db.execute(select(Department.name).where(Department.id == dept_id))
            dept_name = dn.scalar_one_or_none()
        return StaffOut(
            id=user.id, name=user.name, email=user.email, phone=user.phone,
            is_active=user.is_active, last_login_at=user.last_login_at, roles=roles,
            department_id=dept_id, department_name=dept_name,
        )

    @staticmethod
    async def _plan_name(db, tenant: Tenant) -> str | None:
        if tenant.plan_id is None:
            return None
        res = await db.execute(select(Plan.name).where(Plan.id == tenant.plan_id))
        return res.scalar_one_or_none()

    @staticmethod
    async def _subscription_status(db, tenant_id) -> str | None:
        res = await db.execute(
            select(Subscription.status).where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc()).limit(1)
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def _queue_invite_email(db, tenant: Tenant, user: User, raw_token: str) -> None:
        domain = get_app_settings().PUBLIC_ROOT_DOMAIN or "xyz.com"
        link = f"https://{tenant.slug}.{domain}/reset-password?token={raw_token}"
        queue_email(
            db,
            "staff.invited",
            to=user.email or "",
            context={
                "name": user.name,
                "tenant_name": tenant.name,
                "invite_url": link,
            },
            tenant_id=tenant.id,
        )


def _year_out(y: AcademicYear) -> AcademicYearOut:
    return AcademicYearOut(id=y.id, name=y.name, start_date=y.start_date, end_date=y.end_date, is_current=y.is_current)
