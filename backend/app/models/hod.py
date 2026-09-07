"""ORM models required by the HOD department-management console.

The tables already belong to the base ERP schema.  They are modelled here so
HOD workflows read/write the canonical rows instead of maintaining a second
fixture or reporting store.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models.principal import AttendanceStatus


class AssignmentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CLOSED = "CLOSED"


class AssignmentType(str, enum.Enum):
    """PG enum ``assignment_type`` (database.sql §3) behind ``assignments.type``."""

    REGULAR = "REGULAR"
    MILESTONE = "MILESTONE"
    GROUP = "GROUP"


class SubmissionStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RESUBMIT_REQUESTED = "RESUBMIT_REQUESTED"


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        Index("idx_att_records_session", "session_id"),
        Index("idx_att_records_student", "student_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[AttendanceStatus] = mapped_column(
        SAEnum(AttendanceStatus, name="attendance_status"), nullable=False
    )
    late_by_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    marked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (Index("idx_assignments_class", "class_id", "due_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=False)
    teacher_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # Attribute name differs from the column ("type" is a Python keyword);
    # SAEnum matches the PG enum type so asyncpg gets the right cast.
    assignment_type: Mapped[AssignmentType] = mapped_column(
        "type", SAEnum(AssignmentType, name="assignment_type"), nullable=False
    )
    total_marks: Mapped[int] = mapped_column(Integer, nullable=False)
    passing_marks: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    # The teacher console (C-TC-13/14) owns the remaining canonical columns;
    # the HOD console reads the same rows and ignores them.
    allow_late_submission: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    late_penalty_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_file_size_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    allowed_file_types: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    min_group_size: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    max_group_size: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    instructions_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AssignmentStatus] = mapped_column(
        SAEnum(AssignmentStatus, name="assignment_status"), nullable=False, default=AssignmentStatus.DRAFT
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (Index("idx_submissions_assignment", "assignment_id", "student_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    assignment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assignments.id"), nullable=False)
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("milestones.id"), nullable=True)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("project_groups.id"), nullable=True)
    text_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    late_by_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(5), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[SubmissionStatus] = mapped_column(
        SAEnum(SubmissionStatus, name="submission_status"), nullable=False, default=SubmissionStatus.SUBMITTED
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class DiscussionThread(Base):
    __tablename__ = "discussion_threads"
    __table_args__ = (Index("idx_threads_scope", "scope_type", "scope_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reply_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    upvote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class MentorAssignment(Base):
    __tablename__ = "mentor_assignments"
    __table_args__ = (
        Index(
            "uq_mentor_assignments__tenant_student_year_active",
            "tenant_id",
            "student_id",
            "academic_year_id",
            unique=True,
            postgresql_where="is_active = TRUE",
        ),
        Index("idx_mentor_assignments_mentor_id", "mentor_id", "academic_year_id"),
        Index("idx_mentor_assignments_student_id", "student_id", "academic_year_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    mentor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=False)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
