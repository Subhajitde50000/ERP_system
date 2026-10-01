"""Wire contracts for the Teacher Feedback Campaign feature.

Roles and their surfaces:
  INSTITUTION_ADMIN / PRINCIPAL  →  create/manage campaigns, view analytics
  STUDENT                        →  list active campaigns, submit feedback (once per teacher)
  TEACHER                        →  view their own aggregated results (no per-student visibility
                                     unless allow_anonymous=False)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import APIResponse


# ── Campaign management (Admin / Principal) ──────────────────────────────────

class CampaignTargetIn(BaseModel):
    """One teacher+subject pair to include in a campaign."""
    teacher_id: uuid.UUID
    subject_id: uuid.UUID | None = None
    class_id: uuid.UUID | None = None


class CampaignCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    allow_anonymous: bool = True
    # Empty list → must be populated; the API rejects an empty targets list.
    targets: list[CampaignTargetIn] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_window(self) -> "CampaignCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class CampaignUpdate(BaseModel):
    """Partial update — only DRAFT campaigns may be edited."""
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    allow_anonymous: bool | None = None


class CampaignTargetRow(BaseModel):
    id: uuid.UUID
    teacher_id: uuid.UUID
    teacher_name: str | None = None
    subject_id: uuid.UUID | None = None
    subject_name: str | None = None
    class_id: uuid.UUID | None = None
    class_name: str | None = None


class CampaignRow(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    allow_anonymous: bool
    status: str
    created_at: datetime
    closed_at: datetime | None = None
    target_count: int = 0


class CampaignDetail(CampaignRow):
    targets: list[CampaignTargetRow] = Field(default_factory=list)


class CampaignPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CampaignRow]


# ── Admin analytics (aggregated, never per-student) ──────────────────────────

class TeacherAggregateResult(BaseModel):
    """Aggregated scores for one teacher inside a campaign."""
    teacher_id: uuid.UUID
    teacher_name: str | None = None
    response_count: int
    teaching_clarity_avg: float | None = None
    subject_knowledge_avg: float | None = None
    interaction_avg: float | None = None
    overall_avg: float | None = None
    # Only included for admin/principal, and only when allow_anonymous=False
    comments: list[str] | None = None


class CampaignAnalytics(BaseModel):
    campaign_id: uuid.UUID
    campaign_title: str
    total_responses: int
    results: list[TeacherAggregateResult]


# ── Student-facing view ───────────────────────────────────────────────────────

class StudentFeedbackTarget(BaseModel):
    """One teacher the student can rate (filtered to teachers they actually study under)."""
    target_id: uuid.UUID
    teacher_id: uuid.UUID
    teacher_name: str | None = None
    subject_id: uuid.UUID | None = None
    subject_name: str | None = None
    class_name: str | None = None
    already_submitted: bool


class StudentFeedbackCampaign(BaseModel):
    """An active campaign as visible to the student."""
    id: uuid.UUID
    title: str
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    targets: list[StudentFeedbackTarget]


class FeedbackSubmit(BaseModel):
    """Student submits ratings for one teacher target."""
    target_id: uuid.UUID
    teaching_clarity: int | None = Field(default=None, ge=1, le=5)
    subject_knowledge: int | None = Field(default=None, ge=1, le=5)
    interaction: int | None = Field(default=None, ge=1, le=5)
    overall: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = None

    @model_validator(mode="after")
    def _at_least_one_rating(self) -> "FeedbackSubmit":
        if all(v is None for v in [self.teaching_clarity, self.subject_knowledge, self.interaction, self.overall]):
            raise ValueError("At least one rating must be provided")
        return self


# ── Teacher-facing view (aggregated) ─────────────────────────────────────────

class TeacherFeedbackResult(BaseModel):
    """What a teacher sees for one campaign they are part of."""
    campaign_id: uuid.UUID
    campaign_title: str
    starts_at: datetime
    ends_at: datetime
    status: str
    response_count: int
    teaching_clarity_avg: float | None = None
    subject_knowledge_avg: float | None = None
    interaction_avg: float | None = None
    overall_avg: float | None = None
    # Only populated when the campaign has allow_anonymous=False
    comments: list[str] | None = None


# ── API response type aliases ─────────────────────────────────────────────────

APIResponseCampaign = APIResponse[CampaignDetail]
APIResponseCampaigns = APIResponse[CampaignPage]
APIResponseCampaignAnalytics = APIResponse[CampaignAnalytics]
APIResponseStudentCampaigns = APIResponse[list[StudentFeedbackCampaign]]
APIResponseTeacherFeedback = APIResponse[list[TeacherFeedbackResult]]
