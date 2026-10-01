/**
 * Mentor API client.
 *
 * Two surfaces share these shapes (mirroring `backend/app/schemas/mentor.py`):
 *
 * - `/mentor/*` — the mentor's own console; the server derives reach from the
 *   caller's active mentor assignments (students, project teams, classes).
 * - `/institution/mentors/*` — the assignment board owned by the Academic
 *   Coordinator, with the Institution Admin as operational fallback.
 */

import { APIError } from "./api-client";
import {
  leadershipCall,
  queryString,
  type PrincipalNoticeRow,
  type PrincipalPage,
} from "./principal";

const call = <T>(path: string, init: RequestInit = {}): Promise<T> =>
  leadershipCall<T>("mentor", path, init, "MentorAPIError");
const managementCall = <T>(path: string, init: RequestInit = {}): Promise<T> =>
  leadershipCall<T>("institution/mentors", path, init, "MentorAPIError");

export { APIError as MentorAPIError };

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// ── Shared ──────────────────────────────────────────────────────────────────

export type MentorScope = "STUDENT" | "TEAM" | "CLASS";

export const MENTOR_SCOPE_LABEL: Record<MentorScope, string> = {
  STUDENT: "Student",
  TEAM: "Project team",
  CLASS: "Class",
};

export interface MenteeSource {
  assignment_id: string;
  scope_type: MentorScope;
  label: string;
}

// ── Management board (Coordinator / Admin) ──────────────────────────────────

export interface MentorAssignmentRow {
  id: string;
  scope_type: MentorScope;
  target_id: string;
  target_name: string;
  target_detail: string | null;
  class_id: string | null;
  class_name: string | null;
  member_count: number;
  assigned_at: string;
  assigned_by_name: string | null;
  notes: string | null;
}

export interface MentorBoardMentor {
  mentor_id: string;
  mentor_name: string;
  email: string | null;
  designation: string | null;
  department_name: string | null;
  is_active: boolean;
  assignments: MentorAssignmentRow[];
  mentee_count: number;
  at_risk_count: number;
}

export interface MentorCandidate {
  id: string;
  name: string;
  designation: string | null;
  department_name: string | null;
  roles: string[];
  active_assignment_count: number;
}

export interface MentorTargetOption {
  id: string;
  name: string;
  detail: string | null;
  class_id: string | null;
  class_name: string | null;
  member_count: number;
  mentor_id: string | null;
  mentor_name: string | null;
}

export interface MentorCoverage {
  classes_total: number;
  classes_covered: number;
  teams_total: number;
  teams_covered: number;
  students_total: number;
  students_direct: number;
  students_covered: number;
}

export interface MentorManagementBoard {
  academic_year: string | null;
  attendance_threshold: number | null;
  coverage: MentorCoverage;
  mentors: MentorBoardMentor[];
  candidates: MentorCandidate[];
  classes: MentorTargetOption[];
  teams: MentorTargetOption[];
  students: MentorTargetOption[];
}

export interface MentorAssignRequest {
  mentor_id: string;
  scope_type: MentorScope;
  target_id: string;
  notes?: string | null;
}

export const fetchMentorBoard = () => managementCall<MentorManagementBoard>("/board");
export const assignMentor = (payload: MentorAssignRequest) =>
  managementCall<MentorManagementBoard>("/assignments", jsonInit("POST", payload));
export const removeMentorAssignment = (assignmentId: string) =>
  managementCall<MentorManagementBoard>(`/assignments/${assignmentId}`, { method: "DELETE" });

// ── Mentor console ──────────────────────────────────────────────────────────

export interface MentorMenteeRow {
  student_id: string;
  student_name: string;
  roll_number: string | null;
  email: string | null;
  phone: string | null;
  avatar_url: string | null;
  class_id: string | null;
  class_name: string | null;
  department_name: string | null;
  sources: MenteeSource[];
  attendance_percentage: number | null;
  is_at_risk: boolean;
  pending_leave_count: number;
  note_count: number;
  last_note_at: string | null;
}

export interface MentorMenteeList {
  academic_year: string | null;
  attendance_threshold: number | null;
  total: number;
  items: MentorMenteeRow[];
}

export interface MentorClassRow {
  assignment_id: string;
  class_id: string;
  class_name: string;
  class_code: string;
  department_name: string | null;
  room_no: string | null;
  class_teacher_name: string | null;
  student_count: number;
  average_attendance: number | null;
  at_risk_count: number;
  assigned_at: string;
}

export interface MentorTeamMember {
  student_id: string;
  student_name: string;
  roll_number: string | null;
  attendance_percentage: number | null;
  joined_at: string;
}

export interface MentorTeamRow {
  assignment_id: string;
  team_id: string;
  team_name: string;
  coursework_id: string;
  coursework_title: string;
  coursework_status: string;
  due_date: string;
  class_id: string;
  class_name: string;
  subject_name: string | null;
  member_count: number;
  submission_status: string | null;
  open_task_count: number;
  assigned_at: string;
}

export interface MentorTeamTask {
  id: string;
  title: string;
  status: string;
  assigned_to_name: string | null;
  due_date: string | null;
}

export interface MentorTeamResource {
  id: string;
  title: string;
  url: string;
  resource_type: string;
}

