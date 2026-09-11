# Platform Console — Super Admin (C-SA-01…08) + Owner

End-to-end: database → API → client → hook → page. All eight pages from
`complete_webpage_developer_assignment.md` §2.1 now run on real data.

---

## What existed before

All eight pages rendered, but from `lib/platform-data.ts` fixtures. None of
the five API groups had been built, and every action printed the request it
would have sent:

```
// TODO(Dev-A): POST /api/v1/platform/tenants …
setDone(`POST /platform/tenants { … } — API not connected yet (Dev-A, C-SA-04).`)
```

---

## Deploying

```bash
# 1. Schema (raw SQL)
psql -f database/database.sql
psql -f database/update.sql
psql -f database/update2.sql          # ← new, idempotent

#    …or with Alembic (equivalent, and now single-headed again)
cd backend && alembic upgrade head

# 2. Catalogue, roles, plans, Super Admin
python backend/scripts/seed_data.py
python backend/scripts/create_superadmin.py \
  --email admin@shikshasync.me --password 'StrongPass!' --name "Super Admin"

# 3. Run
cd backend  && uvicorn app.main:app
cd fontend  && npm run build && npm start
```

Sign in at `app.shikshasync.me/platform/login` → lands on `/platform/dashboard`.

---

## The API (§2.1)

| Page | Route | Endpoint |
|---|---|---|
| C-SA-01 Dashboard | `/platform/dashboard` | `GET /platform/dashboard-stats` |
| C-SA-02 Institution list | `/platform/institutions` | `GET /platform/tenants` |
| C-SA-03 Institution detail | `/platform/institutions/:id` | `GET·PATCH /platform/tenants/:id`, `PUT …/active`, `DELETE` |
| C-SA-04 Create institution | `/platform/institutions/new` | `POST /platform/tenants` |
| C-SA-05 Plans | `/platform/plans` | `GET·POST /platform/plans`, `PATCH /platform/plans/:id` |
| C-SA-06 Platform users | `/platform/platform-users` | `GET·POST /platform/users`, `PATCH /platform/users/:id` |
| C-SA-07 Audit logs | `/platform/audit-logs` | `GET /platform/audit-logs` |
| C-SA-08 Settings | `/platform/settings` | `GET·PATCH /platform/settings` |

Every route is Super-Admin-only. Support/Sales/Finance authenticate against
the same `platform_users` table, so a valid token is not enough — one
`require_super_admin` dependency guards the whole router and returns 403.

Responses are camelCase on the wire (`Wire` base class in
`schemas/platform_admin.py`), matching `types/platform.ts` exactly, so the
client needs no key translation.

---

## Rules the console enforces

From `role_based_system_design.md` §4.1:

- **Reserved subdomains** — `admin`, `app`, `api`, `www`… are refused (409).
  A tenant may never claim a host the platform answers on.
- **Plan scoping** — a tenant can only enable modules its plan includes.
  Downgrading re-scopes `tenant_modules`, so a demoted tenant can't keep paid
  features. Core modules are always on (§3).
- **Last Super Admin** — cannot be deactivated or demoted, and you cannot
  deactivate yourself. Locking the console out of itself is unrecoverable
  without a DB edit.
- **Audit-only on tenant data** — the console edits *platform* concerns
  (plan, modules, lifecycle, profile). Academic records stay read-only.
- **Soft delete** — deactivate + cancel subscriptions. A hard `DELETE` would
  cascade through ~100 tables of academic history.
- **Audit trail** — every mutation writes `audit_logs` in the *same*
  transaction, so the trail can never disagree with reality. Append-only:
  there is no update or delete path (§10.3).

---

## Structure

```
backend/
├── app/models/audit.py                    AuditLog (§10.3)
├── app/models/platform_setting.py         key/value + code defaults
├── app/schemas/platform_admin.py          camelCase wire contracts
├── app/services/audit_service.py          record() + the C-SA-07 reader
├── app/services/platform_admin_service.py the console's logic
└── app/routers/platform/admin.py          the 13 routes

fontend/
├── lib/platform-api.ts                    typed client
├── hooks/use-platform-admin.tsx           useResource + 8 bindings
├── components/platform/live.tsx           <Live>, useAction, <ActionBar>
├── components/platform/consoles.tsx       hook → existing component
└── app/(platform)/layout.tsx              session gate
```

**No page layout was rewritten.** `InstitutionList`, `InstitutionDetail`,
`CreateInstitution`, `PlatformUsers` and `PlatformAuditView` keep their
existing props and markup; they only gained optional action callbacks
(`onSetActive`, `onCreate`, `onToggleActive`, `onInvite`). Omit the callback
and the original unwired preview behaviour returns, which is what `?role=`
still uses.

Loading, error, retry and mutation state live in `useResource` and `<Live>`
once, not eight times.

---

## Schema drift found and fixed

