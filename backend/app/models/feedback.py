"""ORM models — Teacher Feedback Campaign feature.

Provides the three tables that power the end-to-end teacher-feedback workflow:

* ``feedback_campaigns``         — campaign object created by an Institution
                                   Admin or Principal; controls the window in
                                   which students may submit ratings.
* ``feedback_campaign_targets``  — each (teacher, optional subject, optional
                                   class) tuple that belongs to a campaign.
                                   NULL subject_id means "teacher overall".
* ``feedback_responses``         — one row per student · target · campaign;
                                   stores five numeric dimensions plus a free-
                                   text comment.  ``student_id`` is always
                                   persisted for deduplication but is only
                                   surfaced to the teacher when the campaign
                                   was created with ``allow_anonymous = False``.

The ``campaign_status`` PG enum is created by the companion Alembic migration
``e2f3a4b5c6d7_add_feedback_campaigns.py``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Enum as SAEnum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


# ---------------------------------------------------------------------------
# Python enum — mirrored by the ``campaign_status`` PG enum in the migration.
# ---------------------------------------------------------------------------

class CampaignStatus(str, enum.Enum):
    """Lifecycle states for a :class:`FeedbackCampaign`."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------

class FeedbackCampaign(Base):
    """A teacher-feedback campaign created by an Institution Admin / Principal.

    Columns
    -------
    id              Primary key — random UUID.
    tenant_id       Owning tenant; every service query filters on this column.
    title           Human-readable label, e.g. 'Teacher Feedback — Semester 1'.
    description     Optional long description shown to students.
    starts_at       Timestamp from which students may submit responses.
    ends_at         Timestamp after which the campaign is auto-closed.
    allow_anonymous If ``False`` the teacher can see who submitted; default
                    ``True`` hides ``student_id`` from teacher-facing queries.
    status          DRAFT → ACTIVE → CLOSED lifecycle driven by the scheduler.
    created_by      FK to the user (Admin / Principal) who opened the campaign.
    created_at      Server-side creation timestamp.
    closed_at       Populated when the campaign transitions to CLOSED.
    """

    __tablename__ = "feedback_campaigns"
    __table_args__ = (
        Index("idx_feedback_campaigns_tenant_id", "tenant_id"),
        Index("idx_feedback_campaigns_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    ends_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    # If False, teacher-facing responses expose student_id.
    allow_anonymous: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    # DRAFT | ACTIVE | CLOSED (PG enum — SAEnum keeps the asyncpg INSERT cast
    # aligned with the database type).
    status: Mapped[CampaignStatus] = mapped_column(
        SAEnum(CampaignStatus, name="campaign_status"),
        nullable=False,
        default=CampaignStatus.DRAFT,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class FeedbackCampaignTarget(Base):
    """A (teacher, subject?, class?) tuple included in a :class:`FeedbackCampaign`.

    A ``NULL`` ``subject_id`` means the rating covers the teacher overall rather
    than a specific subject.  A ``NULL`` ``class_id`` means the target applies
    across all classes taught by that teacher in the campaign.

    Columns
    -------
    id           Primary key — random UUID.
    campaign_id  Parent campaign; CASCADE-deleted when the campaign is removed.
    teacher_id   FK to the teacher being rated.
    subject_id   Optional FK to the subject scope (NULL = overall).
    class_id     Optional FK to the class scope (NULL = all classes).

    Constraints
    -----------
    uq_fct__campaign_teacher_subject  — prevents duplicate targets within the
                                        same campaign for the same
                                        (teacher, subject) pair.
    """

    __tablename__ = "feedback_campaign_targets"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "teacher_id",
            "subject_id",
            name="uq_fct__campaign_teacher_subject",
        ),
        Index("idx_fct_campaign_id", "campaign_id"),
        Index("idx_fct_teacher_id", "teacher_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("feedback_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True
    )
    class_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True
    )


class FeedbackResponse(Base):
    """One student's rating for one :class:`FeedbackCampaignTarget`.

    ``student_id`` is always stored so the service can enforce the one-response-
    per-student-per-target constraint, but teacher-facing API endpoints suppress
    it when ``FeedbackCampaign.allow_anonymous`` is ``True``.

    Dimensions are 1–5 SmallInteger ratings; all nullable so a student may skip
    individual questions while still submitting the form.

    Columns
    -------
    id                Primary key — random UUID.
    campaign_id       Denormalised FK for fast per-campaign aggregations;
                      CASCADE-deleted with the parent campaign.
    target_id         FK to the specific (teacher, subject, class) target;
                      CASCADE-deleted when the target is removed.
    student_id        FK to the submitting student; retained for deduplication.
    teaching_clarity  Rating 1–5: clarity of explanations.
    subject_knowledge Rating 1–5: depth of subject knowledge.
    interaction       Rating 1–5: student–teacher interaction quality.
    overall           Rating 1–5: holistic rating.
    comment           Optional free-text feedback.
    submitted_at      Server-side submission timestamp.

    Constraints
    -----------
    uq_fr__campaign_target_student — one response per (campaign, target, student).
    """

    __tablename__ = "feedback_responses"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "target_id",
            "student_id",
            name="uq_fr__campaign_target_student",
        ),
        Index("idx_fr_campaign_id", "campaign_id"),
        Index("idx_fr_target_id", "target_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("feedback_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("feedback_campaign_targets.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Always stored; exposed to the teacher only when allow_anonymous = False.
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # Numeric rating dimensions (1–5); nullable so partial submissions are valid.
    teaching_clarity: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    subject_knowledge: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    interaction: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    overall: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
