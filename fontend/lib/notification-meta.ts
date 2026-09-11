/**
 * Notification type → display metadata (web).
 *
 * Single source of truth for turning the *server's* free-string `type` on a
 * notification row into something a human can read and, where we are sure the
 * route exists for the signed-in console, a deep link.
 *
 * The backend owns which events exist (they are produced by the service layer,
 * e.g. `EXAM_RESULT_RELEASED`, `SUBMISSION_RECEIVED`), so this map is keyed by
 * those exact strings and must stay small. Unknown strings (legacy rows, new
 * event types added before this map is updated) degrade to a generic label
 * and no link — never a crash.
 *
 * Deep links are console-relative (e.g. `/online-classes/{id}` inside the
 * student console) and listed for a console only when the route provably
 * exists there (see fontend/app/<role>/…). `param` names the row `data` key
 * that carries the entity id — the link only deepens when the id is present,
 * otherwise it falls back to the section or to no link. Rows may also carry
 * an explicit `data.href` from the producer, which wins over this map.
 */

import type { AppNotificationRow } from "./notifications-api";

type ConsoleSegment = string; // pathname segment: "student" | "teacher" | …

interface TypeMeta {
  /** Friendly chip label shown on the row. */
  label: string;
}

interface LinkRule {
  /** Console-relative section path, e.g. "/online-classes". */
  path: string;
  /** Optional row `data` key holding the id to deep-link to. */
  param?: string;
}

export const NOTIFICATION_TYPE_META: Record<string, TypeMeta> = {
  ONLINE_CLASS: { label: "Online class" },
  SUBMISSION_RECEIVED: { label: "Submission" },
  ASSIGNMENT_REVIEWED: { label: "Assignment reviewed" },
  EXAM_RESULT_RELEASED: { label: "Result released" },
  "parent.leave.filed": { label: "Leave request" },
};

/** type → console segment → deep-link rule (routes verified per console). */
const TYPE_LINKS: Partial<Record<string, Partial<Record<ConsoleSegment, LinkRule>>>> = {
  ONLINE_CLASS: {
    student: { path: "/online-classes", param: "class_id" },
    teacher: { path: "/online-classes", param: "class_id" },
  },
  SUBMISSION_RECEIVED: {
    // Teacher console has a per-submission review page but no list route, so
    // the id is required — otherwise there is nowhere safe to link.
    teacher: { path: "/submissions", param: "submission_id" },
  },
  ASSIGNMENT_REVIEWED: {
    student: { path: "/assignments", param: "assignment_id" },
  },
  EXAM_RESULT_RELEASED: {
    student: { path: "/results" },
  },
  "parent.leave.filed": {
    student: { path: "/attendance" },
  },
};

/** Friendly label for a server type; falls back to a title-cased raw string. */
export function notificationTypeLabel(type: string): string {
  const known = NOTIFICATION_TYPE_META[type]?.label;
  if (known) return known;
  const words = type.toLowerCase().replace(/_/g, " ").replace(/\./g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Console-relative deep link for a row, or null when there is no verified
 * route. Precedence: producer-supplied `data.href` > known type map.
 */
export function notificationHref(
  type: string,
  row: AppNotificationRow,
  consoleSegment: string,
): string | null {
  const custom = row.data?.href ?? row.data?.click_target;
  if (typeof custom === "string" && custom) {
    return custom.startsWith("http") ? custom : `/${consoleSegment}${custom}`;
  }
  const rule = TYPE_LINKS[type]?.[consoleSegment];
  if (!rule) return null;
  const id =
    rule.param && typeof row.data?.[rule.param] === "string"
      ? (row.data[rule.param] as string)
      : null;
  if (rule.param && !id) return null; // detail route requires the id
  const suffix = id ? `${rule.path}/${id}` : rule.path;
  return `/${consoleSegment}${suffix}`;
}
