# xyz.com ERP + LMS — Student & Teacher app (React Native)

Mobile app for the **Student** and **Teacher** consoles of the xyz.com ERP + LMS.
It is a React Native (Expo + expo-router) port of those sides of the website in
`../fontend` — same screens, same design tokens, same API endpoints, so the
app UI matches the website UI one-to-one.

The website itself is unchanged. Other role apps (Hostel Warden, …) come later.

## Screens

### Shared

- **Login** — tenant login (institution code + email/roll number + password).
  Student accounts open the student console; teacher / mentor accounts open
  the teacher console. Accounts that hold both roles can switch from the
  drawer.

### Student (C-ST-01 … C-ST-20)

- **Dashboard** — attendance, upcoming exams, pending assignments, fee
  balance, today's periods, next exam, recent notices, quick links.
- **Profile** — student record; name / phone / photo are editable.
- **Attendance** — overall + per-subject summary, leave requests, monthly
  calendar, apply-for-leave form.
- **Timetable** — Monday–Saturday period grid with teachers and rooms.
- **Examinations** — list, instructions with countdown, timed attempt with
  autosave (backgrounding the app reports the anti-cheat tab-switch signal),
  result with answer review.
- **Assignments** — list, brief, milestone chain, group formation
  (create/join/reuse/leave), submit/resubmit with files, submission history
  with file preview.
- **Project Teams** — invitations, team metrics, and the team workspace
  (task board, team chat, shared links, roster, submission overview).
- **Content** — library with subject/chapter/type filters, inline viewer.
- **Results** — published results, subject-wise detail, grade card.
- **Notices** — notice board with unread marking.
- **Discussion** — question threads, composer, replies and upvotes.
- **Fees** — fee account, installments, scholarships, payment history and
  official receipts.

### Teacher (C-TC-01 … C-TC-22)

- **Dashboard** — today's periods, submissions to review, upcoming exams,
  pending leaves, notices, quick actions.
- **My schedule** — weekly teaching timetable for the teacher's subjects.
- **Mark attendance** — class/subject/date/period picker, P/A/L/E roster,
  all-present, save. Locked sessions stay read-only.
- **Attendance sessions** — filterable history, lock a session.
- **Leave requests** — approve or reject student leave for classes you teach.
- **Examinations** — list, create/edit draft, publish, question paper
  (MCQ / true-false / descriptive, import from the question bank), results
  and a dedicated grading screen that always shows the full question stem.
- **Question Bank** — list, add, edit, delete, CSV export and paste-import
  (website file-picker / print-to-PDF become share / paste on the phone).
- **Assignments** — list, create, publish / close / reopen, edit draft,
  milestone stages, group roster.
- **Project Teams** — group assignments, roster management, workspace
  (tasks, chat, links, members) and jump to the group submission.
- **Content** — library with hide/show/delete, upload a file key or link.
- **Notices** — board plus class-scoped composer.
- **Discussion** — threads, composer, replies, accept answer, pin / lock /
  delete.

## Get started

1. Install dependencies

   ```bash
   npm install
   ```

2. Point the app at the FastAPI backend (defaults to `http://localhost:8000`,
   the same default as the website). Create `.env.local` from the example:

   ```bash
   cp .env.example .env.local
   # then edit .env.local and set EXPO_PUBLIC_API_URL to your backend host
   ```

   On an Android emulator, `http://localhost:8000` works out of the box.
   On a physical device, use your machine's LAN IP: `http://192.168.x.x:8000`.

3. *(One-time, for EAS builds)* Link the app to your Expo account:

   ```bash
   npm install -g eas-cli
   eas login
   eas init   # fills extra.eas.projectId in app.json — commit the result
   ```

4. Start the app

   ```bash
   npx expo start
   ```

   Open it in Expo Go / a dev build, or press `w` for the web preview.

## Notes on mobile-specific adaptations

