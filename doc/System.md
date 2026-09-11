# ERP + LMS — Parent–Student Connected Access (`System.md`)

Everything the **guardian (parent) portal** is on this platform: the data model that connects an
adult to a student, the module scope that decides what that adult may open, the 23 authenticated
endpoints behind it, the public activation flow, the web console, the mobile console, the office
board that grants and revokes access, and how all of it is tested and operated.

It is written as a system document, not a tutorial: each section states the rule, where it is
enforced, and why it is that way — so that a change to any of it can be checked against the
consequence rather than against a description of a screenshot.

For the opposite audience — a parent with an activation slip, or an office clerk linking a family —
that is `PARENT-PORTAL-USER-GUIDE.md`, which covers the same surface without a single endpoint in it.

| Concern | Lives in |
| --- | --- |
| Tables, constraints, indexes | `database/database.sql` (§6.7 `parent_student_links`), delta in `database/update_parent_portal.sql` |
| ORM model + the two gates (`is_live`, `allows`) | `backend/app/models/parent.py` |
| Request/response shapes | `backend/app/schemas/parent.py` |
| Guardian read paths + family rollup | `backend/app/services/parent_service.py` → `ParentService` |
| Code issuing, claiming, the office board | `backend/app/services/parent_service.py` → `ParentLinkService` |
| Routes | `backend/app/routers/parent.py`, `backend/app/routers/institution/links.py` |
| Web console | `fontend/lib/parent.ts`, `fontend/components/parent/*`, `fontend/app/parent/**` |
| Web activation (public) | `fontend/app/(auth)/guardian-access/page.tsx`, `fontend/components/auth/guardian-access-form.tsx` |
| Web office board (C-IA-12) | `fontend/components/structure/parent-links.tsx`, `fontend/app/admin/guardian-links/page.tsx` |
| Mobile console | `app/src/lib/parent.ts`, `app/src/lib/parent-console.tsx`, `app/src/components/parent-*.tsx`, `app/src/app/(parent)/**` |
| Mobile activation (public) | `app/src/app/guardian-access.tsx` |
| Tests | `backend/tests/test_parent_console.py` (29), `backend/tests/test_parent_portal_integration.py` (19) |

---

## 1. The model in one paragraph

A guardian is **not** a user of the student's account. A `parent_student_links` row joins one
`users` row with role `PARENT` to one `users` row with role `STUDENT`, and that row carries the
relation, whether this adult is the *primary* contact, which **modules** of the child's record may
be opened, an optional **end date**, a **status**, and — before the family has claimed it — a
one-time **activation code**. Every per-child request is resolved through that row on the server,
each time. Nothing about a guardian's permissions is cached in a token, so a school narrowing a
father's access from `attendance, results` to `attendance` takes effect on the guardian's next
request, not on their next login.

Because the grant is per **link**, the same adult can hold different rights for two children, and
two adults for the same child can hold different rights — which is the actual shape of the families
a school has to serve (a court order naming one parent, a grandparent who only follows attendance).

```
users (PARENT) ──┐                      ┌── users (STUDENT)
                 │  parent_student_links│        │
                 └── parent_id ────────┤        └── enrollments → school_classes
                    student_id ────────┘             (the "current class" the card prints)
                    relation · is_primary · status
                    access_scope[] · access_upto
                    activation_code · code_expires_at · claimed_at
                    managed_by · note
```

### 1.1 Columns

`parent_student_links` (the ten columns added for this feature are marked ◆; the rest pre-existed):

