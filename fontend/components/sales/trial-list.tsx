"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CalendarClock,
  Mail,
  MapPin,
  Phone,
  StickyNote,
} from "lucide-react";

import { cn, formatDate, rupees } from "@/lib/utils";
import {
  byUrgency,
  CURRENT_EXEC,
  trialCountdown,
  URGENCY_LABELS,
} from "@/lib/sales";
import { Card, EmptyState } from "@/components/dashboard/primitives";
import {
  FilterBar,
  FilterSelect,
  FilterTabs,
  ResultCount,
  SearchBox,
} from "@/components/platform/list-filters";
import { UrgencyChip } from "./trial-bits";
import type { TrialRow } from "@/types/sales";

/**
 * C-SL-02 — Lead / Trial Institutions.
 * "All trial tenants: days left, contact, follow-up notes"
 *
 * The doc names three things this page must carry, and each is given room:
 * **days left** drives the sort and the chip, **contact** is on the card
 * rather than a click away (an exec working a list is about to phone someone),
 * and **follow-up notes** expand in place.
 *
 * Defaults to everything rather than a sub-queue: five trials is a list you
 * read, not one you filter, and hiding the healthy ones is how a trial goes
 * cold unnoticed.
 */
export function TrialList({
  trials,
  initialOwner,
}: {
  trials: TrialRow[];
  /** `?owner=me` from the dashboard KPI deep-link */
  initialOwner?: string;
}) {
  const [query, setQuery] = useState("");
  const [urgency, setUrgency] = useState("ALL");
  const [plan, setPlan] = useState("ALL");
  const [owner, setOwner] = useState(initialOwner === "me" ? "ME" : "ALL");
  const [expanded, setExpanded] = useState<string | null>(null);

  const plans = useMemo(
    () =>
      [...new Map(trials.map((t) => [t.planSlug, t.planName])).entries()].sort(
        (a, b) => a[1].localeCompare(b[1]),
      ),
    [trials],
  );

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();

    return trials
      .filter((t) => {
        if (urgency === "ACTION") {
          if (t.urgency !== "EXPIRED" && t.urgency !== "CRITICAL") return false;
        } else if (urgency !== "ALL" && t.urgency !== urgency) return false;

        if (plan !== "ALL" && t.planSlug !== plan) return false;
        if (owner === "ME" && t.ownerId !== CURRENT_EXEC.id) return false;
        if (owner === "NONE" && t.ownerId !== null) return false;
        if (!q) return true;

        return (
          t.name.toLowerCase().includes(q) ||
          t.slug.toLowerCase().includes(q) ||
          (t.city ?? "").toLowerCase().includes(q) ||
          t.contactEmail.toLowerCase().includes(q)
        );
      })
      .sort(byUrgency);
  }, [trials, query, urgency, plan, owner]);

  // One control, one dimension. The tabs and the plan/owner dropdowns filter
  // different things and combine; two controls bound to the same state would
  // silently contradict each other.
  const counts = {
    all: trials.length,
    action: trials.filter(
      (t) => t.urgency === "EXPIRED" || t.urgency === "CRITICAL",
    ).length,
    soon: trials.filter((t) => t.urgency === "SOON").length,
    healthy: trials.filter((t) => t.urgency === "HEALTHY").length,
  };

  const pipeline = shown.reduce((a, t) => a + t.monthlyValue, 0);

  return (
    <div className="mx-auto w-full min-w-0 max-w-5xl">
      <div className="mb-4 min-w-0">
        <h1 className="font-display text-[22px] font-bold text-foreground">
          Trials
        </h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Every institution evaluating shikshasync.me, closest to expiry first.
        </p>
      </div>

      <Card className="min-w-0 p-5 sm:p-6">
        <SearchBox
          id="trial-search"
          label="Search trials"
          value={query}
          onChange={setQuery}
          placeholder="Search by institution, subdomain, city or contact…"
        />

        <FilterBar>
          <FilterTabs
            label="Filter by urgency"
            value={urgency}
            onChange={setUrgency}
            tabs={[
              ["ALL", "All", counts.all],
              ["ACTION", "Needs action", counts.action],
              ["SOON", URGENCY_LABELS.SOON, counts.soon],
              ["HEALTHY", URGENCY_LABELS.HEALTHY, counts.healthy],
            ]}
          />

          <FilterSelect
            id="trial-plan"
            label="Filter by plan"
            value={plan}
            onChange={setPlan}
            allLabel="Any plan"
            options={plans.map(([slug, name]) => [slug, name])}
          />

          <FilterSelect
            id="trial-owner"
            label="Filter by owner"
            value={owner}
            onChange={setOwner}
            allLabel="Anyone"
            options={[
              ["ME", "Owned by me"],
              ["NONE", "Unassigned"],
            ]}
          />
        </FilterBar>

        <ResultCount count={shown.length} noun="trial" />

        {shown.length === 0 ? (
          <EmptyState message="No trials match these filters." />
        ) : (
          <ul className="min-w-0 space-y-3">
            {shown.map((t) => (
              <TrialCard
                key={t.tenantId}
                trial={t}
                open={expanded === t.tenantId}
                onToggle={() =>
                  setExpanded(expanded === t.tenantId ? null : t.tenantId)
                }
              />
            ))}
          </ul>
        )}
      </Card>

      {/* Worth stating: this list is a number, and the exec owns it */}
      <p className="mt-4 text-[12px] text-muted-foreground">
        {shown.length} of {trials.length} trials shown ·{" "}
        <span className="font-semibold text-foreground">
          {rupees(pipeline)}/mo
        </span>{" "}
        at list price if every one converts.
      </p>
    </div>
  );
}

