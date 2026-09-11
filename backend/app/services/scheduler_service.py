"""Background scheduler.

Jobs:
1. Auto-starts scheduled online classes that reached `scheduled_at`.
2. Sends online-class reminders to enrolled students ~10 minutes early.
3. Drains the notification push outbox (Firebase FCM) in batches — durable,
   retried delivery of every push that was enqueued with an in-app
   notification (see app/services/notification_service.py).

Multi-worker safety: the API runs behind several uvicorn/gunicorn workers and
`startup` fires in each one, so every job above used to run once per worker
(duplicate auto-starts and reminder notifications). A Redis lease
(`erp:scheduler:leader`, TTL 90 s, renewed every 30 s) now elects a single
leader worker that registers the real jobs; the others run only the cheap
heartbeat. If the leader dies, a survivor takes over within ~2 minutes.
Without Redis the jobs start locally on every worker — the old behaviour,
kept for single-worker dev setups and loudly logged as such. Set
SCHEDULER_ENABLED=false on API-only workers for explicit control.
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

# How often the leader renews its lock, and how long the lock survives
# without renewal before another worker may take over.
_LEADER_RENEW_SECONDS = 30
_LEADER_TTL_SECONDS = 90
_LEADER_KEY = "erp:scheduler:leader"


class _LeaderLock:
    """Redis lease ensuring exactly one worker runs the scheduled jobs.

    Uses ``SET NX EX`` with a per-worker token so the incumbent always wins
    ties; renewal is a token-checked ``EXPIRE``.  If the leader dies, the key
    expires after the TTL and a survivor takes over on its next heartbeat.
    """

    def __init__(self, redis_client) -> None:
        self._redis = redis_client
        self._token = uuid.uuid4().hex

    async def acquire_or_renew(self) -> bool:
        """True when this worker owns (or just won) the leadership lease."""
        try:
            acquired = await self._redis.set(_LEADER_KEY, self._token, nx=True, ex=_LEADER_TTL_SECONDS)
            if acquired:
                return True
            current = await self._redis.get(_LEADER_KEY)
            if current is not None:
                current = current.decode() if isinstance(current, bytes) else str(current)
                if current == self._token:
                    await self._redis.expire(_LEADER_KEY, _LEADER_TTL_SECONDS)
                    return True
            return False
        except Exception as exc:  # noqa: BLE001 - Redis hiccup must not crash the loop
            logger.warning("scheduler leader check failed: %s", exc)
            return False

    async def release(self) -> None:
        """Give up leadership on graceful shutdown so failover is instant."""
        try:
            current = await self._redis.get(_LEADER_KEY)
            if current is not None:
                current = current.decode() if isinstance(current, bytes) else str(current)
                if current == self._token:
                    await self._redis.delete(_LEADER_KEY)
        except Exception:  # noqa: BLE001 - shutdown best-effort
            pass


_leader_lock: _LeaderLock | None = None
# Job ids currently registered on this worker's scheduler (leader only).
_job_ids: set[str] = set()


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


def _register_jobs() -> None:
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


def _deregister_jobs() -> None:
    for job_id in ("online_class_auto_start", "online_class_reminders", "push_deliveries"):
        scheduler.remove_job(job_id)
        _job_ids.discard(job_id)


async def _leader_heartbeat() -> None:
    """Elect or renew leadership, keeping the real jobs in sync with it.

    The incumbent keeps its jobs; a worker that loses (or never held) the
    lease removes them, so after any failover exactly one worker runs the
    auto-start / reminder / push-drain jobs.
    """
    global _job_ids
    if _leader_lock is None:  # no Redis — every worker runs locally (dev mode)
        return
    if await _leader_lock.acquire_or_renew():
        if not _job_ids:
            _register_jobs()
            _job_ids = {"online_class_auto_start", "online_class_reminders", "push_deliveries"}
            logger.info("scheduler leadership acquired — this worker runs the background jobs.")
    elif _job_ids:
        _deregister_jobs()
        logger.info("scheduler leadership lost — background jobs handed to the leader worker.")


async def start_scheduler() -> None:
    """Start the background scheduler with cluster-wide leader election.

    With Redis reachable, only the lease holder registers the jobs, and every
    worker re-checks leadership every 30 s (failover < ~2 min).  Without
    Redis, all jobs start locally — the previous behaviour, correct only for
    single-worker deployments, kept so dev environments keep working.
    """
    global _leader_lock
    if not get_settings().SCHEDULER_ENABLED:
        logger.info("Scheduler disabled via SCHEDULER_ENABLED — worker serves API traffic only.")
        return
    if scheduler.running:
        return
    try:
        from redis.asyncio import from_url

        redis_client = from_url(get_settings().REDIS_URL, decode_responses=False)
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
        await _leader_heartbeat()  # elect immediately instead of after 30 s
        logger.info("ERP background scheduler started with Redis leader election.")
    except Exception as exc:  # noqa: BLE001 - optional Redis: fall back to local jobs
        _leader_lock = None
        _register_jobs()
        scheduler.start()
        logger.warning(
            "Redis unavailable (%s) — scheduler running without leader election; "
            "run a single worker or configure REDIS_URL in production.",
            exc,
        )


async def stop_scheduler() -> None:
    """Gracefully stop the background scheduler and release leadership."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
    if _leader_lock is not None:
        await _leader_lock.release()
