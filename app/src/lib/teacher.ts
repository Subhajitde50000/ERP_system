/**
 * Teacher console API client (C-TC-01 … C-TC-22) — mobile port of
 * fontend/lib/teacher.ts.
 *
 * The server derives the teacher's scope from teacher_subjects + homeroom
 * classes, so this client never sends a teacher id as authority. Snake_case
 * payloads mirror `backend/app/schemas/teacher.py` one-to-one.
 *
 * CSV import/export is included (paste / share) so the website Question Bank
 * tools have a mobile counterpart. Browser print-to-PDF is omitted.
 */

import { APIError, requestJson } from "./api-client";
import { API_BASE_URL, getAccessToken, refreshAccessToken } from "./auth";
import {
  queryString,
  type StudentGroupMessageOut,
  type StudentGroupResourceOut,
  type StudentGroupTaskOut,
} from "./student";

export { APIError as TeacherAPIError } from "./api-client";
export { queryString };

const call = <T>(path: string, init: RequestInit = {}): Promise<T> =>
  requestJson<T>(
    `${API_BASE_URL}/api/v1/teacher${path}`,
    init,
    getAccessToken(),
    "TeacherAPIError",
    refreshAccessToken,
  );

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export interface TeacherPage<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export interface TeachingAssignment {
  subject_id: string;
  subject_code: string;
  subject_name: string;
  class_id: string;
  class_name: string;
  department_id: string | null;
  department_name: string | null;
  role_in_subject: string;
  is_class_teacher: boolean;
}

export interface TeacherTargetOption {
  id: string;
  name: string;
}

// ── C-TC-01 / C-TC-02 dashboard & schedule ──────────────────────────────────

export interface TeacherScheduleSlot {
  id: string;
  day_of_week: number;
  period_number: number;
  start_time: string;
  end_time: string;
  class_id: string;
  class_name: string;
  subject_id: string | null;
  subject_code: string | null;
  subject_name: string | null;
  room_no: string | null;
  slot_type: string;
}

export interface TeacherUpcomingExam {
  id: string;
  title: string;
  class_name: string;
  subject_name: string;
  scheduled_at: string;
  status: string;
}

export interface TeacherNoticeRow {
  id: string;
  title: string;
  body: string;
  author_name: string | null;
  target_scope: "INSTITUTION" | "DEPARTMENT" | "CLASS" | "HOSTEL" | "TRANSPORT";
  target_id: string | null;
  target_name: string | null;
  priority: "NORMAL" | "IMPORTANT" | "URGENT";
  is_pinned: boolean;
  published_at: string;
  expires_at: string | null;
  mine: boolean;
}

export interface TeacherDashboard {
  academic_year: string | null;
  teacher_name: string;
  teaching_assignment_count: number;
  today_periods: TeacherScheduleSlot[];
  pending_submission_count: number;
  pending_unreviewed_submissions: number;
  upcoming_exam_count: number;
  upcoming_exams: TeacherUpcomingExam[];
  active_assignment_count: number;
  pending_leave_count: number;
  recent_notices: TeacherNoticeRow[];
}

export interface TeacherSchedule {
  academic_year: string | null;
  assignments: TeachingAssignment[];
  slots: TeacherScheduleSlot[];
}

export const fetchTeacherDashboard = () => call<TeacherDashboard>("/dashboard");
export const fetchTeacherSchedule = () => call<TeacherSchedule>("/schedule");
export const fetchTeachingAssignments = () => call<TeachingAssignment[]>("/teaching-assignments");

// ── C-TC-03 … C-TC-05 attendance ────────────────────────────────────────────

export interface AttendanceRosterEntry {
  student_id: string;
  student_name: string;
  roll_number: string | null;
  status: string | null;
  late_by_minutes: number | null;
  remarks: string | null;
}

export type AttendanceMarkStatus = "PRESENT" | "ABSENT" | "LATE" | "EXCUSED";

export interface AttendanceRecordIn {
  student_id: string;
  status: AttendanceMarkStatus;
  late_by_minutes?: number | null;
  remarks?: string | null;
}

