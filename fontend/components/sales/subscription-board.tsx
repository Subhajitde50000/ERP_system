"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  Ban,
  RefreshCw,
  Wallet,
} from "lucide-react";

import { cn, formatDate, rupees } from "@/lib/utils";
import { compactINR, SUBSCRIPTION_LABELS, SUBSCRIPTION_TONE } from "@/lib/platform";
import {
  CYCLE_LABELS,
  planDirection,
  isRenewingSoon,
  planFit,
  planPrice,
  RENEWAL_WINDOW_DAYS,
  toMrr,
} from "@/lib/sales";
import { FormAlert } from "@/components/auth/form-alert";
import { Card, EmptyState, Kpi, TONE_BG, TONE_TEXT } from "@/components/dashboard/primitives";
import { Button } from "@/components/ui/button";
import {
  FilterBar,
  FilterSelect,
  FilterTabs,
  ResultCount,
  SearchBox,
} from "@/components/platform/list-filters";
import { PlanFitNotes } from "./trial-bits";
import type { PlanRow } from "@/types/platform";
import type {
  BillingCycle,
  SubscriptionAccount,
  SubscriptionBoard as Board,
} from "@/types/sales";

/**
 * C-SL-04 — Subscription Management.
 * "All active subscriptions: renew, upgrade, downgrade"
 *
 * All three verbs are here, and each one is guarded by the thing that makes
 * it dangerous:
 *
 * - **Renew** is only offered where there is something to renew — a cancelled
 *   account has no next period, and offering the button anyway is how an exec
 *   ends up filing a ticket about a dead control.
 * - **Upgrade** is free to take.
 * - **Downgrade** is checked against the tenant's actual seats, storage and
 *   modules first: moving Nova University from Premium to Basic would strand
 *   8,100 students and switch four modules off. `planFit` blocks it.
 *
 * §4.1 gives Sales exactly this — "upgrade / downgrade subscription plans" —
 * and withholds institution academic data, so every column here is
 * commercial. Suspension is shown because it explains a zero MRR, but
 * lifting it is the Super Admin's call (C-SA-03), not this page's.
 */