| Column | Type | Meaning |
| --- | --- | --- |
| `tenant_id` | UUID | every query is tenant-scoped; there is no cross-tenant parent |
| `parent_id` ◆ | UUID → users, nullable | `NULL` until the family claims the code — a pending row has nobody to authorise |
| `student_id` | UUID → users | the child |
| `relation` | VARCHAR(50) | `Father`, `Mother`, `Guardian`, … Free text, printed as entered |
| `is_primary` | BOOLEAN | exactly one active primary per student (`uq_parent_student_links_primary_active`); it decides who receives attendance alerts and fee reminders |
| `status` ◆ | VARCHAR(20) | `PENDING_CLAIM` · `ACTIVE` · `SUSPENDED` (CHECK-constrained) |
| `parent_email` ◆ | VARCHAR(255) | the invited address, kept on the row while pending so the office can see who is being waited for |
| `access_scope` ◆ | TEXT[] | the modules granted; **not null, default the tenant's set** — see §2 |
| `access_upto` ◆ | DATE | inclusive last day of access, evaluated on the *tenant's* calendar |
| `activation_code` ◆ | VARCHAR(24) | the claim capability; **cleared on claim**, so it cannot be replayed or read back |
| `code_expires_at` ◆ | TIMESTAMPTZ | 14 days by default (`CODE_VALID_DAYS`) |
| `claimed_at` ◆ | TIMESTAMPTZ | when the family redeemed it |
| `managed_by` ◆ | UUID → users | which staff member created/edited the grant; shown on the office board |
| `note` ◆ | TEXT | office-only remarks (access orders, custody notes) |
| `updated_at` ◆ | TIMESTAMPTZ | `onupdate=now()`, and the reason for `eager_defaults=True` on the model |

`attendance_leaves` gained the two columns that make "a parent applied for leave" a real record:

| Column | Type | Meaning |
| --- | --- | --- |
| `requested_by` ◆ | UUID → users, nullable | whoever filed it — the student, or the guardian acting for them |
| `request_source` ◆ | VARCHAR(20) default `STUDENT` | `STUDENT` · `PARENT`; CHECK-constrained, and what the teacher's list reads to say "by parent" |

### 1.2 Indexes and constraints

Six indexes support the paths this feature actually walks, and three of them are the rules:

| Name | Enforces |
| --- | --- |
| `uq_parent_student_links_activation_code` (unique, partial on `status = 'PENDING_CLAIM'`) | no two live codes collide; used codes leave the index, so history is kept |
| `uq_parent_student_links_primary_active` (unique, partial on `is_primary AND status = 'ACTIVE'`) | one primary contact per student — the *service* demotes the previous primary in the same flush rather than letting the insert fail, so "promote this parent" is one click |
| `uq_parent_student_links_pending_email_student` (unique, partial, pending) | the office cannot send a family two slips for the same child |
| `idx_parent_student_links_parent_active` | the portal's entry query: this guardian's links |
| `idx_parent_student_links_pending_email` | reissue-by-address |
| `idx_parent_student_links_managed_by`, `idx_attendance_leaves_requested_by` | audit lookups; both also satisfy the schema's "every FK column has a leading index" rule |

Three CHECK constraints (`ck_parent_student_links_status`, `_guardian`, `_activation`,
`ck_attendance_leaves_request_source`) keep the database honest about states the application
considers invalid, independently of which client wrote the row.

### 1.3 Migrating

An existing installation applies the delta only:

```bash
psql "$DATABASE_URL" -f database/update_parent_portal.sql
```

It is idempotent (`IF NOT EXISTS`, guarded `ALTER … ADD CONSTRAINT`), backfills `status` for rows
that predate the feature, and ends with assertions that fail loudly if the expected shapes are
absent. A new installation gets the same schema from `database/database.sql`, which now contains
these columns inline (132 tables, verified by the trailing `$do$` block).

`parent_student_links` is also removed from `_UNMANAGED_TABLES` in `backend/app/alembic/env.py`. That
list exists so autogenerate does not emit `DROP TABLE` for tables that exist only in raw SQL; this
table now has an ORM model, so leaving it listed would hide its columns and indexes from every future
drift check — the file's own comment is "remove entries here as ORM models are added".

