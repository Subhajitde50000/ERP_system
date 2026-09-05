"""
Notifications API — the platform inbox + push-token registry.

These endpoints serve *every* signed-in tenant user (student, teacher, parent,
principal, HOD …) from one shared implementation, unlike the earlier
online-class-only inbox. The mobile app and the website both consume this
surface:

    GET    /notifications                  → paginated inbox
    GET    /notifications/unread-count     → badge value
    POST   /notifications/read-all         → mark whole inbox read
    POST   /notifications/{id}/read        → mark one row read
    POST   /push-tokens/register           → Android/iOS/web token
    POST   /push-tokens/unregister         → logout / user revoke

Security notes
--------------
* Every read/mark route is scoped to the caller (``user_id`` from the JWT);
  a row id that belongs to another user returns 404, never 403/200.
* Token registration is rate limited per user to keep the registry clean, and
  the service enforces a per-account device cap.
"""

# NOTE: no `from __future__ import annotations` here on purpose — this router
# uses slowapi's @limiter.limit, and slowapi's functools.wraps wrapper does not
# carry __globals__ over, so string annotations would degrade the Depends()
# params into plain query parameters (see routers/parent.py for the same note).

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_tenant_user
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.notification import (
    APIResponseNotification,
    APIResponseNotificationPage,
    APIResponseUnreadCount,
    PushTokenRegisterIn,
    PushTokenUnregisterIn,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])
push_token_router = APIRouter(prefix="/push-tokens", tags=["Push Tokens"])
limiter = Limiter(key_func=get_remote_address)

DB = Annotated[AsyncSession, Depends(get_db)]
AnyTenantUser = Annotated[User, Depends(get_current_tenant_user)]


# ── Inbox ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=APIResponseNotificationPage)
async def list_notifications(
    db: DB,
    user: AnyTenantUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    unread_only: bool = Query(default=False),
):
    """Return the signed-in user's inbox, newest first."""
    return APIResponse(
        success=True,
        data=await NotificationService.list_inbox(
            db, user.id, limit=limit, offset=offset, unread_only=unread_only
        ),
        message="Notifications loaded",
    )


@router.get("/unread-count", response_model=APIResponseUnreadCount)
async def unread_count(db: DB, user: AnyTenantUser):
    """Unread total for the bell badge."""
    return APIResponse(
        success=True,
        data={"unread_count": await NotificationService.unread_count(db, user.id)},
        message="Unread count loaded",
    )


@router.post("/{notification_id}/read", response_model=APIResponseNotification)
async def mark_notification_read(db: DB, user: AnyTenantUser, notification_id: uuid.UUID):
    """Mark one notification read (owner-only)."""
    return APIResponse(
        success=True,
        data=await NotificationService.mark_read(db, user.id, notification_id),
        message="Notification marked read",
    )


@router.post("/read-all", response_model=APIResponse[dict])
async def mark_all_notifications_read(db: DB, user: AnyTenantUser):
    """Mark the entire inbox read; returns the number of rows updated."""
    count = await NotificationService.mark_all_read(db, user.id)
    return APIResponse(
        success=True, data={"updated_count": count}, message=f"Marked {count} notifications as read"
    )


# ── Push-token registry ───────────────────────────────────────────────────────

@push_token_router.post("/register", response_model=APIResponse[dict])
@limiter.limit("30/minute")
async def register_push_token(
    request: Request,
    payload: PushTokenRegisterIn,
    db: DB,
    user: AnyTenantUser,
):
    """Register a device/browser token for push delivery to this account."""
    row = await NotificationService.register_device_token(
        db, user.id, token=payload.token, platform=payload.platform
    )
    return APIResponse(
        success=True,
        data={"registered": True, "device_token_id": str(row.id), "platform": row.platform},
        message="Push token registered",
    )


@push_token_router.post("/unregister", response_model=APIResponse[dict])
async def unregister_push_token(
    payload: PushTokenUnregisterIn,
    db: DB,
    user: AnyTenantUser,
):
    """Deactivate a token (e.g. user signed out or revoked browser access)."""
    removed = await NotificationService.unregister_device_token(db, user.id, payload.token)
    if not removed:
        # Idempotent by design: unregistering an unknown/already-dead token is
        # not an error for the client.
        return APIResponse(
            success=True, data={"removed": False}, message="No active push token matched"
        )
    return APIResponse(success=True, data={"removed": True}, message="Push token unregistered")
