"""Wire contracts for the Teacher console (C-TC-01 … C-TC-22).

Snake_case payloads, matching every other institution console client
(``fontend/lib/teacher.ts`` mirrors these one-to-one).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import APIResponse
from app.schemas.principal import NoticeAttachment, NoticeAttachmentInput
from app.schemas.student import (
    StudentGroupMessageOut,
    StudentGroupResourceOut,
    StudentGroupTaskOut,
)


# ── Shared shapes ───────────────────────────────────────────────────────────


class TeacherPage(BaseModel):
    total: int
    limit: int
    offset: int


class TeachingAssignment(BaseModel):
    """One subject the signed-in teacher teaches (teacher_subjects row)."""

    subject_id: uuid.UUID
    subject_code: str
    subject_name: str
    class_id: uuid.UUID
    class_name: str
    department_id: uuid.UUID | None = None
    department_name: str | None = None
    role_in_subject: str
    is_class_teacher: bool = False


class TeacherTargetOption(BaseModel):
    id: uuid.UUID
    name: str


# ── C-TC-01 dashboard / C-TC-02 schedule ───────────────────────────────────


class TeacherScheduleSlot(BaseModel):
    id: uuid.UUID
    day_of_week: int
    period_number: int
    start_time: time
    end_time: time
    class_id: uuid.UUID
    class_name: str
    subject_id: uuid.UUID | None = None
    subject_code: str | None = None
    subject_name: str | None = None
    room_no: str | None = None
    slot_type: str


class TeacherUpcomingExam(BaseModel):
    id: uuid.UUID
    title: str
    class_name: str
    subject_name: str
    scheduled_at: datetime
    status: str


class TeacherNoticeRow(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    author_name: str | None = None
    target_scope: str
    target_id: uuid.UUID | None = None
    target_name: str | None = None
    priority: str
    is_pinned: bool
    published_at: datetime
    expires_at: datetime | None = None
    mine: bool = False
    attachments: list[NoticeAttachment] = Field(default_factory=list)


class TeacherDashboard(BaseModel):
    academic_year: str | None = None
    teacher_name: str
    teaching_assignment_count: int
    today_periods: list[TeacherScheduleSlot] = Field(default_factory=list)
    pending_submission_count: int
    pending_unreviewed_submissions: int
    upcoming_exam_count: int
    upcoming_exams: list[TeacherUpcomingExam] = Field(default_factory=list)
    active_assignment_count: int
    pending_leave_count: int
    recent_notices: list[TeacherNoticeRow] = Field(default_factory=list)


class TeacherSchedule(BaseModel):
    academic_year: str | None = None
    assignments: list[TeachingAssignment] = Field(default_factory=list)
    slots: list[TeacherScheduleSlot] = Field(default_factory=list)


# ── C-TC-03 … C-TC-05 attendance ───────────────────────────────────────────


class AttendanceRosterEntry(BaseModel):
    student_id: uuid.UUID
    student_name: str
    roll_number: str | None = None
    status: str | None = None
    late_by_minutes: int | None = None
    remarks: str | None = None


class AttendanceRecordIn(BaseModel):
    student_id: uuid.UUID
    status: Literal["PRESENT", "ABSENT", "LATE", "EXCUSED"]
    late_by_minutes: int | None = Field(default=None, ge=0, le=600)
    remarks: str | None = Field(default=None, max_length=255)


class AttendanceSessionUpsert(BaseModel):
    class_id: uuid.UUID
    subject_id: uuid.UUID
    date: date
    period_label: str = Field(..., min_length=1, max_length=30)
    start_time: time | None = None
    end_time: time | None = None
    notes: str | None = Field(default=None, max_length=5000)
    records: list[AttendanceRecordIn] = Field(default_factory=list)


class TeacherAttendanceSessionRow(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    class_name: str
    subject_id: uuid.UUID
    subject_code: str
    subject_name: str
    date: date
    period_label: str
    total_present: int
    total_absent: int
    is_locked: bool
    locked_at: datetime | None = None
    notes: str | None = None


class TeacherAttendanceSessionPage(TeacherPage):
    items: list[TeacherAttendanceSessionRow]


class TeacherAttendanceSessionDetail(TeacherAttendanceSessionRow):
    start_time: time | None = None
    end_time: time | None = None
    records: list[AttendanceRosterEntry] = Field(default_factory=list)


class TeacherAttendanceBoard(BaseModel):
    """Everything the mark-attendance screen needs in one load (C-TC-03)."""

    assignments: list[TeachingAssignment] = Field(default_factory=list)
    roster: list[AttendanceRosterEntry] = Field(default_factory=list)
    existing_session: TeacherAttendanceSessionDetail | None = None


# ── C-TC-06 student leave review ────────────────────────────────────────────


class TeacherLeaveRow(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    roll_number: str | None = None
    class_id: uuid.UUID
    class_name: str
    from_date: date
    to_date: date
    reason: str
    document_url: str | None = None
    status: str
    reviewed_at: datetime | None = None
    created_at: datetime
    #: Who filed it. A "fever, 3 days" from the guardian and the same words from
    #: the student are different pieces of evidence, and the teacher is the one
    #: who has to weigh them.
    request_source: str = "STUDENT"
    requested_by_name: str | None = None


class TeacherLeavePage(TeacherPage):
    pending_count: int
    items: list[TeacherLeaveRow]


class TeacherLeaveReview(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]


# ── C-TC-07 … C-TC-11 examinations ─────────────────────────────────────────


class TeacherExamCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    subject_id: uuid.UUID
    class_id: uuid.UUID
    exam_type: Literal["MCQ", "DESCRIPTIVE", "MIXED", "QUIZ"] = "MIXED"
    mode: Literal["ONLINE", "OFFLINE"] = "ONLINE"
    total_marks: int = Field(..., ge=1, le=1000)
    passing_marks: int = Field(..., ge=0)
    duration_minutes: int = Field(..., ge=5, le=600)
    instructions: str | None = Field(default=None, max_length=20_000)
    scheduled_at: datetime
    window_end_at: datetime | None = None
    allow_review: bool = False
    show_score_immediately: bool = False
    shuffle_questions: bool = False

    @field_validator("scheduled_at", "window_end_at")
    @classmethod
    def must_be_tz_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("datetime must include a timezone")
        return value


class TeacherExamUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    exam_type: Literal["MCQ", "DESCRIPTIVE", "MIXED", "QUIZ"] | None = None
    mode: Literal["ONLINE", "OFFLINE"] | None = None
    total_marks: int | None = Field(default=None, ge=1, le=1000)
    passing_marks: int | None = Field(default=None, ge=0)
    duration_minutes: int | None = Field(default=None, ge=5, le=600)
    instructions: str | None = Field(default=None, max_length=20_000)
    scheduled_at: datetime | None = None
    window_end_at: datetime | None = None
    allow_review: bool | None = None
    show_score_immediately: bool | None = None
    shuffle_questions: bool | None = None

    @field_validator("scheduled_at", "window_end_at")
    @classmethod
    def must_be_tz_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("datetime must include a timezone")
        return value


class TeacherExamRow(BaseModel):
    id: uuid.UUID
    title: str
    class_id: uuid.UUID
    class_name: str
    subject_id: uuid.UUID
    subject_code: str
    subject_name: str
    exam_type: str
    mode: str
    total_marks: int
    passing_marks: int
    duration_minutes: int
    scheduled_at: datetime
    window_end_at: datetime | None = None
    status: str
    question_count: int = 0
    attempt_count: int = 0
    pending_grading_count: int = 0


class TeacherExamPage(TeacherPage):
    items: list[TeacherExamRow]


class TeacherQuestionOptionIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    image_url: str | None = None
    is_correct: bool = False
    sort_order: int = 0


class TeacherQuestionIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=20_000)
    question_type: Literal["MCQ", "SHORT_ANSWER", "LONG_ANSWER", "TRUE_FALSE", "FILL_BLANK", "MATCH"]
    marks: float = Field(..., gt=0, le=1000)
    negative_marks: float = Field(default=0, ge=0, le=1000)
    image_url: str | None = None
    explanation: str | None = Field(default=None, max_length=5000)
    difficulty: Literal["EASY", "MEDIUM", "HARD"] | None = None
    options: list[TeacherQuestionOptionIn] = Field(default_factory=list)


class TeacherQuestionUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=20_000)
    marks: float | None = Field(default=None, gt=0, le=1000)
    negative_marks: float | None = Field(default=None, ge=0, le=1000)
    image_url: str | None = None
    explanation: str | None = Field(default=None, max_length=5000)
    difficulty: Literal["EASY", "MEDIUM", "HARD"] | None = None
    options: list[TeacherQuestionOptionIn] | None = None


class TeacherQuestionOptionOut(BaseModel):
    id: uuid.UUID
    text: str
    image_url: str | None = None
    is_correct: bool
    sort_order: int


class TeacherQuestionOut(BaseModel):
    id: uuid.UUID
    text: str
    question_type: str
    marks: float
    negative_marks: float
    image_url: str | None = None
    explanation: str | None = None
    difficulty: str | None = None
    sort_order: int
    options: list[TeacherQuestionOptionOut] = Field(default_factory=list)


class TeacherQuestionBankItemIn(BaseModel):
    subject_id: uuid.UUID | None = None
    class_id: uuid.UUID | None = None
    text: str = Field(..., min_length=1, max_length=20_000)
    question_type: Literal["MCQ", "SHORT_ANSWER", "LONG_ANSWER", "TRUE_FALSE", "FILL_BLANK", "MATCH"]
    default_marks: float = Field(default=1.0, gt=0, le=1000)
    negative_marks: float = Field(default=0.0, ge=0, le=1000)
    options: list[TeacherQuestionOptionIn] = Field(default_factory=list)
    image_url: str | None = None
    explanation: str | None = Field(default=None, max_length=5000)
    difficulty: Literal["EASY", "MEDIUM", "HARD"] | None = None
    tags: list[str] = Field(default_factory=list)


class TeacherQuestionBankItemUpdate(BaseModel):
    """Partial update — all fields are optional."""

    subject_id: uuid.UUID | None = None
    class_id: uuid.UUID | None = None
    text: str | None = Field(default=None, min_length=1, max_length=20_000)
    question_type: Literal["MCQ", "SHORT_ANSWER", "LONG_ANSWER", "TRUE_FALSE", "FILL_BLANK", "MATCH"] | None = None
    default_marks: float | None = Field(default=None, gt=0, le=1000)
    negative_marks: float | None = Field(default=None, ge=0, le=1000)
    options: list[TeacherQuestionOptionIn] | None = None
    image_url: str | None = None
    explanation: str | None = Field(default=None, max_length=5000)
    difficulty: Literal["EASY", "MEDIUM", "HARD"] | None = None
    tags: list[str] | None = None


class TeacherQuestionBankItemOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by: uuid.UUID | None = None
    subject_id: uuid.UUID | None = None
    subject_name: str | None = None
    class_id: uuid.UUID | None = None
    class_name: str | None = None
    text: str
    question_type: str
    default_marks: float
    negative_marks: float
    options: list[dict] = Field(default_factory=list)
    image_url: str | None = None
    explanation: str | None = None
    difficulty: str | None = None
    tags: list[str] = Field(default_factory=list)
    usage_count: int
    created_at: datetime


class TeacherQuestionBankPage(TeacherPage):
    items: list[TeacherQuestionBankItemOut]


class TeacherQuestionBankImportIn(BaseModel):
    bank_item_ids: list[uuid.UUID] = Field(..., min_length=1)


class TeacherExamDetail(TeacherExamRow):
    instructions: str | None = None
    allow_review: bool
    show_score_immediately: bool
    shuffle_questions: bool
    created_at: datetime
    questions: list[TeacherQuestionOut] = Field(default_factory=list)


class TeacherAnswerGradeIn(BaseModel):
    answer_id: uuid.UUID
    score: float = Field(..., ge=0, le=1000)
    feedback: str | None = Field(default=None, max_length=5000)


class TeacherGradeSubmission(BaseModel):
    grades: list[TeacherAnswerGradeIn] = Field(..., min_length=1)


class TeacherAttemptRow(BaseModel):
    attempt_id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    roll_number: str | None = None
    status: str
    started_at: datetime
    submitted_at: datetime | None = None
    total_score: float | None = None
    percentage: float | None = None
    grade: str | None = None
    tab_switch_count: int
    pending_grading_count: int = 0


class TeacherAttemptPage(TeacherPage):
    items: list[TeacherAttemptRow]


class TeacherAnswerOption(BaseModel):
    """One option of the question's answer key, shown in the grading panel."""

    id: uuid.UUID
    text: str
    is_correct: bool
    sort_order: int = 0


