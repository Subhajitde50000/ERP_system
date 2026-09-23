/**
 * Institution admin API client — the real backend behind the /admin console.
 *
 * Every call is tenant-scoped: the backend resolves the tenant from the JWT,
 * so no slug is sent. The access token comes from the tenant auth store in
 * `lib/auth.ts` (in-memory). 401s are surfaced so the shell can redirect to
 * the institution login.
 */

import { API_BASE_URL, getAccessToken, refreshAccessToken } from "./auth";
import { APIError, requestJson, guardTenantRefresh } from "./api-client";

const BASE = `${API_BASE_URL}/api/v1/institution`;

/** Re-exported so admin pages can `catch (e) { if (e instanceof …) }`. */
export { APIError as InstitutionAPIError };

const call = <T>(path: string, init: RequestInit = {}): Promise<T> =>
  requestJson<T>(
    `${BASE}${path}`,
    init,
    getAccessToken(),
    "InstitutionAPIError",
    refreshAccessToken,
    guardTenantRefresh,
  );

// ── Types ────────────────────────────────────────────────────────────────────

export interface DashboardSummary {
  tenant_id: string;
  name: string;
  slug: string;
  type: string;
  academic_year: string | null;
  counts: Record<string, number>;
  enabled_modules: string[];
  onboarding_complete: boolean;
}

export interface AcademicYear {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
}

export interface Department {
  id: string;
  name: string;
  code: string;
  description: string | null;
  hod_id: string | null;
  hod_name: string | null;
  is_active: boolean;
  class_count: number;
  staff_count: number;
}

export interface StaffMember {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  is_active: boolean;
  last_login_at: string | null;
  roles: string[];
  department_id: string | null;
  department_name: string | null;
}

export interface StudentRecord {
  id: string;
  name: string;
  email: string | null;
  roll_no: string | null;
  gender: string | null;
  is_active: boolean;
  enrollment: { class_id?: string; class_name?: string; academic_year_name?: string } | null;
}

export interface ClassRecord {
  id: string;
  name: string;
  code: string;
  academic_year_name: string | null;
  department_name: string | null;
  is_active: boolean;
  grade_id: string | null;
  program_id: string | null;
  section_label: string | null;
}

/** A single section/batch within a grade or program group. */
export interface SectionRecord {
  id: string;
  name: string;
  code: string;
  section_label: string | null;
  class_teacher_id: string | null;
  class_teacher_name: string | null;
  enrolled_count: number;
  subject_count: number;
  room_no: string | null;
  is_active: boolean;
}

/** School: grade group + its sections. */
export interface ClassGradeRecord {
  id: string;
  academic_year_id: string;
  academic_year_name: string | null;
  department_id: string;
  department_name: string | null;
  name: string;
  grade_number: number;
  stream: string | null;
  is_active: boolean;
  sections: SectionRecord[];
}

/** College: program+semester group + its batches. */
export interface ClassProgramRecord {
  id: string;
  academic_year_id: string;
  academic_year_name: string | null;
  department_id: string;
  department_name: string | null;
  program_name: string;
  program_code: string;
  semester_number: number;
  is_active: boolean;
  batches: SectionRecord[];
}

export interface ModuleRow {
  key: string;
  name: string;
  is_core: boolean;
  is_enabled: boolean;
  price_monthly: number;
}

export interface SettingsInfo {
  timezone: string;
  currency: string;
  onboarding_complete: boolean;
}

export interface InstitutionProfile {
  id: string;
  name: string;
  slug: string;
  type: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  country: string;
  pincode: string | null;
  website: string | null;
  logo_url: string | null;
  timezone: string;
  plan_name: string | null;
  subscription_status: string | null;
}

export interface BulkUploadRowIssue {
  row: number;
  message: string;
}

export interface BulkUploadResult {
  total: number;
  created: number;
  errors: BulkUploadRowIssue[];
  warnings: BulkUploadRowIssue[];
}

// ── Calls ────────────────────────────────────────────────────────────────────

export const fetchDashboard = () => call<DashboardSummary>("/dashboard");

export const fetchAcademicYears = () => call<AcademicYear[]>("/academic-years");
export const createAcademicYear = (payload: Partial<AcademicYear> & { name: string; start_date: string; end_date: string }) =>
  call<AcademicYear>("/academic-years", { method: "POST", body: JSON.stringify(payload) });
export const updateAcademicYear = (id: string, payload: Partial<AcademicYear>) =>
  call<AcademicYear>(`/academic-years/${id}`, { method: "PUT", body: JSON.stringify(payload) });
export const deleteAcademicYear = (id: string) =>
  call<null>(`/academic-years/${id}`, { method: "DELETE" });

export const fetchDepartments = () => call<Department[]>("/departments");
export const createDepartment = (payload: { name: string; code: string; description?: string }) =>
  call<Department>("/departments", { method: "POST", body: JSON.stringify(payload) });
export const updateDepartment = (id: string, payload: { hod_id?: string | null; name?: string; code?: string; description?: string; is_active?: boolean }) =>
  call<Department>(`/departments/${id}`, { method: "PUT", body: JSON.stringify(payload) });