export interface MentorTeamMessage {
  id: string;
  sender_name: string | null;
  message: string;
  created_at: string;
}

export interface MentorTeamDetail extends MentorTeamRow {
  members: MentorTeamMember[];
  tasks: MentorTeamTask[];
  resources: MentorTeamResource[];
  recent_messages: MentorTeamMessage[];
}

export interface MentorNoteRow {
  id: string;
  student_id: string;
  student_name: string;
  class_name: string | null;
  author_id: string;
  author_name: string | null;
  is_own: boolean;
  body: string;
  is_private: boolean;
  note_date: string;
  created_at: string;
  updated_at: string;
}

export interface MentorNoteCreate {
  body: string;
  is_private: boolean;
  note_date?: string | null;
}

export type MentorNoteUpdate = Partial<MentorNoteCreate>;

export interface MentorExamRow {
  id: string;
  title: string;
  class_name: string;
  subject_name: string | null;
  scheduled_at: string;
  status: string;
}

export interface MentorAttendanceSummary {
  present: number;
  absent: number;
  late: number;
  excused: number;
  total: number;
  percentage: number | null;
}

export interface MentorSubjectAttendance extends MentorAttendanceSummary {
  subject_id: string;
  subject_code: string;
  subject_name: string;
}

export interface MentorMenteeResult {
  publication_id: string;
  title: string;
  published_at: string | null;
  total_marks_obtained: number;
  total_marks_possible: number;
  percentage: number;
  grade: string | null;
  rank: number | null;
  result: string;
}

export interface MentorMenteeCoursework {
  id: string;
  title: string;
  subject_name: string | null;
  due_date: string;
  status: string;
  submission_status: string | null;
  score: number | null;
  is_overdue: boolean;
}

export interface MentorMenteeLeave {
  id: string;
  from_date: string;
  to_date: string;
  reason: string;
  status: string;
}

export interface MentorMenteeGuardian {
  name: string | null;
  relation: string;
  phone: string | null;
  email: string | null;
  is_primary: boolean;
}

export interface MentorMenteeDetail {
  profile: MentorMenteeRow;
  gender: string | null;
  date_of_birth: string | null;
  address: string | null;
  guardians: MentorMenteeGuardian[];
  attendance: MentorAttendanceSummary;
  subjects: MentorSubjectAttendance[];
  results: MentorMenteeResult[];
  coursework: MentorMenteeCoursework[];
  upcoming_exams: MentorExamRow[];
  leaves: MentorMenteeLeave[];
  notes: MentorNoteRow[];
}

export interface MentorDashboard {
  academic_year: string | null;
  attendance_threshold: number | null;
  mentee_count: number;
  direct_count: number;
  team_count: number;
  class_count: number;
  average_attendance: number | null;
  at_risk_count: number;
  pending_leave_count: number;
  upcoming_exam_count: number;
  notes_this_month: number;
  at_risk_mentees: MentorMenteeRow[];
  recent_notes: MentorNoteRow[];
  upcoming_exams: MentorExamRow[];
  classes: MentorClassRow[];
  teams: MentorTeamRow[];
}

export type MentorNoticeRow = Omit<PrincipalNoticeRow, "read_count">;

export const fetchMentorDashboard = () => call<MentorDashboard>("/dashboard");

export const fetchMentorMentees = (
  filters: { query?: string; classId?: string; scope?: MentorScope; atRisk?: boolean } = {},
) =>
  call<MentorMenteeList>(
    `/mentees${queryString({ q: filters.query, class_id: filters.classId, scope: filters.scope, at_risk: filters.atRisk || undefined })}`,
  );

export const fetchMentorMentee = (studentId: string) => call<MentorMenteeDetail>(`/mentees/${studentId}`);

export const fetchMentorClasses = () => call<MentorClassRow[]>("/classes");
export const fetchMentorTeams = () => call<MentorTeamRow[]>("/teams");
export const fetchMentorTeam = (teamId: string) => call<MentorTeamDetail>(`/teams/${teamId}`);

export const fetchMentorNotes = (
  filters: { studentId?: string; query?: string; limit?: number; offset?: number } = {},
) =>
  call<PrincipalPage<MentorNoteRow>>(
    `/notes${queryString({ student_id: filters.studentId, q: filters.query, limit: filters.limit, offset: filters.offset })}`,
  );
export const createMentorNote = (studentId: string, payload: MentorNoteCreate) =>
  call<MentorNoteRow>(`/mentees/${studentId}/notes`, jsonInit("POST", payload));
export const updateMentorNote = (noteId: string, payload: MentorNoteUpdate) =>
  call<MentorNoteRow>(`/notes/${noteId}`, jsonInit("PATCH", payload));
export const deleteMentorNote = (noteId: string) => call<null>(`/notes/${noteId}`, { method: "DELETE" });

export const fetchMentorNotices = (
  filters: { query?: string; scope?: "INSTITUTION" | "DEPARTMENT" | "CLASS"; limit?: number; offset?: number } = {},
) =>
  call<PrincipalPage<MentorNoticeRow>>(
    `/notices${queryString({ q: filters.query, scope: filters.scope, limit: filters.limit, offset: filters.offset })}`,
  );
export const fetchMentorNotice = (noticeId: string) => call<MentorNoticeRow>(`/notices/${noticeId}`);
