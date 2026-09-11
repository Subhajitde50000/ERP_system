"use client";

/**
 * Website (browser) push via Firebase Cloud Messaging.
 *
 * The server sends one FCM message per registered platform token; for the
 * browser that token comes from Firebase JS. This module owns:
 *
 *   - reading the Firebase web config from NEXT_PUBLIC_FIREBASE_* env vars
 *     (absent → the whole feature is hidden, never crashes),
 *   - requesting Notification permission and minting/refreshing the FCM
 *     registration token through a VAPID key,
 *   - registering / unregistering that token against our own backend so the
 *     notification worker can deliver to this browser.
 *
 * The actual tray notification is rendered by the service worker served from
 * `/firebase-messaging-sw.js` (see fontend/app/firebase-messaging-sw.js/route.ts,
 * which injects the Firebase web config at request time) — a browser cannot
 * show a notification from the page itself while the tab is backgrounded.
 */

import { initializeApp, type FirebaseApp } from "firebase/app";
import {
  deleteToken,
  getMessaging,
  getToken,
  isSupported,
  onMessage,
  type Messaging,
} from "firebase/messaging";
import { registerPushToken, unregisterPushToken } from "./notifications-api";

interface FirebaseWebConfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
  messagingSenderId: string;
  appId: string;
}

/** Minimal, type-safe read of the NEXT_PUBLIC_FIREBASE_* env block. */
export function firebaseWebConfig(): FirebaseWebConfig | null {
  const cfg: FirebaseWebConfig = {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? "",
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ?? "",
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "",
    messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID ?? "",
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID ?? "",
  };
  const vapid = process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY ?? "";
  return cfg.apiKey && cfg.projectId && cfg.appId && cfg.messagingSenderId && vapid
    ? cfg
    : null;
}

export function firebaseVapidKey(): string {
  return process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY ?? "";
}

/**
 * True when (a) the env config exists, (b) this browser supports FCM and
 * (c) the user has granted notification permission.
 */
export async function isWebPushAvailable(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  if (!("Notification" in window)) return false;
  if (!firebaseWebConfig()) return false;
  try {
    return await isSupported();
  } catch {
    return false;
  }
}

let _app: FirebaseApp | null = null;
let _messaging: Messaging | null = null;

function messaging(): Messaging {
  if (!_app) {
    const cfg = firebaseWebConfig();
    if (!cfg) throw new Error("Firebase web config missing");
    _app = initializeApp({ ...cfg }, "erp-web");
  }
  if (!_messaging) _messaging = getMessaging(_app);
  return _messaging;
}

export type PushPermissionState =
  | "unsupported" // no config / old browser / iframe without permission API
  | "default" // not asked yet
  | "denied"
  | "granted";

export function browserPermissionState(): PushPermissionState {
  if (typeof window === "undefined" || !("Notification" in window)) return "unsupported";
  if (!firebaseWebConfig()) return "unsupported";
  return Notification.permission as PushPermissionState;
}

/**
 * Ask for permission and register this browser. Resolves to the registered
 * FCM token, or null when the user declines / the browser is unsupported.
 */
export async function enableWebPush(): Promise<string | null> {
  const state = browserPermissionState();
  if (state === "denied") return null;
  if (!("Notification" in window)) return null;

  if (state !== "granted") {
    let granted = false;
    try {
      granted = (await Notification.requestPermission()) === "granted";
    } catch {
      return null; // requestPermission threw (e.g. insecure context)
    }
    if (!granted) return null;
  }

  try {
    const mg = messaging();
    const token = await getToken(mg, {
      vapidKey: firebaseVapidKey(),
      serviceWorkerRegistration: await navigator.serviceWorker?.register(
        "/firebase-messaging-sw.js",
      ),
    });
    if (!token) return null;
    await registerPushToken("web", token);
    return token;
  } catch (err) {
    console.error("[web-push] enableWebPush failed", err);
    return null;
  }
}

/** Revoke push for this browser (removes the FCM token + local permission). */
export async function disableWebPush(): Promise<void> {
  if (!firebaseWebConfig() || typeof window === "undefined") return;
  const mg = messaging();
  const current = await getToken(mg, { vapidKey: firebaseVapidKey() }).catch(() => null);
  if (current) {
    try {
      await unregisterPushToken(current);
      await deleteToken(mg);
    } catch (err) {
      console.error("[web-push] disableWebPush failed", err);
    }
  } else if ("Notification" in window && Notification.permission === "granted") {
    // Token already gone from Firebase; still clean the local permission state.
    try {
      await deleteToken(mg);
    } catch {
      /* best effort */
    }
  }
}

/**
 * Foreground message listener: while the app is open FCM does NOT render a
 * tray notification (the service worker only runs in the background), so the
 * page refreshes its inbox/badge. Returns an unsubscribe function.
 */
export function onForegroundPush(onNotification: () => void): () => void {
  if (!firebaseWebConfig() || typeof window === "undefined") return () => undefined;
  try {
    return onMessage(messaging(), () => onNotification());
  } catch {
    return () => undefined;
  }
}
