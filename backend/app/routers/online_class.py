"""Online Class API — schedule or start live classes, join, auto-attendance.

Teacher endpoints live under the teaching scope; student endpoints are scoped
to the caller's active enrollment. The WebSocket carries the live classroom:
presence, chat, raise-hand, WebRTC signalling, whiteboard strokes, heartbeats.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Annotated

import anyio
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies.auth import (
    get_current_tenant_user,
    get_current_tenant_user_admin,
    get_current_tenant_user_hod,
    get_current_tenant_user_principal,
    get_current_tenant_user_student,
    get_current_tenant_user_teacher,
)
from app.models.online_class import OnlineClass, OnlineClassStatus
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.online_class import (
    APIResponseNotification,
    APIResponseNotificationPage,
    APIResponseOnlineAttendanceReport,
    APIResponseOnlineClass,
    APIResponseOnlineClassAdminPage,
    APIResponseOnlineClassDetail,
    APIResponseOnlineClassPage,
    APIResponseOnlineClassSetupOptions,
    APIResponseOnlineFile,
    APIResponseOnlineFiles,
    APIResponseOnlineMessages,
    APIResponseStudentOnlineClasses,
    AttendanceOverrideIn,
    OnlineClassCreate,
    OnlineClassUpdate,
    StudentOnlineClassRow,
)
from app.services.jwt_service import decode_access_token
from app.services.online_class_service import OnlineClassService, live_rooms

router = APIRouter(prefix="/online-classes", tags=["Online Classes"])

DB = Annotated[AsyncSession, Depends(get_db)]
Teacher = Annotated[User, Depends(get_current_tenant_user_teacher)]
Student = Annotated[User, Depends(get_current_tenant_user_student)]
AnyTenantUser = Annotated[User, Depends(get_current_tenant_user)]



# ── Static / Fixed paths (MUST COME BEFORE parameterized /{class_id}) ─────────


@router.get("/setup-options", response_model=APIResponseOnlineClassSetupOptions)
async def setup_options(db: DB, teacher: Teacher):
    return APIResponse(
        success=True, data=await OnlineClassService.setup_options(db, teacher), message="Setup options loaded"
    )


@router.get("/my/classes", response_model=APIResponseStudentOnlineClasses)
async def my_classes(db: DB, student: Student):
    return APIResponse(
        success=True, data=await OnlineClassService.list_for_student(db, student), message="Online classes loaded"
    )


@router.get("/my/notifications", response_model=APIResponseNotificationPage)
async def my_notifications(
    db: DB,
    student: Student,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    unread_only: bool = Query(default=False),
):
    return APIResponse(
        success=True,
        data=await OnlineClassService.list_notifications(db, student, limit, offset, unread_only),
        message="Notifications loaded",
    )


@router.post("/my/notifications/read-all", response_model=APIResponse[dict])
async def mark_all_notifications_read(db: DB, student: Student):
    count = await OnlineClassService.mark_all_notifications_read(db, student)
    return APIResponse(success=True, data={"updated_count": count}, message=f"Marked {count} notifications as read")


@router.patch("/my/notifications/{notif_id}/read", response_model=APIResponseNotification)
async def mark_notification_read(notif_id: uuid.UUID, db: DB, student: Student):
    return APIResponse(
        success=True,
        data=await OnlineClassService.mark_notification_read(db, student, notif_id),
        message="Notification marked read",
    )


@router.get("/admin/overview", response_model=APIResponseOnlineClassAdminPage)
async def admin_classes_overview(
    db: DB,
    user: AnyTenantUser,
    department_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Institutional overview for Principal, Vice Principal, HOD, and Institution Admins."""
    return APIResponse(
        success=True,
        data=await OnlineClassService.list_for_admin(db, user, department_id, status_filter, limit, offset),
        message="Online classes overview loaded",
    )


# ── Teacher: schedule, start & query ──────────────────────────────────────────


@router.post("", response_model=APIResponseOnlineClass, status_code=status.HTTP_201_CREATED)
async def schedule_class(payload: OnlineClassCreate, db: DB, teacher: Teacher):
    return APIResponse(
        success=True,
        data=await OnlineClassService.create_scheduled(db, teacher, payload),
        message="Online class scheduled",
    )


@router.post("/instant", response_model=APIResponseOnlineClass, status_code=status.HTTP_201_CREATED)
async def start_instant_class(payload: OnlineClassCreate, db: DB, teacher: Teacher):
    return APIResponse(
        success=True,
        data=await OnlineClassService.create_instant(db, teacher, payload),
        message="Class is live — students notified",
    )


