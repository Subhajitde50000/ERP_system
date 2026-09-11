# shikshasync.me ERP + LMS — Full Technical Details & System Design

**Document type:** End-to-end engineering reference (codebase-scanned, September 2026)
**Repository:** `Subhajitde5000/ERP_system` — branch `arena/01a06338-erp-system`
**Audience:** Developers, DevOps, architects, technical reviewers, security auditors

---

## 1. What This Product Is

shikshasync.me is a **multi-tenant SaaS ERP + LMS for schools, colleges and universities**.
One *platform owner* account (the customer / institution proprietor, AWS-Shopify-Zoho
account model) can own **many institutions**, and each institution is an isolated
**tenant** provisioned on its own subdomain (e.g. `green.shikshasync.me`). Every tenant gets
the same 16-module product, its own staff/students/parents, its own data partition,
and its own subscription state (trial → paid).

The platform ships **three client surfaces** against **one backend API**:

| Surface | Folder | Stack | Purpose |
|---|---|---|---|
| Web admin/console + marketing site | `fontend/` | Next.js 16 (React 19, TypeScript, Tailwind 3) | Marketing pages, pricing/signup, and the full web console for **all 18 roles** |
| Mobile app | `app/` | Expo SDK 57 / React Native 0.86 (React 19, expo-router) | Student / Teacher / Parent on-the-go app (75 screens) |
| Backend API | `backend/` | FastAPI 0.115 · Python 3.11+ · SQLAlchemy 2 async · PostgreSQL · Redis | All business logic, auth, multi-tenancy, live classes, email, billing |

**Measured size of the codebase:**

| Area | Count |
|---|---|
| Backend Python (app code) | ~48,900 LOC |
| Web frontend (TS/TSX) | ~80,600 LOC, 188 pages |
| Mobile app (TS/TSX) | ~28,600 LOC, 75 screens |
| REST/WebSocket endpoints | **414** |
| Database tables | **132** (canonical `database/database.sql`) |
| Pytest test functions | **289** across 27 test files |
| Roles | **22** (4 platform + 18 institution) |
| Product modules | **16** (8 core free + 8 paid add-ons) |

---

## 2. Technology Stack (Exact Versions in Use)

### 2.1 Backend (`backend/requirements.txt`)

| Layer | Technology | Version |
|---|---|---|
| Web framework | FastAPI | 0.115.5 |
| ASGI server | Uvicorn[standard] | 0.32.1 |
| ORM | SQLAlchemy[asyncio] 2.x (Mapped/mapped_column style) | 2.0.36 |
| DB driver | asyncpg | 0.30.0 |
| Migrations | Alembic | 1.14.0 |
| Validation/settings | Pydantic 2 + pydantic-settings | 2.10.3 / 2.6.1 |
| Auth tokens | python-jose (JWT, HS256) | 3.3.0 |
| Password hashing | passlib[bcrypt] + bcrypt (cost factor 12) | 1.7.4 / 4.2.1 |
| Rate limiting | slowapi (IP-keyed) | 0.1.9 |
| Cache / pub-sub | redis[hiredis] | 5.2.1 |
| Mail (SMTP) | aiosmtplib | 3.0.2 |
| Mail (HTTP API) | httpx (Klaviyo Events API) | 0.28.1 |
| Background jobs | APScheduler (AsyncIOScheduler) | 3.11.0 |
| Forms/multipart | python-multipart | 0.0.12 |
| Tests | pytest, pytest-asyncio, pgserver (embedded Postgres) | 8.3.4 / 0.24.0 / 0.1.4 |

### 2.2 Web frontend (`fontend/package.json`)

- **Next.js 16.2** App Router, **React 19.2**, TypeScript 5, Tailwind CSS 3.4
- `lucide-react` icons, `xlsx` (Excel import/export), `html2canvas` (grade-card/image export)
- Playwright 1.62 (dev dependency, used by `scripts/link-check`)
- **No global state library** — data fetching is done through per-domain client modules in
  `fontend/lib/` (~40 API modules) with small hooks in `fontend/hooks/`
- Fonts are local/system stacks (no Google Fonts dependency at build or runtime)

### 2.3 Mobile app (`app/package.json`)

