# Pre-Launch Issues & Fixes — Website + Mobile App + Backend

**Purpose:** Everything found in an end-to-end scan of the repo that must be fixed
before the product goes live (ads running, public signups open, real schools onboarded).
Severity: **P0 = blocker (legal/security/money/data-loss)** · **P1 = launch-blocking for
the advertised promise** · **P2 = polish/credibility**.

---

## A. P0 — Security & Credential Leaks (fix TODAY, before anything else)

### A1. Real production secrets are committed to Git ❗
- `backend/.env` is **tracked in git** (despite `.gitignore` listing `.env*`) and contains:
  - A real-looking production `JWT_SECRET_KEY`
  - A **live Gmail App Password** (`GOOGLE_SMTP_PASSWORD=znva gebb …`) with a real inbox
- `backend/.env.example` also contains a **real Gmail app password** (`wjsb cwjq …`).
- `backend/scripts/password.md` stores plaintext credentials (emails + passwords + the
  app password) and is committed.
- `backend/scripts/seed_data.py` hardcodes default platform passwords
  (`adminpassword123`, `supportpassword123`, `salespassword123`, `financepassword123`)
  and `DEVELOPER-TEST-GUIDE.md` publishes them.
- `MANUAL.md` contains DB credentials in setup commands (acceptable as *example*, but
  review).

**Why it's critical:** anyone with repo access (or anyone the repo is ever shared with)
can forge JWTs for **every tenant**, read all email, and log in as Super Admin. Git
history retains the secrets even after deletion.

**Fix:**
1. **Rotate every leaked secret immediately**: revoke the Gmail App Password in the
   Google account, generate a new one; regenerate JWT secret (`python -c
   "import secrets;print(secrets.token_hex(64))"`); reset the seeded admin passwords.
2. `git rm --cached backend/.env` and confirm `.env*` ignore is effective; move real
   values to deployment-environment secrets (host secret manager / env vars), never files.
3. Replace `backend/.env.example` values with placeholders only.
4. Delete `backend/scripts/password.md` (or move to a private password manager).
5. Make seed users get random passwords printed once, or forced-reset on first login;
   never ship default platform-admin passwords.
6. Scrub git history (filter-repo/BFG) or accept that old secrets are burned — rotation
   in step 1 is what actually protects you.

### A2. No payment gateway — billing is a mock
`SignupService.mark_paid()` writes `gateway="mock"` and self-marks orders PAID. There is
**no Razorpay/Stripe/Cashfree integration**, no webhook signature verification, and
**student fees are read-only** (no online fee payment endpoint at all — receipts assume
CASH/offline). Running ads → collecting money is impossible today.

**Fix:** integrate a gateway (Razorpay/Cashfree for India) with: order creation,
redirect/checkout, a **signed webhook handler** as the only source of truth for payment
state, GST-compliant invoicing (the landing page already promises "GST invoicing"), and
an online fee-payment flow for parents/students with PDF receipts.
Note: the canonical schema (`database.sql`) already defines
`CONSTRAINT uq_platform_payments_gateway_ref UNIQUE (gateway, gateway_ref)` as a replay
guard, but the ORM model `PlatformPayment` in `models/billing.py` does **not** declare
it — one more ORM-vs-SQL drift to reconcile (see C2).

### A3. No legal/compliance pages for an ad-driven launch
There is **no Privacy Policy, Terms of Service, Refund/Cancellation policy, or Contact
identity page** (`fontend/app` has no privacy/terms routes). The site collects emails,
passwords and children's data (minors — strict under India DPDP Act / GDPR-K). Running
paid ads **and** processing signups without these is a compliance and ad-platform
violation (Google/Meta ads require a working privacy policy URL).

**Fix:** publish `/privacy`, `/terms`, `/refund-policy`, a real `Contact` with legal
entity name, and DPDP-aligned consent language (data of minors, data retention,
deletion). Add a cookie/consent banner if analytics is added.

### A4. Marketing site is `noindex` on every page
`fontend/app/layout.tsx` sets `robots: { index: false, follow: false }` globally. The
public site (landing, features, pricing) will **never appear in Google search**, and
there is no `sitemap.xml` / `robots.txt`. Ad traffic landing page SEO quality score
suffers too.

**Fix:** set robots to index for the public marketing routes (noindex only the
authenticated console), add `app/robots.ts` + `app/sitemap.ts`, and per-page metadata.

### A5. Brand/identity placeholder still ships everywhere
The product is literally named **"xyz.com"** throughout — titles, footer, emails
(`EMAIL_FROM_NAME="xyz.com ERP"`), favicon/meta, demo data, CTA links. Ads cannot point
at a credible destination until the real brand name, domain, logo, support email and
social links replace it. Also `PUBLIC_ROOT_DOMAIN=localhost:3000` in the committed
`.env` while `ALLOWED_ORIGINS` lists `https://xyz.com` — inconsistent production config.