`update2.sql` adds `audit_logs`, `platform_settings` and the console's
indexes. Running it against a real PostgreSQL 16 also surfaced four
pre-existing mismatches between `database.sql` and the Alembic migrations.
Each broke production on a raw-SQL deployment:

| # | Drift | Symptom |
|---|---|---|
| 1 | `modules.price_monthly` missing | every Module query → `UndefinedColumnError` |
| 2 | `subscriptions.status` etc. are PG ENUMs; code sends VARCHAR | `DatatypeMismatchError` on **any** subscription insert — self-service signup was broken too |
| 3 | 8 tables only in Alembic (`orders`, `outbox_emails`, `platform_invoices`, `platform_payments`, `coupons`, `platform_sessions`, `platform_invoice_lines`, `support_ticket_messages`) | no billing or email layer at all |
| 4 | `orders.owner_name`, `support_tickets.owner_id`/`category` missing | owner dashboard queries failed |

After `update2.sql`, a from-scratch raw-SQL database has **zero** table or
column drift against the ORM.

Two unrelated pre-existing bugs also blocked the build and are fixed:
`lib/signup.ts` had a truncated duplicate `getJson()` from a bad merge (the
whole app failed `tsc`), and `/verify-email` used `useSearchParams` with no
Suspense boundary (`next build` prerender error).

---

## Owner console

The same route group serves the **Owner** — the paying customer who owns
institutions. Its backend (`/api/v1/owner/*`) and client (`lib/owner.ts`)
already existed; the seven pages were the last fixtures and are now live:

| Page | Route | Endpoint |
|---|---|---|
| Dashboard | `/platform/dashboard` (OWNER) | `/owner/institutions`, `/billing/summary` |
| My Institutions | `/platform/my-institutions` | `GET /owner/institutions` |
| Billing | `/platform/billing` | `GET /owner/billing/summary`, `/payments` |
| Subscriptions | `/platform/subscriptions` | `GET /owner/subscriptions` |
| Invoices | `/platform/invoices` | `GET /owner/invoices` |
| Support Tickets | `/platform/tickets` | `GET·POST /owner/tickets`, `…/reply` |
| Profile | `/platform/profile` | `PUT /owner/profile`, `POST /change-password` |

Two account types now share `app.shikshasync.me` (`platform_users` staff and
`platform_owners` customers). The gate accepts either; each API rejects the
other's token, which the test suite asserts in both directions.

---

## Production audit

Five defects found and fixed after the initial build:

| # | Defect | Effect |
|---|---|---|
| 1 | Trial countdown measured against a frozen 2026-07-29 clock | a 14-day trial displayed "19d left" |
| 2 | `.shikshasync.me` hardcoded in 11 places | staging / white-label deploys showed the wrong host; "Open" links went to the wrong environment |
| 3 | Sidebar always showed the demo name "Vikram" | every Super Admin saw the same wrong identity |
| 4 | `rahul@gmail.com` and an invented "2 tickets" in the Owner dashboard | fake data on a customer-facing page |
| 5 | Owner API returned snake_case, `types/owner.ts` expects camelCase | **silent** — every owner field read `undefined` and rendered blank, no error anywhere |

Defect 5 is the dangerous class: a wrong key is not an exception, it is an
empty screen. Three regression tests now lock the camelCase contract for both
consoles, and were verified by reverting the fix and confirming they fail.

### Duplication removed

| Was | Now |
|---|---|
| `Wire` inside `platform_admin.py` | `schemas/common.py`, shared by both schema modules |
| `Envelope` + error class + fetch/unwrap/422-flatten in 3 clients | `lib/api-client.ts`; clients keep only base path + token |
| `lib/owner.ts` hand-mapping snake→camel in 3 places | removed — the API emits camelCase |
| `useResource` inside `use-platform-admin` | `hooks/use-resource.tsx`, reused by the Owner hooks |
| `owner-console.tsx`, `owner-section-page.tsx` | deleted (dead once pages went live) |

---

## Verification

| Check | Result |
|---|---|
| Backend unit tests | **94 passed** (was 30 passing + 1 failing at the start) |
| End-to-end vs. real PostgreSQL 16 | **52 assertions** — Super Admin, Owner, and cross-console isolation |
| Client↔server contract | **23 assertions** — every response key matches `types/platform.ts` / `types/owner.ts` |
| `next build` | succeeds; all platform routes compile |
| `tsc --noEmit` / ESLint | clean on every touched file |

The end-to-end run covers authorisation (401/403/200 for anonymous, staff,
owner and Super Admin), tenant CRUD with provisioning side effects, plan
scoping, module downgrade, suspend/reactivate, staff management, the
last-Super-Admin guard, audit filters, settings persistence, soft delete, and
the full owner journey (login → institutions → billing → tickets → profile).

The end-to-end run covers authorisation (401/403/200), tenant CRUD with
provisioning side effects (admin user, role, academic year, activation
email), plan scoping, module downgrade, suspend/reactivate, staff management,
the last-Super-Admin guard, audit filters, settings persistence, and soft
delete.
