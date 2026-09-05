"""Wire contracts for the Student console (C-ST-01 … C-ST-20).

Every response is scoped to the signed-in student's own enrollment; nothing
here accepts a student id — the caller *is* the scope.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal, ClassVar

from pydantic import BaseModel, Field

from app.schemas.common import APIResponse


class StudentPage(BaseModel):
    total: int
    limit: int
    offset: int


class StudentClassInfo(BaseModel):
    class_id: uuid.UUID | None = None
    class_name: str | None = None
    department_id: uuid.UUID | None = None
    department_name: str | None = None
    academic_year_id: uuid.UUID | None = None
    academic_year: str | None = None
    roll_number: str | None = None


# ── C-ST-01 dashboard / C-ST-02 profile ────────────────────────────────────


class StudentNextExam(BaseModel):
    id: uuid.UUID
    title: str
    subject_name: str
    subject_code: str
    scheduled_at: datetime
    total_marks: int
    duration_minutes: int
    status: str


class StudentPendingAssignment(BaseModel):
    id: uuid.UUID
    title: str
    subject_name: str
    due_date: datetime
    total_marks: int


class StudentTimetableSlot(BaseModel):
    id: uuid.UUID
    day_of_week: int
    period_number: int
    start_time: time
    end_time: time
    subject_id: uuid.UUID | None = None
    subject_code: str | None = None
    subject_name: str | None = None
    teacher_name: str | None = None
    room_no: str | None = None
    slot_type: str


class StudentNoticeRow(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    author_name: str | None = None
    target_scope: str
    target_name: str | None = None
    priority: str
    is_pinned: bool
    published_at: datetime
    expires_at: datetime | None = None
    is_read: bool = False


class StudentDashboard(BaseModel):
    student_name: str
    class_info: StudentClassInfo
    attendance_percentage: float | None = None
    attendance_marks: int
    next_exam: StudentNextExam | None = None
    upcoming_exam_count: int
    pending_assignment_count: int
    pending_assignments: list[StudentPendingAssignment] = Field(default_factory=list)
    today_periods: list[StudentTimetableSlot] = Field(default_factory=list)
    recent_notices: list[StudentNoticeRow] = Field(default_factory=list)
    fee_balance_due: float | None = None


class StudentProfile(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    student_roll_no: str | None = None
    class_info: StudentClassInfo
    class_teacher_name: str | None = None


class StudentProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    avatar_url: str | None = None


# ── C-ST-03 … C-ST-05 attendance & leave ───────────────────────────────────


class StudentSubjectAttendance(BaseModel):
    subject_id: uuid.UUID
    subject_code: str
    subject_name: str
    present_count: int
    absent_count: int
    late_count: int
    excused_count: int
    total_marks: int
    attendance_percentage: float | None = None


class StudentAttendanceSummary(BaseModel):
    attendance_percentage: float | None = None
    total_marks: int
    present_count: int
    absent_count: int
    late_count: int
    excused_count: int
    subjects: list[StudentSubjectAttendance] = Field(default_factory=list)


class StudentAttendanceEntry(BaseModel):
    status: str
    subject_code: str
    subject_name: str
    period_label: str


class StudentAttendanceDay(BaseModel):
    date: date
    entries: list[StudentAttendanceEntry] = Field(default_factory=list)


class StudentAttendanceCalendar(BaseModel):
    month: str
    days: list[StudentAttendanceDay] = Field(default_factory=list)


class StudentLeaveRow(BaseModel):
    id: uuid.UUID
    from_date: date
    to_date: date
    reason: str
    document_url: str | None = None
    status: str
    reviewed_at: datetime | None = None
    created_at: datetime


class StudentLeaveCreate(BaseModel):
    from_date: date
    to_date: date
    reason: str = Field(..., min_length=3, max_length=5000)
    document_url: str | None = None


class StudentLeavePage(StudentPage):
    items: list[StudentLeaveRow]


# ── C-ST-06 timetable ───────────────────────────────────────────────────────


class StudentTimetable(BaseModel):
    class_info: StudentClassInfo
    slots: list[StudentTimetableSlot] = Field(default_factory=list)


# ── C-ST-07 … C-ST-09 examinations ─────────────────────────────────────────


class StudentExamRow(BaseModel):
    id: uuid.UUID
    title: str
    subject_name: str
    subject_code: str
    exam_type: str
    mode: str
    total_marks: int
    passing_marks: int
    duration_minutes: int
    scheduled_at: datetime
    window_end_at: datetime | None = None
    status: str
    my_attempt_status: str | None = None
    my_score: float | None = None
    can_attempt: bool = False
    result_available: bool = False


class StudentExamPage(StudentPage):
    items: list[StudentExamRow]


class StudentExamDetail(StudentExamRow):
    instructions: str | None = None
    question_count: int = 0
    allow_review: bool
    show_score_immediately: bool
    attempt_id: uuid.UUID | None = None
    attempt_started_at: datetime | None = None
    attempt_submitted_at: datetime | None = None


class StudentAttemptState(BaseModel):
    attempt_id: uuid.UUID
    exam_id: uuid.UUID
    started_at: datetime
    duration_minutes: int
    ends_at: datetime
    status: str


class StudentTabSwitch(BaseModel):
    """C-ST-08: the anti-cheat counter the attempt screen reports against."""

    tab_switch_count: int


class StudentAttemptOption(BaseModel):
    id: uuid.UUID
    text: str
    image_url: str | None = None
    sort_order: int


class StudentAttemptQuestion(BaseModel):
    id: uuid.UUID
    text: str
    question_type: str
    marks: float
    image_url: str | None = None
    sort_order: int
    options: list[StudentAttemptOption] = Field(default_factory=list)
    my_selected_option_id: uuid.UUID | None = None
    my_text_answer: str | None = None


class StudentAttemptPaper(BaseModel):
    attempt: StudentAttemptState
    questions: list[StudentAttemptQuestion] = Field(default_factory=list)


class StudentAnswerSave(BaseModel):
    question_id: uuid.UUID
    selected_option_id: uuid.UUID | None = None
    text_answer: str | None = Field(default=None, max_length=20_000)


class StudentResultAnswer(BaseModel):
    question_id: uuid.UUID
    question_text: str
    question_type: str
    marks: float
    selected_option_id: uuid.UUID | None = None
    selected_option_text: str | None = None
    correct_option_id: uuid.UUID | None = None
    correct_option_text: str | None = None
    text_answer: str | None = None
    score: float | None = None
    feedback: str | None = None


class StudentExamResult(BaseModel):
    """One exam's result from the student's point of view.

    ``result_state`` is the typed lifecycle the UI renders — clients must not
    string-match error prose:

    * ``NOT_ATTEMPTED``    — the student never started (or is still writing).
    * ``IN_PROGRESS``      — attempt open, exam still being written.
    * ``UNDER_EVALUATION`` — submitted; the teacher has not released results.
    * ``AVAILABLE``        — released (or early review allowed); scores and
      the optional answer review are included.
    """

    # ClassVar: constants for callers, not pydantic fields.
    RESULT_NOT_ATTEMPTED: ClassVar[str] = "NOT_ATTEMPTED"
    RESULT_IN_PROGRESS: ClassVar[str] = "IN_PROGRESS"
    RESULT_UNDER_EVALUATION: ClassVar[str] = "UNDER_EVALUATION"
    RESULT_AVAILABLE: ClassVar[str] = "AVAILABLE"

    exam_id: uuid.UUID
    title: str
    subject_name: str
    total_marks: int
    passing_marks: int
    status: str
    result_state: str = RESULT_AVAILABLE
    total_score: float | None = None
    percentage: float | None = None
    grade: str | None = None
    submitted_at: datetime | None = None
    show_answers: bool = False
    answers: list[StudentResultAnswer] = Field(default_factory=list)


# ── C-ST-10 … C-ST-12 assignments ──────────────────────────────────────────


class StudentAssignmentRow(BaseModel):
    id: uuid.UUID
    title: str
    subject_name: str
    subject_code: str
    teacher_name: str | None = None
    assignment_type: str
    total_marks: int
    due_date: datetime
    status: str
    my_status: str  # PENDING | SUBMITTED | UNDER_REVIEW | APPROVED | REJECTED | RESUBMIT_REQUESTED
    my_score: float | None = None
    my_submitted_at: datetime | None = None
    is_late: bool = False


class StudentAssignmentPage(StudentPage):
    items: list[StudentAssignmentRow]


class StudentMilestoneProgress(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    sort_order: int
    marks: int
    due_date: datetime | None = None
    unlocked: bool
    my_status: str | None = None
    my_score: float | None = None
    my_submitted_at: datetime | None = None


class StudentSubmissionFileIn(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    file_key: str = Field(..., min_length=1)
    file_size_bytes: int = Field(..., ge=0)
    mime_type: str = Field(..., min_length=1, max_length=100)


class StudentSubmissionFileOut(BaseModel):
    id: uuid.UUID
    file_name: str
    file_key: str
    file_size_bytes: int
    mime_type: str
    uploaded_at: datetime


class StudentGroupMember(BaseModel):
    student_id: uuid.UUID
    student_name: str
    roll_number: str | None = None
    is_me: bool = False
    joined_at: datetime


class StudentGroupRow(BaseModel):
    id: uuid.UUID
    assignment_id: uuid.UUID
    name: str
    created_by: uuid.UUID | None = None
    creator_name: str | None = None
    member_count: int = 0
    is_my_group: bool = False
    is_submitted: bool = False
    members: list[StudentGroupMember] = Field(default_factory=list)


class StudentGroupCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)


class StudentGroupReuseIn(BaseModel):
    previous_group_id: uuid.UUID


class StudentPreviousGroupOption(BaseModel):
    group_id: uuid.UUID
    group_name: str
    assignment_title: str
    subject_name: str
    member_count: int = 0
    members: list[StudentGroupMember] = Field(default_factory=list)


class StudentGroupListOut(BaseModel):
    min_group_size: int = 2
    max_group_size: int = 6
    my_group: StudentGroupRow | None = None
    groups: list[StudentGroupRow] = Field(default_factory=list)
    previous_groups: list[StudentPreviousGroupOption] = Field(default_factory=list)


# ── Team Collaboration & Workspace Facilities ───────────────────────────────

class StudentGroupTaskIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    assigned_to: uuid.UUID | None = None
    due_date: datetime | None = None


class StudentGroupTaskUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    assigned_to: uuid.UUID | None = None
    status: str | None = None
    due_date: datetime | None = None


class StudentGroupTaskOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    title: str
    description: str | None = None
    assigned_to: uuid.UUID | None = None
    assignee_name: str | None = None
    status: str = "TODO"
    due_date: datetime | None = None
    created_by: uuid.UUID | None = None
    creator_name: str | None = None
    created_at: datetime
    updated_at: datetime


class StudentGroupMessageIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class StudentGroupMessageOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    sender_id: uuid.UUID
    sender_name: str
    is_me: bool = False
    message: str
    created_at: datetime


class StudentGroupResourceIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., min_length=1, max_length=2000)
    resource_type: str = "LINK"


class StudentGroupResourceOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    title: str
    url: str
    resource_type: str = "LINK"
    created_by: uuid.UUID | None = None
    creator_name: str | None = None
    created_at: datetime


class StudentMyTeamSummary(BaseModel):
    group_id: uuid.UUID
    assignment_id: uuid.UUID
    group_name: str
    assignment_title: str
    subject_code: str
    subject_name: str
    teacher_name: str | None = None
    due_date: datetime
    is_leader: bool = False
    member_count: int = 0
    min_group_size: int = 2
    max_group_size: int = 6
    is_submitted: bool = False
    submission_status: str | None = None
    score: float | None = None
    total_marks: int = 50
    members: list[StudentGroupMember] = Field(default_factory=list)


class StudentMyTeamDetail(BaseModel):
    group: StudentGroupRow
    assignment: StudentAssignmentDetail
    tasks: list[StudentGroupTaskOut] = Field(default_factory=list)
    messages: list[StudentGroupMessageOut] = Field(default_factory=list)
    resources: list[StudentGroupResourceOut] = Field(default_factory=list)
    pending_invitations: list["StudentGroupInviteOut"] = Field(default_factory=list)


# ── Team Invitations (Leader Invite Teammates) ───────────────────────────────

class StudentGroupInviteIn(BaseModel):
    student_id: uuid.UUID


class StudentGroupInviteResponseIn(BaseModel):
    action: Literal["ACCEPT", "REJECT"]


class StudentEligibleClassmateOut(BaseModel):
    student_id: uuid.UUID
    student_name: str
    roll_number: str | None = None
    already_in_group: bool = False
    has_pending_invite: bool = False


class StudentGroupInviteOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    group_name: str
    assignment_id: uuid.UUID
    assignment_title: str
    subject_name: str
    student_id: uuid.UUID
    student_name: str
    student_roll_number: str | None = None
    invited_by: uuid.UUID
    inviter_name: str
    status: str = "PENDING"
    created_at: datetime


class StudentSubmissionOut(BaseModel):
    id: uuid.UUID
    milestone_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    group_name: str | None = None
    submitted_at: datetime
    is_late: bool
    status: str
    score: float | None = None
    grade: str | None = None
    feedback: str | None = None
    reviewed_at: datetime | None = None
    version: int
    text_response: str | None = None
    files: list[StudentSubmissionFileOut] = Field(default_factory=list)


class StudentAssignmentDetail(StudentAssignmentRow):
    description: str
    passing_marks: int
    allow_late_submission: bool
    max_file_size_mb: int
    allowed_file_types: list[str]
    min_group_size: int = 2
    max_group_size: int = 6
    my_group: StudentGroupRow | None = None
    instructions_url: str | None = None
    milestones: list[StudentMilestoneProgress] = Field(default_factory=list)
    my_submissions: list[StudentSubmissionOut] = Field(default_factory=list)


class StudentSubmissionCreate(BaseModel):
    milestone_id: uuid.UUID | None = None
    text_response: str | None = Field(default=None, max_length=20_000)
    files: list[StudentSubmissionFileIn] = Field(default_factory=list, max_length=10)


# ── C-ST-13 / C-ST-14 content ───────────────────────────────────────────────


class StudentContentRow(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    subject_id: uuid.UUID
    subject_code: str
    subject_name: str
    uploader_name: str | None = None
    content_type: str
    file_key: str | None = None
    external_url: str | None = None
    file_size_bytes: int | None = None
    duration_seconds: int | None = None
    chapter: str | None = None
    tags: list[str] = Field(default_factory=list)
    view_count: int
    download_count: int
    created_at: datetime


class StudentContentPage(StudentPage):
    chapters: list[str] = Field(default_factory=list)
    items: list[StudentContentRow]


# ── C-ST-15 … C-ST-17 results ───────────────────────────────────────────────


class StudentResultRow(BaseModel):
    publication_id: uuid.UUID
    title: str
    academic_year: str | None = None
    class_name: str | None = None
    published_at: datetime
    total_marks_obtained: float
    total_marks_possible: float
    percentage: float
    grade: str
    rank: int | None = None
    result: str
    has_grade_card: bool = False


class StudentSubjectScore(BaseModel):
    subject_name: str
    marks_obtained: float
    marks_possible: float
    grade: str | None = None


class StudentResultDetail(StudentResultRow):
    subject_scores: list[StudentSubjectScore] = Field(default_factory=list)
    remarks: str | None = None
    institution_name: str | None = None


# ── C-ST-18 notices ─────────────────────────────────────────────────────────


class StudentNoticePage(StudentPage):
    unread_count: int
    items: list[StudentNoticeRow]


# ── C-ST-19 discussion ─────────────────────────────────────────────────────


class StudentThreadRow(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    author_name: str | None = None
    mine: bool = False
    scope_type: str
    scope_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_pinned: bool
    is_locked: bool
    is_resolved: bool
    reply_count: int
    upvote_count: int
    my_vote: bool = False
    created_at: datetime
    updated_at: datetime


class StudentThreadPage(StudentPage):
    items: list[StudentThreadRow]


class StudentThreadCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    body: str = Field(..., min_length=1, max_length=20_000)
    scope_type: Literal["CLASS", "SUBJECT"]
    scope_id: uuid.UUID
    tags: list[str] = Field(default_factory=list, max_length=5)


class StudentReplyCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=10_000)


class StudentReplyRow(BaseModel):
    id: uuid.UUID
    author_name: str | None = None
    mine: bool = False
    body: str
    is_accepted_answer: bool
    upvote_count: int
    my_vote: bool = False
    created_at: datetime


class StudentThreadDetail(StudentThreadRow):
    replies: list[StudentReplyRow] = Field(default_factory=list)


class StudentDiscussionScope(BaseModel):
    scope_type: str
    scope_id: uuid.UUID
    name: str


class StudentVoteToggle(BaseModel):
    target_type: Literal["THREAD", "REPLY"]
    target_id: uuid.UUID


# ── C-ST-20 fees ────────────────────────────────────────────────────────────


class StudentFeeInstallment(BaseModel):
    id: uuid.UUID
    installment_number: int
    label: str
    amount: float
    due_date: date
    paid_amount: float
    status: str
    late_fine: float


class StudentFeePayment(BaseModel):
    id: uuid.UUID
    amount: float
    payment_mode: str
    transaction_reference: str | None = None
    payment_date: date
    receipt_number: str
    notes: str | None = None


class StudentScholarshipGrant(BaseModel):
    id: uuid.UUID
    scholarship_name: str | None = None
    amount_granted: float
    granted_at: datetime
    remarks: str | None = None


class StudentFeeAccount(BaseModel):
    academic_year: str | None = None
    total_fee: float
    concession_amount: float
    scholarship_amount: float
    net_payable: float
    total_paid: float
    balance_due: float
    status: str
    installments: list[StudentFeeInstallment] = Field(default_factory=list)
    payments: list[StudentFeePayment] = Field(default_factory=list)
    grants: list[StudentScholarshipGrant] = Field(default_factory=list)


# ── Envelopes ───────────────────────────────────────────────────────────────


APIResponseStudentDashboard = APIResponse[StudentDashboard]
APIResponseStudentProfile = APIResponse[StudentProfile]
APIResponseStudentAttendance = APIResponse[StudentAttendanceSummary]
APIResponseStudentAttendanceCalendar = APIResponse[StudentAttendanceCalendar]
APIResponseStudentLeaves = APIResponse[StudentLeavePage]
APIResponseStudentLeave = APIResponse[StudentLeaveRow]
APIResponseStudentTimetable = APIResponse[StudentTimetable]
APIResponseStudentExams = APIResponse[StudentExamPage]
APIResponseStudentExam = APIResponse[StudentExamDetail]
APIResponseStudentAttempt = APIResponse[StudentAttemptState]
APIResponseStudentTabSwitch = APIResponse[StudentTabSwitch]
APIResponseStudentPaper = APIResponse[StudentAttemptPaper]
APIResponseStudentExamResult = APIResponse[StudentExamResult]
APIResponseStudentAssignments = APIResponse[StudentAssignmentPage]
APIResponseStudentAssignment = APIResponse[StudentAssignmentDetail]
APIResponseStudentGroups = APIResponse[StudentGroupListOut]
APIResponseStudentGroup = APIResponse[StudentGroupRow]
APIResponseStudentTeams = APIResponse[list[StudentMyTeamSummary]]
APIResponseStudentTeamDetail = APIResponse[StudentMyTeamDetail]
APIResponseStudentGroupTask = APIResponse[StudentGroupTaskOut]
APIResponseStudentGroupTasks = APIResponse[list[StudentGroupTaskOut]]
APIResponseStudentGroupMessage = APIResponse[StudentGroupMessageOut]
APIResponseStudentGroupMessages = APIResponse[list[StudentGroupMessageOut]]
APIResponseStudentGroupResource = APIResponse[StudentGroupResourceOut]
APIResponseStudentGroupResources = APIResponse[list[StudentGroupResourceOut]]
APIResponseStudentGroupInvite = APIResponse[StudentGroupInviteOut]
APIResponseStudentGroupInvites = APIResponse[list[StudentGroupInviteOut]]
APIResponseStudentEligibleClassmates = APIResponse[list[StudentEligibleClassmateOut]]
APIResponseStudentSubmission = APIResponse[StudentSubmissionOut]
APIResponseStudentContents = APIResponse[StudentContentPage]
APIResponseStudentContent = APIResponse[StudentContentRow]
APIResponseStudentResults = APIResponse[list[StudentResultRow]]
APIResponseStudentResult = APIResponse[StudentResultDetail]
APIResponseStudentNotices = APIResponse[StudentNoticePage]
APIResponseStudentNotice = APIResponse[StudentNoticeRow]
APIResponseStudentThreads = APIResponse[StudentThreadPage]
APIResponseStudentThread = APIResponse[StudentThreadDetail]
APIResponseStudentScopes = APIResponse[list[StudentDiscussionScope]]
APIResponseStudentFees = APIResponse[StudentFeeAccount]
