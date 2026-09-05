/**
 * Student console API client (C-ST-01 … C-ST-20) — mobile port of
 * fontend/lib/student.ts.
 *
 * The caller is the scope: the server resolves the signed-in student's active
 * enrollment and filters every response through it, so no call here accepts a
 * student id. Snake_case payloads mirror `backend/app/schemas/student.py`.
 */

import { APIError, requestJson } from "./api-client";
import { API_BASE_URL, getAccessToken, refreshAccessToken } from "./auth";

export { APIError as StudentAPIError };

export function queryString(
  values: Record<string, string | number | boolean | undefined | null>,
): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

const call = <T>(path: string, init: RequestInit = {}): Promise<T> =>
  requestJson<T>(
    `${API_BASE_URL}/api/v1/student${path}`,
    init,
    getAccessToken(),
    "StudentAPIError",
    refreshAccessToken,
  );

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export interface StudentPage<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export interface StudentClassInfo {
  class_id: string | null;
  class_name: string | null;
  department_id: string | null;
  department_name: string | null;
  academic_year_id: string | null;
  academic_year: string | null;
  roll_number: string | null;
}

// ── C-ST-01 / C-ST-02 dashboard & profile ───────────────────────────────────

export interface StudentNextExam {
  id: string;
  title: string;
  subject_name: string;
  subject_code: string;
  scheduled_at: string;
  total_marks: number;
  duration_minutes: number;
  status: string;
}

export interface StudentPendingAssignment {
  id: string;
  title: string;
  subject_name: string;
  due_date: string;
  total_marks: number;
}

export interface StudentTimetableSlot {
  id: string;
  day_of_week: number;
  period_number: number;
  start_time: string;
  end_time: string;
  subject_id: string | null;
  subject_code: string | null;
  subject_name: string | null;
  teacher_name: string | null;
  room_no: string | null;
  slot_type: string;
}

export interface StudentNoticeRow {
  id: string;
  title: string;
  body: string;
  author_name: string | null;
  target_scope: string;
  target_name: string | null;
  priority: string;
  is_pinned: boolean;
  published_at: string;
  expires_at: string | null;
  is_read: boolean;
}

export interface StudentDashboard {
  student_name: string;
  class_info: StudentClassInfo;
  attendance_percentage: number | null;
  attendance_marks: number;
  next_exam: StudentNextExam | null;
  upcoming_exam_count: number;
  pending_assignment_count: number;
  pending_assignments: StudentPendingAssignment[];
  today_periods: StudentTimetableSlot[];
  recent_notices: StudentNoticeRow[];
  fee_balance_due: number | null;
}

export interface StudentProfile {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  avatar_url: string | null;
  date_of_birth: string | null;
  gender: string | null;
  student_roll_no: string | null;
  class_info: StudentClassInfo;
  class_teacher_name: string | null;
}

export interface StudentProfileUpdate {
  name?: string;
  phone?: string | null;
  avatar_url?: string | null;
}

export const fetchStudentDashboard = () => call<StudentDashboard>("/dashboard");
export const fetchStudentProfile = () => call<StudentProfile>("/profile");
export const updateStudentProfile = (payload: StudentProfileUpdate) =>
  call<StudentProfile>("/profile", jsonInit("PATCH", payload));

// ── C-ST-03 … C-ST-05 attendance & leave ────────────────────────────────────

export interface StudentSubjectAttendance {
  subject_id: string;
  subject_code: string;
  subject_name: string;
  present_count: number;
  absent_count: number;
  late_count: number;
  excused_count: number;
  total_marks: number;
  attendance_percentage: number | null;
}

export interface StudentAttendanceSummary {
  attendance_percentage: number | null;
  total_marks: number;
  present_count: number;
  absent_count: number;
  late_count: number;
  excused_count: number;
  subjects: StudentSubjectAttendance[];
}

export interface StudentAttendanceEntry {
  status: string;
  subject_code: string;
  subject_name: string;
  period_label: string;
}

export interface StudentAttendanceDay {
  date: string;
  entries: StudentAttendanceEntry[];
}

export interface StudentAttendanceCalendar {
  month: string;
  days: StudentAttendanceDay[];
}

