"""Background scheduler.

Jobs:
1. Auto-starts scheduled online classes that reached `scheduled_at`.
2. Sends online-class reminders to enrolled students ~10 minutes early.
3. Drains the notification push outbox (Firebase FCM) in batches — durable,
   retried delivery of every push that was enqueued with an in-app
   notification (see app/services/notification_service.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.online_class import OnlineClass, OnlineClassStatus
from app.services.notification_service import NotificationService
from app.services.online_class_service import OnlineClassService

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def check_and_auto_start_classes() -> None:
    """Scan for scheduled classes that have reached their start time and auto-start them."""
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
                logger.info("Auto-starting scheduled online class %s ('%s')", oc.id, oc.topic)
                oc.status = OnlineClassStatus.LIVE
                oc.started_at = now
                await db.flush()
                await OnlineClassService._notify_class(
                    db, oc, "Class is live now", "Your scheduled class is starting now!"
                )
            await db.commit()
    except Exception as e:
        logger.error("Error running check_and_auto_start_classes: %s", e)


async def send_class_reminders() -> None:
    """Send a reminder notification for classes starting in the next 10-15 minutes."""
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
                    db, oc, "Upcoming Class Reminder", f"Class starts at {oc.scheduled_at.strftime('%H:%M UTC')}."
                )
            await db.commit()
    except Exception as e:
        logger.error("Error running send_class_reminders: %s", e)


async def drain_push_deliveries() -> None:
    """Sweep the notification push outbox (Firebase FCM delivery worker)."""
    try:
        summary = await NotificationService.deliver_pending()
        if summary.get("claimed"):
            logger.info("push worker round: %s", summary)
    except Exception as exc:  # noqa: BLE001 - a worker failure must not kill the loop
        logger.exception("push worker round failed: %s", exc)


def start_scheduler() -> None:
    """Initialize and start the background scheduler."""
    if not scheduler.running:
        scheduler.add_job(
            check_and_auto_start_classes,
            "interval",
            minutes=1,
            id="online_class_auto_start",
            replace_existing=True,
        )
        scheduler.add_job(
            send_class_reminders,
            "interval",
            minutes=5,
            id="online_class_reminders",
            replace_existing=True,
        )
        scheduler.add_job(
            drain_push_deliveries,
            "interval",
            seconds=10,
            id="push_deliveries",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("ERP background scheduler started (online classes + push worker).")


def stop_scheduler() -> None:
    """Gracefully stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Online class background scheduler stopped.")
