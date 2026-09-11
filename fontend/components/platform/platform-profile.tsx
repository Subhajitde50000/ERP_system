"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Building2,
  CheckCircle2,
  Clock,
  ExternalLink,
  KeyRound,
  Layers,
  LayoutDashboard,
  LifeBuoy,
  Lock,
  Mail,
  Receipt,
  ScrollText,
  Settings,
  Shield,
  ShieldCheck,
  TrendingUp,
  User,
  UserCheck,
  UserCircle,
  UsersRound,
  Wallet,
} from "lucide-react";

import { Card } from "@/components/dashboard/primitives";
import { usePlatformAuth } from "@/hooks/use-platform-auth";
import { useOwnerAuth } from "@/hooks/use-owner-auth";
import { usePlatformSession } from "@/hooks/use-platform-session";
import { changePlatformPassword, updatePlatformProfile } from "@/lib/auth";
import { changeOwnerPassword, updateOwnerProfile } from "@/lib/owner";
import { PLATFORM_ROLE_LABELS } from "@/lib/platform";
import type { PlatformRole } from "@/types/auth";

interface RoleMetadata {
  label: string;
  badgeClass: string;
  avatarGradient: string;
  icon: typeof ShieldCheck;
  department: string;
  clearanceLevel: string;
  scopeSummary: string;
  responsibilities: { title: string; description: string }[];
  quickLinks: { label: string; href: string; icon: typeof LayoutDashboard }[];
}

