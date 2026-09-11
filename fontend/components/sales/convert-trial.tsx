"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Check, Mail, Sparkles } from "lucide-react";

import { cn, formatDate, rupees } from "@/lib/utils";
import {
  CYCLE_LABELS,
  planDirection,
  planFit,
  planPrice,
  prorate,
  yearlySavingPct,
} from "@/lib/sales";
import { planLimit } from "@/lib/platform";
import { moduleLabel } from "@/lib/platform-shared";
import { OPTIONAL_MODULES } from "@/lib/session";
import { FormAlert } from "@/components/auth/form-alert";
import { Card } from "@/components/dashboard/primitives";
import { Button } from "@/components/ui/button";
import { PlanFitNotes, UrgencyChip } from "./trial-bits";
import type { PlanRow } from "@/types/platform";
import type { BillingCycle, ConvertContext } from "@/types/sales";

/**
 * C-SL-03 — Convert Trial to Paid.
 * "Select plan, set billing start, send welcome email"
 *
 * The three things the doc names are the three sections here, in that order.
 * Everything else on the page exists to stop a bad conversion:
 *
 * - **The plan is checked against the tenant as it stands today.** Selling
 *   Standard to an institution with 2,400 students means their next enrolment
 *   fails and the first thing the new customer does is raise a ticket. A plan
 *   that doesn't fit is disabled, not merely warned about.
 * - **Billing cannot start in the past** — §4.4 `starts_at` is what the first
 *   invoice is drawn from.
 * - **The exact charge is quoted before the button**, prorated when billing
 *   starts mid-period, because that is the number the exec has just promised
 *   on the phone.
 *
 * §4.1 gives Sales "upgrade / downgrade subscription plans" but "cannot
 * access institution academic data" — so this page changes `subscriptions`
 * (§4.4) and `tenants.plan_id` (§4.2), and shows seats and storage only
 * because those are what the plan is priced on.
 */
