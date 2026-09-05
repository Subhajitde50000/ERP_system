"""
ERP Backend — Main FastAPI Application Entrypoint
"""

import re
import sys
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

settings = get_settings()

# ── Rate Limiter ─────────────────────────────────────────────────────────────
# Keyed on the real client IP so a shared school NAT doesn't lock everyone out
# at the account level. Per-account lockout is enforced in the service layer.
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="ERP Platform API",
    description="Multi-Tenant ERP System Backend",
    version="1.0.0",
    docs_url="/docs" if settings.APP_DEBUG else None,
    redoc_url="/redoc" if settings.APP_DEBUG else None,
)
# B6: uploads live under this root (STORAGE_BACKEND=local) but are NEVER
# publicly mounted — every byte is served through the signed-URL files router.
(PROJECT_ROOT / "uploads").mkdir(parents=True, exist_ok=True)

# Attach limiter to app state so the decorator can find it
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: _rate_limit_exceeded_handler(request, exc))

# ── Middleware Stack ─────────────────────────────────────────────────────────
# Order matters: RequestID first so every subsequent log entry has an ID.
app.add_middleware(RequestIDMiddleware)

# Support subdomains for both localhost (Method 2) and production/custom root domains
escaped_root = re.escape(settings.PUBLIC_ROOT_DOMAIN or "xyz.com")
cors_regex = rf"https?://([a-z0-9-]+\.)*({escaped_root}|localhost|127\.0\.0\.1)(:[0-9]+)?"

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_origin_regex=cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security Headers Middleware
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



# ── Global Exception Handler ─────────────────────────────────────────────────
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


from app.services.fcm_client import get_fcm_client
from app.services.online_class_service import live_rooms
from app.services.scheduler_service import start_scheduler, stop_scheduler
from app.services.storage_service import validate_storage_config


@app.on_event("startup")
async def on_startup():
    # Validate storage backend config early — crashes with a clear message if
    # STORAGE_BACKEND=s3 is set without the required S3_BUCKET (and friends).
    validate_storage_config()
    # Cross-worker live-room fan-out (Redis pub/sub) before anything serves.
    await live_rooms.start()
    await start_scheduler()


@app.on_event("shutdown")
async def on_shutdown():
    await stop_scheduler()
    # Close the live-room Redis listener after jobs stop, but before the
    # process exits, so in-flight frames get a chance to drain.
    await live_rooms.stop()
    # Release the shared FCM HTTP client connection pool, if one was created.
    try:
        await get_fcm_client().aclose()
    except Exception:  # pragma: no cover - teardown best-effort
        pass


# ── Health Check ─────────────────────────────────────────────────────────────
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
# Stored uploads: signed, expiring downloads — replaces the old public
# /uploads static mount (see app/routers/files.py).
app.include_router(files_router, prefix=api_prefix)
