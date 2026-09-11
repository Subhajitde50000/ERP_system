"""
ORM Models — platform billing & tenant subscription state

Tables added for the self-service signup / checkout flow (SYSTEM-FLOW §9
"Missing: the billing tables") plus the tenant-side subscription wiring:

  subscriptions          — one row per active/trial subscription period
  tenant_modules         — which module keys are enabled for a tenant
  tenant_settings        — key/value tenant config (onboarding state lives here)
  platform_invoices      — INV-2026-000145-style invoices (gapless per year)
  platform_invoice_lines — line items behind an invoice
  platform_payments      — payment attempts / records (UPI, card, net banking…)
  coupons                — discount codes applied at checkout
  orders                 — the checkout draft that becomes a tenant on payment
  outbox_emails          — transactional emails queued during provisioning
                            (welcome email). A worker would deliver these; in
                            this codebase they are recorded and inspectable.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


# ── Subscription ──────────────────────────────────────────────────────────────

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False
    )
    # TRIAL | ACTIVE | PAST_DUE | CANCELLED (database.sql subscription_status)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="INR"
    )
    payment_reference: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_subscriptions_tenant_id", "tenant_id"),)


# ── Tenant modules ────────────────────────────────────────────────────────────

class TenantModule(Base):
    __tablename__ = "tenant_modules"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "module_key", name="uq_tenant_modules__tenant_id_module_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    module_key: Mapped[str] = mapped_column(String(50), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    enabled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    disabled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


# ── Tenant settings ───────────────────────────────────────────────────────────

class TenantSetting(Base):
    __tablename__ = "tenant_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_tenant_settings__tenant_id_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


# ── Billing: invoices / payments ──────────────────────────────────────────────

class PlatformInvoice(Base):
    __tablename__ = "platform_invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # e.g. INV-2026-000145 — gapless per financial year (SYSTEM-FLOW §9)
    invoice_number: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True
    )
    # DRAFT | ISSUED | PAID | OVERDUE | VOID | REFUNDED
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    issued_at: Mapped[date] = mapped_column(Date, nullable=False)
    due_at: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="INR"
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    place_of_supply: Mapped[str | None] = mapped_column(String(2), nullable=True)
    pdf_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_platform_invoices_tenant_id", "tenant_id"),)


class PlatformInvoiceLine(Base):
    __tablename__ = "platform_invoice_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    hsn_sac: Mapped[str | None] = mapped_column(String(10), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("1")
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)


class PlatformPayment(Base):
    __tablename__ = "platform_payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # PENDING | SUCCEEDED | FAILED | REFUNDED
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # UPI | CARD | DEBIT_CARD | NET_BANKING | WALLET | INVOICE | BANK_TRANSFER
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="INR"
    )
    gateway: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gateway_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Replay-attack guard: a (gateway, gateway_ref) pair must be globally
        # unique so a webhook delivered twice cannot create a duplicate payment.
        # Mirrors CONSTRAINT uq_platform_payments_gateway_ref in database.sql.
        # NULL gateway_ref rows (offline / mock payments) are excluded by
        # PostgreSQL's NULL-distinct behaviour — two NULLs do not collide.
        UniqueConstraint(
            "gateway", "gateway_ref",
            name="uq_platform_payments_gateway_ref",
        ),
        Index("idx_platform_payments_tenant_id", "tenant_id"),
    )


# ── Coupons ───────────────────────────────────────────────────────────────────

class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    # PERCENT | FIXED
    discount_type: Mapped[str] = mapped_column(String(10), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="INR"
    )
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


# ── Checkout orders ───────────────────────────────────────────────────────────

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # PURCHASE | TRIAL
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    plan_slug: Mapped[str] = mapped_column(String(50), nullable=False)
    module_keys: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), nullable=False, default=list
    )
    # MONTHLY | YEARLY
    billing_cycle: Mapped[str] = mapped_column(
        String(10), nullable=False, default="MONTHLY"
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="INR"
    )
    coupon_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    institution_name: Mapped[str] = mapped_column(String(255), nullable=False)
    institution_type: Mapped[str] = mapped_column(String(20), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_platform_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="India")
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    # The owner who initiated this checkout, when it was started from inside
    # the platform dashboard (the anonymous public checkout leaves it NULL).
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # PENDING | PAID | TRIAL_STARTED | FAILED | CANCELLED
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )
    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gateway_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("idx_orders_status_created_at", "status", "created_at"),
        Index("idx_orders_contact_email", "contact_email"),
        Index("idx_orders_owner_platform_user_id", "owner_platform_user_id"),
    )


# ── Outbox (transactional email) ──────────────────────────────────────────────

class OutboxEmail(Base):
    __tablename__ = "outbox_emails"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event: Mapped[str] = mapped_column(String(50), nullable=False)
    to_address: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # QUEUED | SENT | FAILED
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="QUEUED"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_outbox_emails_status", "status"),)