export interface StudentLeaveRow {
  id: string;
  from_date: string;
  to_date: string;
  reason: string;
  document_url: string | null;
  status: string;
  reviewed_at: string | null;
  created_at: string;
}

export interface StudentLeaveCreate {
  from_date: string;
  to_date: string;
  reason: string;
  document_url?: string | null;
}

export const fetchStudentAttendance = () => call<StudentAttendanceSummary>("/attendance");

export const fetchStudentAttendanceCalendar = (month: string) =>
  call<StudentAttendanceCalendar>(`/attendance/calendar${queryString({ month })}`);

export const fetchStudentLeaves = (filters: { limit?: number; offset?: number } = {}) =>
  call<StudentPage<StudentLeaveRow>>(
    `/attendance/leaves${queryString({ limit: filters.limit, offset: filters.offset })}`,
  );

export const applyStudentLeave = (payload: StudentLeaveCreate) =>
  call<StudentLeaveRow>("/attendance/leaves", jsonInit("POST", payload));

export const cancelStudentLeave = (leaveId: string) =>
  call<StudentLeaveRow>(`/attendance/leaves/${leaveId}/cancel`, { method: "POST" });

// ── C-ST-06 timetable ───────────────────────────────────────────────────────

export interface StudentTimetable {
  class_info: StudentClassInfo;
  slots: StudentTimetableSlot[];
}

export const fetchStudentTimetable = () => call<StudentTimetable>("/timetable");

// ── C-ST-07 … C-ST-09 examinations ─────────────────────────────────────────

export interface StudentExamRow {
  id: string;
  title: string;
  subject_name: string;
  subject_code: string;
  exam_type: string;
  mode: string;
  total_marks: number;
  passing_marks: number;
  duration_minutes: number;
  scheduled_at: string;
  window_end_at: string | null;
  status: string;
  my_attempt_status: string | null;
  my_score: number | null;
  can_attempt: boolean;
  result_available: boolean;
}

export interface StudentExamDetail extends StudentExamRow {
  instructions: string | null;
  question_count: number;
  allow_review: boolean;
  show_score_immediately: boolean;
  attempt_id: string | null;
  attempt_started_at: string | null;
  attempt_submitted_at: string | null;
}

export interface StudentAttemptState {
  attempt_id: string;
  exam_id: string;
  started_at: string;
  duration_minutes: number;
  ends_at: string;
  status: string;
}

export interface StudentAttemptOption {
  id: string;
  text: string;
  image_url: string | null;
  sort_order: number;
}

export interface StudentAttemptQuestion {
  id: string;
  text: string;
  question_type: string;
  marks: number;
  image_url: string | null;
  sort_order: number;
  options: StudentAttemptOption[];
  my_selected_option_id: string | null;
  my_text_answer: string | null;
}

export interface StudentAttemptPaper {
  attempt: StudentAttemptState;
  questions: StudentAttemptQuestion[];
}

export interface StudentAnswerSave {
  question_id: string;
  selected_option_id?: string | null;
  text_answer?: string | null;
}

export interface StudentResultAnswer {
  question_id: string;
  question_text: string;
  question_type: string;
  marks: number;
  selected_option_id: string | null;
  selected_option_text: string | null;
  correct_option_id: string | null;
  correct_option_text: string | null;
  text_answer: string | null;
  score: number | null;
  feedback: string | null;
}

/** Typed result lifecycle — mirrors StudentExamResult.RESULT_* on the backend. */
export type StudentResultState =
  | "NOT_ATTEMPTED"
  | "IN_PROGRESS"
  | "UNDER_EVALUATION"
  | "AVAILABLE";

export interface StudentExamResult {
  exam_id: string;
  title: string;
  subject_name: string;
  total_marks: number;
  passing_marks: number;
  status: string;
  result_state?: StudentResultState;
  total_score: number | null;
  percentage: number | null;
  grade: string | null;
  submitted_at: string | null;
  show_answers: boolean;
  answers: StudentResultAnswer[];
}