**Fix:** global brand pass (search `xyz.com` across repo), real domain in env, real
transactional email domain with SPF/DKIM/DMARC (Gmail SMTP with a personal inbox will
hit deliverability limits/suspension at scale).

---

## B. P1 — Functional defects (the bugs your team already reported + more)

### B1. Assignment close → reopen → resubmission edge case (reported bug)
**Correction after re-verification — the resubmission feature IS built and works.** I
initially reported it missing; the code shows a complete flow:
- Teacher reopen endpoint works: `POST /teacher/assignments/{id}/reopen`
  (DRAFT→PUBLISHED→CLOSED→PUBLISHED), with the Reopen button in both web and mobile.
- A **"Request changes / resubmit"** teacher action exists: review decisions are
  `APPROVED` / `REJECTED` / `CHANGES_REQUESTED`, and `CHANGES_REQUESTED` maps to
  `SubmissionStatus.RESUBMIT_REQUESTED` (`teacher_service.py`, decision_map ~line 3590).
- The student **resubmit path exists end-to-end**: `_SUBMITTABLE_STATUSES =
  (RESUBMIT_REQUESTED, REJECTED)` gates `submit_assignment` (which versions each
  submission, blocks resubmit only when APPROVED/REJECTED), and both the web
  (`student-assignments.tsx`, "Resubmit work"/"Resubmit" CTAs + `SubmissionsHistory`)
  and mobile app show the resubmit UI.

**The real, narrower gap** matching the report ("teacher closed, then can't reopen /
student can't resubmit after submission but teacher didn't approve"):
1. When a teacher **closes then reopens** an assignment, `transition_assignment` only
   flips the *assignment* status back to PUBLISHED — it does **not** reset any student
   *submission* already in `SUBMITTED` / `UNDER_REVIEW`. Such assignments are filtered
   out of the student's "pending" list (`_pending_assignments` excludes anything with a
   SUBMITTED/UNDER_REVIEW/APPROVED submission), so a student who submitted but was never
   graded doesn't get the assignment back as actionable and the "Resubmit" entry only
   appears once a reviewer explicitly marks CHANGES_REQUESTED.
2. Reopen should likely also re-open (or bulk-nudge) un-reviewed submissions so students
   the teacher never got to can revise.

**Fix (verify on a running system first, then):** on reopen, either (a) leave a clear
"Resubmission allowed" state and surface already-submitted-but-not-approved assignments
back in the student's list with a Resubmit CTA, or (b) have reopen offer to mark
un-reviewed submissions `RESUBMIT_REQUESTED`; add a web + mobile test for the exact
close→reopen→resubmit sequence. The core statuses and endpoints already exist — this is
a workflow/UX wiring fix, not a missing feature.

### B2. Teacher question review shows "only squares" (reported bug)
**Verified question types** are MCQ, TRUE_FALSE, SHORT_ANSWER, LONG_ANSWER, FILL_BLANK
and MATCH (`QuestionType` enum in `models/lms.py`; there is no "IMAGE" question type —
`IMAGE` exists only as a content-material kind). Objective questions (MCQ / TRUE_FALSE)
are auto-graded and shown only as an auto-graded summary; the manual grading panel
(`components/teacher/teacher-exam-results.tsx`) renders, per answer, the
**question text** and the student's answer (`text_answer` or `selected_option_text`) —
it does **not** render the full set of answer **options** or the correct answer/key for
context. (The question-authoring screen, `teacher-exam-questions.tsx`, does list
options correctly.)

**Likely cause of "only squares":** with the option/correct-answer context missing, the
reviewer sees question text plus sparse markers instead of a readable answer key — and
depending on the data the student selected, `selected_option_text` may be blank
("(no answer written)"). The exact visual symptom should be reproduced at runtime; it is
a UI/context gap in the grading view, not missing data.

**Fix:** reproduce a grading pass with each of the 6 question types; in the grading
panel render the complete option list (with the correct option and the student's choice
clearly marked), the correct-answer key for auto-graded items, and any special
characters/math in a glyph-safe way; confirm `selected_option_text` is populated for
MCQ/TRUE_FALSE/MATCH/FILL_BLANK answers.

### B3. Student result UI issues (reported bug)
`StudentExamResultPage` / grade-card rendering states need an audit: loading/empty/
error states, "result not yet published" vs "attempted" vs graded, and grade-card
export (`html2canvas`) correctness.