export interface AttendanceSessionUpsert {
  class_id: string;
  subject_id: string;
  date: string;
  period_label: string;
  start_time?: string | null;
  end_time?: string | null;
  notes?: string | null;
  records: AttendanceRecordIn[];
}

export interface TeacherAttendanceSessionRow {
  id: string;
  class_id: string;
  class_name: string;
  subject_id: string;
  subject_code: string;
  subject_name: string;
  date: string;
  period_label: string;
  total_present: number;
  total_absent: number;
  is_locked: boolean;
  locked_at: string | null;
  notes: string | null;
}

export interface TeacherAttendanceSessionDetail extends TeacherAttendanceSessionRow {
  start_time: string | null;
  end_time: string | null;
  records: AttendanceRosterEntry[];
}

export interface TeacherAttendanceBoard {
  assignments: TeachingAssignment[];
  roster: AttendanceRosterEntry[];
  existing_session: TeacherAttendanceSessionDetail | null;
}

export const fetchAttendanceBoard = (filters: {
  subjectId: string;
  classId: string;
  on?: string;
  periodLabel?: string;
}) =>
  call<TeacherAttendanceBoard>(
    `/attendance/board${queryString({
      subject_id: filters.subjectId,
      class_id: filters.classId,
      on: filters.on,
      period_label: filters.periodLabel,
    })}`,
  );

export const saveAttendanceSession = (payload: AttendanceSessionUpsert) =>
  call<TeacherAttendanceSessionDetail>("/attendance/sessions", jsonInit("PUT", payload));

export const fetchAttendanceSessions = (filters: {
  fromDate?: string;
  toDate?: string;
  classId?: string;
  subjectId?: string;
  limit?: number;
  offset?: number;
}) =>
  call<TeacherPage<TeacherAttendanceSessionRow>>(
    `/attendance/sessions${queryString({
      from_date: filters.fromDate,
      to_date: filters.toDate,
      class_id: filters.classId,
      subject_id: filters.subjectId,
      limit: filters.limit,
      offset: filters.offset,
    })}`,
  );

export const fetchAttendanceSession = (sessionId: string) =>
  call<TeacherAttendanceSessionDetail>(`/attendance/sessions/${sessionId}`);

export const lockAttendanceSession = (sessionId: string) =>
  call<TeacherAttendanceSessionDetail>(`/attendance/sessions/${sessionId}/lock`, { method: "POST" });

// ── C-TC-06 student leaves ──────────────────────────────────────────────────

export interface TeacherLeaveRow {
  id: string;
  student_id: string;
  student_name: string;
  roll_number: string | null;
  class_id: string;
  class_name: string;
  from_date: string;
  to_date: string;
  reason: string;
  document_url: string | null;
  status: string;
  reviewed_at: string | null;
  created_at: string;
}

export interface TeacherLeavePage extends TeacherPage<TeacherLeaveRow> {
  pending_count: number;
}

export const fetchTeacherLeaves = (filters: { status?: string; limit?: number; offset?: number }) =>
  call<TeacherLeavePage>(
    `/attendance/leaves${queryString({ status: filters.status, limit: filters.limit, offset: filters.offset })}`,
  );

export const reviewTeacherLeave = (leaveId: string, decision: "APPROVED" | "REJECTED") =>
  call<TeacherLeaveRow>(`/attendance/leaves/${leaveId}/review`, jsonInit("POST", { decision }));

// ── C-TC-07 … C-TC-11 examinations ─────────────────────────────────────────

export type TeacherExamType = "MCQ" | "DESCRIPTIVE" | "MIXED" | "QUIZ";
export type TeacherExamMode = "ONLINE" | "OFFLINE";
export type TeacherQuestionType =
  | "MCQ"
  | "SHORT_ANSWER"
  | "LONG_ANSWER"
  | "TRUE_FALSE"
  | "FILL_BLANK"
  | "MATCH";
export type TeacherDifficulty = "EASY" | "MEDIUM" | "HARD";

