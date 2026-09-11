"""
Routers — Public Signup & Self-Service Checkout

Endpoints (all anonymous, rate-limited):
  GET  /api/v1/public/catalog                plans + modules (pricing page)
  GET  /api/v1/public/subdomains/check       availability + suggestions
  POST /api/v1/public/quote                  live price calculation
  POST /api/v1/public/orders                 create the checkout order
  POST /api/v1/public/orders/{id}/pay        payment + automatic provisioning
  GET  /api/v1/public/orders/{id}            success-page summary
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.common import APIResponse
from app.schemas.signup import (
    APIResponseCatalog,
    APIResponsePlatformAccount,
    APIResponseOrder,
    APIResponseProvision,
    APIResponseQuote,
    APIResponseSubdomain,
    APIResponseVerifyEmail,
    OrderCreateRequest,
    PlatformAccountCreateRequest,
    OrderPayRequest,
    ProvisionResult,
    VerifyEmailRequest,
)
from app.services.signup_service import SignupService

router = APIRouter(prefix="/public", tags=["Public Signup"])
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/platform/accounts",
    response_model=APIResponsePlatformAccount,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/hour")
async def create_platform_account(
    request: Request,
    payload: PlatformAccountCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create the owner's shikshasync.me platform account and send verification.

    This is the AWS/Shopify-style account: the owner signs in once at
    shikshasync.me, then creates and manages one or many institutions from the
    platform dashboard.
    """
    data = await SignupService.create_platform_account(db, payload)
    return APIResponse(
        success=True,
        data=data,
        message="Platform account created — verify your email",
    )


@router.post(
    "/platform/accounts/verify-email",
    response_model=APIResponseVerifyEmail,
)
@limiter.limit("20/hour")
async def verify_platform_account(
    request: Request,
    payload: VerifyEmailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Verify an owner email before dashboard access."""
    data = await SignupService.verify_platform_account(db, payload.token)
    return APIResponse(success=True, data=data, message="Email verified")


@router.get("/tenants/by-slug/{slug}", response_model=APIResponse)
@limiter.limit("120/minute")
async def get_tenant_by_slug(
    slug: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Public tenant lookup — used by the login page to render the right
    institution badge for <tenant>.shikshasync.me without any credentials."""
    from sqlalchemy import select

    from app.models.tenant import Tenant

    res = await db.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = res.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Institution '{slug}' not found",
        )
    return APIResponse(
        success=True,
        data={
            "name": tenant.name,
            "type": tenant.type.value,
            "logo_url": tenant.logo_url,
            "timezone": tenant.timezone,
        },
        message="Tenant found",
    )


@router.get("/catalog", response_model=APIResponseCatalog)
@limiter.limit("60/minute")
async def get_catalog(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Plans + modules for the pricing page and the checkout wizard."""
    data = await SignupService.catalog(db)
    return APIResponse(success=True, data=data, message="Catalogue loaded")


@router.get("/subdomains/check", response_model=APIResponseSubdomain)
@limiter.limit("60/minute")
async def check_subdomain(
    slug: Annotated[str, Query(min_length=1, max_length=100)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Availability verdict + suggestions for the URL step."""
    data = await SignupService.check_subdomain(db, slug)
    return APIResponse(success=True, data=data, message="Subdomain checked")


@router.api_route("/quote", methods=["GET", "POST"], response_model=APIResponseQuote)
@limiter.limit("60/minute")
async def price_quote(
    request: Request,
    mode: Annotated[str, Query(pattern="^(PURCHASE|TRIAL)$")] = "PURCHASE",
    plan: Annotated[str, Query(min_length=1)] = "starter",
    modules: Annotated[str, Query(min_length=0)] = "",
    cycle: Annotated[str, Query(pattern="^(MONTHLY|YEARLY)$")] = "MONTHLY",
    coupon: Annotated[str | None, Query(max_length=50)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,  # type: ignore[assignment]
):
    """Live price calculation — server is the source of truth."""
    keys = [k for k in (modules or "").split(",") if k]
    data = await SignupService.quote(db, mode, plan, keys, cycle, coupon)
    return APIResponse(success=True, data=data, message="Price calculated")


@router.post(
    "/orders",
    response_model=APIResponseOrder,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/hour")
async def create_order(
    request: Request,
    payload: OrderCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create the checkout draft — subdomain + price are validated first."""
    data = await SignupService.create_order(db, payload)
    return APIResponse(
        success=True, data=data, message="Order created — proceed to payment"
    )


@router.post("/orders/{order_id}/pay", response_model=APIResponseProvision)
@limiter.limit("10/hour")
async def pay_order(
    order_id: uuid.UUID,
    request: Request,
    payload: OrderPayRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Pay and provision.

    Marks the payment, then runs the Step-7 pipeline (tenant → subscription
    → invoice → admin → roles → modules → settings → academic year →
    welcome email) inside a single transaction.
    """
    from app.models.billing import Order

    result: ProvisionResult = await SignupService.provision_with_payment(
        db, order_id, payload
    )
    return APIResponse(
        success=True, data=result, message="Payment received — institution provisioned"
    )


@router.get("/orders/{order_id}", response_model=APIResponseProvision)
@limiter.limit("30/minute")
async def get_order(
    order_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Success-page payload (idempotent — safe to re-fetch after redirect).
    Read-only: returns the provisioned result without re-running the pipeline."""
    result: ProvisionResult = await SignupService.result(db, order_id)
    return APIResponse(success=True, data=result, message="Order status")
