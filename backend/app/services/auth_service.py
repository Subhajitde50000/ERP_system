"""
Services — Auth Service

Core business logic for authentication:
- Platform login / logout / refresh
- Tenant login / logout / refresh
- Tenant forgot-password / reset-password
- Permission loading & RBAC resolution
- Session management in user_sessions / platform_sessions
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, status

# ── Per-account login lockout (Redis) ────────────────────────────────────────
# 5 failures within the window → account locked for LOCKOUT_SECONDS.
# Uses Redis so the counter is shared across all Uvicorn workers.
# Degrades silently (no lockout) when Redis is unavailable.
_LOCKOUT_MAX_ATTEMPTS = 5
_LOCKOUT_WINDOW_SECONDS = 300   # 5-minute sliding window for counting failures
_LOCKOUT_SECONDS = 900          # 15-minute freeze after max failures

async def _get_redis():
    """Return a Redis client, or None if Redis is unreachable."""
    try:
        from redis.asyncio import from_url
        client = from_url(get_settings().REDIS_URL, decode_responses=True)
        await client.ping()
        return client
    except Exception:
        return None

def _lockout_key(tenant_id, identifier: str) -> str:
    return f"erp:login_fail:{tenant_id}:{identifier}"

async def _check_and_record_failure(tenant_id, identifier: str, success: bool) -> None:
    """Increment failure counter on bad login; clear it on success."""
    redis = await _get_redis()
    if redis is None:
        return
    key = _lockout_key(tenant_id, identifier)
    if success:
        await redis.delete(key)
        return
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, _LOCKOUT_WINDOW_SECONDS)
    await pipe.execute()

async def _assert_not_locked(tenant_id, identifier: str) -> None:
    """Raise HTTP 429 if the account is currently locked out."""
    redis = await _get_redis()
    if redis is None:
        return
    key = _lockout_key(tenant_id, identifier)
    val = await redis.get(key)
    if val and int(val) >= _LOCKOUT_MAX_ATTEMPTS:
        ttl = await redis.ttl(key)
        wait = max(ttl, 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked after too many failed attempts. "
                   f"Try again in {wait // 60 + 1} minute(s).",
        )
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.platform_session import PlatformSession
from app.models.platform_user import PlatformRole, PlatformUser
from app.models.role import Permission, Role, RoleAssignment
from app.models.session import UserSession
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    PlatformLoginResponse,
    PlatformUserInfo,
    TenantInfo,
    TenantLoginResponse,
    TenantUserInfo,
    TokenResponse,
)
from app.services.jwt_service import (
    create_platform_access_token,
    create_tenant_access_token,
)
from app.services.mailer import queue_email
from app.utils.security import (
    generate_secure_token,
    hash_password,
    hash_token,
    verify_password,
)

settings = get_settings()


async def _load_tenant_user_permissions(
    user_id: Any, tenant_id: Any, db: AsyncSession
) -> tuple[list[str], list[str], str]:
    """
    Fetch all assigned active roles and build permissions string array
    formatted as "module_key.ACTION.SCOPE".
    Returns (roles_list, permissions_list, primary_role_name).
    """
    stmt = (
        select(RoleAssignment, Role)
        .join(Role, RoleAssignment.role_id == Role.id)
        .where(
            RoleAssignment.user_id == user_id,
            RoleAssignment.tenant_id == tenant_id,
            RoleAssignment.is_active == True,
        )
    )
    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return ([], [], "GUEST")

    roles_list = [role.name for _, role in rows]
    role_ids = [role.id for _, role in rows]
    primary_role = roles_list[0]

    perm_stmt = select(Permission).where(Permission.role_id.in_(role_ids))
    perm_result = await db.execute(perm_stmt)
    permissions = perm_result.scalars().all()

    permission_strings = list(
        {f"{p.module_key}.{p.action.value}.{p.scope.value}" for p in permissions}
    )

    return (roles_list, permission_strings, primary_role)


def _extract_ip(request: Request) -> str | None:
    """Pull the real client IP, respecting X-Forwarded-For from a trusted proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


