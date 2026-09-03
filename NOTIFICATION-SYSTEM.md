# Notification & Push System — Integration Report

This document explains the notification system that was integrated across the
three apps in this repository — **backend** (FastAPI), **website** (`fontend`,
Next.js) and **mobile** (`app`, Expo/React Native) — how it works, why it is
built the way it is, and what still needs real Firebase credentials to light
up.

---

## 1. What was asked

> Scan the app and website, check whether the notification system is properly
> integrated, add real Firebase Cloud Messaging (FCM) push for **Android**,
> **iOS** and **website notifications**, add the feature properly like real
> world use, avoid duplicate/unnecessary code, and make it production-ready.

The scan found:

- Notifications existed only as **in-app rows** with no delivery story and no
  user-facing inbox on the website or the mobile app.
- The website carried dead notification scaffolding: a 36-event client-side
  taxonomy (`lib/notification.ts`, `types/notification.ts`) that did not match
  the backend's type strings, plus a stubbed `notification-data.ts`. None of it
  was mounted or referenced at runtime.
- There was no device-token registry, no outbound push path, no unread badge,
  no bell, and no per-role inbox pages.

---

## 2. Architecture at a glance

```
Producers (services that create events)
   │  PushService.create_in_app_notifications(db, user_ids, title, body, type, data)
   ▼
notifications (in-app rows, one per recipient)
   └─▶ notification_deliveries (outbox) ──┐
                                          ▼
                              deliver_pending() worker (every 10s)
                                          │
                                    device_tokens (per platform+user)
                                          │
                     ┌────────────────────┼─────────────────────┐
                     ▼                    ▼                     ▼
              FCM v1 HTTP          Android / iOS          Web browser
              (server → FCM)   (FCM native SDK)     (Firebase JS SDK + SW)
```

- Every push is **durable**: the row is written first, then the delivery is
  attempted by a worker, so a dead network or a failed FCM call never loses a
  notification. Rows without any registered device simply stay unread in the
  in-app inbox (which every client still reads).
- One **unified inbox API** serves every role, scoped by the signed-in user's
  JWT (see §5).

---

## 3. Backend (`backend/app`)

### 3.1 Tables (both schema files updated)

`database/database.sql` (main schema) and `database/notification_push_update.sql`
(update-only file, per repo convention) contain:

- `device_tokens` — one row per device/user/platform with the FCM token,
  `is_active` soft-delete and `partial unique index
  idx_device_tokens_user_active` (one active token per platform per user).
- `notification_deliveries` — the outbox: target token/platform, `status`
  (`PENDING/DELIVERED/FAILED/DEACTIVATED`), provider message id, timestamps
  and retry metadata.

Alembic: `backend/app/alembic/versions/c3d4e5f6a7b8_notification_push_deliveries.py`
is written off the true head (`c2d3e4f5a6b7`); `alembic/env.py` tracks the ORM
tables so future autogenerate runs are consistent.

### 3.2 New modules

| File | Responsibility |
|---|---|
| `models/notification.py` | `DeviceToken`, `NotificationDelivery` ORM models |
| `schemas/notification.py` | shared Pydantic contracts: row/page/envelope/token payloads |
| `services/fcm_client.py` | minimal **FCM HTTP v1** client (OAuth2 service-account token → `POST /v1/projects/{id}/messages:send`), one reusable `httpx.AsyncClient` |
| `services/notification_service.py` | inbox (list/unread/mark-read/mark-all), token registry, enqueue, and the `deliver_pending()` worker |
| `services/push_service.py` | thin facade used by producers — one call creates in-app rows **and** enqueues deliveries |
| `routers/notifications.py` | `notifications_router` + `push_token_router` |

`schemas/online_class.py` and `models/online_class.py` keep the pre-existing
`Notification` model/name exports but delegate the old inbox helpers to
`NotificationService` so no second implementation exists.

### 3.3 Config

`config.py` + `backend/.env.example`:

```
FCM_PROJECT_ID=…              # Firebase project id
FCM_SERVICE_ACCOUNT_JSON=…    # service-account JSON (path or inline string)
FCM_MAX_RETRIES=3
FCM_DELIVERY_BATCH_SIZE=100
```

The client reads the service account only when the worker runs; when FCM is not
configured the whole system degrades to **in-app-only** mode (no crash).

### 3.4 Endpoints (mounted in `main.py` under `/api/v1`)

```
GET    /notifications            ?limit&offset&unread_only   → {total, unread_count, limit, offset, items[]}
GET    /notifications/unread-count                           → {unread_count}
POST   /notifications/{id}/read                              → updated row
POST   /notifications/read-all                               → {updated_count}
POST   /push-tokens/register    {platform, token}            → {registered, device_token_id}
POST   /push-tokens/unregister  {token}                      → {removed}
```

Auth: tenant JWT (same `AnyTenantUser` dependency as every console route) —
users can only ever read/mark **their own** rows and only register tokens
against their own account. Responses use the repo-standard `{success, data,
message}` envelope.