const ROLE_METADATA: Record<PlatformRole, RoleMetadata> = {
  SUPER_ADMIN: {
    label: "Super Admin",
    badgeClass: "bg-purple-100 text-purple-800 border-purple-200",
    avatarGradient: "from-purple-600 to-indigo-700",
    icon: ShieldCheck,
    department: "Platform Engineering & Operations",
    clearanceLevel: "Level 5 — Root Administrator",
    scopeSummary:
      "Full administrative oversight over all tenants, system catalog, global billing settings, and platform staff accounts.",
    responsibilities: [
      {
        title: "Tenant Governance",
        description: "Provision, activate, suspend, and configure institutions across all regions.",
      },
      {
        title: "Catalog & Pricing",
        description: "Manage subscription plans, feature packages, pricing tiers, and quotas.",
      },
      {
        title: "Platform User Administration",
        description: "Provision and manage access for support, sales, and finance personnel.",
      },
      {
        title: "Global Audit & Compliance",
        description: "Review immutable system audit logs for administrative actions and security events.",
      },
    ],
    quickLinks: [
      { label: "Dashboard", href: "/platform/dashboard", icon: LayoutDashboard },
      { label: "Institutions", href: "/platform/institutions", icon: Building2 },
      { label: "Plans", href: "/platform/plans", icon: Layers },
      { label: "Platform Users", href: "/platform/platform-users", icon: UsersRound },
      { label: "Audit Logs", href: "/platform/audit-logs", icon: ScrollText },
      { label: "Settings", href: "/platform/settings", icon: Settings },
    ],
  },
  SUPPORT_STAFF: {
    label: "Support Staff",
    badgeClass: "bg-sky-100 text-sky-800 border-sky-200",
    avatarGradient: "from-sky-600 to-blue-700",
    icon: LifeBuoy,
    department: "Customer Success & Operations",
    clearanceLevel: "Level 3 — Support Specialist",
    scopeSummary:
      "Assigned to handle customer inquiries, technical troubleshooting, diagnostic inspections, and support ticket resolutions.",
    responsibilities: [
      {
        title: "Ticket Resolution Desk",
        description: "Respond to and resolve customer and institution support queries in real time.",
      },
      {
        title: "Tenant Diagnostics",
        description: "Inspect tenant configurations and module status to assist troubleshooting.",
      },
      {
        title: "Escalation Routing",
        description: "Escalate complex infrastructure or billing disputes to platform administrators.",
      },
      {
        title: "Customer Communications",
        description: "Maintain official support dialogues with platform owners and institutional admins.",
      },
    ],
    quickLinks: [
      { label: "Support Desk", href: "/platform/support/dashboard", icon: LifeBuoy },
      { label: "Tickets Queue", href: "/platform/support/tickets", icon: LifeBuoy },
      { label: "Tenant Directory", href: "/platform/institutions", icon: Building2 },
    ],
  },
  SALES_EXECUTIVE: {
    label: "Sales Executive",
    badgeClass: "bg-emerald-100 text-emerald-800 border-emerald-200",
    avatarGradient: "from-emerald-600 to-teal-700",
    icon: TrendingUp,
    department: "Growth & Institutional Sales",
    clearanceLevel: "Level 3 — Sales Executive",
    scopeSummary:
      "Responsible for prospective institution trials, pipeline conversions, subscription expansions, and customer onboarding.",
    responsibilities: [
      {
        title: "Trial Pipeline Oversight",
        description: "Monitor active institutional trial accounts, usage metrics, and expiration dates.",
      },
      {
        title: "Plan Conversion",
        description: "Convert qualifying institutional trials into paid annual and monthly subscriptions.",
      },
      {
        title: "Subscription Tracking",
        description: "Review subscription renewals, expansions, and tier upgrade opportunities.",
      },
      {
        title: "Onboarding Assistance",
        description: "Guide prospective school and college owners through platform setup.",
      },
    ],
    quickLinks: [
      { label: "Sales Dashboard", href: "/platform/sales/dashboard", icon: TrendingUp },
      { label: "Trials Pipeline", href: "/platform/sales/trials", icon: Layers },
      { label: "Subscriptions", href: "/platform/sales/subscriptions", icon: Receipt },
    ],
  },
  FINANCE_MANAGER: {
    label: "Finance Manager",
    badgeClass: "bg-amber-100 text-amber-800 border-amber-200",
    avatarGradient: "from-amber-600 to-yellow-700",
    icon: Wallet,
    department: "Financial Operations & Accounts",
    clearanceLevel: "Level 4 — Finance Manager",
    scopeSummary:
      "Responsible for platform invoices, payment gateway reconciliation, revenue reporting, and taxation compliance.",
    responsibilities: [
      {
        title: "Invoicing Operations",
        description: "Issue, audit, and track platform-wide customer invoices and billing statements.",
      },
      {
        title: "Payment Reconciliation",
        description: "Reconcile successful and failed transactions against Stripe/Razorpay gateways.",
      },
      {
        title: "Revenue Analytics",
        description: "Analyze Monthly Recurring Revenue (MRR), Annual Recurring Revenue (ARR), and churn.",
      },
      {
        title: "Financial Governance",
        description: "Ensure multi-tenant tax breakdowns and audit trails are properly logged.",
      },
    ],
    quickLinks: [
      { label: "Billing Console", href: "/platform/billing", icon: Wallet },
      { label: "Invoices Ledger", href: "/platform/invoices", icon: Receipt },
      { label: "Platform Overview", href: "/platform/dashboard", icon: LayoutDashboard },
    ],
  },
  OWNER: {
    label: "Platform Owner",
    badgeClass: "bg-indigo-100 text-indigo-800 border-indigo-200",
    avatarGradient: "from-indigo-600 to-violet-700",
    icon: Building2,
    department: "Organization Ownership",
    clearanceLevel: "Account Owner — Multi-Institution",
    scopeSummary:
      "Primary organization holder with full authority over owned institutions, billing methods, and subscription licenses.",
    responsibilities: [
      {
        title: "Multi-Institution Ownership",
        description: "Create, launch, and govern institutions associated with your customer account.",
      },
      {
        title: "Billing & Subscriptions",
        description: "Manage subscription plans, payment methods, and download official invoices.",
      },
      {
        title: "Institution Staff Provisioning",
        description: "Access institution administrator portals with dedicated single sign-on links.",
      },
      {
        title: "Support Inquiries",
        description: "Open high-priority support tickets directly with the platform engineering team.",
      },
    ],
    quickLinks: [
      { label: "My Institutions", href: "/platform/my-institutions", icon: Building2 },
      { label: "Billing & Plans", href: "/platform/billing", icon: Wallet },
      { label: "Invoices", href: "/platform/invoices", icon: Receipt },
      { label: "Support Tickets", href: "/platform/tickets", icon: LifeBuoy },
    ],
  },
};

