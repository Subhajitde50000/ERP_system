"""
Services — First-Time Setup Wizard

Step 10 of the institution-admin journey. The admin lands here after the
first login instead of the dashboard. Progress is persisted server-side in
`tenant_settings['onboarding']` (SYSTEM-FLOW §4.3: state lives in
tenant_settings, not the browser) so a 2,000-student college can resume.

`materialize()` turns a completed state into real rows:
  academic_years (already created at provisioning — updated in place)
  departments, classes (sections = classes), subjects
  invited staff → users + role_assignments
  imported students → users + STUDENT role
  modules → tenant_modules (plan-gated)
  branding → tenants.logo_url + tenant_settings
"""

import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic import AcademicYear, Department, SchoolClass, Subject
from app.models.billing import TenantModule, TenantSetting
from app.models.role import Role, RoleAssignment
from app.models.tenant import Tenant, TenantType
from app.models.user import User
from app.schemas.setup import (
    SetupEntityCounts,
    SetupResponse,
    SetupState,
)
from app.utils.security import hash_password

ONBOARDING_KEY = "onboarding"
DEFAULT_SETUP_PASSWORD = "Setup@12345"  # staff get a reset link in real deployments

# SECURITY: Do NOT use a shared constant for student initial passwords.
# Each account receives a unique cryptographically-random password so that
# knowing one student's roll number does not grant access to any account.
def _random_student_password() -> str:
    """Return a per-user unguessable initial password (never shared across accounts)."""
    from app.utils.security import generate_secure_token
    return generate_secure_token(32)


