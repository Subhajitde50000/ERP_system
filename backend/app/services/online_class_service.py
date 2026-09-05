"""Online Class workflows — schedule, go live, track joins, auto-attendance.

Scope model mirrors the teacher console: a teacher may only create classes
for subjects they actually teach (``teacher_subjects``), and a student may
only see/join classes of the class they are actively enrolled in.

Automatic attendance policy (institution default):

* attended >= 75% of the live duration  → PRESENT
* attended 30–74%                       → LATE (partial attendance)
* attended < 30% or never joined        → ABSENT

When a class ends the report is synced into the canonical
``attendance_sessions`` / ``attendance_records`` tables so the rest of the
ERP (teacher sessions, student calendar, HOD reports) sees it unchanged.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import io
import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, WebSocket, status
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.academic import Department, SchoolClass, Subject
from app.models.enrollment import Enrollment
from app.models.hod import AttendanceRecord
from app.models.online_class import (
    OnlineAttendanceStatus,
    OnlineClass,
    OnlineClassFile,
    OnlineClassMessage,
    OnlineClassMode,
    OnlineClassMutedStudent,
    OnlineClassParticipant,
    OnlineClassStatus,
)
from app.models.principal import AttendanceSession, AttendanceStatus
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.online_class import (
    NotificationPage,
    NotificationRow,
    OnlineAttendanceReport,
    OnlineAttendanceRow,
    OnlineClassAdminPage,
    OnlineClassAdminRow,
    OnlineClassAdminSummary,
    OnlineClassCreate,
    OnlineClassDetail,
    OnlineClassPage,
    OnlineClassRow,
    OnlineClassSetupOptions,
    OnlineClassUpdate,
    OnlineFileRow,
    OnlineMessageRow,
    OnlineParticipantRow,
    StudentOnlineClassList,
    StudentOnlineClassRow,
)
from app.services.audit_service import AuditService
from app.services.principal_service import PrincipalService
from app.services.notification_service import NotificationService
from app.services.storage_service import storage
from app.services.push_service import PushService
from app.services.teacher_service import TeacherService

logger = logging.getLogger(__name__)

# ── Institution attendance policy for live classes ────────────────────────────
PRESENT_MIN_RATIO = 0.75
LATE_MIN_RATIO = 0.30
MAX_WHITEBOARD_STROKES = 500


def _tenant_now(tz_name: str | None) -> datetime:
    try:
        return datetime.now(ZoneInfo(tz_name or "UTC"))
    except (ValueError, TypeError, KeyError, ZoneInfoNotFoundError):
        return datetime.now(timezone.utc)


class LiveRoomManager:
    """Hub for live classroom WebSockets with real multi-worker fan-out.

    Each worker keeps its own socket registry (``rooms``) and mirrors every
    broadcast / direct send onto a per-room Redis channel; a pub/sub listener
    on every worker delivers those messages to the sockets it owns.  Presence
    lives in a Redis hash per room so rosters and peer lists are cluster-wide.
    With no reachable Redis the manager degrades to single-worker mode (local
    rooms only) and logs one warning — chat/whiteboard keep working for the
    sockets that worker owns.

    Channel / key layout (all namespaced under ``live:``):

    * ``live:room:{class_id}``  — pub/sub channel carrying an envelope
      ``{"op": "bc" | "dm", "payload": …, "exclude"?, "target"?, "origin"}``;
      workers skip envelopes they published themselves (``origin``).
    * ``live:presence:{class_id}`` — hash ``user_id → {name, role, worker}``
      giving every worker the same roster view.
    * ``live:worker:{worker_id}`` — heartbeat key (TTL); presence entries from
      dead workers are swept on read so a crashed process cannot haunt a room.
    """

    _HEARTBEAT_SECONDS = 20
    _WORKER_TTL_SECONDS = 60
    _MAX_ENVELOPE_BYTES = 256 * 1024

    def __init__(self, redis_factory=None) -> None:
        # class_id → user_id → {"ws": WebSocket, "name": str, "role": str}
        self.rooms: dict[uuid.UUID, dict[uuid.UUID, dict]] = {}
        self._redis = None
        self._redis_factory = redis_factory
        self._pubsub_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._worker_id = uuid.uuid4().hex
        self._started = False
        self._warned_no_redis = False
        # Set once the pub/sub listener is actually subscribed, so start()
        # can guarantee early frames are not missed by a slow listener.
        self._subscribed = asyncio.Event()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Connect Redis (best-effort) and start the listener + heartbeat."""
        if self._started:
            return
        self._started = True
        self._subscribed.clear()
        if self._redis_factory is None:
            return  # unit-test / explicit local-only construction
        try:
            self._redis = self._redis_factory()
            # One round-trip up front: fail fast and fall back to local-only
            # instead of discovering the outage on the first broadcast.
            await self._redis.ping()
        except Exception as exc:  # noqa: BLE001 - Redis is optional by design
            self._redis = None
            self._warn_once(
                "Redis unavailable (%s) — live rooms run in single-worker mode; "
                "chat/whiteboard will not cross workers until Redis is reachable.",
                exc,
            )
            return
        self._pubsub_task = asyncio.create_task(self._listen(), name="live-room-pubsub")
        self._heartbeat_task = asyncio.create_task(self._heartbeat(), name="live-room-heartbeat")
        try:
            # Don't report "started" until fan-out can actually receive —
            # otherwise the first broadcast may beat the SUBSCRIBE.
            await asyncio.wait_for(self._subscribed.wait(), timeout=5)
        except TimeoutError:  # pragma: no cover - slow Redis; listener still retried by task
            logger.warning("live-room pub/sub subscription is slow to establish; proceeding anyway")

    async def stop(self) -> None:
        """Cancel background tasks and close the Redis connection."""
        for task in (self._pubsub_task, self._heartbeat_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
        self._pubsub_task = None
        self._heartbeat_task = None
        if self._redis is not None:
            try:
                await self._redis.delete(f"live:worker:{self._worker_id}")
                await self._redis.aclose()
            except Exception:  # noqa: BLE001 - shutdown best-effort
                pass
            self._redis = None
        self._started = False

    def _warn_once(self, message: str, *args) -> None:
        if self._warned_no_redis:
            return
        self._warned_no_redis = True
        logger.warning(message, *args)

    # ── Pub/sub plumbing ─────────────────────────────────────────────────────

    async def _listen(self) -> None:
        """Deliver envelopes from other workers to this worker's sockets with automatic reconnection."""
        while self._started:
            pubsub = None
            try:
                if self._redis is None and self._redis_factory is not None:
                    try:
                        self._redis = self._redis_factory()
                        await self._redis.ping()
                    except Exception:
                        self._redis = None
                        await asyncio.sleep(2)
                        continue

                if self._redis is None:
                    await asyncio.sleep(2)
                    continue

                pubsub = self._redis.pubsub()
                await pubsub.psubscribe("live:room:*")
                self._subscribed.set()
                async for message in pubsub.listen():
                    if not self._started:
                        break
                    if message.get("type") != "pmessage":
                        continue
                    try:
                        envelope = json.loads(message["data"])
                        if not isinstance(envelope, dict) or envelope.get("origin") == self._worker_id:
                            continue
                        room = uuid.UUID(message["channel"].decode().rsplit(":", 1)[-1])
                    except (ValueError, TypeError, json.JSONDecodeError):
                        continue
                    if envelope.get("op") == "dm":
                        await self._local_send(room, uuid.UUID(str(envelope.get("target"))), envelope.get("payload"))
                    else:
                        await self._local_broadcast(room, envelope.get("payload"), envelope.get("exclude"))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect on transient blip
                self._warn_once("live-room pub/sub connection interrupted, reconnecting: %s", exc)
                self._subscribed.clear()
                await asyncio.sleep(2)
            finally:
                if pubsub is not None:
                    with contextlib.suppress(Exception):
                        await pubsub.punsubscribe("live:room:*")
                        await pubsub.aclose()

    async def _heartbeat(self) -> None:
        """Keep this worker's liveness key fresh; TTL sweeps crashed workers."""
        while self._started:
            if self._redis is not None:
                try:
                    await self._redis.set(
                        f"live:worker:{self._worker_id}", "1", ex=self._WORKER_TTL_SECONDS
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    self._warn_once("live-room heartbeat failed: %s", exc)
            await asyncio.sleep(self._HEARTBEAT_SECONDS)

    async def _publish(self, class_id: uuid.UUID, envelope: dict) -> None:
        if self._redis is None and self._redis_factory is not None:
            try:
                self._redis = self._redis_factory()
                await self._redis.ping()
            except Exception:
                self._redis = None
                return
        if self._redis is None:
            return
        try:
            raw = json.dumps(envelope, default=str)
            if len(raw) > self._MAX_ENVELOPE_BYTES:
                # Relay signalling must never wedge the channel on a huge frame.
                logger.warning("dropping oversized live-room envelope for class %s", class_id)
                return
            await self._redis.publish(f"live:room:{class_id}", raw)
        except Exception as exc:  # noqa: BLE001 - Redis outage must not break local delivery
            self._warn_once("live-room publish failed (fan-out paused): %s", exc)

    # ── Local delivery ───────────────────────────────────────────────────────

    async def _local_broadcast(self, class_id: uuid.UUID, payload: dict, exclude: str | None = None) -> None:
        if not isinstance(payload, dict):
            return
        for user_id, info in list(self.rooms.get(class_id, {}).items()):
            if exclude is not None and str(user_id) == exclude:
                continue
            try:
                await info["ws"].send_json(payload)
            except Exception:
                pass  # half-closed socket; disconnect handler cleans up

    async def _local_send(self, class_id: uuid.UUID, user_id: uuid.UUID, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        info = self.rooms.get(class_id, {}).get(user_id)
        if info is not None:
            try:
                await info["ws"].send_json(payload)
            except Exception:
                pass

    # ── Presence ─────────────────────────────────────────────────────────────

    def _presence_key(self, class_id: uuid.UUID) -> str:
        return f"live:presence:{class_id}"

    async def _track_presence(self, class_id: uuid.UUID, user_id: uuid.UUID, name: str, role: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.hset(
                self._presence_key(class_id),
                str(user_id),
                json.dumps({"name": name, "role": role, "worker": self._worker_id}, default=str),
            )
        except Exception as exc:  # noqa: BLE001
            self._warn_once("live-room presence write failed: %s", exc)

    async def _untrack_presence(self, class_id: uuid.UUID, user_id: uuid.UUID) -> None:
        if self._redis is None:
            return
        try:
            key = self._presence_key(class_id)
            stored = await self._redis.hget(key, str(user_id))
            if stored is None:
                return
            entry = json.loads(stored)
            # Only the worker that owns the socket removes it — a peer that
            # reconnected on another worker must not be wiped by the old one.
            if isinstance(entry, dict) and entry.get("worker") == self._worker_id:
                await self._redis.hdel(key, str(user_id))
        except Exception as exc:  # noqa: BLE001
            self._warn_once("live-room presence delete failed: %s", exc)

    async def _cluster_peers(self, class_id: uuid.UUID) -> dict[str, dict] | None:
        """Cluster-wide presence map, sweeping entries of dead workers.

        Returns ``None`` when Redis is unavailable — callers then fall back to
        this worker's local view.
        """
        if self._redis is None:
            return None
        try:
            key = self._presence_key(class_id)
            raw = await self._redis.hgetall(key)
            peers: dict[str, dict] = {}
            stale: list[str] = []
            for uid, blob in raw.items():
                uid_text = uid.decode() if isinstance(uid, bytes) else str(uid)
                blob_text = blob.decode() if isinstance(blob, bytes) else str(blob)
                try:
                    entry = json.loads(blob_text)
                except json.JSONDecodeError:
                    stale.append(uid_text)
                    continue
                if not isinstance(entry, dict):
                    stale.append(uid_text)
                    continue
                if not await self._redis.exists(f"live:worker:{entry.get('worker')}"):
                    stale.append(uid_text)  # owning worker died mid-class
                    continue
                peers[uid_text] = entry
            if stale:
                await self._redis.hdel(key, *stale)
            return peers
        except Exception as exc:  # noqa: BLE001
            self._warn_once("live-room presence read failed: %s", exc)
            return None

    # ── Public API (unchanged shapes; presence reads are now async) ─────────

    def connect(self, class_id: uuid.UUID, user_id: uuid.UUID, ws: WebSocket, name: str, role: str) -> None:
        settings = get_settings()
        room = self.rooms.setdefault(class_id, {})
        if len(room) >= settings.WS_MAX_ROOM_PARTICIPANTS and user_id not in room:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Room has reached maximum capacity of {settings.WS_MAX_ROOM_PARTICIPANTS} participants",
            )
        room[user_id] = {"ws": ws, "name": name, "role": role}

    def disconnect(self, class_id: uuid.UUID, user_id: uuid.UUID) -> None:
        room = self.rooms.get(class_id)
        if room:
            room.pop(user_id, None)
            if not room:
                self.rooms.pop(class_id, None)

    def is_connected(self, class_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return user_id in self.rooms.get(class_id, {})

    async def active_count(self, class_id: uuid.UUID) -> int:
        peers = await self._cluster_peers(class_id)
        if peers is not None:
            return len(peers)
        return len(self.rooms.get(class_id, {}))

    async def online_peers(self, class_id: uuid.UUID, exclude: uuid.UUID | None = None) -> list[dict]:
        """Cluster-wide peer list (falls back to this worker when offline)."""
        peers = await self._cluster_peers(class_id)
        if peers is not None:
            return [
                {"id": uid, "name": entry.get("name"), "role": entry.get("role")}
                for uid, entry in peers.items()
                if exclude is None or uid != str(exclude)
            ]
        return [
            {"id": str(user_id), "name": info["name"], "role": info["role"]}
            for user_id, info in self.rooms.get(class_id, {}).items()
            if user_id != exclude
        ]

    async def register(self, class_id: uuid.UUID, user_id: uuid.UUID, ws: WebSocket, name: str, role: str) -> None:
        """Capacity-checked local registration + cluster-wide presence entry."""
        self.connect(class_id, user_id, ws, name, role)
        await self._track_presence(class_id, user_id, name, role)

    async def unregister(self, class_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Remove the local socket and (if we still own it) the presence entry."""
        self.disconnect(class_id, user_id)
        await self._untrack_presence(class_id, user_id)

    async def broadcast(self, class_id: uuid.UUID, payload: dict, exclude: uuid.UUID | None = None) -> None:
        """Broadcast payload to every peer in the room across all workers."""
        await self._local_broadcast(class_id, payload, str(exclude) if exclude else None)
        await self._publish(
            class_id,
            {"op": "bc", "payload": payload, "exclude": str(exclude) if exclude else None, "origin": self._worker_id},
        )

    async def send_to(self, class_id: uuid.UUID, user_id: uuid.UUID, payload: dict) -> None:
        """Deliver a signalling envelope to one peer, whichever worker owns it."""
        info = self.rooms.get(class_id, {}).get(user_id)
        if info is not None:
            try:
                await info["ws"].send_json(payload)
                return
            except Exception:
                pass
        await self._publish(
            class_id, {"op": "dm", "target": str(user_id), "payload": payload, "origin": self._worker_id}
        )


def _default_redis_factory():
    """Production Redis client from settings.REDIS_URL (lazy import).

    ``redis`` is a hard dependency of the deployment but an optional one at
    runtime: if the server is unreachable, LiveRoomManager.start() falls back
    to single-worker mode instead of refusing to boot.
    """
    from redis.asyncio import from_url

    return from_url(get_settings().REDIS_URL, decode_responses=False)


live_rooms = LiveRoomManager(redis_factory=_default_redis_factory)


class OnlineClassService:
    # ── Shared helpers ────────────────────────────────────────────────────────

    @staticmethod
    async def _timezone(db: AsyncSession, tenant_id: uuid.UUID) -> str | None:
        return (await db.execute(select(Tenant.timezone).where(Tenant.id == tenant_id))).scalar_one_or_none()

    @staticmethod
    async def _get_owned_class(
        db: AsyncSession, teacher: User, class_id: uuid.UUID, for_update: bool = False
    ) -> OnlineClass:
        try:
            oc = await db.get(OnlineClass, class_id, with_for_update=for_update) if for_update else await db.get(OnlineClass, class_id)
        except TypeError:
            # Handle MagicMock in unit tests that don't take with_for_update argument
            oc = await db.get(OnlineClass, class_id)
        if oc is None or oc.tenant_id != teacher.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Online class not found")
        if oc.teacher_id != teacher.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the class teacher can manage this class")
        return oc

    @staticmethod
    async def _get_visible_class(
        db: AsyncSession, user: User, class_id: uuid.UUID, for_update: bool = False
    ) -> OnlineClass:
        try:
            oc = await db.get(OnlineClass, class_id, with_for_update=for_update) if for_update else await db.get(OnlineClass, class_id)
        except TypeError:
            oc = await db.get(OnlineClass, class_id)
        if oc is None or oc.tenant_id != user.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Online class not found")
        return oc

    @staticmethod
    async def _names(db: AsyncSession, oc: OnlineClass) -> tuple[str, str, str, str]:
        """Single-query lookup for (class_name, subject_code, subject_name, teacher_name)."""
        row = (
            await db.execute(
                select(SchoolClass.name, Subject.code, Subject.name, User.name)
                .select_from(OnlineClass)
                .join(SchoolClass, SchoolClass.id == OnlineClass.class_id)
                .join(Subject, Subject.id == OnlineClass.subject_id)
                .join(User, User.id == OnlineClass.teacher_id)
                .where(OnlineClass.id == oc.id)
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Class metadata not found")
        return row[0], row[1], row[2], row[3]

    @staticmethod
    async def _to_row(db: AsyncSession, oc: OnlineClass) -> OnlineClassRow:
        class_name, subject_code, subject_name, teacher_name = await OnlineClassService._names(db, oc)
        count = (
            await db.execute(
                select(func.count(OnlineClassParticipant.id)).where(
                    OnlineClassParticipant.class_id == oc.id,
                    OnlineClassParticipant.joined_at.is_not(None),
                )
            )
        ).scalar_one()
        return OnlineClassRow(
            id=oc.id,
            class_id=oc.class_id,
            class_name=class_name,
            subject_id=oc.subject_id,
            subject_code=subject_code,
            subject_name=subject_name,
            teacher_id=oc.teacher_id,
            teacher_name=teacher_name,
            topic=oc.topic,
            mode=oc.mode.value,
            status=oc.status.value,
            scheduled_at=oc.scheduled_at,
            duration_minutes=oc.duration_minutes,
            allow_join=oc.allow_join,
            recording_enabled=oc.recording_enabled,
            recording_url=OnlineClassService._recording_url(oc),
            started_at=oc.started_at,
            ended_at=oc.ended_at,
            created_at=oc.created_at,
            participant_count=count,
        )

    @staticmethod
    async def _participant_rows(db: AsyncSession, oc: OnlineClass) -> list[OnlineParticipantRow]:
        # Fetch muted student IDs for this class
        muted_ids = set(
            (
                await db.execute(
                    select(OnlineClassMutedStudent.student_id).where(OnlineClassMutedStudent.class_id == oc.id)
                )
            )
            .scalars()
            .all()
        )

        rows = (
            await db.execute(
                select(OnlineClassParticipant, User.name, Enrollment.roll_number)
                .join(User, User.id == OnlineClassParticipant.student_id)
                .outerjoin(
                    Enrollment,
                    and_(
                        Enrollment.student_id == OnlineClassParticipant.student_id,
                        Enrollment.class_id == oc.class_id,
                    ),
                )
                .where(OnlineClassParticipant.class_id == oc.id)
                .order_by(OnlineClassParticipant.waiting_since)
            )
        ).all()
        return [
            OnlineParticipantRow(
                student_id=p.student_id,
                student_name=name,
                roll_number=roll,
                waiting_since=p.waiting_since,
                joined_at=p.joined_at,
                left_at=p.left_at,
                duration_seconds=p.duration_seconds,
                attendance_status=p.attendance_status.value if p.attendance_status else None,
                hand_raised_at=p.hand_raised_at,
                is_online=p.is_online,
                is_muted=p.student_id in muted_ids,
            )
            for p, name, roll in rows
        ]

    @staticmethod
    async def _file_rows(db: AsyncSession, class_id: uuid.UUID) -> list[OnlineFileRow]:
        rows = (
            await db.execute(
                select(OnlineClassFile, User.name)
                .join(User, User.id == OnlineClassFile.uploader_id)
                .where(OnlineClassFile.class_id == class_id)
                .order_by(OnlineClassFile.created_at)
            )
        ).all()
        return [
            OnlineFileRow(
                id=f.id,
                uploader_id=f.uploader_id,
                uploader_name=name,
                uploader_role=f.uploader_role,
                file_name=f.file_name,
                url=storage.signed_url(
                    f.file_path if "/" in f.file_path else f"online-classes/{class_id}/{f.file_path}"
                ),
                file_size_bytes=f.file_size_bytes,
                mime_type=f.mime_type,
                created_at=f.created_at,
            )
            for f, name in rows
        ]

    @staticmethod
    def _recording_url(oc: OnlineClass) -> str | None:
        """Sign the stored recording key per response (never persist URLs).

        Legacy rows hold ``/uploads/…`` paths, newer ones the bare storage
        key — the storage service normalises both. Absolute external URLs
        pass through untouched.
        """
        if not oc.recording_url:
            return None
        if oc.recording_url.startswith(("http://", "https://", "//")):
            return oc.recording_url
        return storage.signed_url(oc.recording_url)

    # ── Teacher: setup & creation ─────────────────────────────────────────────

    @staticmethod
    async def setup_options(db: AsyncSession, teacher: User) -> OnlineClassSetupOptions:
        scope = await TeacherService.scope_for_user(db, teacher)
        current_year = await TeacherService._current_year(db, teacher.tenant_id)
        slots = []
        if current_year is not None:
            today = await PrincipalService._tenant_today(db, teacher.tenant_id)
            slots = await TeacherService._slots_for(
                db, teacher.tenant_id, current_year.id, teacher_id=teacher.id, day=today
            )
            slots = [s for s in slots if s.class_id in scope.class_ids and s.subject_id is not None]
        return OnlineClassSetupOptions(assignments=list(scope.assignments), today_slots=slots)

    @staticmethod
    async def _create(
        db: AsyncSession,
        teacher: User,
        payload: OnlineClassCreate,
        mode: OnlineClassMode,
    ) -> OnlineClass:
        scope = await TeacherService.scope_for_user(db, teacher)
        TeacherService._ensure_teaches(scope, payload.subject_id, payload.class_id)
        subject = (
            await db.execute(
                select(Subject).where(Subject.id == payload.subject_id, Subject.class_id == payload.class_id)
            )
        ).scalar_one_or_none()
        if subject is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Subject does not belong to this class")

        now = _tenant_now(await OnlineClassService._timezone(db, teacher.tenant_id))
        if mode == OnlineClassMode.INSTANT:
            oc_status, started, scheduled = OnlineClassStatus.LIVE, now, now
        else:
            if payload.scheduled_at is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="scheduled_at is required")
            if payload.scheduled_at <= now:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Scheduled time must be in the future")
            oc_status, started, scheduled = OnlineClassStatus.SCHEDULED, None, payload.scheduled_at

        oc = OnlineClass(
            id=uuid.uuid4(),
            tenant_id=teacher.tenant_id,
            teacher_id=teacher.id,
            class_id=payload.class_id,
            subject_id=payload.subject_id,
            timetable_slot_id=payload.timetable_slot_id,
            topic=payload.topic.strip(),
            mode=mode,
            status=oc_status,
            scheduled_at=scheduled,
            duration_minutes=payload.duration_minutes,
            allow_join=payload.allow_join,
            recording_enabled=payload.recording_enabled,
            started_at=started,
            whiteboard_strokes=[],
        )
        db.add(oc)
        await db.flush()
        AuditService.record(
            db,
            actor=teacher,
            actor_role="TEACHER",
            action="CREATE_ONLINE_CLASS",
            entity="OnlineClass",
            entity_id=oc.id,
            tenant_id=teacher.tenant_id,
            new_value={"mode": mode.value, "topic": oc.topic},
        )
        return oc

    @staticmethod
    async def create_scheduled(db: AsyncSession, teacher: User, payload: OnlineClassCreate) -> OnlineClassRow:
        oc = await OnlineClassService._create(db, teacher, payload, OnlineClassMode.SCHEDULED)
        return await OnlineClassService._to_row(db, oc)

    @staticmethod
    async def create_instant(db: AsyncSession, teacher: User, payload: OnlineClassCreate) -> OnlineClassRow:
        oc = await OnlineClassService._create(db, teacher, payload, OnlineClassMode.INSTANT)
        await OnlineClassService._notify_class(db, oc, "Live class starting now")
        return await OnlineClassService._to_row(db, oc)

    @staticmethod
    async def _notify_class(db: AsyncSession, oc: OnlineClass, title: str, body_suffix: str = "Join from Online classes.") -> None:
        """Send in-app notifications and push alerts to all actively enrolled students."""
        current_year = await TeacherService._current_year(db, oc.tenant_id)
        if current_year is None:
            return
        student_ids = (
            await db.execute(
                select(Enrollment.student_id).where(
                    Enrollment.tenant_id == oc.tenant_id,
                    Enrollment.class_id == oc.class_id,
                    Enrollment.academic_year_id == current_year.id,
                    Enrollment.status == "ACTIVE",
                )
            )
        ).scalars().all()
        if not student_ids:
            return

        subject_name = (await db.execute(select(Subject.name).where(Subject.id == oc.subject_id))).scalar_one_or_none() or "Subject"
        body = f"{subject_name}: {oc.topic}. {body_suffix}"

        await PushService.create_in_app_notifications(
            db,
            tenant_id=oc.tenant_id,
            user_ids=list(student_ids),
            title=title,
            body=body,
            notif_type="ONLINE_CLASS",
            data={"class_id": str(oc.id), "topic": oc.topic},
        )

    # ── Teacher: lifecycle ────────────────────────────────────────────────────

    @staticmethod
    async def list_for_teacher(
        db: AsyncSession,
        teacher: User,
        status_filter: str | None = None,
        subject_id: uuid.UUID | None = None,
        class_id: uuid.UUID | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> OnlineClassPage:
        TeacherService._validate_page(limit, offset)
        base = (
            select(
                OnlineClass,
                SchoolClass.name.label("class_name"),
                Subject.code.label("subject_code"),
                Subject.name.label("subject_name"),
                User.name.label("teacher_name"),
                func.count(OnlineClassParticipant.id).filter(OnlineClassParticipant.joined_at.is_not(None)).label("participant_count"),
            )
            .join(SchoolClass, SchoolClass.id == OnlineClass.class_id)
            .join(Subject, Subject.id == OnlineClass.subject_id)
            .join(User, User.id == OnlineClass.teacher_id)
            .outerjoin(OnlineClassParticipant, OnlineClassParticipant.class_id == OnlineClass.id)
            .where(OnlineClass.tenant_id == teacher.tenant_id, OnlineClass.teacher_id == teacher.id)
            .group_by(OnlineClass.id, SchoolClass.name, Subject.code, Subject.name, User.name)
        )

        if status_filter:
            try:
                base = base.where(OnlineClass.status == OnlineClassStatus(status_filter.upper()))
            except ValueError:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown status filter")
        if subject_id:
            base = base.where(OnlineClass.subject_id == subject_id)
        if class_id:
            base = base.where(OnlineClass.class_id == class_id)
        if from_date:
            base = base.where(func.date(OnlineClass.created_at) >= from_date)
        if to_date:
            base = base.where(func.date(OnlineClass.created_at) <= to_date)
        if search and search.strip():
            base = base.where(OnlineClass.topic.ilike(f"%{search.strip()}%"))

        total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = (
            await db.execute(
                base.order_by(OnlineClass.created_at.desc()).limit(limit).offset(offset)
            )
        ).all()

        items = [
            OnlineClassRow(
                id=oc.id,
                class_id=oc.class_id,
                class_name=class_name,
                subject_id=oc.subject_id,
                subject_code=subject_code,
                subject_name=subject_name,
                teacher_id=oc.teacher_id,
                teacher_name=teacher_name,
                topic=oc.topic,
                mode=oc.mode.value,
                status=oc.status.value,
                scheduled_at=oc.scheduled_at,
                duration_minutes=oc.duration_minutes,
                allow_join=oc.allow_join,
                recording_enabled=oc.recording_enabled,
                recording_url=OnlineClassService._recording_url(oc),
                started_at=oc.started_at,
                ended_at=oc.ended_at,
                created_at=oc.created_at,
                participant_count=p_count,
            )
            for oc, class_name, subject_code, subject_name, teacher_name, p_count in rows
        ]

        return OnlineClassPage(total=total, limit=limit, offset=offset, items=items)

    @staticmethod
    async def detail_for_teacher(db: AsyncSession, teacher: User, class_id: uuid.UUID) -> OnlineClassDetail:
        oc = await OnlineClassService._get_owned_class(db, teacher, class_id)
        row = await OnlineClassService._to_row(db, oc)
        roster = await TeacherService._roster(db, teacher.tenant_id, oc.class_id)
        muted_ids = (
            await db.execute(
                select(OnlineClassMutedStudent.student_id).where(OnlineClassMutedStudent.class_id == oc.id)
            )
        ).scalars().all()

        return OnlineClassDetail(
            **row.model_dump(),
            roster_size=len(roster),
            participants=await OnlineClassService._participant_rows(db, oc),
            files=await OnlineClassService._file_rows(db, oc.id),
            muted_student_ids=list(muted_ids),
            whiteboard_strokes=oc.whiteboard_strokes or [],
        )

    @staticmethod
    async def start(db: AsyncSession, teacher: User, class_id: uuid.UUID) -> OnlineClassRow:
        oc = await OnlineClassService._get_owned_class(db, teacher, class_id, for_update=True)
        if oc.status != OnlineClassStatus.SCHEDULED:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Only a scheduled class can be started")
        now = _tenant_now(await OnlineClassService._timezone(db, teacher.tenant_id))
        oc.status = OnlineClassStatus.LIVE
        oc.started_at = now
        await db.flush()
        await OnlineClassService._notify_class(db, oc, "Class is live now", "Join now from Online classes.")
        AuditService.record(
            db, actor=teacher, actor_role="TEACHER", action="START_ONLINE_CLASS",
            entity="OnlineClass", entity_id=oc.id, tenant_id=teacher.tenant_id,
        )
        return await OnlineClassService._to_row(db, oc)

    @staticmethod
    async def update(
        db: AsyncSession, teacher: User, class_id: uuid.UUID, payload: OnlineClassUpdate
    ) -> OnlineClassRow:
        oc = await OnlineClassService._get_owned_class(db, teacher, class_id, for_update=True)
        if oc.status in (OnlineClassStatus.COMPLETED, OnlineClassStatus.CANCELLED):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This class has already ended or was cancelled")

        if payload.topic is not None and payload.topic.strip():
            oc.topic = payload.topic.strip()
        if payload.scheduled_at is not None:
            if oc.status != OnlineClassStatus.SCHEDULED:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="Can only reschedule an upcoming class")
            now = _tenant_now(await OnlineClassService._timezone(db, teacher.tenant_id))
            if payload.scheduled_at <= now:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Scheduled time must be in the future")
            oc.scheduled_at = payload.scheduled_at
        if payload.duration_minutes is not None:
            oc.duration_minutes = payload.duration_minutes
        if payload.allow_join is not None:
            oc.allow_join = payload.allow_join
        if payload.recording_enabled is not None:
            oc.recording_enabled = payload.recording_enabled

        await db.flush()
        return await OnlineClassService._to_row(db, oc)

    @staticmethod
    async def cancel(db: AsyncSession, teacher: User, class_id: uuid.UUID) -> OnlineClassRow:
        oc = await OnlineClassService._get_owned_class(db, teacher, class_id, for_update=True)
        if oc.status != OnlineClassStatus.SCHEDULED:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Only a scheduled class can be cancelled")
        oc.status = OnlineClassStatus.CANCELLED
        await db.flush()
        await OnlineClassService._notify_class(db, oc, "Class Cancelled", "The scheduled session was cancelled.")
        AuditService.record(
            db, actor=teacher, actor_role="TEACHER", action="CANCEL_ONLINE_CLASS",
            entity="OnlineClass", entity_id=oc.id, tenant_id=teacher.tenant_id,
        )
        return await OnlineClassService._to_row(db, oc)

    @staticmethod
    async def end(db: AsyncSession, teacher: User, class_id: uuid.UUID) -> OnlineAttendanceReport:
        oc = await OnlineClassService._get_owned_class(db, teacher, class_id, for_update=True)
        if oc.status != OnlineClassStatus.LIVE:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Only a live class can be ended")
        now = datetime.now(timezone.utc)
        oc.status = OnlineClassStatus.COMPLETED
        oc.ended_at = now

        participants = (
            await db.execute(select(OnlineClassParticipant).where(OnlineClassParticipant.class_id == oc.id))
        ).scalars().all()
        for p in participants:
            if p.is_online and p.joined_at is not None:
                p.duration_seconds += max(0, int((now - p.waiting_since).total_seconds()))
            if p.joined_at is not None and p.left_at is None:
                p.left_at = now
            p.is_online = False
            p.hand_raised_at = None
        await db.flush()

        oc.attendance_session_id = await OnlineClassService._finalize_attendance(db, oc, participants)
        await db.flush()
        AuditService.record(
            db, actor=teacher, actor_role="TEACHER", action="END_ONLINE_CLASS",
            entity="OnlineClass", entity_id=oc.id, tenant_id=teacher.tenant_id,
            new_value={"participants": len(participants)},
        )
        await live_rooms.broadcast(oc.id, {"type": "class-ended"})
        return await OnlineClassService.attendance_report(db, teacher, class_id)

    # ── Teacher: waiting room, mute & participants ────────────────────────────

    @staticmethod
    async def _get_participant(db: AsyncSession, oc: OnlineClass, student_id: uuid.UUID) -> OnlineClassParticipant:
        p = (
            await db.execute(
                select(OnlineClassParticipant).where(
                    OnlineClassParticipant.class_id == oc.id, OnlineClassParticipant.student_id == student_id
                )
            )
        ).scalar_one_or_none()
        if p is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student is not in the waiting room")
        return p

    @staticmethod
    def _admit_participant(p: OnlineClassParticipant) -> None:
        now = datetime.now(timezone.utc)
        if p.joined_at is None:
            p.joined_at = now
        p.waiting_since = now  # start of the current in-class segment
        p.is_online = True

    @staticmethod
    def _record_leave(p: OnlineClassParticipant) -> None:
        now = datetime.now(timezone.utc)
        if p.is_online and p.joined_at is not None:
            p.duration_seconds += max(0, int((now - p.waiting_since).total_seconds()))
            p.left_at = now
        p.is_online = False
        p.hand_raised_at = None

    @staticmethod
    async def admit(db: AsyncSession, teacher: User, class_id: uuid.UUID, student_id: uuid.UUID) -> OnlineClassDetail:
        oc = await OnlineClassService._get_owned_class(db, teacher, class_id)
        if oc.status != OnlineClassStatus.LIVE:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Class is not live")
        p = await OnlineClassService._get_participant(db, oc, student_id)
        OnlineClassService._admit_participant(p)
        await db.flush()
        await live_rooms.send_to(oc.id, student_id, {"type": "admitted"})
        return await OnlineClassService.detail_for_teacher(db, teacher, class_id)

    @staticmethod
    async def admit_all(db: AsyncSession, teacher: User, class_id: uuid.UUID) -> OnlineClassDetail:
        oc = await OnlineClassService._get_owned_class(db, teacher, class_id)
        if oc.status != OnlineClassStatus.LIVE:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Class is not live")
        waiting = (
            await db.execute(
                select(OnlineClassParticipant).where(
                    OnlineClassParticipant.class_id == oc.id,
                    OnlineClassParticipant.joined_at.is_(None),
                )
            )
        ).scalars().all()
        for p in waiting:
            OnlineClassService._admit_participant(p)
            await live_rooms.send_to(oc.id, p.student_id, {"type": "admitted"})
        await db.flush()
        return await OnlineClassService.detail_for_teacher(db, teacher, class_id)

    @staticmethod
    async def remove_student(
        db: AsyncSession, teacher: User, class_id: uuid.UUID, student_id: uuid.UUID
    ) -> OnlineClassDetail:
        oc = await OnlineClassService._get_owned_class(db, teacher, class_id)
        if oc.status != OnlineClassStatus.LIVE:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Class is not live")
        p = await OnlineClassService._get_participant(db, oc, student_id)
        OnlineClassService._record_leave(p)
        await db.flush()
        await live_rooms.send_to(oc.id, student_id, {"type": "removed"})
        return await OnlineClassService.detail_for_teacher(db, teacher, class_id)

    @staticmethod
    async def mute_student(
        db: AsyncSession, teacher: User, class_id: uuid.UUID, student_id: uuid.UUID
    ) -> OnlineClassDetail:
        oc = await OnlineClassService._get_owned_class(db, teacher, class_id)
        existing = (
            await db.execute(
                select(OnlineClassMutedStudent).where(
                    OnlineClassMutedStudent.class_id == oc.id,
                    OnlineClassMutedStudent.student_id == student_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                OnlineClassMutedStudent(
                    id=uuid.uuid4(),
                    tenant_id=teacher.tenant_id,
                    class_id=oc.id,
                    student_id=student_id,
                )
            )
            await db.flush()
        await live_rooms.send_to(oc.id, student_id, {"type": "muted", "is_muted": True})
        return await OnlineClassService.detail_for_teacher(db, teacher, class_id)

    @staticmethod
    async def unmute_student(
        db: AsyncSession, teacher: User, class_id: uuid.UUID, student_id: uuid.UUID
    ) -> OnlineClassDetail:
        oc = await OnlineClassService._get_owned_class(db, teacher, class_id)
        await db.execute(
            delete(OnlineClassMutedStudent).where(
                OnlineClassMutedStudent.class_id == oc.id,
                OnlineClassMutedStudent.student_id == student_id,
            )
        )
        await db.flush()
        await live_rooms.send_to(oc.id, student_id, {"type": "muted", "is_muted": False})
        return await OnlineClassService.detail_for_teacher(db, teacher, class_id)

    @staticmethod
    async def is_student_muted(db: AsyncSession, class_id: uuid.UUID, student_id: uuid.UUID) -> bool:
        muted = (
            await db.execute(
                select(OnlineClassMutedStudent.id).where(
                    OnlineClassMutedStudent.class_id == class_id,
                    OnlineClassMutedStudent.student_id == student_id,
                )
            )
        ).scalar_one_or_none()
        return muted is not None

    # ── Attendance report & canonical sync ────────────────────────────────────

    @staticmethod
    def _attendance_status(duration_seconds: int, class_seconds: int) -> OnlineAttendanceStatus:
        if class_seconds <= 0 or duration_seconds <= 0:
            return OnlineAttendanceStatus.ABSENT
        ratio = duration_seconds / class_seconds
        if ratio >= PRESENT_MIN_RATIO:
            return OnlineAttendanceStatus.PRESENT
        if ratio >= LATE_MIN_RATIO:
            return OnlineAttendanceStatus.LATE
        return OnlineAttendanceStatus.ABSENT

    @staticmethod
    async def attendance_report(db: AsyncSession, teacher: User, class_id: uuid.UUID) -> OnlineAttendanceReport:
        oc = await OnlineClassService._get_owned_class(db, teacher, class_id)
        class_name, _, subject_name, _ = await OnlineClassService._names(db, oc)
        class_seconds = int((oc.ended_at - oc.started_at).total_seconds()) if oc.started_at and oc.ended_at else 0
        roster = await TeacherService._roster(db, teacher.tenant_id, oc.class_id)
        joined = {
            p.student_id: p
            for p in (
                await db.execute(select(OnlineClassParticipant).where(OnlineClassParticipant.class_id == oc.id))
            ).scalars().all()
        }
        rows: list[OnlineAttendanceRow] = []
        totals = {OnlineAttendanceStatus.PRESENT: 0, OnlineAttendanceStatus.LATE: 0, OnlineAttendanceStatus.ABSENT: 0}
        for entry in roster:
            p = joined.get(entry.student_id)
            seconds = p.duration_seconds if p else 0
            derived = (
                p.attendance_status
                if p is not None and p.attendance_status is not None
                else OnlineClassService._attendance_status(seconds, class_seconds)
            )
            totals[derived] += 1
            rows.append(
                OnlineAttendanceRow(
                    student_id=entry.student_id,
                    student_name=entry.student_name,
                    roll_number=entry.roll_number,
                    joined_at=p.joined_at if p else None,
                    left_at=p.left_at if p else None,
                    duration_seconds=seconds,
                    percent=round(seconds * 100 / class_seconds, 1) if class_seconds else None,
                    attendance_status=derived.value,
                )
            )
        return OnlineAttendanceReport(
            class_id=str(oc.id),
            class_name=class_name,
            subject_name=subject_name,
            topic=oc.topic,
            started_at=oc.started_at,
            ended_at=oc.ended_at,
            duration_seconds=class_seconds,
            present_min_percent=PRESENT_MIN_RATIO * 100,
            late_min_percent=LATE_MIN_RATIO * 100,
            totals_present=totals[OnlineAttendanceStatus.PRESENT],
            totals_late=totals[OnlineAttendanceStatus.LATE],
            totals_absent=totals[OnlineAttendanceStatus.ABSENT],
            rows=rows,
        )

    @staticmethod
    async def override_attendance(
        db: AsyncSession,
        teacher: User,
        class_id: uuid.UUID,
        student_id: uuid.UUID,
        target_status: str,
        remarks: str | None = None,
    ) -> OnlineAttendanceReport:
        """Allow teacher to manually adjust attendance for a participant and update canonical record."""
        oc = await OnlineClassService._get_owned_class(db, teacher, class_id)
        if oc.status != OnlineClassStatus.COMPLETED:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Attendance can only be overridden for completed classes")

        p = (
            await db.execute(
                select(OnlineClassParticipant).where(
                    OnlineClassParticipant.class_id == oc.id,
                    OnlineClassParticipant.student_id == student_id,
                )
            )
        ).scalar_one_or_none()

        new_status = OnlineAttendanceStatus(target_status)
        if p is not None:
            p.attendance_status = new_status
        else:
            # Student never entered waiting room but teacher is marking them present/excused
            p = OnlineClassParticipant(
                id=uuid.uuid4(),
                tenant_id=teacher.tenant_id,
                class_id=oc.id,
                student_id=student_id,
                waiting_since=oc.started_at or datetime.now(timezone.utc),
                joined_at=oc.started_at,
                left_at=oc.ended_at,
                duration_seconds=int((oc.ended_at - oc.started_at).total_seconds()) if oc.started_at and oc.ended_at else 0,
                attendance_status=new_status,
            )
            db.add(p)

        # Also update canonical AttendanceRecord if this class was synced
        if oc.attendance_session_id is not None:
            mapped_status = {
                OnlineAttendanceStatus.PRESENT: AttendanceStatus.PRESENT,
                OnlineAttendanceStatus.LATE: AttendanceStatus.LATE,
                OnlineAttendanceStatus.ABSENT: AttendanceStatus.ABSENT,
            }[new_status]

            record = (
                await db.execute(
                    select(AttendanceRecord).where(
                        AttendanceRecord.session_id == oc.attendance_session_id,
                        AttendanceRecord.student_id == student_id,
                    )
                )
            ).scalar_one_or_none()

            if record is not None:
                record.status = mapped_status
                if remarks:
                    record.remarks = f"{remarks} (Manually updated)"
                record.updated_by = teacher.id

        await db.flush()
        AuditService.record(
            db, actor=teacher, actor_role="TEACHER", action="OVERRIDE_ONLINE_ATTENDANCE",
            entity="OnlineClassParticipant", entity_id=p.id, tenant_id=teacher.tenant_id,
            new_value={"student_id": str(student_id), "status": target_status, "remarks": remarks},
        )
        return await OnlineClassService.attendance_report(db, teacher, class_id)

    @staticmethod
    async def export_attendance_csv(db: AsyncSession, teacher: User, class_id: uuid.UUID) -> str:
        """Generate CSV export of the attendance report."""
        report = await OnlineClassService.attendance_report(db, teacher, class_id)
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["Class Name", report.class_name])
        writer.writerow(["Subject", report.subject_name])
        writer.writerow(["Topic", report.topic])
        writer.writerow(["Started At", report.started_at.isoformat() if report.started_at else ""])
        writer.writerow(["Ended At", report.ended_at.isoformat() if report.ended_at else ""])
        writer.writerow(["Duration (min)", f"{report.duration_seconds // 60} min"])
        writer.writerow([])
        writer.writerow(["Roll Number", "Student Name", "Joined At", "Left At", "Attended (min)", "Attendance %", "Status"])

        for r in report.rows:
            writer.writerow([
                r.roll_number or "",
                r.student_name,
                r.joined_at.strftime("%H:%M:%S") if r.joined_at else "Never",
                r.left_at.strftime("%H:%M:%S") if r.left_at else "N/A",
                f"{r.duration_seconds // 60}m {r.duration_seconds % 60}s",
                f"{r.percent or 0}%",
                r.attendance_status,
            ])

        return output.getvalue()

    @staticmethod
    async def _finalize_attendance(
        db: AsyncSession, oc: OnlineClass, participants: list[OnlineClassParticipant]
    ) -> uuid.UUID | None:
        """Sync the finished live class into attendance_sessions/records."""
        current_year = await TeacherService._current_year(db, oc.tenant_id)
        if current_year is None or not oc.started_at or not oc.ended_at:
            return None
        class_seconds = int((oc.ended_at - oc.started_at).total_seconds())
        tz_name = await OnlineClassService._timezone(db, oc.tenant_id)
        try:
            tz = ZoneInfo(tz_name or "UTC")
        except (ValueError, TypeError, KeyError, ZoneInfoNotFoundError):
            tz = timezone.utc
        local_start = oc.started_at.astimezone(tz)
        local_end = oc.ended_at.astimezone(tz)

        roster = await TeacherService._roster(db, oc.tenant_id, oc.class_id)
        by_student = {p.student_id: p for p in participants}

        session = AttendanceSession(
            id=uuid.uuid4(),
            tenant_id=oc.tenant_id,
            subject_id=oc.subject_id,
            class_id=oc.class_id,
            teacher_id=oc.teacher_id,
            academic_year_id=current_year.id,
            date=local_start.date(),
            period_label=f"ONLINE {local_start.strftime('%H:%M')} #{oc.id.hex[:6]}",
            start_time=local_start.time(),
            end_time=local_end.time(),
            notes=f"Online class: {oc.topic}",
        )
        db.add(session)
        await db.flush()

        present = absent = 0
        for entry in roster:
            p = by_student.get(entry.student_id)
            seconds = p.duration_seconds if p else 0
            derived = (
                p.attendance_status
                if p is not None and p.attendance_status is not None
                else OnlineClassService._attendance_status(seconds, class_seconds)
            )
            if p is not None:
                p.attendance_status = derived
            mapped = {
                OnlineAttendanceStatus.PRESENT: AttendanceStatus.PRESENT,
                OnlineAttendanceStatus.LATE: AttendanceStatus.LATE,
                OnlineAttendanceStatus.ABSENT: AttendanceStatus.ABSENT,
            }[derived]
            if mapped is AttendanceStatus.ABSENT:
                absent += 1
            else:
                present += 1
            percent = round(seconds * 100 / class_seconds, 1) if class_seconds else 0.0
            db.add(
                AttendanceRecord(
                    id=uuid.uuid4(),
                    tenant_id=oc.tenant_id,
                    session_id=session.id,
                    student_id=entry.student_id,
                    status=mapped,
                    late_by_minutes=int((p.joined_at - oc.started_at).total_seconds() // 60)
                    if p and p.joined_at and derived is OnlineAttendanceStatus.LATE
                    else None,
                    remarks=f"Online class · {percent}% of {class_seconds // 60} min",
                    updated_by=oc.teacher_id,
                )
            )
        session.total_present = present
        session.total_absent = absent
        return session.id

    # ── Student console ───────────────────────────────────────────────────────

    @staticmethod
    async def _student_classes(db: AsyncSession, student: User) -> list[uuid.UUID]:
        """Fetch all active enrolled class IDs for this student in the current year."""
        current_year = await TeacherService._current_year(db, student.tenant_id)
        if current_year is None:
            return []
        return list(
            (
                await db.execute(
                    select(Enrollment.class_id).where(
                        Enrollment.tenant_id == student.tenant_id,
                        Enrollment.student_id == student.id,
                        Enrollment.academic_year_id == current_year.id,
                        Enrollment.status == "ACTIVE",
                    )
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    async def list_for_student(db: AsyncSession, student: User) -> StudentOnlineClassList:
        enrolled_classes = await OnlineClassService._student_classes(db, student)
        if not enrolled_classes:
            return StudentOnlineClassList(today=[], upcoming=[], past=[])
        now = _tenant_now(await OnlineClassService._timezone(db, student.tenant_id))
        rows = (
            await db.execute(
                select(OnlineClass)
                .where(
                    OnlineClass.tenant_id == student.tenant_id,
                    OnlineClass.class_id.in_(enrolled_classes),
                    OnlineClass.status != OnlineClassStatus.CANCELLED,
                )
                .order_by(OnlineClass.created_at.desc())
                .limit(100)
            )
        ).scalars().all()

        today, upcoming, past = [], [], []
        for oc in rows:
            row = await OnlineClassService._to_student_row(db, oc, student)
            if oc.status == OnlineClassStatus.LIVE:
                today.append(row)
            elif oc.status == OnlineClassStatus.SCHEDULED:
                (today if oc.scheduled_at and oc.scheduled_at.date() == now.date() else upcoming).append(row)
            else:
                past.append(row)
        return StudentOnlineClassList(today=today, upcoming=upcoming, past=past)

    @staticmethod
    async def _to_student_row(db: AsyncSession, oc: OnlineClass, student: User) -> StudentOnlineClassRow:
        base = await OnlineClassService._to_row(db, oc)
        p = (
            await db.execute(
                select(OnlineClassParticipant).where(
                    OnlineClassParticipant.class_id == oc.id, OnlineClassParticipant.student_id == student.id
                )
            )
        ).scalar_one_or_none()
        if oc.status == OnlineClassStatus.LIVE:
            if p and p.joined_at is not None and p.is_online:
                join_state = "IN_CLASS"
            elif p and p.joined_at is None:
                join_state = "WAITING"
            elif oc.allow_join:
                join_state = "JOINABLE"
            else:
                join_state = "UPCOMING"
        elif oc.status == OnlineClassStatus.SCHEDULED:
            join_state = "UPCOMING"
        else:
            join_state = "ENDED"
        return StudentOnlineClassRow(**base.model_dump(), join_state=join_state)

    @staticmethod
    async def detail_for_student(db: AsyncSession, student: User, class_id: uuid.UUID) -> OnlineClassDetail:
        oc = await OnlineClassService._get_visible_class(db, student, class_id)
        row = await OnlineClassService._to_student_row(db, oc, student)
        participants = await OnlineClassService._participant_rows(db, oc)
        return OnlineClassDetail(
            **row.model_dump(),
            roster_size=0,
            participants=[p for p in participants if p.joined_at is not None or p.student_id == student.id],
            files=await OnlineClassService._file_rows(db, oc.id),
            muted_student_ids=[],
            whiteboard_strokes=oc.whiteboard_strokes or [],
        )

    @staticmethod
    async def request_join(db: AsyncSession, student: User, class_id: uuid.UUID) -> StudentOnlineClassRow:
        oc = await OnlineClassService._get_visible_class(db, student, class_id, for_update=True)
        if oc.status != OnlineClassStatus.LIVE:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This class is not live right now")
        if not oc.allow_join:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="The teacher has not opened this class for joining")
        enrolled_classes = await OnlineClassService._student_classes(db, student)
        if oc.class_id not in enrolled_classes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You are not enrolled in this class")

        existing = (
            await db.execute(
                select(OnlineClassParticipant).where(
                    OnlineClassParticipant.class_id == oc.id, OnlineClassParticipant.student_id == student.id
                )
            )
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if existing is None:
            db.add(
                OnlineClassParticipant(
                    id=uuid.uuid4(),
                    tenant_id=oc.tenant_id,
                    class_id=oc.id,
                    student_id=student.id,
                    waiting_since=now,
                )
            )
        elif existing.joined_at is not None and not existing.is_online:
            # Rejoin after a drop — previously admitted, no waiting room again.
            OnlineClassService._admit_participant(existing)
        await db.flush()
        await live_rooms.broadcast(
            oc.id, {"type": "waiting-updated", "student_id": str(student.id), "name": student.name}
        )
        return await OnlineClassService._to_student_row(db, oc, student)

    @staticmethod
    async def leave(db: AsyncSession, student: User, class_id: uuid.UUID) -> StudentOnlineClassRow:
        oc = await OnlineClassService._get_visible_class(db, student, class_id)
        p = (
            await db.execute(
                select(OnlineClassParticipant).where(
                    OnlineClassParticipant.class_id == oc.id, OnlineClassParticipant.student_id == student.id
                )
            )
        ).scalar_one_or_none()
        if p is not None and oc.status == OnlineClassStatus.LIVE:
            OnlineClassService._record_leave(p)
            await db.flush()
        await live_rooms.broadcast(oc.id, {"type": "peer-left", "peer_id": str(student.id)})
        return await OnlineClassService._to_student_row(db, oc, student)

    # ── Chat, Whiteboard & Files ──────────────────────────────────────────────

    @staticmethod
    async def _ensure_room_member(db: AsyncSession, user: User, oc: OnlineClass) -> str:
        if user.id == oc.teacher_id:
            return "TEACHER"
        p = (
            await db.execute(
                select(OnlineClassParticipant).where(
                    OnlineClassParticipant.class_id == oc.id, OnlineClassParticipant.student_id == user.id
                )
            )
        ).scalar_one_or_none()
        if p is None or p.joined_at is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Join the class before participating")
        return "STUDENT"

    @staticmethod
    async def messages(
        db: AsyncSession, user: User, class_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> list[OnlineMessageRow]:
        oc = await OnlineClassService._get_visible_class(db, user, class_id)
        await OnlineClassService._ensure_room_member(db, user, oc)
        rows = (
            await db.execute(
                select(OnlineClassMessage, User.name)
                .join(User, User.id == OnlineClassMessage.sender_id)
                .where(OnlineClassMessage.class_id == class_id)
                .order_by(OnlineClassMessage.created_at.desc())
                .limit(min(limit, 200))
                .offset(offset)
            )
        ).all()
        return [
            OnlineMessageRow(
                id=m.id, sender_id=m.sender_id, sender_name=name, sender_role=m.sender_role,
                body=m.body, created_at=m.created_at,
            )
            for m, name in reversed(rows)
        ]

    @staticmethod
    async def post_message(db: AsyncSession, user: User, oc: OnlineClass, body: str) -> OnlineMessageRow:
        role = await OnlineClassService._ensure_room_member(db, user, oc)
        if role == "STUDENT" and await OnlineClassService.is_student_muted(db, oc.id, user.id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You have been muted by the teacher in this class")

        m = OnlineClassMessage(
            id=uuid.uuid4(),
            tenant_id=oc.tenant_id,
            class_id=oc.id,
            sender_id=user.id,
            sender_role=role,
            body=body.strip()[:1000],
        )
        db.add(m)
        await db.flush()
        return OnlineMessageRow(
            id=m.id, sender_id=user.id, sender_name=user.name, sender_role=role, body=m.body, created_at=m.created_at
        )

    @staticmethod
    async def save_whiteboard_stroke(db: AsyncSession, oc_id: uuid.UUID, stroke_data: dict[str, Any]) -> None:
        """Store whiteboard stroke data up to max capacity."""
        oc = await db.get(OnlineClass, oc_id)
        if oc is not None:
            strokes = list(oc.whiteboard_strokes or [])
            strokes.append(stroke_data)
            if len(strokes) > MAX_WHITEBOARD_STROKES:
                strokes = strokes[-MAX_WHITEBOARD_STROKES:]
            oc.whiteboard_strokes = strokes
            await db.flush()

    @staticmethod
    async def files(db: AsyncSession, user: User, class_id: uuid.UUID) -> list[OnlineFileRow]:
        oc = await OnlineClassService._get_visible_class(db, user, class_id)
        await OnlineClassService._ensure_room_member(db, user, oc)
        return await OnlineClassService._file_rows(db, class_id)

    @staticmethod
    async def add_file(
        db: AsyncSession,
        user: User,
        oc: OnlineClass,
        filename: str,
        content: bytes | UploadFile,
        mime_type: str,
        role: str = "TEACHER",
    ) -> OnlineFileRow:
        """Share one file into the class room.

        Storage is delegated to the platform storage service (B6): magic-byte
        validation, a tenant-prefixed key, and a short-lived signed download
        URL.
        """
        settings = get_settings()
        if oc.status not in (OnlineClassStatus.LIVE, OnlineClassStatus.COMPLETED):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Files can be shared once the class has started")

        clean_mime = (mime_type or "application/octet-stream").lower().split(";")[0].strip()
        if clean_mime not in settings.allowed_mime_set and clean_mime != "application/octet-stream":
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported or disallowed file type for classroom sharing",
            )

        stored = await storage.save(
            oc.tenant_id,
            f"online-classes/{oc.id}",
            filename,
            content,
            clean_mime,
            max_bytes=settings.ONLINE_CLASS_UPLOAD_MAX_MB * 1024 * 1024,
        )

        file_entry = OnlineClassFile(
            id=uuid.uuid4(),
            tenant_id=oc.tenant_id,
            class_id=oc.id,
            uploader_id=user.id,
            uploader_role=role,
            file_name=re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:200] or "file",
            file_path=stored.key,
            file_size_bytes=stored.size,
            mime_type=stored.mime[:100],
        )
        db.add(file_entry)
        await db.flush()
        row = (await OnlineClassService._file_rows(db, oc.id))[-1]
        await live_rooms.broadcast(oc.id, {"type": "file-shared", "file": row.model_dump(mode="json")})
        return row

    @staticmethod
    async def delete_file(
        db: AsyncSession, teacher: User, class_id: uuid.UUID, file_id: uuid.UUID
    ) -> list[OnlineFileRow]:
        oc = await OnlineClassService._get_owned_class(db, teacher, class_id)
        file_obj = (
            await db.execute(
                select(OnlineClassFile).where(
                    OnlineClassFile.id == file_id,
                    OnlineClassFile.class_id == oc.id,
                )
            )
        ).scalar_one_or_none()
        if file_obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")

        # Remove the stored object (local disk or S3); legacy rows stored a
        # bare name that only resolves with the class namespace attached.
        key = (
            file_obj.file_path
            if "/" in file_obj.file_path
            else f"online-classes/{class_id}/{file_obj.file_path}"
        )
        storage.delete(key)

        await db.delete(file_obj)
        await db.flush()
        return await OnlineClassService._file_rows(db, oc.id)

    @staticmethod
    async def save_recording(
        db: AsyncSession, user: User, oc: OnlineClass, filename: str, content: bytes, mime_type: str
    ) -> OnlineClassRow:
        if user.id != oc.teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the class teacher can save a recording")
        await OnlineClassService.add_file(db, user, oc, filename, content, mime_type, role="TEACHER")
        # Persist the storage KEY (stable forever); a signed URL would expire
        # in the database. Serialization signs it fresh on every response.
        entry = (
            await db.execute(
                select(OnlineClassFile)
                .where(OnlineClassFile.class_id == oc.id)
                .order_by(OnlineClassFile.created_at.desc())
                .limit(1)
            )
        ).scalar_one()
        oc.recording_url = entry.file_path
        await db.flush()
        return await OnlineClassService._to_row(db, oc)

    # ── Student Notification Inbox ────────────────────────────────────────────
    # These used to re-implement the inbox queries locally. The platform-wide
    # notification service (app/services/notification_service.py) is now the
    # single owner of inbox + push logic; these methods stay only as the
    # legacy entry points used by the /online-classes/my/notifications routes
    # and delegate unchanged semantics.

    @staticmethod
    async def list_notifications(
        db: AsyncSession,
        user: User,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False,
    ) -> NotificationPage:
        return await NotificationService.list_inbox(db, user.id, limit=limit, offset=offset, unread_only=unread_only)

    @staticmethod
    async def mark_notification_read(db: AsyncSession, user: User, notif_id: uuid.UUID) -> NotificationRow:
        return await NotificationService.mark_read(db, user.id, notif_id)

    @staticmethod
    async def mark_all_notifications_read(db: AsyncSession, user: User) -> int:
        return await NotificationService.mark_all_read(db, user.id)

    # ── Admin & Principal Monitoring ──────────────────────────────────────────

    @staticmethod
    async def list_for_admin(
        db: AsyncSession,
        user: User,
        department_id: uuid.UUID | None = None,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> OnlineClassAdminPage:
        TeacherService._validate_page(limit, offset)
        base = (
            select(
                OnlineClass,
                SchoolClass.name.label("class_name"),
                Department.name.label("department_name"),
                Subject.code.label("subject_code"),
                Subject.name.label("subject_name"),
                User.name.label("teacher_name"),
                func.count(OnlineClassParticipant.id).filter(OnlineClassParticipant.joined_at.is_not(None)).label("participant_count"),
            )
            .join(SchoolClass, SchoolClass.id == OnlineClass.class_id)
            .outerjoin(Department, Department.id == SchoolClass.department_id)
            .join(Subject, Subject.id == OnlineClass.subject_id)
            .join(User, User.id == OnlineClass.teacher_id)
            .outerjoin(OnlineClassParticipant, OnlineClassParticipant.class_id == OnlineClass.id)
            .where(OnlineClass.tenant_id == user.tenant_id)
            .group_by(OnlineClass.id, SchoolClass.name, Department.name, Subject.code, Subject.name, User.name)
        )

        if department_id:
            base = base.where(SchoolClass.department_id == department_id)
        if status_filter:
            try:
                base = base.where(OnlineClass.status == OnlineClassStatus(status_filter.upper()))
            except ValueError:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown status filter")

        total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = (
            await db.execute(
                base.order_by(OnlineClass.created_at.desc()).limit(limit).offset(offset)
            )
        ).all()

        today = await PrincipalService._tenant_today(db, user.tenant_id)

        # Summary KPIs
        live_count = (
            await db.execute(
                select(func.count(OnlineClass.id)).where(
                    OnlineClass.tenant_id == user.tenant_id,
                    OnlineClass.status == OnlineClassStatus.LIVE,
                )
            )
        ).scalar_one()

        scheduled_today = (
            await db.execute(
                select(func.count(OnlineClass.id)).where(
                    OnlineClass.tenant_id == user.tenant_id,
                    OnlineClass.status == OnlineClassStatus.SCHEDULED,
                    func.date(OnlineClass.scheduled_at) == today,
                )
            )
        ).scalar_one()

        completed_today = (
            await db.execute(
                select(func.count(OnlineClass.id)).where(
                    OnlineClass.tenant_id == user.tenant_id,
                    OnlineClass.status == OnlineClassStatus.COMPLETED,
                    func.date(OnlineClass.ended_at) == today,
                )
            )
        ).scalar_one()

        active_participants_now = (
            await db.execute(
                select(func.count(OnlineClassParticipant.id)).where(
                    OnlineClassParticipant.tenant_id == user.tenant_id,
                    OnlineClassParticipant.is_online.is_(True),
                )
            )
        ).scalar_one()

        items = [
            OnlineClassAdminRow(
                id=oc.id,
                class_id=oc.class_id,
                class_name=class_name,
                department_name=dept_name,
                subject_id=oc.subject_id,
                subject_code=subject_code,
                subject_name=subject_name,
                teacher_id=oc.teacher_id,
                teacher_name=teacher_name,
                topic=oc.topic,
                mode=oc.mode.value,
                status=oc.status.value,
                scheduled_at=oc.scheduled_at,
                duration_minutes=oc.duration_minutes,
                allow_join=oc.allow_join,
                recording_enabled=oc.recording_enabled,
                recording_url=OnlineClassService._recording_url(oc),
                started_at=oc.started_at,
                ended_at=oc.ended_at,
                created_at=oc.created_at,
                participant_count=p_count,
                active_participants=(await live_rooms.active_count(oc.id)) if oc.status == OnlineClassStatus.LIVE else 0,
            )
            for oc, class_name, dept_name, subject_code, subject_name, teacher_name, p_count in rows
        ]

        return OnlineClassAdminPage(
            summary=OnlineClassAdminSummary(
                live_count=live_count,
                scheduled_today_count=scheduled_today,
                completed_today_count=completed_today,
                total_participants_now=active_participants_now,
            ),
            total=total,
            limit=limit,
            offset=offset,
            items=items,
        )

    # ── WebSocket lifecycle hooks ─────────────────────────────────────────────

    @staticmethod
    async def _participant(db: AsyncSession, oc: OnlineClass, student: User) -> OnlineClassParticipant | None:
        return (
            await db.execute(
                select(OnlineClassParticipant).where(
                    OnlineClassParticipant.class_id == oc.id, OnlineClassParticipant.student_id == student.id
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def ws_student_joined(db: AsyncSession, oc: OnlineClass, student: User) -> None:
        """Mark an admitted student online when their live socket connects."""
        p = await OnlineClassService._participant(db, oc, student)
        if p is not None and p.joined_at is not None:
            p.is_online = True
            p.waiting_since = datetime.now(timezone.utc)  # current segment start
            await db.flush()

    @staticmethod
    async def ws_student_left(db: AsyncSession, oc: OnlineClass, student: User) -> None:
        p = await OnlineClassService._participant(db, oc, student)
        if p is not None and oc.status == OnlineClassStatus.LIVE:
            OnlineClassService._record_leave(p)
            await db.flush()