export interface TeacherExamCreate {
  title: string;
  subject_id: string;
  class_id: string;
  exam_type?: TeacherExamType;
  mode?: TeacherExamMode;
  total_marks: number;
  passing_marks: number;
  duration_minutes: number;
  instructions?: string | null;
  scheduled_at: string;
  window_end_at?: string | null;
  allow_review?: boolean;
  show_score_immediately?: boolean;
  shuffle_questions?: boolean;
}

export type TeacherExamUpdate = Partial<Omit<TeacherExamCreate, "subject_id" | "class_id">>;

export interface TeacherExamRow {
  id: string;
  title: string;
  class_id: string;
  class_name: string;
  subject_id: string;
  subject_code: string;
  subject_name: string;
  exam_type: string;
  mode: string;
  total_marks: number;
  passing_marks: number;
  duration_minutes: number;
  scheduled_at: string;
  window_end_at: string | null;
  status: string;
  question_count: number;
  attempt_count: number;
  pending_grading_count: number;
}

export interface TeacherQuestionOptionIn {
  text: string;
  image_url?: string | null;
  is_correct?: boolean;
  sort_order?: number;
}

export interface TeacherQuestionIn {
  text: string;
  question_type: TeacherQuestionType;
  marks: number;
  negative_marks?: number;
  image_url?: string | null;
  explanation?: string | null;
  difficulty?: TeacherDifficulty | null;
  options?: TeacherQuestionOptionIn[];
}

export type TeacherQuestionUpdate = Partial<TeacherQuestionIn>;

export interface TeacherQuestionOptionOut {
  id: string;
  text: string;
  image_url: string | null;
  is_correct: boolean;
  sort_order: number;
}

export interface TeacherQuestionOut {
  id: string;
  text: string;
  question_type: string;
  marks: number;
  negative_marks: number;
  image_url: string | null;
  explanation: string | null;
  difficulty: string | null;
  sort_order: number;
  options: TeacherQuestionOptionOut[];
}

export interface TeacherExamDetail extends TeacherExamRow {
  instructions: string | null;
  allow_review: boolean;
  show_score_immediately: boolean;
  shuffle_questions: boolean;
  created_at: string;
  questions: TeacherQuestionOut[];
}

export interface TeacherAttemptRow {
  attempt_id: string;
  student_id: string;
  student_name: string;
  roll_number: string | null;
  status: string;
  started_at: string;
  submitted_at: string | null;
  total_score: number | null;
  percentage: number | null;
  grade: string | null;
  tab_switch_count: number;
  pending_grading_count: number;
}

export interface TeacherAnswerOption {
  id: string;
  text: string;
  is_correct: boolean;
  sort_order: number;
}

export interface TeacherAnswerRow {
  answer_id: string;
  question_id: string;
  question_text: string;
  question_type: string;
  marks: number;
  selected_option_id: string | null;
  selected_option_text: string | null;
  correct_option_text: string | null;
  /** Full answer key for the question — every option, correct one flagged. */
  options: TeacherAnswerOption[];
  text_answer: string | null;
  /** MATCH-type answers store pairings as JSON instead of plain text. */
  matched_pairs: Record<string, string> | null;
  score: number | null;
  feedback: string | null;
  is_auto_graded: boolean;
}

export interface TeacherAttemptDetail extends TeacherAttemptRow {
  answers: TeacherAnswerRow[];
}

export interface TeacherAnswerGradeIn {
  answer_id: string;
  score: number;
  feedback?: string | null;
}

export const fetchTeacherExams = (filters: { status?: string; limit?: number; offset?: number }) =>
  call<TeacherPage<TeacherExamRow>>(
    `/examinations${queryString({ status: filters.status, limit: filters.limit, offset: filters.offset })}`,
  );

export const createTeacherExam = (payload: TeacherExamCreate) =>
  call<TeacherExamDetail>("/examinations", jsonInit("POST", payload));

export const fetchTeacherExam = (examId: string) => call<TeacherExamDetail>(`/examinations/${examId}`);

export const updateTeacherExam = (examId: string, payload: TeacherExamUpdate) =>
  call<TeacherExamDetail>(`/examinations/${examId}`, jsonInit("PATCH", payload));

export const publishTeacherExam = (examId: string) =>
  call<TeacherExamDetail>(`/examinations/${examId}/publish`, { method: "POST" });