No scheduled job is needed for expiry, and none was added: an unclaimed code is refused at lookup
(`410` past `code_expires_at`) and a lapsed `access_upto` is decided by `is_live()` on the day the
request arrives, so a school suspending access at 6pm does not wait for a cron tick. The only
dependency this feature surfaced is a **correctness fix in `backend/requirements.txt`**: it now pins
`apscheduler==3.11.0`, which `app/main.py` imports for the pre-existing background jobs (retention
sweep, outbox drain, daily reminders) and which was previously missing, so a fresh install failed at
import time before any route — parent or otherwise — could be served.

---

## 2. `access_scope` — what the three states mean

The column is a `TEXT[]` and the seven modules are `PARENT_ACCESS_MODULES` in
`backend/app/models/parent.py`:

`attendance` · `timetable` · `examination` · `assignment` · `results` · `notice` · `finance`

There are **three** intentions to express and only two of them can be written in an array, so the
API uses the presence of the field:

| Sent by the office | Stored | Result |
| --- | --- | --- |
| field omitted / `null` | the tenant's default set (`DEFAULT_PARENT_ACCESS_SCOPE`, currently all seven) | "the school's normal policy for guardians" |
| `["attendance"]` | exactly that | one module |
| `[]` | rejected with 422 | *"a guardian link with no modules grants nothing — pick at least one, or leave it unset for the school default"* |

The distinction is the single most dangerous way this feature could fail: an earlier `payload.access_scope
or DEFAULT` read made a form submitted with every box unticked grant **full** access. `NULL` and empty are
now separate code paths, and the create and update services both say so.

Two consequences for the consoles:

* **`attendance` includes filing leave.** A guardian may read the child's attendance *and* submit a
  leave application on their behalf; the row records `request_source = 'PARENT'` and
  `requested_by = <guardian>`, and the teacher's list shows who asked. Half a conversation about an
  absence is worse than the whole thing.
* **`results` is separate from `examination`.** Dates and per-exam marks come from `examination`;
  a published term card comes from `results`. A school can therefore let a grandparent follow
  attendance and notices while the mark sheet stays with the parents.

The read paths for a child **are** the student's read paths: `ParentService` resolves the link, then
calls `StudentService` as the child. There is no second implementation of attendance or fees for
guardians to drift away from — the frontends likewise import the student types instead of
re-declaring them, and `ParentExamSummary` is the one genuinely new shape (see §4.3).

---

## 3. Enforcement

```
guardian request
  └─ get_current_tenant_user_parent        (backend/app/dependencies/auth.py)
       ├─ valid tenant JWT, live user, role PARENT assigned in this tenant   → else 401 / 403
       └─ ParentService.link(db, parent, child_id, module="…")
            ├─ ACTIVE link row joining this caller to that child in this tenant → else 404
            ├─ status != SUSPENDED                                              → else 403 "paused by the school"
            ├─ link_row.is_live(tenant's today)                                 → else 403 "no longer active"
            └─ module is None or link_row.allows(module)                        → else 403 "not granted … for this student"
```

* **404, not 403, for a child you are not linked to.** An "exists but forbidden" answer tells a
  caller which student ids are real; a 404 for both "not linked" and "no such student" does not.
* **Expiry is evaluated on the tenant's calendar day** (`PrincipalService._tenant_today`), so a
  guardian whose access ends on the 31st does not lose it at midnight UTC.
* **The link is re-read on every request.** Client-side gating is presentation only: hiding a tab
  keeps a family from poking at a locked door, and the 403 is what protects the student. Neither
  `fontend/lib/parent.ts` nor `app/src/lib/parent.ts` has an `isFinanceVisible`-style helper, on
  purpose — one would invite someone to trust it.
* **Suspended and expired links stay listed.** `GET /parent/children` returns them with
  `is_live = false` and `blocked_reason`, so a family can see the record exists and why it is
  closed, instead of finding it silently missing. The per-child data endpoints still 403.
* **Institution admins** go through `get_current_tenant_user_admin`; the board refuses to *create*
  a link for a `COLLEGE` tenant (409) while leaving read and unlink available, so an institution
  that changes type can still clean up what it made.

### 3.1 The activation code