### 3.5 Producer wiring (events that generate notifications today)

| Event `type` | Sent to | Payload keys | Human text |
|---|---|---|---|
| `ONLINE_CLASS` | invited students | `class_id`, `topic` | online class scheduled |
| `SUBMISSION_RECEIVED` | assignment teacher | `assignment_id`, `submission_id`, `student_id`, `version` | new submission |
| `ASSIGNMENT_REVIEWED` | submitting student | `assignment_id`, `submission_id`, `decision` | submission reviewed |
| `EXAM_RESULT_RELEASED` | students in published results | `publication_id`, `publication_title` | results released |
| `parent.leave.filed` | guardian's child | `leave_id` | leave filed by guardian |

Every call site is wrapped best-effort (`try/except` + logging): a notification
failure must never roll back the business transaction it accompanies. Wired in
`online_class_service.py`, `teacher_service.py`, `student_service.py`,
`exam_controller_service.py` and `parent_service.py`.

### 3.6 Delivery worker

`services/scheduler_service.py` registers an APScheduler job every 10 s that
calls `NotificationService.deliver_pending()`: batches `PENDING` rows, sends via
FCM v1, and marks rows `DELIVERED` (with the provider message id), `FAILED`
(retry-safe) or `DEACTIVATED` (when FCM reports the token is no longer valid —
it also soft-deletes the token so future batches skip it).

---

## 4. Website (`fontend`, Next.js)

### 4.1 Inbox for every console

- A single reusable page component `components/notifications/notifications-page.tsx`
  is mounted by **eleven role pages** `fontend/app/<role>/notifications/page.tsx`
  (student, teacher, admin, principal, vice-principal, coordinator, HOD,
  exam-controller, hostel-warden, librarian, parent) — one line per route, no
  per-role UI duplication.
- **Bell + unread badge** live in the shared `InstitutionConsoleShell` header,
  so every tenant console gets the entry point at once; the bell links to the
  current console's `/notifications` page.
- Page features: newest-first list, unread filter, mark-single/mark-all read
  (optimistic, reconciled with the API), relative timestamps, friendly type
  chips and console-verified deep links (see §4.3).
- `lib/notifications-api.ts` is the only API client (paginated inbox, unread
  count, mark read/all, push register/unregister) riding the existing
  `requestJson` tenant-JWT transport with silent refresh.

### 4.2 Unread badge — one poll, many readers

`hooks/use-unread-notifications.ts` is a **shared subscription store**, not a
per-component timer: the shell bell and the inbox page are mounted at the same
time and previously would each have polled `/notifications/unread-count`. The
store fetches once per 30 s (plus on window focus) while at least one consumer
is subscribed and pushes the single cached value to all subscribers. Mutations
call the same store to re-sync immediately.

### 4.3 Notification type → display + deep links

`lib/notification-meta.ts` is the **single** place mapping the backend's real
type strings to friendly labels and console-relative links, and it only links
to routes that provably exist for that console (e.g. `SUBMISSION_RECEIVED`
→ `/submissions/{submission_id}` in the teacher console). Rows may carry a
producer-supplied `data.href` which wins. Unknown/legacy types degrade to a
title-cased label and no link — never a crash.

### 4.4 Web push (browser notifications)

- `lib/web-push.ts` owns the Firebase JS SDK (v10 compat line, installed as
  `firebase@^10.14.1`): reads `NEXT_PUBLIC_FIREBASE_*` env vars, requests
  `Notification` permission, mints an FCM token with the VAPID key and
  registers it with the backend.
- The service worker is served from `/firebase-messaging-sw.js` by
  `fontend/app/firebase-messaging-sw.js/route.ts`, which injects the Firebase
  web config server-side at request time (a static file in `public/` cannot
  read env vars) and returns `204` when Firebase isn't configured.
- **Foreground** messages refresh the open page's inbox (no duplicate tray
  bubble); **background** messages render the system tray notification via the
  service worker and route clicks back to the app.
- Sign-out calls `disableWebPush()` first, so a shared browser stops receiving
  private notifications after logout.
- When the Firebase env vars are absent the whole panel is hidden and the app
  behaves exactly as before (in-app inbox only).

### 4.5 Dead code removed

Per the "no duplicates" instruction, the following were deleted:

- `fontend/lib/notification-data.ts` (stub, unused)
- `fontend/lib/notification.ts` (36-event client taxonomy that never matched
  the backend and was referenced by nothing at runtime)
- `fontend/types/notification.ts` (fed only the deleted matrix)
- the `NotificationEvent`-based `NotificationRule` block in `types/settings.ts`

The as-yet-unmounted settings **channel-preference** types (`NotificationChannel`,
`NotificationPreference`) were kept because they describe a different, future
feature (per-channel user preferences) and are self-contained.

---

## 5. Mobile app (`app`, Expo / React Native)

### 5.1 What was added

- `lib/notifications.ts` — mobile mirror of the web API client (same endpoint
  contracts, same envelope unwrapping).
