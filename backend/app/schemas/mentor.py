"""Mentor schemas — shared by the management board and the mentor console.

Two API surfaces read these shapes:

* ``/institution/mentors/*`` — the Academic Coordinator (primary owner) and
  Institution Admin assign mentors to a student, a project team or a class.
* ``/mentor/*`` — the mentor's own console, fenced to the mentees those
  assignments put in scope.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import APIResponse
from app.schemas.principal import LeadershipNoticeRow, PrincipalPage

MentorScope = Literal["STUDENT", "TEAM", "CLASS"]


# ── Management board (Coordinator / Admin) ──────────────────────────────────


class MentorAssignmentRow(BaseModel):
    id: uuid.UUID
    scope_type: MentorScope
    target_id: uuid.UUID
    target_name: str
    target_detail: str | None = None
    class_id: uuid.UUID | None = None
    class_name: str | None = None
    member_count: int
    assigned_at: datetime
    assigned_by_name: str | None = None
    notes: str | None = None


class MentorBoardMentor(BaseModel):
    mentor_id: uuid.UUID
    mentor_name: str
    email: str | None = None
    designation: str | None = None
    department_name: str | None = None
    is_active: bool
    assignments: list[MentorAssignmentRow] = Field(default_factory=list)
    mentee_count: int
    at_risk_count: int


class MentorCandidate(BaseModel):
    id: uuid.UUID
    name: str
    designation: str | None = None
    department_name: str | None = None
    roles: list[str] = Field(default_factory=list)
    active_assignment_count: int


class MentorTargetOption(BaseModel):
    """A class / team / student that can receive a mentor."""

    id: uuid.UUID
    name: str
    detail: str | None = None
    class_id: uuid.UUID | None = None
    class_name: str | None = None
    member_count: int
    mentor_id: uuid.UUID | None = None
    mentor_name: str | None = None


class MentorCoverage(BaseModel):
    classes_total: int
    classes_covered: int
    teams_total: int
    teams_covered: int
    students_total: int
    students_direct: int
    students_covered: int


class MentorManagementBoard(BaseModel):
    academic_year: str | None = None
    attendance_threshold: int | None = None
    coverage: MentorCoverage
    mentors: list[MentorBoardMentor]
    candidates: list[MentorCandidate]
    classes: list[MentorTargetOption]
    teams: list[MentorTargetOption]
    students: list[MentorTargetOption]


class MentorAssignRequest(BaseModel):
    mentor_id: uuid.UUID
    scope_type: MentorScope
    target_id: uuid.UUID
    notes: str | None = Field(default=None, max_length=2000)


# ── Mentor console ──────────────────────────────────────────────────────────


class MenteeSource(BaseModel):
    assignment_id: uuid.UUID
    scope_type: MentorScope
    label: str


class MentorMenteeRow(BaseModel):
    student_id: uuid.UUID
    student_name: str
    roll_number: str | None = None
    email: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    class_id: uuid.UUID | None = None
    class_name: str | None = None
    department_name: str | None = None
    sources: list[MenteeSource] = Field(default_factory=list)
    attendance_percentage: float | None = None
    is_at_risk: bool = False
    pending_leave_count: int = 0
    note_count: int = 0
    last_note_at: datetime | None = None


class MentorMenteeList(BaseModel):
    academic_year: str | None = None
    attendance_threshold: int | None = None
    total: int
    items: list[MentorMenteeRow]


class MentorClassRow(BaseModel):
    assignment_id: uuid.UUID
    class_id: uuid.UUID
    class_name: str
    class_code: str
    department_name: str | None = None
    room_no: str | None = None
    class_teacher_name: str | None = None
    student_count: int
    average_attendance: float | None = None
    at_risk_count: int
    assigned_at: datetime


class MentorTeamMember(BaseModel):
    student_id: uuid.UUID
    student_name: str
    roll_number: str | None = None
    attendance_percentage: float | None = None
    joined_at: datetime


class MentorTeamRow(BaseModel):
    assignment_id: uuid.UUID
    team_id: uuid.UUID
    team_name: str
    coursework_id: uuid.UUID
    coursework_title: str
    coursework_status: str
    due_date: datetime
    class_id: uuid.UUID
    class_name: str
    subject_name: str | None = None
    member_count: int
    submission_status: str | None = None
    open_task_count: int
    assigned_at: datetime


class MentorTeamTask(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    assigned_to_name: str | None = None
    due_date: datetime | None = None


class MentorTeamResource(BaseModel):
    id: uuid.UUID
    title: str
    url: str
    resource_type: str


class MentorTeamMessage(BaseModel):
    id: uuid.UUID
    sender_name: str | None = None
    message: str
    created_at: datetime


class MentorTeamDetail(MentorTeamRow):
    members: list[MentorTeamMember] = Field(default_factory=list)
    tasks: list[MentorTeamTask] = Field(default_factory=list)
    resources: list[MentorTeamResource] = Field(default_factory=list)
    recent_messages: list[MentorTeamMessage] = Field(default_factory=list)


class MentorNoteRow(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    class_name: str | None = None
    author_id: uuid.UUID
    author_name: str | None = None
    is_own: bool
    body: str
    is_private: bool
    note_date: date
    created_at: datetime
    updated_at: datetime


class MentorNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    is_private: bool = True
    note_date: date | None = None


class MentorNoteUpdate(BaseModel):
    body: str | None = Field(default=None, min_length=1, max_length=5000)
    is_private: bool | None = None
    note_date: date | None = None


class MentorNotePage(PrincipalPage):
    items: list[MentorNoteRow]


class MentorExamRow(BaseModel):
    id: uuid.UUID
    title: str
    class_name: str
    subject_name: str | None = None
    scheduled_at: datetime
    status: str


class MentorAttendanceSummary(BaseModel):
    present: int
    absent: int
    late: int
    excused: int
    total: int
    percentage: float | None = None


class MentorSubjectAttendance(MentorAttendanceSummary):
    subject_id: uuid.UUID
    subject_code: str
    subject_name: str


class MentorMenteeResult(BaseModel):
    publication_id: uuid.UUID
    title: str
    published_at: datetime
    total_marks_obtained: float
    total_marks_possible: float
    percentage: float
    grade: str
    rank: int | None = None
    result: str


class MentorMenteeCoursework(BaseModel):
    id: uuid.UUID
    title: str
    subject_name: str | None = None
    due_date: datetime
    status: str
    submission_status: str | None = None
    score: float | None = None
    is_overdue: bool


class MentorMenteeLeave(BaseModel):
    id: uuid.UUID
    from_date: date
    to_date: date
    reason: str
    status: str


class MentorMenteeGuardian(BaseModel):
    name: str | None = None
    relation: str
    phone: str | None = None
    email: str | None = None
    is_primary: bool


class MentorMenteeDetail(BaseModel):
    profile: MentorMenteeRow
    gender: str | None = None
    date_of_birth: date | None = None
    address: str | None = None
    guardians: list[MentorMenteeGuardian] = Field(default_factory=list)
    attendance: MentorAttendanceSummary
    subjects: list[MentorSubjectAttendance] = Field(default_factory=list)
    results: list[MentorMenteeResult] = Field(default_factory=list)
    coursework: list[MentorMenteeCoursework] = Field(default_factory=list)
    upcoming_exams: list[MentorExamRow] = Field(default_factory=list)
    leaves: list[MentorMenteeLeave] = Field(default_factory=list)
    notes: list[MentorNoteRow] = Field(default_factory=list)


class MentorDashboard(BaseModel):
    academic_year: str | None = None
    attendance_threshold: int | None = None
    mentee_count: int
    direct_count: int
    team_count: int
    class_count: int
    average_attendance: float | None = None
    at_risk_count: int
    pending_leave_count: int
    upcoming_exam_count: int
    notes_this_month: int
    at_risk_mentees: list[MentorMenteeRow] = Field(default_factory=list)
    recent_notes: list[MentorNoteRow] = Field(default_factory=list)
    upcoming_exams: list[MentorExamRow] = Field(default_factory=list)
    classes: list[MentorClassRow] = Field(default_factory=list)
    teams: list[MentorTeamRow] = Field(default_factory=list)


class MentorNoticePage(PrincipalPage):
    items: list[LeadershipNoticeRow]


# ── Envelopes ───────────────────────────────────────────────────────────────

APIResponseMentorBoard = APIResponse[MentorManagementBoard]
APIResponseMentorDashboard = APIResponse[MentorDashboard]
APIResponseMentorMentees = APIResponse[MentorMenteeList]
APIResponseMentorMentee = APIResponse[MentorMenteeDetail]
APIResponseMentorClasses = APIResponse[list[MentorClassRow]]
APIResponseMentorTeams = APIResponse[list[MentorTeamRow]]
APIResponseMentorTeam = APIResponse[MentorTeamDetail]
APIResponseMentorNotes = APIResponse[MentorNotePage]
APIResponseMentorNote = APIResponse[MentorNoteRow]
APIResponseMentorNotices = APIResponse[MentorNoticePage]
APIResponseMentorNotice = APIResponse[LeadershipNoticeRow]