| Property | Value |
| --- | --- |
| Length | 12 characters (`_CODE_LENGTH`) |
| Alphabet | `0123456789ABCDEFGHJKMNPQRSTVWXYZ` — no `I L O U`, so a slip cannot be misread into a wrong code |
| Generated with | `secrets.choice` |
| Validity | `CODE_VALID_DAYS = 14` days, stored in `code_expires_at` |
| Storage | plaintext in `activation_code`, with a partial unique index over pending rows |
| Lifetime | written once, **cleared when the link is claimed**, replaced (never re-shown) by a reissue |
| Never in | a JWT, a URL query string, a log line, an exception message, or a list endpoint |

Plaintext is a deliberate trade, not an oversight: a code is worthless once redeemed, it is
short-lived, and the office genuinely needs to re-read a slip for a family sitting at the counter —
which a hash would make impossible while providing little against the real threat (someone with
database read access also has the students). The blast radius is bounded by the second factor below.
A school that wants hashes instead can swap `find_pending_code` for a lookup by `tenant_id + hash`
without touching any other rule in this document.

**The second factor.** The public `POST /parent/access/activate` requires the code **and** the
child's roll number from the same slip (`student_roll_no`, compared case-insensitively against
`users.student_roll_no` or the current enrolment's roll number). A guessed or leaked code alone
yields a 422, not a record — which is what makes it acceptable for the code to travel by email and
sit on paper for two weeks.

**Rate limits** are enforced by slowapi on the router, per client:
`GET /access/check-code` **20/hour**, `POST /access/activate` **8/hour**. Both are exercised by the
integration suite against the real limiter (21 attempts ⇒ 20 lookups that miss, then 429).
Both frontends state the limit to the user rather than inventing a lockout counter of their own.

---

## 4. Backend API

### 4.1 Guardian routes — `/api/v1/parent` (23)

All require `get_current_tenant_user_parent`; all per-child routes take `child_id` = **student** id
and are fenced as in §3. Envelope `{ success, data, message }`, snake_case throughout.

| Route | Module gate | Notes |
| --- | --- | --- |
| `GET /access/check-code?code=` | *public* | Preview of whose invitation it is; 404 unknown, 410 expired. Returns school, student, class, relation, `is_primary`, expiry — nothing else |
| `POST /access/activate` | *public* | Creates the guardian account **and** claims the link: `{code, student_roll_no, name, email, password, phone?}` → 201 `{slug, institution_name, email, student_name}`. **Returns no token**: the family signs in through the ordinary tenant login, so lockout and session records apply to this identity like any other |
| `GET /children` | — | family: each child with relation, class, scope, `days_left`, `is_live`, `blocked_reason`; plus `pending_invites` and `portal_enabled` |
| `POST /children/claim` | — | attach a code to an existing account (a second child); rejects a duplicate family with 409 |
| `GET /overview` | — | one request per family: per-child rollup (attendance %, low flag, last mark, work due, next exam, fee balance, overdue flag, unread notices, `restricted_modules`) |
| `GET /guardian` / `PATCH /guardian` | — | the guardian's own record; only `phone` and `address` are writable, and a changed phone clears `phone_verified_at` |
| `GET /children/{id}/dashboard` | any | the child's `StudentDashboard` plus the link row and what is restricted |
| `GET /children/{id}/profile` | any | profile + who to call (class teacher, mentor, hostel room, transport route) |
| `GET /children/{id}/attendance` | `attendance` | summary + per-subject rows |
| `GET /children/{id}/attendance/calendar?month=YYYY-MM` | `attendance` | per-day, per-period entries |
| `GET /children/{id}/attendance/last` | `attendance` | "was my child at school today?" without downloading a month |
| `GET · POST /children/{id}/leaves`, `POST …/{leave_id}/cancel` | `attendance` | file on the child's behalf; cancel only while `PENDING` **and** filed by this guardian (`mine`) |
| `GET /children/{id}/timetable` | `timetable` | the class routine |
| `GET /children/{id}/examinations?when=` | `examination` | the student's exam list |
| `GET /children/{id}/examinations/{exam_id}/result` | `examination` | `ParentExamSummary` — see below |
| `GET /children/{id}/assignments?status=` | `assignment` | read-only: no submit route exists for guardians |
| `GET /children/{id}/results`, `GET …/results/{publication_id}` | `results` | published cards only |
| `GET /children/{id}/notices?query=` | `notice` | the child's board; `is_read` is the **student's** and there is no guardian mark-read, so the flag cannot be falsified from a parent account |
| `GET /children/{id}/fees` | `finance` | balance, instalments, receipts, concessions, grants |