class TeacherAnswerRow(BaseModel):
    answer_id: uuid.UUID
    question_id: uuid.UUID
    question_text: str
    question_type: str
    marks: float
    selected_option_id: uuid.UUID | None = None
    selected_option_text: str | None = None
    correct_option_text: str | None = None
    # Full option list (answer key context) — lets the reviewer see every
    # option, which is correct and which the student picked.
    options: list[TeacherAnswerOption] = Field(default_factory=list)
    text_answer: str | None = None
    # MATCH-type answers store pairings as JSONB instead of plain text.
    matched_pairs: dict | None = None
    score: float | None = None
    feedback: str | None = None
    is_auto_graded: bool


class TeacherAttemptDetail(TeacherAttemptRow):
    answers: list[TeacherAnswerRow] = Field(default_factory=list)


# ── C-TC-12 … C-TC-16 assignments ──────────────────────────────────────────


class TeacherAssignmentCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    description: str = Field(..., min_length=1, max_length=20_000)
    subject_id: uuid.UUID
    class_id: uuid.UUID
    assignment_type: Literal["REGULAR", "MILESTONE", "GROUP"] = "REGULAR"
    total_marks: int = Field(..., ge=1, le=1000)
    passing_marks: int = Field(..., ge=0)
    due_date: datetime
    allow_late_submission: bool = False
    late_penalty_percent: int = Field(default=0, ge=0, le=100)
    max_file_size_mb: int = Field(default=10, ge=1, le=100)
    allowed_file_types: list[str] = Field(default_factory=lambda: ["pdf", "doc", "docx", "zip"])
    min_group_size: int = Field(default=2, ge=2, le=50)
    max_group_size: int = Field(default=6, ge=2, le=50)
    instructions_url: str | None = None
    publish: bool = True

    @field_validator("due_date")
    @classmethod
    def due_must_be_tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("due_date must include a timezone")
        return value


