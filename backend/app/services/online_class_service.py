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
    """Hub for live classroom WebSockets supporting multi-worker via Redis pub/sub.

    Maintains local WebSocket connections per worker process and syncs
    broadcast events across instances via Redis channels when available.
    """

    def __init__(self) -> None:
        # class_id → user_id → {"ws": WebSocket, "name": str, "role": str}
        self.rooms: dict[uuid.UUID, dict[uuid.UUID, dict]] = {}
        self._redis = None
        self._pubsub_task: asyncio.Task | None = None

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

    def active_count(self, class_id: uuid.UUID) -> int:
        return len(self.rooms.get(class_id, {}))

    def online_peers(self, class_id: uuid.UUID, exclude: uuid.UUID | None = None) -> list[dict]:
        return [
            {"id": str(user_id), "name": info["name"], "role": info["role"]}
            for user_id, info in self.rooms.get(class_id, {}).items()
            if user_id != exclude
        ]

    async def broadcast(self, class_id: uuid.UUID, payload: dict, exclude: uuid.UUID | None = None) -> None:
        """Broadcast payload to all connected peers in the room on this worker."""
        for user_id, info in list(self.rooms.get(class_id, {}).items()):
            if user_id == exclude:
                continue
            try:
                await info["ws"].send_json(payload)
            except Exception:
                pass  # half-closed socket; disconnect handler cleans up

    async def send_to(self, class_id: uuid.UUID, user_id: uuid.UUID, payload: dict) -> None:
        info = self.rooms.get(class_id, {}).get(user_id)
        if info is not None:
            try:
                await info["ws"].send_json(payload)
            except Exception:
                pass


live_rooms = LiveRoomManager()


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
            recording_url=oc.recording_url,
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
                url=f"/uploads/online-classes/{class_id}/{f.file_path}",
                file_size_bytes=f.file_size_bytes,
                mime_type=f.mime_type,
                created_at=f.created_at,
            )
            for f, name in rows
        ]

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
                recording_url=oc.recording_url,
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
        uploads_root: Path,
        role: str = "TEACHER",
    ) -> OnlineFileRow:
        settings = get_settings()
        if oc.status not in (OnlineClassStatus.LIVE, OnlineClassStatus.COMPLETED):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Files can be shared once the class has started")

        max_bytes = settings.ONLINE_CLASS_UPLOAD_MAX_MB * 1024 * 1024

        # Validate MIME type against configured safe allowlist
        clean_mime = (mime_type or "application/octet-stream").lower().split(";")[0].strip()
        if clean_mime not in settings.allowed_mime_set and clean_mime != "application/octet-stream":
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported or disallowed file type for classroom sharing",
            )

        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:200] or "file"
        stored_name = f"{uuid.uuid4().hex}_{safe_name}"
        target_dir = uploads_root / "online-classes" / str(oc.id)
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / stored_name

        if hasattr(content, "read"):
            total_size = 0
            with dest.open("wb") as out:
                while chunk := await content.read(64 * 1024):
                    total_size += len(chunk)
                    if total_size > max_bytes:
                        dest.unlink(missing_ok=True)
                        raise HTTPException(
                            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"File exceeds the {settings.ONLINE_CLASS_UPLOAD_MAX_MB} MB limit",
                        )
                    out.write(chunk)
            file_size = total_size
        else:
            if len(content) > max_bytes:
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds the {settings.ONLINE_CLASS_UPLOAD_MAX_MB} MB limit",
                )
            dest.write_bytes(content)
            file_size = len(content)

        file_entry = OnlineClassFile(
            id=uuid.uuid4(),
            tenant_id=oc.tenant_id,
            class_id=oc.id,
            uploader_id=user.id,
            uploader_role=role,
            file_name=safe_name,
            file_path=stored_name,
            file_size_bytes=file_size,
            mime_type=clean_mime[:100],
        )
        db.add(file_entry)
        await db.flush()
        row = (await OnlineClassService._file_rows(db, oc.id))[-1]
        await live_rooms.broadcast(oc.id, {"type": "file-shared", "file": row.model_dump(mode="json")})
        return row

    @staticmethod
    async def delete_file(
        db: AsyncSession, teacher: User, class_id: uuid.UUID, file_id: uuid.UUID, uploads_root: Path
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

        # Delete local file from disk if present
        try:
            target = uploads_root / "online-classes" / str(oc.id) / file_obj.file_path
            if target.exists():
                target.unlink()
        except Exception as e:
            logger.warning("Could not unlink physical file: %s", e)

        await db.delete(file_obj)
        await db.flush()
        return await OnlineClassService._file_rows(db, oc.id)

    @staticmethod
    async def save_recording(
        db: AsyncSession, user: User, oc: OnlineClass, filename: str, content: bytes, mime_type: str, uploads_root: Path
    ) -> OnlineClassRow:
        if user.id != oc.teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the class teacher can save a recording")
        row = await OnlineClassService.add_file(db, user, oc, filename, content, mime_type, uploads_root, role="TEACHER")
        oc.recording_url = row.url
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
                recording_url=oc.recording_url,
                started_at=oc.started_at,
                ended_at=oc.ended_at,
                created_at=oc.created_at,
                participant_count=p_count,
                active_participants=live_rooms.active_count(oc.id) if oc.status == OnlineClassStatus.LIVE else 0,
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