- **Expo SDK 57**, React Native 0.86, React 19.2, expo-router (file-based routing)
- `expo-secure-store` for token storage, `expo-web-browser`, `expo-image`,
  `react-native-reanimated` 4 + `react-native-gesture-handler`, `react-native-svg`,
  `@expo/ui`, `expo-glass-effect`
- Shares the same API envelope/types design as the web client (ported `api-client`)
- Route groups: `(student)`, `(teacher)`, `(parent)` plus shared auth screens

### 2.4 Data & infrastructure

- **PostgreSQL 16** — single source of truth (132 tables), UUID primary keys everywhere
- **Redis 7** — sessions/cache target + designed pub/sub channel for multi-worker live classes
- Local disk `backend/uploads/` mounted as `/uploads` static files (assignments, content,
  class materials/recordings) — object storage (S3) is the intended production replacement
- Email: pluggable provider registry — **Google SMTP** (Gmail/Workspace app password),
  **Klaviyo** Events API (flow-triggered), or **console** (dev/test, logs only)
- Push: FCM v1 hook exists (`PushService`, `FCM_SERVER_KEY`) with in-app DB inbox fallback;
  the firebase SDK itself is not yet wired

---

## 3. High-Level System Architecture

```
                         ┌──────────────────────────────────────────────┐
                         │            Browser / Mobile Users            │
                         │  Next.js web (188 pages)  ·  Expo RN app     │
                         └───────────────┬──────────────────────────────┘
                                         │ HTTPS  (Bearer JWT)
                              ┌──────────▼───────────┐
                              │  FastAPI (Uvicorn)   │  /api/v1/*
                              │  21 routers · 414    │  WebSocket /{class}/live
                              │  endpoints           │
                              └──┬───────┬───────┬───┘
            ┌────────────────────┘       │       └──────────────────┐
            │                            │                          │
   ┌────────▼────────┐         ┌─────────▼─────────┐      ┌─────────▼─────────┐
   │  PostgreSQL 16  │         │   Redis 7         │      │  Local /uploads   │
   │  132 tables     │         │ cache · pub/sub   │      │  (→ S3 in prod)   │
   │  row-per-tenant │         │ (live class fan-  │      └───────────────────┘
   └─────────────────┘         │  out design)      │
                               └───────────────────┘
            ┌───────────────────────────┐
            │ APScheduler (in-process)  │  auto-start classes · reminders ·
            │                           │  outbox email drain · retention
            └───────────────────────────┘
            ┌───────────────────────────┐
            │ Mailer registry           │  Google SMTP | Klaviyo API | console
            │ outbox_emails table       │
            └───────────────────────────┘
```

### 3.1 Request lifecycle

1. **Middleware stack** (`backend/app/main.py`), in order:
   `RequestIDMiddleware` (correlation ID on every log line) → `CORSMiddleware`
   (explicit origin list **plus** a subdomain regex for `*.shikshasync.me` / localhost) →
   route handling → slowapi rate limiter → global exception handler.
2. **Auth dependency** (`app/dependencies/auth.py`) decodes the JWT, then
   **re-checks the role live from the database** (`role_assignments` joined to `roles`,
   honouring `is_active` and `expires_at`) — a revoked or expired role is denied even
   with a still-valid token. Roles are never trusted from JWT claims.
3. **Tenant scoping**: every tenant query filters on `tenant_id`; the tenant is resolved
   from the institution `slug` (subdomain) supplied at login and carried in the
   `tenant_id` JWT claim, then re-checked against the loaded row.
4. **Session/transaction**: `get_db()` yields an async session — commit on clean exit,
   rollback on exception, always close. Engine: `pool_pre_ping=True`, pool 10 + overflow 20.
5. **Response envelope**: every endpoint returns `{ success: bool, data: T, message: str }`
   (`app/schemas/common.py`); the web/mobile clients unwrap this and convert
   snake_case → camelCase centrally.

### 3.2 The three separate login systems (token-typed JWT)

All tokens are HS256 JWTs signed with one secret but distinguished by a `type` claim,
and each auth dependency **rejects the other types**:

| Token `type` | Identity table | Login surface | Console |
|---|---|---|---|
| `platform` | `platform_users` | `/platform/login` | Super Admin, Support, Sales, Finance |
| `owner` | `platform_owners` | `/account/login` | Customer account: owns institutions, billing, invoices, trials |
| `tenant` | `users` (tenant-scoped) | `{slug}.shikshasync.me/login` | 18 institution roles |