class TeacherAssignmentReopen(BaseModel):
    """Optional body for POST /assignments/{id}/reopen.

    ``request_resubmission`` (default true) also moves every un-reviewed
    submission (SUBMITTED / UNDER_REVIEW — latest version per student and
    milestone scope) to RESUBMIT_REQUESTED, handing the work back to students:
    the close → reopen → resubmit loop.  Set it to false to reopen only for
    students who never submitted.
    """

    request_resubmission: bool = True


class TeacherAssignmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=20_000)
    assignment_type: Literal["REGULAR", "MILESTONE", "GROUP"] | None = None
    total_marks: int | None = Field(default=None, ge=1, le=1000)
    passing_marks: int | None = Field(default=None, ge=0)
    due_date: datetime | None = None
    allow_late_submission: bool | None = None
    late_penalty_percent: int | None = Field(default=None, ge=0, le=100)
    max_file_size_mb: int | None = Field(default=None, ge=1, le=100)
    allowed_file_types: list[str] | None = None
    min_group_size: int | None = Field(default=None, ge=2, le=50)
    max_group_size: int | None = Field(default=None, ge=2, le=50)
    instructions_url: str | None = None

    @field_validator("due_date")
    @classmethod
    def due_must_be_tz_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("due_date must include a timezone")
        return value


class TeacherMilestoneIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    marks: int = Field(..., ge=0, le=1000)
    due_date: datetime | None = None
    unlock_after_milestone_id: uuid.UUID | None = None

    @field_validator("due_date")
    @classmethod
    def due_must_be_tz_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("due_date must include a timezone")
        return value


class TeacherMilestoneUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    marks: int | None = Field(default=None, ge=0, le=1000)
    due_date: datetime | None = None

    @field_validator("due_date")
    @classmethod
    def due_must_be_tz_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("due_date must include a timezone")
        return value


class TeacherMilestoneOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    sort_order: int
    marks: int
    due_date: datetime | None = None
    unlock_after_milestone_id: uuid.UUID | None = None


class TeacherGroupMember(BaseModel):
    student_id: uuid.UUID
    student_name: str
    roll_number: str | None = None
    joined_at: datetime


class TeacherGroupRow(BaseModel):
    id: uuid.UUID
    assignment_id: uuid.UUID
    name: str
    created_by: uuid.UUID | None = None
    creator_name: str | None = None
    created_at: datetime
    member_count: int = 0
    is_submitted: bool = False
    submission_id: uuid.UUID | None = None
    tasks_count: int = 0
    tasks_done_count: int = 0
    messages_count: int = 0
    resources_count: int = 0
    members: list[TeacherGroupMember] = Field(default_factory=list)


class TeacherGroupPage(TeacherPage):
    items: list[TeacherGroupRow]


class TeacherTeamWorkspace(BaseModel):
    group: TeacherGroupRow
    assignment_id: uuid.UUID
    assignment_title: str
    class_name: str
    subject_code: str
    subject_name: str
    due_date: datetime
    tasks: list[StudentGroupTaskOut] = Field(default_factory=list)
    messages: list[StudentGroupMessageOut] = Field(default_factory=list)
    resources: list[StudentGroupResourceOut] = Field(default_factory=list)
    submission: TeacherSubmissionDetail | None = None


