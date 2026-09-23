# SOURCE CODE EXTRACT DOSSIER
### [Compliance with Rule 70(5) of the Copyright Rules, 2013 as amended by G.S.R. 225(E), 30 March 2021]
## WORK TITLE: Shikshasync — Multi-Tenant Educational ERP & Learning Management System
**Author & Sole Owner:** Subhajit De
**Address:** Kolkata Sector 4, Salt Lake, Bidhannagar, Kolkata, West Bengal, India
**Class of Work:** Literary Work — Computer Software [Section 2(o), Copyright Act 1957]
**Status:** Unpublished Work (2026)

---

> **Rule 70(5) Compliance Statement**
> This dossier contains the first 10 pages and last 10 pages of the source code of the above-named
> computer programme, with no blocked-out or redacted portions, as required by Rule 70(5) of the
> Copyright Rules, 2013 (substituted by G.S.R. 225(E) dated 30 March 2021). All code below is
> reproduced exactly as it appears in the original authored files. No credential, password, secret key,
> or sensitive value appears in any source file because the software stores all such values exclusively
> in environment variables loaded at runtime from a separate `.env` file that is never part of the
> source code repository.

---

## TABLE OF CONTENTS

**PART I — FIRST 10 PAGES (Application Core)**
- Section 1.1: Application Entrypoint & Lifespan (`backend/app/main.py`)
- Section 1.2: Configuration & Settings Model (`backend/app/config.py`)
- Section 1.3: Authentication Dependencies — Tri-Plane Security (`backend/app/dependencies/auth.py`)
- Section 1.4: Tenant ORM Model (`backend/app/models/tenant.py`)

**PART II — LAST 10 PAGES (Service & Router Layer)**
- Section 2.1: Live Classroom WebSocket Router (`backend/app/routers/online_class.py`)
- Section 2.2: Background Scheduler Service (`backend/app/services/scheduler_service.py`)
- Section 2.3: Firebase Cloud Messaging Client (`backend/app/services/fcm_client.py`)

---

# PART I — FIRST 10 PAGES OF SOURCE CODE

---

## Section 1.1 — Application Entrypoint & Lifespan
**File:** `backend/app/main.py`
**Copyright © 2026 Subhajit De. All Rights Reserved.**

```python
"""
ERP Backend — Main FastAPI Application Entrypoint
"""

import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.middleware.request_id import RequestIDMiddleware
from app.routers import (
    platform_auth_router,
    platform_admin_router,
    platform_support_router,
    public_signup_router,
    owner_router,
    institution_router,
    service_requests_router,
    setup_router,
    tenant_auth_router,
    email_router,
    principal_router,
    vice_principal_router,
    hod_router,
    coordinator_router,
    exam_controller_router,
    teacher_router,
    student_router,
    parent_router,
    library_router,
    hostel_router,
    online_class_router,
    notifications_router,
    push_tokens_router,
    files_router,
)
from app.schemas.common import ErrorDetail
from app.services.fcm_client import get_fcm_client
from app.services.online_class_service import live_rooms
from app.services.scheduler_service import start_scheduler, stop_scheduler
from app.services.storage_service import validate_storage_config

settings = get_settings()

# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_storage_config()
    await live_rooms.start()
    await start_scheduler()
    yield
    await stop_scheduler()
    await live_rooms.stop()
    try:
        await get_fcm_client().aclose()
    except Exception:  # pragma: no cover - teardown best-effort
        pass


# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="ERP Platform API",
    description="Multi-Tenant ERP System Backend",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_DEBUG else None,
    redoc_url="/redoc" if settings.APP_DEBUG else None,
)
(PROJECT_ROOT / "uploads").mkdir(parents=True, exist_ok=True)

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: _rate_limit_exceeded_handler(request, exc)
)

# ── Middleware Stack ──────────────────────────────────────────────────────────
app.add_middleware(RequestIDMiddleware)

escaped_root = re.escape(settings.PUBLIC_ROOT_DOMAIN or "shikshasync.me")
cors_regex = (
    rf"https?://([a-z0-9-]+\.)*({escaped_root}|localhost|127\.0\.0\.1)(:[0-9]+)?"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_origin_regex=cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
    return response


# ── Global Exception Handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorDetail(
            success=False,
            error="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred. Please try again later.",
            details=str(exc) if settings.APP_DEBUG else None,
        ).model_dump(),
    )


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "environment": settings.APP_ENV}


# ── Router Mounts ─────────────────────────────────────────────────────────────
api_prefix = "/api/v1"
app.include_router(platform_auth_router, prefix=api_prefix)
app.include_router(platform_admin_router, prefix=api_prefix)
app.include_router(platform_support_router, prefix=api_prefix)
app.include_router(tenant_auth_router, prefix=api_prefix)
app.include_router(service_requests_router, prefix=api_prefix)
app.include_router(public_signup_router, prefix=api_prefix)
app.include_router(owner_router, prefix=api_prefix)
app.include_router(institution_router, prefix=api_prefix)
app.include_router(setup_router, prefix=api_prefix)
app.include_router(email_router, prefix=api_prefix)
app.include_router(principal_router, prefix=api_prefix)
app.include_router(vice_principal_router, prefix=api_prefix)
app.include_router(hod_router, prefix=api_prefix)
app.include_router(coordinator_router, prefix=api_prefix)
app.include_router(exam_controller_router, prefix=api_prefix)
app.include_router(teacher_router, prefix=api_prefix)
app.include_router(student_router, prefix=api_prefix)
app.include_router(parent_router, prefix=api_prefix)
app.include_router(library_router, prefix=api_prefix)
app.include_router(hostel_router, prefix=api_prefix)
app.include_router(online_class_router, prefix=api_prefix)
app.include_router(notifications_router, prefix=api_prefix)
app.include_router(push_tokens_router, prefix=api_prefix)
app.include_router(files_router, prefix=api_prefix)
```