### 4.2 Office board — `/api/v1/institution/parent-links`

`GET` (page + counts + `unlinked`/`unlinked_count` + `tenant_type`), `POST` (three shapes: attach an
existing `parent_user_id`; invite an `email` behind a new code; `create_account` to make the login
now and mail a set-password link), `PATCH /{id}` (relation, primary, suspend/restore, scope,
expiry, note), `POST /{id}/code` (reissue), `DELETE /{id}`.
The activation code appears on **exactly the one response that minted it** and nowhere else.

### 4.3 Shapes worth knowing

* `ParentExamSummary` carries `total_score / percentage / grade / submitted_at / status /
  attempt_missing` and **no answers**. The student's own result endpoint unlocks per-exam
  (`allow_review`, `show_score_immediately`); reusing it for a guardian would let a parent read a
  half-marked script before the child does, so the parent route is its own type and its own
  decision — a known pre-existing test disagreement about that unlock (`test_exam_lifecycle_end_to_end`)
  is precisely why.
* `ParentLeaveRow` adds `request_source` and `mine` on top of the student's leave row. `mine` is
  what the cancel button checks: a child's own request is listed for context but not withdrawable
  by a guardian.
* Per-child reads reuse `StudentAttendanceSummary`, `StudentAttendanceCalendar`, `StudentTimetable`,
  `StudentExamRow`, `StudentAssignmentRow`, `StudentNoticeRow`, `StudentResultRow/Detail`,
  `StudentFeeAccount`. Both frontends re-export them from the parent module rather than declaring a
  second copy.

### 4.4 Audit and logging

Every state change is written through `AuditService.record` with entity `ParentStudentLink` (or
`AttendanceLeave`) and one of:

`CREATE_GUARDIAN_LINK` · `UPDATE_GUARDIAN_LINK` · `DELETE_GUARDIAN_LINK` · `ISSUE_GUARDIAN_CODE` ·
`CLAIM_GUARDIAN_LINK` · `UPDATE_GUARDIAN_PROFILE` · `APPLY_LEAVE_FOR_CHILD` · `CANCEL_LEAVE_FOR_CHILD`

`CLAIM_GUARDIAN_LINK` records `actor_role` as `PARENT` when the family did it and
`INSTITUTION_ADMIN` when the office did — "who removed this grandfather's access, and when" is the
first question in every dispute about a parent portal, and it is answered from the audit table, not
from an app log. Structured log lines go to the `erp.parent` logger with an `event` key
(`parent.link.claimed`, `parent.account.activated`, `parent.activation.rejected`,
`parent.leave.apply`, `parent.db.constraint_violation`, …); codes, emails and phone numbers never
appear in a log `extra`.

Two emails exist, both queued through the platform's outbox (`queue_email`) so a slow SMTP never
blocks a request: `parent.link_invited` (the code, its expiry, and a link to
`https://{slug}.{root}/guardian-access`) and `parent.account_created` (login URL). The claim link
deliberately carries **no `?code=`** — a query string ends up in browser history and in the access
log, and this one would carry the capability itself. Colleges are refused at the service layer
before any email is queued.

---

## 5. Web console (`fontend/`)