/** Plain-text grade card used by the mobile "Share result" action. */
export function gradeCardText(result: StudentExamResult): string {
  const score = `${result.total_score !== null ? result.total_score : "—"}/${result.total_marks}`;
  const pct = result.percentage !== null ? `${result.percentage}%` : "—";
  const grade =
    result.grade ??
    (result.total_score !== null ? (result.total_score >= result.passing_marks ? "PASS" : "FAIL") : "—");
  return [
    result.title,
    result.subject_name,
    `Score: ${score} · ${pct} · Grade: ${grade}`,
    result.submitted_at ? `Submitted: ${result.submitted_at}` : null,
  ]
    .filter(Boolean)
    .join("\n");
}

export const fetchStudentExams = (filters: {
  when?: "upcoming" | "completed" | "all";
  limit?: number;
  offset?: number;
} = {}) =>
  call<StudentPage<StudentExamRow>>(
    `/examinations${queryString({ when: filters.when, limit: filters.limit, offset: filters.offset })}`,
  );

export const fetchStudentExam = (examId: string) =>
  call<StudentExamDetail>(`/examinations/${examId}`);

export const startExamAttempt = (examId: string) =>
  call<StudentAttemptState>(`/examinations/${examId}/attempt`, { method: "POST" });

export const fetchAttemptPaper = (examId: string) =>
  call<StudentAttemptPaper>(`/examinations/${examId}/attempt/paper`);

export const saveExamAnswer = (examId: string, payload: StudentAnswerSave) =>
  call<StudentAttemptPaper>(`/examinations/${examId}/attempt/answers`, jsonInit("PUT", payload));

/** C-ST-08 anti-cheat: report that the student left the exam (app backgrounded). */
export const reportExamTabSwitch = (examId: string) =>
  call<{ tab_switch_count: number }>(`/examinations/${examId}/attempt/tab-switch`, { method: "POST" });

export const submitExamAttempt = (examId: string) =>
  call<StudentAttemptState>(`/examinations/${examId}/attempt/submit`, { method: "POST" });

export const fetchExamResult = (examId: string) =>
  call<StudentExamResult>(`/examinations/${examId}/result`);

// ── C-ST-10 … C-ST-12 assignments ──────────────────────────────────────────

export interface StudentAssignmentRow {
  id: string;
  title: string;
  subject_name: string;
  subject_code: string;
  teacher_name: string | null;
  assignment_type: string;
  total_marks: number;
  due_date: string;
  status: string;
  my_status: string;
  my_score: number | null;
  my_submitted_at: string | null;
  is_late: boolean;
}

export interface StudentMilestoneProgress {
  id: string;
  title: string;
  description: string | null;
  sort_order: number;
  marks: number;
  due_date: string | null;
  unlocked: boolean;
  my_status: string | null;
  my_score: number | null;
  my_submitted_at: string | null;
}

export interface StudentSubmissionFileIn {
  file_name: string;
  file_key: string;
  file_size_bytes: number;
  mime_type: string;
}

export interface StudentSubmissionFileOut extends StudentSubmissionFileIn {
  id: string;
  uploaded_at: string;
}

export interface StudentGroupMember {
  student_id: string;
  student_name: string;
  roll_number: string | null;
  is_me: boolean;
  joined_at: string;
}

export interface StudentGroupRow {
  id: string;
  assignment_id: string;
  name: string;
  created_by: string | null;
  creator_name: string | null;
  member_count: number;
  is_my_group: boolean;
  is_submitted: boolean;
  members: StudentGroupMember[];
}

export interface StudentPreviousGroupOption {
  group_id: string;
  group_name: string;
  assignment_title: string;
  subject_name: string;
  member_count: number;
  members: StudentGroupMember[];
}

export interface StudentGroupListOut {
  min_group_size: number;
  max_group_size: number;
  my_group: StudentGroupRow | null;
  groups: StudentGroupRow[];
  previous_groups?: StudentPreviousGroupOption[];
}

export interface StudentSubmissionOut {
  id: string;
  milestone_id: string | null;
  group_id: string | null;
  group_name: string | null;
  submitted_at: string;
  is_late: boolean;
  status: string;
  score: number | null;
  grade: string | null;
  feedback: string | null;
  reviewed_at: string | null;
  version: number;
  text_response: string | null;
  files: StudentSubmissionFileOut[];
}

