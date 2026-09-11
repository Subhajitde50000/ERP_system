/**
 * Shared auth/tenant contracts — shikshasync.me ERP + LMS
 * Mirrors the login API payload in login_page_design.md §8.
 */

/**
 * Platform-level roles — served from app.shikshasync.me.
 * Ref: role_based_system_design.md §2.1
 */
export type PlatformRole =
  | "SUPER_ADMIN"
  | "SUPPORT_STAFF"
  | "SALES_EXECUTIVE"
  | "FINANCE_MANAGER"
  | "OWNER";

/**
 * The 18 institution roles — served from <tenant>.shikshasync.me.
 * Ref: role_based_system_design.md §2.2, packages/shared-types/roles.ts
 */
export type InstitutionRole =
  | "INSTITUTION_ADMIN"
  | "PRINCIPAL"
  | "VICE_PRINCIPAL"
  | "HOD"
  | "TEACHER"
  | "MENTOR"
  | "EXAM_CONTROLLER"
  | "ACADEMIC_COORDINATOR"
  | "ACCOUNTANT"
  | "STUDENT"
  | "PARENT"
  | "LIBRARIAN"
  | "HOSTEL_WARDEN"
  | "TRANSPORT_MANAGER"
  | "PLACEMENT_OFFICER"
  | "HR_MANAGER"
  | "ADMISSION_OFFICER"
  | "STORE_MANAGER";

/** All roles supported by the platform. */
export type Role = PlatformRole | InstitutionRole;

/**
 * The 16 module keys — 8 core (always on) + 8 optional (toggleable).
 * Ref: packages/shared-types/modules.ts
 */
export type ModuleKey =
  // Core — always enabled
  | "attendance"
  | "examination"
  | "assignment"
  | "notice"
  | "discussion"
  | "content"
  | "results"
  | "timetable"
  // Optional — toggled per tenant in Settings → Modules
  | "library"
  | "hostel"
  | "transport"
  | "placement"
  | "hr"
  | "admission"
  | "inventory"
  | "finance"
  | "parent";

export type TenantType = "SCHOOL" | "COLLEGE" | "UNIVERSITY" | "PLATFORM";

export interface Tenant {
  /** Subdomain slug, e.g. "abc-college" */
  slug: string;
  /** Display name, e.g. "ABC College" */
  name: string;
  /** Full host shown in the badge, e.g. "abc-college.shikshasync.me" */
  host: string;
  type: TenantType;
  logoUrl?: string | null;
  /** true when the slug did not resolve to a known institution (§7) */
  notFound?: boolean;
  /** true for the platform console at app.shikshasync.me */
  isPlatform?: boolean;
  /** Optional SSO provider label, e.g. "Google Workspace" */
  ssoProvider?: string | null;
}

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  avatarUrl?: string | null;
}

/** Response shape of POST /api/v1/auth/login — design §8 */
export interface LoginResponse {
  user: AuthUser;
  roles: Role[];
  enabledModules: ModuleKey[];
  tenant: {
    name: string;
    logo_url?: string | null;
    type: TenantType;
  };
  accessToken?: string;
}

export interface LoginCredentials {
  /** Email address or roll number */
  identifier: string;
  password: string;
  remember: boolean;
  /** Resolved from the subdomain before the request is sent */
  tenantId: string;
}

/** Error codes the UI renders distinct states for — design §7 */
export type AuthErrorCode =
  | "INVALID_CREDENTIALS"
  | "TENANT_NOT_FOUND"
  | "MODULE_DISABLED"
  | "ACCOUNT_LOCKED"
  | "NETWORK_ERROR"
  | "UNKNOWN";

export class AuthError extends Error {
  code: AuthErrorCode;

  constructor(code: AuthErrorCode, message: string) {
    super(message);
    this.name = "AuthError";
    this.code = code;
  }
}

/* ── Platform console sign-in (app.shikshasync.me) ─────────────────────────────── */

/**
 * Platform staff credentials.
 *
 * Deliberately NOT `LoginCredentials`: platform users live in their own table
 * (`platform_users`, DB §4.5) with **no `tenant_id`**, and the column is
 * `email VARCHAR(255) UNIQUE` — there is no roll-number path, so the field is
 * an email, not the tenant side's polymorphic `identifier`.
 */
export interface PlatformLoginCredentials {
  email: string;
  password: string;
  remember: boolean;
}

/** What a successful platform sign-in returns. */
export interface PlatformLoginResponse {
  user: {
    id: string;
    name: string;
    email: string;
    /** `platform_users.last_login_at` — shown as "Last sign-in" on the console. */
    lastLoginAt: string | null;
  };
  /** Exactly one. Unlike institution users, platform staff hold a single role. */
  role: PlatformRole;
  accessToken?: string;
}
