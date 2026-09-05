/**
 * Remote push registration for the mobile app (Android + iOS via Firebase FCM).
 *
 * Firebase's native SDKs (@react-native-firebase) deliver true FCM tokens on
 * both platforms, but they only exist inside a *development build* that has
 * been compiled with the project's own Firebase config (google-services.json
 * / GoogleService-Info.plist) — Expo Go and the web target do not ship the
 * native module. Everything here is therefore guarded:
 *
 *   - static imports are avoided; the Firebase module is required lazily,
 *   - every native call is wrapped so a missing module / missing config can
 *     never crash the app — remote push silently stays off and the in-app
 *     inbox keeps working,
 *   - a module-level token cache lets logout unregister the exact token that
 *     was registered.
 *
 * Expo SDK 57 managed projects: see doc/notification-system.md (or the repo
 * README) for the one-time Firebase project + prebuild steps.
 */

import { Platform } from "react-native";
import * as Notifications from "expo-notifications";

import { registerPushToken, unregisterPushToken, type PushPlatform } from "./notifications";

// Set by Expo's config plugin; harmless default so notifications still work
// before the user opens a screen.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

let registeredToken: string | null = null;
let registeredPlatform: PushPlatform | null = null;

/** True when this runtime can talk to Firebase (native dev build, not web). */
export function nativeFirebaseAvailable(): boolean {
  if (Platform.OS !== "android" && Platform.OS !== "ios") return false;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    require("@react-native-firebase/messaging");
    return true;
  } catch {
    return false;
  }
}

async function hasNotificationPermission(): Promise<boolean> {
  try {
    const current = await Notifications.getPermissionsAsync();
    if (current.granted) return true;
    if (current.status === "undetermined") {
      const asked = await Notifications.requestPermissionsAsync();
      return asked.granted;
    }
    return false;
  } catch {
    return false;
  }
}

/**
 * Request permission and return this device's FCM token + platform.
 * Resolves to null when push cannot run on this runtime.
 */
export async function getFcmRegistration(): Promise<{
  token: string;
  platform: PushPlatform;
} | null> {
  if (!nativeFirebaseAvailable()) return null;
  if (!(await hasNotificationPermission())) return null;

  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const messaging = require("@react-native-firebase/messaging").default;
    // iOS asks for permission through Firebase too; Android 13+ is covered by
    // the expo-notifications check above.
    if (Platform.OS === "ios") {
      const authStatus = await messaging().requestPermission();
      const granted =
        authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
        authStatus === messaging.AuthorizationStatus.PROVISIONAL;
      if (!granted) return null;
    }
    const token = await messaging().getToken();
    if (!token) return null;
    return { token, platform: Platform.OS === "ios" ? "ios" : "android" };
  } catch {
    return null;
  }
}

/**
 * Register this device with the ERP backend for push delivery.
 * Safe to call after every login — re-registration is an idempotent upsert.
 */
export async function registerDevicePush(): Promise<boolean> {
  const registration = await getFcmRegistration();
  if (!registration) return false;
  try {
    await registerPushToken(registration.platform, registration.token);
    registeredToken = registration.token;
    registeredPlatform = registration.platform;
    return true;
  } catch {
    return false; // backend unreachable — the next login will retry
  }
}

/**
 * Tell the backend this device no longer wants push (logout / user revoke).
 * Best-effort: if the network is gone the token simply stays registered and
 * the server's delivery worker will deactivate it once FCM reports it dead.
 */
export async function unregisterDevicePush(): Promise<void> {
  const token = registeredToken;
  registeredToken = null;
  registeredPlatform = null;
  if (!token) return;
  try {
    await unregisterPushToken(token);
  } catch {
    /* best-effort (see doc comment) */
  }
}
