import type { ModuleKey, InstitutionRole } from "./auth";

/**
 * Settings contracts — role_based_shared_pages.md PAGE 16 (C-RB-16).
 *
 * Mirrors `tenant_settings` (DB §4.3), `tenant_modules` (§5.2),
 * `academic_years` (§6.1), `leave_policies` + `salary_structures` (§8.5)
 * and the notification channel matrix (dev doc §12.1).
 *
 * `/settings/modules` is task C-IA-14 — the docs call it "THE module toggle
 * page" — so it is a real sub-route, not just a section.
 */

/** Every section named in the PAGE 16 matrix. */
export type SettingsSectionKey =
  | "GENERAL" // C-IA-13 — institution name, logo, timezone, contact
  | "MODULES" // C-IA-14 — the module toggle
  | "FEES" // C-IA-15 — fee structure
  | "NOTIFICATIONS" // C-IA-16 — which events trigger which channel
  | "ACADEMIC_YEAR" // C-IA-04 — years, current year
  | "BRANDING" // logo, palette
  | "LEAVE_POLICIES" // HR — §8.5 leave_policies
  | "SALARY_DEFAULTS" // HR — §8.5 salary_structures
  | "NOTIFICATION_PREFS" // personal channel preferences
  | "PASSWORD" // change password
  | "PROFILE"; // profile update

export interface SettingsSection {
  key: SettingsSectionKey;
  label: string;
  description: string;
  /**
   * PAGE 16 gives the Principal "Academic Year (view)" — the section is
   * visible but nothing in it is editable.
   */
  readOnly?: boolean;
  /** Section is backed by an optional module and hides when it's off (§3) */
  module?: ModuleKey;
  /** Sub-route for sections the assignment doc gives their own page */
  href?: string;
}

export interface SettingsPermissions {
  sections: SettingsSection[];
  /** Institution-wide settings, as opposed to personal preferences */
  canManageInstitution: boolean;
  /** C-IA-14 — toggle optional modules */
  canToggleModules: boolean;
  note: string;
}

/* ── General / branding (`tenant_settings`, DB §4.3) ────────────────────── */

export interface InstitutionSettings {
  name: string;
  shortName: string;
  type: "SCHOOL" | "COLLEGE" | "UNIVERSITY";
  email: string;
  phone: string;
  address: string;
  website: string | null;
  timezone: string;
  /** Percentage below which a student is flagged (§4.3 attendance_threshold) */
  attendanceThreshold: number;
  academicYearStartMonth: number;
  /** Branding */
  logoUrl: string | null;
  primaryColor: string;
  accentColor: string;
}

/* ── Modules (`tenant_modules`, DB §5.2) ────────────────────────────────── */

/**
 * One row of the C-IA-14 checklist.
 *
 * Core modules are always on and cannot be toggled (§3). Optional ones each
 * activate a role, which is the part an admin actually needs to understand
 * before flipping the switch.
 */
export interface ModuleToggle {
  key: ModuleKey;
  label: string;
  description: string;
  isCore: boolean;
  isEnabled: boolean;
  /** The role this module activates — null for core modules (§3) */
  activatesRole: InstitutionRole | null;
  /** Users currently holding that role; they lose access when it's off */
  affectedUsers: number;
  /** Rows retained while disabled — §3 "Data is retained (not deleted)" */
  retainedRecords: number;
  enabledAt: string | null;
  enabledByName: string | null;
}

/* ── Academic years (`academic_years`, DB §6.1) ─────────────────────────── */

export interface AcademicYearRow {
  id: string;
  name: string;
  startDate: string;
  endDate: string;
  isCurrent: boolean;
  classCount: number;
  studentCount: number;
}

/* ── Notification config (C-IA-16 + dev doc §12.1) ──────────────────────── */

export type NotificationChannel = "IN_APP" | "PUSH" | "EMAIL" | "SMS";

/** Personal: the "notification preferences" every role gets. */
export interface NotificationPreference {
  channel: NotificationChannel;
  label: string;
  description: string;
  enabled: boolean;
  /** Channels the institution has disabled outright can't be opted into */
  lockedByInstitution?: boolean;
}

/* ── Fee structure (C-IA-15, DB §9) ─────────────────────────────────────── */

export interface FeeHeadRow {
  id: string;
  name: string;
  amount: number;
  isOptional: boolean;
  appliesTo: string;
}

/* ── HR (DB §8.5) ───────────────────────────────────────────────────────── */

export interface LeavePolicyRow {
  id: string;
  name: string;
  code: string;
  daysPerYear: number;
  isCarryForward: boolean;
  maxCarryForwardDays: number;
  appliesTo: string[];
  isActive: boolean;
}

/** Defaults a new `salary_structures` row is seeded from. */
export interface SalaryDefaults {
  hraPercent: number;
  daPercent: number;
  pfPercent: number;
  professionalTax: number;
  /** Day of the month payroll is processed */
  payrollDay: number;
}

/** Everything the settings page may render, scoped to the caller. */
export interface SettingsData {
  institution?: InstitutionSettings;
  modules?: ModuleToggle[];
  academicYears?: AcademicYearRow[];
  feeHeads?: FeeHeadRow[];
  leavePolicies?: LeavePolicyRow[];
  salaryDefaults?: SalaryDefaults;
  /** Personal preferences — every role gets these */
  preferences: NotificationPreference[];
}