```
app/parent/layout.tsx                    Suspense → ParentConsoleProvider → ParentShell
app/parent/dashboard/page.tsx            family: rollup cards, pending invites, claim form
app/parent/child/page.tsx                today (periods, work due, notices, who to call)
app/parent/child/attendance/page.tsx     summary + per-subject + month calendar
app/parent/child/leave/page.tsx          list + file on behalf + withdraw
app/parent/child/timetable/page.tsx      weekly grid (the shared console component)
app/parent/child/results/page.tsx        exams (upcoming/completed/all) + published cards
app/parent/child/assignments/page.tsx    status tabs, read-only
app/parent/child/notices/page.tsx        the child's board
app/parent/child/fees/page.tsx           instalments, receipts, concessions
app/parent/guardian/page.tsx             own details + what the school shares + claim
(app)/(auth)/guardian-access/page.tsx    public activation — no console layout
app/admin/guardian-links/page.tsx        C-IA-12 office board
```

* `components/parent/parent-console-context.tsx` — the roster (`GET /children`) fetched **once**, the
  selected child, and `allows(module)`. The selection lives in `?child=` so any screen can be
  bookmarked or reloaded; the layout wraps the provider in `Suspense` because search params are read
  during prerender.
* `components/parent/parent-shell.tsx` — sidebar built from `PARENT_NAVIGATION`, each entry carrying
  the module it needs; entries the current child's link does not grant are not rendered. The header
  holds the child switcher (a `ChildSwitcher` component calling `useParentConsole().selectChild` —
  no module-level bridge state).
* `components/parent/parent-shared.tsx` — `ChildGate` renders the four arrival states **in order**
  (loading → error → no child → module denied), because getting that order wrong looks like a bug:
  an expired family shown an empty list rings the office about a blank screen.
* `components/parent/parent-family.tsx` degrades rather than blocking: if `/overview` fails, the
  cards still render from the roster with the links, since the links are the important half.
* `lib/parent.ts` is the only transport: `leadershipCall("parent", …)` (shared token attach, silent
  refresh, tenant guard) and `requestJson(…, null, …)` for the two public calls, with `refreshFn: null`
  so a 401 there cannot start a refresh loop that cannot win.
* The role gate reuses the shared console guard: `ProtectedInstitutionRole` now includes `"PARENT"`,
  with an **empty** `ROLE_NAV` entry — the parent console supplies its own navigation, so the role is
  listed to be *authenticated and scoped*, not to be offered an operator sidebar. `ROLE_MAP.PARENT`
  sends a signed-in guardian to `/parent/dashboard`.
* `lib/roles.ts` / `lib/student.ts` are unchanged in behaviour: the parent console imports the student
  types rather than shadowing them.
* No grade-card PDF download. `StudentService`'s grade-card route is the student's own; re-issuing
  the school's signed document from a guardian session needs its own policy decision, so the console
  tells the family to ask the office, and the office prints it from the student record.

**Verified:** `node_modules/.bin/tsc --noEmit` clean and `npm run build` succeeds — all ten `/parent/**`
routes prerender as static, `/guardian-access` renders dynamically (it reads headers), and
`/admin/guardian-links` is static. ESLint reports 0 errors / 0 warnings on every file in §5.

---

## 6. Office board UI

`components/structure/parent-links.tsx` was previously a mock that announced "API not connected
yet"; it is now the real board on `/api/v1/institution/parent-links`, reached from **Admin →
Guardians**.

* Status and relation filters, a search box, and a counts strip (links / waiting to claim / active /
  suspended) taken from the same response.
* **Students with no guardian at all** is answered by the database (`unlinked_count`), with the first
  20 listed and the total named — the gap the page exists to close.
* A warning line for students whose parents are linked but with **no active primary**, because then
  alerts have no single recipient.
* A college tenant gets the reason the button is absent, not an empty table.
* The create dialog states the two invite modes (code vs create-login-now), the "one student, one
  link per guardian" 409 that comes back from the server verbatim, and a module picker that lists
  each module's hint plus the refusal of an empty selection.
* Editing a row cannot swap the guardian: *who* is linked is immutable, because the link is the grant
  **to that person**; the office unlinks and creates, which is also the only path that writes an
  honest audit trail.
