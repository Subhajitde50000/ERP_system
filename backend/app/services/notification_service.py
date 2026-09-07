"""
Notification subsystem service.

One place that owns:

* the in-app inbox API  (list / unread-count / mark-read / read-all)
* device-token registry (register / unregister a push destination)
* enqueuing push deliveries when a notification is created
* the background worker that drains the push outbox through Firebase FCM

The old ad-hoc copies of inbox logic in ``OnlineClassService`` and the
Firebase stub in ``push_service.py`` were folded into this service so every
consumer (online classes, parent portal, assignments, results …) talks to the
same code path. Push delivery is *durable*: when an in-app notification is
written, one ``notification_deliveries`` row is queued per live device token
and a scheduler job (``scheduler_service``) sends them with retries/backoff.
Notification failures never break the API transaction that created them —
everything below is best-effort and logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.notification import DeviceToken, NotificationDelivery
from app.models.online_class import Notification
from app.schemas.notification import (
    ALLOWED_PLATFORMS,
    NotificationPage,
    NotificationRow,
)
from app.services.fcm_client import FcmMessage, FcmResult, get_fcm_client

logger = logging.getLogger(__name__)

# ── Registry guard rails ───────────────────────────────────────────────────────
MAX_DEVICE_TOKENS_PER_USER = 25   # a user genuinely owns a handful of devices
MAX_PUSH_ATTEMPTS = 4             # total attempts incl. the first
RETRY_BACKOFF_BASE_SECONDS = 30   # 30s, 60s, 120s … capped at ~1 hour
RETRY_BACKOFF_CAP_SECONDS = 3600
MAX_DATA_PAYLOAD_BYTES = 4000     # FCM data payload soft cap (4096 per message)

VALID_DELIVERY_STATUSES = frozenset({"PENDING", "SENT", "FAILED", "SKIPPED"})


class NotificationService:
    """Inbox + device-token registry + push outbox management."""

    # ── Inbox API ─────────────────────────────────────────────────────────────

    @staticmethod
    async def _row(notification: Notification) -> NotificationRow:
        return NotificationRow(
            id=notification.id,
            title=notification.title,
            body=notification.body,
            type=notification.type,
            data=notification.data or {},
            is_read=notification.is_read,
            read_at=notification.read_at,
            created_at=notification.created_at,
        )

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        if limit < 1 or limit > 100:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="limit must be between 1 and 100")
        if offset < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="offset cannot be negative")

    @staticmethod
    async def list_inbox(
        db: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False,
    ) -> NotificationPage:
        """Paginated inbox for any signed-in user, newest first."""
        NotificationService._validate_page(limit, offset)

        where = select(Notification.id).where(Notification.user_id == user_id)
        total = (
            await db.execute(
                select(func.count(Notification.id)).where(Notification.user_id == user_id)
            )
        ).scalar_one()
        unread_count = (
            await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.user_id == user_id, Notification.is_read.is_(False)
                )
            )
        ).scalar_one()

        base = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            base = base.where(Notification.is_read.is_(False))

        rows = (
            await db.execute(
                base.order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()

        return NotificationPage(
            total=int(total),
            unread_count=int(unread_count),
            limit=limit,
            offset=offset,
            items=[await NotificationService._row(n) for n in rows],
        )

    @staticmethod
    async def unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
        """Number of unread rows — drives the bell badge on every client."""
        value = (
            await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.user_id == user_id, Notification.is_read.is_(False)
                )
            )
        ).scalar_one_or_none()
        return int(value or 0)

    @staticmethod
    async def mark_read(db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID) -> NotificationRow:
        """Mark one row read. Row must belong to the caller (owner check)."""
        notification = (
            await db.execute(
                select(Notification).where(
                    Notification.id == notification_id,
                    Notification.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if notification is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Notification not found")
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.now(timezone.utc)
            await db.flush()
        return await NotificationService._row(notification)

    @staticmethod
    async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> int:
        """Mark the caller's whole inbox read; returns the number updated."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True, read_at=now)
        )
        await db.flush()
        count = result.rowcount
        return int(count) if count is not None else 0

    # ── Device token registry ─────────────────────────────────────────────────

    @staticmethod
    async def register_device_token(
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        token: str,
        platform: str,
    ) -> DeviceToken:
        """
        Register (or refresh) one push destination for a user.

        * Re-registration of the same token only bumps ``last_used_at`` and
          re-activates a previously dead token (e.g. after a reinstall).
        * A hard cap prevents an account from filling the table with junk.
        * A unique constraint guards against duplicate rows from two racing
          requests; the loser simply adopts the winner's row.
        """
        platform = platform.strip().lower()
        if platform not in ALLOWED_PLATFORMS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"platform must be one of {sorted(ALLOWED_PLATFORMS)}")

        existing = (
            await db.execute(
                select(DeviceToken).where(
                    DeviceToken.user_id == user_id, DeviceToken.token == token
                )
            )
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if existing is not None:
            existing.is_active = True
            existing.last_used_at = now
            existing.platform = platform
            await db.flush()
            return existing

        active_count = (
            await db.execute(
                select(func.count(DeviceToken.id)).where(
                    DeviceToken.user_id == user_id, DeviceToken.is_active.is_(True)
                )
            )
        ).scalar_one_or_none()
        if int(active_count or 0) >= MAX_DEVICE_TOKENS_PER_USER:
            logger.warning(
                "push-token registration rejected: user %s already has %d active tokens",
                user_id, MAX_DEVICE_TOKENS_PER_USER,
            )
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Only {MAX_DEVICE_TOKENS_PER_USER} devices can be registered per account",
            )

        row = DeviceToken(
            id=uuid.uuid4(),
            user_id=user_id,
            token=token,
            platform=platform,
            registered_at=now,
            last_used_at=now,
            is_active=True,
        )
        db.add(row)
        try:
            await db.flush()
        except IntegrityError:
            # Lost a registration race — the unique (user_id, token) row is
            # already there; refresh it instead of failing the request.
            await db.rollback()
            existing = (
                await db.execute(
                    select(DeviceToken).where(
                        DeviceToken.user_id == user_id, DeviceToken.token == token
                    )
                )
            ).scalar_one_or_none()
            if existing is None:  # pragma: no cover - theoretical only
                raise
            existing.is_active = True
            existing.last_used_at = now
            existing.platform = platform
            await db.flush()
            return existing
        return row

    @staticmethod
    async def unregister_device_token(db: AsyncSession, user_id: uuid.UUID, token: str) -> bool:
        """
        Deactivate one token (logout / user revoked permission).

        Returns True when a row was deactivated. Inactive rows are kept as an
        audit trail but never used for delivery again.
        """
        row = (
            await db.execute(
                select(DeviceToken).where(
                    DeviceToken.user_id == user_id, DeviceToken.token == token
                )
            )
        ).scalar_one_or_none()
        if row is None or not row.is_active:
            return False
        row.is_active = False
        row.last_used_at = datetime.now(timezone.utc)
        await db.flush()
        return True

    # ── Notification creation + push enqueue ──────────────────────────────────

    @staticmethod
    def _clean_data(data: dict[str, Any] | None) -> dict[str, str]:
        """Normalise a data payload to strings and bound its size."""
        if not data:
            return {}
        cleaned: dict[str, str] = {}
        size = 0
        for key, value in data.items():
            encoded = json.dumps(value) if not isinstance(value, str) else value
            size += len(str(key)) + len(encoded)
            if size > MAX_DATA_PAYLOAD_BYTES:
                break
            cleaned[str(key)] = str(value)
        return cleaned

    @staticmethod
    async def create_notifications(
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID | None,
        user_ids: Iterable[uuid.UUID],
        title: str,
        body: str,
        notif_type: str = "SYSTEM",
        data: dict[str, Any] | None = None,
    ) -> list[Notification]:
        """
        Write an in-app notification for every recipient and enqueue push
        deliveries for their live device tokens.

        Push enqueueing is fully best-effort: a token lookup or FCM outage can
        never roll back the in-app rows or break the calling API transaction.
        """
        recipient_ids = {uid for uid in user_ids if uid is not None}
        if not recipient_ids:
            return []

        cleaned_data = NotificationService._clean_data(data)
        rows: list[Notification] = []
        for uid in recipient_ids:
            notification = Notification(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=uid,
                title=title,
                body=body,
                type=notif_type,
                data=cleaned_data,
                is_read=False,
            )
            db.add(notification)
            rows.append(notification)

        try:
            await db.flush()
            await NotificationService._enqueue_push_deliveries(db, rows)
        except Exception as exc:  # noqa: BLE001 - delivery is best-effort
            logger.warning("Push enqueue failed (in-app rows unaffected): %s", exc)
        return rows

    @staticmethod
    async def _enqueue_push_deliveries(db: AsyncSession, notifications: list[Notification]) -> None:
        """Queue one delivery row per active device token of each recipient."""
        if not notifications:
            return
        # No Firebase credentials configured → keep the outbox empty and avoid
        # pointless work for every notification created in dev/test.
        if not get_fcm_client().enabled:
            return

        user_ids = [n.user_id for n in notifications]
        tokens = (
            await db.execute(
                select(DeviceToken).where(
                    DeviceToken.user_id.in_(user_ids),
                    DeviceToken.is_active.is_(True),
                )
            )
        ).scalars().all()

        by_user: dict[uuid.UUID, list[DeviceToken]] = {}
        for token in tokens:
            by_user.setdefault(token.user_id, []).append(token)

        now = datetime.now(timezone.utc)
        for notification in notifications:
            for token in by_user.get(notification.user_id, []):
                db.add(
                    NotificationDelivery(
                        id=uuid.uuid4(),
                        notification_id=notification.id,
                        user_id=notification.user_id,
                        device_token_id=token.id,
                        platform=token.platform,
                        status="PENDING",
                        attempts=0,
                        next_attempt_at=now,
                        created_at=now,
                    )
                )
        await db.flush()

    # ── Push delivery worker ──────────────────────────────────────────────────

    @staticmethod
    def _backoff_time(attempts: int) -> datetime:
        """Exponential backoff: 30s → 60s → 120s → … capped at 1 hour."""
        delay = min(RETRY_BACKOFF_BASE_SECONDS * (2 ** max(0, attempts - 1)), RETRY_BACKOFF_CAP_SECONDS)
        return datetime.now(timezone.utc) + timedelta(seconds=delay)

    @staticmethod
    async def deliver_pending(batch_size: int | None = None) -> dict[str, int]:
        """
        Claim and send the next batch of pending pushes (scheduler job).

        Uses ``FOR UPDATE SKIP LOCKED`` so several API workers can run the
        sweep concurrently without double-sending. Returns a small counter
        dict for logging/tests:
        ``{"claimed": n, "sent": n, "disabled_tokens": n, "failed": n}``
        """
        if not get_fcm_client().enabled:
            logger.debug("push worker skipped: Firebase is not configured")
            return {"claimed": 0, "sent": 0, "disabled_tokens": 0, "failed": 0}

        settings = get_settings()
        size = batch_size or settings.NOTIFICATION_PUSH_BATCH_SIZE
        now = datetime.now(timezone.utc)
        summary = {"claimed": 0, "sent": 0, "disabled_tokens": 0, "failed": 0}

        async with AsyncSessionLocal() as db:
            try:
                deliveries = (
                    await db.execute(
                        select(NotificationDelivery)
                        .where(
                            NotificationDelivery.status == "PENDING",
                            NotificationDelivery.next_attempt_at <= now,
                            NotificationDelivery.attempts < MAX_PUSH_ATTEMPTS,
                        )
                        .order_by(NotificationDelivery.created_at.asc())
                        .limit(size)
                        .with_for_update(skip_locked=True)
                    )
                ).scalars().all()
            except Exception as exc:  # noqa: BLE001
                logger.error("push worker: could not claim outbox rows: %s", exc)
                return summary

            if not deliveries:
                return summary
            summary["claimed"] = len(deliveries)

            # Load the notification rows (title/body/data) once for the batch.
            notif_ids = {d.notification_id for d in deliveries}
            notifications = {
                n.id: n
                for n in (
                    await db.execute(select(Notification).where(Notification.id.in_(notif_ids)))
                ).scalars().all()
            }
            # Badge counts (iOS) for the users in this batch, one grouped query.
            badge_counts = dict(
                (
                    await db.execute(
                        select(Notification.user_id, func.count(Notification.id))
                        .where(
                            Notification.user_id.in_({d.user_id for d in deliveries}),
                            Notification.is_read.is_(False),
                        )
                        .group_by(Notification.user_id)
                    )
                ).all()
            )
            token_rows = {
                t.id: t
                for t in (
                    await db.execute(
                        select(DeviceToken).where(
                            DeviceToken.id.in_({d.device_token_id for d in deliveries})
                        )
                    )
                ).scalars().all()
            }

            fcm = get_fcm_client()
            semaphore = asyncio.Semaphore(10)  # bound concurrent HTTP sends

            async def send_one(delivery: NotificationDelivery) -> None:
                async with semaphore:
                    notification = notifications.get(delivery.notification_id)
                    token = token_rows.get(delivery.device_token_id)
                    if notification is None or token is None or not token.is_active:
                        delivery.status = "SKIPPED"
                        delivery.last_error = "notification or token no longer available"
                        delivery.next_attempt_at = None
                        await db.flush()
                        return
                    payload_data = dict(notification.data or {})
                    payload_data.update(
                        {
                            "notification_id": str(notification.id),
                            "type": notification.type,
                            "click_action": "OPEN_NOTIFICATIONS",
                        }
                    )
                    message = FcmMessage(
                        title=notification.title,
                        body=notification.body,
                        data=payload_data,
                        badge=int(badge_counts.get(notification.user_id, 0) or 0),
                    )
                    delivery.attempts = int(delivery.attempts or 0) + 1
                    try:
                        result: FcmResult = await fcm.send(token.token, token.platform, message)
                    except Exception as exc:  # noqa: BLE001
                        result = FcmResult(kind="retryable", error_code="EXCEPTION", detail=str(exc))

                    if result.kind == "sent":
                        delivery.status = "SENT"
                        delivery.last_error = None
                        delivery.sent_at = datetime.now(timezone.utc)
                        delivery.next_attempt_at = None
                        summary["sent"] += 1
                    elif result.kind == "invalid_token":
                        token.is_active = False
                        token.last_used_at = datetime.now(timezone.utc)
                        delivery.status = "FAILED"
                        delivery.last_error = f"{result.error_code}: {result.detail}" if result.detail else result.error_code
                        delivery.next_attempt_at = None
                        summary["disabled_tokens"] += 1
                        logger.info(
                            "deactivated dead FCM token %s (%s)", token.token[:24], result.error_code
                        )
                    else:  # retryable / failed
                        if delivery.attempts >= MAX_PUSH_ATTEMPTS:
                            delivery.status = "FAILED"
                            delivery.last_error = f"{result.error_code}: {result.detail}" if result.detail else result.error_code
                            delivery.next_attempt_at = None
                            logger.warning(
                                "push delivery %s gave up after %d attempts: %s",
                                delivery.id, delivery.attempts, delivery.last_error,
                            )
                        else:
                            delivery.next_attempt_at = NotificationService._backoff_time(delivery.attempts)
                            delivery.last_error = f"{result.error_code}: {result.detail}" if result.detail else result.error_code
                        summary["failed"] += 1

            await asyncio.gather(*(send_one(d) for d in deliveries))
            await db.commit()
        return summary
