"use client";

/**
 * Live Owner consoles — the shikshasync.me account-holder's seven pages.
 *
 * Same shape as `consoles.tsx` on the Super Admin side: a hook for the data,
 * `<Live>` for loading/error, `useAction` for mutations. Nothing here
 * re-implements those; the shared primitives live in `./live` and
 * `hooks/use-resource`.
 *
 * The backend (`/api/v1/owner/*`) and the client (`lib/owner.ts`) already
 * existed and were complete — these pages were the only part still rendering
 * `platform-data.ts` fixtures, with a hardcoded `rahul@gmail.com` and an
 * invented "2 support tickets".
 *
 * Everything is scoped to the signed-in owner by the API itself: the routes
 * resolve the owner from the JWT, so one account can never read another's
 * institutions, invoices or tickets.
 */

import { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Building2,
  FileText,
  LifeBuoy,
  Plus,
  Receipt,
  UserCircle,
  Wallet,
} from "lucide-react";

import { cn, formatDate } from "@/lib/utils";
import { compactINR } from "@/lib/platform";
import { changeOwnerPassword, createOwnerTicket, updateOwnerProfile } from "@/lib/owner";
import { Card, Chip, EmptyState } from "@/components/dashboard/primitives";
import { StatsCard } from "@/components/dashboard/stats-card";
import { useOwnerAuth } from "@/hooks/use-owner-auth";
import {
  useOwnerBilling,
  useOwnerInstitutions,
  useOwnerInvoices,
  useOwnerPayments,
  useOwnerSubscriptions,
  useOwnerTickets,
} from "@/hooks/use-owner-console";
import { ActionBar, Live, useAction } from "./live";
import type { Stat } from "@/types/dashboard";
import type { OwnerInstitution, SupportTicket } from "@/types/owner";

/* ── Shared bits ─────────────────────────────────────────────────────────── */

const STATUS_TONE: Record<string, "success" | "accent" | "warning" | "muted"> = {
  ACTIVE: "success",
  TRIAL: "accent",
  PAST_DUE: "warning",
  CANCELLED: "muted",
  PAID: "success",
  OPEN: "accent",
  IN_PROGRESS: "warning",
  RESOLVED: "success",
  CLOSED: "muted",
};

/** Page heading — identical on all seven Owner pages, so written once. */
function OwnerHeader({
  icon: Icon,
  title,
  subtitle,
  action,
}: {
  icon: typeof Building2;
  title: string;
  subtitle: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex min-w-0 flex-wrap items-start justify-between gap-3">
      <div className="flex min-w-0 items-start gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent-light text-accent">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h1 className="font-display text-[22px] font-bold text-foreground">
            {title}
          </h1>
          <p className="mt-1 text-[13px] text-muted-foreground">{subtitle}</p>
        </div>
      </div>
      {action}
    </div>
  );
}

/** Build the institution login URL at click-time from window.location. */
function openInstitution(slug: string) {
  const hostname = window.location.hostname;
  const port = window.location.port;
  let url: string;
  if (hostname === "localhost" || hostname === "127.0.0.1" || hostname === "0.0.0.0") {
    const domain = port ? `localhost:${port}` : "localhost";
    url = `http://${slug}.${domain}/login`;
  } else {
    const parts = hostname.split(".");
    const root = parts.length >= 2 ? parts.slice(-2).join(".") : hostname;
    url = `https://${slug}.${root}/login`;
  }
  window.open(url, "_blank", "noreferrer");
}

/** One institution row — used by the dashboard and My Institutions. */
function InstitutionRow({ inst }: { inst: OwnerInstitution }) {
  return (
    <li className="flex min-w-0 items-center gap-3 py-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-foreground">
          {inst.name}
        </p>
        <p className="truncate font-mono text-[11px] text-muted-foreground">
          {inst.slug}
          {inst.planName ? ` · ${inst.planName}` : ""}
        </p>
      </div>
      <Chip tone={STATUS_TONE[inst.subscriptionStatus ?? ""] ?? "muted"}>
        {inst.isActive ? (inst.subscriptionStatus ?? "—") : "SUSPENDED"}
      </Chip>
      <button
        type="button"
        onClick={() => openInstitution(inst.slug)}
        className="inline-flex shrink-0 items-center gap-1 rounded text-[12px] font-semibold text-accent hover:underline bg-transparent border-none p-0 cursor-pointer"
      >
        Go to <ArrowRight className="h-3 w-3" aria-hidden="true" />
      </button>
    </li>
  );
}