export function SubscriptionBoard({
  board,
  plans,
}: {
  board: Board;
  plans: PlanRow[];
}) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [plan, setPlan] = useState("ALL");
  const [cycle, setCycle] = useState("ALL");
  const [editing, setEditing] = useState<SubscriptionAccount | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();

    return board.accounts.filter((a) => {
      // Same predicate as the KPI above it — a tab whose count disagrees
      // with the card it sits under is worse than no tab.
      if (status === "RENEWING") {
        if (!isRenewingSoon(a)) return false;
      } else if (status === "ATTENTION") {
        if (a.status !== "PAST_DUE" && a.isActive) return false;
      } else if (status !== "ALL" && a.status !== status) return false;

      if (plan !== "ALL" && a.planSlug !== plan) return false;
      if (cycle !== "ALL" && a.cycle !== cycle) return false;
      if (!q) return true;

      return (
        a.tenantName.toLowerCase().includes(q) ||
        a.tenantSlug.toLowerCase().includes(q) ||
        (a.paymentReference ?? "").toLowerCase().includes(q)
      );
    });
  }, [board.accounts, query, status, plan, cycle]);

  const counts = {
    all: board.accounts.length,
    renewing: board.renewalsDue,
    attention: board.accounts.filter((a) => a.status === "PAST_DUE" || !a.isActive)
      .length,
    cancelled: board.accounts.filter((a) => a.status === "CANCELLED").length,
  };

  // Recomputed from what's on screen, so a filter changes the total it labels
  const shownMrr = shown.reduce((a, s) => a + s.mrr, 0);

  return (
    <div className="mx-auto w-full min-w-0 max-w-6xl">
      <div className="mb-4 min-w-0">
        <h1 className="font-display text-[22px] font-bold text-foreground">
          Subscriptions
        </h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Every paying institution, soonest renewal first.
        </p>
      </div>

      {notice && (
        <FormAlert variant="info" className="mb-4">
          {notice}
        </FormAlert>
      )}

      <div className="mb-4 grid min-w-0 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="MRR" value={compactINR(board.mrr)} hint="recurring, ex-trials" />
        <Kpi label="ARR" value={compactINR(board.arr)} hint="MRR × 12" />
        <Kpi
          label={`Renewing in ${RENEWAL_WINDOW_DAYS}d`}
          value={String(board.renewalsDue)}
          hint="confirm before they lapse"
          tone={board.renewalsDue > 0 ? "warning" : "muted"}
        />
        <Kpi
          label="Past due"
          value={String(board.pastDue)}
          hint="payment failed"
          tone={board.pastDue > 0 ? "danger" : "success"}
        />
      </div>

      <Card className="min-w-0 p-5 sm:p-6">
        <SearchBox
          id="sub-search"
          label="Search subscriptions"
          value={query}
          onChange={setQuery}
          placeholder="Search by institution, subdomain or payment reference…"
        />

        <FilterBar>
          <FilterTabs
            label="Filter by state"
            value={status}
            onChange={setStatus}
            tabs={[
              ["ALL", "All", counts.all],
              ["RENEWING", "Renewing", counts.renewing],
              ["ATTENTION", "Needs attention", counts.attention],
              ["CANCELLED", "Cancelled", counts.cancelled],
            ]}
          />

          <FilterSelect
            id="sub-plan"
            label="Filter by plan"
            value={plan}
            onChange={setPlan}
            allLabel="All plans"
            options={plans.map((p) => [p.slug, p.name])}
          />

          <FilterSelect
            id="sub-cycle"
            label="Filter by cycle"
            value={cycle}
            onChange={setCycle}
            allLabel="Any cycle"
            options={[
              ["MONTHLY", "Monthly"],
              ["YEARLY", "Yearly"],
            ]}
          />
        </FilterBar>

        <ResultCount count={shown.length} noun="subscription" />

        {shown.length === 0 ? (
          <EmptyState message="No subscriptions match these filters." />
        ) : (
          <>
            {/* ≥768px: table */}
            <div className="-mx-1 hidden overflow-x-auto px-1 md:block">
              <table className="w-full min-w-[820px] border-collapse">
                <caption className="sr-only">
                  Subscriptions — {shown.length} rows, {rupees(shownMrr)} monthly
                </caption>
                <thead>
                  <tr className="border-b border-border">
                    {[
                      ["Institution", false],
                      ["Plan", false],
                      ["Cycle", false],
                      ["MRR", true],
                      ["Renews", false],
                      ["State", false],
                      ["", false],
                    ].map(([h, numeric], i) => (
                      <th
                        key={i}
                        scope="col"
                        className={cn(
                          "py-2 pr-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground",
                          numeric ? "text-right" : "text-left",
                        )}
                      >
                        {h as string}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((a) => (
                    <tr key={a.tenantId} className="border-b border-border last:border-0">
                      <th scope="row" className="py-3 pr-3 text-left align-top">
                        <span className="block truncate text-[13px] font-medium text-foreground">
                          {a.tenantName}
                        </span>
                        <span className="block truncate font-mono text-[11px] font-normal text-muted-foreground">
                          {a.tenantSlug}.shikshasync.me
                        </span>
                      </th>
                      <td className="py-3 pr-3 align-top text-[12px] text-muted-foreground">
                        {a.planName}
                        {a.seatPct !== null && (
                          <span
                            className={cn(
                              "block text-[10px]",
                              a.seatPct >= 90
                                ? "text-destructive-text"
                                : "text-muted-foreground",
                            )}
                          >
                            {a.seatPct}% of seats
                          </span>
                        )}
                      </td>
                      <td className="py-3 pr-3 align-top text-[12px] text-muted-foreground">
                        {CYCLE_LABELS[a.cycle]}
                        <span className="block text-[10px]">
                          {compactINR(a.amount)}/{a.cycle === "YEARLY" ? "yr" : "mo"}
                        </span>
                      </td>
                      <td className="py-3 pr-3 text-right align-top text-[13px] tabular-nums text-foreground">
                        {a.mrr > 0 ? rupees(a.mrr) : "—"}
                      </td>
                      <td className="py-3 pr-3 align-top text-[12px] text-muted-foreground">
                        <RenewalCell account={a} />
                      </td>
                      <td className="py-3 pr-3 align-top">
                        <StateChip account={a} />
                      </td>
                      <td className="py-3 text-right align-top">
                        <button
                          type="button"
                          onClick={() => setEditing(a)}
                          className="rounded-field border border-border px-2.5 py-1 text-[11px] font-medium text-[#475569] transition-colors hover:border-accent hover:text-accent focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15"
                        >
                          Manage
                          <span className="sr-only"> {a.tenantName}</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* <768px: stacked */}
            <ul className="min-w-0 divide-y divide-border border-t border-border md:hidden">
              {shown.map((a) => (
                <li key={a.tenantId} className="min-w-0 py-3">
                  <div className="flex min-w-0 items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-medium text-foreground">
                        {a.tenantName}
                      </p>
                      <p className="truncate font-mono text-[11px] text-muted-foreground">
                        {a.tenantSlug}.shikshasync.me
                      </p>
                    </div>
                    <StateChip account={a} />
                  </div>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {a.planName} · {CYCLE_LABELS[a.cycle]} ·{" "}
                    {a.mrr > 0 ? `${rupees(a.mrr)}/mo` : "no revenue"}
                  </p>
                  <div className="mt-1.5 flex min-w-0 flex-wrap items-center justify-between gap-2">
                    <span className="text-[11px] text-muted-foreground">
                      <RenewalCell account={a} />
                    </span>
                    <button
                      type="button"
                      onClick={() => setEditing(a)}
                      className="shrink-0 rounded-field border border-border px-2.5 py-1 text-[11px] font-medium text-[#475569] transition-colors hover:border-accent hover:text-accent focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15"
                    >
                      Manage
                      <span className="sr-only"> {a.tenantName}</span>
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <p className="mt-4 flex min-w-0 items-start gap-1.5 text-[12px] text-muted-foreground">
        <Wallet className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        Yearly commitments are divided by 12 so both cycles can be summed.
        A suspended or cancelled institution contributes nothing.
      </p>

      {editing && (
        <ManageDialog
          account={editing}
          plans={plans}
          onClose={() => setEditing(null)}
          onDone={(message) => {
            setEditing(null);
            setNotice(message);
          }}
        />
      )}
    </div>
  );
}


/**
 * Suspension beats billing status: `is_active` (§4.2) and
 * `subscriptions.status` (§4.4) are independent, and a suspended tenant is
 * locked out whatever it is paying. Mirrors `tenantState()` on the Super
 * Admin side so one institution can't read differently in two consoles.
 */
function StateChip({ account }: { account: SubscriptionAccount }) {
  const suspended = !account.isActive;
  const tone = suspended ? "danger" : SUBSCRIPTION_TONE[account.status];
  const label = suspended ? "Suspended" : SUBSCRIPTION_LABELS[account.status];

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        TONE_BG[tone],
        tone === "muted" ? "text-[#475569]" : TONE_TEXT[tone],
      )}
    >
      {label}
    </span>
  );
}

function RenewalCell({ account }: { account: SubscriptionAccount }) {
  if (account.renewsAt === null) {
    return <span className="text-muted-foreground">No renewal</span>;
  }

  const d = account.daysToRenewal ?? 0;
  // Highlight only what the KPI counts. A suspended tenant still carries a
  // period end date, but amber-flagging it says "chase this" about an
  // account that bills nothing — and contradicts the "Renewing 2" tab
  // directly above. `isRenewingSoon` is the single predicate.
  const soon = isRenewingSoon(account);

  return (
    <>
      <span className={cn(soon && "font-medium text-[#B45309]")}>
        {formatDate(account.renewsAt)}
      </span>
      <span className="block text-[10px] text-muted-foreground">
        {d < 0 ? `${Math.abs(d)}d overdue` : `in ${d}d`}
        {!account.isActive && " · suspended"}
      </span>
    </>
  );
}

/**
 * Renew / upgrade / downgrade, in one dialog.
 *
 * Escape lives on `document`, not on the dialog div: a div that never holds
 * focus never receives a keydown, so `onKeyDown` there would be dead code.
 */
function ManageDialog({
  account,
  plans,
  onClose,
  onDone,
}: {
  account: SubscriptionAccount;
  plans: PlanRow[];
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [planSlug, setPlanSlug] = useState(account.planSlug);
  const [cycle, setCycle] = useState<BillingCycle>(account.cycle);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  const current = plans.find((p) => p.slug === account.planSlug);
  const target = plans.find((p) => p.slug === planSlug);
  const fit = target ? planFit(target, account) : null;
  const direction = planDirection(current, target);
  const changed = planSlug !== account.planSlug || cycle !== account.cycle;

  const nextAmount = target ? planPrice(target, cycle) : 0;
  const nextMrr = toMrr(nextAmount, cycle);
  const mrrDelta = nextMrr - account.mrr;

  async function act(kind: "RENEW" | "CHANGE") {
    if (busy) return;
    setBusy(true);
    // TODO(Dev-A): PATCH /api/v1/platform/subscriptions/:id — writes the new
    // `subscriptions` row (§4.4) and repoints `tenants.plan_id` (§4.2).
    await new Promise((r) => setTimeout(r, 700));
    setBusy(false);
    onDone(
      kind === "RENEW"
        ? `PATCH /platform/subscriptions/${account.tenantId} { action: "renew", cycle: "${account.cycle}" } — API not connected yet (Dev-A, C-SL-04).`
        : `PATCH /platform/subscriptions/${account.tenantId} { plan: "${planSlug}", cycle: "${cycle}" } — API not connected yet (Dev-A, C-SL-04).`,
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="manage-title"
      className="fixed inset-0 z-50 flex items-end justify-center overflow-y-auto bg-primary/40 p-0 sm:items-center sm:p-6"
    >
      <div className="w-full max-w-lg rounded-t-card border border-border bg-white p-6 text-left shadow-card sm:rounded-card">
        <h2
          id="manage-title"
          className="font-display text-[16px] font-bold text-foreground"
        >
          {account.tenantName}
        </h2>
        <p className="mt-0.5 text-[12px] text-muted-foreground">
          {account.planName} · {CYCLE_LABELS[account.cycle]} ·{" "}
          {account.mrr > 0 ? `${rupees(account.mrr)}/mo` : "no revenue"}
          {account.renewsAt && ` · renews ${formatDate(account.renewsAt)}`}
        </p>

        {/* Renew: only where there is a next period to renew into */}
        <div className="mt-4 min-w-0 rounded-field border border-border p-4">
          <h3 className="text-[13px] font-semibold text-foreground">Renew</h3>
          {account.renewsAt === null ? (
            <p className="mt-1 text-[12px] text-muted-foreground">
              This subscription is cancelled — there is no period to renew.
              Converting them again starts a new one.
            </p>
          ) : (
            <>
              <p className="mt-1 text-[12px] text-muted-foreground">
                Extends by one {account.cycle === "YEARLY" ? "year" : "month"} from{" "}
                {formatDate(account.renewsAt)} at {rupees(account.amount)}.
              </p>
              <Button
                type="button"
                variant="secondary"
                loading={busy}
                loadingText="Working…"
                onClick={() => act("RENEW")}
                className="mt-3 h-9 w-auto px-3 text-[13px]"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                Renew now
              </Button>
            </>
          )}
        </div>

        {/* Upgrade / downgrade */}
        <div className="mt-3 min-w-0 rounded-field border border-border p-4">
          <h3 className="text-[13px] font-semibold text-foreground">
            Change plan
          </h3>

          <div className="mt-2 grid min-w-0 gap-3 sm:grid-cols-2">
            <div className="min-w-0">
              <label
                htmlFor="manage-plan"
                className="text-[12px] font-medium text-[#334155]"
              >
                Plan
              </label>
              <select
                id="manage-plan"
                value={planSlug}
                onChange={(e) => {
                  setPlanSlug(e.target.value);
                  // An acknowledgement is per-plan, not sticky
                  setAck(false);
                }}
                className="mt-1 h-10 w-full min-w-0 rounded-field border border-border bg-white px-3 text-[13px] transition focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent/15"
              >
                {plans.map((p) => (
                  <option key={p.slug} value={p.slug}>
                    {p.name} — {compactINR(planPrice(p, cycle))}/
                    {cycle === "YEARLY" ? "yr" : "mo"}
                  </option>
                ))}
              </select>
            </div>

            <div className="min-w-0">
              <label
                htmlFor="manage-cycle"
                className="text-[12px] font-medium text-[#334155]"
              >
                Cycle
              </label>
              <select
                id="manage-cycle"
                value={cycle}
                onChange={(e) => setCycle(e.target.value as BillingCycle)}
                className="mt-1 h-10 w-full min-w-0 rounded-field border border-border bg-white px-3 text-[13px] transition focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent/15"
              >
                <option value="MONTHLY">Monthly</option>
                <option value="YEARLY">Yearly</option>
              </select>
            </div>
          </div>

          {changed && (
            <div className="mt-3 min-w-0">
              <p className="flex min-w-0 flex-wrap items-center gap-2 text-[12px]">
                {direction === "UPGRADE" && (
                  <span className="inline-flex shrink-0 items-center gap-1 font-semibold text-success-text">
                    <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
                    Upgrade
                  </span>
                )}
                {direction === "DOWNGRADE" && (
                  <span className="inline-flex shrink-0 items-center gap-1 font-semibold text-[#B45309]">
                    <ArrowDownRight className="h-3.5 w-3.5" aria-hidden="true" />
                    Downgrade
                  </span>
                )}
                <span className="text-muted-foreground">
                  {rupees(nextAmount)} per{" "}
                  {cycle === "YEARLY" ? "year" : "month"} ·{" "}
                  <span
                    className={cn(
                      "font-medium",
                      mrrDelta > 0
                        ? "text-success-text"
                        : mrrDelta < 0
                          ? "text-destructive-text"
                          : "text-muted-foreground",
                    )}
                  >
                    {mrrDelta > 0 && "+"}
                    {rupees(mrrDelta)}/mo
                  </span>
                </span>
              </p>

              {fit && (
                <div className="mt-2">
                  <PlanFitNotes fit={fit} />
                </div>
              )}

              {/* A downgrade that drops a module is allowed (§4.1) but must
                  be deliberate — otherwise the customer discovers it. */}
              {fit?.ok && fit.needsAck && (
                <label
                  htmlFor="ack-downgrade"
                  className="mt-2 flex min-w-0 items-start gap-2.5 rounded-field border border-warning-border bg-warning-light px-3 py-2.5"
                >
                  <input
                    id="ack-downgrade"
                    type="checkbox"
                    checked={ack}
                    onChange={(e) => setAck(e.target.checked)}
                    className="mt-0.5 h-4 w-4 shrink-0 rounded border-[#B45309] text-accent focus:ring-3 focus:ring-accent/15"
                  />
                  <span className="min-w-0 text-[11px] leading-5 text-[#B45309]">
                    {account.tenantName} has agreed to lose these modules.
                    Their data is kept and returns on upgrade.
                  </span>
                </label>
              )}
            </div>
          )}

          <div className="mt-3 flex flex-wrap justify-end gap-2">
            <Button
              type="button"
              loading={busy}
              loadingText="Working…"
              disabled={!changed || !fit?.ok || (fit.needsAck && !ack)}
              onClick={() => act("CHANGE")}
              className="h-9 w-auto px-3 text-[13px]"
            >
              Apply change
            </Button>
          </div>

          {changed && !fit?.ok && (
            <p className="mt-2 flex min-w-0 items-start gap-1.5 text-[11px] text-destructive-text">
              <Ban className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
              This plan cannot carry {account.tenantName} as it stands — the
              change would break them on day one.
            </p>
          )}
        </div>

        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-10 items-center rounded-field border border-border px-4 text-[13px] font-medium text-[#475569] transition-colors hover:bg-background focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
