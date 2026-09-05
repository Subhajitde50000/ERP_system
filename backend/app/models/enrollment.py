"""
ORM Models — enrollment + teaching links

  student_enrollments — links a STUDENT user to a class for an academic year
                        (the roster behind C-IA-11 Enrollments).
  teacher_subjects    — which teacher teaches a subject, and their role in it
                        (§6.5; powers "Assign teachers" on C-IA-07).

These tables already exist in database.sql but had no ORM model, so no service
could read or write them. Mirrors the schema exactly.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, Enum as SAEnum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class EnrollmentStatus(str, enum.Enum):
    """PG enum ``enrollment_status`` (database.sql §3)."""

    ACTIVE = "ACTIVE"
    TRANSFERRED = "TRANSFERRED"
    DROPPED = "DROPPED"
    COMPLETED = "COMPLETED"


class Enrollment(Base):
    __tablename__ = "student_enrollments"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "class_id",
            "academic_year_id",
            name="uq_student_enrollments__student_id_class_id_academic_year_id",
        ),
        Index("idx_student_enrollments_tenant_id", "tenant_id"),
        Index("idx_student_enrollments_class_id", "class_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False
    )
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=False
    )
    roll_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    enrollment_date: Mapped[date] = mapped_column(
        Date, nullable=False, default=date.today
    )
    # ACTIVE | TRANSFERRED | DROPPED | COMPLETED (PG enum — SAEnum keeps the
    # asyncpg INSERT cast aligned with the database type).
    status: Mapped[EnrollmentStatus] = mapped_column(
        SAEnum(EnrollmentStatus, name="enrollment_status"), nullable=False, default=EnrollmentStatus.ACTIVE
    )
    transferred_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class TeacherSubject(Base):
    __tablename__ = "teacher_subjects"
    __table_args__ = (
        UniqueConstraint(
            "teacher_id",
            "subject_id",
            "role_in_subject",
            name="uq_teacher_subjects__teacher_id_subject_id_role_in_subject",
        ),
        Index("idx_teacher_subjects_tenant_id", "tenant_id"),
        Index("idx_teacher_subjects_subject_id", "subject_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False
    )
    # TEACHER | CO_TEACHER | LAB_ASSISTANT | …
    role_in_subject: Mapped[str] = mapped_column(
        String(50), nullable=False, default="TEACHER"
    )
    assigned_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
