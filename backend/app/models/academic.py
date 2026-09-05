"""
ORM Models — academic structure (created by the first-time setup wizard)

Mirrors database.sql + class_hierarchy_migration.sql:
  academic_years  — e.g. "2026-27", exactly one current per tenant
  departments     — e.g. "Computer Science" (code "CS")
  class_grades    — school grade group (Class 1–12 + optional stream) [NEW]
  class_programs  — college program + semester group [NEW]
  classes         — the final Academic Group (section / batch); FK-referenced by
                    subjects, enrollments, attendance, exams, timetable
  subjects        — tied to a class; subject_type THEORY/PRACTICAL/ELECTIVE/PROJECT
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class SubjectType(str, enum.Enum):
    """PG enum ``subject_type`` (database.sql §3)."""

    THEORY = "THEORY"
    PRACTICAL = "PRACTICAL"
    ELECTIVE = "ELECTIVE"
    PROJECT = "PROJECT"


class AcademicYear(Base):
    __tablename__ = "academic_years"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_academic_years__tenant_id_name"),
        Index("idx_academic_years_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_departments__tenant_id_code"),
        Index("idx_departments_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    hod_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ClassGrade(Base):
    """School grade group: one row per (tenant, year, grade_number, stream).

    Children: SchoolClass rows with grade_id pointing here — one per section letter.
    E.g.  grade_number=11, stream='Science'  →  sections 11-Sci-A, 11-Sci-B.
    """
    __tablename__ = "class_grades"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "academic_year_id", "grade_number", "stream",
            name="uq_class_grades",
        ),
        Index("idx_class_grades_tenant_id", "tenant_id"),
        Index("idx_class_grades_academic_year_id", "academic_year_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Class 11"
    grade_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12
    stream: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Science/Commerce/Arts/custom
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class ClassProgram(Base):
    """College program + semester group.

    Children: SchoolClass rows with program_id pointing here — one per batch.
    E.g.  program_code='BTCSE', semester_number=3  →  batches CSE-3A, CSE-3B.
    """
    __tablename__ = "class_programs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "department_id", "program_code", "semester_number", "academic_year_id",
            name="uq_class_programs",
        ),
        Index("idx_class_programs_tenant_id", "tenant_id"),
        Index("idx_class_programs_department_id", "department_id"),
        Index("idx_class_programs_academic_year_id", "academic_year_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False
    )
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=False
    )
    program_name: Mapped[str] = mapped_column(String(200), nullable=False)  # "B.Tech CSE"
    program_code: Mapped[str] = mapped_column(String(30), nullable=False)   # "BTCSE"
    semester_number: Mapped[int] = mapped_column(Integer, nullable=False)   # 1, 2, 3…
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class SchoolClass(Base):
    __tablename__ = "classes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "department_id",
            "academic_year_id",
            "code",
            name="uq_classes__tenant_id_dept_year_code",
        ),
        Index("idx_classes_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False
    )
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    max_strength: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    class_teacher_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    room_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    # ── Hierarchy parents (set for classes created via the wizard) ──────────
    # grade_id   → set for school sections (FK to class_grades)
    # program_id → set for college batches (FK to class_programs)
    # section_label → "A", "B", "Batch A" etc. — display label for the section
    grade_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("class_grades.id", ondelete="SET NULL"), nullable=True
    )
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("class_programs.id", ondelete="SET NULL"), nullable=True
    )
    section_label: Mapped[str | None] = mapped_column(String(20), nullable=True)


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "class_id", "code", name="uq_subjects__tenant_id_class_id_code"),
        Index("idx_subjects_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    # THEORY | PRACTICAL | ELECTIVE | PROJECT (PG enum — SAEnum keeps the
    # asyncpg INSERT cast aligned with the database type).
    subject_type: Mapped[SubjectType] = mapped_column(SAEnum(SubjectType, name="subject_type"), nullable=False)
    credits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_marks: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    passing_marks: Mapped[int] = mapped_column(Integer, nullable=False, default=35)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