* The activation code renders in a one-time dialog with a copy button and the sentence *"it is not
  shown again after this dialog closes — reissue a new one rather than hunting for this one."*
* The board asks for 200 rows and says so when `total` is larger, instead of pretending to page.

---

## 7. Mobile console (`app/`)

Expo Router, mirroring the web console's rules with the app's own primitives — no screen in the app
re-implements a fetch or a gate that `lib/` already owns.

```
src/app/(parent)/_layout.tsx     role gate → ParentConsoleProvider → header + Stack + drawer
src/app/(parent)/dashboard.tsx   family rollups, pending invites, claim
                                today / attendance / leave / timetable / exams / results /
                                assignments / notices / fees / me
src/app/guardian-access.tsx      public activation (outside the group, like /login)
src/lib/parent.ts                ported from the web lib — same endpoints, same types
src/lib/parent-console.tsx       roster + selected child + allows(module)
src/components/parent-shell.tsx  header with child sheet, module-filtered drawer
src/components/parent-ui.tsx     ChildGate, AccessNotice, ModuleDenied, FactRow, DataRow, Chip
src/components/parent-claim.tsx  the claim form, shared by dashboard and "me"
```

* **Gating.** `(parent)/_layout.tsx` bounces anyone without role `PARENT` to `/login`; the per-child
  screens call `ChildGate`, which shows loading → error → "no child linked" → `ModuleDenied` in that
  order, then an `AccessNotice` banner when the link is closed or has ≤ 30 days left. `consoleHref`
  in `src/lib/roles.ts` prefers teacher → student → guardian, so an account holding both a student
  record and a parent link reads its own data first.
* **Selected child** lives in `ParentConsoleProvider` (no URL params on the phone) and is persisted
  under `erp_parent_child` in `expo-secure-store`, the store the app already uses for its session — a
  guardian with two children at two schools should land on the child they last opened, and a child
  since unlinked is not silently kept as the selection. The header's child sheet lists non-live links
  greyed with their reason.