---

## Section 1.2 — Configuration & Settings Model
**File:** `backend/app/config.py`
**Copyright © 2026 Subhajit De. All Rights Reserved.**

```python
"""
ERP Backend — Settings

All configuration is loaded from environment variables (or a .env file).
Validated at startup — a missing required variable crashes immediately,
not at the first request.
"""

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    TURN_URL: str = ""
    TURN_USERNAME: str = ""
    TURN_CREDENTIAL: str = ""
    SFU_ENABLED: bool = False
    SFU_URL: str = ""
    SFU_API_KEY: str = ""
    SFU_API_SECRET: str = ""
    SCHEDULER_ENABLED: bool = True

    def ice_servers(self) -> list[dict]:
        servers = [{"urls": "stun:stun.l.google.com:19302"}]
        if self.TURN_URL and self.TURN_USERNAME and self.TURN_CREDENTIAL:
            urls = [u.strip() for u in self.TURN_URL.split(",") if u.strip()]
            servers.append(
                {
                    "urls": (
                        urls if len(urls) > 1
                        else (urls[0] if urls else self.TURN_URL)
                    ),
                    "username": self.TURN_USERNAME,
                    "credential": self.TURN_CREDENTIAL,
                }
            )
        return servers

    # ── Online Class ──────────────────────────────────────────────────────────
    WS_MAX_ROOM_PARTICIPANTS: int = 500
    ONLINE_CLASS_UPLOAD_MAX_MB: int = 25

    # ── File storage ──────────────────────────────────────────────────────────
    STORAGE_BACKEND: str = "auto"
    UPLOAD_FILE_ROOT: str = "uploads"
    UPLOAD_SIGNED_URL_TTL_SECONDS: int = 900
    R2_BUCKET: str = ""
    R2_ENDPOINT_URL: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_KEY_PREFIX: str = ""
    S3_BUCKET: str = ""
    S3_REGION: str = ""
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_KEY_PREFIX: str = ""
    S3_FORCE_PATH_STYLE: bool = False
    ONLINE_CLASS_ALLOWED_MIME_TYPES: str = (
        "application/pdf,"
        "application/msword,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/vnd.ms-excel,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "application/vnd.ms-powerpoint,"
        "application/vnd.openxmlformats-officedocument.presentationml.presentation,"
        "image/jpeg,image/png,image/gif,image/webp,image/svg+xml,"
        "video/mp4,video/webm,video/ogg,"
        "audio/mpeg,audio/ogg,audio/wav,"
        "text/plain,text/csv"
    )

    @property
    def allowed_mime_set(self) -> set[str]:
        return {
            m.strip()
            for m in self.ONLINE_CLASS_ALLOWED_MIME_TYPES.split(",")
            if m.strip()
        }

    # ── Firebase Cloud Messaging ──────────────────────────────────────────────
    FCM_SERVICE_ACCOUNT_JSON: str = ""
    FCM_SERVICE_ACCOUNT_B64: str = ""
    FCM_PROJECT_ID: str = ""
    FCM_TTL_SECONDS: int = 86400
    NOTIFICATION_PUSH_BATCH_SIZE: int = 100

    # ── CORS ──────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_DEBUG: bool = True

    # ── Signup / provisioning ─────────────────────────────────────────────────
    PUBLIC_ROOT_DOMAIN: str = "shikshasync.me"
    TRIAL_DAYS: int = 14
    TENANT_DEFAULT_TIMEZONE: str = "Asia/Kolkata"

    # ── Email ─────────────────────────────────────────────────────────────────
    EMAIL_PROVIDER: str = "console"
    EMAIL_FROM: str = ""
    EMAIL_FROM_NAME: str = "shikshasync.me ERP"
    EMAIL_REPLY_TO: str = ""
    EMAIL_TIMEOUT_SECONDS: int = 20
    GOOGLE_SMTP_HOST: str = "smtp.gmail.com"
    GOOGLE_SMTP_PORT: int = 587
    GOOGLE_SMTP_USER: str = ""
    GOOGLE_SMTP_PASSWORD: str = ""
    ZEPTO_MAIL_SEND_TOKEN: str = ""
    ZEPTO_MAIL_API_URL: str = "https://api.zeptomail.com/v1.1/email"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]
```