The app reuses the website's exact palette, typography sizes, radii, shadows,
labels and empty states (see `src/theme.ts`). Only where a browser feature
has no native counterpart is it adapted:

- `<select>` dropdowns become bottom-sheet pickers.
- Browser `confirm()` becomes native alert dialogs.
- `<input type="date">` / `datetime-local` become `YYYY-MM-DD` and
  `YYYY-MM-DDTHH:MM` text fields.
- Hover-only affordances (tooltips, hover reveals) are dropped, as on the
  website's own mobile view.
- Print/save-as-PDF and CSV import-export buttons are omitted — the document
  itself is rendered identically where it exists.
- Exam grading is a full screen (not a modal overlay) so every question is
  readable.

---

# Release pipeline (B7 — environment, EAS builds, store submission)

## Environment model

| Variable | Dev (Expo Go / dev client) | Release (EAS build) |
| --- | --- | --- |
| `EXPO_PUBLIC_API_URL` | `http://localhost:8000` (emulator) or `http://<LAN-IP>:8000` (device) | **HTTPS only** — injected by the build profile |
| `EXPO_PUBLIC_WEB_URL` | optional | web console base URL (enables the in-app "Join audio/video in browser" link) |

Two guardrails make a broken release impossible to ship silently
(`src/lib/auth.ts::resolveApiBaseUrl`):

* a **production** bundle without `EXPO_PUBLIC_API_URL` throws at startup
  with instructions instead of pointing at localhost;
* a **production** bundle pointed at `http://localhost/127.0.0.1/10.0.2.2`
  throws for the same reason.

Development builds are untouched — localhost stays the default there.
Cleartext HTTP is disabled in release Android builds and ATS is locked down
on iOS via `expo-build-properties` in `app.json`; dev builds keep OS defaults
so local servers work.

## Build profiles (`eas.json`)

```bash
# one-time
npm i -g eas-cli && eas login && eas init            # fills extra.eas.projectId

# development build (dev client + localhost API)
eas build --profile development --platform android

# internal testing build against staging/prod API
EXPO_PUBLIC_API_URL=https://api.staging.example.com \
eas build --profile preview --platform android

# store build — API URLs come from EAS secrets, never from the repo
eas secret:create --name EXPO_PUBLIC_API_URL   --value https://api.example.com
eas secret:create --name EXPO_PUBLIC_WEB_URL   --value https://erp.example.com
eas build --profile production --platform android
eas build --profile production --platform ios
eas submit --profile production --platform android   # then Play/App Store
```

`appVersionSource: remote` + `autoIncrement` keep `versionCode`/`buildNumber`
managed by EAS so store uploads never collide.

## Store submission checklist

1. **Identifiers** — `app.json` ships with `com.erpcampus.mobile`
   (`android.package` / `ios.bundleIdentifier`). These are permanent once
   published: replace with the institution's own reverse-domain id **before
   the first store submission**.
2. **Icons/splash** — already complete in `assets/images/` (1024 icon,
   Android adaptive set, monochrome, splash, favicon).
3. **Store assets** — `assets/store/feature-graphic.png` (1024×500) and
   `assets/store/icon-512.png` are generated deterministically:
   `python3 - <<'EOF'` snippet in `doc/bugfix-b6-b7.md` §B7 regenerates them.
4. **Screenshots** — required per store (phone + 7"/10" tablet for Play).
   Capture from the `preview` build; do not reuse marketing renders.
5. **Listings** — title ≤ 30 chars, short description ≤ 80, full description
   ≤ 4000; privacy policy URL is mandatory (data: names, email, attendance,
   grades — see backend privacy docs) and must reference FCM push usage.
6. **Backend** — the release API host must be HTTPS with a valid certificate
   (`NODE_ENV=production` builds reject cleartext URLs); CORS for the app is
   not needed (native), but the web console origin must be allowlisted.

## Tests

`npm test` — vitest; `npx tsc --noEmit` — types. The API-URL guard has its
own suite in `src/lib/auth.test.ts`.
