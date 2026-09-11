# ERP + LMS Platform — System & Backend Architecture

> **Scope.** `TECHNICAL-DETAILS-AND-SYSTEM-DESIGN.md` and `DEPLOYMENT.md` specify the
> production stack, repo layout, guards, module system, API envelope, and
> deployment. **This document covers:** the failure modes, the data-integrity rules, the
> operational contract, and tenant isolation architecture.
>
> Read `TECHNICAL-DETAILS-AND-SYSTEM-DESIGN.md` for *what* is built. Read this one for
> *reliability, failure modes, and operational guardrails*.
>
> Companion: `database.sql` (106 tables, verified on PostgreSQL 17),
> `DB-DOC-AUDIT.md`, `docs/database_design_complete.md` v2.1.

---

## Table of Contents

1. [Architecture at a glance](#1-architecture-at-a-glance)
2. [Three defects in the current design](#2-three-defects-in-the-current-design)
3. [Tenant isolation — defence in depth](#3-tenant-isolation--defence-in-depth)
4. [Authorization model](#4-authorization-model)
5. [Backend service architecture](#5-backend-service-architecture)
6. [Data access & the connection budget](#6-data-access--the-connection-budget)
7. [Write integrity: idempotency, concurrency, transactions](#7-write-integrity-idempotency-concurrency-transactions)
8. [Async work: queues, jobs and the outbox](#8-async-work-queues-jobs-and-the-outbox)
9. [Caching & invalidation](#9-caching--invalidation)
10. [Real-time layer](#10-real-time-layer)
11. [File storage](#11-file-storage)
12. [Failure modes & degradation](#12-failure-modes--degradation)
13. [Observability](#13-observability)
14. [Security controls](#14-security-controls)
15. [Deployment & release safety](#15-deployment--release-safety)
16. [Capacity model](#16-capacity-model)
17. [Backup & disaster recovery](#17-backup--disaster-recovery)
18. [Environments & configuration](#18-environments--configuration)

---

## 1. Architecture at a glance

The platform is **one deployment serving many institutions**, split across two
origins that share a database but not a permission model.

```
                          ┌───────────────────────────────┐
                          │        CloudFront (CDN)       │
                          │   TLS · WAF · rate limiting   │
                          └───────────────┬───────────────┘
                                          │
              ┌───────────────────────────┼───────────────────────────┐
              │                           │                           │
    app.shikshasync.me                 *.shikshasync.me                    api.shikshasync.me
    (platform console)          (tenant app)                 (REST + WS)
              │                           │                           │
    ┌─────────▼─────────┐      ┌──────────▼────────┐      ┌───────────▼─────────┐
    │  Next.js (RSC)    │      │  Next.js (RSC)    │      │  NestJS API         │
    │  4 platform roles │      │  18 inst. roles   │      │  ── middleware ──   │
    └─────────┬─────────┘      └──────────┬────────┘      │  RequestContext     │
              │                           │               │  TenantResolver     │
              └────────────┬──────────────┘               │  AuthGuard          │
                           │  server-side fetch           │  RolesGuard         │
                           └──────────────────────────────►  ModuleGuard        │
                                                          │  ScopeGuard  ◄─ NEW │
                                                          └───────────┬─────────┘
                                                                      │
        ┌──────────────┬──────────────┬──────────────┬────────────────┤
        │              │              │              │                │
  ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐   ┌──────▼──────┐
  │ PgBouncer │  │  Redis 7  │  │  BullMQ   │  │ Socket.IO │   │     S3      │
  │  (pool)   │  │ cache/pub │  │  workers  │  │  gateway  │   │  + presign  │
  └─────┬─────┘  └───────────┘  └─────┬─────┘  └───────────┘   └─────────────┘
        │                             │
  ┌─────▼──────────────┐              └──► SES (email) · FCM (push)
  │  PostgreSQL 15+    │
  │  primary + replica │
  └────────────────────┘
```

**Two origins, one API.** `app.shikshasync.me` has no `tenant_id`; `*.shikshasync.me` always
has one. The same NestJS app serves both — the tenant resolver decides which
mode a request is in, and that decision is the root of every authorization
check downstream.

### Request lifecycle (corrected)

```
  1. CloudFront          TLS, WAF, edge rate limit (per IP)
  2. ALB                 health check, connection draining
  3. RequestContext      AsyncLocalStorage: requestId, tenantId, userId
  4. TenantResolver      subdomain → tenant (Redis, 5-min TTL)
                         ── platform origin: tenantId = null
  5. AuthGuard           verify JWT signature + exp; load session from Redis
  6. RolesGuard          role ∈ route's allowed roles
  7. ModuleGuard         module enabled for tenant (core modules bypass)
  8. ScopeGuard   ← NEW  row-level: is THIS record inside the caller's scope?
  9. Controller          DTO validation (class-validator, whitelist: true)
 10. Service             business rules; transaction boundary lives here
 11. Repository          Prisma, tenant filter applied by extension
 12. Interceptor         response envelope, audit event → outbox
```

Steps 6–8 are three different questions and are routinely conflated:

| Guard | Question | Failure |
|---|---|---|
| `RolesGuard` | *May a TEACHER call this endpoint at all?* | 403 |
| `ModuleGuard` | *Does this institution have `library` switched on?* | 403 |
| `ScopeGuard` | *Is class `c-42` one of **this** teacher's classes?* | 404 |

**ScopeGuard returns 404, not 403.** A 403 on `/students/:id` confirms the
student exists. For any resource keyed by a person's identity, an out-of-scope
read must be indistinguishable from a non-existent one.

---

## 2. Three defects in the current design

Found by auditing `developer_system_design_deployment.md` against
`database.sql`. All three are load-bearing.

### 2.1 🔴 The tenant-scoping extension covers 13 of 81 tables

§5.3 hard-codes a `tenantScopedModels` array:

```typescript
const tenantScopedModels = [
  'User', 'Department', 'Class', 'Subject',
  'AttendanceSession', 'AttendanceRecord',
  'Exam', 'ExamAttempt', 'Assignment', 'Submission',
  'Notice', 'ContentItem', 'DiscussionThread',
];   // 13 models
```

`database.sql` has **81 tables carrying `tenant_id`**. The other 68 —
including `fee_payments`, `payslips`, `book_issues`, `student_results`,
`malpractice_logs` — are queried with **no tenant filter at all**. Any handler
that forgets a manual `where: { tenantId }` returns another institution's
data, and the array silently rots every time a table is added.

**Fix — derive the list, never hand-maintain it:**

```typescript
// Built once at boot from the generated Prisma DMMF, so a new table with a
// tenantId column is scoped the moment it exists. A hand-written list is one
// migration away from being wrong.
import { Prisma } from '@prisma/client';

export const TENANT_SCOPED = new Set(
  Prisma.dmmf.datamodel.models
    .filter((m) => m.fields.some((f) => f.name === 'tenantId'))
    .map((m) => m.name),
);

// Fail fast rather than leak: a model that looks tenant-ish but isn't in the
// set is a bug, and boot is the cheapest place to find it.
if (TENANT_SCOPED.size !== 81) {
  throw new Error(`Expected 81 tenant-scoped models, found ${TENANT_SCOPED.size}`);
}
```

### 2.2 🔴 18 child tables have no `tenant_id` — cross-tenant reads by id

These inherit isolation only through a parent FK:

```
answers · questions · question_options · exam_sections · milestones
submission_files · notice_attachments · notice_reads · discussion_votes
content_tags · content_access_logs · transport_stops · drive_eligibility
interview_rounds · appraisals · application_documents
purchase_order_items · device_tokens
```

No tenant column means no filter is *possible*. `GET /questions/:id` with a
guessed UUID reads another institution's exam paper.

**Fix — always join to the parent, never query the child alone:**

```typescript
// WRONG — nothing constrains this to the caller's tenant
return this.prisma.question.findUnique({ where: { id } });

// RIGHT — the parent carries tenant_id, so the join enforces it
return this.prisma.question.findFirst({
  where: { id, exam: { tenantId: ctx.tenantId } },
});
```

Codify it: a lint rule banning `findUnique` on any model in the
no-tenant-column set, plus an integration test per table that asserts a
foreign tenant's id returns null. RLS (§3.3) is the belt to this braces.

### 2.3 🔴 `new PrismaClient()` per request exhausts the connection pool

§5.3 is `Scope.REQUEST` and constructs a client in the constructor. Each
`PrismaClient` opens its **own** pool (`num_cpus * 2 + 1` by default).

| Load | In-flight (Little's law) | Per-request client | Singleton |
|---|---|---|---|
| 50 rps @ 80 ms, 2 vCPU | ~4 | 20 conns | 5 |
| 200 rps @ 80 ms, 4 vCPU | ~16 | 144 conns | 9 |
| **500 rps @ 80 ms, 4 vCPU** | ~40 | **360 conns** | **9** |

`db.t4g.medium` allows ~340. The design dies at 500 rps on one task — before
horizontal scaling multiplies it.

**Fix — one singleton client; carry the tenant in `AsyncLocalStorage`:**

```typescript
@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit {
  constructor(private readonly ctx: RequestContextService) {
    super({ log: [{ emit: 'event', level: 'query' }] });
  }

  onModuleInit() {
    this.$extends({
      query: {
        $allModels: {
          async $allOperations({ model, args, query }) {
            const tenantId = ctx.get('tenantId');   // ALS, not DI scope
            if (tenantId && TENANT_SCOPED.has(model)) {
              args.where = { ...args.where, tenantId };
            }
            return query(args);
          },
        },
      },
    });
  }
}
```

`AsyncLocalStorage` gives per-request state without per-request instances —
which is the whole reason `Scope.REQUEST` was reached for.

---

## 3. Tenant isolation — defence in depth

One control is not enough; a single missed `where` clause should not be a
breach. Four layers, each independently sufficient:

| # | Layer | Catches |
|---|---|---|
| 1 | **Subdomain → tenant** at the edge | Wrong-origin requests |
| 2 | **JWT `tenantId` must equal resolved tenant** | Replaying a token on another subdomain |
| 3 | **Prisma extension** injects `tenantId` | A forgotten `where` clause |
| 4 | **PostgreSQL RLS** | Anything the ORM misses, including raw SQL |

### 3.1 Token/origin binding

```typescript
// A token minted for abc-college replayed against xyz-school must fail even
// though the signature is valid. Bind the token to the origin.
if (payload.tenantId !== ctx.get('tenantId')) {
  throw new UnauthorizedException('Token does not belong to this institution');
}
```

### 3.2 Impersonation is read-only and always audited

§4.1 grants Support Staff "impersonate (read-only) for debugging". Model it in
the token, not by logging in as the user:

```typescript
interface JwtPayload {
  sub: string;
  tenantId: string | null;
  roles: string[];
  impersonatedBy?: { platformUserId: string; ticketId: string };  // ← present = read-only
}
```

Any mutating verb with `impersonatedBy` set is rejected at the guard, and every
request writes an audit row naming the real operator and the ticket.

### 3.3 Row-Level Security as the backstop

`database.sql` §7 ships the template commented out. Recommended **on** in
production:

```sql
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON users
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
```

```typescript
// SET LOCAL, never SET: with PgBouncer a session GUC leaks to whoever
// borrows the connection next. SET LOCAL dies with the transaction.
await this.prisma.$transaction(async (tx) => {
  await tx.$executeRaw`SELECT set_config('app.current_tenant', ${tenantId}, true)`;
  return work(tx);
});
```

This requires **transaction-mode** pooling (§6) and every tenant-scoped query
inside a transaction. That is a real cost — measure it before committing.

---

## 4. Authorization model

Four independent dimensions. Collapsing any two of them is the most common
source of permission bugs in this codebase's domain.

```
  WHO      roles[]              TEACHER, HOD, PRINCIPAL …  (22 total)
  WHAT     module               attendance, library …      (16 keys)
  ACTION   CREATE/READ/…        permissions table
  WHICH    scope                ALL | DEPARTMENT | CLASS | SUBJECT | OWN | CHILD
```

### 4.1 Scope resolution

`scope_level` on `roles` says how wide a role reaches; the resolver turns that
into a concrete id set, cached per session:

```typescript
type Scope =
  | { kind: 'ALL' }                                   // Institution Admin, Principal
  | { kind: 'DEPARTMENT'; ids: string[] }             // HOD
  | { kind: 'CLASS'; ids: string[] }                  // Class teacher
  | { kind: 'SUBJECT'; ids: string[] }                // Teacher
  | { kind: 'OWN'; userId: string }                   // Student, staff self-service
  | { kind: 'CHILD'; studentIds: string[] };          // Parent

// Multi-role users get the UNION. A Teacher who is also HOD sees the whole
// department, not the intersection — the richest grant wins, matching how the
// frontend already merges permissions.
```

### 4.2 Decide entitlement in the data layer

The single most important rule in this codebase, learned repeatedly on the
frontend and equally true server-side:

> **Never return a field the caller may not see and rely on the UI to hide
> it.** Pass the permission object *into* the query builder so unowned columns
> are absent from the response body.

```typescript
// WRONG — bank details reach the client; the UI hides them
const staff = await this.repo.findOne(id);
return { ...staff, canSeeSalary: perms.hr };

// RIGHT — the projection depends on the grant
return this.repo.findOne(id, {
  select: perms.hr ? FULL_STAFF_SELECT : PUBLIC_STAFF_SELECT,
});
```

Real leaks this prevents, all of which the frontend audit caught: PAN/bank/PF,
exam answer keys, classmates' marks, borrower identities, other students' fee
accounts.

### 4.3 Permission caching

Resolving roles + scope + modules costs 4 queries. Cache per session:

```
Key    perm:{tenantId}:{userId}
TTL    900s
Bust   role_assignments write · tenant_modules write · user deactivation
```

Invalidate by **publishing on Redis pub/sub**, not by waiting for TTL — a
revoked role that stays live for 15 minutes is a security incident.

---

## 5. Backend service architecture

NestJS modules map 1:1 to the 16 module keys plus platform concerns.

```
apps/api/src/
├── common/
│   ├── context/          AsyncLocalStorage request context
│   ├── guards/           Auth · Roles · Module · Scope
│   ├── interceptors/     envelope · audit · timeout
│   ├── filters/          global exception → error envelope
│   ├── prisma/           singleton client + tenant extension
│   └── redis/            cache · pub-sub · locks
├── platform/             tenants · plans · subscriptions · support · billing
├── identity/             auth · users · roles · sessions
├── structure/            departments · classes · subjects · enrolments
├── modules/
│   ├── attendance/  examination/  assignment/  notice/
│   ├── discussion/  content/      results/     timetable/
│   ├── library/     hostel/       transport/   placement/
│   └── hr/          admission/    inventory/   finance/
└── jobs/                 BullMQ processors
```

**Layering rule:** Controller (HTTP only) → Service (business rules, owns the
transaction) → Repository (Prisma only). A controller must never touch Prisma;
a repository must never contain an `if (role === …)`.

**Cross-module calls go through the owning service, never its tables.**
`results` needs marks from `examination` → it calls `ExaminationService`, not
`prisma.examAttempt`. This is the server-side form of the ownership rule the
frontend fixtures follow, and it is what makes the modules independently
testable.

### 5.1 The one hard cross-module rule

§4.1 says Finance Manager "cannot access institution academic data". That is
not a UI concern — the platform-billing service must have **no import path**
to any academic repository. Enforce it in CI:

```json
// .eslintrc — dependency-cruiser or eslint-plugin-boundaries
{ "from": "platform/billing", "disallow": ["modules/*"] }
```

A guard can be bypassed by a new endpoint; a missing import cannot.

---

## 6. Data access & the connection budget

### 6.1 PgBouncer is mandatory, not optional

ECS tasks scale horizontally; PostgreSQL connections do not. Without a pooler,
every new task multiplies the connection count.

```
50 tasks × 9 pool connections = 450 connections → exceeds db.m6g.large (683)
                                                   at ~75 tasks
With PgBouncer (transaction mode):
50 tasks × 9 client connections → PgBouncer → 25 server connections
```

**Transaction mode** — not session mode. Consequences, all of which change how
you write code:

- No session-level `SET`. Use `SET LOCAL` inside a transaction (§3.3).
- No `LISTEN/NOTIFY`. Use Redis pub/sub, which we already run.
- Prepared statements need `pgbouncer=true` in the Prisma URL.

### 6.2 Read replicas

Route the heavy read-only paths to a replica; keep everything else on the
primary.

| Path | Target | Why |
|---|---|---|
| Reports, analytics, exports | replica | Minutes-old data is fine |
| Dashboards | replica | Same |
| Everything transactional | primary | Replica lag breaks read-your-writes |

**The trap:** marking attendance then immediately reloading the class must not
hit the replica, or the teacher sees their own write missing. Rule: *any read
in the same request as a write, or in the redirect after one, goes to the
primary.*

### 6.3 N+1 is the default failure

Prisma makes N+1 easy. A class of 60 with a naive include is 61 queries.

```typescript
// WRONG — one query per student
for (const s of students) s.attendance = await this.repo.forStudent(s.id);

// RIGHT — one query, grouped in memory
const rows = await this.prisma.attendanceRecord.groupBy({
  by: ['studentId', 'status'],
  where: { studentId: { in: students.map((s) => s.id) }, session: { classId } },
  _count: true,
});
```

Enforce it: log every request issuing > 20 queries with its route, and fail CI
on a golden-query-count test for the ten hottest endpoints.

### 6.4 Pagination

Offset pagination degrades on large tables (`OFFSET 100000` scans 100k rows)
and skips rows when data shifts mid-scroll. Use **keyset** for anything
append-heavy — audit logs, notifications, discussion replies:

```sql
SELECT * FROM audit_logs
WHERE tenant_id = $1 AND (created_at, id) < ($2, $3)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

`(created_at, id)` because `created_at` alone is not unique and will drop rows.
Offset is fine for bounded admin lists (departments, classes, plans).

---

## 7. Write integrity: idempotency, concurrency, transactions

### 7.1 Idempotency

Every unsafe endpoint accepts `Idempotency-Key`. Without it, a retried fee
payment on a flaky mobile connection charges twice.

```
POST /api/v1/finance/payments
Idempotency-Key: 7c9e6679-7425-40de-944b-e07fc1f90ae7

Redis SETNX idem:{tenant}:{key} → 24h
  miss → execute, store (status, body)
  hit  → replay the stored response, do not re-execute
```

Mandatory on: fee payments, receipt generation, exam submission, bulk imports,
payroll runs, book issue/return.

### 7.2 Concurrency — three real races

| Race | Scenario | Control |
|---|---|---|
| Lost update | Two teachers edit one exam | Optimistic: `version` column, bump on write, 409 on mismatch |
| Double-spend | Two librarians issue the last copy | Pessimistic: `SELECT … FOR UPDATE` on `book_copies` |
| Duplicate insert | Attendance submitted twice | DB unique constraint + `ON CONFLICT DO UPDATE` |

The database constraint is the only one that cannot be raced — prefer it.
`database.sql` already carries the unique keys (e.g.
`uq_attendance_sessions`, `(slot_id, date)` on substitutions, `(exam_id,
student_id)` on attempts); the service should **rely on them** rather than
pre-checking with a `SELECT`, which is itself a race.

### 7.3 Transaction boundaries

The **service** opens the transaction; repositories join it. Keep them short —
a transaction held open across an S3 upload or an email send pins a connection
for seconds.

```typescript
// WRONG — the PDF and the email are inside the transaction
await this.prisma.$transaction(async (tx) => {
  const receipt = await tx.feePayment.create({ data });
  await this.pdf.generate(receipt);      // ~2s, holds the connection
  await this.mail.send(receipt);         // external, can hang
});

// RIGHT — commit, then queue the slow work
const receipt = await this.prisma.$transaction((tx) => tx.feePayment.create({ data }));
await this.queue.add('receipt.generate', { receiptId: receipt.id });
```

---

## 8. Async work: queues, jobs and the outbox

### 8.1 Queues

| Queue | Jobs | Concurrency | Retry |
|---|---|---|---|
| `mail` | Notices, receipts, reset links | 20 | 5 × exponential |
| `push` | FCM fan-out | 20 | 3 |
| `documents` | Grade cards, receipts, exports | 4 | 3 |
| `imports` | CSV student/staff/question import | 2 | none — report failures per row |
| `reports` | Heavy analytics | 2 | 2 |
| `scheduled` | Overdue fines, attendance alerts | 1 | 3 |

Every job carries `tenantId` and `requestId` so a queued failure is traceable
to the request that caused it.

### 8.2 The outbox pattern

Notifications must not be lost when the DB commits but Redis is down, and must
not fire when the transaction rolls back. Write the intent **in the same
transaction** as the business change:

```typescript
await this.prisma.$transaction(async (tx) => {
  const notice = await tx.notice.create({ data });
  await tx.outbox.create({
    data: { topic: 'notice.published', payload: { noticeId: notice.id }, tenantId },
  });
});
// A relay polls outbox WHERE published_at IS NULL and pushes to BullMQ.
```

This is the one addition to the schema this document recommends: an `outbox`
table (`id, tenant_id, topic, payload jsonb, created_at, published_at,
attempts`). Without it, "notice created but nobody notified" is a silent,
unreproducible bug class.

### 8.3 Scheduled jobs

| Job | Cadence | Note |
|---|---|---|
| Overdue library fines | daily 00:15 IST | Idempotent — recompute, don't increment |
| Attendance shortfall alerts | daily 19:00 IST | Batched per parent, not per subject |
| Trial expiry sweep | hourly | Drives the Sales console |
| Session cleanup | hourly | Expired `user_sessions` |
| Outbox relay | every 5 s | Plus a nightly sweep for stuck rows |

**Run schedulers on a single leader**, elected with a Redis lock. Three ECS
tasks each running the fine job triples the fines.

---

## 9. Caching & invalidation

| Data | Key | TTL | Invalidation |
|---|---|---|---|
| Tenant by slug | `tenant:{slug}` | 300 s | On tenant update |
| Enabled modules | `modules:{tenantId}` | 900 s | On `tenant_modules` write — **publish** |
| Permissions | `perm:{tenantId}:{userId}` | 900 s | On role change — **publish** |
| Session | `session:{jti}` | = refresh TTL | On logout / revoke |
| Dashboard aggregates | `dash:{tenantId}:{role}:{userId}` | 60 s | TTL only |

**Cache the tenant's *state*, not just its row.** `is_active` (§4.2) and
`subscriptions.status` (§4.4) are independent, and suspension must win. Cache
the derived verdict so 60 endpoints don't each re-derive it — and bust it on
either input changing.

Two rules that prevent the classic multi-tenant cache bug:

1. **Every key starts with `{tenantId}`.** A key without it will eventually
   serve one institution's data to another.
2. **Never cache a permission decision longer than you can tolerate a stale
   grant.** 15 minutes for reads; zero for anything destructive — re-check.

---

## 10. Real-time layer

Socket.IO, used by two features only: live exam monitoring (C-EC-05) and the
notification bell.

```
Rooms:  tenant:{tenantId}                broadcast
        tenant:{tenantId}:user:{userId}  personal
        tenant:{tenantId}:exam:{examId}  proctoring
```

- **Authenticate on connect**, not on message. An unauthenticated socket must
  never be allowed to join a room.
- **Room names are tenant-prefixed** — the same `examId` guess from another
  tenant lands in a different room.
- **Redis adapter** so any ECS task can reach a socket held by another.
- **Fall back to polling.** WebSocket is an optimisation; the monitor page must
  still work behind a proxy that blocks upgrades. The UI already renders from
  a server fetch, so this is a 15-second poll, not a rewrite.

---

## 11. File storage

Uploads never pass through the API — presigned PUT direct to S3:

```
1. POST /uploads/sign  { filename, contentType, size, purpose }
   → validate: extension allowlist, size cap, quota for tenant's plan
   → key: tenants/{tenantId}/{module}/{yyyy}/{mm}/{uuid}-{slug}.{ext}
2. Client PUTs to the presigned URL (300 s expiry)
3. POST /uploads/confirm { key } → row written, ClamAV scan queued
```

**Downloads are presigned GET, 60 s, issued only after the same ScopeGuard
check as the parent record.** The bucket is private with no public policy —
a leaked key is useless once the URL expires. Never serve a file by proxying
it through the API: it pins a Node process for the length of the transfer.

The tenant prefix in the key means an S3 lifecycle rule or a bulk delete for
one institution is a prefix operation, and it makes accidental cross-tenant
reads visible in access logs.

---

## 12. Failure modes & degradation

The system must not go dark because one dependency does.

| Dependency | On failure | Degraded behaviour |
|---|---|---|
| **Redis** | Cache miss → DB | Works, slower. Sessions fall back to JWT-only (accept short-lived staleness on revocation) |
| **S3** | Uploads fail | Reads still work; queue retries the confirm |
| **SES** | Mail queued | Retried 5×, then dead-letter + alert |
| **FCM** | Push dropped | In-app notification row still written — the bell works |
| **Read replica** | Route to primary | Higher primary load, correct data |
| **Primary DB** | Hard fail | 503 with `Retry-After`; health check pulls the task |

**Circuit breakers** on SES, FCM and S3: after 5 consecutive failures, open for
30 s and fail fast. Without one, a hanging third party consumes every worker
and takes the API down with it.

**Timeouts everywhere.** Node's default is *no timeout* — one hung request can
hold a connection forever.

```
HTTP client → external      5 s
DB query                   10 s   (statement_timeout)
Request end-to-end         30 s   (interceptor)
Job execution             300 s   (BullMQ)
```

**Graceful shutdown**, or every deploy drops in-flight work:

```typescript
app.enableShutdownHooks();
// SIGTERM → stop accepting, drain ALB (30s), finish in-flight,
// close BullMQ workers (let current jobs finish), disconnect Prisma, exit.
```

---

## 13. Observability

Three signals, all carrying `requestId` and `tenantId`.

**Structured logs** — JSON, never string-concatenated:

```json
{ "level":"info","ts":"2026-08-01T10:14:22Z","requestId":"01J...","tenantId":"...",
  "userId":"...","route":"POST /attendance/sessions","status":201,"ms":84,"queries":6 }
```

Never log: passwords, JWTs, reset tokens, PAN/bank/PF, exam answer keys.
Enforce with a serializer allowlist, not developer discipline.

**Metrics** (Prometheus → CloudWatch): request rate/latency/error by route,
p95 DB query time, pool utilisation, queue depth and job age, cache hit ratio,
**and per-tenant request volume** — one institution's bulk import should not
be invisible when it degrades everyone else.

**Traces** (OpenTelemetry): HTTP → guard → service → query → external call. The
question a trace must answer is *"why was this one request 4 s?"*, which logs
alone cannot.

**Alerts that page** (everything else is a dashboard):

| Condition | Threshold |
|---|---|
| 5xx rate | > 1% for 5 min |
| p95 latency | > 2 s for 10 min |
| DB pool saturation | > 80% for 5 min |
| Queue age | oldest job > 15 min |
| Replica lag | > 30 s |
| Disk | > 80% |

---

## 14. Security controls

**Auth.** Access token 15 min, refresh 7 days, rotated on use with reuse
detection — a replayed refresh token revokes the whole family. Store the
refresh token hashed. bcrypt cost 12.

**Rate limits** (per tenant *and* per IP — a shared school NAT is one IP):

| Endpoint | Limit |
|---|---|
| `POST /auth/login` | 5 / 15 min / account, then lockout |
| `POST /auth/forgot-password` | 3 / hour / account |
| Mutations | 100 / min / user |
| Reads | 1000 / min / user |
| Bulk import | 5 / hour / tenant |

**Input.** `class-validator` with `whitelist: true, forbidNonWhitelisted: true`
— strip unknown keys so a client cannot set `role` by adding it to a body.
Parameterised queries only; `$queryRaw` requires review and must include
`tenant_id`.

**Headers.** HSTS, CSP, `X-Content-Type-Options`, `Referrer-Policy:
strict-origin-when-cross-origin`. The reset-password page also sets
`robots: noindex` — a reset link must never be indexed or leak via referrer.

**Audit.** `audit_logs` gets every mutation: who, what, before, after, IP, and
`impersonatedBy` when set. Written via the outbox so an audit failure cannot
roll back the business change, and so it cannot be silently skipped.

**Secrets.** AWS Secrets Manager, rotated quarterly; JWT signing key rotated
with an overlap window so live tokens stay valid. Nothing in `.env` in prod.

---

## 15. Deployment & release safety

**Pipeline:** lint + typecheck → unit → integration (ephemeral Postgres) →
build → migrate → deploy → smoke → auto-rollback on health-check failure.

**Migrations must be backward compatible**, because during a rolling deploy old
and new code run against one schema. The expand/contract sequence:

```
Release N     add nullable column; write to both; read from old
Release N+1   backfill; read from new
Release N+2   drop the old column
```

A destructive migration in the same release as the code that needs it will
fail mid-deploy with half the tasks on each version.

Two specific traps for this schema:

- **`CREATE INDEX` locks writes.** Use `CREATE INDEX CONCURRENTLY` — it cannot
  run inside a transaction, so it needs its own migration step.
- **Adding an enum value** cannot run in a transaction on PostgreSQL < 12 and
  cannot be removed at all. Prefer a lookup table for anything likely to churn.

**Blue/green** on ECS with an ALB target-group swap; keep the old task set for
30 minutes for instant rollback.

---

## 16. Capacity model

Per institution (mid-size college, 2,000 students, 150 staff):

| Metric | Estimate |
|---|---|
| Peak concurrent users | ~400 (exam window) |
| Sustained rps | 40–60 |
| Peak rps (online exam) | 250 |
| DB rows/year | ~4M (attendance dominates: 2000 × 6 × 200 = 2.4M) |
| Storage/year | ~50 GB (content + submissions) |

**Peaks are synchronised and that is the whole problem.** Attendance at 09:00,
exam submission at the end of the slot, results the hour after publication —
600 students clicking submit in the same 60 seconds is 10× the mean.

Mitigations: queue the write-heavy paths (submission accepts, then grades
async), cache dashboards for 60 s, autoscale on p95 latency rather than CPU
(Node saturates on event-loop lag long before CPU), and pre-warm before a
scheduled exam.

**Partition `attendance_records` by year** once it passes ~10M rows. It is
append-only and always queried by date range — the ideal candidate.

---

## 17. Backup & disaster recovery

| Control | Setting |
|---|---|
| Automated snapshots | Daily, 30-day retention |
| PITR | 7 days (5-minute granularity) |
| Cross-region copy | Weekly |
| S3 | Versioning + 90-day lifecycle to Glacier |
| **RPO** | **5 minutes** |
| **RTO** | **1 hour** |

**Restores are tested quarterly.** An untested backup is a hope. The drill:
restore into a scratch account, run `database.sql`'s verification block, and
confirm 106 tables and referential integrity.

**Single-tenant restore** is the common real case ("we deleted a department").
PITR restores the *whole* cluster, so the procedure is: restore to a temporary
instance, `pg_dump` that tenant's rows in FK order, load into production. Keep
the script written and tested — improvising it during an incident is how a
one-tenant problem becomes an all-tenant outage.

---

## 18. Environments & configuration

| Env | Purpose | Data |
|---|---|---|
| local | Docker Compose: Postgres, Redis, MinIO, MailHog | Seeded |
| ci | Ephemeral per PR | Fixtures |
| staging | Prod mirror, smaller | Anonymised copy |
| production | Live | Real |

Config is environment variables only, validated at boot with a Zod schema so a
missing `JWT_SECRET` fails at startup rather than at the first login. No
config file is read at runtime; no secret has a default.

**Staging data must be anonymised.** Names, emails, phone numbers and PAN/bank
fields are scrubbed on copy. A staging database with real student records is a
breach waiting for the first contractor login.

---

## Appendix — verification commands

```bash
# Schema loads clean (verified on PostgreSQL 17.10)
createdb erp_lms && psql -d erp_lms -v ON_ERROR_STOP=1 -f database.sql
#   Tables: 106 · Enums: 54 · FKs: 283 · Unindexed FKs: 0

# Tenant-scoped model count must match the extension's guard
node -e "const {Prisma}=require('@prisma/client');
  console.log(Prisma.dmmf.datamodel.models.filter(m=>
    m.fields.some(f=>f.name==='tenantId')).length)"   # expect 81

# Tables with NO tenant_id (expect 25 = 18 child + 7 global-by-design)
psql -d erp_lms -tAc "
  SELECT table_name FROM information_schema.tables t
   WHERE table_schema='public' AND table_type='BASE TABLE'
     AND NOT EXISTS (SELECT 1 FROM information_schema.columns c
                      WHERE c.table_name=t.table_name AND c.column_name='tenant_id')
   ORDER BY 1;"

# The 18 that matter (§2.2): no tenant column AND a parent FK, so every query
# MUST join the parent. This is the list to drive the lint rule from.
psql -d erp_lms -tAc "
  SELECT t.table_name
    FROM information_schema.tables t
   WHERE t.table_schema='public' AND t.table_type='BASE TABLE'
     AND t.table_name NOT IN ('plans','platform_users','tenants','modules',
                              'roles','permissions','user_sessions')
     AND NOT EXISTS (SELECT 1 FROM information_schema.columns c
                      WHERE c.table_name=t.table_name AND c.column_name='tenant_id')
   ORDER BY 1;"                                        # expect 18
```

> All three commands were run against a live PostgreSQL 17.10 instance while
> writing this document. The counts above are observed, not estimated.

---

*Architecture v1.0 · companion to `developer_system_design_deployment.md` ·
verified against `database.sql` (106 tables, PostgreSQL 17.10)*
