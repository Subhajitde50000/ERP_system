# MANUAL.md — shikshasync.me ERP Platform

End-to-end operations manual for the shikshasync.me multi-tenant ERP + LMS platform.
Read this before deploying. It covers architecture, setup, the three login
systems, the live admin features, the API, and the production checklist.

---

## 1. What this system is

A **multi-tenant SaaS ERP + LMS** for schools, colleges and universities, modelled
on AWS / Shopify / Zoho:

- **One platform account owns many institutions.** A customer (e.g. Rahul,
  `rahul@gmail.com`) signs up once and runs Green College, ABC School and XYZ
  Academy under a single account, with consolidated billing and support.
- **Each institution is an isolated tenant** with its own subdomain
  (`green.shikshasync.me`), data, roles and modules.
- **16 modules** — 8 core (always on) + 8 optional (plan-gated).

There are **three identity tables / three login systems**, each with its own JWT
type so a token from one is never accepted by another:

| Identity | Table | Logs in at | JWT type | Purpose |
|---|---|---|---|---|
| Platform **staff** | `platform_users` | `/platform/login` (`app.shikshasync.me`) | `platform` | Super Admin / Support / Sales / Finance run shikshasync.me |
| Platform **owner** (customer) | `platform_owners` | `/account/login` (`shikshasync.me/login`) | `owner` | Owns institutions, billing, subscriptions, support |
| Institution **members** | `users` | `/login` (`green.shikshasync.me/login`) | `tenant` | Daily ERP: students, teachers, admins, … |

---

## 2. Architecture

```
fontend/   Next.js 16 (App Router) + React 19 + Tailwind
backend/   FastAPI + SQLAlchemy 2 (async) + asyncpg + Alembic + bcrypt + JWT
database/  database.sql (106-table base schema) + update.sql + update2.sql (post-base changes)
doc/       architecture, system-flow, owner-accounts, page specs
```

- **Backend** is fully async, tenant-scoped, RBAC-guarded. All responses use the
  `{ success, data, message }` envelope.
- **Frontend** has three surfaces:
  - **Public marketing site** (`/`, `/features`, `/pricing`, …) — no auth.
  - **Owner console** (`/account/*`) — owner JWT, manages institutions/billing.
  - **Institution consoles** (`/admin/*` and `/principal/*` real authenticated
    surfaces; `(institution)/*` legacy module-preview pages — see §8).
- **Auth** stores the short-lived access token in memory only; the refresh token
  is in `localStorage` (tenant + owner) or memory (staff). Passwords are bcrypt
  cost-12; refresh tokens are SHA-256 hashed at rest.

---

## 3. Prerequisites

- Python **3.11+**, Node.js **20+**, npm
- **PostgreSQL 15+** (developed on 17)
- Redis (optional; reserved for caching/rate-limit backing)

---

## 4. First-time setup

### 4.1 Database

```bash
# 1. Create the DB and user
psql -U postgres -c "CREATE USER erp_user WITH PASSWORD 'erp_password';"
psql -U postgres -c "CREATE DATABASE erp_db OWNER erp_user;"

# 2. Base schema (106 tables + role/permission/module seeds)
psql -U erp_user -d erp_db -f database/database.sql

# 3. Post-base updates (owner accounts, academic links, support and Principal governance)
psql -U erp_user -d erp_db -f database/update.sql
psql -U erp_user -d erp_db -f database/update2.sql
```

> **Alembic-managed deployments** instead of raw SQL:
> ```bash
> cd backend && alembic upgrade head
> ```
> The migrations end at `e7f2a6c3b904` and include the Principal governance
> and HOD mentor/scope workflow. Apply the raw schema plus both update files for the documented
> production path, or use your validated Alembic baseline for a
> migrations-managed environment — never mix a raw-schema bootstrap and
> Alembic on the same database without stamping/validating its revision.

