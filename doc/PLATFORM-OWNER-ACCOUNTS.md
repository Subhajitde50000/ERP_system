# Platform Owner Accounts — the AWS / Shopify / Zoho model

> **What this is.** The "account-holder" architecture that turns shikshasync.me into a
> multi-tenant SaaS platform like AWS, Shopify or Zoho: **one customer account
> owns many institutions**, managed from a single platform dashboard.
>
> **Status.** Implemented in backend migration `e2a3f5b7c8d0` (platform_owners),
> the `/api/v1/owner/*` API, and the `/account/*` frontend console.

---

## The mistake this fixes

Before this change the system had only two identity tables:

| Table | Who | Login at |
|---|---|---|
| `platform_users` | shikshasync.me **staff** (Super Admin, Support, Sales, Finance) | `app.shikshasync.me/login` |
| `users` | institution-bound members (Teacher, Student, INSTITUTION_ADMIN…) | `green.shikshasync.me/login` |

There was **no customer**. The public `/signup` created an isolated institution
plus a single institution-admin `users` row — with nothing tying multiple
institutions to one buyer. A person who ran three schools had three separate,
unrelated logins and no consolidated billing.

## The fix: a third identity — `platform_owners`

| Table | Who | Login at |
|---|---|---|
| `platform_users` | shikshasync.me staff (unchanged) | `app.shikshasync.me/login` → `/platform/login` |
| **`platform_owners`** | **the customer / account-holder** | **`shikshasync.me/login` → `/account/login`** |
| `users` | institution members (unchanged) | `green.shikshasync.me/login` → `/login` |

An owner is the buyer. **One owner → many institutions**, via
`tenants.owner_id`. Rahul (`rahul@gmail.com`) signs up once and owns Green
College, ABC School and XYZ Academy; he logs into `shikshasync.me` once and manages
billing, subscriptions, invoices and support for all of them.

```
   Visit shikshasync.me
   │
   ▼  Sign Up (Name, Email, Password)            → platform_owners (unverified)
   │
   ▼  Verify Email                                → is_email_verified = true
   │
   ▼  Platform Dashboard  /account
        ├── My Institutions
        ├── Billing
        ├── Subscriptions
        ├── Invoices
        ├── Support Tickets
        └── Profile
   │
   ▼  Create New Institution  /account/institutions/new
   │      (reuses the public checkout: Plan → Subdomain → Payment → Provision,
   │       but the order carries owner_id so tenants.owner_id is stamped)
   │
   ▼  Go To  green.shikshasync.me/login   (daily ERP — a separate login system)
```

## Two (really three) login systems

1. **Platform / Owner login** — `shikshasync.me/login` (`/account/login`).
   - JWT `type: "owner"`. Owns institutions, billing, subscriptions, invoices,
     support tickets, profile.
2. **Institution login** — `green.shikshasync.me/login` (`/login`).
   - JWT `type: "tenant"`. Daily ERP: students, teachers, attendance, exams,
     LMS, finance, reports.
3. **Staff console** — `app.shikshasync.me/login` (`/platform/login`).
   - JWT `type: "platform"`. Super Admin / Support / Sales / Finance running the
     platform itself.

A token from one system is never accepted by another — the JWT `type` claim and
the `get_current_*` dependency enforce that.

## Data model additions (migration `e2a3f5b7c8d0`)

```
platform_owners            customer accounts (name, email, password_hash,
                           is_email_verified, verification + reset tokens)
owner_sessions             hashed refresh tokens (type="owner")
support_tickets            account-level tickets raised from the dashboard
support_ticket_messages    the conversation thread
tenants.owner_id  (new)    1 owner → many institutions
orders.owner_id   (new)    records who started an in-dashboard checkout
```

`owner_id` is nullable so pre-existing Sales/Super-Admin-created institutions
keep working without an owner.

## API surface (`/api/v1/owner/*`)

| Method & path | Purpose |
|---|---|
| `POST /owner/signup` | Create the account (email unverified) |
| `POST /owner/verify-email` | Confirm the email token |
| `POST /owner/resend-verification` | Re-send the link (silent success) |
| `POST /owner/login` | Sign in (requires verified email) |
| `POST /owner/logout` · `/refresh` · `GET /me` | Session |
| `POST /owner/forgot-password` · `/reset-password` | Self-service reset |
| `GET /owner/institutions` | **My Institutions** |
| `GET /owner/billing/summary` | Totals across all institutions |
| `GET /owner/subscriptions` · `/invoices` · `/payments` | Billing records |
| `GET /owner/tickets` · `POST` · `GET /{id}` · `POST /{id}/reply` | Support |
| `GET /owner/subdomains/check` | Availability for "Choose Subdomain" |
| `POST /owner/orders` · `POST /orders/{id}/pay` · `GET /orders/{id}` | Create institution checkout, owner-scoped |
| `PUT /owner/profile` · `POST /owner/change-password` | Profile |

## How institution creation was reused (no duplicate code)

The full checkout wizard — Choose Plan → Subdomain → Modules → Review → Payment
→ Provision — already existed as `CheckoutFlow` + `SignupService.provision`.
It was **not** duplicated. Instead:

- `OrderCreateRequest` gained an optional `owner_id`; `provision()` stamps
  `tenants.owner_id = order.owner_id`.
- `CheckoutFlow` gained an optional `ownerToken` prop; when set it POSTs to the
  `/owner/orders` endpoints instead of the anonymous `/public/orders`.
- The owner dashboard's "Create New Institution" page (`/account/institutions/new`)
  renders the same `CheckoutFlow` with the owner's token.

So one wizard serves both the legacy anonymous path and the authenticated
owner path, and the entire provisioning pipeline (invoice, admin user, modules,
settings, academic year, welcome email) is shared.

## Email verification

Signup creates the owner with `is_email_verified = false` and queues a
verification email in `outbox_emails` (the same outbox the tenant provisioning
uses). **Login is blocked until the email is verified.** In dev/no-mailer mode
the raw verification token is returned in the API response so the flow can be
completed end to end; in production (`APP_DEBUG=false`) it is delivered only by
email.