@router.get("", response_model=APIResponseOnlineClassPage)
async def teacher_classes(
    db: DB,
    teacher: Teacher,
    status_filter: str | None = Query(default=None, alias="status"),
    subject_id: uuid.UUID | None = Query(default=None),
    class_id: uuid.UUID | None = Query(default=None),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await OnlineClassService.list_for_teacher(
            db, teacher, status_filter, subject_id, class_id, from_date, to_date, search, limit, offset
        ),
        message="Online classes loaded",
    )


# ── Parameterized endpoints: /{class_id} ──────────────────────────────────────


@router.get("/{class_id}", response_model=APIResponseOnlineClassDetail)
async def class_detail(class_id: uuid.UUID, db: DB, teacher: Teacher):
    return APIResponse(
        success=True, data=await OnlineClassService.detail_for_teacher(db, teacher, class_id), message="Class loaded"
    )


@router.post("/{class_id}/start", response_model=APIResponseOnlineClass)
async def start_class(class_id: uuid.UUID, db: DB, teacher: Teacher):
    return APIResponse(success=True, data=await OnlineClassService.start(db, teacher, class_id), message="Class is live")


@router.patch("/{class_id}", response_model=APIResponseOnlineClass)
async def update_class(class_id: uuid.UUID, payload: OnlineClassUpdate, db: DB, teacher: Teacher):
    return APIResponse(
        success=True, data=await OnlineClassService.update(db, teacher, class_id, payload), message="Class updated"
    )


@router.post("/{class_id}/cancel", response_model=APIResponseOnlineClass)
async def cancel_class(class_id: uuid.UUID, db: DB, teacher: Teacher):
    return APIResponse(success=True, data=await OnlineClassService.cancel(db, teacher, class_id), message="Class cancelled")


@router.post("/{class_id}/end", response_model=APIResponseOnlineAttendanceReport)
async def end_class(class_id: uuid.UUID, db: DB, teacher: Teacher):
    return APIResponse(
        success=True,
        data=await OnlineClassService.end(db, teacher, class_id),
        message="Class ended — attendance generated",
    )


# ── Teacher: waiting room, mute & participants ────────────────────────────────


@router.post("/{class_id}/admit-all", response_model=APIResponseOnlineClassDetail)
async def admit_all(class_id: uuid.UUID, db: DB, teacher: Teacher):
    return APIResponse(
        success=True, data=await OnlineClassService.admit_all(db, teacher, class_id), message="Everyone admitted"
    )


@router.post("/{class_id}/participants/{student_id}/admit", response_model=APIResponseOnlineClassDetail)
async def admit_student(class_id: uuid.UUID, student_id: uuid.UUID, db: DB, teacher: Teacher):
    return APIResponse(
        success=True,
        data=await OnlineClassService.admit(db, teacher, class_id, student_id),
        message="Student admitted",
    )


@router.post("/{class_id}/participants/{student_id}/remove", response_model=APIResponseOnlineClassDetail)
async def remove_student(class_id: uuid.UUID, student_id: uuid.UUID, db: DB, teacher: Teacher):
    return APIResponse(
        success=True,
        data=await OnlineClassService.remove_student(db, teacher, class_id, student_id),
        message="Student removed from class",
    )


@router.post("/{class_id}/participants/{student_id}/mute", response_model=APIResponseOnlineClassDetail)
async def mute_student(class_id: uuid.UUID, student_id: uuid.UUID, db: DB, teacher: Teacher):
    return APIResponse(
        success=True,
        data=await OnlineClassService.mute_student(db, teacher, class_id, student_id),
        message="Student chat muted",
    )


@router.delete("/{class_id}/participants/{student_id}/mute", response_model=APIResponseOnlineClassDetail)
async def unmute_student(class_id: uuid.UUID, student_id: uuid.UUID, db: DB, teacher: Teacher):
    return APIResponse(
        success=True,
        data=await OnlineClassService.unmute_student(db, teacher, class_id, student_id),
        message="Student chat unmuted",
    )


# ── Teacher: attendance & files ───────────────────────────────────────────────


@router.get("/{class_id}/attendance", response_model=APIResponseOnlineAttendanceReport)
async def attendance_report(class_id: uuid.UUID, db: DB, teacher: Teacher):
    return APIResponse(
        success=True,
        data=await OnlineClassService.attendance_report(db, teacher, class_id),
        message="Attendance report loaded",
    )


@router.post("/{class_id}/attendance/override/{student_id}", response_model=APIResponseOnlineAttendanceReport)
async def override_attendance(
    class_id: uuid.UUID,
    student_id: uuid.UUID,
    payload: AttendanceOverrideIn,
    db: DB,
    teacher: Teacher,
):
    return APIResponse(
        success=True,
        data=await OnlineClassService.override_attendance(
            db, teacher, class_id, student_id, payload.attendance_status, payload.remarks
        ),
        message="Attendance overridden successfully",
    )