- Access token: **15 minutes**; refresh token: **7 days**.
- Refresh tokens are random (`secrets.token_urlsafe(64)`), stored only as **SHA-256
  hashes** in `user_sessions` / `platform_sessions` / `owner_sessions`; logout revokes the row.
- Web: access token in memory only, refresh token in `localStorage`; silent refresh on
  load with a **single-flight refresh guard** (`createRefreshGuard`) to prevent
  thundering-herd refreshes. Mobile: `expo-secure-store`.
- Login is **constant-time** (bcrypt-verify against a dummy hash when the user doesn't
  exist) and rate-limited (e.g. tenant login 10/min, forgot-password 5/hour).

### 3.3 Multi-tenancy model

- **Shared database, shared schema, row-level tenant discrimination** — every business
  table carries `tenant_id`; `users` has a partial unique index on `(tenant_id, email)`
  and `(tenant_id, student_roll_no)` so the same email can exist in two institutions.
- Tenants (`tenants` table): slug (subdomain), type SCHOOL/COLLEGE, plan, owner FK,
  timezone (default `Asia/Kolkata`), trial end date, active flag.
- Module entitlement: `tenant_modules` vs the `modules` catalogue; the 8 core modules
  are always on, the 8 optional modules are subscription-gated.
- Platform staff (Support) can read across tenants to resolve tickets; all such access
  is written to `audit_logs`.

---

## 4. Backend Architecture (Layered)

```
backend/app/
├── main.py                 # FastAPI app, CORS, rate limiter, middleware, router mounts
├── config.py               # pydantic-settings, env-validated singleton
├── database.py             # async engine, session factory, DeclarativeBase
├── middleware/             # RequestID correlation middleware
├── dependencies/auth.py    # platform / owner / tenant + per-role guards
├── routers/                # HTTP/WebSocket layer (thin) — 21 routers
│   ├── platform/           #   platform admin, auth, support
│   ├── owner/              #   owner auth, billing, dashboard, tickets, profile
│   ├── tenant/ + public/   #   tenant login, public signup
│   ├── institution/        #   setup wizard, structure, people, config, links
│   └── principal, vice_principal, hod, coordinator, exam_controller,
│       teacher, student, parent, library, hostel, online_class, email …
├── services/               # Business logic (fat service layer) — 30+ services
│   ├── auth_service.py            # login/refresh/lockout/reset flows
│   ├── signup_service.py          # 7-step order→payment→provision pipeline
│   ├── institution_service.py     # tenant setup, staff invites (outbox email)
│   ├── teacher/student/parent…    # per-role domain services
│   ├── online_class_service.py    # live rooms, WS lifecycle, auto-attendance
│   ├── audit_service.py           # audit_logs writer
│   ├── push_service.py            # in-app inbox + optional FCM
│   ├── scheduler_service.py       # APScheduler jobs
│   ├── department_scope_service.py# HOD/VP data-scoping rules
│   └── mailer/                     # base, registry, service, templates,
│                                   # providers/{console,google,klaviyo}
├── models/                 # SQLAlchemy ORM — 30 model modules, mirror database.sql
├── schemas/                # Pydantic request/response models
├── utils/security.py       # bcrypt(12), secure tokens, SHA-256 token hashing
└── alembic/                # 7 migrations (initial + online class, question bank…)
```

**Key architectural patterns**

- **Thin routers, fat services** — routers validate input and call a static service
  method; services own transactions, invariants, audit writes and notifications.
- **Fail-closed authorization** — every privileged route depends on a role guard that
  resolves live role assignments; the Vice-Principal guard intentionally *never*
  satisfies Principal-only approval endpoints.
- **Outbox email pattern** — transactional emails (staff invites, password resets,
  parent claim codes) are written to `outbox_emails` inside the same DB transaction as
  the business change, then drained by the scheduler/mailer — no "DB committed but
  email lost" or "email sent but DB rolled back" states.
- **Audit by default** — `AuditService.record()` logs actor, role, action, entity,
  tenant, before/after values. `audit_logs.user_id` deliberately has no FK so it can
  reference any of the three identity tables.
- **Pluggable mailer** — provider chosen by `EMAIL_PROVIDER`; tests force `console` so
  the suite never sends real mail.

---

## 5. Data Model (132 tables, by domain)