### 4.2 Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env       # then edit values (see §9 Production checklist)
python scripts/seed_data.py        # catalogue, plans, 22 roles, demo tenant + users
python run.py                     # dev server on :8000  (python run.py --prod for prod)
```

Seed also creates a demo institution (`abc-college`) with an INSTITUTION_ADMIN
so you can explore `/login` → `/admin` immediately. See `seed_data.py` for the
demo credentials.

Create platform **staff** (Super Admin etc.) separately:

```bash
python scripts/create_superadmin.py --email admin@shikshasync.me --password 'StrongPass!' --name "Super Admin"
```

### 4.3 Frontend

```bash
cd fontend
npm ci
cp .env.example .env.local      # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                     # http://localhost:3000
```

### 4.4 Smoke test

1. `GET http://localhost:8000/health` → `{"status":"healthy"}`.
2. Visit `http://localhost:3000` (marketing site) → **Start free** → create an
   owner account → verify email (dev returns the link on-screen) → `/account`.
3. From `/account` → **New institution** → checkout → institution provisioned.
4. Open the institution login (`/login` for the seeded `abc-college` tenant, or
   your new subdomain) as the admin → `/admin/dashboard`.

---

## 5. The three login systems

### 5.1 Owner (customer) — `shikshasync.me/login` → `/account/login`
- `POST /api/v1/owner/signup` → `POST /owner/verify-email` → `POST /owner/login`.
- Email **must** be verified before login is allowed.
- Owns institutions, billing, subscriptions, invoices, payments, support tickets,
  profile. See `doc/PLATFORM-OWNER-ACCOUNTS.md`.

### 5.2 Institution member — `green.shikshasync.me/login` → `/login`
- `POST /api/v1/tenant/auth/login` `{ slug, identifier, password }`.
- `identifier` is an **email or roll number**. JWT is bound to the tenant
  (`tenant_id`) and the origin — replaying it against another institution fails.
- Institution Admins land on the **real** admin console at `/admin/dashboard`.
- Principals land on the **real** academic-oversight console at `/principal/dashboard`.
- Vice Principals land on `/vp/dashboard`; an active delegated department scope is required.
- HODs land on `/hod/dashboard`; a department HOD assignment creates their scoped access automatically.

### 5.3 Staff (shikshasync.me employees) — `app.shikshasync.me/login` → `/platform/login`
- `POST /api/v1/platform/auth/login`. Created via `create_superadmin.py` or seed.

> On a single-origin dev deploy these are three **paths**; in production they are
> three **hosts** (rewrite `shikshasync.me/login`→`/account/login`,
> `app.shikshasync.me/login`→`/platform/login`, `*.shikshasync.me/login`→`/login`).

---

## 6. Institution Admin — what is LIVE (real backend, no demo data)

The `/admin/*` console is fully wired to the backend at `/api/v1/institution/*`.
All routes require a `type="tenant"` JWT whose user holds the
**INSTITUTION_ADMIN** role (RBAC is read live from `role_assignments`).

| Page | Backend | What works |
|---|---|---|
| `/admin/dashboard` | `GET /institution/dashboard` | Real counts (years, departments, classes, subjects, staff, students), enabled modules, onboarding state |
| `/admin/academic-years` | `/institution/academic-years` | Create / list / set-current / delete; exactly one current per tenant |
| `/admin/departments` | `/institution/departments` | Create / list / update (HOD) / delete (blocked if classes exist) |
| `/admin/staff` | `/institution/staff` | List, invite (set-password link emailed), assign roles |
| `/admin/modules` | `/institution/modules` | List + toggle; core locked, optional **plan-gated** (402 if not in plan) |
| `/admin/settings` | `/institution/settings` | Timezone / currency |
| `/admin/profile` | `/institution/profile` | View + edit institution details |

Plus backend-only (ready to wire): `/institution/classes`, `/subjects`,
`/students`, `/enrollments`, `/staff/{id}/roles`, `/staff/{id}/active`.

Staff/student invites use the **reset-token flow**: the new user is created with
no password and a one-time token; a "set your password" email is queued in
`outbox_emails`. The platform never knows anyone's password.

---

## 7. Principal — what is LIVE (real backend, no demo data)

The `/principal/*` console is wired to `/api/v1/principal/*` and accepts only a
current **PRINCIPAL** tenant-role assignment. The role is checked from
`role_assignments` on every request, so a revoked or expired assignment cannot
use an old JWT. The Vice Principal is intentionally excluded from this surface:
final schedule and result approval belong to the Principal.

