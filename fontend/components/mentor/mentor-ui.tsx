"use client";

import Link from "next/link";
import { AlertTriangle, Lock, Users } from "lucide-react";

import { percent } from "@/components/principal/principal-ui";
import { MENTOR_SCOPE_LABEL, type MenteeSource, type MentorMenteeRow } from "@/lib/mentor";

/** Attendance % coloured against the tenant threshold. */
export function AttendanceBadge({ value, atRisk }: { value: number | null; atRisk: boolean }) {
  const tone = value === null ? "bg-muted text-muted-foreground" : atRisk ? "bg-destructive-light text-destructive-text" : "bg-success-light text-success-text";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${tone}`}>
      {atRisk ? <AlertTriangle className="h-3 w-3" aria-hidden="true" /> : null}
      {percent(value)}
    </span>
  );
}

/** Why this student is in scope — direct, via a team, via a class. */
export function ScopeChips({ sources }: { sources: MenteeSource[] }) {
  return (
    <span className="flex flex-wrap gap-1">
      {sources.map((source) => (
        <span key={source.assignment_id} title={MENTOR_SCOPE_LABEL[source.scope_type]} className="rounded-full bg-accent-light px-2 py-0.5 text-[11px] font-medium text-accent">
          {source.label}
        </span>
      ))}
    </span>
  );
}

export function MenteeAvatar({ name, avatarUrl, size = "h-10 w-10" }: { name: string; avatarUrl: string | null; size?: string }) {
  const initials = name.split(" ").map((part) => part[0]).filter(Boolean).slice(0, 2).join("").toUpperCase();
  return avatarUrl ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={avatarUrl} alt="" className={`${size} shrink-0 rounded-full object-cover`} />
  ) : (
    <span className={`${size} inline-flex shrink-0 items-center justify-center rounded-full bg-accent-light font-display text-sm font-bold text-accent`}>{initials || <Users className="h-4 w-4" />}</span>
  );
}

/** Compact mentee row used by the list, dashboard and class/team pages. */
export function MenteeListItem({ mentee }: { mentee: MentorMenteeRow }) {
  return (
    <li>
      <Link href={`/mentor/mentees/${mentee.student_id}`} className="flex items-center gap-3 rounded-field px-2 py-2.5 transition hover:bg-muted">
        <MenteeAvatar name={mentee.student_name} avatarUrl={mentee.avatar_url} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-primary">{mentee.student_name}</span>
          <span className="block truncate text-xs text-muted-foreground">
            {mentee.roll_number ?? "—"} · {mentee.class_name ?? "No active class"}
            {mentee.pending_leave_count ? ` · ${mentee.pending_leave_count} pending leave` : ""}
          </span>
          <span className="mt-1 block"><ScopeChips sources={mentee.sources} /></span>
        </span>
        <span className="flex shrink-0 flex-col items-end gap-1">
          <AttendanceBadge value={mentee.attendance_percentage} atRisk={mentee.is_at_risk} />
          <span className="text-[11px] text-muted-foreground">{mentee.note_count} note{mentee.note_count === 1 ? "" : "s"}</span>
        </span>
      </Link>
    </li>
  );
}

export function PrivacyTag({ isPrivate }: { isPrivate: boolean }) {
  return isPrivate ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"><Lock className="h-3 w-3" aria-hidden="true" /> Private</span>
  ) : (
    <span className="rounded-full bg-accent-light px-2 py-0.5 text-[11px] font-medium text-accent">Shared with mentors</span>
  );
}

export const primaryButtonClass = "inline-flex h-10 items-center gap-1.5 rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60";
export const secondaryButtonClass = "inline-flex h-10 items-center gap-1.5 rounded-field border border-border bg-white px-4 text-sm font-semibold text-foreground transition hover:border-accent hover:text-accent disabled:opacity-60";
