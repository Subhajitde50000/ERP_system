"use client";

/**
 * Unread-notification badge store (web).
 *
 * One shared subscription store instead of per-component timers: the console
 * shell bell and the notifications page are often mounted at the same time,
 * and each would otherwise poll `/notifications/unread-count` on its own.
 * Here the fetch + 30s interval + window-focus refresh run exactly once while
 * at least one subscriber is mounted, and every subscriber is updated from
 * the single cached value. Screens that mutate read state call
 * `requestUnreadRefresh()` so the badge re-syncs immediately.
 */

import { useCallback, useSyncExternalStore } from "react";

import { fetchUnreadCount } from "@/lib/notifications-api";

const POLL_MS = 30_000;

let value = 0;
let inFlight: Promise<void> | null = null;
let timer: ReturnType<typeof setInterval> | null = null;
let focusBound = false;
const listeners = new Set<() => void>();

function emit(): void {
  const next = value;
  listeners.forEach((listener) => listener());
}

async function refreshOnce(): Promise<void> {
  if (inFlight) return inFlight;
  inFlight = fetchUnreadCount()
    .then((count) => {
      if (count !== value) {
        value = count;
        emit();
      }
    })
    .catch(() => undefined) // transient failure — keep the previous badge
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1) {
    void refreshOnce();
    timer = setInterval(() => void refreshOnce(), POLL_MS);
    if (!focusBound && typeof window !== "undefined") {
      window.addEventListener("focus", () => {
        if (listeners.size > 0) void refreshOnce();
      });
      focusBound = true;
    }
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };
}

/** Ask the store to re-fetch now (after mark-read / mark-all actions). */
export function requestUnreadRefresh(): void {
  void refreshOnce();
}

/** Read the shared unread count, subscribing to updates while mounted. */
export function useUnreadNotifications(): { unread: number; refresh: () => Promise<void> } {
  const unread = useSyncExternalStore(
    subscribe,
    () => value,
    () => 0,
  );
  const refresh = useCallback(() => refreshOnce(), []);
  return { unread, refresh };
}