export const addExamQuestion = (examId: string, payload: TeacherQuestionIn) =>
  call<TeacherQuestionOut>(`/examinations/${examId}/questions`, jsonInit("POST", payload));

export const updateExamQuestion = (examId: string, questionId: string, payload: TeacherQuestionUpdate) =>
  call<TeacherQuestionOut>(`/examinations/${examId}/questions/${questionId}`, jsonInit("PATCH", payload));

export const deleteExamQuestion = (examId: string, questionId: string) =>
  call<TeacherExamDetail>(`/examinations/${examId}/questions/${questionId}`, { method: "DELETE" });

export interface QuestionBankItemOut {
  id: string;
  tenant_id: string;
  created_by: string | null;
  subject_id: string | null;
  subject_name?: string | null;
  class_id: string | null;
  class_name?: string | null;
  text: string;
  question_type: string;
  default_marks: number;
  negative_marks: number;
  options: { text: string; is_correct?: boolean; image_url?: string | null; sort_order?: number }[];
  image_url: string | null;
  explanation: string | null;
  difficulty: string | null;
  tags: string[];
  usage_count: number;
  created_at: string;
}

export interface QuestionBankItemIn {
  subject_id?: string | null;
  class_id?: string | null;
  text: string;
  question_type: TeacherQuestionType;
  default_marks?: number;
  negative_marks?: number;
  options?: TeacherQuestionOptionIn[];
  image_url?: string | null;
  explanation?: string | null;
  difficulty?: TeacherDifficulty | null;
  tags?: string[];
}

export const fetchQuestionBank = (
  filters: {
    subject_id?: string;
    question_type?: string;
    difficulty?: string;
    search?: string;
    limit?: number;
    offset?: number;
  } = {},
) =>
  call<TeacherPage<QuestionBankItemOut>>(
    `/question-bank${queryString({
      subject_id: filters.subject_id,
      question_type: filters.question_type,
      difficulty: filters.difficulty,
      search: filters.search,
      limit: filters.limit,
      offset: filters.offset,
    })}`,
  );

export const createQuestionBankItem = (payload: QuestionBankItemIn) =>
  call<QuestionBankItemOut>("/question-bank", jsonInit("POST", payload));

export const updateQuestionBankItem = (itemId: string, payload: Partial<QuestionBankItemIn>) =>
  call<QuestionBankItemOut>(`/question-bank/${itemId}`, jsonInit("PATCH", payload));

export const deleteQuestionBankItem = (itemId: string) =>
  call<{ id: string }>(`/question-bank/${itemId}`, { method: "DELETE" });

export interface QuestionBankImportResult {
  imported: number;
  errors: string[];
}

/** Fetch the question bank as CSV text (website triggers a browser download). */
export async function exportQuestionBankCsv(
  filters: {
    subject_id?: string;
    question_type?: string;
    difficulty?: string;
    search?: string;
  } = {},
): Promise<{ filename: string; csv: string }> {
  const qs = queryString({
    fmt: "csv",
    subject_id: filters.subject_id,
    question_type: filters.question_type,
    difficulty: filters.difficulty,
    search: filters.search,
  });
  const url = `${API_BASE_URL}/api/v1/teacher/question-bank/export${qs}`;
  let token = getAccessToken();
  let res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (res.status === 401) {
    token = await refreshAccessToken();
    if (token) {
      res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    }
  }
  if (!res.ok) throw new APIError("Export failed", res.status);
  const csv = await res.text();
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="([^"]+)"/);
  return { filename: match ? match[1] : "question_bank.csv", csv };
}

/**
 * Bulk-import questions from a CSV or JSON payload.
 * The website uploads a File; the app sends the same multipart field.
 */