@router.get("/{class_id}/attendance/export")
async def export_attendance_csv(class_id: uuid.UUID, db: DB, teacher: Teacher):
    csv_content = await OnlineClassService.export_attendance_csv(db, teacher, class_id)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="attendance_{class_id.hex[:8]}.csv"'},
    )


@router.post("/{class_id}/files", response_model=APIResponseOnlineFile, status_code=status.HTTP_201_CREATED)
async def share_file(class_id: uuid.UUID, db: DB, teacher: Teacher, file: UploadFile = File(...)):
    oc = await OnlineClassService._get_owned_class(db, teacher, class_id)
    row = await OnlineClassService.add_file(
        db, teacher, oc, file.filename or "file", file, file.content_type or "", role="TEACHER"
    )
    return APIResponse(success=True, data=row, message="File shared with the class")


@router.delete("/{class_id}/files/{file_id}", response_model=APIResponseOnlineFiles)
async def delete_file(class_id: uuid.UUID, file_id: uuid.UUID, db: DB, teacher: Teacher):
    files = await OnlineClassService.delete_file(db, teacher, class_id, file_id)
    return APIResponse(success=True, data=files, message="File deleted")


@router.post("/{class_id}/recording", response_model=APIResponseOnlineClass, status_code=status.HTTP_201_CREATED)
async def save_recording(class_id: uuid.UUID, db: DB, teacher: Teacher, file: UploadFile = File(...)):
    oc = await OnlineClassService._get_owned_class(db, teacher, class_id)
    row = await OnlineClassService.save_recording(
        db, teacher, oc, file.filename or "recording.webm", file, file.content_type or "video/webm"
    )
    return APIResponse(success=True, data=row, message="Recording saved")


# ── Student views & actions ───────────────────────────────────────────────────


@router.get("/{class_id}/student-view", response_model=APIResponseOnlineClassDetail)
async def student_class_detail(class_id: uuid.UUID, db: DB, student: Student):
    return APIResponse(
        success=True,
        data=await OnlineClassService.detail_for_student(db, student, class_id),
        message="Class loaded",
    )


@router.post("/{class_id}/join", response_model=APIResponse[StudentOnlineClassRow])
async def join_class(class_id: uuid.UUID, db: DB, student: Student):
    return APIResponse(
        success=True, data=await OnlineClassService.request_join(db, student, class_id), message="You are in the waiting room"
    )


@router.post("/{class_id}/leave", response_model=APIResponse[StudentOnlineClassRow])
async def leave_class(class_id: uuid.UUID, db: DB, student: Student):
    return APIResponse(success=True, data=await OnlineClassService.leave(db, student, class_id), message="You left the class")


@router.post("/{class_id}/files/student", response_model=APIResponseOnlineFile, status_code=status.HTTP_201_CREATED)
async def student_share_file(class_id: uuid.UUID, db: DB, student: Student, file: UploadFile = File(...)):
    oc = await OnlineClassService._get_visible_class(db, student, class_id)
    row = await OnlineClassService.add_file(
        db, student, oc, file.filename or "student_upload", file, file.content_type or "", role="STUDENT"
    )
    return APIResponse(success=True, data=row, message="File uploaded")


@router.get("/{class_id}/messages", response_model=APIResponseOnlineMessages)
async def chat_history(
    class_id: uuid.UUID,
    db: DB,
    teacher: Teacher,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True, data=await OnlineClassService.messages(db, teacher, class_id, limit, offset), message="Chat loaded"
    )


@router.get("/{class_id}/student/messages", response_model=APIResponseOnlineMessages)
async def student_chat_history(
    class_id: uuid.UUID,
    db: DB,
    student: Student,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True, data=await OnlineClassService.messages(db, student, class_id, limit, offset), message="Chat loaded"
    )


@router.get("/{class_id}/student/files", response_model=APIResponseOnlineFiles)
async def student_files(class_id: uuid.UUID, db: DB, student: Student):
    return APIResponse(success=True, data=await OnlineClassService.files(db, student, class_id), message="Materials loaded")


# ── Live classroom WebSocket ──────────────────────────────────────────────────


async def _send_roster(websocket: WebSocket, db: AsyncSession, oc: OnlineClass) -> None:
    rows = await OnlineClassService._participant_rows(db, oc)
    await websocket.send_json({"type": "roster", "participants": [r.model_dump(mode="json") for r in rows]})


