"""
Pydantic schemas for the notification & push-token API surface.

``NotificationRow`` / ``NotificationPage`` are the canonical shapes for every
inbox (mobile app, website and the legacy online-class endpoints). They used
to live in ``schemas/online_class.py``; they are defined here once and
re-exported there so nothing breaks.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import APIResponse

# Platforms accepted when registering a device token. FCM v1 receives tokens
# for Android + web directly; iOS also flows through Firebase when the app is
# built with the Firebase SDK.
PushPlatform = Literal["android", "ios", "web"]

# Keep in sync with device_tokens.platform column width (VARCHAR(10)).
ALLOWED_PLATFORMS = frozenset({"android", "ios", "web"})

# Real-world guard rails: tokens are long opaque strings; anything longer is
# almost certainly a mangled payload and would waste an outbox row.
MAX_TOKEN_LENGTH = 4096
MIN_TOKEN_LENGTH = 8


class NotificationRow(BaseModel):
    """A single in-app notification as returned to any signed-in user."""

    id: uuid.UUID
    title: str
    body: str
    type: str
    data: dict[str, Any] = {}
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class NotificationPage(BaseModel):
    """Cursor-free paginated inbox."""

    total: int
    unread_count: int
    limit: int
    offset: int
    items: list[NotificationRow]


class UnreadCount(BaseModel):
    """Badge value for the bell icon."""

    unread_count: int


class PushTokenRegisterIn(BaseModel):
    """Body for POST /push-tokens/register."""

    token: str = Field(min_length=MIN_TOKEN_LENGTH, max_length=MAX_TOKEN_LENGTH)
    platform: str

    @field_validator("platform")
    @classmethod
    def _platform_must_be_known(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in ALLOWED_PLATFORMS:
            raise ValueError(f"platform must be one of {sorted(ALLOWED_PLATFORMS)}")
        return value

    @field_validator("token")
    @classmethod
    def _token_must_be_clean(cls, value: str) -> str:
        value = value.strip()
        # FCM registration tokens are URL-safe; reject control characters /
        # whitespace that would only ever come from a buggy client.
        if any(ch.isspace() or ord(ch) < 32 for ch in value):
            raise ValueError("token contains invalid characters")
        return value


class PushTokenUnregisterIn(BaseModel):
    """Body for POST /push-tokens/unregister."""

    token: str = Field(min_length=MIN_TOKEN_LENGTH, max_length=MAX_TOKEN_LENGTH)


# ── Response envelopes ───────────────────────────────────────────────────────

APIResponseNotificationPage = APIResponse[NotificationPage]
APIResponseNotification = APIResponse[NotificationRow]
APIResponseUnreadCount = APIResponse[UnreadCount]
