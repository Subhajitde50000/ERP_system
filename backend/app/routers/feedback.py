"""Feedback Campaign API.

Accessible surfaces:
  INSTITUTION_ADMIN / PRINCIPAL  →  /feedback/campaigns (and /principal/feedback/campaigns)
  STUDENT                        →  /student/feedback   (in student router)
  TEACHER                        →  /teacher/feedback   (in teacher router)
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_tenant_user_feedback_manager
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.feedback import (
    APIResponseCampaign,
    APIResponseCampaignAnalytics,
    APIResponseCampaigns,
    CampaignCreate,
    CampaignUpdate,
)
from app.services.feedback_service import FeedbackService

router = APIRouter(prefix="/feedback", tags=["Feedback Campaigns"])


@router.post("/campaigns", response_model=APIResponseCampaign, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user_feedback_manager)],
):
    data = await FeedbackService.create_campaign(
        db, current_user.tenant_id, current_user.id, payload
    )
    return APIResponse(success=True, data=data, message="Feedback campaign created")


@router.get("/campaigns", response_model=APIResponseCampaigns)
async def list_campaigns(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user_feedback_manager)],
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    data = await FeedbackService.list_campaigns(
        db, current_user.tenant_id, status_filter, limit, offset
    )
    return APIResponse(success=True, data=data, message="Campaigns loaded")


@router.get("/campaigns/{campaign_id}", response_model=APIResponseCampaign)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user_feedback_manager)],
):
    data = await FeedbackService.get_campaign(db, campaign_id, current_user.tenant_id)
    return APIResponse(success=True, data=data, message="Campaign loaded")


@router.patch("/campaigns/{campaign_id}", response_model=APIResponseCampaign)
async def update_campaign(
    campaign_id: uuid.UUID,
    payload: CampaignUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user_feedback_manager)],
):
    data = await FeedbackService.update_campaign(
        db, campaign_id, current_user.tenant_id, payload
    )
    return APIResponse(success=True, data=data, message="Campaign updated")


@router.post("/campaigns/{campaign_id}/publish", response_model=APIResponseCampaign)
async def publish_campaign(
    campaign_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user_feedback_manager)],
):
    data = await FeedbackService.publish_campaign(db, campaign_id, current_user.tenant_id)
    return APIResponse(success=True, data=data, message="Campaign published and students notified")


@router.post("/campaigns/{campaign_id}/close", response_model=APIResponseCampaign)
async def close_campaign(
    campaign_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user_feedback_manager)],
):
    data = await FeedbackService.close_campaign(db, campaign_id, current_user.tenant_id)
    return APIResponse(success=True, data=data, message="Campaign closed")


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user_feedback_manager)],
):
    await FeedbackService.delete_campaign(db, campaign_id, current_user.tenant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/campaigns/{campaign_id}/analytics", response_model=APIResponseCampaignAnalytics)
async def campaign_analytics(
    campaign_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user_feedback_manager)],
):
    data = await FeedbackService.get_campaign_analytics(
        db, campaign_id, current_user.tenant_id
    )
    return APIResponse(success=True, data=data, message="Campaign analytics loaded")
