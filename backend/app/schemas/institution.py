"""
Pydantic Schemas — institution admin management API

DTOs for the day-to-day admin flows: dashboard, academic structure (years,
departments, classes, subjects), people (staff/users, students, enrollments),
modules, settings and the institution profile. All scoped to the admin's
tenant via the JWT.
"""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import APIResponse

# ── Dashboard ────────────────────────────────────────────────────────────────

class DashboardSummary(BaseModel):
    tenant_id: uuid.UUID
    name: str
    slug: str
    type: str
    academic_year: str | None = None
    counts: dict[str, int]
    enabled_modules: list[str]
    onboarding_complete: bool


# ── Academic years ───────────────────────────────────────────────────────────

class AcademicYearCreate(BaseModel):
    name: str = Field(..., max_length=50)
    start_date: date
    end_date: date
    is_current: bool = False


class AcademicYearUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=50)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None


class AcademicYearOut(BaseModel):
    id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    is_current: bool


# ── Departments ──────────────────────────────────────────────────────────────

class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    code: str = Field(..., min_length=1, max_length=20)
    description: str | None = None
    hod_id: uuid.UUID | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=20)
    description: str | None = None
    hod_id: uuid.UUID | None = None
    is_active: bool | None = None


class DepartmentOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    description: str | None = None
    hod_id: uuid.UUID | None = None
    hod_name: str | None = None
    is_active: bool
    class_count: int = 0
    staff_count: int = 0


# ── Class grades (school) + programs (college) ─────────────────────────────

# School: one ClassGrade row groups the N sections of e.g. "Class 11 Science"
class ClassGradeCreate(BaseModel):
    """Wizard payload: create a school grade group + one section per letter."""
    academic_year_id: uuid.UUID
    # Section lives inside a department even for school (for FK integrity)
    department_id: uuid.UUID
    grade_number: int = Field(..., ge=1, le=12, description="Grade 1–12")
    stream: str | None = Field(default=None, max_length=50, description="Science/Commerce/Arts or custom")
    # Section labels: ["A","B","C"] — each becomes one SchoolClass (Academic Group)
    sections: list[str] = Field(..., min_length=1, description="Section letters/labels, e.g. ['A','B','C']")
    max_strength: int = Field(default=60, ge=1)
    # Optional: assign the same class teacher to all sections, or leave empty
    # (per-section assignment can be done from the class detail page)
    class_teacher_id: uuid.UUID | None = None


class SectionOut(BaseModel):
    """A single academic group (section) within a grade or program."""
    id: uuid.UUID
    name: str
    code: str
    section_label: str | None = None
    class_teacher_id: uuid.UUID | None = None
    class_teacher_name: str | None = None
    enrolled_count: int = 0
    subject_count: int = 0
    room_no: str | None = None
    is_active: bool


class ClassGradeOut(BaseModel):
    id: uuid.UUID
    academic_year_id: uuid.UUID
    academic_year_name: str | None = None
    department_id: uuid.UUID
    department_name: str | None = None
    name: str              # "Class 11"
    grade_number: int
    stream: str | None     # "Science" / None
    is_active: bool
    sections: list[SectionOut] = Field(default_factory=list)


# College: one ClassProgram row groups the N batches of e.g. "B.Tech CSE Semester 3"
class ClassProgramCreate(BaseModel):
    """Wizard payload: create a college program+semester + one batch per label."""
    academic_year_id: uuid.UUID
    department_id: uuid.UUID
    program_name: str = Field(..., min_length=2, max_length=200, description="B.Tech CSE")
    program_code: str = Field(..., min_length=1, max_length=30, description="BTCSE")
    semester_number: int = Field(..., ge=1, description="Semester number")
    # Batch labels: ["A","B"] — each becomes one SchoolClass (Academic Group)
    batches: list[str] = Field(..., min_length=1, description="Batch labels, e.g. ['A','B']")
    max_strength: int = Field(default=60, ge=1)
    class_teacher_id: uuid.UUID | None = None


class ClassProgramOut(BaseModel):
    id: uuid.UUID
    academic_year_id: uuid.UUID
    academic_year_name: str | None = None
    department_id: uuid.UUID
    department_name: str | None = None
    program_name: str      # "B.Tech CSE"
    program_code: str      # "BTCSE"
    semester_number: int
    is_active: bool
    batches: list[SectionOut] = Field(default_factory=list)


# ── Classes (Academic Groups) ───────────────────────────────────────────

class ClassCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=20)
    department_id: uuid.UUID
    academic_year_id: uuid.UUID
    max_strength: int = Field(default=60, ge=1)
    room_no: str | None = Field(default=None, max_length=20)
    class_teacher_id: uuid.UUID | None = None


class ClassUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    max_strength: int | None = Field(default=None, ge=1)
    room_no: str | None = None
    class_teacher_id: uuid.UUID | None = None
    is_active: bool | None = None


class ClassOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    department_id: uuid.UUID
    department_name: str | None = None
    academic_year_id: uuid.UUID
    academic_year_name: str | None = None
    max_strength: int
    room_no: str | None = None
    class_teacher_id: uuid.UUID | None = None
    class_teacher_name: str | None = None
    is_active: bool
    enrolled_count: int = 0
    subject_count: int = 0
    # ── Hierarchy parent fields (None for flat / legacy classes) ───────────
    grade_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None
    section_label: str | None = None


# ── Subjects ─────────────────────────────────────────────────────────────────

class SubjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=30)
    class_id: uuid.UUID
    subject_type: str = Field(default="THEORY", pattern="^(THEORY|PRACTICAL|ELECTIVE|PROJECT)$")
    credits: int | None = Field(default=None, ge=0)
    max_marks: int = Field(default=100, ge=1)
    passing_marks: int = Field(default=35, ge=0)