export interface StudentAssignmentDetail extends StudentAssignmentRow {
  description: string;
  passing_marks: number;
  allow_late_submission: boolean;
  max_file_size_mb: number;
  allowed_file_types: string[];
  min_group_size: number;
  max_group_size: number;
  my_group: StudentGroupRow | null;
  instructions_url: string | null;
  milestones: StudentMilestoneProgress[];
  my_submissions: StudentSubmissionOut[];
}

export interface StudentSubmissionCreate {
  milestone_id?: string | null;
  text_response?: string | null;
  files?: StudentSubmissionFileIn[];
}

export const fetchStudentAssignments = (filters: { status?: string; limit?: number; offset?: number } = {}) =>
  call<StudentPage<StudentAssignmentRow>>(
    `/assignments${queryString({ status: filters.status, limit: filters.limit, offset: filters.offset })}`,
  );

export const fetchStudentAssignment = (assignmentId: string) =>
  call<StudentAssignmentDetail>(`/assignments/${assignmentId}`);

export const submitStudentAssignment = (assignmentId: string, payload: StudentSubmissionCreate) =>
  call<StudentSubmissionOut>(`/assignments/${assignmentId}/submit`, jsonInit("POST", payload));

export const fetchStudentAssignmentGroups = (assignmentId: string) =>
  call<StudentGroupListOut>(`/assignments/${assignmentId}/groups`);

export const createStudentAssignmentGroup = (assignmentId: string, name: string) =>
  call<StudentGroupRow>(`/assignments/${assignmentId}/groups`, jsonInit("POST", { name }));

export const reuseStudentAssignmentGroup = (assignmentId: string, previousGroupId: string) =>
  call<StudentGroupRow>(`/assignments/${assignmentId}/groups/reuse`, jsonInit("POST", { previous_group_id: previousGroupId }));

export const joinStudentAssignmentGroup = (assignmentId: string, groupId: string) =>
  call<StudentGroupRow>(`/assignments/${assignmentId}/groups/${groupId}/join`, { method: "POST" });

export const leaveStudentAssignmentGroup = (assignmentId: string) =>
  call<void>(`/assignments/${assignmentId}/groups/leave`, { method: "POST" });

// ── Team Workspace & Collaboration Facilities ───────────────────────────────

