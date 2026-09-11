"""
Pydantic Schemas — public signup / self-service checkout

Covers the public catalogue (plans + modules), subdomain availability,
price quotes, order creation and the payment → provisioning result.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import APIResponse, Wire

# ── Catalogue ─────────────────────────────────────────────────────────────────

class ModuleInfo(BaseModel):
    """One module in the a-la-carte catalogue."""

    key: str
    name: str
    description: str | None = None
    is_core: bool
    price_monthly: Decimal


class PlanInfo(BaseModel):
    """One sellable plan."""

    id: uuid.UUID
    name: str
    slug: str
    max_students: int
    max_teachers: int
    max_storage_gb: int
    price_monthly: Decimal
    price_yearly: Decimal
    currency: str
    allowed_modules: list[str]
    is_active: bool


class CatalogResponse(BaseModel):
    """Everything the pricing page and the checkout wizard need, one call."""

    plans: list[PlanInfo]
    modules: list[ModuleInfo]


# ── Subdomain ─────────────────────────────────────────────────────────────────

class SubdomainCheckResponse(BaseModel):
    """Availability verdict plus suggestions for the URL step."""

    slug: str
    available: bool
    url: str
    suggestions: list[str]


# ── Price quote ───────────────────────────────────────────────────────────────

class PriceLine(BaseModel):
    label: str
    amount: Decimal


class CouponResult(BaseModel):
    code: str
    discount_type: str
    value: Decimal
    message: str


class PriceQuoteResponse(BaseModel):
    """Server-computed quote — the live price source of truth."""

    mode: str  # PURCHASE | TRIAL
    plan_slug: str
    billing_cycle: str
    module_keys: list[str]
    currency: str
    lines: list[PriceLine]
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    coupon: CouponResult | None = None


# ── Platform account / owner ───────────────────────────────────────────────


class OwnerDraft(Wire):
    """Platform account owner captured before institution checkout.

    This is the shikshasync.me account (AWS/Shopify style). One owner can later
    create and manage many institutions from the platform dashboard.
    """

    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr


class PlatformAccountCreateRequest(BaseModel):
    """Body for POST /public/platform/accounts."""

    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class PlatformAccountResponse(BaseModel):
    """Owner platform account created from public signup."""

    id: uuid.UUID
    name: str
    email: str
    role: str
    email_verified: bool
    verification_sent_to: str


class VerifyEmailRequest(BaseModel):
    """Body for POST /public/platform/accounts/verify-email."""

    token: str = Field(..., min_length=1)


class VerifyEmailResponse(BaseModel):
    email: str
    verified: bool


# ── Order ─────────────────────────────────────────────────────────────────────

class InstitutionDraft(Wire):
    """Institution + admin identity captured during registration."""

    name: str = Field(..., min_length=2, max_length=255)
    type: str = Field(..., pattern="^(SCHOOL|COLLEGE)$")
    email: EmailStr
    phone: str | None = Field(default=None, max_length=20)
    country: str = Field(default="India", max_length=100)
    state: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    address: str | None = None


class OrderCreateRequest(Wire):
    """Body for POST /public/orders."""

    mode: str = Field(..., pattern="^(PURCHASE|TRIAL)$")
    plan_slug: str = Field(..., min_length=1, max_length=50)
    module_keys: list[str] = Field(default_factory=list)
    billing_cycle: str = Field(default="MONTHLY", pattern="^(MONTHLY|YEARLY)$")
    coupon_code: str | None = Field(default=None, max_length=50)
    owner: OwnerDraft | None = None
    institution: InstitutionDraft
    url_slug: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=128)
    # Set when the checkout is started from inside an owner's platform
    # dashboard; provisioning then stamps tenants.owner_id so the institution
    # appears under "My Institutions". Anonymous public checkout leaves it NULL.
    owner_id: uuid.UUID | None = None


class OrderResponse(BaseModel):
    """The checkout draft once created; `pay` consumes it."""

    id: uuid.UUID
    mode: str
    plan_slug: str
    module_keys: list[str]
    billing_cycle: str
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    currency: str
    coupon_code: str | None = None
    status: str
    institution_name: str
    url_slug: str
    login_url: str
    created_at: datetime


# ── Payment + provisioning ────────────────────────────────────────────────────

class OrderPayRequest(Wire):
    """Body for POST /public/orders/{id}/pay.

    `method` is the payment channel: UPI, CARD, DEBIT_CARD, NET_BANKING,
    WALLET, INVOICE (enterprise) or TRIAL (free-trial start — no charge).
    """

    method: str = Field(..., pattern="^(UPI|CARD|DEBIT_CARD|NET_BANKING|WALLET|INVOICE|TRIAL)$")
    gateway_ref: str | None = Field(default=None, max_length=255)


class ProvisionedTenant(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    login_url: str


class ProvisionedSubscription(BaseModel):
    status: str
    amount: Decimal
    currency: str
    starts_at: datetime
    ends_at: datetime | None = None
    trial_ends_at: datetime | None = None


class ProvisionedInvoice(BaseModel):
    number: str
    status: str
    issued_at: str
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    amount_paid: Decimal


class WelcomeEmailResult(BaseModel):
    to: str
    subject: str
    status: str  # QUEUED


class ProvisionResult(BaseModel):
    """Step 7 output — what the automatic provisioning created."""

    order_id: uuid.UUID
    mode: str
    tenant: ProvisionedTenant
    subscription: ProvisionedSubscription
    invoice: ProvisionedInvoice | None = None
    owner_email: str
    platform_dashboard_url: str
    admin_email: str
    enabled_modules: list[str]
    welcome_email: WelcomeEmailResult
    steps: list[str]  # the provisioning checklist, in order


APIResponsePlatformAccount = APIResponse[PlatformAccountResponse]
APIResponseVerifyEmail = APIResponse[VerifyEmailResponse]
APIResponseCatalog = APIResponse[CatalogResponse]
APIResponseSubdomain = APIResponse[SubdomainCheckResponse]
APIResponseQuote = APIResponse[PriceQuoteResponse]
APIResponseOrder = APIResponse[OrderResponse]
APIResponseProvision = APIResponse[ProvisionResult]