export async function importQuestionBankText(
  filename: string,
  content: string,
): Promise<QuestionBankImportResult> {
  const mime = filename.toLowerCase().endsWith(".json") ? "application/json" : "text/csv";
  const form = new FormData();
  if (typeof File !== "undefined") {
    form.append("file", new File([content], filename, { type: mime }));
  } else {
    form.append(
      "file",
      {
        uri: `data:${mime};base64,${globalThis.btoa(unescape(encodeURIComponent(content)))}`,
        name: filename,
        type: mime,
      } as unknown as Blob,
    );
  }
  let token = getAccessToken();
  const url = `${API_BASE_URL}/api/v1/teacher/question-bank/import-file`;
  const send = (t?: string | null) =>
    fetch(url, {
      method: "POST",
      headers: t ? { Authorization: `Bearer ${t}` } : {},
      body: form,
    });
  let res = await send(token);
  if (res.status === 401) {
    token = await refreshAccessToken();
    if (token) res = await send(token);
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new APIError(text || "Import failed", res.status);
  }
  const json = (await res.json()) as { data: QuestionBankImportResult };
  return json.data;
}

export const QUESTION_BANK_CSV_TEMPLATE =
  'text,question_type,difficulty,default_marks,negative_marks,explanation,options_json,tags,subject_id,class_id\n"What is 2+2?",MCQ,EASY,1,0,"Basic arithmetic","[{""text"":""4"",""is_correct"":true},{""text"":""3"",""is_correct"":false}]",,,';

export const importQuestionsFromBank = (examId: string, bankItemIds: string[]) =>
  call<TeacherExamDetail>(`/examinations/${examId}/import-questions`, jsonInit("POST", { bank_item_ids: bankItemIds }));

export const fetchExamAttempts = (examId: string, filters: { limit?: number; offset?: number } = {}) =>
  call<TeacherPage<TeacherAttemptRow>>(
    `/examinations/${examId}/attempts${queryString({ limit: filters.limit, offset: filters.offset })}`,
  );

export const fetchExamAttempt = (examId: string, attemptId: string) =>
  call<TeacherAttemptDetail>(`/examinations/${examId}/attempts/${attemptId}`);

export const gradeExamAttempt = (examId: string, attemptId: string, grades: TeacherAnswerGradeIn[]) =>
  call<TeacherAttemptDetail>(
    `/examinations/${examId}/attempts/${attemptId}/grade`,
    jsonInit("POST", { grades }),
  );

export const releaseExamResults = (examId: string) =>
  call<TeacherExamDetail>(`/examinations/${examId}/release`, { method: "POST" });

// ── C-TC-12 … C-TC-16 assignments ──────────────────────────────────────────

export type TeacherAssignmentType = "REGULAR" | "MILESTONE" | "GROUP";

export interface TeacherAssignmentCreate {
  title: string;
  description: string;
  subject_id: string;
  class_id: string;
  assignment_type?: TeacherAssignmentType;
  total_marks: number;
  passing_marks: number;
  due_date: string;
  allow_late_submission?: boolean;
  late_penalty_percent?: number;
  max_file_size_mb?: number;
  allowed_file_types?: string[];
  min_group_size?: number;
  max_group_size?: number;
  instructions_url?: string | null;
  publish?: boolean;
}

export type TeacherAssignmentUpdate = Partial<
  Omit<TeacherAssignmentCreate, "subject_id" | "class_id" | "publish">
>;

export interface TeacherMilestoneIn {
  title: string;
  description?: string | null;
  marks: number;
  due_date?: string | null;
  unlock_after_milestone_id?: string | null;
}

export type TeacherMilestoneUpdateIn = Partial<Omit<TeacherMilestoneIn, "unlock_after_milestone_id">>;

export interface TeacherMilestoneOut {
  id: string;
  title: string;
  description: string | null;
  sort_order: number;
  marks: number;
  due_date: string | null;
  unlock_after_milestone_id: string | null;
}

export interface TeacherGroupMember {
  student_id: string;
  student_name: string;
  roll_number: string | null;
  joined_at: string;
}

export interface TeacherGroupRow {
  id: string;
  assignment_id: string;
  name: string;
  created_by: string | null;
  creator_name: string | null;
  created_at: string;
  member_count: number;
  is_submitted: boolean;
  submission_id?: string | null;
  tasks_count?: number;
  tasks_done_count?: number;
  messages_count?: number;
  resources_count?: number;
  members: TeacherGroupMember[];
}

