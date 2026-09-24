"""Routers — mentor assignment board (Academic Coordinator primary, Institution Admin fallback).

Mounted under ``/institution/mentors``.  Assigns one mentor to a student, a
project team or a whole class; every target holds at most one active mentor
per academic year while a mentor may hold many targets.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_tenant_user_student_records_manager
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.mentor import APIResponseMentorBoard, MentorAssignRequest
from app.services.mentor_assignment_service import MentorAssignmentService
from app.services.mentor_management_service import MentorManagementService

router = APIRouter(prefix="/mentors")


async def _actor_role(db: AsyncSession, actor: User) -> str:
    """Audit label: the Coordinator owns this workflow, Admin is the fallback."""
    roles = await MentorAssignmentService.live_role_names(db, actor.tenant_id, actor.id)
    return "ACADEMIC_COORDINATOR" if "ACADEMIC_COORDINATOR" in roles else "INSTITUTION_ADMIN"


@router.get("/board", response_model=APIResponseMentorBoard)
async def mentor_board(
    db: Annotated[AsyncSession, Depends(get_db)],
    manager: Annotated[User, Depends(get_current_tenant_user_student_records_manager)],
):
    return APIResponse(success=True, data=await MentorManagementService.board(db, manager.tenant_id), message="Mentor board loaded")


@router.post("/assignments", response_model=APIResponseMentorBoard, status_code=201)
async def assign_mentor(
    payload: MentorAssignRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    manager: Annotated[User, Depends(get_current_tenant_user_student_records_manager)],
):
    board = await MentorManagementService.assign(db, manager, await _actor_role(db, manager), payload)
    return APIResponse(success=True, data=board, message="Mentor assigned")


@router.delete("/assignments/{assignment_id}", response_model=APIResponseMentorBoard)
async def remove_mentor_assignment(
    assignment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    manager: Annotated[User, Depends(get_current_tenant_user_student_records_manager)],
):
    board = await MentorManagementService.remove(db, manager, await _actor_role(db, manager), assignment_id)
    return APIResponse(success=True, data=board, message="Mentor assignment removed")
