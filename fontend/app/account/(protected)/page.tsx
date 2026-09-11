"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  Building2,
  CreditCard,
  Loader2,
  Plus,
  Sparkles,
  Wallet,
} from "lucide-react";

import { useOwnerAuth } from "@/hooks/use-owner-auth";
import { Button } from "@/components/ui/button";
import {
  fetchBillingSummary,
  fetchOwnerInstitutions,
} from "@/lib/owner";
import { tenantHost } from "@/lib/platform-shared";
import { formatINR } from "@/lib/signup";
import type { BillingSummary, OwnerInstitution } from "@/types/owner";

/**
 * Build the institution login URL at click-time from window.location.
 *
 * We cannot use a static href derived from NEXT_PUBLIC_ROOT_DOMAIN because
 * that env value is embedded at compile time and may be stale (e.g. still
 * "shikshasync.me" when the dev server is running on localhost). Reading
 * window.location at the moment of the click is always correct.
 */
function openInstitution(slug: string) {
  const hostname = window.location.hostname;
  const port = window.location.port;
  let url: string;
  if (hostname === "localhost" || hostname === "127.0.0.1" || hostname === "0.0.0.0") {
    const domain = port ? `localhost:${port}` : "localhost";
    url = `http://${slug}.${domain}/login`;
  } else {
    // On abc.shikshasync.me → root = shikshasync.me
    const parts = hostname.split(".");
    const root = parts.length >= 2 ? parts.slice(-2).join(".") : hostname;
    url = `https://${slug}.${root}/login`;
  }
  window.open(url, "_blank", "noreferrer");
}

const SUB_LABELS: Record<string, string> = {
  TRIAL: "Trial",
  ACTIVE: "Active",
  PAST_DUE: "Past due",
  CANCELLED: "Cancelled",
};

/**
 * Platform dashboard — "My Institutions" + a billing snapshot, with the
 * primary CTA to create another institution.
 */
export default function AccountDashboardPage() {
  const { owner } = useOwnerAuth();
  const [institutions, setInstitutions] = useState<OwnerInstitution[] | null>(null);
  const [summary, setSummary] = useState<BillingSummary | null>(null);

  const load = useCallback(async () => {
    const [insts, sum] = await Promise.allSettled([fetchOwnerInstitutions(), fetchBillingSummary()]);
    if (insts.status === "fulfilled") setInstitutions(insts.value);
    else setInstitutions([]);
    if (sum.status === "fulfilled") setSummary(sum.value);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const loading = institutions === null;

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-display text-2xl font-extrabold tracking-tight text-primary">
            Welcome, {owner?.name.split(" ")[0] ?? "there"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage every institution you own from one place.
          </p>
        </div>
        <Link href="/account/institutions/new">
          <Button>
            <Plus className="h-4 w-4" aria-hidden="true" /> Create New Institution
          </Button>
        </Link>
      </header>

      {/* Billing snapshot */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={<Building2 className="h-4 w-4" />}
          label="Institutions"
          value={summary ? String(summary.totalInstitutions) : "—"}
        />
        <StatCard
          icon={<Sparkles className="h-4 w-4" />}
          label="Active subscriptions"
          value={summary ? String(summary.activeSubscriptions) : "—"}
          hint={summary ? `${summary.trialing} on trial` : undefined}
        />
        <StatCard
          icon={<CreditCard className="h-4 w-4" />}
          label="Outstanding"
          value={summary ? formatINR(summary.outstanding) : "—"}
        />
        <StatCard
          icon={<Wallet className="h-4 w-4" />}
          label="Lifetime spend"
          value={summary ? formatINR(summary.lifetimeSpend) : "—"}
        />
      </section>

      {/* My Institutions */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-lg font-bold text-primary">My Institutions</h2>
          <Link href="/account/billing" className="text-sm font-medium text-accent hover:underline">
            View billing
          </Link>
        </div>

        {loading ? (
          <div className="flex items-center justify-center rounded-card border border-border bg-white py-16 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          </div>
        ) : institutions && institutions.length === 0 ? (
          <EmptyState />
        ) : (
          <ul className="grid gap-3">
            {institutions?.map((inst) => (
              <li
                key={inst.id}
                className="flex flex-col gap-3 rounded-card border border-border bg-white p-5 transition hover:border-accent-border hover:shadow-card sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="flex h-9 w-9 items-center justify-center rounded-field bg-accent-light text-accent">
                      <Building2 className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate font-display text-base font-bold text-primary">
                        {inst.name}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {tenantHost(inst.slug)} · {inst.planName ?? "No plan"}
                      </p>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <StatusPill status={inst.subscriptionStatus} isActive={inst.isActive} />
                  <button
                    type="button"
                    onClick={() => openInstitution(inst.slug)}
                    className="inline-flex items-center gap-1 text-sm font-semibold text-accent hover:underline"
                  >
                    Open <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-card border border-border bg-white p-5">
      <div className="flex items-center gap-2 text-muted-foreground">
        <span className="text-accent">{icon}</span>
        <span className="text-xs font-semibold uppercase tracking-wide">{label}</span>
      </div>
      <p className="mt-2 font-display text-2xl font-extrabold text-primary">{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function StatusPill({
  status,
  isActive,
}: {
  status: string | null;
  isActive: boolean;
}) {
  const label = !isActive ? "Suspended" : status ? SUB_LABELS[status] ?? status : "No plan";
  const tone = !isActive || status === "PAST_DUE" || status === "CANCELLED"
    ? "bg-destructive-light text-destructive-text"
    : status === "TRIAL"
      ? "bg-warning-light text-warning-text"
      : "bg-success-light text-success-text";
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${tone}`}>{label}</span>;
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-4 rounded-card border border-dashed border-border bg-white px-6 py-14 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent-light text-accent">
        <Building2 className="h-6 w-6" aria-hidden="true" />
      </span>
      <div>
        <h3 className="font-display text-lg font-bold text-primary">No institutions yet</h3>
        <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
          Create your first institution — choose a plan, claim a subdomain, and it&apos;s
          provisioned automatically.
        </p>
      </div>
      <Link href="/account/institutions/new">
        <Button>
          <Plus className="h-4 w-4" aria-hidden="true" /> Create your first institution
        </Button>
      </Link>
    </div>
  );
}
