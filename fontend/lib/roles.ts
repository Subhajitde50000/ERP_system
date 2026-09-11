import type { InstitutionRole, Role } from "@/types/auth";

/**
 * Role → dashboard routing + display metadata.
 * Redirect table from login_page_design.md §8.
 */

interface RoleMeta {
  /** Label shown in the role chip, e.g. "Teacher Access" */
  label: string;
  /** Post-login destination */
  redirect: string;
  /** Absolute redirect (platform console lives on app.shikshasync.me) */
  external?: boolean;
}

const ROLE_MAP: Record<Role, RoleMeta> = {
  // Platform — hosted on app.shikshasync.me
  SUPER_ADMIN: { label: "Super Admin", redirect: "/platform/dashboard", external: true },
  SUPPORT_STAFF: { label: "Support Staff", redirect: "/platform/support/dashboard", external: true },
  SALES_EXECUTIVE: { label: "Sales Executive", redirect: "/platform/sales/dashboard", external: true },
  FINANCE_MANAGER: { label: "Finance Manager", redirect: "/platform/finance", external: true },
  OWNER: { label: "Owner", redirect: "/platform/dashboard", external: true },

  // Institution leadership
  INSTITUTION_ADMIN: { label: "Institution Admin", redirect: "/admin/dashboard" },
  PRINCIPAL: { label: "Principal", redirect: "/principal/dashboard" },
  // Dedicated, delegated production surface. The documented `/vp/*` routes
  // are distinct from the Principal's final-approval console.
  VICE_PRINCIPAL: { label: "Vice Principal", redirect: "/vp/dashboard" },
  HOD: { label: "HOD", redirect: "/hod/dashboard" },

  // Academic
  TEACHER: { label: "Teacher", redirect: "/teacher/dashboard" },
  MENTOR: { label: "Mentor", redirect: "/mentor/dashboard" },
  EXAM_CONTROLLER: { label: "Exam Controller", redirect: "/exam-controller/dashboard" },
  ACADEMIC_COORDINATOR: { label: "Academic Coordinator", redirect: "/coordinator/dashboard" },
  STUDENT: { label: "Student", redirect: "/student/dashboard" },
  PARENT: { label: "Parent", redirect: "/parent/dashboard" },

  // Operations
  ACCOUNTANT: { label: "Accountant", redirect: "/accountant/dashboard" },
  LIBRARIAN: { label: "Librarian", redirect: "/librarian/dashboard" },
  HOSTEL_WARDEN: { label: "Hostel Warden", redirect: "/hostel-warden/dashboard" },
  TRANSPORT_MANAGER: { label: "Transport Manager", redirect: "/transport-manager/dashboard" },
  PLACEMENT_OFFICER: { label: "Placement Officer", redirect: "/placement-officer/dashboard" },
  HR_MANAGER: { label: "HR Manager", redirect: "/hr-manager/dashboard" },
  ADMISSION_OFFICER: { label: "Admission Officer", redirect: "/admission-officer/dashboard" },
  STORE_MANAGER: { label: "Store Manager", redirect: "/store-manager/dashboard" },
};

const DEFAULT_META: RoleMeta = { label: "Member Access", redirect: "/dashboard" };

/** Priority order when a user holds several roles — highest privilege wins. */
const PRIORITY: Role[] = [
  "SUPER_ADMIN",
  "SUPPORT_STAFF",
  "FINANCE_MANAGER",
  "SALES_EXECUTIVE",
  "OWNER",
  "INSTITUTION_ADMIN",
  "PRINCIPAL",
  "VICE_PRINCIPAL",
  "HOD",
  "ACADEMIC_COORDINATOR",
  "EXAM_CONTROLLER",
  "TEACHER",
  "MENTOR",
  "ACCOUNTANT",
  "HR_MANAGER",
  "PLACEMENT_OFFICER",
  "LIBRARIAN",
  "HOSTEL_WARDEN",
  "TRANSPORT_MANAGER",
  "ADMISSION_OFFICER",
  "STORE_MANAGER",
  "STUDENT",
  "PARENT",
];

/** Pick the role that decides the landing page. */
export function primaryRole(roles: Role[]): Role | null {
  if (!roles?.length) return null;
  return PRIORITY.find((r) => roles.includes(r)) ?? roles[0]!;
}

export function roleLabel(role: Role | null): string {
  if (!role) return DEFAULT_META.label;
  return (ROLE_MAP[role] ?? DEFAULT_META).label;
}

/** Resolve the post-login destination for a set of roles. */
export function redirectForRoles(roles: Role[]): string {
  const role = primaryRole(roles);
  if (!role) return DEFAULT_META.redirect;

  const meta = ROLE_MAP[role] ?? DEFAULT_META;

  // SUPER_ADMIN and platform staff land on the platform console host (§8)
  if (meta.external) {
    const root = process.env.NEXT_PUBLIC_ROOT_DOMAIN ?? "shikshasync.me";
    const isLocal =
      typeof window !== "undefined" &&
      /^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname);

    // Keep local dev on the same origin instead of jumping to production
    return isLocal ? meta.redirect : `https://app.${root}${meta.redirect}`;
  }

  return meta.redirect;
}

/** Student/parent get the cyan accent chip; everyone else indigo (§2). */
export function isYouthRole(role: Role | null): boolean {
  return role === "STUDENT" || role === "PARENT";
}

/* ── Institution dashboard helpers ──────────────────────────────────────── */

/** The 18 institution roles served from <tenant>.shikshasync.me. */
export const INSTITUTION_ROLES = PRIORITY.filter(
  (r) => !(ROLE_MAP[r]?.external ?? false),
) as InstitutionRole[];

/**
 * Staff roles an Institution Admin may invite or grant — the institution
 * roles minus the console owner (INSTITUTION_ADMIN) and the two non-staff
 * audiences (STUDENT, PARENT; students have their own creation flow).
 * Derived from INSTITUTION_ROLES so the dropdown can never drift from the
 * role map again (e.g. ACADEMIC_COORDINATOR was once missing).
 */
export const STAFF_INVITABLE_ROLES = INSTITUTION_ROLES.filter(
  (r) => r !== "INSTITUTION_ADMIN" && r !== "STUDENT" && r !== "PARENT",
);

export function isInstitutionRole(role: string): role is InstitutionRole {
  return (INSTITUTION_ROLES as string[]).includes(role);
}

/** "TEACHER" → "teacher" (the /[role]/dashboard segment). */
export function roleToSlug(role: Role): string {
  const meta = ROLE_MAP[role] ?? DEFAULT_META;
  // Derive from the single source of truth so slugs can't drift.
  return meta.redirect.split("/").filter(Boolean)[0] ?? "dashboard";
}

/** "teacher" → "TEACHER". Returns null for unknown segments. */
export function slugToRole(slug: string): InstitutionRole | null {
  const normalised = slug.toLowerCase();
  return (
    INSTITUTION_ROLES.find((r) => roleToSlug(r) === normalised) ?? null
  );
}

/** Short chip label, e.g. "Teacher" (the roleLabel minus " Access"). */
export function roleChip(role: Role | null): string {
  return roleLabel(role).replace(/ Access$/, "");
}
