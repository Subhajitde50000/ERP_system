"""Push notification facade (kept for callers that predate the platform).

Historically ``PushService.create_in_app_notifications`` inserted inbox rows
and *logged* that FCM delivery was requested — push itself was a stub. The
real implementation now lives in ``NotificationService``
(``app/services/notification_service.py``): inbox rows plus a durable FCM
push outbox drained by the background scheduler.

This module only forwards to that service so existing callers (online-class
module, integrations added later) keep a stable, well-named API and no
notification code is duplicated across services.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.online_class import Notification
from app.services.notification_service import NotificationService


class PushService:
    """Dispatches notifications across the in-app DB inbox and push channels."""

    @staticmethod
    async def create_in_app_notifications(
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID | None,
        user_ids: list[uuid.UUID],
        title: str,
        body: str,
        notif_type: str = "ONLINE_CLASS",
        data: dict[str, Any] | None = None,
    ) -> list[Notification]:
        """Insert in-app rows and enqueue FCM push for live device tokens."""
        return await NotificationService.create_notifications(
            db,
            tenant_id=tenant_id,
            user_ids=user_ids,
            title=title,
            body=body,
            notif_type=notif_type,
            data=data,
        )