---

## Section 1.3 — Authentication Dependencies — Tri-Plane Security
**File:** `backend/app/dependencies/auth.py`
**Copyright © 2026 Subhajit De. All Rights Reserved.**

```python
"""
Dependencies — Auth & Security Dependencies

Provides FastAPI Depends handlers for protecting routes:
- get_current_platform_user: verifies Platform JWT token & returns PlatformUser
- get_current_tenant_user: verifies Tenant JWT token & returns User
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.platform_user import PlatformUser
from app.models.platform_owner import PlatformOwner
from app.models.role import Role, RoleAssignment
from app.models.user import User
from app.services.jwt_service import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/tenant/auth/login")


async def get_current_platform_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformUser:
    """Dependency to extract & validate a Platform User from a JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate platform credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub", "")
        token_type: str = payload.get("type", "")
        if not user_id or token_type != "platform":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    stmt = select(PlatformUser).where(PlatformUser.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


async def get_current_tenant_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Dependency to extract & validate a Tenant User from a JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate tenant user credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub", "")
        tenant_id: str = payload.get("tenant_id", "")
        token_type: str = payload.get("type", "")
        if not user_id or not tenant_id or token_type != "tenant":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    stmt = select(User).where(
        User.id == user_id,
        User.tenant_id == tenant_id,
        User.deleted_at == None,
    )
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


async def get_current_platform_owner(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformOwner:
    """
    Dependency to extract & validate a Platform Owner (customer account) from a
    type="owner" JWT. This is the third login system: an owner token is not
    accepted by tenant or staff routes, and vice-versa.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate owner credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        owner_id: str = payload.get("sub", "")
        token_type: str = payload.get("type", "")
        if not owner_id or token_type != "owner":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    stmt = select(PlatformOwner).where(PlatformOwner.id == owner_id)
    res = await db.execute(stmt)
    owner = res.scalar_one_or_none()
    if owner is None or not owner.is_active:
        raise credentials_exception
    return owner


async def _require_current_tenant_roles(
    current_user: User,
    db: AsyncSession,
    allowed_roles: set[str],
    denial_message: str,
) -> User:
    """Resolve tenant roles from the database, not a stale JWT claim."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(RoleAssignment.id)
        .join(Role, RoleAssignment.role_id == Role.id)
        .where(
            RoleAssignment.user_id == current_user.id,
            RoleAssignment.tenant_id == current_user.tenant_id,
            RoleAssignment.is_active.is_(True),
            or_(
                RoleAssignment.expires_at.is_(None),
                RoleAssignment.expires_at > now
            ),
            Role.name.in_(allowed_roles),
        )
        .limit(1)
    )
    res = await db.execute(stmt)
    if res.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=denial_message
        )
    return current_user


async def get_current_tenant_user_admin(
    current_user: Annotated[User, Depends(get_current_tenant_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    return await _require_current_tenant_roles(
        current_user, db, {"INSTITUTION_ADMIN"},
        "Institution admin privileges are required",
    )


async def get_current_tenant_user_principal(
    current_user: Annotated[User, Depends(get_current_tenant_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    return await _require_current_tenant_roles(
        current_user, db, {"PRINCIPAL"},
        "Principal privileges are required",
    )


async def get_current_tenant_user_teacher(
    current_user: Annotated[User, Depends(get_current_tenant_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    return await _require_current_tenant_roles(
        current_user, db, {"TEACHER", "MENTOR"},
        "Teacher privileges are required",
    )


async def get_current_tenant_user_student(
    current_user: Annotated[User, Depends(get_current_tenant_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    return await _require_current_tenant_roles(
        current_user, db, {"STUDENT"},
        "Student privileges are required",
    )


async def get_current_tenant_user_parent(
    current_user: Annotated[User, Depends(get_current_tenant_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    return await _require_current_tenant_roles(
        current_user, db, {"PARENT"},
        "Parent privileges are required",
    )
```