export const deleteDepartment = (id: string) =>
  call<null>(`/departments/${id}`, { method: "DELETE" });

export const fetchStaff = () => call<StaffMember[]>("/staff");
export const uploadStaff = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return call<BulkUploadResult>("/staff/bulk", { method: "POST", body: form });
};
export const inviteStaff = (payload: {
  name: string;
  email: string;
  phone?: string;
  role: string;
  departmentId?: string;
  password?: string;
}) =>
  call<StaffMember>("/staff", {
    method: "POST",
    body: JSON.stringify({
      name: payload.name,
      email: payload.email,
      phone: payload.phone,
      role: payload.role,
      department_id: payload.departmentId,
      password: payload.password,
    }),
  });
export const assignStaffRole = (userId: string, roleName: string, departmentId?: string) =>
  call<StaffMember>(`/staff/${userId}/roles`, {
    method: "PUT",
    body: JSON.stringify({ role_name: roleName, department_id: departmentId }),
  });
export const revokeStaffRole = (userId: string, roleName: string, departmentId?: string) =>
  call<StaffMember>(
    `/staff/${userId}/roles/${encodeURIComponent(roleName)}${
      departmentId ? `?department_id=${encodeURIComponent(departmentId)}` : ""
    }`,
    { method: "DELETE" },
  );
export const updateStaff = (
  userId: string,
  payload: { name?: string; email?: string; phone?: string; departmentId?: string }
) =>
  call<StaffMember>(`/staff/${userId}`, {
    method: "PUT",
    body: JSON.stringify({
      name: payload.name,
      email: payload.email,
      phone: payload.phone,
      department_id: payload.departmentId,
    }),
  });
export const deleteStaff = (userId: string) =>
  call<null>(`/staff/${userId}`, { method: "DELETE" });
export const setStaffActive = (userId: string, active: boolean) =>
  call<StaffMember>(`/staff/${userId}/active?active=${active}`, { method: "PUT" });
export const resendPasswordReset = (userId: string) =>
  call<null>(`/users/${userId}/password-reset`, { method: "POST" });
export const resendStudentPasswordReset = (studentId: string) =>
  call<null>(`/students/${studentId}/password-reset`, { method: "POST" });

export const fetchStudents = () => call<StudentRecord[]>("/students");
export const fetchClasses = () => call<ClassRecord[]>("/classes");
export const createStudent = (payload: { name: string; roll_no: string; email?: string; gender?: string; class_id?: string; password?: string }) =>
  call<StudentRecord>("/students", { method: "POST", body: JSON.stringify(payload) });
export const updateStudent = (
  id: string,
  payload: { name?: string; roll_no?: string; email?: string; gender?: string; class_id?: string; is_active?: boolean }
) => call<StudentRecord>(`/students/${id}`, { method: "PUT", body: JSON.stringify(payload) });
export const deleteStudent = (id: string) =>
  call<null>(`/students/${id}`, { method: "DELETE" });
export const uploadStudents = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return call<BulkUploadResult>("/students/bulk", { method: "POST", body: form });
};

// ── Subjects ─────────────────────────────────────────────────────────────────

export interface SubjectRecord {
  id: string;
  name: string;
  code: string;
  class_id: string;
  class_name: string | null;
  subject_type: string;
  credits: number | null;
  max_marks: number;
  passing_marks: number;
  is_active: boolean;
  teachers: { id: string; name: string; role: string }[];
}

export const fetchSubjects = () => call<SubjectRecord[]>("/subjects");
export const createSubject = (payload: {
  name: string;
  code: string;
  class_id: string;
  subject_type?: string;
  credits?: number;
  max_marks?: number;
  passing_marks?: number;
}) => call<SubjectRecord>("/subjects", { method: "POST", body: JSON.stringify(payload) });

export const updateSubject = (
  id: string,
  payload: {
    name?: string;
    subject_type?: string;
    credits?: number;
    max_marks?: number;
    passing_marks?: number;
    is_active?: boolean;
  }
) => call<SubjectRecord>(`/subjects/${id}`, { method: "PUT", body: JSON.stringify(payload) });

export const deleteSubject = (id: string) =>
  call<null>(`/subjects/${id}`, { method: "DELETE" });

// ── School grade wizard ─────────────────────────────────────────────────────

export const fetchGrades = (academic_year_id?: string) =>
  call<ClassGradeRecord[]>(`/grades${academic_year_id ? `?academic_year_id=${academic_year_id}` : ""}`);

export const createGrade = (payload: {
  academic_year_id: string;
  department_id: string;
  grade_number: number;
  stream?: string;
  sections: string[];
  max_strength?: number;
  class_teacher_id?: string;
}) => call<ClassGradeRecord>("/grades", { method: "POST", body: JSON.stringify(payload) });

export const deleteGrade = (grade_id: string) =>
  call<null>(`/grades/${grade_id}`, { method: "DELETE" });

// ── College program wizard ──────────────────────────────────────────────────

