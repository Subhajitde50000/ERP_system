"use client";

/**
 * Shared notifications inbox rendered by every institution console
 * (student/teacher/admin/principal/… each mount this page under their own
 * route prefix, e.g. `/student/notifications`).
 *
 * Responsibilities:
 *   - list the signed-in user's inbox (newest first) with unread filter
 *   - mark single / mark-all as read (optimistic, reconciling with the API)
 *   - drive the unread badge in the shell
 *   - offer the optional "browser notifications" (web push) enable panel —
 *     shown only when a Firebase web config is present and the browser
 *     supports FCM, hidden otherwise.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BellOff, BellRing, CheckCheck, RefreshCw } from "lucide-react";

import { useUnreadNotifications } from "@/hooks/use-unread-notifications";
import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type AppNotificationRow,
} from "@/lib/notifications-api";
import { notificationHref, notificationTypeLabel } from "@/lib/notification-meta";
import {
  browserPermissionState,
  disableWebPush,
  enableWebPush,
  isWebPushAvailable,
  onForegroundPush,
} from "@/lib/web-push";

const PAGE_SIZE = 100;

function formatAge(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  const diff = Date.now() - at.getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return at.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function NotificationsConsolePage() {
  const pathname = usePathname() ?? "";
  const consoleSegment = pathname.split("/")[1] || "";
  const base = `/${consoleSegment}`; // e.g. "/student"
  const { unread, refresh: refreshBadge } = useUnreadNotifications();
  const [items, setItems] = useState<AppNotificationRow[] | null>(null);
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pushSupported, setPushSupported] = useState(false);
  const [pushEnabled, setPushEnabled] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [pushError, setPushError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const page = await fetchNotifications({ limit: PAGE_SIZE, offset: 0 });
      setItems(page.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load notifications.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    let cancelled = false;
    (async () => {
      const supported = await isWebPushAvailable();
      if (!cancelled) {
        setPushSupported(supported);
        setPushEnabled(supported && browserPermissionState() === "granted");
      }
    })();
    const off = onForegroundPush(() => void load());
    return () => {
      cancelled = true;
      off();
    };
  }, [load]);

  const visible = useMemo(() => {
    if (!items) return [];
    return filter === "unread" ? items.filter((item) => !item.is_read) : items;
  }, [items, filter]);

  async function markRead(row: AppNotificationRow) {
    if (row.is_read) return;
    setItems((prev) => prev?.map((i) => (i.id === row.id ? { ...i, is_read: true, read_at: new Date().toISOString() } : i)) ?? prev);
    try {
      const updated = await markNotificationRead(row.id);
      setItems((prev) => prev?.map((i) => (i.id === row.id ? { ...i, ...updated } : i)) ?? prev);
      void refreshBadge();
    } catch {
      setItems((prev) => prev?.map((i) => (i.id === row.id ? { ...i, is_read: false } : i)) ?? prev);
    }
  }

  async function markAll() {
    if (!items) return;
    const before = items;
    setItems(items.map((i) => ({ ...i, is_read: true })));
    try {
      await markAllNotificationsRead();
      void refreshBadge();
    } catch {
      setItems(before);
    }
  }

  async function togglePush() {
    if (pushEnabled) {
      setPushBusy(true);
      setPushError(null);
      try {
        await disableWebPush();
        setPushEnabled(false);
      } catch {
        setPushError("Could not disable browser notifications right now.");
      } finally {
        setPushBusy(false);
      }
      return;
    }
    setPushBusy(true);
    setPushError(null);
    try {
      const token = await enableWebPush();
      setPushEnabled(token !== null);
      if (token === null) setPushError("Permission was not granted.");
    } finally {
      setPushBusy(false);
    }
  }

  const unreadCount = items?.filter((i) => !i.is_read).length ?? unread;

  return (
    <div className="mx-auto w-full max-w-3xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-xl font-bold text-foreground">Notifications</h1>
          <p className="text-[13px] text-muted-foreground">
            {unreadCount ? `${unreadCount} unread` : "You're all caught up"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void load()}
            aria-label="Refresh notifications"
            className="rounded-lg border border-border bg-white p-2 text-muted-foreground transition hover:bg-muted hover:text-foreground"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => void markAll()}
            disabled={!unreadCount}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-white px-3 py-2 text-[13px] font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:opacity-50"
          >
            <CheckCheck className="h-4 w-4" aria-hidden="true" /> Mark all read
          </button>
        </div>
      </div>

      {pushSupported ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-field border border-border bg-white p-4">
          <div className="flex items-center gap-3">
            {pushEnabled ? (
              <BellRing className="h-5 w-5 text-accent" aria-hidden="true" />
            ) : (
              <BellOff className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
            )}
            <div>
              <p className="text-[13px] font-semibold text-foreground">Browser notifications</p>
              <p className="text-xs text-muted-foreground">
                {pushEnabled
                  ? "New alerts will appear even when this tab is in the background."
                  : "Get alerts on this device while you're signed in."}
              </p>
              {pushError ? <p className="text-xs text-red-600">{pushError}</p> : null}
            </div>
          </div>
          <button
            type="button"
            onClick={() => void togglePush()}
            disabled={pushBusy}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-[13px] font-semibold transition disabled:opacity-60 ${
              pushEnabled
                ? "border border-border bg-white text-muted-foreground hover:bg-muted"
                : "bg-primary text-white hover:opacity-90"
            }`}
          >
            {pushBusy ? "Working…" : pushEnabled ? "Turn off" : "Enable"}
          </button>
        </div>
      ) : null}

      <div className="flex gap-1 rounded-lg bg-muted p-1 text-[13px]">
        {(["all", "unread"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => setFilter(mode)}
            className={`flex-1 rounded-md px-3 py-1.5 font-medium capitalize transition ${
              filter === mode ? "bg-white text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {mode === "unread" ? `Unread (${unreadCount})` : "All"}
          </button>
        ))}
      </div>

      {error ? (
        <div className="rounded-field border border-red-200 bg-red-50 p-4 text-[13px] text-red-700">
          {error}
          <button type="button" onClick={() => void load()} className="ml-2 font-semibold underline">
            Retry
          </button>
        </div>
      ) : null}

      {loading ? (
        <div className="space-y-2" aria-label="Loading notifications">
          {[0, 1, 2].map((n) => (
            <div key={n} className="h-20 animate-pulse rounded-field border border-border bg-muted/50" />
          ))}
        </div>
      ) : visible.length === 0 ? (
        <div className="rounded-field border border-dashed border-border bg-white/60 px-6 py-14 text-center">
          <BellOff className="mx-auto h-8 w-8 text-muted-foreground/60" aria-hidden="true" />
          <p className="mt-3 text-sm font-medium text-foreground">
            {filter === "unread" ? "Nothing unread" : "No notifications yet"}
          </p>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Notices, class alerts and results will show up here and on your devices.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {visible.map((row) => {
            const href = notificationHref(row.type, row, consoleSegment);
            const rowBody = (
              <div
                className={`flex gap-3 rounded-field border p-4 transition ${
                  row.is_read ? "border-border bg-white" : "border-accent/30 bg-accent-light/40"
                } hover:bg-muted/60`}
              >
                <span
                  className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${row.is_read ? "bg-transparent" : "bg-accent"}`}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                    <p className={`text-[13.5px] ${row.is_read ? "font-medium text-foreground/80" : "font-semibold text-foreground"}`}>
                      {row.title}
                    </p>
                    <span className="text-[11px] text-muted-foreground">{formatAge(row.created_at)}</span>
                  </div>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-muted-foreground">{row.body}</p>
                  <p className="mt-1 text-[10.5px] uppercase tracking-wide text-muted-foreground/70">
                    {notificationTypeLabel(row.type)}
                  </p>
                </div>
              </div>
            );
            return (
              <li key={row.id}>
                {href ? (
                  <Link href={href} onClick={() => void markRead(row)} className="block">
                    {rowBody}
                  </Link>
                ) : (
                  <button type="button" onClick={() => void markRead(row)} className="block w-full text-left">
                    {rowBody}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