class SetupService:
    # ── Read ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def _tenant(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
        res = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = res.scalar_one_or_none()
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
            )
        return tenant

    @staticmethod
    async def _load_state(db: AsyncSession, tenant_id: uuid.UUID) -> dict:
        res = await db.execute(
            select(TenantSetting).where(
                TenantSetting.tenant_id == tenant_id,
                TenantSetting.key == ONBOARDING_KEY,
            )
        )
        setting = res.scalar_one_or_none()
        if setting is None:
            return {}
        try:
            return json.loads(setting.value)
        except (TypeError, json.JSONDecodeError):
            return {}

    @staticmethod
    async def get_state(db: AsyncSession, tenant_id: uuid.UUID) -> SetupResponse:
        tenant = await SetupService._tenant(db, tenant_id)
        state = await SetupService._load_state(db, tenant_id)
        entities = await SetupService._counts(db, tenant_id)
        return SetupResponse(
            tenant_id=tenant.id,
            tenant_slug=tenant.slug,
            state=SetupState.model_validate(state),
            entities=entities,
        )

    # ── Write ────────────────────────────────────────────────────────────────

    @staticmethod
    async def save_state(
        db: AsyncSession, tenant_id: uuid.UUID, state: SetupState
    ) -> SetupResponse:
        """Upsert the full wizard state (called after every step)."""
        tenant = await SetupService._tenant(db, tenant_id)
        raw = state.model_dump(mode="json")
        res = await db.execute(
            select(TenantSetting).where(
                TenantSetting.tenant_id == tenant_id,
                TenantSetting.key == ONBOARDING_KEY,
            )
        )
        setting = res.scalar_one_or_none()
        if setting is None:
            setting = TenantSetting(
                tenant_id=tenant_id, key=ONBOARDING_KEY, value="{}"
            )
            db.add(setting)
        setting.value = json.dumps(raw)
        await db.flush()
        entities = await SetupService._counts(db, tenant_id)
        return SetupResponse(
            tenant_id=tenant.id,
            tenant_slug=tenant.slug,
            state=state,
            entities=entities,
        )

    @staticmethod
    async def _counts(db: AsyncSession, tenant_id: uuid.UUID) -> SetupEntityCounts:
        async def count(model) -> int:
            res = await db.execute(
                select(model.id).where(model.tenant_id == tenant_id).limit(1)
            )
            return 1 if res.scalar_one_or_none() is not None else 0

        return SetupEntityCounts(
            academic_years=await count(AcademicYear),
            departments=await count(Department),
            classes=await count(SchoolClass),
            subjects=await count(Subject),
            staff=0,
            students=0,
            modules=0,
        )

    # ── Materialise ──────────────────────────────────────────────────────────

    @staticmethod
    async def complete(
        db: AsyncSession, tenant_id: uuid.UUID
    ) -> SetupResponse:
        """
        Called when the admin finishes the wizard (step 12).

        Materialises departments → classes → subjects → staff → students →
        modules into real tables, flags the tenant as onboarded, and marks
        the state complete so the dashboard gate opens.
        """
        tenant = await SetupService._tenant(db, tenant_id)
        raw = await SetupService._load_state(db, tenant_id)
        state = SetupState.model_validate(raw)
        state.completed = True
        state.step = 12

        await SetupService._materialize_entities(db, tenant, state)
        await SetupService._mark_complete(db, tenant, state)

        entities = await SetupService._counts(db, tenant_id)
        return SetupResponse(
            tenant_id=tenant.id,
            tenant_slug=tenant.slug,
            state=state,
            entities=entities,
        )

    @staticmethod
    async def _materialize_entities(
        db: AsyncSession, tenant: Tenant, state: SetupState
    ) -> None:
        # 1. Profile → tenants row.
        profile = state.profile
        if profile is not None:
            if profile.name:
                tenant.name = profile.name
            if profile.type:
                tenant.type = TenantType(profile.type)
            if profile.email:
                tenant.email = str(profile.email)
            if profile.phone:
                tenant.phone = profile.phone
            if profile.address:
                tenant.address = profile.address
            if profile.city:
                tenant.city = profile.city
            if profile.state:
                tenant.state = profile.state
            if profile.country:
                tenant.country = profile.country
            if profile.pincode:
                tenant.pincode = profile.pincode
            if profile.website:
                tenant.website = profile.website
            if profile.timezone:
                tenant.timezone = profile.timezone

        # 2. Academic year — the provisioning template is updated in place.
        year = await SetupService._current_year(db, tenant.id)
        if year is None and state.academic_year is not None:
            year = AcademicYear(
                tenant_id=tenant.id,
                name=state.academic_year.name,
                start_date=state.academic_year.start_date,
                end_date=state.academic_year.end_date,
                is_current=True,
            )
            db.add(year)
        elif year is not None and state.academic_year is not None:
            year.name = state.academic_year.name
            year.start_date = state.academic_year.start_date
            year.end_date = state.academic_year.end_date
            year.is_current = True
        await db.flush()

        # 3. Departments.
        dept_by_code: dict[str, Department] = {}
        for dep in state.departments:
            res = await db.execute(
                select(Department).where(
                    Department.tenant_id == tenant.id, Department.code == dep.code
                )
            )
            row = res.scalar_one_or_none()
            if row is None:
                row = Department(
                    tenant_id=tenant.id,
                    name=dep.name,
                    code=dep.code,
                    description=dep.description,
                )
                db.add(row)
            else:
                row.name = dep.name
                row.description = dep.description
            dept_by_code[dep.code] = row
        await db.flush()

        # 4. Classes (sections are classes — "10-A", "CSE-3").
        class_by_code: dict[str, SchoolClass] = {}
        for cls in state.classes:
            department = dept_by_code.get(cls.department_code)
            if department is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Class '{cls.code}' references unknown department '{cls.department_code}'",
                )
            if year is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Set the academic year before creating classes",
                )
            res = await db.execute(
                select(SchoolClass).where(
                    SchoolClass.tenant_id == tenant.id, SchoolClass.code == cls.code
                )
            )
            row = res.scalar_one_or_none()
            name = cls.section and f"{cls.name} · {cls.section}" or cls.name
            if row is None:
                row = SchoolClass(
                    tenant_id=tenant.id,
                    department_id=department.id,
                    academic_year_id=year.id,
                    name=name,
                    code=cls.code,
                    max_strength=cls.max_strength,
                    room_no=cls.room_no,
                )
                db.add(row)
            else:
                row.department_id = department.id
                row.academic_year_id = year.id
                row.name = name
                row.max_strength = cls.max_strength
                row.room_no = cls.room_no
            class_by_code[cls.code] = row
        await db.flush()

        # 5. Subjects.
        for subject in state.subjects:
            school_class = class_by_code.get(subject.class_code)
            if school_class is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Subject '{subject.code}' references unknown class '{subject.class_code}'",
                )
            res = await db.execute(
                select(Subject).where(
                    Subject.tenant_id == tenant.id, Subject.code == subject.code
                )
            )
            row = res.scalar_one_or_none()
            if row is None:
                row = Subject(
                    tenant_id=tenant.id,
                    class_id=school_class.id,
                    name=subject.name,
                    code=subject.code,
                    subject_type=subject.subject_type,
                    credits=subject.credits,
                    max_marks=subject.max_marks,
                    passing_marks=subject.passing_marks,
                )
                db.add(row)
            else:
                row.class_id = school_class.id
                row.name = subject.name
                row.subject_type = subject.subject_type
                row.credits = subject.credits
                row.max_marks = subject.max_marks
                row.passing_marks = subject.passing_marks
        await db.flush()

        # 6. Staff → users + role assignments.
        roles = await SetupService._roles_by_name(db)
        now = datetime.now(timezone.utc)
        for member in state.staff:
            email = str(member.email).lower()
            res = await db.execute(
                select(User).where(
                    User.tenant_id == tenant.id, User.email == email
                )
            )
            user = res.scalar_one_or_none()
            if user is None:
                user = User(
                    tenant_id=tenant.id,
                    name=member.name,
                    email=email,
                    phone=member.phone,
                    password_hash=hash_password(DEFAULT_SETUP_PASSWORD),
                    is_active=True,
                )
                db.add(user)
                await db.flush()
            role = roles.get(member.role)
            if role is not None:
                res2 = await db.execute(
                    select(RoleAssignment.id).where(
                        RoleAssignment.user_id == user.id,
                        RoleAssignment.role_id == role.id,
                        RoleAssignment.tenant_id == tenant.id,
                        RoleAssignment.is_active == True,  # noqa: E712
                    )
                )
                if res2.scalar_one_or_none() is None:
                    db.add(
                        RoleAssignment(
                            user_id=user.id,
                            role_id=role.id,
                            tenant_id=tenant.id,
                            assigned_at=now,
                            is_active=True,
                        )
                    )
        await db.flush()

        # 7. Students → users + STUDENT role.
        student_role = roles.get("STUDENT")
        for student in state.students:
            res = await db.execute(
                select(User).where(
                    User.tenant_id == tenant.id,
                    User.student_roll_no == student.roll_no,
                )
            )
            user = res.scalar_one_or_none()
            if user is None:
                user = User(
                    tenant_id=tenant.id,
                    name=student.name,
                    email=str(student.email).lower() if student.email else None,
                    gender=student.gender,
                    date_of_birth=student.date_of_birth,
                    student_roll_no=student.roll_no,
                    password_hash=hash_password(_random_student_password()),
                    is_active=True,
                )
                db.add(user)
                await db.flush()
            if student_role is not None:
                res2 = await db.execute(
                    select(RoleAssignment.id).where(
                        RoleAssignment.user_id == user.id,
                        RoleAssignment.role_id == student_role.id,
                        RoleAssignment.tenant_id == tenant.id,
                        RoleAssignment.is_active == True,  # noqa: E712
                    )
                )
                if res2.scalar_one_or_none() is None:
                    db.add(
                        RoleAssignment(
                            user_id=user.id,
                            role_id=student_role.id,
                            tenant_id=tenant.id,
                            assigned_at=now,
                            is_active=True,
                        )
                    )
        await db.flush()

        # 8. Modules — plan-gated: only modules the tenant's plan allows.
        await SetupService._sync_modules(db, tenant, state.modules)

        # 9. Branding.
        branding = state.branding
        if branding is not None:
            if branding.logo_url:
                tenant.logo_url = branding.logo_url
            if branding.primary_color:
                await SetupService._set_setting(
                    db, tenant.id, "branding.primary_color", branding.primary_color
                )
            if branding.tagline:
                await SetupService._set_setting(
                    db, tenant.id, "branding.tagline", branding.tagline
                )
        await db.flush()

    @staticmethod
    async def _current_year(
        db: AsyncSession, tenant_id: uuid.UUID
    ) -> AcademicYear | None:
        res = await db.execute(
            select(AcademicYear)
            .where(AcademicYear.tenant_id == tenant_id)
            .order_by(AcademicYear.is_current.desc(), AcademicYear.start_date.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def _roles_by_name(db: AsyncSession) -> dict[str, Role]:
        res = await db.execute(select(Role))
        return {role.name: role for role in res.scalars().all()}

    @staticmethod
    async def _set_setting(
        db: AsyncSession, tenant_id: uuid.UUID, key: str, value: str
    ) -> None:
        res = await db.execute(
            select(TenantSetting).where(
                TenantSetting.tenant_id == tenant_id, TenantSetting.key == key
            )
        )
        setting = res.scalar_one_or_none()
        if setting is None:
            db.add(TenantSetting(tenant_id=tenant_id, key=key, value=value))
        else:
            setting.value = value

    @staticmethod
    async def _sync_modules(
        db: AsyncSession, tenant: Tenant, module_keys: list[str]
    ) -> None:
        """Enable selected modules — but never beyond the tenant's plan."""
        from app.models.catalog import Module, Plan

        plan_res = await db.execute(select(Plan).where(Plan.id == tenant.plan_id))
        plan = plan_res.scalar_one_or_none()
        allowed = set(plan.allowed_modules or []) if plan else set()

        res = await db.execute(select(Module))
        modules = list(res.scalars().all())

        existing_res = await db.execute(
            select(TenantModule).where(TenantModule.tenant_id == tenant.id)
        )
        existing = {tm.module_key: tm for tm in existing_res.scalars().all()}

        now = datetime.now(timezone.utc)
        for module in modules:
            if module.is_core:
                wanted = True
            elif module.key in module_keys and module.key in allowed:
                wanted = True
            else:
                wanted = False
            row = existing.get(module.key)
            if row is None:
                if wanted:
                    db.add(
                        TenantModule(
                            tenant_id=tenant.id,
                            module_key=module.key,
                            is_enabled=True,
                            enabled_at=now,
                        )
                    )
            elif wanted and not row.is_enabled:
                row.is_enabled = True
                row.enabled_at = now
            elif not wanted and row.is_enabled:
                row.is_enabled = False
                row.disabled_at = now
        await db.flush()

    @staticmethod
    async def _mark_complete(
        db: AsyncSession, tenant: Tenant, state: SetupState
    ) -> None:
        res = await db.execute(
            select(TenantSetting).where(
                TenantSetting.tenant_id == tenant.id,
                TenantSetting.key == ONBOARDING_KEY,
            )
        )
        setting = res.scalar_one_or_none()
        if setting is None:
            setting = TenantSetting(
                tenant_id=tenant.id, key=ONBOARDING_KEY, value="{}"
            )
            db.add(setting)
        setting.value = json.dumps(state.model_dump(mode="json"))
        await SetupService._set_setting(db, tenant.id, "onboarding.completed", "true")
        await db.flush()