export interface StudentGroupTaskOut {
  id: string;
  group_id: string;
  title: string;
  description: string | null;
  assigned_to: string | null;
  assignee_name: string | null;
  status: "TODO" | "IN_PROGRESS" | "DONE" | string;
  due_date: string | null;
  created_by: string | null;
  creator_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface StudentGroupTaskIn {
  title: string;
  description?: string | null;
  assigned_to?: string | null;
  due_date?: string | null;
}

export interface StudentGroupTaskUpdateIn {
  title?: string | null;
  description?: string | null;
  assigned_to?: string | null;
  status?: string | null;
  due_date?: string | null;
}

export interface StudentGroupMessageOut {
  id: string;
  group_id: string;
  sender_id: string;
  sender_name: string;
  is_me: boolean;
  message: string;
  created_at: string;
}

export interface StudentGroupResourceOut {
  id: string;
  group_id: string;
  title: string;
  url: string;
  resource_type: string;
  created_by: string | null;
  creator_name: string | null;
  created_at: string;
}

export interface StudentGroupResourceIn {
  title: string;
  url: string;
  resource_type?: string;
}

export interface StudentMyTeamSummary {
  group_id: string;
  assignment_id: string;
  group_name: string;
  assignment_title: string;
  subject_code: string;
  subject_name: string;
  teacher_name: string | null;
  due_date: string;
  is_leader: boolean;
  member_count: number;
  min_group_size: number;
  max_group_size: number;
  is_submitted: boolean;
  submission_status: string | null;
  score: number | null;
  total_marks: number;
  members: StudentGroupMember[];
}

export interface StudentEligibleClassmateOut {
  student_id: string;
  student_name: string;
  roll_number: string | null;
  already_in_group: boolean;
  has_pending_invite: boolean;
}

export interface StudentGroupInviteOut {
  id: string;
  group_id: string;
  group_name: string;
  assignment_id: string;
  assignment_title: string;
  subject_name: string;
  student_id: string;
  student_name: string;
  student_roll_number: string | null;
  invited_by: string;
  inviter_name: string;
  status: string;
  created_at: string;
}

export interface StudentMyTeamDetail {
  group: StudentGroupRow;
  assignment: StudentAssignmentDetail;
  tasks: StudentGroupTaskOut[];
  messages: StudentGroupMessageOut[];
  resources: StudentGroupResourceOut[];
  pending_invitations: StudentGroupInviteOut[];
}

export const fetchMyTeams = () => call<StudentMyTeamSummary[]>("/teams");

export const fetchTeamWorkspace = (groupId: string) => call<StudentMyTeamDetail>(`/teams/${groupId}`);

export const createTeamTask = (groupId: string, payload: StudentGroupTaskIn) =>
  call<StudentGroupTaskOut>(`/teams/${groupId}/tasks`, jsonInit("POST", payload));

export const updateTeamTask = (groupId: string, taskId: string, payload: StudentGroupTaskUpdateIn) =>
  call<StudentGroupTaskOut>(`/teams/${groupId}/tasks/${taskId}`, jsonInit("PATCH", payload));

export const deleteTeamTask = (groupId: string, taskId: string) =>
  call<void>(`/teams/${groupId}/tasks/${taskId}`, { method: "DELETE" });

export const postTeamMessage = (groupId: string, message: string) =>
  call<StudentGroupMessageOut>(`/teams/${groupId}/messages`, jsonInit("POST", { message }));

export const addTeamResource = (groupId: string, payload: StudentGroupResourceIn) =>
  call<StudentGroupResourceOut>(`/teams/${groupId}/resources`, jsonInit("POST", payload));

export const deleteTeamResource = (groupId: string, resourceId: string) =>
  call<void>(`/teams/${groupId}/resources/${resourceId}`, { method: "DELETE" });

export const fetchEligibleClassmates = (groupId: string) =>
  call<StudentEligibleClassmateOut[]>(`/teams/${groupId}/eligible-members`);

export const inviteTeamMember = (groupId: string, studentId: string) =>
  call<StudentGroupInviteOut>(`/teams/${groupId}/invitations`, jsonInit("POST", { student_id: studentId }));

export const cancelTeamInvitation = (groupId: string, inviteId: string) =>
  call<void>(`/teams/${groupId}/invitations/${inviteId}`, { method: "DELETE" });

export const fetchMyInvitations = () =>
  call<StudentGroupInviteOut[]>("/invitations");

export const respondToInvitation = (inviteId: string, action: "ACCEPT" | "REJECT") =>
  call<void>(`/invitations/${inviteId}/respond`, jsonInit("POST", { action }));

// ── C-ST-13 / C-ST-14 content ───────────────────────────────────────────────

export interface StudentContentRow {
  id: string;
  title: string;
  description: string | null;
  subject_id: string;
  subject_code: string;
  subject_name: string;
  uploader_name: string | null;
  content_type: string;
  file_key: string | null;
  external_url: string | null;
  file_size_bytes: number | null;
  duration_seconds: number | null;
  chapter: string | null;
  tags: string[];
  view_count: number;
  download_count: number;
  created_at: string;
}

export interface StudentContentPage extends StudentPage<StudentContentRow> {
  chapters: string[];
}

export const fetchStudentContent = (filters: {
  subjectId?: string;
  chapter?: string;
  contentType?: string;
  query?: string;
  limit?: number;
  offset?: number;
} = {}) =>
  call<StudentContentPage>(
    `/content${queryString({
      subject_id: filters.subjectId,
      chapter: filters.chapter,
      content_type: filters.contentType,
      query: filters.query,
      limit: filters.limit,
      offset: filters.offset,
    })}`,
  );

export const fetchStudentContentItem = (contentId: string) =>
  call<StudentContentRow>(`/content/${contentId}`);

// ── C-ST-15 … C-ST-17 results ───────────────────────────────────────────────

export interface StudentResultRow {
  publication_id: string;
  title: string;
  academic_year: string | null;
  class_name: string | null;
  published_at: string;
  total_marks_obtained: number;
  total_marks_possible: number;
  percentage: number;
  grade: string;
  rank: number | null;
  result: string;
  has_grade_card: boolean;
}

export interface StudentSubjectScore {
  subject_name: string;
  marks_obtained: number;
  marks_possible: number;
  grade: string | null;
}

export interface StudentResultDetail extends StudentResultRow {
  subject_scores: StudentSubjectScore[];
  remarks: string | null;
  institution_name: string | null;
}

export const fetchStudentResults = () => call<StudentResultRow[]>("/results");

export const fetchStudentResult = (publicationId: string) =>
  call<StudentResultDetail>(`/results/${publicationId}`);

export const fetchGradeCard = (publicationId: string) =>
  call<StudentResultDetail>(`/results/${publicationId}/grade-card`);

// ── C-ST-18 notices ─────────────────────────────────────────────────────────

export interface StudentNoticePage extends StudentPage<StudentNoticeRow> {
  unread_count: number;
}

export const fetchStudentNotices = (filters: { query?: string; limit?: number; offset?: number } = {}) =>
  call<StudentNoticePage>(
    `/notices${queryString({ query: filters.query, limit: filters.limit, offset: filters.offset })}`,
  );

export const markStudentNoticeRead = (noticeId: string) =>
  call<StudentNoticeRow>(`/notices/${noticeId}/read`, { method: "POST" });

// ── C-ST-19 discussion ──────────────────────────────────────────────────────

export interface StudentThreadRow {
  id: string;
  title: string;
  body: string;
  author_name: string | null;
  mine: boolean;
  scope_type: string;
  scope_name: string | null;
  tags: string[];
  is_pinned: boolean;
  is_locked: boolean;
  is_resolved: boolean;
  reply_count: number;
  upvote_count: number;
  my_vote: boolean;
  created_at: string;
  updated_at: string;
}

export interface StudentReplyRow {
  id: string;
  author_name: string | null;
  mine: boolean;
  body: string;
  is_accepted_answer: boolean;
  upvote_count: number;
  my_vote: boolean;
  created_at: string;
}

export interface StudentThreadDetail extends StudentThreadRow {
  replies: StudentReplyRow[];
}

export interface StudentDiscussionScope {
  scope_type: string;
  scope_id: string;
  name: string;
}

export const fetchDiscussionScopes = () => call<StudentDiscussionScope[]>("/discussion/scopes");

export const fetchStudentDiscussion = (filters: {
  scopeId?: string;
  query?: string;
  limit?: number;
  offset?: number;
} = {}) =>
  call<StudentPage<StudentThreadRow>>(
    `/discussion${queryString({
      scope_id: filters.scopeId,
      query: filters.query,
      limit: filters.limit,
      offset: filters.offset,
    })}`,
  );

export const createStudentThread = (payload: {
  title: string;
  body: string;
  scope_type: "CLASS" | "SUBJECT";
  scope_id: string;
  tags?: string[];
}) => call<StudentThreadDetail>("/discussion", jsonInit("POST", payload));

export const fetchStudentThread = (threadId: string) =>
  call<StudentThreadDetail>(`/discussion/${threadId}`);

export const replyToStudentThread = (threadId: string, body: string) =>
  call<StudentThreadDetail>(`/discussion/${threadId}/replies`, jsonInit("POST", { body }));

export const toggleStudentVote = (targetType: "THREAD" | "REPLY", targetId: string) =>
  call<StudentThreadDetail>(`/discussion/vote`, jsonInit("POST", { target_type: targetType, target_id: targetId }));

// ── C-ST-20 fees ────────────────────────────────────────────────────────────

export interface StudentFeeInstallment {
  id: string;
  installment_number: number;
  label: string;
  amount: number;
  due_date: string;
  paid_amount: number;
  status: string;
  late_fine: number;
}

export interface StudentFeePayment {
  id: string;
  amount: number;
  payment_mode: string;
  transaction_reference: string | null;
  payment_date: string;
  receipt_number: string;
  notes: string | null;
}

export interface StudentScholarshipGrant {
  id: string;
  scholarship_name: string | null;
  amount_granted: number;
  granted_at: string;
  remarks: string | null;
}

export interface StudentFeeAccount {
  academic_year: string | null;
  total_fee: number;
  concession_amount: number;
  scholarship_amount: number;
  net_payable: number;
  total_paid: number;
  balance_due: number;
  status: string;
  installments: StudentFeeInstallment[];
  payments: StudentFeePayment[];
  grants: StudentScholarshipGrant[];
}

export const fetchStudentFees = () => call<StudentFeeAccount>("/fees");