export interface TeacherTeamWorkspace {
  group: TeacherGroupRow;
  assignment_id: string;
  assignment_title: string;
  class_name: string;
  subject_code: string;
  subject_name: string;
  due_date: string;
  tasks: StudentGroupTaskOut[];
  messages: StudentGroupMessageOut[];
  resources: StudentGroupResourceOut[];
  submission: TeacherSubmissionDetail | null;
}

export interface TeacherAssignmentRow {
  id: string;
  title: string;
  class_id: string;
  class_name: string;
  subject_id: string;
  subject_code: string;
  subject_name: string;
  assignment_type: string;
  total_marks: number;
  due_date: string;
  status: string;
  milestone_count: number;
  student_count: number;
  group_count: number;
  submission_count: number;
  pending_review_count: number;
  reviewed_count: number;
}

export interface TeacherAssignmentDetail extends TeacherAssignmentRow {
  description: string;
  passing_marks: number;
  allow_late_submission: boolean;
  late_penalty_percent: number;
  max_file_size_mb: number;
  allowed_file_types: string[];
  min_group_size: number;
  max_group_size: number;
  instructions_url: string | null;
  created_at: string;
  milestones: TeacherMilestoneOut[];
}

export const fetchTeacherAssignments = (filters: { status?: string; limit?: number; offset?: number }) =>
  call<TeacherPage<TeacherAssignmentRow>>(
    `/assignments${queryString({ status: filters.status, limit: filters.limit, offset: filters.offset })}`,
  );

export const createTeacherAssignment = (payload: TeacherAssignmentCreate) =>
  call<TeacherAssignmentDetail>("/assignments", jsonInit("POST", payload));

export const fetchTeacherAssignment = (assignmentId: string) =>
  call<TeacherAssignmentDetail>(`/assignments/${assignmentId}`);

export const updateTeacherAssignment = (assignmentId: string, payload: TeacherAssignmentUpdate) =>
  call<TeacherAssignmentDetail>(`/assignments/${assignmentId}`, jsonInit("PATCH", payload));

export const publishTeacherAssignment = (assignmentId: string) =>
  call<TeacherAssignmentDetail>(`/assignments/${assignmentId}/publish`, { method: "POST" });

export const closeTeacherAssignment = (assignmentId: string) =>
  call<TeacherAssignmentDetail>(`/assignments/${assignmentId}/close`, { method: "POST" });

/**
 * Reopen a closed assignment. With `requestResubmission` (default) every
 * un-reviewed submission is handed back to its student as RESUBMIT_REQUESTED,
 * so the assignment reappears in their pending list with a resubmit action;
 * without it only students who never submitted can now submit.
 */
export const reopenTeacherAssignment = (assignmentId: string, requestResubmission = true) =>
  call<TeacherAssignmentDetail>(`/assignments/${assignmentId}/reopen`, {
    ...jsonInit("POST", { request_resubmission: requestResubmission }),
  });

export const addAssignmentMilestone = (assignmentId: string, payload: TeacherMilestoneIn) =>
  call<TeacherAssignmentDetail>(`/assignments/${assignmentId}/milestones`, jsonInit("POST", payload));

export const updateAssignmentMilestone = (
  assignmentId: string,
  milestoneId: string,
  payload: TeacherMilestoneUpdateIn,
) =>
  call<TeacherAssignmentDetail>(
    `/assignments/${assignmentId}/milestones/${milestoneId}`,
    jsonInit("PATCH", payload),
  );

export const deleteAssignmentMilestone = (assignmentId: string, milestoneId: string) =>
  call<TeacherAssignmentDetail>(`/assignments/${assignmentId}/milestones/${milestoneId}`, {
    method: "DELETE",
  });

export const fetchTeacherAssignmentGroups = (
  assignmentId: string,
  filters: { limit?: number; offset?: number } = {},
) =>
  call<TeacherPage<TeacherGroupRow>>(
    `/assignments/${assignmentId}/groups${queryString({ limit: filters.limit, offset: filters.offset })}`,
  );

export const fetchTeacherAssignmentGroup = (assignmentId: string, groupId: string) =>
  call<TeacherGroupRow>(`/assignments/${assignmentId}/groups/${groupId}`);

