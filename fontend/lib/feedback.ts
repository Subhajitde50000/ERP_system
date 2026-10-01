/**
 * Teacher Feedback Campaign API client.
 *
 * Three role surfaces:
 *  - Admin / Principal  →  CRUD + analytics  (prefix: /feedback or /principal/feedback)
 *  - Student            →  list + submit      (prefix: /student/feedback)
 *  - Teacher            →  own results        (prefix: /teacher/feedback)
 *
 * `leadershipCall` / `requestJson` already unwraps the `{ success, data }` envelope
 * and returns `data` directly, so every function here is typed to the inner shape.
 */

import { leadershipCall, queryString } from "./principal";

// ── Shared shapes ─────────────────────────────────────────────────────────────

export interface CampaignTargetIn {
  teacher_id: string;
  subject_id?: string | null;
  class_id?: string | null;
}

export interface CampaignCreate {
  title: string;
  description?: string | null;
  starts_at: string; // ISO datetime
  ends_at: string;
  allow_anonymous: boolean;
  targets: CampaignTargetIn[];
}

export interface CampaignUpdate {
  title?: string;
  description?: string | null;
  starts_at?: string;
  ends_at?: string;
  allow_anonymous?: boolean;
}

export interface CampaignTargetRow {
  id: string;
  teacher_id: string;
  teacher_name: string | null;
  subject_id: string | null;
  subject_name: string | null;
  class_id: string | null;
  class_name: string | null;
}

export interface CampaignRow {
  id: string;
  title: string;
  description: string | null;
  starts_at: string;
  ends_at: string;
  allow_anonymous: boolean;
  status: "DRAFT" | "ACTIVE" | "CLOSED";
  created_at: string;
  closed_at: string | null;
  target_count: number;
}

export interface CampaignDetail extends CampaignRow {
  targets: CampaignTargetRow[];
}

export interface CampaignPage {
  total: number;
  limit: number;
  offset: number;
  items: CampaignRow[];
}

export interface TeacherAggregateResult {
  teacher_id: string;
  teacher_name: string | null;
  response_count: number;
  teaching_clarity_avg: number | null;
  subject_knowledge_avg: number | null;
  interaction_avg: number | null;
  overall_avg: number | null;
  comments: string[] | null;
}

export interface CampaignAnalytics {
  campaign_id: string;
  campaign_title: string;
  total_responses: number;
  results: TeacherAggregateResult[];
}

// ── Student shapes ────────────────────────────────────────────────────────────

export interface StudentFeedbackTarget {
  target_id: string;
  teacher_id: string;
  teacher_name: string | null;
  subject_id: string | null;
  subject_name: string | null;
  class_name: string | null;
  already_submitted: boolean;
}

export interface StudentFeedbackCampaign {
  id: string;
  title: string;
  description: string | null;
  starts_at: string;
  ends_at: string;
  targets: StudentFeedbackTarget[];
}

export interface FeedbackSubmit {
  target_id: string;
  teaching_clarity?: number | null;
  subject_knowledge?: number | null;
  interaction?: number | null;
  overall?: number | null;
  comment?: string | null;
}

// ── Teacher shapes ────────────────────────────────────────────────────────────

export interface TeacherFeedbackResult {
  campaign_id: string;
  campaign_title: string;
  starts_at: string;
  ends_at: string;
  status: string;
  response_count: number;
  teaching_clarity_avg: number | null;
  subject_knowledge_avg: number | null;
  interaction_avg: number | null;
  overall_avg: number | null;
  comments: string[] | null;
}

// ── Admin / Principal API calls ───────────────────────────────────────────────
// NOTE: requestJson already unwraps the { success, data } envelope.
// These functions return the inner `data` type directly.

type AdminPrefix = "feedback" | "principal/feedback";

function adminCall<T>(prefix: AdminPrefix, path: string, init: RequestInit = {}): Promise<T> {
  return leadershipCall<T>(prefix, path, init, "FeedbackAPIError");
}

export function createCampaign(prefix: AdminPrefix, payload: CampaignCreate): Promise<CampaignDetail> {
  return adminCall<CampaignDetail>(prefix, "/campaigns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function listCampaigns(
  prefix: AdminPrefix,
  params: { status?: string; limit?: number; offset?: number } = {},
): Promise<CampaignPage> {
  return adminCall<CampaignPage>(prefix, `/campaigns${queryString(params)}`);
}

export function getCampaign(prefix: AdminPrefix, id: string): Promise<CampaignDetail> {
  return adminCall<CampaignDetail>(prefix, `/campaigns/${id}`);
}

export function updateCampaign(
  prefix: AdminPrefix,
  id: string,
  payload: CampaignUpdate,
): Promise<CampaignDetail> {
  return adminCall<CampaignDetail>(prefix, `/campaigns/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function publishCampaign(prefix: AdminPrefix, id: string): Promise<CampaignDetail> {
  return adminCall<CampaignDetail>(prefix, `/campaigns/${id}/publish`, { method: "POST" });
}

export function closeCampaign(prefix: AdminPrefix, id: string): Promise<CampaignDetail> {
  return adminCall<CampaignDetail>(prefix, `/campaigns/${id}/close`, { method: "POST" });
}

export function deleteCampaign(prefix: AdminPrefix, id: string): Promise<null> {
  return adminCall<null>(prefix, `/campaigns/${id}`, { method: "DELETE" });
}

export function getCampaignAnalytics(prefix: AdminPrefix, id: string): Promise<CampaignAnalytics> {
  return adminCall<CampaignAnalytics>(prefix, `/campaigns/${id}/analytics`);
}

// ── Student API calls ─────────────────────────────────────────────────────────

function studentCall<T>(path: string, init: RequestInit = {}): Promise<T> {
  return leadershipCall<T>("student", path, init, "StudentFeedbackAPIError");
}

export function getStudentFeedbackCampaigns(): Promise<StudentFeedbackCampaign[]> {
  return studentCall<StudentFeedbackCampaign[]>("/feedback");
}

export function submitStudentFeedback(
  campaignId: string,
  payload: FeedbackSubmit,
): Promise<null> {
  return studentCall<null>(`/feedback/${campaignId}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ── Teacher API calls ─────────────────────────────────────────────────────────

export function getTeacherFeedbackResults(): Promise<TeacherFeedbackResult[]> {
  return leadershipCall<TeacherFeedbackResult[]>(
    "teacher",
    "/feedback",
    {},
    "TeacherFeedbackAPIError",
  );
}
