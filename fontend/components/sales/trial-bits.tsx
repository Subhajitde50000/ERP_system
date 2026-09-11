import Link from "next/link";
import { Ban, CalendarClock, StickyNote, TriangleAlert } from "lucide-react";

import { cn, formatDate, rupees } from "@/lib/utils";
import {
  trialCountdown,
  URGENCY_LABELS,
  URGENCY_TONE,
} from "@/lib/sales";
import { TONE_BG, TONE_TEXT } from "@/components/dashboard/primitives";
import type { PlanFit, TrialRow } from "@/types/sales";

/**
 * Trial presentation shared by the dashboard (C-SL-01), the trial list
 * (C-SL-02) and the convert form (C-SL-03). Written once so a trial reads the
 * same wherever it appears.
 */

/** How close a trial is to its end date — `tenants.trial_ends_at` (§4.2). */
export function UrgencyChip({ trial }: { trial: TrialRow }) {
  const tone = URGENCY_TONE[trial.urgency];

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        TONE_BG[tone],
        // `muted` never appears here, but the ternary keeps the pattern
        // consistent with the other chips — `cn()` has no conflict resolution
        tone === "muted" ? "text-[#475569]" : TONE_TEXT[tone],
      )}
    >
      {URGENCY_LABELS[trial.urgency]}
      <span className="ml-1 normal-case opacity-80">
        · {trialCountdown(trial.daysLeft)}
      </span>
    </span>
  );
}

/** Owner, or the state that matters more: nobody has it. */
export function OwnerLabel({ trial }: { trial: TrialRow }) {
  if (trial.ownerName) {
    return <span className="text-muted-foreground">{trial.ownerName}</span>;
  }
  return <span className="font-medium text-[#B45309]">Unassigned</span>;
}

/** One row in any trial list. */
export function TrialListItem({ trial }: { trial: TrialRow }) {
  return (
    <li className="min-w-0 py-3">
      <div className="flex min-w-0 items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            <Link
              href={`/platform/sales/trials/${trial.tenantId}/convert`}
              className="min-w-0 truncate rounded text-[13px] font-medium text-foreground transition-colors hover:text-accent focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15"
            >
              {trial.name}
            </Link>
            <UrgencyChip trial={trial} />
          </div>

          <p className="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
            <span className="shrink-0 font-mono">{trial.slug}.shikshasync.me</span>
            <span className="shrink-0">· {trial.planName}</span>
            <span className="shrink-0">
              · {trial.studentCount.toLocaleString("en-IN")} students
            </span>
            {trial.notes.length > 0 && (
              <span className="inline-flex shrink-0 items-center gap-1">
                <StickyNote className="h-3 w-3" aria-hidden="true" />
                {trial.notes.length}
              </span>
            )}
          </p>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="text-[12px] font-semibold tabular-nums text-foreground">
            {rupees(trial.monthlyValue)}
            <span className="font-normal text-muted-foreground">/mo</span>
          </span>
          <span className="text-[11px]">
            <OwnerLabel trial={trial} />
          </span>
        </div>
      </div>

      {/* The commitment the exec made, if any — the thing that gets forgotten */}
      {trial.nextActionAt && (
        <p className="mt-1 inline-flex items-center gap-1.5 text-[11px] text-[#475569]">
          <CalendarClock className="h-3 w-3 shrink-0" aria-hidden="true" />
          Next contact {formatDate(trial.nextActionAt)}
        </p>
      )}
    </li>
  );
}

/**
 * What changing to a plan would do to a tenant.
 *
 * Shared by C-SL-03 (converting a trial) and C-SL-04 (upgrade / downgrade),
 * because both are the same question: does this plan still fit?
 *
 * Three levels, styled apart so they can't be skimmed as one list: a blocker
 * is red and refuses, a warning is amber and needs acknowledging, a note is
 * grey and informs. Merging warnings into blockers is what made every
 * downgrade impossible in the first draft.
 */
export function PlanFitNotes({ fit }: { fit: PlanFit }) {
  if (!fit.blockers.length && !fit.warnings.length && !fit.notes.length)
    return null;

  return (
    <div className="min-w-0 space-y-1.5">
      {fit.blockers.map((issue) => (
        <p
          key={issue}
          className="flex min-w-0 items-start gap-1.5 text-[12px] font-medium text-destructive-text"
        >
          <Ban className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
          <span className="min-w-0">{issue}</span>
        </p>
      ))}
      {fit.warnings.map((warn) => (
        <p
          key={warn}
          className="flex min-w-0 items-start gap-1.5 text-[12px] font-medium text-[#B45309]"
        >
          <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
          <span className="min-w-0">{warn}</span>
        </p>
      ))}
      {fit.notes.map((note) => (
        <p
          key={note}
          className="flex min-w-0 items-start gap-1.5 text-[12px] text-muted-foreground"
        >
          <span aria-hidden="true">•</span>
          <span className="min-w-0">{note}</span>
        </p>
      ))}
    </div>
  );
}
