/**
 * Notifications API client (mobile) — mirrors fontend/lib/notifications-api.ts.
 *
 * Talks to the platform inbox + push-token registry behind the tenant JWT:
 *   GET  /notifications · /notifications/unread-count
 *   POST /notifications/{id}/read · /notifications/read-all
 *   POST /push-tokens/register · /push-tokens/unregister
 */

import { APIError, requestJson } from "./api-client";
import { API_BASE_URL, getAccessToken, refreshAccessToken } from "./auth";

export { APIError as NotificationAPIError };

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

export type PushPlatform = "android" | "ios" | "web";

function notificationsCall<T>(path: string, init: RequestInit = {}): Promise<T> {
  return requestJson<T>(
    `${API_BASE_URL}/api/v1${path}`,
    init,
    getAccessToken(),
    "NotificationAPIError",
    refreshAccessToken,
  );
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function fetchNotifications(
  opts: { limit?: number; offset?: number; unread_only?: boolean } = {},
): Promise<NotificationPage> {
  const params: string[] = [];
  if (opts.limit !== undefined) params.push(`limit=${opts.limit}`);
  if (opts.offset !== undefined) params.push(`offset=${opts.offset}`);
  if (opts.unread_only) params.push("unread_only=true");
  const qs = params.length ? `?${params.join("&")}` : "";
  return notificationsCall<NotificationPage>(`/notifications${qs}`);
}

export async function fetchUnreadCount(): Promise<number> {
  const data = await notificationsCall<{ unread_count: number }>(
    "/notifications/unread-count",
  );
  return data.unread_count;
}

export function markNotificationRead(id: string): Promise<AppNotificationRow> {
  return notificationsCall<AppNotificationRow>(
    `/notifications/${id}/read`,
    jsonInit("POST", {}),
  );
}

export async function markAllNotificationsRead(): Promise<number> {
  const data = await notificationsCall<{ updated_count: number }>(
    "/notifications/read-all",
    jsonInit("POST", {}),
  );
  return data.updated_count;
}

export function registerPushToken(
  platform: PushPlatform,
  token: string,
): Promise<{ registered: boolean; device_token_id: string }> {
  return notificationsCall<{ registered: boolean; device_token_id: string }>(
    "/push-tokens/register",
    jsonInit("POST", { platform, token }),
  );
}

export function unregisterPushToken(token: string): Promise<{ removed: boolean }> {
  return notificationsCall<{ removed: boolean }>(
    "/push-tokens/unregister",
    jsonInit("POST", { token }),
  );
}