class TeacherAssignmentRow(BaseModel):
    id: uuid.UUID
    title: str
    class_id: uuid.UUID
    class_name: str
    subject_id: uuid.UUID
    subject_code: str
    subject_name: str
    assignment_type: str
    total_marks: int
    due_date: datetime
    status: str
    milestone_count: int = 0
    student_count: int = 0
    group_count: int = 0
    submission_count: int = 0
    pending_review_count: int = 0
    reviewed_count: int = 0


class TeacherAssignmentPage(TeacherPage):
    items: list[TeacherAssignmentRow]


class TeacherAssignmentDetail(TeacherAssignmentRow):
    description: str
    passing_marks: int
    allow_late_submission: bool
    late_penalty_percent: int
    max_file_size_mb: int
    allowed_file_types: list[str]
    min_group_size: int = 2
    max_group_size: int = 6
    instructions_url: str | None = None
    created_at: datetime
    milestones: list[TeacherMilestoneOut] = Field(default_factory=list)


class TeacherSubmissionRow(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    roll_number: str | None = None
    group_id: uuid.UUID | None = None
    group_name: str | None = None
    milestone_id: uuid.UUID | None = None
    milestone_title: str | None = None
    milestone_marks: int | None = None
    submitted_at: datetime
    is_late: bool
    late_by_minutes: int | None = None
    status: str
    score: float | None = None
    grade: str | None = None
    version: int


class TeacherSubmissionPage(TeacherPage):
    items: list[TeacherSubmissionRow]


class TeacherSubmissionFileOut(BaseModel):
    id: uuid.UUID
    file_name: str
    file_key: str
    file_size_bytes: int
    mime_type: str
    uploaded_at: datetime


class TeacherReviewHistoryRow(BaseModel):
    id: uuid.UUID
    reviewer_name: str | None = None
    decision: str
    marks_awarded: float | None = None
    feedback: str | None = None
    attempt_number: int
    reviewed_at: datetime


class TeacherSubmissionDetail(TeacherSubmissionRow):
    assignment_id: uuid.UUID
    assignment_title: str
    total_marks: int
    text_response: str | None = None
    feedback: str | None = None
    files: list[TeacherSubmissionFileOut] = Field(default_factory=list)
    reviews: list[TeacherReviewHistoryRow] = Field(default_factory=list)


class TeacherSubmissionReviewIn(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "CHANGES_REQUESTED"]
    score: float | None = Field(default=None, ge=0, le=1000)
    feedback: str | None = Field(default=None, max_length=5000)


# ── C-TC-17 / C-TC-18 content ───────────────────────────────────────────────


class TeacherContentIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    subject_id: uuid.UUID
    class_id: uuid.UUID
    content_type: Literal["PDF", "VIDEO", "SLIDE", "LINK", "IMAGE", "AUDIO", "ZIP"]
    file_key: str | None = None
    external_url: str | None = None
    file_size_bytes: int | None = Field(default=None, ge=0)
    duration_seconds: int | None = Field(default=None, ge=0)
    chapter: str | None = Field(default=None, max_length=100)
    tags: list[str] = Field(default_factory=list)
    is_visible: bool = True


class TeacherContentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    content_type: Literal["PDF", "VIDEO", "SLIDE", "LINK", "IMAGE", "AUDIO", "ZIP"] | None = None
    file_key: str | None = None
    external_url: str | None = None
    file_size_bytes: int | None = Field(default=None, ge=0)
    duration_seconds: int | None = Field(default=None, ge=0)
    chapter: str | None = Field(default=None, max_length=100)
    tags: list[str] | None = None
    is_visible: bool | None = None


class TeacherContentRow(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    subject_id: uuid.UUID
    subject_code: str
    subject_name: str
    class_id: uuid.UUID
    class_name: str
    content_type: str
    file_key: str | None = None
    external_url: str | None = None
    file_size_bytes: int | None = None
    duration_seconds: int | None = None
    chapter: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_visible: bool
    download_count: int
    view_count: int
    created_at: datetime


class TeacherContentPage(TeacherPage):
    items: list[TeacherContentRow]


# ── C-TC-19 / C-TC-20 notices ───────────────────────────────────────────────


class TeacherNoticeCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    body: str = Field(..., min_length=1, max_length=20_000)
    class_id: uuid.UUID
    priority: Literal["NORMAL", "IMPORTANT", "URGENT"] = "NORMAL"
    expires_at: datetime | None = None
    attachments: list[NoticeAttachmentInput] = Field(default_factory=list, max_length=5)

    @field_validator("expires_at")
    @classmethod
    def expiry_must_be_tz_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("expires_at must include a timezone")
        return value


class TeacherNoticePage(TeacherPage):
    items: list[TeacherNoticeRow]


# ── C-TC-21 / C-TC-22 discussion ────────────────────────────────────────────


class TeacherThreadRow(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    author_id: uuid.UUID | None = None
    author_name: str | None = None
    mine: bool = False
    scope_type: str
    scope_id: uuid.UUID
    scope_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_pinned: bool
    is_locked: bool
    is_resolved: bool
    reply_count: int
    upvote_count: int
    view_count: int = 0
    can_moderate: bool = False
    created_at: datetime
    updated_at: datetime


class TeacherThreadPage(TeacherPage):
    items: list[TeacherThreadRow]


class TeacherThreadCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    body: str = Field(..., min_length=1, max_length=20_000)
    scope_type: Literal["CLASS", "SUBJECT"]
    scope_id: uuid.UUID
    tags: list[str] = Field(default_factory=list, max_length=5)


class TeacherReplyCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=10_000)


class TeacherReplyRow(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID | None = None
    author_name: str | None = None
    mine: bool = False
    body: str
    is_accepted_answer: bool
    upvote_count: int
    created_at: datetime


class TeacherThreadDetail(TeacherThreadRow):
    replies: list[TeacherReplyRow] = Field(default_factory=list)


class TeacherThreadModeration(BaseModel):
    action: Literal["PIN", "UNPIN", "LOCK", "UNLOCK", "DELETE"]


# ── Envelopes ───────────────────────────────────────────────────────────────


APIResponseTeacherDashboard = APIResponse[TeacherDashboard]
APIResponseTeacherSchedule = APIResponse[TeacherSchedule]
APIResponseTeacherAssignments = APIResponse[list[TeachingAssignment]]
APIResponseTeacherAttendanceBoard = APIResponse[TeacherAttendanceBoard]
APIResponseTeacherAttendanceSessions = APIResponse[TeacherAttendanceSessionPage]
APIResponseTeacherAttendanceSession = APIResponse[TeacherAttendanceSessionDetail]
APIResponseTeacherLeaves = APIResponse[TeacherLeavePage]
APIResponseTeacherLeave = APIResponse[TeacherLeaveRow]
APIResponseTeacherExams = APIResponse[TeacherExamPage]
APIResponseTeacherExam = APIResponse[TeacherExamDetail]
APIResponseTeacherQuestion = APIResponse[TeacherQuestionOut]
APIResponseTeacherAttempts = APIResponse[TeacherAttemptPage]
APIResponseTeacherAttempt = APIResponse[TeacherAttemptDetail]
APIResponseTeacherAssignmentList = APIResponse[TeacherAssignmentPage]
APIResponseTeacherAssignment = APIResponse[TeacherAssignmentDetail]
APIResponseTeacherMilestone = APIResponse[TeacherMilestoneOut]
APIResponseTeacherGroups = APIResponse[TeacherGroupPage]
APIResponseTeacherGroup = APIResponse[TeacherGroupRow]
APIResponseTeacherTeamWorkspace = APIResponse[TeacherTeamWorkspace]
APIResponseTeacherSubmissions = APIResponse[TeacherSubmissionPage]
APIResponseTeacherSubmission = APIResponse[TeacherSubmissionDetail]
APIResponseTeacherContents = APIResponse[TeacherContentPage]
APIResponseTeacherContent = APIResponse[TeacherContentRow]
APIResponseTeacherNotices = APIResponse[TeacherNoticePage]
APIResponseTeacherNotice = APIResponse[TeacherNoticeRow]
APIResponseTeacherNoticeTargets = APIResponse[list[TeacherTargetOption]]
APIResponseTeacherThreads = APIResponse[TeacherThreadPage]
APIResponseTeacherThread = APIResponse[TeacherThreadDetail]
APIResponseTeacherReply = APIResponse[TeacherReplyRow]
APIResponseTeacherQuestionBankList = APIResponse[TeacherQuestionBankPage]
APIResponseTeacherQuestionBankItem = APIResponse[TeacherQuestionBankItemOut]