**Fix:** define and test all result states; show "results under evaluation" instead of
blank/error; verify grade-card PDF/image export and marks breakdown on web and mobile.

### B4. Live class audio/video works on web only, with no TURN/SFU and no mobile A/V
**Correction after re-verification:** the web classroom **does** implement real
audio/video — `hooks/use-live-room.ts` builds a peer-to-peer WebRTC mesh
(`RTCPeerConnection` per peer, `getUserMedia` for camera/mic, `getDisplayMedia` for
screen share, SDP/ICE signalling relayed over the WebSocket), and records locally with
`MediaRecorder`. So it is *not* chat-only. The real production gaps are:
- **No TURN server** — `RTC_CONFIG` uses only `stun:stun.l.google.com:19302`. P2P mesh
  fails across many NAT/firewall setups (most school/corporate networks) without TURN.
- **Mesh topology does not scale** — each client sends a stream to every other client;
  at room sizes above a handful it saturates uplinks/CPU. There is no SFU.
- **Signalling shares the un-finished multi-worker path** — the WebSocket that carries
  SDP/ICE relay is the same channel whose Redis fan-out is not connected (see B5), so
  peers on different Uvicorn workers cannot establish a connection.
- **Mobile has no WebRTC** — the app explicitly documents "React Native has no WebRTC
  in this build" (`app/src/lib/online-class.ts`); the app does chat/whiteboard/presence/
  materials/attendance only. On iOS/Android (where most students/parents actually are),
  live A/V is unavailable.
- Recordings are captured teacher-side in the browser and uploaded as files — not
  reliable for long/backgrounded sessions.

**Fix before advertising "live classes" to schools:** add a TURN server (coturn) at
minimum; for classes beyond ~6–8 participants use an SFU (self-hosted mediasoup/LiveKit
or Agora/EnableX white-label) which also gives server-side recording; route media
signalling through a transport that works across workers; and add a React Native
WebRTC path (or a documented "join A/V in browser") for the mobile app.

### B5. Redis pub/sub for multi-worker live classes is not connected
`LiveRoomManager._redis` is always `None`; broadcasts only reach sockets on the **same
worker**. With >1 Uvicorn worker (the production sizing assumes 8–60 workers), a
teacher and student can land on different workers and never see each other's
chat/whiteboard. Also APScheduler runs inside every worker → duplicate class
auto-starts/reminders.

**Fix:** finish the Redis pub/sub fan-out (or move live sockets to a single pinned
service / the media provider), and run scheduler jobs as a singleton (leader lock in
Redis or a separate worker process).

### B6. Uploads are local-disk only with weak production guarantees
Files land in `backend/uploads/` served by StaticFiles. This (a) doesn't survive
container redeploys / multi-instance setups, (b) has no signed-URL access control —
`/uploads` is mounted **publicly**, so anyone with a file URL can view student
submissions/documents, (c) no antivirus/content scanning beyond MIME allowlist.

**Fix:** move to S3/object storage with private buckets + short-lived signed URLs,
per-tenant path prefixes, and validate magic bytes not just MIME strings.

### B7. Mobile app cannot reach a real backend
`EXPO_PUBLIC_API_URL` defaults to `http://localhost:8000`, which on a physical phone is
the phone itself. No production API env, no Android network-security config for cleartext,
and the app is not configured for store builds (no app icons/store listing work shown).

**Fix:** add production/staging env builds, HTTPS API, eas build profiles, and store
assets before any app-related promotion.

---

## C. P1 — Operations & Production Readiness