| Domain | Representative tables |
|---|---|
| Platform / tenancy | `platform_owners`, `platform_users`, `platform_sessions`, `platform_settings`, `tenants`, `tenant_settings`, `tenant_modules`, `users`, `roles`, `permissions`, `role_assignments`, `user_sessions`, `audit_logs` |
| Catalog / billing | `modules`, `plans`, `coupons`, `orders`, `subscriptions`, `platform_invoices`, `platform_invoice_lines`, `platform_payments`, `service_requests`, `support_tickets`, `support_ticket_messages` |
| Academic structure | `academic_years`, `academic_events`, `departments`, `classes`, `subjects`, `teacher_subjects`, `student_enrollments`, `timetable_slots`, `timetable_substitutions`, `bulk_import_jobs` |
| LMS | `assignments`, `milestones`, `submissions`, `submission_files`, `submission_reviews`, `content_items`, `content_tags`, `content_access_logs`, `discussion_threads`, `discussion_replies`, `discussion_votes`, `notices`, `notice_attachments`, `notice_reads`, `project_groups*` (collaboration), `notifications` |
| Examinations | `exams`, `exam_sections`, `questions`, `question_options`, `question_bank_items`, `exam_attempts`, `answers`, `student_results`, `grade_cards`, `result_publications`, `exam_hall_allocations`, `malpractice_logs`, `exam_controller_publications`, `exam_controller_grade_cards` |
| Attendance / leave | `attendance_sessions`, `attendance_records`, `attendance_leaves`, `leave_requests`, `leave_policies` |
| Fees / finance | `fee_heads`, `fee_structures`, `fee_installments`, `student_fee_accounts`, `fee_payments`, `scholarships`, `scholarship_grants`, `payroll_runs`, `payslips`, `salary_structures` |
| Library | `books`, `book_copies`, `book_issues`, `e_resources` |
| Hostel | `hostel_blocks`, `hostel_rooms`, `hostel_allotments`, `hostel_attendance`, `hostel_leave_requests`, `hostel_complaints` |
| Transport | `transport_routes`, `transport_stops`, `vehicles`, `drivers`, `student_transport` |
| Placement / HR / admission / inventory | `placement_drives`, `companies`, `placement_applications`, `placement_offers`, `merit_lists`, `drive_eligibility`, `staff_profiles`, `staff_documents`, `appraisals`, `appraisal_cycles`, `mentor_assignments`, `mentor_notes`, `admission_cycles`, `admission_applications`, `application_documents`, `interview_rounds`, `inventory_categories`, `inventory_items`, `stock_transactions`, `vendors`, `purchase_orders`, `purchase_order_items` |
| Parents | `parent_student_links` (+ parent claim codes / slips), `device_tokens` |
| Live classes | `online_classes`, `online_class_participants`, `online_class_messages`, `online_class_files`, `online_class_muted_students` |

**Migration strategy note:** there are two schema sources — the canonical
`database/database.sql` (132 tables, plus ~14 incremental migration SQL files) and the
Alembic chain in `backend/app/alembic/versions/` (7 revisions, including explicit
`drift_check` / `schema_drift_fixes` revisions). The ORM models are written to mirror
`database.sql`.

---

## 6. Roles & Permissions (RBAC)

**22 roles** seeded by `scripts/seed_data.py`:

- **Platform (4):** SUPER_ADMIN, SUPPORT_STAFF, SALES_EXECUTIVE, FINANCE_MANAGER
- **Institution (18):** INSTITUTION_ADMIN, PRINCIPAL, VICE_PRINCIPAL, HOD,
  ACADEMIC_COORDINATOR, EXAM_CONTROLLER, TEACHER, STUDENT, PARENT/GUARDIAN,
  LIBRARIAN, HOSTEL_WARDEN, and supporting staff roles.

Permissions are materialized as **`module_key.ACTION.SCOPE`** strings (e.g.
`attendance.MARK.DEPARTMENT`) loaded from the `permissions` table per role, embedded in
the tenant JWT, **and re-validated live**. Scope levels: PLATFORM / INSTITUTION /
DEPARTMENT / CLASS / SELF. The `department_scope_service` enforces that HODs and
Vice-Principals only see their delegated departments/classes.

---

## 7. The 16 Product Modules

**8 core (included in every plan):** Attendance · Examination · Assignments ·
Notice Board · Discussion · Content (LMS) · Results · Timetable.