/** Money/date table — invoices and payments differ only by their columns. */
function DataTable<T>({
  rows,
  columns,
  empty,
}: {
  rows: T[];
  columns: { head: string; cell: (row: T) => React.ReactNode; right?: boolean }[];
  empty: string;
}) {
  if (rows.length === 0) return <EmptyState message={empty} />;
  return (
    <div className="min-w-0 overflow-x-auto">
      <table className="w-full min-w-[520px] border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-border text-left">
            {columns.map((c) => (
              <th
                key={c.head}
                className={cn(
                  "py-2 pr-3 font-medium text-muted-foreground",
                  c.right && "text-right",
                )}
              >
                {c.head}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border last:border-0">
              {columns.map((c) => (
                <td
                  key={c.head}
                  className={cn("py-2.5 pr-3 text-foreground", c.right && "text-right")}
                >
                  {c.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Dashboard ───────────────────────────────────────────────────────────── */

export function LiveOwnerDashboard() {
  const institutions = useOwnerInstitutions();
  const billing = useOwnerBilling();
  const tickets = useOwnerTickets();
  const { owner } = useOwnerAuth();

  return (
    <Live resource={institutions} label="Loading your institutions…">
      {(mine) => {
        const b = billing.data;
        const openTickets = (tickets.data ?? []).filter(
          (t) => t.status === "OPEN" || t.status === "IN_PROGRESS",
        ).length;

        const stats: Stat[] = [
          {
            label: "My institutions",
            value: String(b?.totalInstitutions ?? mine.length),
            icon: Building2,
            tone: "accent",
          },
          {
            label: "Lifetime spend",
            value: compactINR(b?.lifetimeSpend ?? 0),
            icon: Wallet,
            tone: "success",
          },
          {
            label: "Outstanding",
            value: compactINR(b?.outstanding ?? 0),
            icon: FileText,
            tone: b?.outstanding ? "warning" : "success",
          },
          {
            label: "Open tickets",
            value: String(openTickets),
            icon: LifeBuoy,
            tone: openTickets ? "warning" : "muted",
          },
        ];

        return (
          <div className="mx-auto w-full min-w-0 max-w-6xl">
            <OwnerHeader
              icon={Building2}
              title="Platform dashboard"
              subtitle={
                owner
                  ? `Signed in as ${owner.email}. Manage every institution from one account.`
                  : "Manage every institution from one account."
              }
              action={
                <Link
                  href="/signup"
                  className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent transition-colors hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15"
                >
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  Create new institution
                </Link>
              }
            />

            <div className="mb-4 grid min-w-0 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {stats.map((s) => (
                <StatsCard key={s.label} stat={s} />
              ))}
            </div>

            <Card className="min-w-0 p-5 sm:p-6">
              <h2 className="mb-1 font-display text-[15px] font-bold text-foreground">
                My institutions
              </h2>
              {mine.length === 0 ? (
                <EmptyState message="No institutions yet. Create your first one to get started." />
              ) : (
                <ul className="divide-y divide-border border-t border-border">
                  {mine.map((i) => (
                    <InstitutionRow key={i.id} inst={i} />
                  ))}
                </ul>
              )}
            </Card>
          </div>
        );
      }}
    </Live>
  );
}

/* ── My Institutions ─────────────────────────────────────────────────────── */

export function LiveOwnerInstitutions() {
  const institutions = useOwnerInstitutions();

  return (
    <Live resource={institutions} label="Loading your institutions…">
      {(mine) => (
        <div className="mx-auto w-full min-w-0 max-w-5xl">
          <OwnerHeader
            icon={Building2}
            title="My Institutions"
            subtitle="Institutions owned by this platform account."
            action={
              <Link
                href="/signup"
                className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent transition-colors hover:bg-accent-hover"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                New institution
              </Link>
            }
          />
          <Card className="min-w-0 p-5 sm:p-6">
            {mine.length === 0 ? (
              <EmptyState message="No institutions yet." />
            ) : (
              <ul className="divide-y divide-border border-t border-border">
                {mine.map((i) => (
                  <InstitutionRow key={i.id} inst={i} />
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </Live>
  );
}

/* ── Billing ─────────────────────────────────────────────────────────────── */

export function LiveOwnerBilling() {
  const billing = useOwnerBilling();
  const payments = useOwnerPayments();

  return (
    <Live resource={billing} label="Loading billing…">
      {(b) => (
        <div className="mx-auto w-full min-w-0 max-w-5xl">
          <OwnerHeader
            icon={Wallet}
            title="Billing"
            subtitle="Spend and renewals across every institution you own."
          />

          <div className="mb-4 grid min-w-0 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {(
              [
                ["Institutions", String(b.totalInstitutions), Building2, "accent"],
                ["Active subscriptions", String(b.activeSubscriptions), Receipt, "success"],
                ["Lifetime spend", compactINR(b.lifetimeSpend), Wallet, "success"],
                [
                  "Outstanding",
                  compactINR(b.outstanding),
                  FileText,
                  b.outstanding ? "warning" : "success",
                ],
              ] as const
            ).map(([label, value, icon, tone]) => (
              <StatsCard
                key={label}
                stat={{ label, value, icon, tone } as Stat}
              />
            ))}
          </div>

          <Card className="mb-4 min-w-0 p-5 sm:p-6">
            <dl className="grid min-w-0 gap-x-6 gap-y-3 sm:grid-cols-3">
              {[
                ["Trialing", String(b.trialing)],
                ["Next renewal", formatDate(b.nextRenewalAt)],
                ["Currency", b.currency],
              ].map(([k, v]) => (
                <div key={k} className="min-w-0">
                  <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    {k}
                  </dt>
                  <dd className="mt-0.5 truncate text-[13px] text-foreground">{v}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card className="min-w-0 p-5 sm:p-6">
            <h2 className="mb-3 font-display text-[15px] font-bold text-foreground">
              Payment history
            </h2>
            <DataTable
              rows={payments.data ?? []}
              empty="No payments recorded yet."
              columns={[
                { head: "Date", cell: (p) => formatDate(p.receivedAt ?? p.createdAt) },
                { head: "Institution", cell: (p) => p.tenantName ?? "—" },
                { head: "Method", cell: (p) => p.method },
                {
                  head: "Status",
                  cell: (p) => (
                    <Chip tone={STATUS_TONE[p.status] ?? "muted"}>{p.status}</Chip>
                  ),
                },
                { head: "Amount", right: true, cell: (p) => compactINR(p.amount) },
              ]}
            />
          </Card>
        </div>
      )}
    </Live>
  );
}

/* ── Subscriptions ───────────────────────────────────────────────────────── */

export function LiveOwnerSubscriptions() {
  const subs = useOwnerSubscriptions();

  return (
    <Live resource={subs} label="Loading subscriptions…">
      {(rows) => (
        <div className="mx-auto w-full min-w-0 max-w-5xl">
          <OwnerHeader
            icon={Receipt}
            title="Subscriptions"
            subtitle="Plan renewals across all owned institutions."
          />
          <Card className="min-w-0 p-5 sm:p-6">
            <DataTable
              rows={rows}
              empty="No subscriptions yet."
              columns={[
                { head: "Institution", cell: (s) => s.tenantName },
                { head: "Plan", cell: (s) => s.planName },
                {
                  head: "Status",
                  cell: (s) => (
                    <Chip tone={STATUS_TONE[s.status] ?? "muted"}>{s.status}</Chip>
                  ),
                },
                { head: "Started", cell: (s) => formatDate(s.startsAt) },
                { head: "Renews", cell: (s) => formatDate(s.endsAt) },
                { head: "Amount", right: true, cell: (s) => compactINR(s.amount) },
              ]}
            />
          </Card>
        </div>
      )}
    </Live>
  );
}

/* ── Invoices ────────────────────────────────────────────────────────────── */

export function LiveOwnerInvoices() {
  const invoices = useOwnerInvoices();

  return (
    <Live resource={invoices} label="Loading invoices…">
      {(rows) => (
        <div className="mx-auto w-full min-w-0 max-w-5xl">
          <OwnerHeader
            icon={FileText}
            title="Invoices"
            subtitle="GST invoices for every institution under this account."
          />
          <Card className="min-w-0 p-5 sm:p-6">
            <DataTable
              rows={rows}
              empty="No invoices yet."
              columns={[
                { head: "Number", cell: (i) => <span className="font-mono">{i.invoiceNumber}</span> },
                { head: "Institution", cell: (i) => i.tenantName },
                { head: "Issued", cell: (i) => formatDate(i.issuedAt) },
                {
                  head: "Status",
                  cell: (i) => (
                    <Chip tone={STATUS_TONE[i.status] ?? "muted"}>{i.status}</Chip>
                  ),
                },
                { head: "Paid", right: true, cell: (i) => compactINR(i.amountPaid) },
                { head: "Total", right: true, cell: (i) => compactINR(i.total) },
              ]}
            />
          </Card>
        </div>
      )}
    </Live>
  );
}

/* ── Support tickets ─────────────────────────────────────────────────────── */

const CATEGORIES = ["BILLING", "TECHNICAL", "ACCOUNT", "OTHER"];

export function LiveOwnerTickets() {
  const tickets = useOwnerTickets();
  const institutions = useOwnerInstitutions();
  const action = useAction();
  const [raising, setRaising] = useState(false);

  return (
    <Live resource={tickets} label="Loading tickets…">
      {(rows, resource) => (
        <div className="mx-auto w-full min-w-0 max-w-5xl">
          <OwnerHeader
            icon={LifeBuoy}
            title="Support Tickets"
            subtitle="Raise and track requests without logging into each institution."
            action={
              <button
                type="button"
                onClick={() => setRaising((v) => !v)}
                className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent transition-colors hover:bg-accent-hover"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                New ticket
              </button>
            }
          />

          <ActionBar action={action} />

          {raising && (
            <NewTicket
              institutions={institutions.data ?? []}
              busy={action.busy}
              onCancel={() => setRaising(false)}
              onSubmit={(input) =>
                void action
                  .run(() => createOwnerTicket(input), "Ticket raised — support will reply by email.")
                  .then((ok) => {
                    if (ok) {
                      setRaising(false);
                      void resource.reload();
                    }
                  })
              }
            />
          )}

          <Card className="min-w-0 p-5 sm:p-6">
            {rows.length === 0 ? (
              <EmptyState message="No tickets yet." />
            ) : (
              <ul className="divide-y divide-border border-t border-border">
                {rows.map((t) => (
                  <TicketRow key={t.id} ticket={t} />
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </Live>
  );
}

function TicketRow({ ticket: t }: { ticket: SupportTicket }) {
  return (
    <li className="py-3">
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">
            {t.subject}
          </p>
          <p className="mt-0.5 truncate text-[12px] text-muted-foreground">
            {t.category}
            {t.tenantName ? ` · ${t.tenantName}` : ""} · {formatDate(t.createdAt)}
            {t.messages?.length ? ` · ${t.messages.length} message(s)` : ""}
          </p>
        </div>
        <Chip tone={STATUS_TONE[t.status] ?? "muted"}>{t.status}</Chip>
      </div>
    </li>
  );
}

function NewTicket({
  institutions,
  onSubmit,
  onCancel,
  busy,
}: {
  institutions: OwnerInstitution[];
  onSubmit: (input: {
    subject: string;
    category: string;
    tenantId: string | null;
    message: string;
  }) => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const [subject, setSubject] = useState("");
  const [category, setCategory] = useState("TECHNICAL");
  const [tenantId, setTenantId] = useState("");
  const [message, setMessage] = useState("");

  const field =
    "h-10 w-full min-w-0 rounded-field border border-border bg-white px-3 text-[13px] transition placeholder:text-[#94A3B8] focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent/15";

  return (
    <Card className="mb-4 min-w-0 p-5 sm:p-6">
      <form
        className="grid min-w-0 gap-3 sm:grid-cols-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (subject.trim() && message.trim()) {
            onSubmit({
              subject: subject.trim(),
              category,
              tenantId: tenantId || null,
              message: message.trim(),
            });
          }
        }}
      >
        <div className="min-w-0 sm:col-span-3">
          <label htmlFor="t-subject" className="sr-only">
            Subject
          </label>
          <input
            id="t-subject"
            className={field}
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject"
            required
          />
        </div>
        <div className="min-w-0">
          <label htmlFor="t-category" className="sr-only">
            Category
          </label>
          <select
            id="t-category"
            className={field}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c.charAt(0) + c.slice(1).toLowerCase()}
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-0 sm:col-span-2">
          <label htmlFor="t-tenant" className="sr-only">
            Institution
          </label>
          <select
            id="t-tenant"
            className={field}
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
          >
            <option value="">Not about a specific institution</option>
            {institutions.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-0 sm:col-span-3">
          <label htmlFor="t-message" className="sr-only">
            Message
          </label>
          <textarea
            id="t-message"
            rows={4}
            className="w-full min-w-0 rounded-field border border-border bg-white p-3 text-[13px] transition placeholder:text-[#94A3B8] focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent/15"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Describe the issue…"
            required
          />
        </div>
        <div className="flex gap-2 sm:col-span-3">
          <button
            type="submit"
            disabled={busy}
            className="inline-flex h-10 items-center rounded-field bg-accent px-4 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-60"
          >
            {busy ? "Sending…" : "Raise ticket"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="inline-flex h-10 items-center rounded-field border border-border bg-white px-4 text-sm font-medium text-muted-foreground transition hover:border-accent hover:text-accent"
          >
            Cancel
          </button>
        </div>
      </form>
    </Card>
  );
}

/* ── Profile ─────────────────────────────────────────────────────────────── */

export function LiveOwnerProfile() {
  const { owner, isLoading, refresh } = useOwnerAuth();
  const nameAction = useAction();
  const passwordAction = useAction();
  const [name, setName] = useState("");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");

  const field =
    "h-10 w-full min-w-0 rounded-field border border-border bg-white px-3 text-[13px] transition focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent/15";
  const label =
    "mb-1 block text-[11px] font-medium uppercase tracking-wide text-muted-foreground";

  if (isLoading) {
    return (
      <Card className="mx-auto max-w-3xl p-6 text-center text-[13px] text-muted-foreground">
        Loading profile…
      </Card>
    );
  }

  if (!owner) {
    return (
      <Card className="mx-auto max-w-3xl p-6">
        <EmptyState message="Sign in to your owner account to manage your profile." />
      </Card>
    );
  }

  return (
    <div className="mx-auto w-full min-w-0 max-w-3xl">
      <OwnerHeader
        icon={UserCircle}
        title="Profile"
        subtitle="Your name, email verification and account security."
      />

      <Card className="mb-4 min-w-0 p-5 sm:p-6">
        <dl className="grid min-w-0 gap-x-6 gap-y-3 sm:grid-cols-2">
          {[
            ["Email", owner.email],
            ["Verified", owner.isEmailVerified ? "Yes" : "Not verified"],
            ["Member since", formatDate(owner.createdAt)],
            ["Last sign-in", formatDate(owner.lastLoginAt)],
          ].map(([k, v]) => (
            <div key={k} className="min-w-0">
              <dt className={label}>{k}</dt>
              <dd className="mt-0.5 truncate text-[13px] text-foreground">{v}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card className="mb-4 min-w-0 p-5 sm:p-6">
        <h2 className="mb-3 font-display text-[15px] font-bold text-foreground">
          Display name
        </h2>
        <ActionBar action={nameAction} />
        <form
          className="flex min-w-0 flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const value = (name || owner.name).trim();
            if (value.length < 2) return;
            void nameAction
              .run(() => updateOwnerProfile(value), "Name updated.")
              .then((ok) => {
                if (ok) void refresh();
              });
          }}
        >
          <div className="min-w-0 flex-1">
            <label htmlFor="p-name" className={label}>
              Name
            </label>
            <input
              id="p-name"
              className={field}
              value={name || owner.name}
              onChange={(e) => setName(e.target.value)}
              minLength={2}
            />
          </div>
          <button
            type="submit"
            disabled={nameAction.busy}
            className="inline-flex h-10 items-center rounded-field bg-accent px-4 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-60"
          >
            {nameAction.busy ? "Saving…" : "Save"}
          </button>
        </form>
      </Card>

      <Card className="min-w-0 p-5 sm:p-6">
        <h2 className="mb-3 font-display text-[15px] font-bold text-foreground">
          Change password
        </h2>
        <ActionBar action={passwordAction} />
        <form
          className="grid min-w-0 gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!current || next.length < 8) return;
            void passwordAction
              .run(
                () => changeOwnerPassword(current, next),
                "Password changed — other sessions were signed out.",
              )
              .then((ok) => {
                if (ok) {
                  setCurrent("");
                  setNext("");
                }
              });
          }}
        >
          <div className="min-w-0">
            <label htmlFor="p-current" className={label}>
              Current password
            </label>
            <input
              id="p-current"
              type="password"
              className={field}
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
            />
          </div>
          <div className="min-w-0">
            <label htmlFor="p-next" className={label}>
              New password (min 8)
            </label>
            <input
              id="p-next"
              type="password"
              className={field}
              value={next}
              onChange={(e) => setNext(e.target.value)}
              minLength={8}
              required
            />
          </div>
          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={passwordAction.busy}
              className="inline-flex h-10 items-center rounded-field bg-accent px-4 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-60"
            >
              {passwordAction.busy ? "Changing…" : "Change password"}
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
}