/**
 * One trial. The three things C-SL-02 asks for are laid out top to bottom:
 * days left (header), contact (middle), follow-up notes (expandable).
 */
function TrialCard({
  trial,
  open,
  onToggle,
}: {
  trial: TrialRow;
  open: boolean;
  onToggle: () => void;
}) {
  const notesId = `notes-${trial.tenantId}`;

  return (
    <li className="min-w-0 rounded-field border border-border p-4">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="min-w-0 truncate text-[14px] font-semibold text-foreground">
              {trial.name}
            </h2>
            <UrgencyChip trial={trial} />
          </div>
          <p className="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
            <span className="shrink-0 font-mono">{trial.slug}.shikshasync.me</span>
            <span className="shrink-0 capitalize">
              · {trial.type.toLowerCase()}
            </span>
            <span className="shrink-0">· signed up {trial.ageDays}d ago</span>
          </p>
        </div>

        <div className="shrink-0 text-right">
          <p className="text-[14px] font-bold tabular-nums text-foreground">
            {rupees(trial.monthlyValue)}
            <span className="text-[11px] font-normal text-muted-foreground">
              /mo
            </span>
          </p>
          <p className="text-[11px] text-muted-foreground">
            {trial.planName} trial
          </p>
        </div>
      </div>

      {/* Usage — the evidence behind "are they actually using it?" */}
      <dl className="mt-3 grid min-w-0 grid-cols-2 gap-x-4 gap-y-2 border-t border-border pt-3 sm:grid-cols-4">
        <Metric label="Students" value={trial.studentCount.toLocaleString("en-IN")} />
        <Metric label="Teachers" value={String(trial.teacherCount)} />
        <Metric label="Storage" value={`${trial.storageUsedGb} GB`} />
        <Metric
          label="Optional modules"
          value={`${trial.optionalModulesOn} on`}
          tone={trial.optionalModulesOn > 0 ? "good" : "flat"}
        />
      </dl>

      {/* Contact — the doc asks for it here, not one click away */}
      <div className="mt-3 flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border pt-3 text-[12px]">
        <a
          href={`mailto:${trial.contactEmail}`}
          className="inline-flex min-w-0 items-center gap-1.5 rounded text-accent transition-colors hover:text-accent-hover focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15"
        >
          <Mail className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="min-w-0 truncate">{trial.contactEmail}</span>
        </a>
        {trial.contactPhone && (
          <a
            href={`tel:${trial.contactPhone.replace(/\s/g, "")}`}
            className="inline-flex shrink-0 items-center gap-1.5 rounded text-accent transition-colors hover:text-accent-hover focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15"
          >
            <Phone className="h-3.5 w-3.5" aria-hidden="true" />
            {trial.contactPhone}
          </a>
        )}
        {(trial.city || trial.state) && (
          <span className="inline-flex shrink-0 items-center gap-1.5 text-muted-foreground">
            <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
            {[trial.city, trial.state].filter(Boolean).join(", ")}
          </span>
        )}
      </div>

      <div className="mt-3 flex min-w-0 flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
          <span className="shrink-0">
            Owner:{" "}
            {trial.ownerName ? (
              trial.ownerName
            ) : (
              <span className="font-medium text-[#B45309]">Unassigned</span>
            )}
          </span>
          {trial.nextActionAt && (
            <span className="inline-flex shrink-0 items-center gap-1 text-[#475569]">
              <CalendarClock className="h-3 w-3" aria-hidden="true" />
              Next contact {formatDate(trial.nextActionAt)}
            </span>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            aria-controls={notesId}
            className="inline-flex h-8 items-center gap-1.5 rounded-field border border-border px-3 text-[12px] font-medium text-[#475569] transition-colors hover:border-accent hover:text-accent focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15"
          >
            <StickyNote className="h-3.5 w-3.5" aria-hidden="true" />
            {trial.notes.length === 0
              ? "No notes"
              : `${trial.notes.length} note${trial.notes.length === 1 ? "" : "s"}`}
          </button>

          <Link
            href={`/platform/sales/trials/${trial.tenantId}/convert`}
            className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-field bg-accent px-3 text-[12px] font-semibold text-white shadow-accent transition-colors hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15"
          >
            Convert
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
      </div>

      {open && (
        <div id={notesId} className="mt-3 min-w-0 border-t border-border pt-3">
          {trial.notes.length === 0 ? (
            <p className="text-[12px] text-muted-foreground">
              Nobody has logged a conversation with {trial.name} yet.
            </p>
          ) : (
            <ul className="min-w-0 space-y-2.5">
              {trial.notes.map((n) => (
                <li
                  key={n.id}
                  className="min-w-0 rounded-field bg-background px-3 py-2.5"
                >
                  <p className="text-[12px] leading-6 text-[#334155]">{n.body}</p>
                  <p className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                    <span>{n.authorName}</span>
                    <span>· {formatDate(n.createdAt)}</span>
                    {n.nextActionAt && (
                      <span className="font-medium text-[#475569]">
                        · follow up {formatDate(n.nextActionAt)}
                      </span>
                    )}
                  </p>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2.5 text-[11px] text-muted-foreground">
            {/* Honest about the gap rather than faking a composer */}
            Adding notes needs `trial_notes`, which is not in the schema yet —
            TODO(Dev-A), C-SL-02.
          </p>
        </div>
      )}
    </li>
  );
}

function Metric({
  label,
  value,
  tone = "flat",
}: {
  label: string;
  value: string;
  tone?: "good" | "flat";
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-0.5 truncate text-[13px] font-semibold tabular-nums",
          tone === "good" ? "text-success-text" : "text-foreground",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

/** Re-exported for the dashboard's compact pipeline list. */
export { trialCountdown };
