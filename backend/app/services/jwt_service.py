"""
Services — JWT Service

Encapsulates token minting, decoding, and verification for both
Platform and Tenant tokens.
Matches the payload spec in ARCHITECTURE.md exactly:
  Platform JWT: { sub, type: "platform", role, exp, iat }
  Tenant JWT:   { sub, type: "tenant", tenant_id, role, permissions, exp, iat }
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()


def create_platform_access_token(user_id: uuid.UUID, role: str) -> str:
    """Mint a Platform JWT access token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "platform",
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_tenant_access_token(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    permissions: list[str],
) -> str:
    """Mint a Tenant JWT access token with role and permission array."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "tenant",
        "tenant_id": str(tenant_id),
        "role": role,
        "permissions": permissions,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_owner_access_token(owner_id: uuid.UUID) -> str:
    """
    Mint a Platform-Owner JWT access token.

    The owner is the customer / account-holder who logs in at shikshasync.me and
    manages their institutions, billing and subscriptions. `type="owner"`
    distinguishes it from staff (`type="platform"`) and institution users
    (`type="tenant"`), so a token from one login system is never accepted by
    another.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(owner_id),
        "type": "owner",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT access token.
    Raises JWTError if invalid or expired.
    """
    return jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