export const fetchPrograms = (department_id?: string, academic_year_id?: string) => {
  const params = new URLSearchParams();
  if (department_id) params.set("department_id", department_id);
  if (academic_year_id) params.set("academic_year_id", academic_year_id);
  const qs = params.toString();
  return call<ClassProgramRecord[]>(`/programs${qs ? `?${qs}` : ""}`);
};

export const createProgram = (payload: {
  academic_year_id: string;
  department_id: string;
  program_name: string;
  program_code: string;
  semester_number: number;
  batches: string[];
  max_strength?: number;
  class_teacher_id?: string;
}) => call<ClassProgramRecord>("/programs", { method: "POST", body: JSON.stringify(payload) });

export const deleteProgram = (program_id: string) =>
  call<null>(`/programs/${program_id}`, { method: "DELETE" });

export const fetchModules = () => call<ModuleRow[]>("/modules");
export const toggleModule = (key: string, enabled: boolean) =>
  call<ModuleRow>(`/modules/${key}`, { method: "PUT", body: JSON.stringify({ enabled }) });

export const fetchSettings = () => call<SettingsInfo>("/settings");
export const updateSettings = (payload: Partial<SettingsInfo>) =>
  call<SettingsInfo>("/settings", { method: "PUT", body: JSON.stringify(payload) });

export const fetchProfile = () => call<InstitutionProfile>("/profile");
export const updateProfile = (payload: Partial<InstitutionProfile>) =>
  call<InstitutionProfile>("/profile", { method: "PUT", body: JSON.stringify(payload) });

// ── C-IA-12 · guardian (parent) links ───────────────────────────────────────
//
// The office side of the parent portal. Wire format is snake_case like every other
// endpoint here, and the shapes are `ParentLinkRow` / `ParentLinkPage` in
// `backend/app/schemas/parent.py`.
//
// Two rules the UI has to respect because the server enforces them:
//  * creating a link is school-only — a college gets a 409, so the board hides the
//    button instead of letting an admin discover it;
//  * `activation_code` is present on exactly one response: the one that created or
//    reissued it. It is a capability, never listable afterwards, so the office reads
//    it off the dialog in front of them or sends a fresh one.

export interface GuardianLinkRow {
  id: string;
  tenant_id: string;
  parent_id: string | null;
  parent_name: string | null;
  parent_email: string | null;
  parent_phone: string | null;
  /** false once the account has been disabled — the portal is closed either way */
  parent_is_active: boolean | null;
  student_id: string;
  student_name: string;
  student_roll_no: string | null;
  class_name: string | null;
  relation: string;
  is_primary: boolean;
  /** PENDING_CLAIM | ACTIVE | SUSPENDED */
  status: string;
  access_scope: string[];
  access_upto: string | null;
  activation_code?: string | null;
  code_expires_at: string | null;
  claimed_at: string | null;
  note: string | null;
  managed_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface GuardianLinkBoard {
  total: number;
  limit: number;
  offset: number;
  items: GuardianLinkRow[];
  /** Link counts by status, plus `total` */
  counts: Record<string, number>;
  tenant_type: string;
  portal_enabled?: boolean;
  /** Students with no guardian on record at all — the gap this page exists to close */
  unlinked_count: number;
  unlinked: { student_id: string; student_name: string; student_roll_no: string | null; class_name: string | null }[];
}

export interface GuardianLinkCreate {
  student_id: string;
  relation: string;
  /** Attach an account the school already created… */
  parent_user_id?: string | null;
  /** …or invite one behind an activation code */
  parent_name?: string | null;
  email?: string | null;
  phone?: string | null;
  is_primary?: boolean;
  /** Omitted/null = the tenant default (all modules); [] is an explicit "nothing yet". */
  access_scope?: string[] | null;
  access_upto?: string | null;
  note?: string | null;
  /** Create the login now and mail a reset link, instead of the code route. */
  create_account?: boolean;
  send_email?: boolean;
}

export interface GuardianLinkUpdate {
  relation?: string;
  is_primary?: boolean;
  status?: "ACTIVE" | "SUSPENDED";
  access_scope?: string[] | null;
  access_upto?: string | null;
  note?: string | null;
}

export const fetchGuardianLinks = (filters: {
  query?: string;
  status?: string;
  class_id?: string;
  relation?: string;
  primary_only?: boolean;
  limit?: number;
  offset?: number;
} = {}) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return call<GuardianLinkBoard>(`/parent-links${qs ? `?${qs}` : ""}`);
};

export const createGuardianLink = (payload: GuardianLinkCreate) =>
  call<GuardianLinkRow>(`/parent-links`, { method: "POST", body: JSON.stringify(payload) });

export const updateGuardianLink = (linkId: string, payload: GuardianLinkUpdate) =>
  call<GuardianLinkRow>(`/parent-links/${linkId}`, { method: "PATCH", body: JSON.stringify(payload) });

export const issueGuardianLinkCode = (linkId: string) =>
  call<GuardianLinkRow>(`/parent-links/${linkId}/code`, { method: "POST" });

export const deleteGuardianLink = (linkId: string) =>
  call<null>(`/parent-links/${linkId}`, { method: "DELETE" });