| Page | Backend | What works |
|---|---|---|
| `/principal/dashboard` | `GET /principal/dashboard` | Live attendance, exam, result-approval, staff-leave and notice metrics |
| `/principal/attendance` | `GET /principal/attendance` | Department/class weighted attendance with date range and CSV export |
| `/principal/examinations` | `GET /principal/examinations`, `POST /…/{id}/approval` | All schedules, filters, audited approve/reject decision, CSV export |
| `/principal/results` | `GET /principal/results`, `POST /results/publications/{id}/approval` | Department/class result roll-ups and two-person publication approval |
| `/principal/staff` | `GET /principal/staff`, `GET /principal/staff/{id}` | Read-only staff directory and non-sensitive profile fields |
| `/principal/students` | `GET /principal/students`, `GET /principal/students/{id}` | Read-only student directory with class/enrolment status |
| `/principal/notices` | `GET/POST /principal/notices` | All notices, receipt viewer, institution/department/class composer |
| `/principal/timetable` | `GET /principal/timetable` | Read-only institution/class timetable and CSV export |
| `/principal/reports` | `GET /principal/reports`, `/reports/export` | Attendance, results and combined performance reports / CSV exports |

### Governance migration

`database/update2.sql` (or Alembic revision `e7f2a6c3b904`) adds explicit
`PENDING` / `APPROVED` / `REJECTED` decision state, actor, timestamp and note
to exam schedules and result publications. Existing visible result publications
are backfilled as approved; unpublished legacy publications enter the pending
queue. Every Principal decision is written to the append-only `audit_logs`
table in the same transaction.

### Vice Principal — delegated live console (C-VP-01 … C-VP-07)

The `/vp/*` console is wired to `/api/v1/vice-principal/*`. It uses the same
live academic rows as the Principal console, but **every query is restricted
before aggregation** to active department delegations on the user's
`VICE_PRINCIPAL` role assignments. An unscoped VP is denied rather than being
silently widened to the full institution.

| Page | What works |
|---|---|
| `/vp/dashboard` | Delegated attendance, exams, results, staff and notice metrics, with the resolved department scope shown |
| `/vp/attendance` | Delegated department/class attendance and scoped CSV export |
| `/vp/examinations` | Delegated exam schedules and CSV export — view-only, no final schedule decision |
| `/vp/results` | Delegated result/publication summaries and scoped CSV export — view-only, no final result approval |
| `/vp/notices` | Institution notices plus delegated department/class notices; no read receipt payload |
| `/vp/notices/new` | Post only to delegated departments or their classes; institution-wide posting is server-blocked |
| `/vp/staff` | Read-only staff profiles in delegated departments |

To provision a VP through the Admin **Staff** form, choose `Vice Principal` and
select a delegated department. The same VP may receive more department scopes
through `PUT /api/v1/institution/staff/:id/roles` with
`{"role_name":"VICE_PRINCIPAL","department_id":"…"}`. To remove one
scope, use `DELETE /api/v1/institution/staff/:id/roles/VICE_PRINCIPAL?department_id=…`;
other delegated departments remain active. No schema migration is needed for
delegation: `role_assignments.scope_id` / `scope_type` already model
department-scoped roles.

### Head of Department — live department console (C-HD-01 … C-HD-12)

The `/hod/*` console is wired to `/api/v1/hod/*`. Its scope comes from the
active HOD department role assignment and the canonical `departments.hod_id`
link; all reads and writes are fenced before aggregation, pagination and
mutation. An HOD without a department receives a 403 rather than an
institution-wide fallback.

| Area | What works |
|---|---|
| `/hod/dashboard` | Department KPIs for attendance, assignments, results, notices and exams |
| `/hod/attendance`, `/hod/attendance/report` | Class heatmap plus per-student/subject records and CSV export |
| `/hod/examinations`, `/hod/results` | Department-only schedules/results with CSV export; final approval stays with the Principal |
| `/hod/assignments` | Department assignment and pending-review overview |
| `/hod/teachers` | Subject staffing and safe removal of a scoped teacher-subject link |
| `/hod/mentors` | Assign/reassign/remove one active mentor per student/year |
| `/hod/notices`, `/hod/notices/new` | Institution feed plus department/class-only posting; no read receipt payload |
| `/hod/discussion` | Pin, lock and soft-delete department/class/subject threads |
| `/hod/timetable` | Read-only classes in the HOD's departments |

