/**
 * Notifications API client — the platform inbox shared by every institution
 * console (student, teacher, admin, principal, …) and the web-push registry.
 *
 * Backend surface (backend/app/routers/notifications.py):
 *   GET  /api/v1/notifications              → inbox (newest first)
 *   GET  /api/v1/notifications/unread-count → bell badge value
 *   POST /api/v1/notifications/{id}/read
 *   POST /api/v1/notifications/read-all
 *   POST /api/v1/push-tokens/register | unregister
 *
 * All calls ride the ordinary tenant JWT (same transport as the principal /
 * coordinator clients) so a signed-in user can only ever read their own rows.
 */

import {
  APIError,
  errorMessage,
  guardTenantRefresh,
  requestJson,
} from "./api-client";
import { API_BASE_URL, getAccessToken, refreshAccessToken } from "./auth";

export { APIError as NotificationAPIError };

/** One notification row as stored in the `notifications` table (snake_case). */
export interface AppNotificationRow {
  id: string;
  title: string;
  body: string;
  type: string;
  data: Record<string, unknown>;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface NotificationPage {
  total: number;
  unread_count: number;
  limit: number;
  offset: number;
  items: AppNotificationRow[];
}

/** Platform token handed to the API when registering for web push. */
export type PushPlatform = "android" | "ios" | "web";

function notificationsCall<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  return requestJson<T>(
    `${API_BASE_URL}/api/v1${path}`,
    init,
    getAccessToken(),
    "NotificationAPIError",
    refreshAccessToken,
    guardTenantRefresh,
  );
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

/** Paginated inbox, newest first. */
export function fetchNotifications(
  opts: { limit?: number; offset?: number; unread_only?: boolean } = {},
): Promise<NotificationPage> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts.offset !== undefined) params.set("offset", String(opts.offset));
  if (opts.unread_only) params.set("unread_only", "true");
  const qs = params.toString();
  return notificationsCall<NotificationPage>(
    `/notifications${qs ? `?${qs}` : ""}`,
  );
}

/** Unread total for the bell badge. */
export async function fetchUnreadCount(): Promise<number> {
  const data = await notificationsCall<{ unread_count: number }>(
    "/notifications/unread-count",
  );
  return data.unread_count;
}

/** Mark one notification read; returns the updated row. */
export function markNotificationRead(id: string): Promise<AppNotificationRow> {
  return notificationsCall<AppNotificationRow>(
    `/notifications/${id}/read`,
    jsonInit("POST", {}),
  );
}

/** Mark the whole inbox read; resolves to the number of rows updated. */
export async function markAllNotificationsRead(): Promise<number> {
  const data = await notificationsCall<{ updated_count: number }>(
    "/notifications/read-all",
    jsonInit("POST", {}),
  );
  return data.updated_count;
}

/** Register this device/browser for push delivery. */
export function registerPushToken(
  platform: PushPlatform,
  token: string,
): Promise<{ registered: boolean; device_token_id: string }> {
  return notificationsCall<{ registered: boolean; device_token_id: string }>(
    "/push-tokens/register",
    jsonInit("POST", { platform, token }),
  );
}

/** Deactivate a push token (sign out / user revoked permission). */
export function unregisterPushToken(token: string): Promise<{ removed: boolean }> {
  return notificationsCall<{ removed: boolean }>(
    "/push-tokens/unregister",
    jsonInit("POST", { token }),
  );
}

/** Keep the error helper importable by callers that pattern-match on it. */
export { errorMessage };