class SubjectUpdate(BaseModel):
    name: str | None = None
    subject_type: str | None = Field(default=None, pattern="^(THEORY|PRACTICAL|ELECTIVE|PROJECT)$")
    credits: int | None = Field(default=None, ge=0)
    max_marks: int | None = Field(default=None, ge=1)
    passing_marks: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class SubjectOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    class_id: uuid.UUID
    class_name: str | None = None
    subject_type: str
    credits: int | None = None
    max_marks: int
    passing_marks: int
    is_active: bool
    teachers: list[dict[str, Any]] = Field(default_factory=list)


# ── People: staff / users ────────────────────────────────────────────────────

class StaffInvite(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=20)
    role: str = Field(..., max_length=50, description="Role name, e.g. TEACHER")
    department_id: uuid.UUID | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class StaffUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    department_id: uuid.UUID | None = None



class RoleAssignmentOut(BaseModel):
    role_id: uuid.UUID
    role_name: str
    is_active: bool


class StaffOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None = None
    phone: str | None = None
    is_active: bool
    last_login_at: datetime | None = None
    roles: list[str] = Field(default_factory=list)
    department_id: uuid.UUID | None = None
    department_name: str | None = None


class AssignRoleRequest(BaseModel):
    role_name: str = Field(..., max_length=50)
    # Required when assigning VICE_PRINCIPAL: it is the delegated department
    # scope, not an optional profile field.
    department_id: uuid.UUID | None = None


# ── People: students + enrollments ───────────────────────────────────────────

class StudentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr | None = None
    roll_no: str = Field(..., min_length=1, max_length=50)
    gender: str | None = Field(default=None, pattern="^(MALE|FEMALE|OTHER)$")
    date_of_birth: date | None = None
    class_id: uuid.UUID | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class StudentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    email: EmailStr | None = None
    roll_no: str | None = Field(default=None, min_length=1, max_length=50)
    gender: str | None = Field(default=None, pattern="^(MALE|FEMALE|OTHER)$")
    date_of_birth: date | None = None
    class_id: uuid.UUID | None = None
    is_active: bool | None = None


class StudentOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None = None
    roll_no: str | None = None
    gender: str | None = None
    is_active: bool
    enrollment: dict[str, Any] | None = None


class BulkUploadRowIssue(BaseModel):
    """One problem found in a CSV row during bulk student import."""
    row: int
    message: str


class BulkUploadResult(BaseModel):
    total: int
    created: int
    errors: list[BulkUploadRowIssue] = Field(default_factory=list)
    warnings: list[BulkUploadRowIssue] = Field(default_factory=list)


class EnrollmentCreate(BaseModel):
    student_id: uuid.UUID
    class_id: uuid.UUID
    academic_year_id: uuid.UUID | None = None
    roll_number: str | None = Field(default=None, max_length=50)


class EnrollmentOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    class_id: uuid.UUID
    class_name: str
    academic_year_id: uuid.UUID
    academic_year_name: str
    roll_number: str | None = None
    status: str
    enrollment_date: date


# ── Modules + settings ───────────────────────────────────────────────────────

class ModuleOut(BaseModel):
    key: str
    name: str
    is_core: bool
    is_enabled: bool
    price_monthly: float = 0


class ModuleToggle(BaseModel):
    enabled: bool


class SettingsOut(BaseModel):
    timezone: str
    currency: str
    onboarding_complete: bool


class SettingsUpdate(BaseModel):
    timezone: str | None = None
    currency: str | None = None


# ── Institution profile ──────────────────────────────────────────────────────

class InstitutionProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    type: str
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str
    pincode: str | None = None
    website: str | None = None
    logo_url: str | None = None
    timezone: str
    plan_name: str | None = None
    subscription_status: str | None = None


class InstitutionProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=20)
    website: str | None = Field(default=None, max_length=255)
    logo_url: str | None = None


# ── Typed APIResponse aliases ────────────────────────────────────────────────

APIResponseDashboard = APIResponse[DashboardSummary]
APIResponseYears = APIResponse[list[AcademicYearOut]]
APIResponseYear = APIResponse[AcademicYearOut]
APIResponseDepartments = APIResponse[list[DepartmentOut]]
APIResponseDepartment = APIResponse[DepartmentOut]
APIResponseGrades = APIResponse[list[ClassGradeOut]]
APIResponseGrade = APIResponse[ClassGradeOut]
APIResponsePrograms = APIResponse[list[ClassProgramOut]]
APIResponseProgram = APIResponse[ClassProgramOut]
APIResponseClasses = APIResponse[list[ClassOut]]
APIResponseClass = APIResponse[ClassOut]
APIResponseSubjects = APIResponse[list[SubjectOut]]
APIResponseSubject = APIResponse[SubjectOut]
APIResponseStaff = APIResponse[list[StaffOut]]
APIResponseStaffOne = APIResponse[StaffOut]
APIResponseStudents = APIResponse[list[StudentOut]]
APIResponseStudent = APIResponse[StudentOut]
APIResponseBulk = APIResponse[BulkUploadResult]
APIResponseEnrollments = APIResponse[list[EnrollmentOut]]
APIResponseEnrollment = APIResponse[EnrollmentOut]
APIResponseModules = APIResponse[list[ModuleOut]]
APIResponseModule = APIResponse[ModuleOut]
APIResponseSettings = APIResponse[SettingsOut]
APIResponseProfile = APIResponse[InstitutionProfileOut]