export function PlatformProfile({ role }: { role: PlatformRole }) {
  const session = usePlatformSession();
  const staffAuth = usePlatformAuthSafe();
  const ownerAuth = useOwnerAuthSafe();

  const isOwner = role === "OWNER";
  const meta = ROLE_METADATA[role] || ROLE_METADATA.SUPER_ADMIN;
  const RoleIcon = meta.icon;

  // Resolve user info from live context or fallback preview
  const liveUser = isOwner
    ? ownerAuth?.owner
      ? {
          name: ownerAuth.owner.name,
          email: ownerAuth.owner.email,
          createdAt: ownerAuth.owner.createdAt,
          lastLoginAt: ownerAuth.owner.lastLoginAt,
          isVerified: ownerAuth.owner.isEmailVerified,
        }
      : null
    : staffAuth?.user
      ? {
          name: staffAuth.user.name,
          email: staffAuth.user.email,
          createdAt: "2024-01-15T00:00:00Z",
          lastLoginAt: staffAuth.user.lastLoginAt,
          isVerified: true,
        }
      : null;

  const defaultDemoName = {
    SUPER_ADMIN: "Vikram Malhotra",
    SUPPORT_STAFF: "Nandini Sharma",
    SALES_EXECUTIVE: "Rohit Verma",
    FINANCE_MANAGER: "Sanjay Singhania",
    OWNER: "Rahul Roy",
  }[role];

  const defaultDemoEmail = {
    SUPER_ADMIN: "vikram.admin@shikshasync.me",
    SUPPORT_STAFF: "nandini.support@shikshasync.me",
    SALES_EXECUTIVE: "rohit.sales@shikshasync.me",
    FINANCE_MANAGER: "sanjay.finance@shikshasync.me",
    OWNER: "rahul.owner@acme-edu.com",
  }[role];

  const displayName = liveUser?.name ?? session?.name ?? defaultDemoName;
  const displayEmail = liveUser?.email ?? session?.email ?? defaultDemoEmail;
  const isEmailVerified = liveUser?.isVerified ?? true;
  const lastLoginText = liveUser?.lastLoginAt
    ? formatDate(liveUser.lastLoginAt)
    : "Active now (Current session)";

  // Display Name Edit State
  const [nameInput, setNameInput] = useState(displayName);
  const [isUpdatingName, setIsUpdatingName] = useState(false);
  const [nameStatus, setNameStatus] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // Password Change State
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [passwordStatus, setPasswordStatus] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const handleUpdateName = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = nameInput.trim();
    if (trimmed.length < 2) {
      setNameStatus({
        type: "error",
        message: "Name must be at least 2 characters long.",
      });
      return;
    }

    setIsUpdatingName(true);
    setNameStatus(null);

    try {
      if (isOwner && ownerAuth?.owner) {
        await updateOwnerProfile(trimmed);
        await ownerAuth.refresh();
      } else if (!isOwner && staffAuth?.user) {
        await updatePlatformProfile(trimmed);
        await staffAuth.refresh();
      }
      setNameStatus({
        type: "success",
        message: "Your profile display name has been updated successfully.",
      });
    } catch (err: unknown) {
      const errorMsg =
        err instanceof Error ? err.message : "Failed to update profile name.";
      setNameStatus({ type: "error", message: errorMsg });
    } finally {
      setIsUpdatingName(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordStatus(null);

    if (!currentPassword) {
      setPasswordStatus({
        type: "error",
        message: "Please enter your current password.",
      });
      return;
    }
    if (newPassword.length < 8) {
      setPasswordStatus({
        type: "error",
        message: "New password must be at least 8 characters long.",
      });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordStatus({
        type: "error",
        message: "New password and confirmation do not match.",
      });
      return;
    }

    setIsChangingPassword(true);

    try {
      if (isOwner && ownerAuth?.owner) {
        await changeOwnerPassword(currentPassword, newPassword);
      } else if (!isOwner && staffAuth?.user) {
        await changePlatformPassword(currentPassword, newPassword);
      }
      setPasswordStatus({
        type: "success",
        message:
          "Password changed successfully. All other active sessions have been invalidated.",
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: unknown) {
      const errorMsg =
        err instanceof Error ? err.message : "Failed to change password.";
      setPasswordStatus({ type: "error", message: errorMsg });
    } finally {
      setIsChangingPassword(false);
    }
  };

  const fieldClass =
    "h-10 w-full min-w-0 rounded-lg border border-border bg-white px-3 text-[13px] text-foreground transition focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20";
  const labelClass =
    "mb-1 block text-[11px] font-medium uppercase tracking-wide text-muted-foreground";

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6 pb-12">
      {/* ── Top Hero Profile Banner ── */}
      <Card className="overflow-hidden border border-border bg-white p-6 sm:p-8 shadow-sm">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-5">
            <div
              className={`flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${meta.avatarGradient} text-2xl font-bold text-white shadow-md ring-4 ring-white`}
            >
              {displayName.charAt(0).toUpperCase()}
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2.5">
                <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">
                  {displayName}
                </h1>
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-0.5 text-xs font-semibold ${meta.badgeClass}`}
                >
                  <RoleIcon className="h-3.5 w-3.5" />
                  {meta.label}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                <span className="inline-flex items-center gap-1.5">
                  <Mail className="h-4 w-4" />
                  {displayEmail}
                </span>
                <span>•</span>
                <span className="inline-flex items-center gap-1 text-emerald-600 font-medium">
                  <CheckCircle2 className="h-4 w-4" />
                  {isEmailVerified ? "Verified Account" : "Unverified"}
                </span>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                {meta.scopeSummary}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 border-t border-border pt-4 sm:border-0 sm:pt-0">
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-xs font-medium text-foreground">
              <Shield className="h-3.5 w-3.5 text-muted-foreground" />
              {meta.clearanceLevel}
            </span>
          </div>
        </div>
      </Card>

      {/* ── Role & Clearance Overview Grid ── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-4 border-border">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-accent/10 p-2.5 text-accent">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Access Tier
              </p>
              <p className="mt-0.5 text-sm font-bold text-foreground">
                {PLATFORM_ROLE_LABELS[role]}
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4 border-border">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-emerald-500/10 p-2.5 text-emerald-600">
              <UserCheck className="h-5 w-5" />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Status
              </p>
              <p className="mt-0.5 text-sm font-bold text-emerald-600">
                Active & Authorized
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4 border-border">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-blue-500/10 p-2.5 text-blue-600">
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Department
              </p>
              <p className="mt-0.5 truncate text-sm font-bold text-foreground">
                {meta.department}
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4 border-border">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-purple-500/10 p-2.5 text-purple-600">
              <Clock className="h-5 w-5" />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Last Activity
              </p>
              <p className="mt-0.5 truncate text-sm font-bold text-foreground">
                {lastLoginText}
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* ── Main Content Columns ── */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left 2 Columns: Forms & Permissions */}
        <div className="space-y-6 lg:col-span-2">
          {/* Display Name Edit Card */}
          <Card className="p-6 border-border">
            <div className="flex items-center justify-between border-b border-border pb-4">
              <div>
                <h2 className="font-display text-base font-bold text-foreground">
                  Personal Information
                </h2>
                <p className="text-xs text-muted-foreground">
                  Manage your display name and public platform profile
                </p>
              </div>
              <User className="h-5 w-5 text-muted-foreground" />
            </div>

            {nameStatus && (
              <div
                className={`mt-4 rounded-lg p-3 text-xs font-medium ${
                  nameStatus.type === "success"
                    ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                    : "bg-red-50 text-red-800 border border-red-200"
                }`}
              >
                {nameStatus.message}
              </div>
            )}

            <form onSubmit={handleUpdateName} className="mt-4 space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="pf-name" className={labelClass}>
                    Display Name
                  </label>
                  <input
                    id="pf-name"
                    type="text"
                    className={fieldClass}
                    value={nameInput}
                    onChange={(e) => setNameInput(e.target.value)}
                    minLength={2}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="pf-email" className={labelClass}>
                    Email Address
                  </label>
                  <input
                    id="pf-email"
                    type="email"
                    className={`${fieldClass} bg-muted/40 cursor-not-allowed text-muted-foreground`}
                    value={displayEmail}
                    disabled
                  />
                </div>
              </div>

              <div className="flex items-center justify-end pt-2">
                <button
                  type="submit"
                  disabled={isUpdatingName}
                  className="inline-flex h-9 items-center rounded-lg bg-accent px-4 text-xs font-semibold text-white shadow-sm transition hover:bg-accent-hover disabled:opacity-50"
                >
                  {isUpdatingName ? "Saving Changes…" : "Save Changes"}
                </button>
              </div>
            </form>
          </Card>

          {/* Security & Password Change Card */}
          <Card className="p-6 border-border">
            <div className="flex items-center justify-between border-b border-border pb-4">
              <div>
                <h2 className="font-display text-base font-bold text-foreground">
                  Security & Password
                </h2>
                <p className="text-xs text-muted-foreground">
                  Update your platform login password. This will terminate all
                  other active sessions.
                </p>
              </div>
              <Lock className="h-5 w-5 text-muted-foreground" />
            </div>

            {passwordStatus && (
              <div
                className={`mt-4 rounded-lg p-3 text-xs font-medium ${
                  passwordStatus.type === "success"
                    ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                    : "bg-red-50 text-red-800 border border-red-200"
                }`}
              >
                {passwordStatus.message}
              </div>
            )}

            <form onSubmit={handleChangePassword} className="mt-4 space-y-4">
              <div>
                <label htmlFor="pf-current-pw" className={labelClass}>
                  Current Password
                </label>
                <input
                  id="pf-current-pw"
                  type="password"
                  className={fieldClass}
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="pf-new-pw" className={labelClass}>
                    New Password (min 8 chars)
                  </label>
                  <input
                    id="pf-new-pw"
                    type="password"
                    className={fieldClass}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="••••••••••••"
                    minLength={8}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="pf-confirm-pw" className={labelClass}>
                    Confirm New Password
                  </label>
                  <input
                    id="pf-confirm-pw"
                    type="password"
                    className={fieldClass}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••••••"
                    minLength={8}
                    required
                  />
                </div>
              </div>

              <div className="flex items-center justify-between pt-2">
                <p className="text-[11px] text-muted-foreground">
                  Password must include letters, numbers, and at least 8
                  characters.
                </p>
                <button
                  type="submit"
                  disabled={isChangingPassword}
                  className="inline-flex h-9 items-center rounded-lg bg-accent px-4 text-xs font-semibold text-white shadow-sm transition hover:bg-accent-hover disabled:opacity-50"
                >
                  {isChangingPassword ? "Updating…" : "Change Password"}
                </button>
              </div>
            </form>
          </Card>

          {/* Role Capabilities Matrix */}
          <Card className="p-6 border-border">
            <div className="flex items-center justify-between border-b border-border pb-4">
              <div>
                <h2 className="font-display text-base font-bold text-foreground">
                  Role Capabilities & Granted Scope
                </h2>
                <p className="text-xs text-muted-foreground">
                  Operational authorizations assigned to your {meta.label} account
                </p>
              </div>
              <KeyRound className="h-5 w-5 text-muted-foreground" />
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {meta.responsibilities.map((r, idx) => (
                <div
                  key={idx}
                  className="rounded-lg border border-border/80 bg-muted/20 p-3.5"
                >
                  <div className="flex items-start gap-2.5">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                    <div>
                      <h3 className="text-xs font-bold text-foreground">
                        {r.title}
                      </h3>
                      <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
                        {r.description}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Right 1 Column: Quick Actions & System Info */}
        <div className="space-y-6">
          {/* Quick Consoles Navigation Card */}
          <Card className="p-5 border-border">
            <h3 className="font-display text-sm font-bold text-foreground">
              Direct Role Consoles
            </h3>
            <p className="text-xs text-muted-foreground">
              Jump directly to workspaces associated with your clearance
            </p>

            <div className="mt-4 space-y-1.5">
              {meta.quickLinks.map((link) => {
                const Icon = link.icon;
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className="flex items-center justify-between rounded-lg border border-transparent p-2.5 text-xs font-medium text-foreground transition hover:border-border hover:bg-muted/50"
                  >
                    <div className="flex items-center gap-2.5">
                      <Icon className="h-4 w-4 text-accent" />
                      <span>{link.label}</span>
                    </div>
                    <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
                  </Link>
                );
              })}
            </div>
          </Card>

          {/* Account & Session Security Card */}
          <Card className="p-5 border-border">
            <h3 className="font-display text-sm font-bold text-foreground">
              Active Session Details
            </h3>
            <p className="text-xs text-muted-foreground">
              Security telemetry for this browser session
            </p>

            <div className="mt-4 divide-y divide-border text-xs">
              <div className="flex items-center justify-between py-2">
                <span className="text-muted-foreground">Authentication Protocol</span>
                <span className="font-medium text-foreground">JWT Bearer (HS256)</span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-muted-foreground">Session Expiration</span>
                <span className="font-medium text-foreground">15 Minutes (Sliding)</span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-muted-foreground">Access Realm</span>
                <span className="font-medium text-foreground">Platform Root (shikshasync.me)</span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-muted-foreground">2FA Enforcement</span>
                <span className="font-medium text-emerald-600 font-semibold">Enabled</span>
              </div>
            </div>
          </Card>

          {/* Role Switching / Preview Helper for Testing */}
          <Card className="p-5 border-border bg-slate-50">
            <div className="flex items-center gap-2">
              <UserCircle className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-xs font-bold text-foreground">
                Role Preview Switcher
              </h3>
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Quickly preview how the profile page renders for other platform roles:
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {(
                [
                  ["SUPER_ADMIN", "Super Admin"],
                  ["SUPPORT_STAFF", "Support"],
                  ["SALES_EXECUTIVE", "Sales"],
                  ["FINANCE_MANAGER", "Finance"],
                  ["OWNER", "Owner"],
                ] as const
              ).map(([rKey, rLabel]) => (
                <Link
                  key={rKey}
                  href={`/platform/profile?role=${rKey}`}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
                    role === rKey
                      ? "bg-primary text-white"
                      : "bg-white border border-border text-foreground hover:bg-muted"
                  }`}
                >
                  {rLabel}
                </Link>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function formatDate(isoDate?: string | null): string {
  if (!isoDate) return "N/A";
  try {
    const d = new Date(isoDate);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return isoDate;
  }
}

/** Safe accessor that does not throw when context is absent in previews. */
function usePlatformAuthSafe() {
  try {
    return usePlatformAuth();
  } catch {
    return null;
  }
}

/** Safe accessor that does not throw when context is absent in previews. */
function useOwnerAuthSafe() {
  try {
    return useOwnerAuth();
  } catch {
    return null;
  }
}