| # | Issue | Fix |
|---|---|---|
| C1 | **No Dockerfile, no docker-compose, no CI/CD, no deploy scripts** in repo | ✅ **FIXED**: Multi-stage Dockerfiles (backend & frontend), docker-compose (dev & prod), GitHub Actions CI/CD workflows, and deploy/backup scripts created. |
| C2 | **Two schema sources** (`database/database.sql` + 14 SQL migrations vs Alembic 7 revisions with "drift" patches) | Make Alembic the single source of truth; baseline against production; add a CI drift check (`alembic check`) |
| C3 | **README quickstart is wrong**: references `python run.py` which doesn't exist | Use `uvicorn app.main:app`; fix docs |
| C4 | **No error monitoring / structured log aggregation** (no Sentry/Logtail/Datadog) | Add Sentry (backend + web), ship RequestID-correlated logs |
| C5 | **No backups / DR / PITR strategy** documented; school data is irreplaceable | Configure automated Postgres backups + restore drills, encryption at rest |
| C6 | `echo=settings.APP_DEBUG` logs **all SQL** in debug; verify env in prod is debug=false and pool sizing via PgBouncer | Production env audit; PgBouncer for the pool math in the capacity report |
| C7 | Deprecated FastAPI `@app.on_event("startup"/"shutdown")` | Migrate to `lifespan` handler |
| C8 | Forgot-password mail path has a `TODO` (outbox event with raw token not enqueued in `auth_service.py:480`) | Verify reset emails actually send in production; complete outbox wiring |
| C9 | FCM push is a stub (`FCM_SERVER_KEY` slot but no firebase-admin SDK; `device_tokens` table exists) | Either wire firebase-admin or remove push claims from marketing |
| C10 | Tenant login brute-force defence is only 10 req/min per **IP**; no per-account lockout for tenant users (owner routes have limits; verify account lockout) | Add per-account failed-attempt lockout + CAPTCHA after N failures |
| C11 | Refresh token in **localStorage** (XSS-exfiltratable) on web | ✅ **FIXED**: Switched to secure `httpOnly` cookies (`SameSite=Lax`, `Secure` in prod, `path=/`) with in-memory access tokens and graceful fallback. |
| C12 | No security headers documented (CSP, HSTS, X-Frame-Options) at the app/proxy layer | ✅ **FIXED**: Added CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy & Permissions-Policy at Next.js, FastAPI, and Nginx proxy layers; documented in DEPLOYMENT.md. |

| C13 | Tests are heavily mocked in part and there's no CI gate; no load test for the exam-burst scenario the capacity report promises | Add CI gate + k6/Locust load test for attendance/exam bursts |
| C14 | Duplicate superadmin scripts (`manage_superadmin.py` at root and in `scripts/`) | Consolidate |
| C15 | Email deliverability via a personal Gmail (500/day cap, spam risk) for transactional mail to schools/parents | Use a transactional provider (SES/Postmark/Resend) with subdomain + DKIM |

---

## D. P2 — Website / Ad-Readiness & Credibility

1. **No analytics or ad conversion tracking** — no GA4, Meta Pixel, LinkedIn tag, or
   UTM handling. You cannot measure ad ROI or build remarketing audiences. Add GA4 +
   Meta/Google Ads conversion tracking on signup/trial-start, with consent banner.
2. **Testimonials are placeholders** (`TESTIMONIALS` in `landing-page.tsx`) — fake
   quotes/names/orgs are illegal in ads (misleading endorsement) and erode trust on
   inspection. Replace with real pilot-school testimonials or remove before launch.
3. **"99.95% uptime" and "GST invoicing" are claimed on the landing page** but not
   delivered (no uptime monitoring/SLO; billing is mocked). Align claims with reality or
   ship the features.
4. **No WhatsApp/chat support, no demo booking calendar backend** visible — the
   funnel is Features → Pricing → Book Demo; verify the service-request form
   (`service_requests`) notifies sales and has an SLA.
5. **No OG/social share images, favicon branding, or per-page metadata** beyond
   defaults — ad click-through quality depends on share previews.
6. **English-only UI** for an India-first school market — no Hindi/regional language;
   parents in tier-2/3 cities need at least Hindi (consider i18n in a later phase, but
   note it for ad targeting).
7. **No SMS/OTP channel** — many Indian schools rely on phone; phone login/OTP
   (MSG91/Twilio) is a strong conversion lever and expected by parents.
8. **Accessibility/responsive pass** on marketing + key console flows before traffic.
9. **404/not-found** exists; verify authenticated route guards redirect cleanly and
   subdomain-less deep links resolve.
10. **Performance**: run Lighthouse on landing/pricing; the web bundle includes xlsx +
    html2canvas — ensure they're code-split out of marketing pages.

---

## E. Suggested Go-Live Sequence

1. **Week 0 (blockers):** Rotate/remove all leaked secrets (A1); legal pages (A3);
   turn on indexing + real brand/domain (A4/A5); payment gateway + fee payments (A2).
2. **Week 1:** Verify and fix the three reported bugs (B1–B3 — reproduce on a running
   system first) end-to-end on web **and** mobile; harden live class for production
   (TURN/SFU + mobile A/V, B4); Redis fan-out + singleton scheduler (B5); object storage
   + signed URLs (B6).
3. **Week 2:** Dockerize + CI/CD + backups + monitoring (C1–C5); Alembic single source
   (C2); email provider switch (C15); push decision (C9).
4. **Week 3:** Pilot with 2–3 real schools (free), collect real testimonials, load-test
   exam bursts, then switch ads on with analytics + conversion tracking (D1–D3).

**Do not spend on ads until A1–A5 and B1–B3 are done:** traffic to a noindex,
placeholder-branded site with mock payments and leaked credentials cannot convert and
creates legal exposure.