@router.websocket("/{class_id}/live")
async def live_room(websocket: WebSocket, class_id: uuid.UUID, db: DB, token: str = Query(...)):
    """Presence + chat + raise-hand + WebRTC signalling + whiteboard relay + heartbeat.

    Browsers cannot set headers on a WebSocket handshake, so the short-lived
    tenant JWT travels in the query string and is validated before accept().
    The injected session lives for the whole connection; every persisted
    event commits immediately so a mid-class crash loses nothing.
    """
    user: User | None = None
    oc: OnlineClass | None = None
    role = ""
    try:
        try:
            payload = decode_access_token(token)
        except JWTError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if payload.get("type") != "tenant" or not payload.get("sub") or not payload.get("tenant_id"):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        try:
            user_pk = uuid.UUID(str(payload["sub"]))
        except ValueError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        user = await db.get(User, user_pk)
        oc = await db.get(OnlineClass, class_id)
        if user is None or not user.is_active or oc is None or oc.tenant_id != user.tenant_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        role = "TEACHER" if user.id == oc.teacher_id else "STUDENT"
        if role == "STUDENT":
            participant = await OnlineClassService._participant(db, oc, user)
            if oc.status != OnlineClassStatus.LIVE or participant is None or participant.joined_at is None:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

        await websocket.accept()
        await live_rooms.register(class_id, user.id, websocket, user.name, role)
        if role == "STUDENT":
            await OnlineClassService.ws_student_joined(db, oc, user)
        await db.commit()

        # Send welcome payload with whiteboard state for replay
        await websocket.send_json(
            {
                "type": "welcome",
                "you": {"id": str(user.id), "name": user.name, "role": role},
                "peers": await live_rooms.online_peers(class_id, exclude=user.id),
                # ICE config for this deployment; the client keeps its STUN
                # fallback when TURN is not configured server-side.
                "ice_servers": get_settings().ice_servers(),
                "sfu": {
                    "enabled": get_settings().SFU_ENABLED,
                    "url": get_settings().SFU_URL,
                },
                "whiteboard": oc.whiteboard_strokes or [],
            }
        )
        await live_rooms.broadcast(
            class_id,
            {"type": "peer-joined", "peer": {"id": str(user.id), "name": user.name, "role": role}},
            exclude=user.id,
        )

        while True:
            raw = await websocket.receive_text()
            if len(raw) > 128 * 1024:
                continue  # oversized frame — ignore
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")

            if kind == "ping":
                # Heartbeat ping / pong to keep proxies alive
                await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
            elif kind == "chat":
                body = str(msg.get("body", "")).strip()[:1000]
                if body and oc.status == OnlineClassStatus.LIVE:
                    if role == "STUDENT" and await OnlineClassService.is_student_muted(db, oc.id, user.id):
                        await websocket.send_json({"type": "error", "message": "You are muted in this class"})
                        continue
                    row = await OnlineClassService.post_message(db, user, oc, body)
                    await db.commit()
                    await live_rooms.broadcast(class_id, {"type": "chat", "message": row.model_dump(mode="json")})
            elif kind == "hand" and role == "STUDENT":
                participant = await OnlineClassService._participant(db, oc, user)
                if participant is not None:
                    participant.hand_raised_at = datetime.now(timezone.utc) if msg.get("raised") else None
                    await db.commit()
                await live_rooms.broadcast(
                    class_id, {"type": "hand", "student_id": str(user.id), "raised": bool(msg.get("raised"))}
                )
            elif kind == "signal":
                try:
                    target_id = uuid.UUID(str(msg.get("to")))
                except (ValueError, TypeError):
                    continue
                await live_rooms.send_to(
                    class_id, target_id, {"type": "signal", "from": str(user.id), "data": msg.get("data")}
                )
            elif kind == "whiteboard":
                stroke = msg.get("stroke")
                if stroke and isinstance(stroke, dict):
                    await OnlineClassService.save_whiteboard_stroke(db, oc.id, stroke)
                    await db.commit()
                await live_rooms.broadcast(
                    class_id,
                    {"type": "whiteboard", "from": str(user.id), "stroke": stroke},
                    exclude=user.id,
                )
            elif kind == "screen":
                await live_rooms.broadcast(
                    class_id, {"type": "screen", "from": str(user.id), "sharing": bool(msg.get("sharing"))}
                )
            elif kind == "roster-request" and role == "TEACHER":
                await _send_roster(websocket, db, oc)
    except WebSocketDisconnect:
        pass
    except Exception:
        await db.rollback()
    finally:
        if user is not None:
            await live_rooms.unregister(class_id, user.id)
            with anyio.CancelScope(shield=True):
                try:
                    if role == "STUDENT" and oc is not None and oc.status == OnlineClassStatus.LIVE:
                        await OnlineClassService.ws_student_left(db, oc, user)
                        await db.commit()
                    await live_rooms.broadcast(class_id, {"type": "peer-left", "peer_id": str(user.id)})
                except Exception:
                    with contextlib.suppress(Exception):
                        await db.rollback()
