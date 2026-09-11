# System Flow — Lead → Purchase → Onboard → Daily Operation

> **What this covers.** The complete lifecycle of an institution on the
> platform: how it is created, how it *pays*, what happens on the first login,
> how the Institution Admin buys and configures everything, and what happens
> when payment fails.
>
> **Sources.** `role_based_system_design.md` §7 (module activation),
> `complete_webpage_developer_assignment.md` §2 (platform pages),
> `database_design_complete.md` §4 (platform layer), and `database.sql`
> (106 tables, verified on PostgreSQL 17.10).
>
> **Three gaps in the current spec are flagged inline** — the billing tables
> for C-FM-02/03 do not exist, plan limits are not enforced anywhere, and
> there is no self-service signup. Section 9 specifies what to add.

---

## Contents

1. [The two doors: who creates an institution](#1-the-two-doors-who-creates-an-institution)
2. [Stage 1 — Lead and trial](#2-stage-1--lead-and-trial)
3. [Stage 2 — Purchase: what "buying" actually is](#3-stage-2--purchase-what-buying-actually-is)
4. [Stage 3 — First login and the onboarding wizard](#4-stage-3--first-login-and-the-onboarding-wizard)
5. [Stage 4 — Buying modules (the toggle is a purchase)](#5-stage-4--buying-modules-the-toggle-is-a-purchase)
6. [Stage 5 — Filling the institution](#6-stage-5--filling-the-institution)
7. [Stage 6 — Steady state and renewal](#7-stage-6--steady-state-and-renewal)
8. [Failure paths](#8-failure-paths)
9. [🔴 Missing: the billing tables](#9--missing-the-billing-tables)
10. [End-to-end sequence](#10-end-to-end-sequence)

---

## 1. The two doors: who creates an institution

The public entry point is now owner-first, like AWS, Shopify or Zoho. The
account at `shikshasync.me` belongs to the owner, not to one institution. One owner
can create and manage many tenants from the platform dashboard.

```
Visit shikshasync.me
  │
  ▼  Sign Up (Owner name, email, password)
  │
  ▼  Verify Email
  │
  ▼  Platform Dashboard
  │
  ├── My Institutions
  ├── Billing
  ├── Subscriptions
  ├── Invoices
  ├── Support Tickets
  └── Profile
  │
  ▼  Create New Institution
  │
  ▼  Choose Plan
  │
  ▼  Choose Subdomain
  │
  ▼  Payment
  │
  ▼  Institution Created
  │
  ▼  Go To green.shikshasync.me
```

Example ownership model:

```
Owner: Rahul Sharma
Platform account: rahul@gmail.com

rahul@gmail.com
  ├── Green College
  ├── ABC School
  └── XYZ Academy
```

There are still staff-assisted doors for sales-led trials and enterprise
contracts, but all paths link the tenant back to a platform owner account and
end at the same place: a row in `tenants`, a row in `subscriptions`, and one
user holding `INSTITUTION_ADMIN`.

```
   DOOR A — Self-service owner
   ───────────────────────────
   Owner signs up  →  verifies email  →  creates institution
                   →  pays / starts trial
                   →  tenant is provisioned automatically

   DOOR B — Sales-led
   ─────────────────
   Prospect enquires  →  Sales Executive assists the owner / trial
                      →  14-day trial or paid conversion

   DOOR C — Super Admin (direct/enterprise)
   ────────────────────────────────────────
   Signed contract    →  Super Admin creates or links owner + tenant
                      →  Starts ACTIVE on day one, invoiced offline
```

**Who is "buying" at each step matters, because there are two different
purchases in this system and they are easy to confuse:**

| Purchase | Buyer | Pays whom | Tables |
|---|---|---|---|
| **Platform subscription** | Institution → shikshasync.me | The platform | `plans`, `subscriptions` |
| **Student fees** | Parent/Student → Institution | The institution | `fee_structures`, `fee_payments` |

§9 of the DB doc is titled "Platform ERP Tables (Finance Module)" but contains
`student_fee_accounts` and `fee_payments` — that is the **second** kind. The
first kind has almost no tables at all (§9 of this document).

---

## 2. Stage 1 — Lead and trial

### 2.1 Sales creates the trial

```
Sales Executive  ──►  /platform/sales/trials  ──►  "New trial"
                                │
                                ▼
          POST /api/v1/platform/tenants  { name, slug, type, contactEmail }
                                │
   ┌────────────────────────────┼────────────────────────────┐
   │  ONE TRANSACTION                                        │
   │  1. INSERT tenants        (is_active=TRUE,              │
   │                            trial_ends_at = now + 14d,   │
   │                            plan_id = Starter)           │
   │  2. INSERT subscriptions  (status = TRIAL, amount = 0)  │
   │  3. INSERT tenant_modules (8 core = TRUE, 8 optional    │
   │                            = FALSE)                     │
   │  4. INSERT users          (the admin, no password yet)  │
   │  5. INSERT role_assignments (INSTITUTION_ADMIN)         │
   │  6. INSERT outbox         ('tenant.provisioned')        │
   └────────────────────────────┬────────────────────────────┘
                                │  commit
                                ▼
        Outbox relay ──► queue ──► SES: "Set your password" link
                                   (reset token, 30-min expiry)
```

**Why one transaction.** A tenant that exists without an admin user is
unreachable — nobody can log in to fix it. A tenant without
`tenant_modules` rows has an empty sidebar. Either half-state requires manual
DB surgery, so all six writes commit together or none do.

**Why the email is in the outbox, not inline.** If SES is down, the tenant is
still correctly provisioned and the mail retries. If the transaction rolls
back, the email was never queued. Sending inline gets this backwards: a
"welcome" mail for a tenant that does not exist.

### 2.2 Trial state

```
tenants.trial_ends_at = 2026-08-15      ← the countdown
tenants.is_active     = TRUE            ← can log in
subscriptions.status  = TRIAL           ← not paying
```

Both flags matter and they are **independent** — this catches people out:

| `is_active` | `subscriptions.status` | Result |
|---|---|---|
| TRUE | TRIAL | Working trial |
| TRUE | ACTIVE | Paying customer |
| TRUE | PAST_DUE | Grace period — read-only (§8.2) |
| **FALSE** | ACTIVE | **Suspended despite paying** (abuse, non-payment dispute) |

`is_active = FALSE` always wins. One function, `tenantState()`, derives the
verdict; nothing else may re-derive it.

### 2.3 The trial clock

An hourly job sweeps expiring trials:

| Days left | Action |
|---|---|
| 7, 3, 1 | Email the admin + flag on the Sales dashboard |
| 0 | `is_active = FALSE`, `subscriptions.status = CANCELLED` |
| +30 | Data retained, login blocked — recoverable on conversion |
| +90 | Purge (per §17 retention policy) |

**Data is never deleted at expiry.** A school that forgets to renew over the
summer break and loses a year of attendance will not come back.

---

## 3. Stage 2 — Purchase: what "buying" actually is

This is the step the question is really about. In the current design,
"buying" is **C-SL-03 Convert Trial to Paid** — a Sales Executive action, not
a self-service checkout.

### 3.1 The conversion flow

```
Sales Executive ─► /platform/sales/trials/{id}/convert
                          │
                          ▼
              ┌───────────────────────────┐
              │  Pick plan + billing cycle│
              │  Starter / Standard /     │
              │  Professional / Enterprise│
              │  Monthly | Yearly         │
              └─────────────┬─────────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │  planFit() — 3 levels     │
              │                           │
              │  BLOCKER  over a hard cap │──► refuse
              │           (students /     │
              │            teachers /     │
              │            storage)       │
              │  WARNING  a module the    │──► checkbox
              │           plan drops      │    to acknowledge
              │  NOTE     headroom        │──► informational
              └─────────────┬─────────────┘
                            │ confirmed
                            ▼
   ┌────────────────────────────────────────────────────────┐
   │  ONE TRANSACTION                                       │
   │  1. UPDATE tenants       SET plan_id, trial_ends_at=NULL│
   │  2. UPDATE subscriptions SET status='CANCELLED'  (trial)│
   │  3. INSERT subscriptions (status='ACTIVE',              │
   │                           starts_at, ends_at,           │
   │                           amount, payment_reference)    │
   │  4. UPDATE tenant_modules for modules the plan grants   │
   │  5. INSERT audit_logs                                   │
   │  6. INSERT outbox ('subscription.activated')            │
   └────────────────────────┬───────────────────────────────┘
                            │
                            ▼
             invoice generated · receipt emailed
```

**`planFit()` has three levels, not two, and that is deliberate.** A downgrade
*always* drops something — §4.1 grants Sales "upgrade / **downgrade**", so
collapsing warnings into blockers would make downgrades impossible. A blocker
is only a hard cap: selling Standard (2,000 seats) to an institution with
2,400 students means their next enrolment fails, so that is refused.

### 3.2 Billing cycle is derived, not stored

`subscriptions` has `starts_at` and `ends_at` but **no billing-cycle column**,
while `plans` prices both `price_monthly` and `price_yearly`. The cycle is
therefore the *length of the period*:

```typescript
// Derived so it can never contradict the dates it describes.
const cycle = monthsBetween(sub.startsAt, sub.endsAt) >= 12 ? 'YEARLY' : 'MONTHLY';
```

### 3.3 Where the money actually moves

**Nowhere in the current design.** `subscriptions.payment_reference` is a free
VARCHAR described as "gateway transaction ID", but:

- no payment-gateway integration is specified anywhere,
- no invoice table exists,
- no webhook endpoint is defined,
- no failed-payment record is possible.

So today the flow is: Sales collects payment **out of band** (bank transfer,
signed PO), pastes the reference into the conversion form, and the row is
marked ACTIVE. That is a legitimate B2B model — most Indian institutional
software is sold on invoice, not card — but it must be a **conscious choice**,
because C-FM-02 "Invoices" and C-FM-03 "Payment Records" are pages with no
tables behind them. Section 9 specifies the fix.

---

## 4. Stage 3 — First login and the onboarding wizard

### 4.1 Setting the password

The admin never receives a password. They receive a reset link:

```
Email → https://abc-college.shikshasync.me/reset-password?token=…
              │
              ├─ token missing  → "This link isn't complete"
              ├─ token expired  → "This link has expired" + request a new one
              └─ token valid    → set password (min 6, confirm, both revealed)
                       │
                       ▼
              users.password_hash written (bcrypt cost 12)
              users.password_reset_token = NULL   ← single use
              all other sessions invalidated
```

Single-use matters: a reset link sitting in an inbox is a standing key to the
institution's admin account.

### 4.2 The login itself

```
POST /auth/login  { identifier, password }   on abc-college.shikshasync.me
        │
        ├─ TenantResolver: subdomain → tenant  (Redis, 5-min TTL)
        ├─ tenantState():  is_active AND subscription not CANCELLED
        │       └─ suspended → 403 "Institution suspended" (NOT invalid-password)
        ├─ bcrypt.compare
        ├─ load roles + scope + enabled modules
        └─ issue access (15 min) + refresh (7 days, rotating)
```

The JWT carries `tenantId`, `roles[]` and `scopeIds` — and the token is
**bound to the origin**, so replaying an `abc-college` token against
`xyz-school` fails even though the signature is valid.

### 4.3 First-run wizard

An institution with no departments cannot have classes; with no classes it
cannot have students. The wizard enforces that order rather than dropping the
admin onto an empty dashboard:

```
Step 1  Institution profile   name, logo, address, timezone, academic year
Step 2  Academic structure    departments → classes → subjects
Step 3  Modules               which optional modules to switch on  (§5)
Step 4  People                invite staff, bulk-import students
Step 5  Done                  dashboard unlocks
```

Progress is resumable — step 4 for a 2,000-student college is not a
single sitting. State lives in `tenant_settings`
(`onboarding.step = 3`), not in the browser.

---

## 5. Stage 4 — Buying modules (the toggle is a purchase)

This is where "how does the Institution Admin buy everything" gets specific —
and where the current design has a real hole.

### 5.1 What the toggle does today

`role_based_system_design.md` §7:

```
Institution Admin → Settings → Modules → Toggle ON
        ├── Module becomes visible in navigation
        ├── Associated role is created
        ├── Admin can assign users to that role
        └── Permissions active immediately
```

Sixteen modules: **8 core** (attendance, examination, assignment, notice,
discussion, content, results, timetable) that are always on and cannot be
switched off, and **8 optional** (library, hostel, transport, placement, hr,
admission, inventory, finance).

Each optional module activates exactly one role:

| Module | Role unlocked |
|---|---|
| library | LIBRARIAN |
| hostel | HOSTEL_WARDEN |
| transport | TRANSPORT_MANAGER |
| placement | PLACEMENT_OFFICER |
| hr | HR_MANAGER |
| admission | ADMISSION_OFFICER |
| inventory | STORE_MANAGER |
| finance | ACCOUNTANT |

### 5.2 🔴 The hole: nothing checks the plan

`plans.allowed_modules TEXT[]` exists. `tenant_modules.is_enabled` exists.
**Nothing joins them.** I grepped the entire design doc for
`allowed_modules`, `max_students`, `quota` and `limit` — zero enforcement
anywhere.

So an institution on **Starter** (8 core modules, ₹4,999/month) can open
Settings → Modules and switch on Placement, HR and Inventory for free.

**Fix — the toggle must consult the plan:**

```typescript
async enableModule(tenantId: string, key: ModuleKey, actor: User) {
  const { plan } = await this.tenants.withPlan(tenantId);

  if (!plan.allowedModules.includes(key)) {
    throw new PaymentRequiredException({      // 402, not 403
      code: 'MODULE_NOT_IN_PLAN',
      message: `${MODULE_LABELS[key]} is not included in ${plan.name}.`,
      upgradeTo: this.plans.cheapestWith(key),   // drives the upsell
    });
  }
  // …enable
}
```

**402 Payment Required, not 403 Forbidden.** The distinction is the whole
upsell path: 403 means *you may never do this*; 402 means *you may, on a
higher plan* — and the UI can then show "Upgrade to Professional" instead of
a dead end.

### 5.3 Buying more: the upgrade path

```
Admin hits a limit  ──►  402 + upgradeTo
        │
        ├── UI: "Placement needs Professional — ₹24,999/mo"
        │        [Request upgrade]
        │
        ▼
   POST /platform/upgrade-requests   { tenantId, targetPlanId, reason }
        │
        └──► Sales dashboard  ──► Sales runs the same planFit() +
                                   conversion flow as §3.1
```

The admin **requests**; Sales executes. Same reason there is no self-signup:
plan changes move money, and money changes are a human decision until a
payment gateway exists (§9).

### 5.4 Switching a module off

```
Toggle OFF
   ├── hidden from navigation for every user
   ├── the role's permissions stop resolving
   ├── DATA IS RETAINED — nothing is deleted
   └── re-enabling restores everything
```

Retention is the important half. A hostel warden's two years of room
allotments must survive an accidental toggle. The confirm dialog states the
retained record count, so the admin sees what they are hiding.

### 5.5 Seat limits — the other unenforced cap

`plans.max_students` and `max_teachers` are equally unchecked. Enforce at the
point of creation, not on a nightly report:

```typescript
// Blocks the 2,001st student on a 2,000-seat plan.
const used = await this.count(tenantId, 'STUDENT');
if (plan.maxStudents !== -1 && used >= plan.maxStudents) {
  throw new PaymentRequiredException({
    code: 'SEAT_LIMIT_REACHED',
    message: `${plan.name} allows ${plan.maxStudents} students. You have ${used}.`,
    upgradeTo: this.plans.nextTierFrom(plan),
  });
}
```

`-1` means unlimited (Enterprise). Check on **bulk import too** — importing a
5,000-row CSV into a 2,000-seat plan must fail at validation, before it writes
2,000 rows and then stops.

---

## 6. Stage 5 — Filling the institution

Order is forced by foreign keys — this is not a UI preference:

```
academic_years          ← everything is scoped to a year
    └── departments     (CSE, ECE, MECH…)
          └── classes   (FY-BSc-A) — needs department + year
                └── subjects  (CS301) — needs class
                      └── teacher_subjects  — who teaches what
                            └── student_enrollments
                                  └── parent_student_links (SCHOOL type only)
```

| Step | Page | Task | Notes |
|---|---|---|---|
| 1 | `/academic-years` | C-IA-04 | Exactly one `is_current` |
| 2 | `/departments` | C-IA-02 | Assign an HOD |
| 3 | `/classes` | C-IA-05 | Class teacher + capacity |
| 4 | `/subjects` | C-IA-07 | Theory/practical/elective |
| 5 | `/users` | C-IA-08 | Invite staff — email + role |
| 6 | `/users/:id/roles` | C-IA-10 | Multi-role: Teacher + Mentor |
| 7 | `/enrollments` | C-IA-11 | Bulk CSV import |
| 8 | `/parent-links` | C-IA-12 | School-type only |

**Staff are invited, never created with a password.** Same reset-token flow as
§4.1 — the platform never knows anyone's password.

**Bulk import is async.** A 2,000-row CSV cannot run in a request:

```
POST /import/students (CSV → S3)
   → INSERT bulk_import_jobs (status=PENDING)
   → BullMQ job
   → UI polls GET /import/jobs/:id
   → "1,847 imported · 153 failed" + a downloadable error CSV, row by row
```

Partial success is the normal outcome. Failing the whole batch because 153
rows have a bad date forces the admin to fix a 2,000-row file blind.

---

## 7. Stage 6 — Steady state and renewal

```
        ┌──────────────────────────────────────────────┐
        │              ACTIVE                          │
        │   daily use · MRR counted · all modules      │
        └───────────────────┬──────────────────────────┘
                            │  ends_at − 45 days
                            ▼
                 renewal window opens on the Sales dashboard
                            │
             ┌──────────────┴──────────────┐
             │                             │
         renewed                      not renewed
             │                             │
             ▼                             ▼
   new subscriptions row          status = PAST_DUE
   (ACTIVE, next period)          grace 14 days, read-only
                                           │
                                    still unpaid
                                           │
                                           ▼
                                  is_active = FALSE
                                  data retained 90 days
```

**MRR is computed in one place.** `tenantMrr()` reads each tenant's real
cycle — a yearly plan contributes `price_yearly / 12`, and a **suspended
tenant contributes zero**. Computing it locally in the sales layer once booked
₹4,999 from a suspended tenant while the platform overview correctly showed
nothing.

---

## 8. Failure paths

Every one of these must be a designed screen, not a stack trace.

### 8.1 Payment fails / never arrives

```
ends_at passes, no new subscription
   → status = PAST_DUE
   → login still works, banner: "Payment overdue — read-only from 15 Aug"
   → 14-day grace: reads allowed, writes blocked (402 on every mutation)
   → then is_active = FALSE
```

Read-only rather than a hard lock: a school mid-term still needs to see
today's timetable while finance sorts out a bank transfer.

### 8.2 Suspension vs expiry

| State | Login | Reads | Writes | Cause |
|---|---|---|---|---|
| ACTIVE | ✅ | ✅ | ✅ | Normal |
| PAST_DUE (grace) | ✅ | ✅ | ❌ 402 | Payment late |
| CANCELLED | ❌ | — | — | Trial lapsed / churned |
| `is_active=FALSE` | ❌ | — | — | Suspended by platform |

### 8.3 The admin loses access

The single point of failure in the whole model: one `INSTITUTION_ADMIN` who
leaves, with nobody else holding the role.

- **Prevention:** warn when a tenant has exactly one admin; the wizard
  encourages a second.
- **Recovery:** Support Staff can see the tenant read-only (C-SP-04) but
  **cannot** create users. Only Super Admin can appoint a new admin, and that
  action is audited with the ticket id.

### 8.4 Downgrade with data in a dropped module

Professional → Standard drops Placement, which holds 3 years of offers.

```
planFit() → WARNING (not a blocker)
   "Placement holds 412 records. They will be hidden but not deleted."
   [ ] I understand            ← must be ticked
```

Data survives the downgrade and returns intact on re-upgrade. Deleting it
would make a downgrade irreversible, which turns a billing decision into a
data-loss event.

---

## 9. 🔴 Missing: the billing tables

**C-FM-02 (Invoices) and C-FM-03 (Payment Records) are specified pages with no
tables behind them.** All 106 tables were searched: the only billing-adjacent
ones are `plans` and `subscriptions`. `fee_payments` is *student* fees paid to
the institution — a different flow entirely.

What `subscriptions` cannot express:

- an invoice number, issue date or due date
- GST (mandatory on Indian B2B invoices — CGST/SGST/IGST split by state)
- a failed or partial payment (there is one nullable `payment_reference`)
- a credit note or refund
- payment method or gateway response

**Three tables close it:**

```sql
CREATE TABLE platform_invoices (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL REFERENCES tenants(id),
  subscription_id UUID REFERENCES subscriptions(id),
  invoice_number  VARCHAR(50)  NOT NULL,      -- INV-2026-000123, gapless
  status          invoice_status NOT NULL,    -- DRAFT/ISSUED/PAID/OVERDUE/VOID/REFUNDED
  issued_at       DATE NOT NULL,
  due_at          DATE NOT NULL,
  currency        VARCHAR(3) NOT NULL DEFAULT 'INR',
  subtotal        NUMERIC(12,2) NOT NULL,
  tax_amount      NUMERIC(12,2) NOT NULL DEFAULT 0,
  total           NUMERIC(12,2) NOT NULL,
  amount_paid     NUMERIC(12,2) NOT NULL DEFAULT 0,
  gstin           VARCHAR(15),                -- the institution's GSTIN
  place_of_supply VARCHAR(2),                 -- state code → CGST+SGST vs IGST
  pdf_key         TEXT,
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_platform_invoices_number UNIQUE (invoice_number)
);

CREATE TABLE platform_invoice_lines (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id   UUID NOT NULL REFERENCES platform_invoices(id) ON DELETE CASCADE,
  description  VARCHAR(500) NOT NULL,         -- "Professional plan · Aug 2026"
  hsn_sac      VARCHAR(10),                   -- 998314 for SaaS
  quantity     NUMERIC(10,2) NOT NULL DEFAULT 1,
  unit_price   NUMERIC(12,2) NOT NULL,
  tax_rate     NUMERIC(5,2)  NOT NULL DEFAULT 18.00,
  line_total   NUMERIC(12,2) NOT NULL
);

CREATE TABLE platform_payments (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID NOT NULL REFERENCES tenants(id),
  invoice_id     UUID REFERENCES platform_invoices(id),
  status         payment_status NOT NULL,     -- PENDING/SUCCEEDED/FAILED/REFUNDED
  method         payment_method NOT NULL,     -- BANK_TRANSFER/UPI/CARD/CHEQUE/CREDIT
  amount         NUMERIC(12,2) NOT NULL,
  currency       VARCHAR(3) NOT NULL DEFAULT 'INR',
  gateway        VARCHAR(50),                 -- razorpay | manual
  gateway_ref    VARCHAR(255),                -- idempotency anchor
  gateway_payload JSONB,                      -- raw webhook, for disputes
  failure_reason TEXT,
  received_at    TIMESTAMPTZ,
  recorded_by    UUID REFERENCES platform_users(id),  -- NULL = gateway
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_platform_payments_gateway_ref UNIQUE (gateway, gateway_ref)
);
```

Three details that matter more than they look:

- **`invoice_number` must be gapless per financial year** — Indian statutory
  requirement. Allocate from a sequence inside the transaction, never
  `count(*) + 1`, which races.
- **`UNIQUE (gateway, gateway_ref)`** makes webhook replay a no-op. Gateways
  retry on any non-2xx, so the same `payment.captured` will arrive more than
  once; without this constraint a subscription gets paid twice.
- **`place_of_supply`** decides CGST+SGST (intra-state) vs IGST
  (inter-state). Getting it wrong is a filing correction, not a bug fix.

### 9.1 If a payment gateway is added later

```
Admin clicks "Pay now"  ──►  POST /billing/checkout  (idempotency key)
                                     │
                         create Razorpay order, return order_id
                                     │
                        ┌────────────┴────────────┐
                        │  Client-side checkout   │
                        └────────────┬────────────┘
                                     │
        ┌────────────────────────────┴──────────────────────┐
        │  WEBHOOK is the source of truth, not the redirect │
        │  POST /webhooks/razorpay                          │
        │    1. verify HMAC signature      ← reject if bad  │
        │    2. UNIQUE(gateway, ref)       ← replay = no-op │
        │    3. INSERT platform_payments (SUCCEEDED)        │
        │    4. UPDATE invoice amount_paid → PAID           │
        │    5. INSERT subscriptions (ACTIVE, next period)  │
        │    6. INSERT outbox ('subscription.activated')    │
        └───────────────────────────────────────────────────┘
```

**Never activate on the browser redirect.** The user can close the tab, and
the redirect can be forged. The signed webhook is the only trustworthy signal;
the redirect just shows a spinner until the webhook lands.

---

## 10. End-to-end sequence

```
 ACTOR              ACTION                        STATE AFTER
─────────────────────────────────────────────────────────────────────────
 Prospect           enquiry                       —
 Sales Executive    create trial                  tenants(TRIAL, 14d)
                                                  subscriptions(TRIAL)
                                                  tenant_modules(8 core ON)
                                                  users(admin, no password)
 System             email reset link              outbox → SES
─────────────────────────────────────────────────────────────────────────
 Inst. Admin        set password                  password_hash written
 Inst. Admin        first login                   JWT (15m) + refresh (7d)
 Inst. Admin        wizard 1–2                    year, departments, classes
─────────────────────────────────────────────────────────────────────────
 Sales Executive    convert to paid               plan_id = Professional
                    (planFit passes)              subscriptions(ACTIVE, 1y)
                                                  trial_ends_at = NULL
                                                  invoice + receipt   ← §9
─────────────────────────────────────────────────────────────────────────
 Inst. Admin        Settings → Modules            tenant_modules: library,
                    (plan-gated — §5.2)           hostel, hr = TRUE
                                                  → 3 roles now assignable
 Inst. Admin        invite staff                  users + role_assignments
 Inst. Admin        bulk-import students          bulk_import_jobs → 1,847 ok
 Inst. Admin        link parents (SCHOOL)         parent_student_links
─────────────────────────────────────────────────────────────────────────
 Teacher            marks attendance              STEADY STATE
 Exam Controller    schedules exams
 Accountant         collects student fees         ← institution's own money,
                                                    NOT the platform's
─────────────────────────────────────────────────────────────────────────
 System             T−45d renewal window          Sales dashboard flag
 Sales Executive    renew                         new subscriptions row
   … or not         grace → PAST_DUE (read-only) → is_active = FALSE
                                                  data retained 90 days
```

---

## Summary of gaps flagged

| # | Gap | Severity | Where | Status |
|---|---|---|---|---|
| 1 | **No invoice / payment tables** — C-FM-02 and C-FM-03 have no data source | 🔴 | §9 | ✅ Implemented — `platform_invoices`, `platform_invoice_lines`, `platform_payments`, `coupons`, `orders` (migration `8a1e4b2c5f01`); gapless `INV-YYYY-NNNNNN` numbering, GST 18% |
| 2 | **`plans.allowed_modules` is never enforced** — Starter can enable every module free | 🔴 | §5.2 | ✅ Enforced in the signup quote engine and the setup-wizard module sync (`_sync_modules` is plan-gated) |
| 3 | **`max_students` / `max_teachers` never checked** — no seat limit exists | 🔴 | §5.5 | 🟡 Open — surfaced on the pricing cards; enforcement on enrolment is future work |
| 4 | No self-service signup (by design — confirm it is intentional) | 🟡 | §1 | ✅ Implemented — public `/pricing` → `/signup` checkout (registration → subdomain check → plan/BYO → review/coupon → payment → auto-provisioning) plus the 12-step admin setup wizard |
| 5 | No payment gateway specified; conversion assumes out-of-band payment | 🟡 | §3.3 | 🟡 Mock gateway with `UNIQUE(gateway, gateway_ref)` replay protection; swap `SignupService.mark_paid` for the real webhook (§9.1) |
| 6 | Single-admin lockout has no automated recovery | 🟡 | §8.3 | 🟡 Open — reset link flow already exists for tenant users |

Gaps 2 and 3 are the ones that cost money on day one: today the plan a
customer pays for constrains nothing at all. (2 is fixed; 3 is the seat
check at enrolment time.)

---

*System flow v1.0 · companion to `ARCHITECTURE.md` and `database.sql` ·
verified against the 106-table schema*