export const removeStudentFromGroup = (assignmentId: string, groupId: string, studentId: string) =>
  call<TeacherGroupRow>(`/assignments/${assignmentId}/groups/${groupId}/members/${studentId}`, {
    method: "DELETE",
  });

export const fetchTeacherTeamWorkspace = (groupId: string) =>
  call<TeacherTeamWorkspace>(`/teams/${groupId}`);

// ── Submissions & review ────────────────────────────────────────────────────

export interface TeacherSubmissionRow {
  id: string;
  student_id: string;
  student_name: string;
  roll_number: string | null;
  group_id: string | null;
  group_name: string | null;
  milestone_id: string | null;
  milestone_title: string | null;
  milestone_marks: number | null;
  submitted_at: string;
  is_late: boolean;
  late_by_minutes: number | null;
  status: string;
  score: number | null;
  grade: string | null;
  version: number;
}

export interface TeacherSubmissionFileOut {
  id: string;
  file_name: string;
  file_key: string;
  file_size_bytes: number;
  mime_type: string;
  uploaded_at: string;
}

export interface TeacherReviewHistoryRow {
  id: string;
  reviewer_name: string | null;
  decision: string;
  marks_awarded: number | null;
  feedback: string | null;
  attempt_number: number;
  reviewed_at: string;
}

export interface TeacherSubmissionDetail extends TeacherSubmissionRow {
  assignment_id: string;
  assignment_title: string;
  total_marks: number;
  text_response: string | null;
  feedback: string | null;
  files: TeacherSubmissionFileOut[];
  reviews: TeacherReviewHistoryRow[];
}

export type TeacherReviewDecision = "APPROVED" | "REJECTED" | "CHANGES_REQUESTED";

export interface TeacherSubmissionReviewIn {
  decision: TeacherReviewDecision;
  score?: number | null;
  feedback?: string | null;
}

export const fetchTeacherSubmissions = (filters: {
  assignmentId?: string;
  milestoneId?: string;
  status?: string;
  limit?: number;
  offset?: number;
}) =>
  call<TeacherPage<TeacherSubmissionRow>>(
    `/submissions${queryString({
      assignment_id: filters.assignmentId,
      milestone_id: filters.milestoneId,
      status: filters.status,
      limit: filters.limit,
      offset: filters.offset,
    })}`,
  );

export const fetchTeacherSubmission = (submissionId: string) =>
  call<TeacherSubmissionDetail>(`/submissions/${submissionId}`);

export const reviewTeacherSubmission = (submissionId: string, payload: TeacherSubmissionReviewIn) =>
  call<TeacherSubmissionDetail>(`/submissions/${submissionId}/review`, jsonInit("POST", payload));

// ── C-TC-17 / C-TC-18 content ───────────────────────────────────────────────

export type TeacherContentType = "PDF" | "VIDEO" | "SLIDE" | "LINK" | "IMAGE" | "AUDIO" | "ZIP";

export interface TeacherContentIn {
  title: string;
  description?: string | null;
  subject_id: string;
  class_id: string;
  content_type: TeacherContentType;
  file_key?: string | null;
  external_url?: string | null;
  file_size_bytes?: number | null;
  duration_seconds?: number | null;
  chapter?: string | null;
  tags?: string[];
  is_visible?: boolean;
}

export type TeacherContentUpdate = Partial<Omit<TeacherContentIn, "subject_id" | "class_id">>;

export interface TeacherContentRow {
  id: string;
  title: string;
  description: string | null;
  subject_id: string;
  subject_code: string;
  subject_name: string;
  class_id: string;
  class_name: string;
  content_type: string;
  file_key: string | null;
  external_url: string | null;
  file_size_bytes: number | null;
  duration_seconds: number | null;
  chapter: string | null;
  tags: string[];
  is_visible: boolean;
  download_count: number;
  view_count: number;
  created_at: string;
}

