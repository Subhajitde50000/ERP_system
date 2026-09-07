"""ORM models used by the Principal console.

The principal console is intentionally a read-heavy cross-module surface.  The
models in this module mirror the existing core tables instead of introducing a
second reporting store, so dashboard figures, approval queues and exports all
come from the same rows used by the operational modules.

Only the two governance fields that were absent from the original schema are
added by ``database/update2.sql`` / the matching Alembic migration:

* ``exams.schedule_approval_*``
* ``result_publications.approval_*``

Every model carrying tenant-owned data has a ``tenant_id`` and every service
query filters it explicitly.  Child tables without a tenant column (for
example ``notice_reads``) are only reached after their tenant-scoped parent has
been loaded.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, Enum as SAEnum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class AttendanceStatus(str, enum.Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"
    EXCUSED = "EXCUSED"


class LeaveStatus(str, enum.Enum):
    """Shared ``leave_status`` PG enum — used by both staff and student leave."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ExamType(str, enum.Enum):
    MCQ = "MCQ"
    DESCRIPTIVE = "DESCRIPTIVE"
    MIXED = "MIXED"
    QUIZ = "QUIZ"


class ExamMode(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class SlotType(str, enum.Enum):
    CLASS = "CLASS"
    BREAK = "BREAK"
    LAB = "LAB"
    ACTIVITY = "ACTIVITY"


class EmploymentType(str, enum.Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    VISITING = "VISITING"


class ExamStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ONGOING = "ONGOING"
    COMPLETED = "COMPLETED"
    RESULTS_RELEASED = "RESULTS_RELEASED"
    CANCELLED = "CANCELLED"


class AttemptStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    GRADED = "GRADED"
    MALPRACTICE = "MALPRACTICE"


class ResultOutcome(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WITHHELD = "WITHHELD"
    ABSENT = "ABSENT"


class NoticeScope(str, enum.Enum):
    INSTITUTION = "INSTITUTION"
    DEPARTMENT = "DEPARTMENT"
    CLASS = "CLASS"
    HOSTEL = "HOSTEL"
    TRANSPORT = "TRANSPORT"


class NoticePriority(str, enum.Enum):
    NORMAL = "NORMAL"
    IMPORTANT = "IMPORTANT"
    URGENT = "URGENT"


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    __table_args__ = (
        Index("idx_att_sessions_class_date", "class_id", "date"),
        Index("idx_att_sessions_date_range", "tenant_id", "class_id", "date", "subject_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    teacher_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    period_label: Mapped[str] = mapped_column(String(30), nullable=False)
    start_time: Mapped[time | None] = mapped_column(nullable=True)
    end_time: Mapped[time | None] = mapped_column(nullable=True)
    total_present: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_absent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    locked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Exam(Base):
    __tablename__ = "exams"
    __table_args__ = (
        Index("idx_exams_class_subject", "class_id", "subject_id"),
        Index("idx_exams_status_date", "status", "scheduled_at"),
        Index("idx_exams_tenant_schedule_approval", "tenant_id", "schedule_approval_status", "scheduled_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=False)
    # PG enums (database.sql §3) — mapped with SAEnum so asyncpg receives the
    # correct type cast on INSERT/UPDATE and reads come back as enum members.
    exam_type: Mapped[ExamType] = mapped_column(SAEnum(ExamType, name="exam_type"), nullable=False)
    mode: Mapped[ExamMode] = mapped_column(SAEnum(ExamMode, name="exam_mode"), nullable=False, default=ExamMode.ONLINE)
    total_marks: Mapped[int] = mapped_column(Integer, nullable=False)
    passing_marks: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    window_end_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    results_release_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    status: Mapped[ExamStatus] = mapped_column(SAEnum(ExamStatus, name="exam_status"), nullable=False, default=ExamStatus.DRAFT)
    allow_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    show_score_immediately: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    schedule_approval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    schedule_approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    schedule_approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    schedule_approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ExamHallAllocation(Base):
    __tablename__ = "exam_hall_allocations"
    __table_args__ = (
        Index("idx_exam_hall_allocations_exam_id", "exam_id"),
        Index("idx_exam_hall_allocations_invigilator_id", "invigilator_id"),
        Index("idx_exam_hall_allocations_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    exam_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("exams.id"), nullable=False)
    room_no: Mapped[str] = mapped_column(String(50), nullable=False)
    invigilator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    student_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class ExamAttempt(Base):
    __tablename__ = "exam_attempts"
    __table_args__ = (
        Index("idx_attempts_exam_student", "exam_id", "student_id"),
        Index("idx_attempts_status", "status"),
        Index("idx_exam_attempts_student_id", "student_id"),
        Index("idx_exam_attempts_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    exam_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("exams.id"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    auto_submitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(5), nullable=True)
    status: Mapped[AttemptStatus] = mapped_column(SAEnum(AttemptStatus, name="attempt_status"), nullable=False, default=AttemptStatus.IN_PROGRESS)
    tab_switch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    device_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class MalpracticeLog(Base):
    __tablename__ = "malpractice_logs"
    __table_args__ = (
        Index("idx_malpractice_tenant_logged", "tenant_id", "logged_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("exam_attempts.id"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logged_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    handled_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class ResultPublication(Base):
    __tablename__ = "result_publications"
    __table_args__ = (
        Index("idx_result_publications_tenant_approval", "tenant_id", "approval_status", "published_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=False)
    class_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)
    exam_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    published_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    published_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    is_visible_to_students: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class StudentResult(Base):
    __tablename__ = "student_results"
    __table_args__ = (
        Index("idx_results_publication", "publication_id"),
        Index("idx_results_student", "student_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    publication_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("result_publications.id"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    total_marks_obtained: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    total_marks_possible: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    grade: Mapped[str] = mapped_column(String(5), nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[ResultOutcome] = mapped_column(SAEnum(ResultOutcome, name="result_outcome"), nullable=False)
    subject_scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Notice(Base):
    __tablename__ = "notices"
    __table_args__ = (
        Index("idx_notices_scope_target", "tenant_id", "target_scope", "target_id"),
        Index("idx_notices_expiry", "expires_at", postgresql_where="expires_at IS NOT NULL"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    target_scope: Mapped[NoticeScope] = mapped_column(SAEnum(NoticeScope, name="notice_scope"), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    priority: Mapped[NoticePriority] = mapped_column(SAEnum(NoticePriority, name="notice_priority"), nullable=False, default=NoticePriority.NORMAL)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class NoticeAttachment(Base):
    __tablename__ = "notice_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("notices.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class NoticeRead(Base):
    __tablename__ = "notice_reads"
    __table_args__ = (Index("uq_notice_reads__notice_id_user_id", "notice_id", "user_id", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("notices.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    read_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class TimetableSlot(Base):
    __tablename__ = "timetable_slots"
    __table_args__ = (Index("idx_timetable_class_day", "class_id", "day_of_week", "period_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(nullable=False)
    end_time: Mapped[time] = mapped_column(nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)
    teacher_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    room_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    slot_type: Mapped[SlotType] = mapped_column(SAEnum(SlotType, name="slot_type"), nullable=False, default=SlotType.CLASS)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class StaffProfile(Base):
    __tablename__ = "staff_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    employee_code: Mapped[str] = mapped_column(String(50), nullable=False)
    designation: Mapped[str] = mapped_column(String(100), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    employment_type: Mapped[EmploymentType] = mapped_column(
        SAEnum(EmploymentType, name="employment_type"), nullable=False
    )
    date_of_joining: Mapped[date] = mapped_column(Date, nullable=False)
    date_of_leaving: Mapped[date | None] = mapped_column(Date, nullable=True)
    qualification: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_years: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StaffLeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_days: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[LeaveStatus] = mapped_column(
        SAEnum(LeaveStatus, name="leave_status"), nullable=False, default=LeaveStatus.PENDING
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