---

## Section 1.4 — Tenant ORM Model
**File:** `backend/app/models/tenant.py`
**Copyright © 2026 Subhajit De. All Rights Reserved.**

```python
"""
ORM Model — tenants

One row per institution (school or college).
The slug is the subdomain identifier used for tenant resolution.
"""

import enum
import uuid

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class TenantType(str, enum.Enum):
    SCHOOL = "SCHOOL"
    COLLEGE = "COLLEGE"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    type: Mapped[TenantType] = mapped_column(
        SAEnum(TenantType, name="tenant_type"), nullable=False
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_owners.id", ondelete="SET NULL"),
        nullable=True,
    )
    owner_platform_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_users.id"), nullable=True
    )
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(
        String(100), nullable=False, default="India"
    )
    pincode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="Asia/Kolkata"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trial_ends_at: Mapped[TIMESTAMP | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[TIMESTAMP] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[TIMESTAMP] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Tenant {self.slug} ({self.name})>"
```

---

# PART II — LAST 10 PAGES OF SOURCE CODE

---

## Section 2.1 — Live Classroom WebSocket Router
**File:** `backend/app/routers/online_class.py`
**Copyright © 2026 Subhajit De. All Rights Reserved.**

```python
"""Online Class API — schedule or start live classes, join, auto-attendance.

Teacher endpoints live under the teaching scope; student endpoints are scoped
to the caller's active enrollment. The WebSocket carries the live classroom:
presence, chat, raise-hand, WebRTC signalling, whiteboard strokes, heartbeats.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Annotated

import anyio
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies.auth import (
    get_current_tenant_user,
    get_current_tenant_user_admin,
    get_current_tenant_user_hod,
    get_current_tenant_user_principal,
    get_current_tenant_user_student,
    get_current_tenant_user_teacher,
)
from app.models.online_class import OnlineClass, OnlineClassStatus
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.online_class import (
    APIResponseNotification,
    APIResponseNotificationPage,
    APIResponseOnlineAttendanceReport,
    APIResponseOnlineClass,
    APIResponseOnlineClassAdminPage,
    APIResponseOnlineClassDetail,
    APIResponseOnlineClassPage,
    APIResponseOnlineClassSetupOptions,
    APIResponseOnlineFile,
    APIResponseOnlineFiles,
    APIResponseOnlineMessages,
    APIResponseStudentOnlineClasses,
    AttendanceOverrideIn,
    OnlineClassCreate,
    OnlineClassUpdate,
    StudentOnlineClassRow,
)
from app.services.jwt_service import decode_access_token
from app.services.online_class_service import OnlineClassService, live_rooms

router = APIRouter(prefix="/online-classes", tags=["Online Classes"])

DB = Annotated[AsyncSession, Depends(get_db)]
Teacher = Annotated[User, Depends(get_current_tenant_user_teacher)]
Student = Annotated[User, Depends(get_current_tenant_user_student)]
AnyTenantUser = Annotated[User, Depends(get_current_tenant_user)]


@router.get("/setup-options", response_model=APIResponseOnlineClassSetupOptions)
async def setup_options(db: DB, teacher: Teacher):
    return APIResponse(
        success=True,
        data=await OnlineClassService.setup_options(db, teacher),
        message="Setup options loaded"
    )


@router.get("/my/classes", response_model=APIResponseStudentOnlineClasses)
async def my_classes(db: DB, student: Student):
    return APIResponse(
        success=True,
        data=await OnlineClassService.list_for_student(db, student),
        message="Online classes loaded"
    )


@router.post("", response_model=APIResponseOnlineClass, status_code=status.HTTP_201_CREATED)
async def schedule_class(payload: OnlineClassCreate, db: DB, teacher: Teacher):
    return APIResponse(
        success=True,
        data=await OnlineClassService.create_scheduled(db, teacher, payload),
        message="Online class scheduled",
    )


@router.post("/instant", response_model=APIResponseOnlineClass, status_code=status.HTTP_201_CREATED)
async def start_instant_class(payload: OnlineClassCreate, db: DB, teacher: Teacher):
    return APIResponse(
        success=True,
        data=await OnlineClassService.create_instant(db, teacher, payload),
        message="Class is live — students notified",
    )


@router.post("/{class_id}/start", response_model=APIResponseOnlineClass)
async def start_class(class_id: uuid.UUID, db: DB, teacher: Teacher):
    return APIResponse(
        success=True,
        data=await OnlineClassService.start(db, teacher, class_id),
        message="Class is live"
    )


@router.post("/{class_id}/end", response_model=APIResponseOnlineAttendanceReport)
async def end_class(class_id: uuid.UUID, db: DB, teacher: Teacher):
    return APIResponse(
        success=True,
        data=await OnlineClassService.end(db, teacher, class_id),
        message="Class ended — attendance generated",
    )


@router.websocket("/{class_id}/live")
async def live_room(
    websocket: WebSocket,
    class_id: uuid.UUID,
    db: DB,
    token: str = Query(...)
):
    """WebRTC signalling, presence, chat, whiteboard, and heartbeat relay.

    Browsers cannot set headers on a WebSocket handshake, so the short-lived
    tenant JWT travels in the query string and is validated before accept().
    """
    user: User | None = None
    oc: OnlineClass | None = None
    role = ""
    try:
        try:
            payload = decode_access_token(token)
        except JWTError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if (
            payload.get("type") != "tenant"
            or not payload.get("sub")
            or not payload.get("tenant_id")
        ):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        try:
            user_pk = uuid.UUID(str(payload["sub"]))
        except ValueError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        user = await db.get(User, user_pk)
        oc = await db.get(OnlineClass, class_id)
        if (
            user is None
            or not user.is_active
            or oc is None
            or oc.tenant_id != user.tenant_id
        ):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        role = "TEACHER" if user.id == oc.teacher_id else "STUDENT"
        if role == "STUDENT":
            participant = await OnlineClassService._participant(db, oc, user)
            if (
                oc.status != OnlineClassStatus.LIVE
                or participant is None
                or participant.joined_at is None
            ):
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

        await websocket.accept()
        await live_rooms.register(class_id, user.id, websocket, user.name, role)
        if role == "STUDENT":
            await OnlineClassService.ws_student_joined(db, oc, user)
        await db.commit()

        await websocket.send_json(
            {
                "type": "welcome",
                "you": {"id": str(user.id), "name": user.name, "role": role},
                "peers": await live_rooms.online_peers(class_id, exclude=user.id),
                "ice_servers": get_settings().ice_servers(),
                "sfu": {
                    "enabled": get_settings().SFU_ENABLED,
                    "url": get_settings().SFU_URL,
                },
                "whiteboard": oc.whiteboard_strokes or [],
            }
        )
        await live_rooms.broadcast(
            class_id,
            {
                "type": "peer-joined",
                "peer": {"id": str(user.id), "name": user.name, "role": role}
            },
            exclude=user.id,
        )

        while True:
            raw = await websocket.receive_text()
            if len(raw) > 128 * 1024:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")

            if kind == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            elif kind == "chat":
                body = str(msg.get("body", "")).strip()[:1000]
                if body and oc.status == OnlineClassStatus.LIVE:
                    if role == "STUDENT" and await OnlineClassService.is_student_muted(
                        db, oc.id, user.id
                    ):
                        await websocket.send_json({
                            "type": "error",
                            "message": "You are muted in this class"
                        })
                        continue
                    row = await OnlineClassService.post_message(db, user, oc, body)
                    await db.commit()
                    await live_rooms.broadcast(
                        class_id,
                        {"type": "chat", "message": row.model_dump(mode="json")}
                    )
            elif kind == "signal":
                try:
                    target_id = uuid.UUID(str(msg.get("to")))
                except (ValueError, TypeError):
                    continue
                await live_rooms.send_to(
                    class_id, target_id,
                    {"type": "signal", "from": str(user.id), "data": msg.get("data")}
                )
            elif kind == "whiteboard":
                stroke = msg.get("stroke")
                if stroke and isinstance(stroke, dict):
                    await OnlineClassService.save_whiteboard_stroke(db, oc.id, stroke)
                    await db.commit()
                await live_rooms.broadcast(
                    class_id,
                    {"type": "whiteboard", "from": str(user.id), "stroke": stroke},
                    exclude=user.id,
                )

    except WebSocketDisconnect:
        pass
    except Exception:
        await db.rollback()
    finally:
        if user is not None:
            await live_rooms.unregister(class_id, user.id)
            with anyio.CancelScope(shield=True):
                try:
                    if (
                        role == "STUDENT"
                        and oc is not None
                        and oc.status == OnlineClassStatus.LIVE
                    ):
                        await OnlineClassService.ws_student_left(db, oc, user)
                        await db.commit()
                    await live_rooms.broadcast(
                        class_id, {"type": "peer-left", "peer_id": str(user.id)}
                    )
                except Exception:
                    with contextlib.suppress(Exception):
                        await db.rollback()
```