`database/update2.sql` section 10 / Alembic `e7f2a6c3b904` adds the partial
unique mentor index. Section 11 backfills scoped HOD role assignments for
legacy `departments.hod_id` records. Apply this update before deploying the
HOD console.

---

## 8. Module workflows — status

The legacy preview workflows under `(institution)/*` (attendance marking,
fees, library, hostel, timetable, etc.) currently read from in-memory **demo
data** (`lib/*-data.ts`) and the demo `getSession`. They render for preview/QA
but are **not yet wired to the backend**. The Principal, Vice Principal and
HOD routes in §7 are the exception: they are standalone authenticated
production routes and do not use those fixtures.

The migration pattern is established and identical for each:
1. Add an ORM model (most tables already exist in `database.sql`).
2. Add a service + `/api/v1/institution/<feature>` router (RBAC-scoped).
3. Add a `lib/institution.ts` call + a `/admin/<feature>` client page (or convert
   the existing `(institution)/<feature>` page), removing its `*-data.ts`.

`database/update2.sql` is the current post-base migration file for additive production schema changes; every change also needs a matching Alembic revision.

**Online classes** (`/api/v1/online-classes`, `database/online_class_migration.sql`)
is a fully wired production module: teachers schedule a class from the timetable
or start an instant one (students get a notification), students join through a
waiting room, and the live room (video/audio, screen share, chat, raise hand,
whiteboard, file sharing) runs over one WebSocket per class. Attendance is
automatic — join/leave times are tracked per student and, when the class ends,
scored by policy (≥75% of class duration → Present, 30–74% → Late/Partial,
<30% → Absent) and synced into `attendance_sessions` / `attendance_records`.

---

## 9. Production checklist

- [ ] **Secrets** — `JWT_SECRET_KEY` a 64-hex random string; rotate periodically.
      `APP_DEBUG=false` (hides `/docs`, `/redoc`, stack traces; also hides the
      raw email-verification token from API responses).
- [ ] **Database** — `database.sql`, `update.sql` **and** `update2.sql` applied (or the validated Alembic path reaches `e7f2a6c3b904`); backups on.
- [ ] **CORS** — `ALLOWED_ORIGINS` lists only your real origins
      (`https://shikshasync.me,https://app.shikshasync.me`, approved tenant origins).
- [ ] **Email** — wire an outbound provider to drain `outbox_emails`
      (`tenant.provisioned`, `staff.invited`, `owner.verify_email`). Until then,
      verification/invite links are only visible in dev mode / the DB.
- [ ] **Payments** — replace the mock gateway in
      `SignupService.mark_paid` with a real Razorpay/Cashfree webhook handler
      (SYSTEM-FLOW §9.1; `UNIQUE(gateway, gateway_ref)` already guards replays).
- [ ] **DNS / hosts** — apex `shikshasync.me`, staff `app.shikshasync.me`, tenant `*.shikshasync.me`.
- [ ] **Frontend build** — `npm run build` in CI. The app uses local/system font stacks, so production builds do not depend on a Google Fonts network fetch.
- [ ] **Process** — run the backend with `python run.py --prod` (4 workers) or a
      process manager; serve the frontend via `next start` or a CDN.
- [ ] **Rate limits** — already set per endpoint via `slowapi`; front with your
      proxy's limits too.

---

## 10. API quick reference

All under `/api/v1`. Authenticated routes take `Authorization: Bearer <jwt>`.