export const fetchTeacherContent = (filters: {
  subjectId?: string;
  classId?: string;
  contentType?: string;
  query?: string;
  limit?: number;
  offset?: number;
}) =>
  call<TeacherPage<TeacherContentRow>>(
    `/content${queryString({
      subject_id: filters.subjectId,
      class_id: filters.classId,
      content_type: filters.contentType,
      query: filters.query,
      limit: filters.limit,
      offset: filters.offset,
    })}`,
  );

export const createTeacherContent = (payload: TeacherContentIn) =>
  call<TeacherContentRow>("/content", jsonInit("POST", payload));

export const updateTeacherContent = (contentId: string, payload: TeacherContentUpdate) =>
  call<TeacherContentRow>(`/content/${contentId}`, jsonInit("PATCH", payload));

export const deleteTeacherContent = (contentId: string) =>
  call<null>(`/content/${contentId}`, { method: "DELETE" });

// ── C-TC-19 / C-TC-20 notices ───────────────────────────────────────────────

export interface TeacherNoticeCreate {
  title: string;
  body: string;
  class_id: string;
  priority?: "NORMAL" | "IMPORTANT" | "URGENT";
  expires_at?: string | null;
}

export const fetchTeacherNoticeTargets = () => call<TeacherTargetOption[]>("/notices/targets");

export const fetchTeacherNotices = (filters: { query?: string; limit?: number; offset?: number } = {}) =>
  call<TeacherPage<TeacherNoticeRow>>(
    `/notices${queryString({ query: filters.query, limit: filters.limit, offset: filters.offset })}`,
  );

export const createTeacherNotice = (payload: TeacherNoticeCreate) =>
  call<TeacherNoticeRow>("/notices", jsonInit("POST", payload));

export const fetchTeacherNotice = (noticeId: string) => call<TeacherNoticeRow>(`/notices/${noticeId}`);

// ── C-TC-21 / C-TC-22 discussion ────────────────────────────────────────────

export interface TeacherThreadRow {
  id: string;
  title: string;
  body: string;
  author_id: string | null;
  author_name: string | null;
  mine: boolean;
  scope_type: string;
  scope_id: string;
  scope_name: string | null;
  tags: string[];
  is_pinned: boolean;
  is_locked: boolean;
  is_resolved: boolean;
  reply_count: number;
  upvote_count: number;
  view_count: number;
  can_moderate: boolean;
  created_at: string;
  updated_at: string;
}

export interface TeacherReplyRow {
  id: string;
  author_id: string | null;
  author_name: string | null;
  mine: boolean;
  body: string;
  is_accepted_answer: boolean;
  upvote_count: number;
  created_at: string;
}

export interface TeacherThreadDetail extends TeacherThreadRow {
  replies: TeacherReplyRow[];
}

export type TeacherModerationAction = "PIN" | "UNPIN" | "LOCK" | "UNLOCK" | "DELETE";

export const fetchTeacherDiscussion = (
  filters: {
    query?: string;
    scopeType?: "CLASS" | "SUBJECT" | "DEPARTMENT";
    scopeId?: string;
    limit?: number;
    offset?: number;
  } = {},
) =>
  call<TeacherPage<TeacherThreadRow>>(
    `/discussion${queryString({
      query: filters.query,
      scope_type: filters.scopeType,
      scope_id: filters.scopeId,
      limit: filters.limit,
      offset: filters.offset,
    })}`,
  );

export const createTeacherThread = (payload: {
  title: string;
  body: string;
  scope_type: "CLASS" | "SUBJECT";
  scope_id: string;
  tags?: string[];
}) => call<TeacherThreadDetail>("/discussion", jsonInit("POST", payload));

export const fetchTeacherThread = (threadId: string) =>
  call<TeacherThreadDetail>(`/discussion/${threadId}`);

export const replyToTeacherThread = (threadId: string, body: string) =>
  call<TeacherReplyRow>(`/discussion/${threadId}/replies`, jsonInit("POST", { body }));

export const moderateTeacherThread = (threadId: string, action: TeacherModerationAction) =>
  call<TeacherThreadDetail>(`/discussion/${threadId}`, jsonInit("PATCH", { action }));

export const acceptTeacherReply = (replyId: string) =>
  call<TeacherThreadDetail>(`/discussion/replies/${replyId}/accept`, { method: "POST" });
