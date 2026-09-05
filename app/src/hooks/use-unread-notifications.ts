/**
 * Unread-notification badge store (mobile) — mirror of
 * fontend/hooks/use-unread-notifications.ts.
 *
 * A module-level store rather than a per-component timer: the console-header
 * bell is the only permanent consumer, but inbox screens also need to push
 * the badge to refresh after mark-read actions. While at least one subscriber
 * is mounted the store polls `/notifications/unread-count` every 30s and on
 * app-foreground; everything else reads the single cached value.
 */

import { useCallback, useSyncExternalStore } from "react";
import { AppState } from "react-native";

import { fetchUnreadCount } from "@/lib/notifications";

const POLL_MS = 30_000;

let value = 0;
let inFlight: Promise<void> | null = null;
let timer: ReturnType<typeof setInterval> | null = null;
let appStateBound = false;
const listeners = new Set<() => void>();

function emit(): void {
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
    if (!appStateBound) {
      AppState.addEventListener("change", (state) => {
        if (state === "active" && listeners.size > 0) void refreshOnce();
      });
      appStateBound = true;
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

/** Ask the store to re-fetch now (inbox screens call this after mutations). */
export function requestUnreadRefresh(): void {
  void refreshOnce();
}

/** Read the shared unread count, subscribing to updates while mounted. */
export function useUnreadNotifications(): { unread: number; refresh: () => Promise<void> } {
  const unread = useSyncExternalStore(subscribe, () => value, () => 0);
  const refresh = useCallback(() => refreshOnce(), []);
  return { unread, refresh };
}
