import { NextResponse } from "next/server";

/**
 * Serves /firebase-messaging-sw.js with the Firebase web config injected from
 * server env at request time. A plain static file cannot read NEXT_PUBLIC_*
 * vars, so the service worker script is generated instead of stored in /public.
 * When the env config is absent (development without Firebase), a 204 is
 * returned and web push simply stays hidden in the UI.
 */

const SW_SOURCE = `/* Firebase Cloud Messaging service worker (website notifications). */
/* global importScripts, firebase */
importScripts("https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js");

firebase.initializeApp(__FIREBASE_CONFIG__);

const messaging = firebase.messaging();

messaging.onBackgroundMessage(function (payload) {
  const data = payload.data || {};
  const title = data.title || (payload.notification && payload.notification.title) || "New update";
  const options = {
    body: data.body || (payload.notification && payload.notification.body) || "",
    badge: "/favicon.ico",
    data: { url: data.click_action || data.href || "/notifications" },
    tag: data.type || "erp-notification",
    renotify: true,
  };
  self.registration.showNotification(title, options);
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (clientList) {
      for (const client of clientList) {
        if ("focus" in client) return client.focus();
      }
      return self.clients.openWindow(target);
    }),
  );
});
`;

export function GET(): NextResponse {
  const config = {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? "",
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ?? "",
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "",
    messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID ?? "",
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID ?? "",
  };
  if (!config.apiKey || !config.projectId || !config.messagingSenderId || !config.appId) {
    return new NextResponse(null, { status: 204 });
  }
  const script = SW_SOURCE.replace("__FIREBASE_CONFIG__", JSON.stringify(config));
  return new NextResponse(script, {
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Service-Worker-Allowed": "/",
      "Cache-Control": "no-cache, no-store, must-revalidate",
    },
  });
}
