"""
Pydantic Schemas — Authentication

Request/response models for both platform and tenant auth flows.
Pydantic v2 — uses model_config instead of class Config.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ── Requests ──────────────────────────────────────────────────────────────────

class PlatformLoginRequest(BaseModel):
    """Body for POST /platform/auth/login"""

    email: EmailStr
    password: str = Field(..., min_length=1)


class TenantLoginRequest(BaseModel):
    """
    Body for POST /tenant/auth/login.
    The slug identifies which institution this login belongs to.
    The frontend extracts it from the subdomain (abc.xyz.com → slug = 'abc').
    identifier accepts either an email address or a student roll number.
    """

    slug: str = Field(..., min_length=1, max_length=100)
    identifier: str = Field(
        ...,
        min_length=1,
        description="Email address or student roll number",
    )
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    """Body for POST .../auth/refresh (optional if refresh_token cookie is present)"""

    refresh_token: str | None = Field(default=None)


class LogoutRequest(BaseModel):
    """Body for POST .../auth/logout (optional if refresh_token cookie is present)"""

    refresh_token: str | None = Field(default=None)


class ForgotPasswordRequest(BaseModel):
    """
    Body for POST /tenant/auth/forgot-password.
    Always returns 200 — never reveals whether an account exists.
    """

    slug: str = Field(..., min_length=1, max_length=100)
    identifier: str = Field(
        ...,
        min_length=1,
        description="Email address or student roll number",
    )


class ResetPasswordRequest(BaseModel):
    """Body for POST /tenant/auth/reset-password"""

    token: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6, max_length=128)


class PlatformProfileUpdateRequest(BaseModel):
    """Body for PUT /platform/auth/profile"""

    name: str = Field(..., min_length=2, max_length=255)


class PlatformChangePasswordRequest(BaseModel):
    """Body for POST /platform/auth/change-password"""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


# ── Token payload ─────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    """Token pair returned on successful login or refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int     # access token TTL in seconds


# ── User info ─────────────────────────────────────────────────────────────────

class PlatformUserInfo(BaseModel):
    """Platform user details embedded in the login response."""

    id: uuid.UUID
    name: str
    email: str
    role: str           # e.g. "SUPER_ADMIN"
    is_active: bool
    last_login_at: datetime | None = None


class TenantUserInfo(BaseModel):
    """Tenant user details embedded in the login response."""

    id: uuid.UUID
    name: str
    email: str | None = None
    phone: str | None = None
    role: str           # primary role name, e.g. "TEACHER"
    roles: list[str]    # all role names (a user can have multiple)
    permissions: list[str]  # ["module.ACTION.SCOPE", ...]
    tenant_id: uuid.UUID
    is_active: bool
    last_login_at: datetime | None = None


# ── Login responses ───────────────────────────────────────────────────────────

class PlatformLoginResponse(BaseModel):
    """Full response body for a successful platform login."""

    tokens: TokenResponse
    user: PlatformUserInfo


class TenantLoginResponse(BaseModel):
    """Full response body for a successful tenant login."""

    tokens: TokenResponse
    user: TenantUserInfo
    tenant: "TenantInfo"


class TenantInfo(BaseModel):
    """Minimal tenant context returned on tenant login."""

    id: uuid.UUID
    name: str
    slug: str
    type: str
    timezone: str
    logo_url: str | None = None


# ── Refresh response ──────────────────────────────────────────────────────────

class AccessTokenResponse(BaseModel):
    """Returned on a successful token refresh — only a new access token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