- `lib/push-registry.ts` — native push registration:
  - static imports are avoided and `@react-native-firebase/messaging` is
    `require()`d lazily, so **Expo Go and web builds degrade safely** — the
    module simply isn't there and push stays off instead of crashing;
  - requests permission through `expo-notifications` (and Firebase on iOS),
    mints the FCM token, registers `{platform, token}` with the backend;
  - `unregisterDevicePush()` keeps the exact token that was registered so
    logout cleans up correctly (best-effort if offline).
- `hooks/use-unread-notifications.ts` — same shared-store pattern as the web.
- `components/notification-bell.tsx` — one shared bell/badge, added to the
  student, teacher and parent shell headers.
- `components/notifications-screen.tsx` — one shared inbox screen, mounted at
  `(student)/notifications.tsx`, `(teacher)/notifications.tsx` and
  `(parent)/notifications.tsx` and registered in each group layout.
- `lib/session.tsx` — registers the device for push whenever a user is signed
  in (after hydration/login) and unregisters on logout.
- `lib/format.ts` — added a `timeAgo()` helper reused by the inbox.

### 5.2 Expo/Firebase native setup (one-time)

Dependencies added: `@react-native-firebase/app`, `@react-native-firebase/messaging`
(v26.x), `expo-notifications` (SDK 57). `app/app.json` already registers the
config plugins (`expo-notifications`, `@react-native-firebase/app`,
`@react-native-firebase/messaging`) and the Android 13
`android.permission.POST_NOTIFICATIONS` permission.

To build a dev client / store build with real push:

1. In Firebase console create (or reuse) a project, then add **Android**
   (`google-services.json`) and **iOS** (`GoogleService-Info.plist`) apps whose
   package/bundle ids match `app.json` (`android.package`,
   `ios.bundleIdentifier`).
2. Drop the two files into the `app/` directory (they are consumed at
   `expo prebuild` time; keep them out of git if you prefer, or use EAS
   secrets).
3. `npx expo prebuild` then build/run — native FCM modules only exist in
   development builds, **not Expo Go**.
4. Android 13+ asks for notification permission at runtime (the app requests it
   the first time push is registered); iOS asks through Firebase.

### 5.3 Mobile behavior notes

- While the app is open, incoming pushes are presented via the
  `expo-notifications` foreground handler configured in `push-registry.ts`.
- The header badge polls the server and refreshes on app-foreground, and inbox
  actions (`mark read`, `mark all read`) re-sync it immediately through the
  shared store.
- Notification-tap deep navigation to a specific assignment/class is a
  follow-up that needs a per-event route map on the device; rows always open
  the console, and the in-app inbox remains the source of truth.

---

## 6. Security & production hardening

- Tokens are stored per-user and never exposed cross-tenant; inbox endpoints
  always scope by `user.id` from the JWT, never by a client-supplied owner.
- FCM service-account secrets live only in server env (never `NEXT_PUBLIC_*`).
  The web app's public config is the standard non-secret Firebase web config.
- The outbox worker is idempotent and retry-safe; dead tokens are
  deactivated after FCM reports them invalid.
- Best-effort producer calls are logged and never break the primary write.
- Rate/route security follows the existing router conventions (tenant guard +
  slowapi limits where the repo applies them).

---

## 7. Testing

- `backend/tests/test_notifications.py` — 18 tests: inbox paging/unread
  filtering, mark read/all, token register/unregister, duplicate/unregister
  semantics, envelope shapes, worker status transitions. **18 passed.**
- Console suites around the producers (online-class, parent, teacher, student +
  notifications): **119 passed**.
- exam-controller/principal/hod/coordinator suites: 115 passed, 4 failed —
  the same 4 failures reproduce on an unmodified `HEAD` worktree and predate
  this work (`test_principal_can_publish_an_institution_notice_with_audit_row`,
  `test_create_slot_rejects_duplicate_unique_key`,
  `test_create_slot_succeeds_with_audit_trail`,
  `test_update_slot_records_old_and_new_state`).
- Website: `tsc --noEmit` clean; `next build` clean (all role
  `/notifications` pages compile; `/firebase-messaging-sw.js` is dynamic).
- Mobile: `tsc --noEmit` clean.

---

## 8. What still needs real-world credentials to go live

The code is complete and degrades gracefully, but push cannot be exercised
end-to-end until real values exist:

| Where | What | Status |
|---|---|---|
| `fontend/.env.example` | `NEXT_PUBLIC_FIREBASE_*` (web app config + VAPID key) | placeholders |
| `backend/.env.example` | `FCM_PROJECT_ID`, `FCM_SERVICE_ACCOUNT_JSON` | placeholders |
| Firebase console | web app + Android/iOS apps in one project | not created |
| `app/` | `google-services.json`, `GoogleService-Info.plist`, `android.package` / `ios.bundleIdentifier` in `app.json` | to be added at build time |

Until then: in-app notifications, bells, badges, inbox pages and the
device-token registry all work against the live API; web/mobile push quietly
stays hidden/off and starts working the moment the credentials are supplied.