| Group | Prefix | Key endpoints |
|---|---|---|
| Owner (customer) | `/owner` | `/signup`, `/verify-email`, `/login`, `/me`, `/institutions`, `/billing/summary`, `/subscriptions`, `/invoices`, `/payments`, `/tickets`, `/orders` (+ `/pay`) |
| Public signup | `/public` | `/catalog`, `/subdomains/check`, `/quote`, `/orders` (+ `/pay`), `/service-requests` |
| Institution admin | `/institution` | `/dashboard`, `/academic-years`, `/departments`, `/classes`, `/subjects`, `/staff`, `/students`, `/enrollments`, `/modules`, `/settings`, `/profile` |
| Principal | `/principal` | `/dashboard`, `/attendance`, `/examinations` (+ schedule approval), `/results` (+ publication approval), `/staff`, `/students`, `/notices`, `/timetable`, `/reports`, `/reports/export` |
| Vice Principal | `/vice-principal` | Delegated `/dashboard`, `/attendance`, `/examinations`, `/results`, `/staff`, `/notices`, `/reports/export`; no final approval endpoints |
| Head of Department | `/hod` | Department dashboard, attendance detail/export, exams, assignments, results, teachers/subjects, mentors, notices, discussion moderation and timetable |
| Online classes | `/online-classes` | Teacher: `/setup-options`, schedule (`POST`), `/instant`, `/{id}/start`, `/{id}/end`, admit/remove, `/{id}/attendance`, `/{id}/files`, `/{id}/recording`. Student: `/my/classes`, `/{id}/join`, `/{id}/leave`, chat, materials. Live room: `WS /{id}/live` |
| Tenant auth | `/tenant/auth` | `/login`, `/logout`, `/refresh`, `/me`, `/forgot-password`, `/reset-password` |
| Platform staff auth | `/platform/auth` | `/login`, `/logout`, `/refresh`, `/me` |
| Setup wizard | `/setup` | `GET`, `PUT`, `POST /complete` |

OpenAPI: with `APP_DEBUG=true`, browse `http://localhost:8000/docs`.

---

## 11. Running the tests

```bash
cd backend
pytest -q          # backend unit/API tests, including Principal governance routes
```

Tests use scripted fake DB sessions (no Postgres required) and cover the
provisioning pipeline, gapless invoicing, owner signup→verify→login, and the
institution-admin RBAC guard + plan-gated modules.

---

## 12. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `401 Could not validate …` | Token missing, expired, or wrong type for the endpoint. Re-login; owner tokens are `type=owner`, institution `type=tenant`, staff `type=platform`. |
| `403 Institution admin privileges are required` | The tenant user does not hold the INSTITUTION_ADMIN role in `role_assignments` for their tenant. Grant it (seed/setup wizard). |
| `403 Principal privileges are required` | The tenant user needs an active, unexpired PRINCIPAL assignment. A Vice Principal cannot approve final schedules or result publications. |
| `402 … not included in your plan` | Optional module toggle blocked by `plans.allowed_modules`. Upgrade the plan. |
| `next build` fails | Run `npm ci` first, then inspect the reported TypeScript/route error. The app no longer fetches Google Fonts during build. |
| Email links never arrive | No outbound provider draining `outbox_emails`. In dev (`APP_DEBUG=true`) the owner verification token is returned in the signup response. |
| Migration conflict | Ensure a single source: raw SQL (`database.sql` + `update.sql` + `update2.sql`) **or** your validated Alembic path, not both. Current head revision is `e7f2a6c3b904`. |

---

## 13. Documentation index

- `doc/ARCHITECTURE.md` — system architecture
- `doc/SYSTEM-FLOW.md` — lead → purchase → onboarding → daily operation
- `doc/PLATFORM-OWNER-ACCOUNTS.md` — the account-holder (multi-institution) model
- `doc/database_design_complete.md`, `doc/role_based_system_design.md`
- `doc/PAGES-TODO.md` — page coverage matrix
- `INSTITUTION-ADMIN-GUIDE.md` — the office user guide (no technical background needed)
- `PARENT-PORTAL-USER-GUIDE.md` — screen-by-screen how-to for guardians (activation, every menu,
  leave filing) and for the office board that grants or removes access
- `System.md` — parent–student connected access: schema, enforcement, the 23 guardian endpoints,
  both consoles and the test map

_Manual v1.5 — verified against the 106-table schema, `update2.sql`, Alembic
head `e7f2a6c3b904`, and the live `/admin`, `/principal`, `/vp` and `/hod` consoles._