class AuthService:
    # ── Platform Auth ────────────────────────────────────────────────────────

    @staticmethod
    async def platform_login(
        email: str,
        password: str,
        request: Request,
        db: AsyncSession,
    ) -> PlatformLoginResponse:
        stmt = select(PlatformUser).where(PlatformUser.email == email)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        # Constant-time: always verify even when user is absent
        # A syntactically valid bcrypt hash that never matches any real password.
        # passlib requires a well-formed hash to return False rather than raise.
        # Generated once with hash_password("sentinel-never-matches").
        dummy_hash = "$2b$12$CZmb7IjM5B19jizvARYHEuhnP.d0Wv4hMRaqVSwevmCb7ovXPXNWy"
        stored_hash = user.password_hash if user else dummy_hash
        password_ok = verify_password(password, stored_hash)

        if not user or not password_ok:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Platform account is inactive",
            )

        if user.platform_role == PlatformRole.OWNER and user.email_verified_at is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Verify your email before opening the platform dashboard",
            )

        user.last_login_at = datetime.now(timezone.utc)
        await db.flush()

        access_token = create_platform_access_token(
            user_id=user.id, role=user.platform_role.value
        )
        refresh_token = generate_secure_token()

        # Persist hashed refresh token
        session = PlatformSession(
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            device_info=request.headers.get("User-Agent"),
            ip_address=_extract_ip(request),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        db.add(session)
        await db.flush()

        tokens = TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        user_info = PlatformUserInfo(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.platform_role.value,
            is_active=user.is_active,
            last_login_at=user.last_login_at,
        )
        return PlatformLoginResponse(tokens=tokens, user=user_info)

    @staticmethod
    async def platform_logout(refresh_token: str, db: AsyncSession) -> None:
        """Revoke a platform session using the raw refresh token."""
        token_h = hash_token(refresh_token)
        stmt = (
            update(PlatformSession)
            .where(PlatformSession.refresh_token_hash == token_h)
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await db.execute(stmt)

    @staticmethod
    async def platform_refresh(
        refresh_token: str, db: AsyncSession
    ) -> AccessTokenResponse:
        """Issue a new platform access token if the refresh session is valid."""
        token_h = hash_token(refresh_token)
        stmt = (
            select(PlatformSession, PlatformUser)
            .join(PlatformUser, PlatformSession.user_id == PlatformUser.id)
            .where(PlatformSession.refresh_token_hash == token_h)
        )
        res = await db.execute(stmt)
        row = res.first()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        session, user = row

        if not session.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or revoked",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Platform account is inactive",
            )

        new_access_token = create_platform_access_token(
            user_id=user.id, role=user.platform_role.value
        )
        return AccessTokenResponse(
            access_token=new_access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    async def update_platform_profile(
        db: AsyncSession,
        user: PlatformUser,
        name: str,
    ) -> PlatformUserInfo:
        """Update platform user profile display name."""
        user.name = name.strip()
        await db.flush()
        return PlatformUserInfo(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.platform_role.value,
            is_active=user.is_active,
            last_login_at=user.last_login_at,
        )

    @staticmethod
    async def change_platform_password(
        db: AsyncSession,
        user: PlatformUser,
        current_password: str,
        new_password: str,
    ) -> None:
        """Change platform user password and invalidate all active sessions."""
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )
        user.password_hash = hash_password(new_password)
        await db.flush()
        # Revoke all active sessions
        stmt = (
            update(PlatformSession)
            .where(PlatformSession.user_id == user.id)
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await db.execute(stmt)

    # ── Tenant Auth ──────────────────────────────────────────────────────────

    @staticmethod
    async def tenant_login(
        slug: str,
        identifier: str,
        password: str,
        request: Request,
        db: AsyncSession,
    ) -> TenantLoginResponse:
        # 1. Resolve Tenant
        tenant_stmt = select(Tenant).where(Tenant.slug == slug)
        tenant_res = await db.execute(tenant_stmt)
        tenant = tenant_res.scalar_one_or_none()

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Institution '{slug}' not found",
            )

        if not tenant.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Institution account is suspended or inactive",
            )

        # 2. Resolve User — match on email OR student_roll_no
        from sqlalchemy import or_
        user_stmt = select(User).where(
            User.tenant_id == tenant.id,
            User.deleted_at == None,
            or_(User.email == identifier, User.student_roll_no == identifier),
        )
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()

        # Block locked-out accounts before running bcrypt (fast-fail, saves CPU)
        await _assert_not_locked(tenant.id, identifier)

        # A syntactically valid bcrypt hash that never matches any real password.
        # passlib requires a well-formed hash to return False rather than raise.
        # Generated once with hash_password("sentinel-never-matches").
        dummy_hash = "$2b$12$CZmb7IjM5B19jizvARYHEuhnP.d0Wv4hMRaqVSwevmCb7ovXPXNWy"
        stored_hash = user.password_hash if (user and user.password_hash) else dummy_hash
        password_ok = verify_password(password, stored_hash)

        if not user or not password_ok:
            # Record failure; counter drives the lockout threshold
            await _check_and_record_failure(tenant.id, identifier, success=False)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            )

        # Login succeeded — clear the failure counter
        await _check_and_record_failure(tenant.id, identifier, success=True)

        # 3. Load Roles & Permissions
        roles, permissions, primary_role = await _load_tenant_user_permissions(
            user.id, tenant.id, db
        )

        user.last_login_at = datetime.now(timezone.utc)
        await db.flush()

        # 4. Generate Tokens
        access_token = create_tenant_access_token(
            user_id=user.id,
            tenant_id=tenant.id,
            role=primary_role,
            permissions=permissions,
        )
        refresh_token = generate_secure_token()

        # 5. Persist Session
        session = UserSession(
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            device_info=request.headers.get("User-Agent"),
            ip_address=_extract_ip(request),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        db.add(session)
        await db.flush()

        # 6. Format Response
        tokens = TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        user_info = TenantUserInfo(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            role=primary_role,
            roles=roles,
            permissions=permissions,
            tenant_id=tenant.id,
            is_active=user.is_active,
            last_login_at=user.last_login_at,
        )
        tenant_info = TenantInfo(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            type=tenant.type.value,
            timezone=tenant.timezone,
            logo_url=tenant.logo_url,
        )
        return TenantLoginResponse(tokens=tokens, user=user_info, tenant=tenant_info)

    @staticmethod
    async def tenant_logout(refresh_token: str, db: AsyncSession) -> None:
        """Revoke an active tenant session using the refresh token."""
        token_h = hash_token(refresh_token)
        stmt = (
            update(UserSession)
            .where(UserSession.refresh_token_hash == token_h)
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await db.execute(stmt)

    @staticmethod
    async def tenant_refresh(
        refresh_token: str, db: AsyncSession
    ) -> AccessTokenResponse:
        """Issue a new access token if the refresh token session is valid."""
        token_h = hash_token(refresh_token)
        stmt = (
            select(UserSession, User)
            .join(User, UserSession.user_id == User.id)
            .where(UserSession.refresh_token_hash == token_h)
        )
        res = await db.execute(stmt)
        row = res.first()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        session, user = row

        if not session.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or revoked",
            )

        if not user.is_active or user.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is no longer active",
            )

        roles, permissions, primary_role = await _load_tenant_user_permissions(
            user.id, user.tenant_id, db
        )

        new_access_token = create_tenant_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=primary_role,
            permissions=permissions,
        )
        return AccessTokenResponse(
            access_token=new_access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    # ── Password Reset (tenant users only) ──────────────────────────────────

    @staticmethod
    async def tenant_forgot_password(
        slug: str, identifier: str, db: AsyncSession
    ) -> None:
        """
        Initiate a password reset for a tenant user.
        Always returns success — never reveals whether an account exists.
        The reset token is written to users.password_reset_token (hashed)
        and users.password_reset_expires. Email delivery is handled by the
        caller (queue/outbox). Returns the raw token only when an account
        was found so the caller can enqueue the email.
        """
        tenant_stmt = select(Tenant).where(Tenant.slug == slug)
        tenant_res = await db.execute(tenant_stmt)
        tenant = tenant_res.scalar_one_or_none()

        if not tenant or not tenant.is_active:
            # Silently succeed — don't reveal tenant existence to an attacker
            return

        from sqlalchemy import or_
        user_stmt = select(User).where(
            User.tenant_id == tenant.id,
            User.deleted_at == None,
            User.is_active == True,
            or_(User.email == identifier, User.student_roll_no == identifier),
        )
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()

        if not user:
            return  # Silent success

        raw_token = generate_secure_token(32)
        user.password_reset_token = hash_token(raw_token)
        user.password_reset_expires = datetime.now(timezone.utc) + timedelta(minutes=30)
        await db.flush()

        # Build the tenant-scoped reset URL: https://{slug}.{root_domain}/reset-password?token=...
        root = settings.PUBLIC_ROOT_DOMAIN or "shikshasync.me"
        reset_url = f"https://{tenant.slug}.{root}/reset-password?token={raw_token}"

        # Queue the reset email inside the same transaction — the outbox worker
        # delivers it after the session commits (same pattern as owner.forgot_password).
        if user.email:
            queue_email(
                db,
                "tenant.password_reset",
                to=user.email,
                context={
                    "name": user.name,
                    "reset_url": reset_url,
                    "expires_minutes": 30,
                    "institution": tenant.name,
                },
                tenant_id=tenant.id,
            )

    @staticmethod
    async def verify_reset_token(token: str, db: AsyncSession) -> None:
        """
        Confirm a reset token is valid and unexpired without consuming it.
        Raises HTTP 400 if invalid or expired.
        """
        token_hash = hash_token(token)
        now = datetime.now(timezone.utc)

        stmt = select(User).where(
            User.password_reset_token == token_hash,
            User.password_reset_expires > now,
            User.deleted_at == None,
        )
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reset token is invalid or has expired",
            )

    @staticmethod
    async def tenant_reset_password(
        token: str, new_password: str, db: AsyncSession
    ) -> None:
        """
        Set a new password if the reset token is valid and unexpired.
        Invalidates the token and all other sessions on success.
        """
        token_hash = hash_token(token)
        now = datetime.now(timezone.utc)

        stmt = select(User).where(
            User.password_reset_token == token_hash,
            User.password_reset_expires > now,
            User.deleted_at == None,
        )
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reset token is invalid or has expired",
            )

        user.password_hash = hash_password(new_password)
        user.password_reset_token = None
        user.password_reset_expires = None
        await db.flush()

        # Revoke all active sessions for this user
        revoke_stmt = (
            update(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.revoked_at == None,
            )
            .values(revoked_at=now)
        )
        await db.execute(revoke_stmt)