---

## Section 2.2 — Background Scheduler Service
**File:** `backend/app/services/scheduler_service.py`
**Copyright © 2026 Subhajit De. All Rights Reserved.**

```python
"""Background scheduler.

Jobs:
1. Auto-starts scheduled online classes that reached scheduled_at.
2. Sends online-class reminders to enrolled students ~10 minutes early.
3. Drains the notification push outbox (Firebase FCM) in batches.

Multi-worker safety: a Redis lease (erp:scheduler:leader, TTL 90s, renewed
every 30s) elects a single leader worker that registers the real jobs; the
others run only the cheap heartbeat. If the leader dies, a survivor takes
over within ~2 minutes. Without Redis the jobs start locally on every
worker — correct only for single-worker dev setups.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.online_class import OnlineClass, OnlineClassStatus
from app.services.notification_service import NotificationService
from app.services.online_class_service import OnlineClassService

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

_LEADER_RENEW_SECONDS = 30
_LEADER_TTL_SECONDS = 90
_LEADER_KEY = "erp:scheduler:leader"


class _LeaderLock:
    """Redis lease ensuring exactly one worker runs the scheduled jobs."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client
        self._token = uuid.uuid4().hex

    async def acquire_or_renew(self) -> bool:
        try:
            acquired = await self._redis.set(
                _LEADER_KEY, self._token, nx=True, ex=_LEADER_TTL_SECONDS
            )
            if acquired:
                return True
            current = await self._redis.get(_LEADER_KEY)
            if current is not None:
                current = (
                    current.decode()
                    if isinstance(current, bytes)
                    else str(current)
                )
                if current == self._token:
                    await self._redis.expire(_LEADER_KEY, _LEADER_TTL_SECONDS)
                    return True
            return False
        except Exception as exc:
            logger.warning("scheduler leader check failed: %s", exc)
            return False

    async def release(self) -> None:
        try:
            current = await self._redis.get(_LEADER_KEY)
            if current is not None:
                current = (
                    current.decode()
                    if isinstance(current, bytes)
                    else str(current)
                )
                if current == self._token:
                    await self._redis.delete(_LEADER_KEY)
        except Exception:
            pass


_leader_lock: _LeaderLock | None = None
_job_ids: set[str] = set()


async def check_and_auto_start_classes() -> None:
    now = datetime.now(timezone.utc)
    try:
        async with AsyncSessionLocal() as db:
            classes = (
                await db.execute(
                    select(OnlineClass).where(
                        OnlineClass.status == OnlineClassStatus.SCHEDULED,
                        OnlineClass.scheduled_at.is_not(None),
                        OnlineClass.scheduled_at <= now,
                    )
                )
            ).scalars().all()
            for oc in classes:
                logger.info(
                    "Auto-starting scheduled online class %s ('%s')",
                    oc.id, oc.topic
                )
                oc.status = OnlineClassStatus.LIVE
                oc.started_at = now
                await db.flush()
                await OnlineClassService._notify_class(
                    db, oc,
                    "Class is live now",
                    "Your scheduled class is starting now!"
                )
            await db.commit()
    except Exception as e:
        logger.error("Error running check_and_auto_start_classes: %s", e)


async def send_class_reminders() -> None:
    now = datetime.now(timezone.utc)
    window_start = now + timedelta(minutes=9)
    window_end = now + timedelta(minutes=15)
    try:
        async with AsyncSessionLocal() as db:
            classes = (
                await db.execute(
                    select(OnlineClass).where(
                        OnlineClass.status == OnlineClassStatus.SCHEDULED,
                        OnlineClass.scheduled_at.is_not(None),
                        OnlineClass.scheduled_at >= window_start,
                        OnlineClass.scheduled_at <= window_end,
                    )
                )
            ).scalars().all()
            for oc in classes:
                await OnlineClassService._notify_class(
                    db, oc,
                    "Upcoming Class Reminder",
                    f"Class starts at {oc.scheduled_at.strftime('%H:%M UTC')}."
                )
            await db.commit()
    except Exception as e:
        logger.error("Error running send_class_reminders: %s", e)


async def drain_push_deliveries() -> None:
    try:
        summary = await NotificationService.deliver_pending()
        if summary.get("claimed"):
            logger.info("push worker round: %s", summary)
    except Exception as exc:
        logger.exception("push worker round failed: %s", exc)


async def start_scheduler() -> None:
    global _leader_lock
    if not get_settings().SCHEDULER_ENABLED:
        logger.info(
            "Scheduler disabled via SCHEDULER_ENABLED — "
            "worker serves API traffic only."
        )
        return
    if scheduler.running:
        return
    try:
        from redis.asyncio import from_url
        redis_client = from_url(
            get_settings().REDIS_URL, decode_responses=False
        )
        await redis_client.ping()
        _leader_lock = _LeaderLock(redis_client)
        scheduler.add_job(
            _leader_heartbeat,
            "interval",
            seconds=_LEADER_RENEW_SECONDS,
            id="scheduler_leader_heartbeat",
            replace_existing=True,
        )
        scheduler.start()
        await _leader_heartbeat()
        logger.info(
            "ERP background scheduler started with Redis leader election."
        )
    except Exception as exc:
        _leader_lock = None
        _register_jobs()
        scheduler.start()
        logger.warning(
            "Redis unavailable (%s) — scheduler running without leader "
            "election; run a single worker or configure REDIS_URL in "
            "production.", exc,
        )


async def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
    if _leader_lock is not None:
        await _leader_lock.release()
```

