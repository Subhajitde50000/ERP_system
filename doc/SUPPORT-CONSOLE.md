# Support Staff Console — C-SP-01 … C-SP-04

End-to-end: database → API → client → hook → page. All four pages from
`complete_webpage_developer_assignment.md` §2.2 run on real data.

---

## What existed before

All four pages rendered, but from `lib/support-data.ts` fixtures. None of the
four APIs existed, and replying printed the request it would have sent:

```
// TODO(Dev-A): POST /api/v1/platform/tickets/:id/reply
setNotice(`POST /platform/tickets/${id}/reply … — API not connected yet`)
```

---

## Deploying

```bash
psql -f database/database.sql
psql -f database/update.sql
psql -f database/update2.sql          # ← §8 adds the Support schema

# …or with Alembic
cd backend && alembic upgrade head
```

Create a Support account, then sign in at `app.shikshasync.me/platform/login`:

```bash
python backend/scripts/create_superadmin.py \
  --email support@shikshasync.me --password 'StrongPass!' --name "Support Agent"
# then set platform_role = 'SUPPORT'
```

---

## The API (§2.2)

| Page | Route | Endpoint |
|---|---|---|
| C-SP-01 Dashboard | `/platform/support/dashboard` | `GET /platform/support/stats` |
| C-SP-02 Ticket list | `/platform/support/tickets` | `GET /platform/tickets` |
| C-SP-03 Ticket detail | `/platform/support/tickets/:id` | `GET·PATCH /platform/tickets/:id`, `POST …/reply` |
| C-SP-04 Institution read-only | `/platform/support/institutions/:id` | `GET /platform/institutions/:id/readonly` |

Access is Support **or** Super Admin — §4.1 gives the Super Admin
platform-wide oversight, and an escalated ticket must be reachable. Sales and
Finance authenticate against the same `platform_users` table and get 403.

---

## Rules the console enforces

From `role_based_system_design.md` §4.1 — *"View institution data in read-only
mode · Respond to support tickets · **Cannot modify institution data or
settings**"*:

- **Read-only is structural.** The snapshot route has no `PATCH`/`PUT`/`DELETE`
  sibling, so all four return 405. A test asserts the router exposes no write
  path outside `/tickets`, rather than trusting a comment.
- **CLOSED is terminal.** Reopening is the customer raising a new ticket. Every
  other transition is validated server-side, so the dropdown can never offer a
  move the API refuses.
- **Internal notes never reach the customer.** Filtered in the owner query's
  `WHERE` clause, not a loop, so a refactor cannot drop the guard.
- **A public reply moves OPEN → IN_PROGRESS**; an internal note does not — a
  memo to the team is not a response.
- **`resolved_at` is stamped on resolve**, because that is what the dashboard's
  "resolved today" counts.
- **Every mutation writes `audit_logs`** in the same transaction.

---

## Schema — `update2.sql` §8

`support_tickets` existed in **two incompatible shapes**:

| | database.sql §10.2 | update.sql §1 |
|---|---|---|
| Raiser | `raised_by` → users | `owner_id` → platform_owners |
| Tenant | NOT NULL | nullable |
| Has | `assigned_to`, `description`, `resolved_at` | `category` |

Each was missing half of the other. C-SP-02 says *"All tickets"*, so §8 unifies
them into **one queue** — one SLA clock, one reply thread — with a CHECK that
exactly one raiser is set. Two tables would have meant two of everything.

Also added: `reference` (TKT-1042, sequence-backed — never `count(*)+1`, which
races), `is_internal` on messages, and five queue indexes.

### Three conflicts settled

| # | Conflict | Resolution |
|---|---|---|
| 1 | Priority was `LOW/NORMAL/HIGH/URGENT` in the ORM but `LOW/MEDIUM/HIGH/CRITICAL` in `database.sql` *and* `types/support.ts` | DB spelling wins; rows migrated; CHECK stops the old values returning |
| 2 | Owner ticket replies returned internal notes | filtered in SQL — a staff-only memo would have been shown to the customer |
| 3 | Owner create defaulted priority to `NORMAL` | now `MEDIUM`; the new CHECK would have made every owner ticket 500 |

---

## Two bugs only real PostgreSQL caught

1. **Blank references.** SQLAlchemy sent an explicit `NULL` for `reference`, so
   Postgres never applied its `DEFAULT`. Tickets created through the app had no
   reference; raw `INSERT`s did. Fixed with `server_default`.
2. **Bare numbers.** Binding the `Sequence` to the column made SQLAlchemy
   pre-fetch `nextval` and insert `1001` instead of `TKT-1001`. It now sits on
   the metadata only — still emitted by `create_all` for the integration tests,
   but the server applies the prefix.

Neither is visible against mocks.

---

## Structure

```
backend/
├── app/schemas/support.py            camelCase wire contracts
├── app/services/support_service.py   queue, SLA, transitions, snapshot
└── app/routers/platform/support.py   the 6 routes

fontend/
├── lib/platform-api.ts               + Support endpoints (same client)
├── hooks/use-support-console.tsx     4 bindings over useResource
└── components/support/consoles.tsx   hook → existing component
```

**No new primitives.** `useResource`, `<Live>` and `useAction` come from the
Super Admin work; the Support endpoints live in the existing `platform-api.ts`
because they share the origin, token and transport. `TicketList`,
`TicketDetail` and `InstitutionReadonly` keep their markup and props.

`SLA_HOURS` and `STATUS_TRANSITIONS` exist on both sides by necessity — the
server enforces, the client renders. Two tests parse `fontend/lib/support.ts`
and fail if either drifts.

---

## Hardcoded data removed

- `CURRENT_AGENT = { id: "pu-2", name: "Nandini Rao" }` — every agent saw that
  name on the reply box, and "assigned to me" filtered on somebody else's id.
  Now from the platform session.
- `{slug}.shikshasync.me` in the read-only view → `tenantHost()`.
- `lib/support-data.ts` (352 lines) deleted as dead code.

---

## Verification

| Check | Result |
|---|---|
| Backend unit tests | **125 passed** (was 94) |
| End-to-end vs. real PostgreSQL 16 | **60 assertions** on a from-scratch database |
| Client↔server contract | **25 assertions** — keys match `types/support.ts`; PATCH/POST/PUT/DELETE on the snapshot all 405 |
| `next build` | succeeds; all 4 routes compile |
| `tsc --noEmit` / ESLint | clean |
| `update2.sql` | idempotent; zero ORM drift on a fresh DB |

The 31 new unit tests include two cross-language drift guards, each verified by
reverting the fix and confirming the test fails.
