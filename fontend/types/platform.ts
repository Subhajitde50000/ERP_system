import type { ModuleKey, PlatformRole } from "./auth";

/**
 * Platform console contracts — the Super Admin pages (C-SA-01…C-SA-08).
 *
 * These live at **`app.shikshasync.me`**, not on an institution subdomain
 * (`complete_webpage_developer_assignment.md` §2: "These pages live at
 * app.shikshasync.me — not institution subdomains · Next.js route prefix
 * `app/(platform)/`").
 *
 * Mirrors the Layer 1 tables in `database_design_complete.md`:
 *   §4.1 `plans` · §4.2 `tenants` · §4.3 `tenant_settings`
 *   §4.4 `subscriptions` · §4.5 `platform_users` · §4.6 `support_tickets`
 *   §10.3 `audit_logs` (global, `tenant_id` NULL for platform actions)
 *
 * ── Naming conflict, flagged in the README ────────────────────────────────
 * The DB enum is `platform_role AS ENUM ('SUPER_ADMIN','SUPPORT','SALES',
 * 'FINANCE')` (§12) but `types/auth.ts` — which came from
 * `role_based_system_design.md` §2.1 and drives the whole app — uses
 * `SUPPORT_STAFF / SALES_EXECUTIVE / FINANCE_MANAGER`. The app's names win
 * here because 40+ files already depend on them; `PLATFORM_ROLE_DB` below maps
 * to the DB spelling at the boundary, which is the one place it matters.
 */

/** `platform_role` as the database spells it (§12). */
export const PLATFORM_ROLE_DB: Record<PlatformRole, string> = {
  SUPER_ADMIN: "SUPER_ADMIN",
  SUPPORT_STAFF: "SUPPORT",
  SALES_EXECUTIVE: "SALES",
  FINANCE_MANAGER: "FINANCE",
  OWNER: "OWNER",
};

/* ── §4.2 tenants ───────────────────────────────────────────────────────── */

export type TenantType = "SCHOOL" | "COLLEGE";

/** `subscriptions.status` (§4.4). A tenant's badge is derived from this. */
export type SubscriptionStatus = "TRIAL" | "ACTIVE" | "PAST_DUE" | "CANCELLED";

export interface TenantRow {
  id: string;
  name: string;
  /** Subdomain — `abc-college.shikshasync.me` */
  slug: string;
  type: TenantType;
  planName: string;
  planSlug: string;
  status: SubscriptionStatus;
  /** `is_active` — suspending a tenant locks every user out */
  isActive: boolean;
  studentCount: number;
  teacherCount: number;
  /** Modules the tenant has switched on (`tenant_modules`, §5.2) */
  enabledModules: ModuleKey[];
  storageUsedGb: number;
  city: string | null;
  state: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  timezone: string;
  /** `trial_ends_at` — null when not on trial */
  trialEndsAt: string | null;
  createdAt: string;
}

/** One tenant plus everything the detail page shows (C-SA-03). */
export interface TenantDetail {
  tenant: TenantRow;
  /** Billing history (§4.4) */
  subscriptions: SubscriptionRow[];
  /** Which admin to contact */
  adminName: string;
  adminEmail: string;
  /** Recent platform-visible activity for this tenant (§10.3) */
  recentActivity: PlatformAuditEntry[];
  /** Open tickets raised by this institution (§4.6) */
  openTickets: number;
}

/* ── §4.1 plans ─────────────────────────────────────────────────────────── */

export interface PlanRow {
  id: string;
  name: string;
  slug: string;
  /** -1 means unlimited (§4.1) */
  maxStudents: number;
  maxTeachers: number;
  maxStorageGb: number;
  priceMonthly: number;
  priceYearly: number;
  currency: string;
  allowedModules: ModuleKey[];
  isActive: boolean;
  /** Derived: how many tenants are on this plan */
  tenantCount: number;
}

/* ── §4.4 subscriptions ─────────────────────────────────────────────────── */

/**
 * How a period is billed.
 *
 * Not a column: §4.4 stores `starts_at` and `ends_at`, and `plans` (§4.1)
 * prices both `price_monthly` and `price_yearly`. The cycle is therefore the
 * *length of the period*, derived rather than stored, so it can never
 * disagree with the dates it is supposed to describe.
 */
export type BillingCycle = "MONTHLY" | "YEARLY";

export interface SubscriptionRow {
  id: string;
  tenantId: string;
  tenantName: string;
  planName: string;
  status: SubscriptionStatus;
  startsAt: string;
  endsAt: string | null;
  amount: number;
  currency: string;
  paymentReference: string | null;
  /** Derived from the period length — see `BillingCycle` */
  cycle: BillingCycle;
}

/* ── §4.5 platform_users ────────────────────────────────────────────────── */

export interface PlatformUserRow {
  id: string;
  name: string;
  email: string;
  role: PlatformRole;
  isActive: boolean;
  lastLoginAt: string | null;
  createdAt: string;
}

/* ── §10.3 audit_logs (global view) ─────────────────────────────────────── */

export interface PlatformAuditEntry {
  id: string;
  action: string;
  entity: string;
  target: string;
  actorName: string;
  /** Role held at the time — may be a platform or an institution role */
  actorRole: string;
  /** null for platform-level actions (§10.3: "NULL for platform actions") */
  tenantName: string | null;
  ipAddress: string;
  createdAt: string;
}

/* ── C-SA-01 dashboard ──────────────────────────────────────────────────── */

export interface PlatformStats {
  totalInstitutions: number;
  activeInstitutions: number;
  trialInstitutions: number;
  suspendedInstitutions: number;
  totalStudents: number;
  totalTeachers: number;
  /** Monthly recurring revenue, summed from active subscriptions */
  mrr: number;
  openTickets: number;
  criticalTickets: number;
  /** Revenue per month, oldest first */
  revenueTrend: { label: string; amount: number }[];
  /** Tenants per plan, for the mix chart */
  planMix: { plan: string; count: number }[];
  /** Newest signups */
  recentTenants: TenantRow[];
}

/* ── C-SA-08 platform settings ──────────────────────────────────────────── */

export interface PlatformSettings {
  productName: string;
  supportEmail: string;
  rootDomain: string;
  /** Modules a plan is allowed to offer at all — the global master list (§3) */
  allowedModules: { key: ModuleKey; label: string; core: boolean }[];
  defaultTimezone: string;
  defaultCurrency: string;
  trialLengthDays: number;
  /** Branding shown on every tenant login page unless overridden */
  brandPrimary: string;
  brandAccent: string;
}
