"""
ORM models for the cross-platform notification subsystem.

Two tables back real-world delivery:

* ``device_tokens``           – every push destination a user has registered
  (Android / iOS via Firebase FCM, and the browser / website via FCM web
  push). One user may hold several devices; a token is re-used/upserted on
  re-registration and soft-deactivated when FCM reports it as dead.
* ``notification_deliveries`` – a durable push outbox. When an in-app
  notification row is created, one delivery row is enqueued per active device
  token of each recipient. A background worker (``scheduler_service``) drains
  the outbox in batches through Firebase FCM v1, so a slow network or a
  crashed worker can never lose a push and retries are transactional.

The ``notifications`` inbox table itself stays in
``app.models.online_class.Notification`` (kept there for backward
compatibility with existing imports/tests); these two tables are the
delivery-layer companions of that inbox.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from app.database import Base


class DeviceToken(Base):
    """A push destination registered by a user for a specific platform."""

    __tablename__ = "device_tokens"
    __table_args__ = (
        UniqueConstraint("user_id", "token", name="uq_device_tokens__user_id_token"),
        # Fast path for "all live tokens of these users" used when a
        # notification is broadcast to many recipients at once.
        Index(
            "idx_device_tokens_user_active",
            "user_id",
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(String(10), nullable=False)  # android | ios | web
    registered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class NotificationDelivery(Base):
    """One pending/attempted Firebase push for one device token."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        # Partial index: the worker only scans rows whose status is PENDING
        # and whose backoff time has been reached.
        Index(
            "idx_notif_deliveries_pending",
            "status",
            "next_attempt_at",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index("idx_notif_deliveries_notification", "notification_id"),
        Index("idx_notif_deliveries_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_token_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("device_tokens.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(10), nullable=False)
    # PENDING → SENT | FAILED | SKIPPED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
