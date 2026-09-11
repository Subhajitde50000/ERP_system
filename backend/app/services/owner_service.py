"""
Services — Platform Owner (customer account)

The AWS / Shopify / Zoho account-holder logic: signup + email verification,
login (gated on verification), the platform dashboard data (My Institutions,
Subscriptions, Invoices, Payments, Billing summary), Support Tickets and
Profile management.

An owner owns many institutions (`tenants.owner_id`); everything here is
scoped to the authenticated owner and never leaks another owner's data.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.billing import (
    Order,
    PlatformInvoice,
    PlatformPayment,
    Subscription,
)
from app.models.catalog import Plan
from app.models.owner_session import OwnerSession
from app.models.platform_owner import PlatformOwner
from app.models.support_ticket import (
    SupportTicket,
    SupportTicketMessage,
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_PRIORITY_DEFAULT,
    TICKET_STATUSES,
)
from app.models.tenant import Tenant
from app.schemas.owner import (
    AccessTokenResponse,
    BillingSummaryResponse,
    ChangePasswordRequest,
    OwnerInfo,
    OwnerInstitution,
    OwnerInstitutionsResponse,
    OwnerInvoice,
    OwnerLoginResponse,
    OwnerPayment,
    OwnerSignupResponse,
    OwnerSubscription,
    SupportTicketOut,
    TicketCreateRequest,
    TicketMessageOut,
    TokenResponse,
)
from app.services.jwt_service import create_owner_access_token
from app.services.mailer import queue_email
from app.utils.security import (
    generate_secure_token,
    hash_password,
    hash_token,
    verify_password,
)

settings = get_settings()

# A bcrypt hash that is syntactically valid but matches nothing, so the
# password check always runs in constant time even when no account exists
# (prevents user-enumeration timing).  Generated once with hash_password(...).
_DUMMY_HASH = "$2b$12$CZmb7IjM5B19jizvARYHEuhnP.d0Wv4hMRaqVSwevmCb7ovXPXNWy"


def _extract_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _login_url(slug: str) -> str:
    domain = settings.PUBLIC_ROOT_DOMAIN or "shikshasync.me"
    scheme = "http" if "localhost" in domain else "https"
    return f"{scheme}://{slug}.{domain}/login"


class OwnerService:
    # ── Signup & email verification ──────────────────────────────────────────

    @staticmethod
    async def signup(
        db: AsyncSession, name: str, email: str, password: str
    ) -> OwnerSignupResponse:
        email_lc = email.strip().lower()
        existing = await db.execute(
            select(PlatformOwner.id).where(PlatformOwner.email == email_lc)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists. Try signing in.",
            )

        raw_token = generate_secure_token(32)
        owner = PlatformOwner(
            id=uuid.uuid4(),
            name=name.strip(),
            email=email_lc,
            password_hash=hash_password(password),
            is_email_verified=False,
            email_verification_token=hash_token(raw_token),
            email_verification_expires=datetime.now(timezone.utc)
            + timedelta(hours=24),
        )
        db.add(owner)
        await db.flush()

        verify_url = (
            f"https://{settings.PUBLIC_ROOT_DOMAIN or 'shikshasync.me'}/verify-email"
            f"?token={raw_token}"
        )
        # Queued in the outbox inside this transaction, then delivered by the
        # active provider (ZeptoMail in production; see mailer/registry.py).
        # In dev/no-mailer mode the raw token is also returned to the caller so
        # the flow can be completed end-to-end.
        queue_email(
            db,
            "owner.verify_email",
            to=email_lc,
            context={"name": owner.name, "verify_url": verify_url},
        )
        await db.flush()

        return OwnerSignupResponse(
            id=owner.id,
            name=owner.name,
            email=owner.email,
            is_email_verified=False,
            # Included so a no-mailer environment can complete verification;
            # never surface this to end users in production.
            verification_token=raw_token if settings.APP_DEBUG else None,
        )

    @staticmethod
    async def verify_email(db: AsyncSession, token: str) -> OwnerInfo:
        token_hash = hash_token(token)
        now = datetime.now(timezone.utc)
        res = await db.execute(
            select(PlatformOwner).where(
                PlatformOwner.email_verification_token == token_hash,
                PlatformOwner.email_verification_expires > now,
            )
        )
        owner = res.scalar_one_or_none()
        if owner is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification link is invalid or has expired",
            )
        owner.is_email_verified = True
        owner.email_verification_token = None
        owner.email_verification_expires = None
        await db.flush()
        return OwnerService._info(owner)

    @staticmethod
    async def resend_verification(db: AsyncSession, email: str) -> None:
        res = await db.execute(
            select(PlatformOwner).where(
                PlatformOwner.email == email.strip().lower()
            )
        )
        owner = res.scalar_one_or_none()
        # Silent success — never reveals whether an account exists.
        if owner is None or owner.is_email_verified:
            return
        raw_token = generate_secure_token(32)
        owner.email_verification_token = hash_token(raw_token)
        owner.email_verification_expires = datetime.now(timezone.utc) + timedelta(
            hours=24
        )
        verify_url = (
            f"https://{settings.PUBLIC_ROOT_DOMAIN or 'shikshasync.me'}/verify-email"
            f"?token={raw_token}"
        )
        queue_email(
            db,
            "owner.verify_email",
            to=owner.email,
            context={"name": owner.name, "verify_url": verify_url},
        )
        await db.flush()

    # ── Auth ──────────────────────────────────────────────────────────────────

    @staticmethod
    async def login(
        db: AsyncSession, email: str, password: str, request: Request
    ) -> OwnerLoginResponse:
        res = await db.execute(
            select(PlatformOwner).where(
                PlatformOwner.email == email.strip().lower()
            )
        )
        owner = res.scalar_one_or_none()

        stored = owner.password_hash if owner else _DUMMY_HASH
        ok = verify_password(password, stored)
        if owner is None or not ok:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if not owner.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive. Contact support.",
            )
        if not owner.is_email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please verify your email before signing in.",
            )

        owner.last_login_at = datetime.now(timezone.utc)
        access = create_owner_access_token(owner.id)
        refresh = generate_secure_token()

        db.add(
            OwnerSession(
                id=uuid.uuid4(),
                owner_id=owner.id,
                refresh_token_hash=hash_token(refresh),
                device_info=request.headers.get("User-Agent"),
                ip_address=_extract_ip(request),
                expires_at=datetime.now(timezone.utc)
                + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            )
        )
        await db.flush()

        return OwnerLoginResponse(
            tokens=TokenResponse(
                access_token=access,
                refresh_token=refresh,
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            ),
            owner=OwnerService._info(owner),
        )

    @staticmethod
    async def logout(db: AsyncSession, refresh_token: str) -> None:
        th = hash_token(refresh_token)
        await db.execute(
            OwnerSession.__table__.update()
            .where(OwnerSession.refresh_token_hash == th)
            .values(revoked_at=datetime.now(timezone.utc))
        )

    @staticmethod
    async def refresh(db: AsyncSession, refresh_token: str) -> AccessTokenResponse:
        th = hash_token(refresh_token)
        res = await db.execute(
            select(OwnerSession, PlatformOwner)
            .join(PlatformOwner, OwnerSession.owner_id == PlatformOwner.id)
            .where(OwnerSession.refresh_token_hash == th)
        )
        row = res.first()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
        session, owner = row
        if not session.is_valid or not owner.is_active or not owner.is_email_verified:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or revoked",
            )
        return AccessTokenResponse(
            access_token=create_owner_access_token(owner.id),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    # ── Profile ───────────────────────────────────────────────────────────────

    @staticmethod
    def _info(owner: PlatformOwner) -> OwnerInfo:
        return OwnerInfo(
            id=owner.id,
            name=owner.name,
            email=owner.email,
            is_email_verified=owner.is_email_verified,
            is_active=owner.is_active,
            last_login_at=owner.last_login_at,
            created_at=owner.created_at,
        )

    @staticmethod
    async def update_profile(
        db: AsyncSession, owner: PlatformOwner, name: str
    ) -> OwnerInfo:
        owner.name = name.strip()
        await db.flush()
        return OwnerService._info(owner)

    @staticmethod
    async def change_password(
        db: AsyncSession, owner: PlatformOwner, payload: ChangePasswordRequest
    ) -> None:
        if not verify_password(payload.current_password, owner.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )
        owner.password_hash = hash_password(payload.new_password)
        await db.flush()
        # Invalidate every other session — a password change is a security event.
        await db.execute(
            OwnerSession.__table__.update()
            .where(OwnerSession.owner_id == owner.id)
            .values(revoked_at=datetime.now(timezone.utc))
        )

    @staticmethod
    async def forgot_password(db: AsyncSession, email: str) -> None:
        res = await db.execute(
            select(PlatformOwner).where(
                PlatformOwner.email == email.strip().lower(),
                PlatformOwner.is_active == True,  # noqa: E712
            )
        )
        owner = res.scalar_one_or_none()
        if owner is None:
            return  # Silent success — no account enumeration.
        raw = generate_secure_token(32)
        owner.password_reset_token = hash_token(raw)
        owner.password_reset_expires = datetime.now(timezone.utc) + timedelta(
            minutes=30
        )
        reset_url = (
            f"https://{settings.PUBLIC_ROOT_DOMAIN or 'shikshasync.me'}/reset-password"
            f"?token={raw}"
        )
        queue_email(
            db,
            "owner.password_reset",
            to=owner.email,
            context={
                "name": owner.name,
                "reset_url": reset_url,
                "expires_minutes": 30,
            },
        )
        await db.flush()

    @staticmethod
    async def reset_password(
        db: AsyncSession, token: str, new_password: str
    ) -> None:
        th = hash_token(token)
        now = datetime.now(timezone.utc)
        res = await db.execute(
            select(PlatformOwner).where(
                PlatformOwner.password_reset_token == th,
                PlatformOwner.password_reset_expires > now,
            )
        )
        owner = res.scalar_one_or_none()
        if owner is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reset link is invalid or has expired",
            )
        owner.password_hash = hash_password(new_password)
        owner.password_reset_token = None
        owner.password_reset_expires = None
        await db.flush()
        await db.execute(
            OwnerSession.__table__.update()
            .where(OwnerSession.owner_id == owner.id)
            .values(revoked_at=now)
        )

    # ── Dashboard: institutions ───────────────────────────────────────────────

    @staticmethod
    async def list_institutions(
        db: AsyncSession, owner: PlatformOwner
    ) -> OwnerInstitutionsResponse:
        t_res = await db.execute(
            select(Tenant)
            .where(Tenant.owner_id == owner.id)
            .order_by(Tenant.created_at.desc())
        )
        tenants = list(t_res.scalars().all())
        if not tenants:
            return OwnerInstitutionsResponse(institutions=[])

        tenant_ids = [t.id for t in tenants]
        plan_ids = {t.plan_id for t in tenants if t.plan_id is not None}

        plans: dict[Any, str] = {}
        if plan_ids:
            p_res = await db.execute(select(Plan).where(Plan.id.in_(plan_ids)))
            plans = {p.id: p.name for p in p_res.scalars().all()}

        # Latest subscription per tenant (created_at desc, take first per tenant).
        sub_res = await db.execute(
            select(Subscription)
            .where(Subscription.tenant_id.in_(tenant_ids))
            .order_by(Subscription.tenant_id, Subscription.created_at.desc())
        )
        latest_sub: dict[Any, Subscription] = {}
        for sub in sub_res.scalars().all():
            latest_sub.setdefault(sub.tenant_id, sub)

        return OwnerInstitutionsResponse(
            institutions=[
                OwnerInstitution(
                    id=t.id,
                    name=t.name,
                    slug=t.slug,
                    type=t.type.value,
                    plan_name=plans.get(t.plan_id),
                    subscription_status=latest_sub[t.id].status
                    if t.id in latest_sub
                    else None,
                    is_active=t.is_active,
                    trial_ends_at=t.trial_ends_at,
                    login_url=_login_url(t.slug),
                    created_at=t.created_at,
                )
                for t in tenants
            ]
        )

    # ── Dashboard: billing ────────────────────────────────────────────────────

    @staticmethod
    async def _owner_tenant_ids(db: AsyncSession, owner_id: uuid.UUID) -> list[uuid.UUID]:
        res = await db.execute(select(Tenant.id).where(Tenant.owner_id == owner_id))
        return [r for r in res.scalars().all()]

    @staticmethod
    async def billing_summary(
        db: AsyncSession, owner: PlatformOwner
    ) -> BillingSummaryResponse:
        tenant_ids = await OwnerService._owner_tenant_ids(db, owner.id)
        if not tenant_ids:
            return BillingSummaryResponse(
                total_institutions=0,
                active_subscriptions=0,
                trialing=0,
                lifetime_spend=__import__("decimal").Decimal("0"),
                outstanding=__import__("decimal").Decimal("0"),
            )

        # Latest subscription status per tenant.
        sub_res = await db.execute(
            select(Subscription)
            .where(Subscription.tenant_id.in_(tenant_ids))
            .order_by(Subscription.tenant_id, Subscription.created_at.desc())
        )
        latest: dict[Any, str] = {}
        next_renewal: datetime | None = None
        now = datetime.now(timezone.utc)
        for sub in sub_res.scalars().all():
            if sub.tenant_id in latest:
                continue
            latest[sub.tenant_id] = sub.status
            if sub.status == "ACTIVE" and sub.ends_at and sub.ends_at > now:
                if next_renewal is None or sub.ends_at < next_renewal:
                    next_renewal = sub.ends_at

        active = sum(1 for s in latest.values() if s == "ACTIVE")
        trialing = sum(1 for s in latest.values() if s == "TRIAL")

        spend_res = await db.execute(
            select(func.coalesce(func.sum(PlatformPayment.amount), 0))
            .where(
                PlatformPayment.tenant_id.in_(tenant_ids),
                PlatformPayment.status == "SUCCEEDED",
            )
        )
        lifetime_spend = spend_res.scalar() or 0

        out_res = await db.execute(
            select(func.coalesce(
                func.sum(PlatformInvoice.total - PlatformInvoice.amount_paid), 0
            )).where(
                PlatformInvoice.tenant_id.in_(tenant_ids),
                PlatformInvoice.status.in_(["ISSUED", "OVERDUE"]),
            )
        )
        outstanding = out_res.scalar() or 0

        return BillingSummaryResponse(
            total_institutions=len(tenant_ids),
            active_subscriptions=active,
            trialing=trialing,
            next_renewal_at=next_renewal,
            lifetime_spend=lifetime_spend,
            outstanding=outstanding,
        )

    @staticmethod
    async def list_subscriptions(
        db: AsyncSession, owner: PlatformOwner
    ) -> list[OwnerSubscription]:
        tenant_ids = await OwnerService._owner_tenant_ids(db, owner.id)
        if not tenant_ids:
            return []
        rows = await db.execute(
            select(Subscription, Tenant, Plan)
            .join(Tenant, Subscription.tenant_id == Tenant.id)
            .join(Plan, Subscription.plan_id == Plan.id)
            .where(Subscription.tenant_id.in_(tenant_ids))
            .order_by(Subscription.created_at.desc())
        )
        return [
            OwnerSubscription(
                id=sub.id,
                tenant_id=sub.tenant_id,
                tenant_name=tenant.name,
                plan_name=plan.name,
                status=sub.status,
                amount=sub.amount,
                currency=sub.currency,
                starts_at=sub.starts_at,
                ends_at=sub.ends_at,
            )
            for sub, tenant, plan in rows.all()
        ]

    @staticmethod
    async def list_invoices(
        db: AsyncSession, owner: PlatformOwner
    ) -> list[OwnerInvoice]:
        tenant_ids = await OwnerService._owner_tenant_ids(db, owner.id)
        if not tenant_ids:
            return []
        rows = await db.execute(
            select(PlatformInvoice, Tenant)
            .join(Tenant, PlatformInvoice.tenant_id == Tenant.id)
            .where(PlatformInvoice.tenant_id.in_(tenant_ids))
            .order_by(PlatformInvoice.created_at.desc())
        )
        return [
            OwnerInvoice(
                id=inv.id,
                invoice_number=inv.invoice_number,
                tenant_id=inv.tenant_id,
                tenant_name=tenant.name,
                status=inv.status,
                issued_at=datetime.combine(inv.issued_at, datetime.min.time()),
                total=inv.total,
                amount_paid=inv.amount_paid,
                currency=inv.currency,
            )
            for inv, tenant in rows.all()
        ]

    @staticmethod
    async def list_payments(
        db: AsyncSession, owner: PlatformOwner
    ) -> list[OwnerPayment]:
        tenant_ids = await OwnerService._owner_tenant_ids(db, owner.id)
        if not tenant_ids:
            return []
        rows = await db.execute(
            select(PlatformPayment, Tenant)
            .outerjoin(Tenant, PlatformPayment.tenant_id == Tenant.id)
            .where(PlatformPayment.tenant_id.in_(tenant_ids))
            .order_by(PlatformPayment.created_at.desc())
        )
        return [
            OwnerPayment(
                id=pay.id,
                tenant_id=pay.tenant_id,
                tenant_name=tenant.name if tenant else None,
                status=pay.status,
                method=pay.method,
                amount=pay.amount,
                currency=pay.currency,
                gateway=pay.gateway,
                received_at=pay.received_at,
                created_at=pay.created_at,
            )
            for pay, tenant in rows.all()
        ]

    # ── Support tickets ───────────────────────────────────────────────────────

    @staticmethod
    async def list_tickets(
        db: AsyncSession, owner: PlatformOwner
    ) -> list[SupportTicketOut]:
        res = await db.execute(
            select(SupportTicket)
            .where(SupportTicket.owner_id == owner.id)
            .order_by(SupportTicket.created_at.desc())
        )
        tickets = list(res.scalars().all())
        if not tickets:
            return []
        tenant_ids = {t.tenant_id for t in tickets if t.tenant_id}
        names: dict[Any, str] = {}
        if tenant_ids:
            t_res = await db.execute(
                select(Tenant.id, Tenant.name).where(Tenant.id.in_(tenant_ids))
            )
            names = {tid: n for tid, n in t_res.all()}
        return [
            SupportTicketOut(
                id=t.id,
                subject=t.subject,
                category=t.category,
                status=t.status,
                priority=t.priority,
                tenant_id=t.tenant_id,
                tenant_name=names.get(t.tenant_id) if t.tenant_id else None,
                created_at=t.created_at,
                updated_at=t.updated_at,
                messages=[],
            )
            for t in tickets
        ]

    @staticmethod
    async def create_ticket(
        db: AsyncSession, owner: PlatformOwner, payload: TicketCreateRequest
    ) -> SupportTicketOut:
        category = payload.category.upper()
        priority = payload.priority.upper()
        if category not in TICKET_CATEGORIES:
            category = "OTHER"
        if priority not in TICKET_PRIORITIES:
            priority = TICKET_PRIORITY_DEFAULT

        # If a tenant is referenced, it must belong to this owner.
        if payload.tenant_id is not None:
            owned = await db.execute(
                select(Tenant.id).where(
                    Tenant.id == payload.tenant_id,
                    Tenant.owner_id == owner.id,
                )
            )
            if owned.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Institution not found in your account",
                )

        now = datetime.now(timezone.utc)
        ticket = SupportTicket(
            id=uuid.uuid4(),
            owner_id=owner.id,
            tenant_id=payload.tenant_id,
            subject=payload.subject.strip(),
            category=category,
            priority=priority,
            status="OPEN",
            created_at=now,
            updated_at=now,
        )
        db.add(ticket)
        await db.flush()
        db.add(
            SupportTicketMessage(
                id=uuid.uuid4(),
                ticket_id=ticket.id,
                author_role="OWNER",
                author_id=owner.id,
                body=payload.message.strip(),
            )
        )
        await db.flush()
        return await OwnerService._ticket_out(db, ticket)

    @staticmethod
    async def get_ticket(
        db: AsyncSession, owner: PlatformOwner, ticket_id: uuid.UUID
    ) -> SupportTicketOut:
        ticket = await OwnerService._load_owned_ticket(db, owner.id, ticket_id)
        return await OwnerService._ticket_out(db, ticket, with_messages=True)

    @staticmethod
    async def reply_ticket(
        db: AsyncSession,
        owner: PlatformOwner,
        ticket_id: uuid.UUID,
        message: str,
    ) -> SupportTicketOut:
        ticket = await OwnerService._load_owned_ticket(db, owner.id, ticket_id)
        db.add(
            SupportTicketMessage(
                ticket_id=ticket.id,
                author_role="OWNER",
                author_id=owner.id,
                body=message.strip(),
            )
        )
        # A customer reply reopens a resolved/closed ticket.
        if ticket.status in ("RESOLVED", "CLOSED"):
            ticket.status = "IN_PROGRESS"
        await db.flush()
        return await OwnerService._ticket_out(db, ticket, with_messages=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    async def _load_owned_ticket(
        db: AsyncSession, owner_id: uuid.UUID, ticket_id: uuid.UUID
    ) -> SupportTicket:
        res = await db.execute(
            select(SupportTicket).where(
                SupportTicket.id == ticket_id,
                SupportTicket.owner_id == owner_id,
            )
        )
        ticket = res.scalar_one_or_none()
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
            )
        return ticket

    @staticmethod
    async def _ticket_out(
        db: AsyncSession, ticket: SupportTicket, with_messages: bool = False
    ) -> SupportTicketOut:
        tenant_name = None
        if ticket.tenant_id:
            t_res = await db.execute(
                select(Tenant.name).where(Tenant.id == ticket.tenant_id)
            )
            tenant_name = t_res.scalar_one_or_none()
        messages: list[TicketMessageOut] = []
        if with_messages:
            m_res = await db.execute(
                select(SupportTicketMessage)
                .where(
                    SupportTicketMessage.ticket_id == ticket.id,
                    # Internal notes are staff-only (update2.sql §8). Filtered
                    # in the query, not the loop, so a future refactor cannot
                    # drop the guard and leak one to the customer.
                    SupportTicketMessage.is_internal.is_(False),
                )
                .order_by(SupportTicketMessage.created_at.asc())
            )
            messages = [
                TicketMessageOut(
                    id=m.id,
                    author_role=m.author_role,
                    body=m.body,
                    created_at=m.created_at,
                )
                for m in m_res.scalars().all()
            ]
        return SupportTicketOut(
            id=ticket.id,
            subject=ticket.subject,
            category=ticket.category,
            status=ticket.status,
            priority=ticket.priority,
            tenant_id=ticket.tenant_id,
            tenant_name=tenant_name,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            messages=messages,
        )