---

## Section 2.3 — Firebase Cloud Messaging Client
**File:** `backend/app/services/fcm_client.py`
**Copyright © 2026 Subhajit De. All Rights Reserved.**

```python
"""
Firebase Cloud Messaging (FCM) v1 HTTP client.

Sends push messages to Android, iOS and web registration tokens using the
Firebase v1 HTTP API without pulling in the whole firebase-admin SDK:
1. Build a signed JWT assertion from the Firebase service-account JSON,
2. exchange it at Google's OAuth2 token endpoint for an access token,
3. POST each message to https://fcm.googleapis.com/v1/projects/.../messages:send

The access token is cached and refreshed (with an asyncio.Lock so many
concurrent sends never stampede the token endpoint). The caller
(notification_service.deliver_pending) owns retries/backoff; this module
only classifies errors so the caller can decide whether a token is dead
(UNREGISTERED / INVALID_ARGUMENT / SENDER_ID_MISMATCH) or the failure
is transient (HTTP 429 / 5xx).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from jose import jwt

from app.config import get_settings

logger = logging.getLogger(__name__)

_FCM_SEND_URL = (
    "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
)
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_OAUTH_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

TERMINAL_TOKEN_CODES = frozenset({
    "UNREGISTERED", "INVALID_ARGUMENT", "SENDER_ID_MISMATCH"
})


class FcmDisabledError(RuntimeError):
    """Raised when Firebase credentials have not been configured."""


@dataclass(slots=True)
class FcmMessage:
    title: str
    body: str
    data: dict[str, str] | None = None
    badge: int | None = None


@dataclass(slots=True)
class FcmResult:
    kind: str
    error_code: str | None = None
    detail: str | None = None


class FcmClient:
    def __init__(
        self,
        settings=None,
        http_client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings or get_settings()
        self._http = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_http = http_client is None
        self._token_cache: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._credentials: dict[str, Any] | None = None

    def _load_service_account(self) -> dict[str, Any] | None:
        if self._credentials is None:
            raw: str | None = None
            if self._settings.FCM_SERVICE_ACCOUNT_JSON:
                try:
                    raw = Path(
                        self._settings.FCM_SERVICE_ACCOUNT_JSON
                    ).read_text(encoding="utf-8")
                except OSError as exc:
                    logger.error(
                        "FCM: cannot read service-account file: %s", exc
                    )
            elif self._settings.FCM_SERVICE_ACCOUNT_B64:
                try:
                    raw = base64.b64decode(
                        self._settings.FCM_SERVICE_ACCOUNT_B64
                    ).decode("utf-8")
                except (ValueError, UnicodeDecodeError) as exc:
                    logger.error(
                        "FCM: FCM_SERVICE_ACCOUNT_B64 is not valid "
                        "base64 JSON: %s", exc
                    )
            if raw:
                try:
                    self._credentials = json.loads(raw)
                except ValueError as exc:
                    logger.error(
                        "FCM: service-account payload is not valid "
                        "JSON: %s", exc
                    )
                    self._credentials = None
        return self._credentials

    @property
    def project_id(self) -> str | None:
        return (
            self._settings.FCM_PROJECT_ID
            or (self._load_service_account() or {}).get("project_id")
            or None
        )

    @property
    def enabled(self) -> bool:
        return bool(self._load_service_account() and self.project_id)

    async def _fetch_access_token(
        self, credentials: dict[str, Any]
    ) -> str | None:
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": credentials["client_email"],
                "sub": credentials["client_email"],
                "aud": credentials["token_uri"],
                "iat": now,
                "exp": now + 3600,
                "scope": _OAUTH_SCOPE,
            },
            credentials["private_key"],
            algorithm="RS256",
        )
        resp = await self._http.post(
            _OAUTH_TOKEN_URL,
            data={
                "grant_type": (
                    "urn:ietf:params:oauth:grant-type:jwt-bearer"
                ),
                "assertion": assertion,
            },
        )
        if resp.status_code != 200:
            logger.error(
                "FCM: OAuth token request failed: HTTP %s %s",
                resp.status_code, resp.text[:300]
            )
            return None
        return resp.json().get("access_token")

    async def access_token(self) -> str | None:
        credentials = self._load_service_account()
        if not credentials:
            raise FcmDisabledError(
                "Firebase Cloud Messaging is not configured"
            )
        cached = self._token_cache.get("token")
        if cached and self._token_cache.get("expires_at", 0) > time.time() + 60:
            return cached
        async with self._lock:
            cached = self._token_cache.get("token")
            if (
                cached
                and self._token_cache.get("expires_at", 0) > time.time() + 60
            ):
                return cached
            token = await self._fetch_access_token(credentials)
            if token:
                self._token_cache = {
                    "token": token,
                    "expires_at": time.time() + 3600,
                }
            return token

    async def send(
        self, token: str, platform: str, message: FcmMessage
    ) -> FcmResult:
        if not self.enabled:
            raise FcmDisabledError(
                "Firebase Cloud Messaging is not configured"
            )
        access_token = await self.access_token()
        if not access_token:
            return FcmResult(
                kind="retryable",
                error_code="AUTH",
                detail="Could not obtain OAuth token"
            )
        ttl = get_settings().FCM_TTL_SECONDS
        fcm: dict[str, Any] = {
            "token": token,
            "notification": {
                "title": message.title,
                "body": message.body
            },
            "android": {
                "priority": "HIGH",
                "ttl": f"{ttl}s",
                "notification": {
                    "sound": "default",
                    "click_action": "FLUTTER_NOTIFICATION_CLICK"
                },
            },
            "apns": {
                "headers": {
                    "apns-priority": "10",
                    "apns-push-type": "alert"
                },
                "payload": {"aps": {"sound": "default"}},
            },
        }
        if message.data:
            fcm["data"] = {str(k): str(v) for k, v in message.data.items()}
        resp = await self._http.post(
            _FCM_SEND_URL.format(project_id=self.project_id or ""),
            headers={"Authorization": f"Bearer {access_token}"},
            json={"message": fcm},
        )
        return self._classify(resp)

    @staticmethod
    def _classify(resp: httpx.Response) -> FcmResult:
        if resp.status_code == 200:
            return FcmResult(kind="sent")
        code: str | None = None
        detail: str | None = None
        try:
            payload = resp.json()
            reason = payload.get("error", {})
            code = reason.get("status") or reason.get("code")
            detail = reason.get("message") or resp.text[:300]
        except ValueError:
            detail = resp.text[:300]
        if code in TERMINAL_TOKEN_CODES:
            return FcmResult(
                kind="invalid_token", error_code=code, detail=detail
            )
        if resp.status_code in (429, 500, 502, 503, 504) or code in (
            "UNAVAILABLE", "INTERNAL", "QUOTA_EXCEEDED"
        ):
            return FcmResult(
                kind="retryable",
                error_code=code or str(resp.status_code),
                detail=detail
            )
        return FcmResult(
            kind="failed",
            error_code=code or str(resp.status_code),
            detail=detail
        )

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()


_client: FcmClient | None = None


def get_fcm_client(
    settings=None,
    http_client: httpx.AsyncClient | None = None
) -> FcmClient:
    global _client
    if _client is None:
        _client = FcmClient(settings=settings, http_client=http_client)
    elif http_client is not None or settings is not None:
        return FcmClient(settings=settings, http_client=http_client)
    return _client


def fcm_enabled() -> bool:
    return get_fcm_client().enabled
```

---

**END OF SOURCE CODE EXTRACT DOSSIER**
*Submitted under Rule 70(5) of the Copyright Rules, 2013 (as amended by G.S.R. 225(E), 30 March 2021) on behalf of the Author, Subhajit De.*
*Total: First 10 pages (Sections 1.1 to 1.4) + Last 10 pages (Sections 2.1 to 2.3). No portion is blocked out or redacted.*