export function ConvertTrial({
  context,
  plans,
}: {
  context: ConvertContext;
  plans: PlanRow[];
}) {
  const { trial } = context;

  const [planSlug, setPlanSlug] = useState(context.recommendedPlanSlug);
  const [cycle, setCycle] = useState<BillingCycle>("YEARLY");
  const [startDate, setStartDate] = useState(context.defaultBillingStart);
  const [sendWelcome, setSendWelcome] = useState(true);
  const [poNumber, setPoNumber] = useState("");
  const [ackModuleLoss, setAckModuleLoss] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const plan = plans.find((p) => p.slug === planSlug);
  const currentPlan = plans.find((p) => p.slug === trial.planSlug);
  const fit = useMemo(
    () => (plan ? planFit(plan, trial) : null),
    [plan, trial],
  );

  const amount = plan ? planPrice(plan, cycle) : 0;
  const periodDays = cycle === "YEARLY" ? 365 : 30;

  /**
   * First charge. Billing that starts later than today bills the whole
   * period from that date — nothing is prorated, because nothing has been
   * consumed yet. Proration only applies when the exec back-dates the start
   * into a period already running, which the date floor prevents; the
   * calculation stays so a mid-period upgrade can reuse it.
   */
  const firstCharge = useMemo(() => {
    const start = Date.parse(`${startDate}T00:00:00Z`);
    const today = Date.parse(`${context.today}T00:00:00Z`);
    if (Number.isNaN(start) || start >= today) return amount;
    const elapsed = Math.round((today - start) / 86_400_000);
    return prorate(amount, periodDays - elapsed, periodDays);
  }, [startDate, context.today, amount, periodDays]);

  const direction = planDirection(currentPlan, plan);

  function validate() {
    const e: Record<string, string> = {};

    if (!plan) e.plan = "Choose a plan";
    else if (!fit?.ok)
      e.plan = `${plan.name} cannot carry this institution as it stands`;
    else if (fit.needsAck && !ackModuleLoss)
      e.plan = "Confirm you have agreed the modules they will lose";

    if (!startDate) e.start = "Set the billing start date";
    else if (Number.isNaN(Date.parse(`${startDate}T00:00:00Z`)))
      e.start = "That isn't a valid date";
    // Validated here, not with a native `min` attribute: `min` suppresses the
    // form's own message and the field silently refuses to submit instead.
    else if (
      Date.parse(`${startDate}T00:00:00Z`) <
      Date.parse(`${context.today}T00:00:00Z`)
    )
      e.start = "Billing cannot start in the past";

    return e;
  }

  async function onSubmit(ev: React.FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    if (busy) return;

    const e = validate();
    setErrors(e);
    if (Object.keys(e).length) return;

    setBusy(true);
    // TODO(Dev-A): POST /api/v1/platform/trials/:id/convert — writes the
    // paid `subscriptions` row (§4.4), clears `tenants.trial_ends_at` (§4.2),
    // repoints `plan_id`, and queues the welcome email through SES.
    await new Promise((r) => setTimeout(r, 800));
    setBusy(false);
    setDone(
      `POST /platform/trials/${trial.tenantId}/convert { plan: "${planSlug}", cycle: "${cycle}", starts_at: "${startDate}", welcome_email: ${sendWelcome}${poNumber ? `, po: "${poNumber}"` : ""} } — API not connected yet (Dev-A, C-SL-03).`,
    );
  }

  return (
    <div className="mx-auto w-full min-w-0 max-w-3xl">
      <Link
        href="/platform/sales/trials"
        className="mb-3 inline-flex items-center gap-1.5 rounded text-[13px] font-medium text-muted-foreground transition-colors hover:text-accent focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        All trials
      </Link>

      <div className="mb-1 flex min-w-0 flex-wrap items-start gap-2">
        <h1 className="min-w-0 font-display text-[22px] font-bold text-foreground">
          Convert {trial.name}
        </h1>
        <div className="pt-1.5">
          <UrgencyChip trial={trial} />
        </div>
      </div>
      <p className="mb-4 flex min-w-0 flex-wrap items-center gap-x-2 text-[13px] text-muted-foreground">
        <span className="font-mono">{trial.slug}.shikshasync.me</span>
        <span>· trialling {trial.planName}</span>
        <span>· {trial.contactName}</span>
      </p>

      {done && (
        <FormAlert variant="success" className="mb-4">
          {done}
        </FormAlert>
      )}

      {/* An expired trial is still convertible — say so, don't just show a
          red chip and leave the exec guessing whether the button works. */}
      {trial.daysLeft < 0 && !done && (
        <FormAlert variant="info" className="mb-4">
          This trial expired {Math.abs(trial.daysLeft)} day
          {Math.abs(trial.daysLeft) === 1 ? "" : "s"} ago. Their data is
          retained and converting restores access immediately.
        </FormAlert>
      )}

      <form onSubmit={onSubmit} noValidate className="grid min-w-0 gap-4">
        {/* 1 — Select plan */}
        <Card className="min-w-0 p-5 sm:p-6">
          <fieldset className="min-w-0">
            <legend className="font-display text-[15px] font-bold text-foreground">
              1. Select plan
            </legend>
            <p className="mt-1 text-[12px] text-muted-foreground">
              Checked against their current {trial.studentCount.toLocaleString("en-IN")}{" "}
              students, {trial.teacherCount} teachers, {trial.storageUsedGb} GB
              and {trial.enabledModules.length} enabled modules.
            </p>

            <div className="mt-3 grid min-w-0 gap-3">
              {plans.map((p) => (
                <PlanOption
                  key={p.slug}
                  plan={p}
                  cycle={cycle}
                  selected={planSlug === p.slug}
                  recommended={p.slug === context.recommendedPlanSlug}
                  fit={planFit(p, trial)}
                  onSelect={() => {
                    setPlanSlug(p.slug);
                    // A tick agreed for one plan does not carry to another
                    setAckModuleLoss(false);
                  }}
                />
              ))}
            </div>

            {/* A plan that drops a module they use can still be sold — §4.1
                allows downgrades — but only deliberately. */}
            {fit?.needsAck && (
              <label
                htmlFor="ack-module-loss"
                className="mt-3 flex min-w-0 items-start gap-2.5 rounded-field border border-warning-border bg-warning-light px-3.5 py-3"
              >
                <input
                  id="ack-module-loss"
                  type="checkbox"
                  checked={ackModuleLoss}
                  onChange={(e) => setAckModuleLoss(e.target.checked)}
                  className="mt-0.5 h-4 w-4 shrink-0 rounded border-[#B45309] text-accent focus:ring-3 focus:ring-accent/15"
                />
                <span className="min-w-0 text-[12px] leading-6 text-[#B45309]">
                  {trial.contactName} has agreed to lose the modules listed
                  above. Their data is retained and returns if they upgrade.
                </span>
              </label>
            )}

            {errors.plan && (
              <p className="mt-2 text-[12px] text-destructive-text">
                {errors.plan}
              </p>
            )}
          </fieldset>
        </Card>

        {/* 2 — Set billing start */}
        <Card className="min-w-0 p-5 sm:p-6">
          <h2 className="font-display text-[15px] font-bold text-foreground">
            2. Billing
          </h2>

          <div className="mt-3 grid min-w-0 gap-4 sm:grid-cols-2">
            <div className="min-w-0">
              <span
                id="cycle-label"
                className="text-[13px] font-medium text-[#334155]"
              >
                Cycle
              </span>
              <div
                role="group"
                aria-labelledby="cycle-label"
                className="mt-1.5 flex min-w-0 gap-2"
              >
                {(["MONTHLY", "YEARLY"] as BillingCycle[]).map((c) => (
                  <button
                    key={c}
                    type="button"
                    aria-pressed={cycle === c}
                    onClick={() => setCycle(c)}
                    className={cn(
                      "h-11 min-w-0 flex-1 rounded-field border px-3 text-[13px] font-medium transition focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15",
                      cycle === c
                        ? "border-accent bg-accent-light text-accent"
                        : "border-border bg-white text-muted-foreground hover:border-accent",
                    )}
                  >
                    {CYCLE_LABELS[c]}
                    {c === "YEARLY" && plan && yearlySavingPct(plan) > 0 && (
                      <span className="ml-1 text-[11px] text-success-text">
                        −{yearlySavingPct(plan)}%
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            <div className="min-w-0">
              <label
                htmlFor="billing-start"
                className="text-[13px] font-medium text-[#334155]"
              >
                Billing starts
              </label>
              <input
                id="billing-start"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                aria-invalid={errors.start ? true : undefined}
                aria-describedby={errors.start ? "billing-start-error" : undefined}
                className={cn(
                  "mt-1.5 h-11 w-full min-w-0 rounded-field border bg-white px-3 text-[14px] transition focus:outline-none focus:ring-3",
                  errors.start
                    ? "border-destructive focus:border-destructive focus:ring-destructive/15"
                    : "border-border focus:border-accent focus:ring-accent/15",
                )}
              />
              {errors.start ? (
                <p
                  id="billing-start-error"
                  className="mt-1 text-[12px] text-destructive-text"
                >
                  {errors.start}
                </p>
              ) : (
                <p className="mt-1 text-[12px] text-muted-foreground">
                  {trial.daysLeft > 0
                    ? "Defaults to the day their trial ends, so they keep every day they were promised."
                    : "Their trial has ended, so billing starts today."}
                </p>
              )}
            </div>
          </div>

          <div className="mt-4 min-w-0">
            <label
              htmlFor="po-number"
              className="text-[13px] font-medium text-[#334155]"
            >
              Purchase order number
              <span className="ml-1 font-normal text-muted-foreground">
                (optional)
              </span>
            </label>
            <input
              id="po-number"
              value={poNumber}
              onChange={(e) => setPoNumber(e.target.value)}
              placeholder="Institutions with a finance committee usually need one"
              className="mt-1.5 h-11 w-full min-w-0 rounded-field border border-border bg-white px-3 text-[14px] transition placeholder:text-[#94A3B8] focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent/15"
            />
          </div>

          {/* The quote — what the exec just told them on the phone */}
          <dl className="mt-4 min-w-0 rounded-field bg-background p-4">
            <QuoteRow
              label={`${plan?.name ?? "Plan"} · ${CYCLE_LABELS[cycle].toLowerCase()}`}
              value={`${rupees(amount)} / ${cycle === "YEARLY" ? "year" : "month"}`}
            />
            <QuoteRow
              label="First charge"
              value={rupees(firstCharge)}
              hint={
                firstCharge === amount
                  ? `on ${formatDate(`${startDate}T00:00:00Z`)}`
                  : "prorated for the part-period"
              }
              strong
            />
            <QuoteRow
              label="Recurring revenue"
              value={`${rupees(cycle === "YEARLY" ? Math.round(amount / 12) : amount)} / month`}
              hint={
                cycle === "YEARLY" ? "yearly commitment ÷ 12" : undefined
              }
            />
            {direction !== "SAME" && currentPlan && plan && (
              <QuoteRow
                label="Against their trial plan"
                value={
                  direction === "UPGRADE"
                    ? `Upgrade from ${currentPlan.name}`
                    : `Downgrade from ${currentPlan.name}`
                }
              />
            )}
          </dl>
        </Card>

        {/* 3 — Send welcome email */}
        <Card className="min-w-0 p-5 sm:p-6">
          <h2 className="font-display text-[15px] font-bold text-foreground">
            3. Welcome email
          </h2>

          {/* Explicit id + `for`, not a wrapping label — assistive tech
              resolves a bound label more reliably. */}
          <label
            htmlFor="send-welcome"
            className="mt-3 flex min-w-0 items-start gap-2.5"
          >
            <input
              id="send-welcome"
              type="checkbox"
              checked={sendWelcome}
              onChange={(e) => setSendWelcome(e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 rounded border-border text-accent focus:ring-3 focus:ring-accent/15"
            />
            <span className="min-w-0 text-[13px] text-[#334155]">
              Email {trial.contactName} at{" "}
              <span className="font-medium">{trial.contactEmail}</span>
              <span className="block text-[12px] text-muted-foreground">
                Confirms the plan, the first invoice date and who to contact.
                Their existing sign-ins are unaffected.
              </span>
            </span>
          </label>

          {sendWelcome && (
            <div className="mt-3 min-w-0 rounded-field border border-accent-border bg-accent-light px-3.5 py-3">
              <p className="flex min-w-0 items-start gap-2 text-[12px] leading-6 text-[#3730A3]">
                <Mail className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="min-w-0">
                  <strong className="font-semibold">
                    Welcome to shikshasync.me, {trial.name}
                  </strong>
                  <br />
                  Your {plan?.name} plan starts{" "}
                  {formatDate(`${startDate}T00:00:00Z`)} at {rupees(amount)} per{" "}
                  {cycle === "YEARLY" ? "year" : "month"}. Everything you set up
                  during the trial carries over.
                </span>
              </p>
            </div>
          )}
        </Card>

        {Object.keys(errors).length > 0 && (
          <FormAlert variant="error">
            Check the highlighted fields and try again.
          </FormAlert>
        )}

        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          <Link
            href="/platform/sales/trials"
            className="inline-flex h-11 items-center rounded-field border border-border px-4 text-[14px] font-medium text-[#475569] transition-colors hover:bg-background focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15"
          >
            Cancel
          </Link>
          <Button
            type="submit"
            loading={busy}
            loadingText="Converting…"
            disabled={!fit?.ok || (fit.needsAck && !ackModuleLoss)}
            className="w-auto px-5"
          >
            Convert to paid
          </Button>
        </div>

        {!fit?.ok ? (
          <p className="text-right text-[12px] text-destructive-text">
            {plan?.name} cannot carry this institution — choose a plan that
            fits.
          </p>
        ) : fit.needsAck && !ackModuleLoss ? (
          <p className="text-right text-[12px] text-[#B45309]">
            Confirm the modules they will lose before converting.
          </p>
        ) : null}
      </form>
    </div>
  );
}

/** One selectable plan, with what it would mean for this tenant. */
function PlanOption({
  plan,
  cycle,
  selected,
  recommended,
  fit,
  onSelect,
}: {
  plan: PlanRow;
  cycle: BillingCycle;
  selected: boolean;
  recommended: boolean;
  fit: ReturnType<typeof planFit>;
  onSelect: () => void;
}) {
  const price = planPrice(plan, cycle);

  return (
    <label
      htmlFor={`plan-${plan.slug}`}
      className={cn(
        "flex min-w-0 cursor-pointer items-start gap-3 rounded-field border p-4 transition",
        // The selected card keeps a white body and shows selection through
        // its border and ring. A tint here would put `muted-foreground` at
        // 4.56:1 — passing, but one shade away from failing AA, and this
        // card carries the plan-fit text an exec has to read carefully.
        selected
          ? "border-accent bg-white ring-3 ring-accent/15"
          : "border-border bg-white hover:border-accent",
        !fit.ok && "opacity-70",
      )}
    >
      <input
        id={`plan-${plan.slug}`}
        type="radio"
        name="plan"
        value={plan.slug}
        checked={selected}
        onChange={onSelect}
        className="mt-1 h-4 w-4 shrink-0 border-border text-accent focus:ring-3 focus:ring-accent/15"
      />

      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-[14px] font-semibold text-foreground">
            {plan.name}
          </span>
          {recommended && fit.ok && (
            <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-success-light px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-success-text">
              <Sparkles className="h-2.5 w-2.5" aria-hidden="true" />
              Best fit
            </span>
          )}
          {!fit.ok && (
            <span className="shrink-0 rounded-full bg-destructive-light px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-destructive-text">
              Won&apos;t fit
            </span>
          )}
        </div>

        <p className="mt-0.5 text-[12px] text-muted-foreground">
          {planLimit(plan.maxStudents)} students · {planLimit(plan.maxTeachers)}{" "}
          teachers · {plan.maxStorageGb} GB ·{" "}
          {plan.allowedModules.length} modules
        </p>

        <div className="mt-2 min-w-0">
          <PlanFitNotes fit={fit} />
        </div>

        {/* The optional modules this plan licenses — the only part that
            differs between plans. Listing the 8 core modules too filled the
            card with "Attendance, Examination, Assignment…", which every
            plan includes and nobody is deciding between. */}
        {selected && fit.ok && (
          <p className="mt-2 flex min-w-0 flex-wrap items-center gap-1.5">
            {optionalOf(plan).length === 0 ? (
              <span className="text-[11px] text-muted-foreground">
                Core modules only — no optional modules on this plan.
              </span>
            ) : (
              <>
                <span className="shrink-0 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  Optional
                </span>
                {optionalOf(plan).map((m) => (
                  <span
                    key={m}
                    className="inline-flex shrink-0 items-center gap-0.5 rounded-full bg-white px-2 py-0.5 text-[10px] font-medium text-[#475569] ring-1 ring-border"
                  >
                    <Check
                      className="h-2.5 w-2.5 text-success-text"
                      aria-hidden="true"
                    />
                    {moduleLabel(m)}
                  </span>
                ))}
              </>
            )}
          </p>
        )}
      </div>

      <div className="shrink-0 text-right">
        <p className="text-[14px] font-bold tabular-nums text-foreground">
          {rupees(price)}
        </p>
        <p className="text-[11px] text-muted-foreground">
          per {cycle === "YEARLY" ? "year" : "month"}
        </p>
      </div>
    </label>
  );
}

/** The optional modules a plan licenses — what actually varies between them. */
function optionalOf(plan: PlanRow) {
  return plan.allowedModules.filter((m) => OPTIONAL_MODULES.includes(m));
}

function QuoteRow({
  label,
  value,
  hint,
  strong,
}: {
  label: string;
  value: string;
  hint?: string;
  strong?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 py-1.5",
        strong && "border-y border-border",
      )}
    >
      <dt className="min-w-0 text-[12px] text-muted-foreground">
        {label}
        {hint && <span className="ml-1 text-[11px]">({hint})</span>}
      </dt>
      <dd
        className={cn(
          "shrink-0 tabular-nums",
          strong
            ? "text-[15px] font-bold text-foreground"
            : "text-[13px] font-medium text-[#334155]",
        )}
      >
        {value}
      </dd>
    </div>
  );
}
