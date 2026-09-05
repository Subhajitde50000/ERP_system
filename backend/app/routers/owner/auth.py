"""
Routers — Owner auth (signup, email verification, login, refresh, logout).

These are the xyz.com "Platform Login" door described in the system flow:
sign up (Name, Email, Password) → verify email → platform dashboard.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies.auth import get_current_platform_owner
from app.models.platform_owner import PlatformOwner
from app.schemas.common import APIResponse
from app.schemas.owner import (
    APIResponseAccessToken,
    APIResponseOwner,
    APIResponseOwnerLogin,
    APIResponseOwnerSignup,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LogoutRequest,
    OwnerLoginRequest,
    OwnerSignupRequest,
    RefreshRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from app.services.owner_service import OwnerService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
settings = get_settings()



@router.post(
    "/signup",
    response_model=APIResponseOwnerSignup,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/hour")
async def owner_signup(
    payload: OwnerSignupRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a platform owner account. Email verification is required to log in."""
    data = await OwnerService.signup(db, payload.name, payload.email, payload.password)
    return APIResponse(
        success=True, data=data, message="Account created — check your email to verify"
    )


@router.post("/verify-email", response_model=APIResponseOwner)
@limiter.limit("30/hour")
async def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Confirm an email with the one-time verification token."""
    data = await OwnerService.verify_email(db, payload.token)
    return APIResponse(success=True, data=data, message="Email verified — you can sign in")


@router.post("/resend-verification", response_model=APIResponse[None])
@limiter.limit("5/hour")
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Re-send the verification link. Always succeeds (no account enumeration)."""
    await OwnerService.resend_verification(db, payload.email)
    return APIResponse(success=True, data=None, message="If the email exists, a new link was sent")


@router.post("/login", response_model=APIResponseOwnerLogin)
@limiter.limit("10/minute")
async def owner_login(
    payload: OwnerLoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Sign an owner in. Requires a verified email."""
    data = await OwnerService.login(db, payload.email, payload.password, request)
    # Set secure httpOnly cookie
    response.set_cookie(
        key="erp_owner_refresh_token",
        value=data.tokens.refresh_token,
        httponly=True,
        secure=settings.APP_ENV == "production",
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
    )
    return APIResponse(success=True, data=data, message="Login successful")


@router.post("/logout", response_model=APIResponse[None])
async def owner_logout(
    payload: LogoutRequest | None,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[PlatformOwner, Depends(get_current_platform_owner)],
):
    token = (payload.refresh_token if payload and payload.refresh_token else None) or request.cookies.get("erp_owner_refresh_token") or request.cookies.get("refresh_token")
    if token:
        await OwnerService.logout(db, token)
    response.delete_cookie(key="erp_owner_refresh_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    return APIResponse(success=True, data=None, message="Logout successful")


@router.post("/refresh", response_model=APIResponseAccessToken)
async def owner_refresh(
    payload: RefreshRequest | None,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    token = (payload.refresh_token if payload and payload.refresh_token else None) or request.cookies.get("erp_owner_refresh_token") or request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token is required via request body or httpOnly cookie",
        )
    data = await OwnerService.refresh(db, token)
    return APIResponse(success=True, data=data, message="Token refreshed")



@router.get("/me", response_model=APIResponseOwner)
async def owner_me(
    owner: Annotated[PlatformOwner, Depends(get_current_platform_owner)],
):
    return APIResponse(success=True, data=OwnerService._info(owner), message="Profile retrieved")


# ── Password reset ────────────────────────────────────────────────────────────

@router.post("/forgot-password", response_model=APIResponse[None])
@limiter.limit("5/hour")
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await OwnerService.forgot_password(db, payload.email)
    return APIResponse(success=True, data=None, message="If the email exists, a reset link was sent")


@router.post("/reset-password", response_model=APIResponse[None])
@limiter.limit("10/hour")
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await OwnerService.reset_password(db, payload.token, payload.password)
    return APIResponse(success=True, data=None, message="Password updated — you can sign in")