**8 paid add-ons (monthly à-la-carte prices in ₹):**

| Module | ₹/month | Module | ₹/month |
|---|---|---|---|
| Library | 1,500 | HR | 2,000 |
| Hostel | 2,000 | Admission | 1,500 |
| Transport | 1,500 | Inventory | 1,500 |
| Placement | 1,500 | Finance | 2,000 |

Plans: **Starter / Professional (₹7,999/mo advertised) / Enterprise**, 14-day free
trial, coupons (WELCOME10, LAUNCH500).

---

## 8. Key Subsystems

### 8.1 Signup → provisioning pipeline (`signup_service.py`)

A 7-step flow: public signup → create owner account → build an order (plan + modules,
trial or purchase) → **payment** (`mark_paid` — currently a **mock gateway** with a
single documented integration point and `UNIQUE(gateway, gateway_ref)` replay guard) →
`provision()` creates the tenant, admin user, roles, module entitlements and default
settings **in one transaction**, then hands off to the institution setup wizard.

### 8.2 Live online classes (`online_class_service.py` + WS endpoint)

- `GET /api/v1/.../online-classes/{class_id}/live?token=...` WebSocket (token in query
  because browsers can't set WS headers); the handshake verifies JWT type, tenant,
  enrolment/participant admission, and class state before `accept()`.
- In-memory `LiveRoomManager` tracks rooms → users → sockets per worker, with
  waiting room, mute controls, chat, whiteboard strokes (capped at 500), hand-raise,
  file sharing and presence. Frame size capped at 128 KB; room cap 500 per worker.
- **Audio/video (web):** the web client (`fontend/hooks/use-live-room.ts`) establishes
  a peer-to-peer **WebRTC mesh** — one `RTCPeerConnection` per peer, `getUserMedia`
  (camera/mic), `getDisplayMedia` (screen share), with SDP/ICE signalling relayed over
  the WebSocket. ICE config currently lists only Google's public STUN (no TURN/SFU).
  Recording is done teacher-side in the browser via `MediaRecorder` and uploaded.
  The **mobile app intentionally has no WebRTC** in this build (`app/src/lib/online-class.ts`
  documents this) — it carries chat, board, presence, materials and the attendance report.
- **Auto-attendance policy**: ≥75% of live duration = PRESENT, 30–74% = LATE,
  <30%/absent = ABSENT; on class end the report syncs into the canonical
  `attendance_sessions`/`attendance_records` tables so the whole ERP sees it.
- APScheduler auto-starts due classes and sends 10–15-minute reminders.
- Redis pub/sub is designed in (`_redis` hook, config present) but **not yet wired**, so
  cross-worker broadcasts and multi-worker signalling don't work yet (see pre-launch doc).

### 8.3 Examinations

Question bank with six question types (MCQ, SHORT_ANSWER, LONG_ANSWER, TRUE_FALSE,
FILL_BLANK, MATCH; difficulty EASY/MEDIUM/HARD), exam sections, timed attempts with
server-side autosave (`save_answer`), auto-grading of objective questions, manual
grading of subjective answers (with a `CHANGES_REQUESTED` → resubmission-style review
flow for assignments), result publication with grade cards, hall allocation,
malpractice logs, and an Exam Controller console (schedule, monitor, publish, reports).
Note: `IMAGE` is a *content-material* kind, not a question type.

### 8.4 Parent portal

Parents claim children via secure codes (printed-slip format `XXXX-XXXX-XXXX`,
delivered through the outbox mailer), then view attendance, fees, results, notices,
timetable, assignments and can apply for leave — for multiple children. Mobile app has
a full `(parent)` route group; web has `/parent/*`.

### 8.5 Email & notifications

Outbox table + provider registry (Google SMTP / Klaviyo / console), templated
transactional mail, in-app `notifications` inbox for every role, optional FCM push
(service-account key config slot present).

---

## 9. Frontend Architecture

### 9.1 Web (`fontend/`)

- **App Router** route groups: `(auth)` (login, platform login, reset/verify,
  guardian access), `(platform)` (platform staff + owner account consoles: dashboard,
  institutions, plans, billing, invoices, subscriptions, sales/trials, support tickets,
  audit logs, settings), and per-role areas: `admin/`, `principal/`, `vice-principal`,
  `hod/`, `coordinator/`, `exam-controller/`, `teacher/`, `student/`, `parent/`,
  `librarian/`, `hostel-warden/`, plus public marketing (`/`, `/features`, `/solutions`,
  `/pricing`, `/about`, `/contact`, `/faq`, `/security`, `/customers`, `/signup`).
- **API layer:** `lib/api-client.ts` (envelope unwrap, camelCase conversion, 422
  flattening, single-flight 401 refresh) + ~50 domain/helper modules in `lib/`
  (`lib/auth.ts`, `lib/teacher.ts`, …). Three auth domains share the transport but keep
  separate token slots/guards (tenant, platform, owner).
- Components are grouped per role under `components/<role>/` plus shared
  `components/ui`, `components/marketing`, `components/checkout`.
- Excel export/import via `xlsx`; grade cards rendered/exported via `html2canvas`.

### 9.2 Mobile (`app/`)

- expo-router file-based routing with `(student)` / `(teacher)` / `(parent)` groups;
  shared login/institution/forgot/guardian screens.
- Same envelope client, `expo-secure-store` token storage, `use-live-chat` hook for the
  live-class socket, live-class lib for WS messaging.

---

## 10. Cross-Cutting Concerns

| Concern | Implementation |
|---|---|
| Correlation IDs | `RequestIDMiddleware` on every request |
| Rate limiting | slowapi, IP-keyed (shared school NAT safe); limits on auth/signup/owner routes |
| Password security | bcrypt rounds=12; constant-time login; dummy-hash user enumeration defence |
| Token security | Short-lived access (15 min) + rotating refresh (7 days, hashed at rest, revocable) |
| Authorization | Live DB role checks on every request; fail-closed; scope-aware services |
| Tenant isolation | `tenant_id` on every row + per-request JWT tenant binding |
| Auditing | `audit_logs` for privileged actions with before/after |
| Email reliability | Transactional outbox + scheduler drain; provider abstraction |
| Error handling | Global JSON exception handler; stack traces only when `APP_DEBUG=true` |
| Docs | OpenAPI/Swagger at `/docs` only in debug; `/health` liveness endpoint |
| Tests | 289 pytest functions; embedded Postgres integration suites; mailer forced to console; rate limiters reset per test |

---

## 11. Local Development & Deployment Topology (as documented)

```bash
# 1. PostgreSQL
psql -U erp_user -d erp_db -f database/database.sql   # + incremental migration SQLs
# 2. Backend (.venv, pip install -r requirements.txt, .env, seed_data.py)
uvicorn app.main:app --reload                         # :8000
# 3. Web
cd fontend && npm ci && npm run dev                   # :3000
# 4. Mobile
cd app && npx expo start
```

Production target (per `doc/ARCHITECTURE.md` and the capacity report): Uvicorn/Gunicorn
workers behind a reverse proxy, managed PostgreSQL (RDS-style) with PgBouncer, Redis,
object storage for uploads, subdomain wildcard DNS (`*.shikshasync.me`) routing to the web
front, and the scheduler running as a singleton. The capacity analysis in
`SYSTEM_ANALYSIS_AND_PRODUCTION_REPORT.md` models tiers from a single 2-vCPU node
(~500 concurrent users) up to a Kubernetes multi-pod SaaS fleet (150k+ users).

---

## 12. Strengths of This Architecture (engineering summary)

1. **Genuine multi-tenancy with three hard-separated auth planes** — rare in this
   product category; owner/platform/tenant tokens cannot cross.
2. **Authorization is re-evaluated from the database per request**, not baked into
   tokens — instant revocation, role expiry, least-privilege by scope.
3. **Async end-to-end** (FastAPI + asyncpg + SQLAlchemy 2) for the attendance/exam
   burst workloads schools actually have.
4. **Transactional outbox email**, audit-everything, and fail-closed role guards show
   production-grade thinking.
5. **One API serving web + mobile with a strict shared envelope** — clients stay thin.
6. **Broad functional depth**: 16 modules, 22 roles, 132 tables, 414 endpoints —
   far beyond a typical MVP, covering the full school operating cycle.
7. **Real test culture**: 289 tests including embedded-Postgres integration suites.

The companion documents `PRE-LAUNCH-ISSUES-AND-FIXES.md` and
`MARKET-AND-BUSINESS-ANALYSIS.md` cover what must change before go-live and the
market/business positioning respectively.
