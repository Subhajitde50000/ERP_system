"""Mentor console API — mounted under ``/api/v1/mentor``.

Every handler requires a live MENTOR role; the service then derives the
caller's reach from their active mentor assignments (students, project teams,
classes).  Route ids alone never widen access beyond that derived scope.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_tenant_user_mentor
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.mentor import (
    APIResponseMentorClasses,
    APIResponseMentorDashboard,
    APIResponseMentorMentee,
    APIResponseMentorMentees,
    APIResponseMentorNote,
    APIResponseMentorNotes,
    APIResponseMentorNotice,
    APIResponseMentorNotices,
    APIResponseMentorTeam,
    APIResponseMentorTeams,
    MentorNoteCreate,
    MentorNoteUpdate,
    MentorScope,
)
from app.services.mentor_service import MentorService

router = APIRouter(prefix="/mentor", tags=["Mentor"])

DB = Annotated[AsyncSession, Depends(get_db)]
Mentor = Annotated[User, Depends(get_current_tenant_user_mentor)]


@router.get("/dashboard", response_model=APIResponseMentorDashboard)
async def dashboard(db: DB, mentor: Mentor):
    return APIResponse(success=True, data=await MentorService.dashboard(db, mentor), message="Mentor dashboard loaded")


@router.get("/mentees", response_model=APIResponseMentorMentees)
async def mentees(
    db: DB,
    mentor: Mentor,
    q: Annotated[str | None, Query(max_length=120)] = None,
    class_id: uuid.UUID | None = None,
    scope: MentorScope | None = None,
    at_risk: bool = False,
):
    data = await MentorService.mentees(db, mentor, query=q, class_id=class_id, scope=scope, at_risk_only=at_risk)
    return APIResponse(success=True, data=data, message="Mentees loaded")


@router.get("/mentees/{student_id}", response_model=APIResponseMentorMentee)
async def mentee_detail(student_id: uuid.UUID, db: DB, mentor: Mentor):
    return APIResponse(success=True, data=await MentorService.mentee_detail(db, mentor, student_id), message="Mentee loaded")


@router.post("/mentees/{student_id}/notes", response_model=APIResponseMentorNote, status_code=status.HTTP_201_CREATED)
async def create_note(student_id: uuid.UUID, payload: MentorNoteCreate, db: DB, mentor: Mentor):
    return APIResponse(success=True, data=await MentorService.create_note(db, mentor, student_id, payload), message="Note saved")


@router.get("/notes", response_model=APIResponseMentorNotes)
async def notes(
    db: DB,
    mentor: Mentor,
    student_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: int = 20,
    offset: int = 0,
):
    data = await MentorService.notes(db, mentor, student_id=student_id, query=q, limit=limit, offset=offset)
    return APIResponse(success=True, data=data, message="Notes loaded")


@router.patch("/notes/{note_id}", response_model=APIResponseMentorNote)
async def update_note(note_id: uuid.UUID, payload: MentorNoteUpdate, db: DB, mentor: Mentor):
    return APIResponse(success=True, data=await MentorService.update_note(db, mentor, note_id, payload), message="Note updated")


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: uuid.UUID, db: DB, mentor: Mentor):
    await MentorService.delete_note(db, mentor, note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/classes", response_model=APIResponseMentorClasses)
async def classes(db: DB, mentor: Mentor):
    return APIResponse(success=True, data=await MentorService.classes(db, mentor), message="Classes loaded")


@router.get("/teams", response_model=APIResponseMentorTeams)
async def teams(db: DB, mentor: Mentor):
    return APIResponse(success=True, data=await MentorService.teams(db, mentor), message="Teams loaded")


@router.get("/teams/{team_id}", response_model=APIResponseMentorTeam)
async def team_detail(team_id: uuid.UUID, db: DB, mentor: Mentor):
    return APIResponse(success=True, data=await MentorService.team_detail(db, mentor, team_id), message="Team loaded")


@router.get("/notices", response_model=APIResponseMentorNotices)
async def notices(
    db: DB,
    mentor: Mentor,
    q: Annotated[str | None, Query(max_length=120)] = None,
    scope: Literal["INSTITUTION", "DEPARTMENT", "CLASS"] | None = None,
    limit: int = 20,
    offset: int = 0,
):
    data = await MentorService.notices(db, mentor, query=q, scope=scope, limit=limit, offset=offset)
    return APIResponse(success=True, data=data, message="Notices loaded")


@router.get("/notices/{notice_id}", response_model=APIResponseMentorNotice)
async def notice_detail(notice_id: uuid.UUID, db: DB, mentor: Mentor):
    return APIResponse(success=True, data=await MentorService.notice_detail(db, mentor, notice_id), message="Notice loaded")
