"""
Routers — Platform Auth Router

Endpoints:
  POST /api/v1/platform/auth/login
  POST /api/v1/platform/auth/logout
  POST /api/v1/platform/auth/refresh
  GET  /api/v1/platform/auth/me
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies.auth import get_current_platform_user
from app.models.platform_user import PlatformUser
from app.schemas.auth import (
    AccessTokenResponse,
    LogoutRequest,
    PlatformChangePasswordRequest,
    PlatformLoginRequest,
    PlatformLoginResponse,
    PlatformProfileUpdateRequest,
    PlatformUserInfo,
    RefreshRequest,
)
from app.schemas.common import APIResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/platform/auth", tags=["Platform Authentication"])
limiter = Limiter(key_func=get_remote_address)
settings = get_settings()


@router.post("/login", response_model=APIResponse[PlatformLoginResponse])
@limiter.limit("10/minute")
async def platform_login(
    req: PlatformLoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Authenticate a platform staff member and return JWT token pair."""
    data = await AuthService.platform_login(
        email=req.email,
        password=req.password,
        request=request,
        db=db,
    )
    # Set secure httpOnly cookie
    response.set_cookie(
        key="erp_platform_refresh_token",
        value=data.tokens.refresh_token,
        httponly=True,
        secure=settings.APP_ENV == "production",
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
    )
    return APIResponse(success=True, data=data, message="Platform login successful")


@router.post("/logout", response_model=APIResponse[None])
async def platform_logout(
    req: LogoutRequest | None,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[PlatformUser, Depends(get_current_platform_user)],
):
    """Revoke the current platform session and clear cookie."""
    token = (req.refresh_token if req and req.refresh_token else None) or request.cookies.get("erp_platform_refresh_token") or request.cookies.get("refresh_token")
    if token:
        await AuthService.platform_logout(refresh_token=token, db=db)
    response.delete_cookie(key="erp_platform_refresh_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    return APIResponse(success=True, data=None, message="Logout successful")


@router.post("/refresh", response_model=APIResponse[AccessTokenResponse])
async def platform_refresh(
    req: RefreshRequest | None,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Issue a new platform access token using a valid refresh token from body or cookie."""
    token = (req.refresh_token if req and req.refresh_token else None) or request.cookies.get("erp_platform_refresh_token") or request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token is required via request body or httpOnly cookie",
        )
    data = await AuthService.platform_refresh(
        refresh_token=token, db=db
    )
    return APIResponse(
        success=True, data=data, message="Token refreshed successfully"
    )



@router.get("/me", response_model=APIResponse[PlatformUserInfo])
async def get_me(
    current_user: Annotated[PlatformUser, Depends(get_current_platform_user)],
):
    """Retrieve details of the currently authenticated platform user."""
    user_info = PlatformUserInfo(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        role=current_user.platform_role.value,
        is_active=current_user.is_active,
        last_login_at=current_user.last_login_at,
    )
    return APIResponse(success=True, data=user_info, message="User profile retrieved")


@router.put("/profile", response_model=APIResponse[PlatformUserInfo])
async def update_profile(
    payload: PlatformProfileUpdateRequest,
    current_user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update display name of the currently authenticated platform user."""
    updated = await AuthService.update_platform_profile(
        db=db, user=current_user, name=payload.name
    )
    return APIResponse(success=True, data=updated, message="Profile updated")


@router.post("/change-password", response_model=APIResponse[None])
async def change_password(
    payload: PlatformChangePasswordRequest,
    current_user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Change password for the currently authenticated platform user."""
    await AuthService.change_platform_password(
        db=db,
        user=current_user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return APIResponse(
        success=True, data=None, message="Password changed successfully"
    )