* **Activation** needs no slug field: the backend derives the tenant from the code, and the
  response's `slug` is written into `setInstitutionSlug`, so `Sign in` after activation is one tap.
  The roll-number second factor, the 10-character password floor (`GUARDIAN_MIN_PASSWORD`, stricter
  than the staff invite's 6) and the API's own 429 message are all surfaced in the form.
* **Parity, deliberately imperfect.** The web attendance screen's month grid became a tappable day
  grid in RN (same data, `attendance/calendar`), the timetable reuses the app's
  `components/weekly-grid.tsx` — whose slot mapping is now the shared `timetableSlots()` helper used
  by the student screen too, rather than a second copy — and the fee table became stacked rows with
  `₹` via `inr()` from `lib/format.ts`.

**Verified:** `tsc --noEmit` clean, also with `--noUnusedLocals --noUnusedParameters` for the parent
sources.

---

## 8. Front-to-back walkthroughs

**A family that has never logged in.** Office creates the link with an email → row is
`PENDING_CLAIM`, `parent_id` `NULL`, code minted, email queued. Guardian opens
`/{slug}.shikshasync.me/guardian-access`, types code + roll number, optionally *Checks the invitation*
(which prints only the child, class, relation and expiry), sets a password ≥ 10, submits.
`activate_with_code` locks the row (`SELECT … FOR UPDATE`, so two guardians with one slip cannot both
win), refuses a mismatched roll (422) or an existing email (409 with "sign in and claim the code from
your profile"), creates the `User` with role `PARENT` (`email_verified_at` stays `NULL` — the claimer
proved they can read the admission slip, not the mailbox), attaches and clears the code, records
`CLAIM_GUARDIAN_LINK`, and returns **no token**. They sign in, and `/parent/dashboard` opens.

**A second child at the same school.** Office issues another code for the sibling. Signed-in
guardian enters it at **My details** → `POST /children/claim` → the existing account gains a link,
and no second login is created. If they *were* already linked to that child: 409
"already linked to your account".

**The separated parents.** Mother: scope `attendance, notice`. Father: scope `attendance,
timetable, notice, examination, assignment, results, finance` — the finance module is where the
order says otherwise, and both are the same child. Each console shows only what its own row grants,
and the office can see both rows side by side with who set them (`managed_by_name`).

**A dispute in March.** Office suspends the link. The guardian's next request 403s
("paused by the school"); the dashboard still lists the child with `blocked_reason: SUSPENDED`, and
`DELETE`/re-suspend are audited. Nothing in the JWT changed, nothing needs re-logging-in.

**A leave filed by a grandmother.** Allowed — `attendance` is granted. The teacher's leave list shows
`by parent` from `request_source`, the row's `requested_by` is the grandmother, the student's own list
shows the same request, and only the guardian who filed it may withdraw it while `PENDING`.

---

## 9. Testing

```bash
cd backend
/home/user/venv/bin/python -m pytest tests/test_parent_console.py tests/test_parent_portal_integration.py -q
# 48 passed
```

* `test_parent_console.py` (29) — the units at the seam: `is_live`/`allows` truth tables including
  the tenant-day boundary; `access_scope` `null` vs `[]` vs a subset; every parent response schema's
  field set against its model (so an endpoint cannot quietly leak a field); leave `mine`/
  `request_source`; the code alphabet, length, normalisation and expiry; the 404-vs-403 rule; the
  claim and duplicate-family guards; `ParentExamSummary` carrying no answers; the demote-before-flush
  primary rule; the constraint-violation mapper's fallbacks.
* `test_parent_portal_integration.py` (19) — HTTP against an embedded Postgres: the whole activation
  flow, claim-by-existing-account, the real slowapi limits, reissue invalidating the old code
  (old 404 / new 200 / outbox body / `ISSUE_GUARDIAN_CODE` audit row), suspended and expired links,
  per-module 403s on every route, the college 409, cross-tenant isolation, and profile edits clearing
  `phone_verified_at`.
* Frontends: `tsc --noEmit` + ESLint (web), `tsc --noEmit` with the unused-locals flags (app), and a
  full `next build` for the routing layer.

Repo-wide the backend suite is **390 passed / 15 failed**. Those 15 are the pre-existing failures
recorded before this feature — `test_vice_principal_console.py` (4), `test_coordinator_console.py`
(3), `test_signup_flow.py` (3), `test_teacher_student_integration.py` (2, one of them the
exam-result unlock of §4.3), `test_online_class_integration.py` (1), `test_platform_admin.py` (1),
`test_principal_console.py` (1). None is in a parent path, and none was papered over or rewritten to
make this feature look green.

---

## 10. Known gaps and non-goals

| Gap | Why it is like this |
| --- | --- |
| No guardian download of the signed grade-card PDF | The student's own route issues it; a guardian copy needs its own policy on who may hold the school's document |
| Guardians cannot submit assignments | Submitting is the child's act; the list is read-only by design, and the UI says so instead of showing a dead button |
| No guardian mark-as-read on notices | `is_read` measures whether the *student* looked; a guardian ticking it would falsify a number the school uses |
| No in-app messaging to the class teacher | There is no parent↔teacher thread in this platform's schema; `GET /children/{id}/profile` answers "who do I call" instead |
| No fee payment | A webview payment link that leaves the balance unchanged is a reconciliation problem nobody can see; the screen names the office path instead |
| One family per tenant | `parent_id` is per-tenant by design: a guardian with children in two schools has two accounts, because the schools must not share a login. Cross-tenant guardian identity is a platform decision, not a portal feature |
| Codes are stored plainly | See §3.1 — re-readability at the counter vs an unrecoverable slip; bounded by the roll-number factor, expiry, rate limits and clearing on claim |
| No push notifications for guardians | The outbox is email-only today; the absence-alert hooks that would carry it live in `attendance`, which a guardian's link may not even include |

If any of these is taken up, the change belongs in the same three places this feature touched: the
service (rule), the router/schema (contract), and both consoles' gate (presentation) — never in the
client alone.
