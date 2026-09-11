"""
Services — Super Admin console (C-SA-01 … C-SA-08)

The platform-layer counterpart of `InstitutionService`: everything the
Super Admin does to tenants, plans, platform staff, the audit trail and
global settings.

Boundaries that shape this file:

  * §4.1 "access all institution data (**audit-only, no edit**)" — this
    service reads tenant records and edits *platform* concerns (plan, modules,
    lifecycle, profile). It never touches a tenant's academic data.
  * Every mutation writes an `audit_logs` row in the same transaction
    (`AuditService.record`), so the trail cannot drift from reality.
  * Tenant creation reuses `SignupService`'s provisioning primitives instead
    of re-implementing them — one pipeline, whether the tenant arrives through
    self-service checkout or a Super Admin creating it by hand.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.academic import AcademicYear
from app.models.audit import AuditLog
from app.models.billing import (
    PlatformInvoice,
    Subscription,
    TenantModule,
    TenantSetting,
)
from app.models.catalog import Module, Plan
from app.models.platform_setting import (
    PLATFORM_SETTING_DEFAULTS,
    PLATFORM_SETTING_INT_KEYS,
    PlatformSetting,
)
from app.models.platform_user import PlatformRole, PlatformUser
from app.models.role import Role, RoleAssignment
from app.models.support_ticket import SupportTicket
from app.models.tenant import Tenant, TenantType
from app.models.user import User
from app.schemas.platform_admin import (
    AuditEntry,
    ModuleFlag,
    PlanCreate,
    PlanRow,
    PlanUpdate,
    PlatformSettingsOut,
    PlatformSettingsUpdate,
    PlatformStats,
    PlatformUserCreate,
    PlatformUserRow,
    PlatformUserUpdate,
    PlanMixPoint,
    SubscriptionRow,
    TenantCreate,
    TenantCreated,
    TenantDetail,
    TenantRow,
    TenantUpdate,
    TrendPoint,
)
from app.services.audit_service import AuditService
from app.services.mailer import queue_email
from app.utils.security import generate_secure_token, hash_password, hash_token

settings = get_settings()

# Subdomains the platform itself answers on — a tenant may never claim them.
RESERVED_SLUGS = frozenset(
    {
        "www", "app", "api", "admin", "platform", "support", "sales",
        "finance", "billing", "docs", "status", "mail", "static", "cdn",
        "assets", "help", "blog", "about", "login", "signup",
    }
)

ACTIVE_SUB_STATUSES = ("TRIAL", "ACTIVE", "PAST_DUE")


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _conflict(msg: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)


def _bad(msg: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


class PlatformAdminService:
    # ══ Shared loaders ═══════════════════════════════════════════════════════
    # Used by several endpoints; written once here rather than per-router.

    @staticmethod
    async def _tenant(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
        res = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = res.scalar_one_or_none()
        if tenant is None:
            raise _not_found("Institution")
        return tenant

    @staticmethod
    async def _plan_by_slug(db: AsyncSession, slug: str) -> Plan:
        res = await db.execute(select(Plan).where(Plan.slug == slug))
        plan = res.scalar_one_or_none()
        if plan is None:
            raise _not_found(f"Plan '{slug}'")
        return plan

    @staticmethod
    async def _counts_by_role(
        db: AsyncSession, tenant_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, int]]:
        """
        Student/teacher headcount per tenant in ONE query.

        Counting per tenant inside a loop is the classic N+1 that makes the
        institution list crawl; this groups instead so the page is two queries
        regardless of tenant count.
        """
        ids = list(tenant_ids)
        if not ids:
            return {}
        res = await db.execute(
            select(User.tenant_id, Role.name, func.count(func.distinct(User.id)))
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                User.tenant_id.in_(ids),
                User.is_active.is_(True),
                RoleAssignment.is_active.is_(True),
                Role.name.in_(("STUDENT", "TEACHER")),
            )
            .group_by(User.tenant_id, Role.name)
        )
        out: dict[uuid.UUID, dict[str, int]] = {}
        for tenant_id, role_name, count in res.all():
            out.setdefault(tenant_id, {})[role_name] = int(count)
        return out

    @staticmethod
    async def _latest_subs(
        db: AsyncSession, tenant_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, Subscription]:
        """Newest subscription per tenant — the one whose status is 'current'."""
        ids = list(tenant_ids)
        if not ids:
            return {}
        res = await db.execute(
            select(Subscription)
            .where(Subscription.tenant_id.in_(ids))
            .order_by(Subscription.tenant_id, Subscription.created_at.desc())
        )
        latest: dict[uuid.UUID, Subscription] = {}
        for sub in res.scalars().all():
            latest.setdefault(sub.tenant_id, sub)
        return latest

    @staticmethod
    async def _modules_by_tenant(
        db: AsyncSession, tenant_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, list[str]]:
        ids = list(tenant_ids)
        if not ids:
            return {}
        res = await db.execute(
            select(TenantModule.tenant_id, TenantModule.module_key)
            .where(TenantModule.tenant_id.in_(ids), TenantModule.is_enabled.is_(True))
            .order_by(TenantModule.module_key)
        )
        out: dict[uuid.UUID, list[str]] = {}
        for tenant_id, key in res.all():
            out.setdefault(tenant_id, []).append(key)
        return out

    @staticmethod
    def _row(
        tenant: Tenant,
        plan: Plan | None,
        sub: Subscription | None,
        counts: dict[str, int],
        modules: list[str],
    ) -> TenantRow:
        """The single place a Tenant becomes a TenantRow."""
        return TenantRow(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            type=tenant.type.value if hasattr(tenant.type, "value") else str(tenant.type),
            plan_name=plan.name if plan else "—",
            plan_slug=plan.slug if plan else "",
            # No subscription row yet → the tenant is still on its trial.
            status=(sub.status if sub else "TRIAL"),  # type: ignore[arg-type]
            is_active=tenant.is_active,
            student_count=counts.get("STUDENT", 0),
            teacher_count=counts.get("TEACHER", 0),
            enabled_modules=modules,
            # Not metered yet — surfaced as 0 rather than invented, so the
            # console never shows a number the platform cannot back up.
            storage_used_gb=0.0,
            city=tenant.city,
            state=tenant.state,
            email=tenant.email,
            phone=tenant.phone,
            website=tenant.website,
            timezone=tenant.timezone,
            trial_ends_at=tenant.trial_ends_at,
            created_at=tenant.created_at,
        )

    @staticmethod
    async def _rows(db: AsyncSession, tenants: list[Tenant]) -> list[TenantRow]:
        """Batch-hydrate tenants — 4 queries total, not 4 per tenant."""
        if not tenants:
            return []
        ids = [t.id for t in tenants]
        plan_ids = {t.plan_id for t in tenants if t.plan_id}
        plans: dict[uuid.UUID, Plan] = {}
        if plan_ids:
            res = await db.execute(select(Plan).where(Plan.id.in_(plan_ids)))
            plans = {p.id: p for p in res.scalars().all()}

        counts = await PlatformAdminService._counts_by_role(db, ids)
        subs = await PlatformAdminService._latest_subs(db, ids)
        modules = await PlatformAdminService._modules_by_tenant(db, ids)

        return [
            PlatformAdminService._row(
                t,
                plans.get(t.plan_id) if t.plan_id else None,
                subs.get(t.id),
                counts.get(t.id, {}),
                modules.get(t.id, []),
            )
            for t in tenants
        ]

    # ══ C-SA-02 · Institution list ═══════════════════════════════════════════

    @staticmethod
    async def list_tenants(
        db: AsyncSession,
        *,
        search: str | None = None,
        plan_slug: str | None = None,
        state: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[TenantRow]:
        stmt = select(Tenant)
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(
                func.lower(Tenant.name).like(like)
                | func.lower(Tenant.slug).like(like)
                | func.lower(func.coalesce(Tenant.city, "")).like(like)
            )
        if plan_slug and plan_slug != "ALL":
            plan = await PlatformAdminService._plan_by_slug(db, plan_slug)
            stmt = stmt.where(Tenant.plan_id == plan.id)
        if state == "SUSPENDED":
            stmt = stmt.where(Tenant.is_active.is_(False))

        res = await db.execute(stmt.order_by(Tenant.name).limit(limit).offset(offset))
        rows = await PlatformAdminService._rows(db, list(res.scalars().all()))

        # Subscription status lives on `subscriptions`, not `tenants`, so this
        # filter is applied after hydration rather than as another join.
        if state and state not in ("ALL", "SUSPENDED"):
            rows = [r for r in rows if r.is_active and r.status == state]
        return rows

    # ══ C-SA-03 · Institution detail ═════════════════════════════════════════

    @staticmethod
    async def tenant_detail(db: AsyncSession, tenant_id: uuid.UUID) -> TenantDetail:
        tenant = await PlatformAdminService._tenant(db, tenant_id)
        row = (await PlatformAdminService._rows(db, [tenant]))[0]

        sub_res = await db.execute(
            select(Subscription)
            .where(Subscription.tenant_id == tenant.id)
            .order_by(Subscription.created_at.desc())
        )
        plan_res = await db.execute(select(Plan))
        plans = {p.id: p for p in plan_res.scalars().all()}
        subscriptions = [
            SubscriptionRow(
                id=s.id,
                tenant_id=s.tenant_id,
                tenant_name=tenant.name,
                plan_name=plans[s.plan_id].name if s.plan_id in plans else "—",
                status=s.status,  # type: ignore[arg-type]
                starts_at=s.starts_at,
                ends_at=s.ends_at,
                amount=float(s.amount),
                currency=s.currency,
                payment_reference=s.payment_reference,
                cycle=_cycle(s.starts_at, s.ends_at),
            )
            for s in sub_res.scalars().all()
        ]

        admin_name, admin_email = await PlatformAdminService._admin_contact(db, tenant)

        audit_res = await db.execute(
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant.id)
            .order_by(AuditLog.created_at.desc())
            .limit(10)
        )
        activity = await AuditService.to_entries(db, list(audit_res.scalars().all()))

        tickets = 0
        if tenant.owner_id is not None:
            t_res = await db.execute(
                select(func.count())
                .select_from(SupportTicket)
                .where(
                    SupportTicket.tenant_id == tenant.id,
                    SupportTicket.status.in_(("OPEN", "IN_PROGRESS")),
                )
            )
            tickets = int(t_res.scalar() or 0)

        return TenantDetail(
            tenant=row,
            subscriptions=subscriptions,
            admin_name=admin_name,
            admin_email=admin_email,
            recent_activity=activity,
            open_tickets=tickets,
        )

    @staticmethod
    async def _admin_contact(db: AsyncSession, tenant: Tenant) -> tuple[str, str]:
        """The institution's own admin — who the platform contacts."""
        res = await db.execute(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                User.tenant_id == tenant.id,
                Role.name == "INSTITUTION_ADMIN",
                RoleAssignment.is_active.is_(True),
            )
            .order_by(User.created_at)
            .limit(1)
        )
        admin = res.scalar_one_or_none()
        if admin is not None:
            return admin.name, admin.email or (tenant.email or "—")
        return "Unassigned", tenant.email or "—"

    # ══ C-SA-04 · Create institution ═════════════════════════════════════════

    @staticmethod
    async def create_tenant(
        db: AsyncSession,
        payload: TenantCreate,
        actor: PlatformUser,
        request: Request | None = None,
    ) -> TenantCreated:
        """
        Create tenant + subscription + admin + roles + modules + settings +
        academic-year template, then email the admin an activation link.

        Same pipeline as self-service checkout (`SignupService.provision`),
        minus the order/invoice: a Super-Admin-created institution is billed
        by contract, not by card. One transaction — a half-created tenant
        that nobody can log into must not survive (SYSTEM-FLOW §2.1).
        """
        slug = payload.slug.strip().lower()
        if slug in RESERVED_SLUGS:
            raise _conflict(f"'{slug}' is reserved for the platform console")

        exists = await db.execute(select(Tenant.id).where(Tenant.slug == slug))
        if exists.scalar_one_or_none() is not None:
            raise _conflict("That subdomain is already taken")

        plan = await PlatformAdminService._plan_by_slug(db, payload.plan_slug)
        email = str(payload.admin_email).lower()

        now = datetime.now(timezone.utc)
        trial_days = await PlatformAdminService._trial_days(db)
        tenant = Tenant(
            id=uuid.uuid4(),
            name=payload.name.strip(),
            slug=slug,
            type=TenantType(payload.type),
            plan_id=plan.id,
            city=payload.city,
            state=payload.state,
            phone=payload.phone,
            email=email,
            timezone=await PlatformAdminService._setting(db, "default_timezone"),
            is_active=True,
            trial_ends_at=(now + timedelta(days=trial_days)) if payload.trial else None,
        )
        db.add(tenant)
        await db.flush()

        subscription = Subscription(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="TRIAL" if payload.trial else "ACTIVE",
            starts_at=now,
            ends_at=(now + timedelta(days=trial_days)) if payload.trial else None,
            amount=Decimal("0") if payload.trial else plan.price_monthly,
            currency=plan.currency,
        )
        db.add(subscription)

        # Institution admin — no password yet; the activation link sets it.
        raw_token = generate_secure_token(32)
        admin = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name=payload.admin_name.strip(),
            email=email,
            password_hash=None,
            is_active=True,
            password_reset_token=hash_token(raw_token),
            password_reset_expires=now + timedelta(days=7),
        )
        db.add(admin)
        await db.flush()

        role_res = await db.execute(
            select(Role).where(
                Role.name == "INSTITUTION_ADMIN",
                Role.is_platform.is_(False),
            )
        )
        admin_role = role_res.scalar_one_or_none()
        if admin_role is None:
            raise _bad(
                "INSTITUTION_ADMIN role is missing — run scripts/seed_data.py"
            )
        db.add(
            RoleAssignment(
                user_id=admin.id,
                role_id=admin_role.id,
                tenant_id=tenant.id,
                is_active=True,
            )
        )

        enabled = await PlatformAdminService._sync_modules(
            db, tenant.id, set(plan.allowed_modules)
        )

        currency = await PlatformAdminService._setting(db, "default_currency")
        for key, value in {
            "onboarding": (
                '{"completed": false, "step": 0, "profile": null, "logo": null, '
                '"academic_year": null, "departments": [], "programs": [], '
                '"classes": [], "subjects": [], "staff": [], "students": [], '
                '"modules": [], "branding": null, "meta": {}}'
            ),
            "currency": currency,
            "timezone": tenant.timezone,
        }.items():
            db.add(TenantSetting(tenant_id=tenant.id, key=key, value=value))

        year = date.today().year
        db.add(
            AcademicYear(
                tenant_id=tenant.id,
                name=f"{year}-{str(year + 1)[-2:]}",
                start_date=date(year, 6, 1),
                end_date=date(year + 1, 5, 31),
                is_current=True,
            )
        )

        domain = settings.PUBLIC_ROOT_DOMAIN or "shikshasync.me"
        scheme = "http" if "localhost" in domain else "https"
        login_url = f"{scheme}://{slug}.{domain}/login"
        queue_email(
            db,
            "staff.invited",
            to=email,
            context={
                "name": admin.name,
                "tenant_name": tenant.name,
                "invite_url": f"https://{slug}.{domain}/reset-password?token={raw_token}",
            },
            tenant_id=tenant.id,
        )

        AuditService.record(
            db,
            actor=actor,
            actor_role=actor.platform_role.value,
            action="TENANT_CREATED",
            entity="tenant",
            entity_id=tenant.id,
            tenant_id=tenant.id,
            new_value={
                "name": tenant.name,
                "slug": slug,
                "type": payload.type,
                "plan": plan.slug,
                "trial": payload.trial,
                "admin_email": email,
            },
            request=request,
        )

        await db.flush()
        await db.commit()

        row = (await PlatformAdminService._rows(db, [tenant]))[0]
        return TenantCreated(
            tenant=row,
            admin_email=email,
            login_url=login_url,
            activation_token=raw_token if settings.APP_DEBUG else None,
        )

    # ══ C-SA-03 · Update / suspend / delete ══════════════════════════════════

    @staticmethod
    async def update_tenant(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        payload: TenantUpdate,
        actor: PlatformUser,
        request: Request | None = None,
    ) -> TenantRow:
        tenant = await PlatformAdminService._tenant(db, tenant_id)
        before = {
            "name": tenant.name,
            "plan_id": str(tenant.plan_id) if tenant.plan_id else None,
            "city": tenant.city,
            "timezone": tenant.timezone,
        }
        changed: dict[str, Any] = {}

        if payload.plan_slug is not None:
            plan = await PlatformAdminService._plan_by_slug(db, payload.plan_slug)
            tenant.plan_id = plan.id
            changed["plan"] = plan.slug
            # A plan change must re-scope modules, or a downgraded tenant keeps
            # features it no longer pays for.
            await PlatformAdminService._sync_modules(
                db, tenant.id, set(plan.allowed_modules)
            )

        for field in ("name", "city", "state", "phone", "website", "timezone"):
            value = getattr(payload, field)
            if value is not None:
                setattr(tenant, field, value.strip() if isinstance(value, str) else value)
                changed[field] = value
        if payload.email is not None:
            tenant.email = str(payload.email).lower()
            changed["email"] = tenant.email

        if payload.enabled_modules is not None:
            plan = None
            if tenant.plan_id:
                p_res = await db.execute(select(Plan).where(Plan.id == tenant.plan_id))
                plan = p_res.scalar_one_or_none()
            allowed = set(plan.allowed_modules) if plan else set()
            requested = set(payload.enabled_modules)
            # §4.1: a tenant can only enable what its plan offers.
            illegal = requested - allowed
            if illegal:
                raise _bad(
                    f"Plan '{plan.slug if plan else '—'}' does not include: "
                    f"{', '.join(sorted(illegal))}"
                )
            changed["modules"] = await PlatformAdminService._sync_modules(
                db, tenant.id, requested
            )

        if not changed:
            return (await PlatformAdminService._rows(db, [tenant]))[0]

        AuditService.record(
            db,
            actor=actor,
            actor_role=actor.platform_role.value,
            action="TENANT_UPDATED",
            entity="tenant",
            entity_id=tenant.id,
            tenant_id=tenant.id,
            old_value=before,
            new_value={"name": tenant.name, **changed},
            request=request,
        )
        await db.flush()
        await db.commit()
        return (await PlatformAdminService._rows(db, [tenant]))[0]

    @staticmethod
    async def set_tenant_active(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        active: bool,
        actor: PlatformUser,
        request: Request | None = None,
    ) -> TenantRow:
        """
        Suspend / reactivate. `is_active=False` locks every user of the
        institution out at login — it does not delete anything.
        """
        tenant = await PlatformAdminService._tenant(db, tenant_id)
        if tenant.is_active == active:
            return (await PlatformAdminService._rows(db, [tenant]))[0]

        tenant.is_active = active
        AuditService.record(
            db,
            actor=actor,
            actor_role=actor.platform_role.value,
            action="TENANT_REACTIVATED" if active else "TENANT_SUSPENDED",
            entity="tenant",
            entity_id=tenant.id,
            tenant_id=tenant.id,
            old_value={"is_active": not active},
            new_value={"name": tenant.name, "is_active": active},
            request=request,
        )
        await db.flush()
        await db.commit()
        return (await PlatformAdminService._rows(db, [tenant]))[0]

    @staticmethod
    async def delete_tenant(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        actor: PlatformUser,
        request: Request | None = None,
    ) -> None:
        """
        Soft delete — deactivate and cancel the subscription.

        A hard DELETE would cascade through ~100 tables of academic history
        (§10.3 keeps an append-only trail precisely so that cannot happen by
        accident). Purging a tenant for real is a deliberate, separate
        operations task, not a button in the console.
        """
        tenant = await PlatformAdminService._tenant(db, tenant_id)
        tenant.is_active = False

        subs = await db.execute(
            select(Subscription).where(
                Subscription.tenant_id == tenant.id,
                Subscription.status.in_(ACTIVE_SUB_STATUSES),
            )
        )
        for sub in subs.scalars().all():
            sub.status = "CANCELLED"
            sub.ends_at = datetime.now(timezone.utc)

        AuditService.record(
            db,
            actor=actor,
            actor_role=actor.platform_role.value,
            action="TENANT_DELETED",
            entity="tenant",
            entity_id=tenant.id,
            tenant_id=tenant.id,
            old_value={"is_active": True},
            new_value={"name": tenant.name, "slug": tenant.slug, "soft_deleted": True},
            request=request,
        )
        await db.flush()
        await db.commit()

    @staticmethod
    async def _sync_modules(
        db: AsyncSession, tenant_id: uuid.UUID, wanted: set[str]
    ) -> list[str]:
        """
        Make `tenant_modules` match `wanted` ∪ core. Core modules are always
        on (§3), so they are added to the target rather than left to the caller.
        """
        mod_res = await db.execute(select(Module).order_by(Module.sort_order))
        catalogue = list(mod_res.scalars().all())
        target = {m.key for m in catalogue if m.is_core} | {
            m.key for m in catalogue if m.key in wanted
        }

        existing_res = await db.execute(
            select(TenantModule).where(TenantModule.tenant_id == tenant_id)
        )
        existing = {tm.module_key: tm for tm in existing_res.scalars().all()}
        now = datetime.now(timezone.utc)

        for key in target:
            row = existing.get(key)
            if row is None:
                db.add(
                    TenantModule(
                        tenant_id=tenant_id,
                        module_key=key,
                        is_enabled=True,
                        enabled_at=now,
                    )
                )
            elif not row.is_enabled:
                row.is_enabled = True
                row.enabled_at = now

        for key, row in existing.items():
            if key not in target and row.is_enabled:
                row.is_enabled = False

        await db.flush()
        return sorted(target)

    # ══ C-SA-05 · Plans ══════════════════════════════════════════════════════

    @staticmethod
    async def list_plans(db: AsyncSession) -> list[PlanRow]:
        res = await db.execute(select(Plan).order_by(Plan.price_monthly))
        plans = list(res.scalars().all())

        count_res = await db.execute(
            select(Tenant.plan_id, func.count())
            .where(Tenant.plan_id.isnot(None))
            .group_by(Tenant.plan_id)
        )
        counts = {pid: int(c) for pid, c in count_res.all()}
        return [_plan_row(p, counts.get(p.id, 0)) for p in plans]

    @staticmethod
    async def create_plan(
        db: AsyncSession,
        payload: PlanCreate,
        actor: PlatformUser,
        request: Request | None = None,
    ) -> PlanRow:
        exists = await db.execute(select(Plan.id).where(Plan.slug == payload.slug))
        if exists.scalar_one_or_none() is not None:
            raise _conflict(f"A plan with slug '{payload.slug}' already exists")

        await PlatformAdminService._assert_modules_exist(db, payload.allowed_modules)

        plan = Plan(
            id=uuid.uuid4(),
            name=payload.name.strip(),
            slug=payload.slug,
            max_students=payload.max_students,
            max_teachers=payload.max_teachers,
            max_storage_gb=payload.max_storage_gb,
            price_monthly=Decimal(str(payload.price_monthly)),
            price_yearly=Decimal(str(payload.price_yearly)),
            currency=payload.currency,
            allowed_modules=payload.allowed_modules,
            is_active=payload.is_active,
        )
        db.add(plan)
        AuditService.record(
            db,
            actor=actor,
            actor_role=actor.platform_role.value,
            action="PLAN_CREATED",
            entity="plan",
            entity_id=plan.id,
            new_value={"name": plan.name, "slug": plan.slug},
            request=request,
        )
        await db.flush()
        await db.commit()
        return _plan_row(plan, 0)

    @staticmethod
    async def update_plan(
        db: AsyncSession,
        plan_id: uuid.UUID,
        payload: PlanUpdate,
        actor: PlatformUser,
        request: Request | None = None,
    ) -> PlanRow:
        res = await db.execute(select(Plan).where(Plan.id == plan_id))
        plan = res.scalar_one_or_none()
        if plan is None:
            raise _not_found("Plan")

        before = {"name": plan.name, "price_monthly": float(plan.price_monthly)}
        changed: dict[str, Any] = {}

        if payload.allowed_modules is not None:
            await PlatformAdminService._assert_modules_exist(db, payload.allowed_modules)
            plan.allowed_modules = payload.allowed_modules
            changed["allowed_modules"] = payload.allowed_modules

        for field in ("name", "max_students", "max_teachers", "max_storage_gb", "is_active"):
            value = getattr(payload, field)
            if value is not None:
                setattr(plan, field, value.strip() if isinstance(value, str) else value)
                changed[field] = value
        for field in ("price_monthly", "price_yearly"):
            value = getattr(payload, field)
            if value is not None:
                setattr(plan, field, Decimal(str(value)))
                changed[field] = value

        if not changed:
            count = await PlatformAdminService._plan_tenant_count(db, plan.id)
            return _plan_row(plan, count)

        AuditService.record(
            db,
            actor=actor,
            actor_role=actor.platform_role.value,
            action="PLAN_UPDATED",
            entity="plan",
            entity_id=plan.id,
            old_value=before,
            new_value={"name": plan.name, **changed},
            request=request,
        )
        await db.flush()
        await db.commit()
        count = await PlatformAdminService._plan_tenant_count(db, plan.id)
        return _plan_row(plan, count)

    @staticmethod
    async def _plan_tenant_count(db: AsyncSession, plan_id: uuid.UUID) -> int:
        res = await db.execute(
            select(func.count()).select_from(Tenant).where(Tenant.plan_id == plan_id)
        )
        return int(res.scalar() or 0)

    @staticmethod
    async def _assert_modules_exist(db: AsyncSession, keys: list[str]) -> None:
        if not keys:
            return
        res = await db.execute(select(Module.key))
        known = {k for (k,) in res.all()}
        unknown = set(keys) - known
        if unknown:
            raise _bad(f"Unknown module keys: {', '.join(sorted(unknown))}")

    # ══ C-SA-06 · Platform users ═════════════════════════════════════════════

    @staticmethod
    async def list_platform_users(db: AsyncSession) -> list[PlatformUserRow]:
        # OWNER rows are customer accounts, not staff — C-SA-06 manages staff.
        res = await db.execute(
            select(PlatformUser)
            .where(PlatformUser.platform_role != PlatformRole.OWNER)
            .order_by(PlatformUser.name)
        )
        return [_user_row(u) for u in res.scalars().all()]

    @staticmethod
    async def create_platform_user(
        db: AsyncSession,
        payload: PlatformUserCreate,
        actor: PlatformUser,
        request: Request | None = None,
    ) -> PlatformUserRow:
        email = str(payload.email).lower()
        exists = await db.execute(
            select(PlatformUser.id).where(PlatformUser.email == email)
        )
        if exists.scalar_one_or_none() is not None:
            raise _conflict("A platform account already uses this email")

        # No password supplied → issue a verification token and email a link,
        # so a Super Admin never has to invent and transmit a password.
        raw_token = generate_secure_token(32)
        user = PlatformUser(
            id=uuid.uuid4(),
            name=payload.name.strip(),
            email=email,
            password_hash=hash_password(payload.password or generate_secure_token(16)),
            platform_role=PlatformRole(payload.role),
            is_active=True,
            email_verification_token_hash=hash_token(raw_token),
        )
        db.add(user)
        queue_email(
            db,
            "platform_owner.verify_email",
            to=email,
            context={"name": user.name, "token": raw_token},
        )
        AuditService.record(
            db,
            actor=actor,
            actor_role=actor.platform_role.value,
            action="PLATFORM_USER_CREATED",
            entity="platform_user",
            entity_id=user.id,
            new_value={"name": user.name, "email": email, "role": payload.role},
            request=request,
        )
        await db.flush()
        await db.commit()
        return _user_row(user)

    @staticmethod
    async def update_platform_user(
        db: AsyncSession,
        user_id: uuid.UUID,
        payload: PlatformUserUpdate,
        actor: PlatformUser,
        request: Request | None = None,
    ) -> PlatformUserRow:
        res = await db.execute(select(PlatformUser).where(PlatformUser.id == user_id))
        user = res.scalar_one_or_none()
        if user is None:
            raise _not_found("Platform user")
        if user.platform_role == PlatformRole.OWNER:
            raise _bad("Owner accounts are customer accounts, not platform staff")

        deactivating = payload.is_active is False
        demoting = (
            payload.role is not None
            and user.platform_role == PlatformRole.SUPER_ADMIN
            and payload.role != "SUPER_ADMIN"
        )

        # You cannot lock the console out of itself: removing the last active
        # Super Admin is unrecoverable without a DB edit.
        if (deactivating or demoting) and user.platform_role == PlatformRole.SUPER_ADMIN:
            if user.id == actor.id and deactivating:
                raise _bad("You cannot deactivate your own account")
            remaining = await db.execute(
                select(func.count())
                .select_from(PlatformUser)
                .where(
                    PlatformUser.platform_role == PlatformRole.SUPER_ADMIN,
                    PlatformUser.is_active.is_(True),
                    PlatformUser.id != user.id,
                )
            )
            if int(remaining.scalar() or 0) == 0:
                raise _bad("This is the last active Super Admin — promote another first")

        before = {
            "name": user.name,
            "role": user.platform_role.value,
            "is_active": user.is_active,
        }
        if payload.name is not None:
            user.name = payload.name.strip()
        if payload.role is not None:
            user.platform_role = PlatformRole(payload.role)
        if payload.is_active is not None:
            user.is_active = payload.is_active

        AuditService.record(
            db,
            actor=actor,
            actor_role=actor.platform_role.value,
            action="PLATFORM_USER_UPDATED",
            entity="platform_user",
            entity_id=user.id,
            old_value=before,
            new_value={
                "name": user.name,
                "email": user.email,
                "role": user.platform_role.value,
                "is_active": user.is_active,
            },
            request=request,
        )
        await db.flush()
        await db.commit()
        return _user_row(user)

    # ══ C-SA-01 · Dashboard ══════════════════════════════════════════════════

    @staticmethod
    async def stats(db: AsyncSession) -> PlatformStats:
        res = await db.execute(select(Tenant))
        tenants = list(res.scalars().all())
        rows = await PlatformAdminService._rows(db, tenants)

        active = [r for r in rows if r.is_active and r.status == "ACTIVE"]
        trial = [r for r in rows if r.is_active and r.status == "TRIAL"]
        suspended = [r for r in rows if not r.is_active]

        # MRR from live subscriptions, normalised to a monthly figure so a
        # yearly plan does not inflate the number twelvefold.
        sub_res = await db.execute(
            select(Subscription).where(Subscription.status.in_(("ACTIVE", "PAST_DUE")))
        )
        mrr = 0.0
        for sub in sub_res.scalars().all():
            amount = float(sub.amount)
            mrr += amount / 12 if _cycle(sub.starts_at, sub.ends_at) == "YEARLY" else amount

        tickets_res = await db.execute(
            select(SupportTicket.priority, func.count())
            .where(SupportTicket.status.in_(("OPEN", "IN_PROGRESS")))
            .group_by(SupportTicket.priority)
        )
        by_priority = {p: int(c) for p, c in tickets_res.all()}

        plan_res = await db.execute(select(Plan))
        plans = {p.id: p for p in plan_res.scalars().all()}
        mix: dict[str, int] = {}
        for t in tenants:
            name = plans[t.plan_id].name if t.plan_id in plans else "Unassigned"
            mix[name] = mix.get(name, 0) + 1

        return PlatformStats(
            total_institutions=len(rows),
            active_institutions=len(active),
            trial_institutions=len(trial),
            suspended_institutions=len(suspended),
            total_students=sum(r.student_count for r in rows),
            total_teachers=sum(r.teacher_count for r in rows),
            mrr=round(mrr, 2),
            open_tickets=sum(by_priority.values()),
            critical_tickets=by_priority.get("URGENT", 0) + by_priority.get("HIGH", 0),
            revenue_trend=await PlatformAdminService._revenue_trend(db),
            plan_mix=[
                PlanMixPoint(plan=name, count=count)
                for name, count in sorted(mix.items(), key=lambda kv: -kv[1])
            ],
            recent_tenants=sorted(rows, key=lambda r: r.created_at, reverse=True)[:5],
        )

    @staticmethod
    async def _revenue_trend(db: AsyncSession, months: int = 6) -> list[TrendPoint]:
        """Paid invoice totals per month, oldest first."""
        res = await db.execute(
            select(PlatformInvoice.issued_at, PlatformInvoice.amount_paid).where(
                PlatformInvoice.status == "PAID"
            )
        )
        buckets: dict[str, float] = {}
        for issued_at, amount in res.all():
            if issued_at is None:
                continue
            buckets[issued_at.strftime("%Y-%m")] = buckets.get(
                issued_at.strftime("%Y-%m"), 0.0
            ) + float(amount or 0)

        today = date.today()
        points: list[TrendPoint] = []
        for i in range(months - 1, -1, -1):
            year = today.year + (today.month - 1 - i) // 12
            month = (today.month - 1 - i) % 12 + 1
            key = f"{year:04d}-{month:02d}"
            points.append(
                TrendPoint(
                    label=date(year, month, 1).strftime("%b"),
                    amount=round(buckets.get(key, 0.0), 2),
                )
            )
        return points

    # ══ C-SA-08 · Settings ═══════════════════════════════════════════════════

    @staticmethod
    async def _all_settings(db: AsyncSession) -> dict[str, str]:
        """Stored values layered over the code defaults."""
        res = await db.execute(select(PlatformSetting))
        stored = {s.key: s.value for s in res.scalars().all()}
        return {**PLATFORM_SETTING_DEFAULTS, **stored}

    @staticmethod
    async def _setting(db: AsyncSession, key: str) -> str:
        return (await PlatformAdminService._all_settings(db)).get(
            key, PLATFORM_SETTING_DEFAULTS.get(key, "")
        )

    @staticmethod
    async def _trial_days(db: AsyncSession) -> int:
        raw = await PlatformAdminService._setting(db, "trial_length_days")
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return settings.TRIAL_DAYS

    @staticmethod
    async def get_settings_page(db: AsyncSession) -> PlatformSettingsOut:
        values = await PlatformAdminService._all_settings(db)
        mod_res = await db.execute(select(Module).order_by(Module.sort_order))
        modules = [
            ModuleFlag(key=m.key, label=m.name, core=m.is_core)
            for m in mod_res.scalars().all()
        ]
        return PlatformSettingsOut(
            product_name=values["product_name"],
            support_email=values["support_email"],
            root_domain=settings.PUBLIC_ROOT_DOMAIN or "shikshasync.me",
            allowed_modules=modules,
            default_timezone=values["default_timezone"],
            default_currency=values["default_currency"],
            trial_length_days=await PlatformAdminService._trial_days(db),
            brand_primary=values["brand_primary"],
            brand_accent=values["brand_accent"],
        )

    @staticmethod
    async def update_settings(
        db: AsyncSession,
        payload: PlatformSettingsUpdate,
        actor: PlatformUser,
        request: Request | None = None,
    ) -> PlatformSettingsOut:
        incoming = payload.model_dump(exclude_none=True)
        if not incoming:
            return await PlatformAdminService.get_settings_page(db)

        before = await PlatformAdminService._all_settings(db)
        res = await db.execute(select(PlatformSetting))
        existing = {s.key: s for s in res.scalars().all()}

        for key, value in incoming.items():
            text = str(value)
            if key in PLATFORM_SETTING_INT_KEYS:
                text = str(int(value))
            row = existing.get(key)
            if row is None:
                db.add(PlatformSetting(id=uuid.uuid4(), key=key, value=text))
            else:
                row.value = text

        AuditService.record(
            db,
            actor=actor,
            actor_role=actor.platform_role.value,
            action="PLATFORM_SETTINGS_UPDATED",
            entity="platform_settings",
            old_value={k: before.get(k) for k in incoming},
            new_value={k: str(v) for k, v in incoming.items()},
            request=request,
        )
        await db.flush()
        await db.commit()
        return await PlatformAdminService.get_settings_page(db)

    # ══ Subscriptions (shared with Sales C-SL-04) ════════════════════════════

    @staticmethod
    async def list_subscriptions(
        db: AsyncSession, *, status_filter: str | None = None
    ) -> list[SubscriptionRow]:
        stmt = select(Subscription).order_by(Subscription.created_at.desc())
        if status_filter and status_filter != "ALL":
            stmt = stmt.where(Subscription.status == status_filter)
        res = await db.execute(stmt)
        subs = list(res.scalars().all())
        if not subs:
            return []

        t_res = await db.execute(
            select(Tenant.id, Tenant.name).where(
                Tenant.id.in_({s.tenant_id for s in subs})
            )
        )
        tenant_names = {i: n for i, n in t_res.all()}
        p_res = await db.execute(select(Plan.id, Plan.name))
        plan_names = {i: n for i, n in p_res.all()}

        return [
            SubscriptionRow(
                id=s.id,
                tenant_id=s.tenant_id,
                tenant_name=tenant_names.get(s.tenant_id, "—"),
                plan_name=plan_names.get(s.plan_id, "—"),
                status=s.status,  # type: ignore[arg-type]
                starts_at=s.starts_at,
                ends_at=s.ends_at,
                amount=float(s.amount),
                currency=s.currency,
                payment_reference=s.payment_reference,
                cycle=_cycle(s.starts_at, s.ends_at),
            )
            for s in subs
        ]


# ── Row builders (module-level: pure, no DB) ─────────────────────────────────

def _cycle(starts_at: datetime, ends_at: datetime | None) -> str:
    """
    Billing cycle derived from the period length, never stored.

    types/platform.ts: "The cycle is therefore the *length of the period*,
    derived rather than stored, so it can never disagree with the dates it is
    supposed to describe."
    """
    if ends_at is None or starts_at is None:
        return "MONTHLY"
    return "YEARLY" if (ends_at - starts_at).days > 45 else "MONTHLY"


def _plan_row(plan: Plan, tenant_count: int) -> PlanRow:
    return PlanRow(
        id=plan.id,
        name=plan.name,
        slug=plan.slug,
        max_students=plan.max_students,
        max_teachers=plan.max_teachers,
        max_storage_gb=plan.max_storage_gb,
        price_monthly=float(plan.price_monthly),
        price_yearly=float(plan.price_yearly),
        currency=plan.currency,
        allowed_modules=list(plan.allowed_modules or []),
        is_active=plan.is_active,
        tenant_count=tenant_count,
    )


def _user_row(user: PlatformUser) -> PlatformUserRow:
    return PlatformUserRow(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.platform_role.value,  # type: ignore[arg-type]
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )
