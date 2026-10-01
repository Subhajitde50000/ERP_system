"use client";

import { useMemo, useState } from "react";
import { UserPlus, X } from "lucide-react";

import { Card, EmptyState, PageHeader, inputClass, labelClass } from "@/components/admin/ui";
import { useResource } from "@/hooks/use-resource";
import {
  MENTOR_SCOPE_LABEL,
  assignMentor,
  fetchMentorBoard,
  removeMentorAssignment,
  type MentorManagementBoard,
  type MentorScope,
  type MentorTargetOption,
} from "@/lib/mentor";
import { AsyncState, MetricCard, dateOnly } from "@/components/principal/principal-ui";

import { primaryButtonClass } from "./mentor-ui";

const SCOPES: MentorScope[] = ["CLASS", "TEAM", "STUDENT"];

const SCOPE_HELP: Record<MentorScope, string> = {
  CLASS: "Every actively enrolled student in the class becomes a mentee.",
  TEAM: "One mentor per project team; all members become mentees.",
  STUDENT: "A single student. The HOD console can also make these assignments.",
};

function targetLabel(option: MentorTargetOption, scope: MentorScope) {
  const parts = [option.name];
  if (scope === "STUDENT") parts.push(option.class_name ?? option.detail ?? "");
  else if (option.detail) parts.push(option.detail);
  if (scope !== "STUDENT") parts.push(`${option.member_count} student${option.member_count === 1 ? "" : "s"}`);
  return parts.filter(Boolean).join(" · ") + (option.mentor_name ? ` · currently ${option.mentor_name}` : "");
}

/**
 * Mentor allocation board. The Academic Coordinator owns it; the Institution
 * Admin sees the same page as the operational fallback. Rules enforced by the
 * API: one active mentor per student / team / class per academic year, while a
 * mentor may hold any number of targets.
 */
export function MentorAssignmentsBoardPage({ isAdmin = false }: { isAdmin?: boolean }) {
  const resource = useResource(fetchMentorBoard, []);
  const [scope, setScope] = useState<MentorScope>("CLASS");
  const [targetId, setTargetId] = useState("");
  const [mentorId, setMentorId] = useState("");
  const [notes, setNotes] = useState("");
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options = useMemo(() => {
    if (!resource.data) return [];
    const list = scope === "CLASS" ? resource.data.classes : scope === "TEAM" ? resource.data.teams : resource.data.students;
    // Unassigned first so the gaps are obvious; the select still allows reassignment.
    return [...list].sort((left, right) => Number(Boolean(left.mentor_id)) - Number(Boolean(right.mentor_id)) || left.name.localeCompare(right.name));
  }, [resource.data, scope]);

  const selected = options.find((option) => option.id === targetId);
  const reassigning = Boolean(selected?.mentor_id && selected.mentor_id !== mentorId);

  async function run(action: () => Promise<MentorManagementBoard>, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      resource.setData(await action());
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : fallback);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!targetId || !mentorId) return;
    if (reassigning && !window.confirm(`${selected?.name} already has ${selected?.mentor_name} as mentor. Replace them?`)) return;
    if (await run(() => assignMentor({ mentor_id: mentorId, scope_type: scope, target_id: targetId, notes: notes.trim() || null }), "Could not assign the mentor.")) {
      setTargetId("");
      setMentorId("");
      setNotes("");
    }
  }

  const mentors = (resource.data?.mentors ?? []).filter((mentor) => {
    const needle = filter.trim().toLowerCase();
    return !needle || mentor.mentor_name.toLowerCase().includes(needle) || mentor.assignments.some((row) => row.target_name.toLowerCase().includes(needle));
  });

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Mentor assignments"
        subtitle={isAdmin ? "Operational fallback for mentor allocation — the Academic Coordinator manages this day to day. Each student, team or class holds one active mentor per academic year." : "Allocate mentors to classes, project teams and individual students. Each target holds one active mentor per academic year; a mentor may hold many."}
      />
      <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading mentor board…">
        {resource.data ? (
          <div className="space-y-6">
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard label="Classes with a mentor" value={`${resource.data.coverage.classes_covered}/${resource.data.coverage.classes_total}`} tone={resource.data.coverage.classes_covered < resource.data.coverage.classes_total ? "warning" : "success"} />
              <MetricCard label="Teams with a mentor" value={`${resource.data.coverage.teams_covered}/${resource.data.coverage.teams_total}`} tone={resource.data.coverage.teams_covered < resource.data.coverage.teams_total ? "warning" : "success"} />
              <MetricCard label="Students covered" value={`${resource.data.coverage.students_covered}/${resource.data.coverage.students_total}`} hint={`${resource.data.coverage.students_direct} assigned directly`} tone={resource.data.coverage.students_covered < resource.data.coverage.students_total ? "warning" : "success"} />
              <MetricCard label="Active mentors" value={resource.data.mentors.length} hint={resource.data.academic_year ? `Academic year ${resource.data.academic_year}` : "No current academic year"} />
            </section>

            <Card>
              <h2 className="font-display text-base font-bold text-primary">Assign a mentor</h2>
              <p className="mt-1 text-xs text-muted-foreground">{SCOPE_HELP[scope]} Staff without the Mentor role receive it automatically on first assignment.</p>
              <form onSubmit={submit} className="mt-4 grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="assign-scope" className={labelClass}>Assign to</label>
                  <select id="assign-scope" className={inputClass} value={scope} onChange={(event) => { setScope(event.target.value as MentorScope); setTargetId(""); }}>
                    {SCOPES.map((key) => <option key={key} value={key}>{MENTOR_SCOPE_LABEL[key]}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor="assign-target" className={labelClass}>{MENTOR_SCOPE_LABEL[scope]}</label>
                  <select id="assign-target" className={inputClass} value={targetId} onChange={(event) => setTargetId(event.target.value)} required disabled={!resource.data.academic_year}>
                    <option value="">Select {MENTOR_SCOPE_LABEL[scope].toLowerCase()}</option>
                    {options.map((option) => <option key={option.id} value={option.id}>{targetLabel(option, scope)}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor="assign-mentor" className={labelClass}>Mentor</label>
                  <select id="assign-mentor" className={inputClass} value={mentorId} onChange={(event) => setMentorId(event.target.value)} required disabled={!resource.data.academic_year}>
                    <option value="">Select staff member</option>
                    {resource.data.candidates.map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>
                        {candidate.name}{candidate.designation ? ` · ${candidate.designation}` : ""}{candidate.department_name ? ` · ${candidate.department_name}` : ""} · {candidate.active_assignment_count} active{candidate.roles.includes("MENTOR") ? "" : " · role granted on assign"}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="assign-notes" className={labelClass}>Notes (optional)</label>
                  <input id="assign-notes" className={inputClass} value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={2000} placeholder="Context for the mentor" />
                </div>
                <div className="sm:col-span-2 flex flex-wrap items-center gap-3">
                  <button type="submit" disabled={busy || !resource.data.academic_year} className={primaryButtonClass}><UserPlus className="h-4 w-4" /> {busy ? "Saving…" : reassigning ? "Reassign mentor" : "Assign mentor"}</button>
                  {reassigning ? <span className="text-sm text-warning-text">This replaces {selected?.mentor_name} for {selected?.name}.</span> : null}
                  {!resource.data.academic_year ? <span className="text-sm text-warning-text">Mark an academic year as current before assigning mentors.</span> : null}
                </div>
              </form>
              {error ? <p role="alert" className="mt-3 text-sm text-destructive-text">{error}</p> : null}
            </Card>

            <Card>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-display text-base font-bold text-primary">Mentors and their scope</h2>
                <div className="w-full sm:w-72"><label htmlFor="mentor-filter" className="sr-only">Filter mentors</label><input id="mentor-filter" type="search" value={filter} onChange={(event) => setFilter(event.target.value)} className={inputClass} placeholder="Filter by mentor, class, team or student" /></div>
              </div>
              {mentors.length ? (
                <div className="grid gap-4 lg:grid-cols-2">
                  {mentors.map((mentor) => (
                    <div key={mentor.mentor_id} className="rounded-field border border-border p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="truncate font-display font-bold text-primary">{mentor.mentor_name}{!mentor.is_active ? <span className="ml-2 rounded-full bg-destructive-light px-2 py-0.5 text-[11px] font-medium text-destructive-text">inactive</span> : null}</h3>
                          <p className="truncate text-xs text-muted-foreground">{[mentor.designation, mentor.department_name, mentor.email].filter(Boolean).join(" · ") || "Mentor"}</p>
                        </div>
                        <div className="shrink-0 text-right text-xs">
                          <p className="text-sm font-semibold text-primary">{mentor.mentee_count} mentees</p>
                          <p className={mentor.at_risk_count ? "text-destructive-text" : "text-muted-foreground"}>{mentor.at_risk_count} at risk</p>
                        </div>
                      </div>
                      <ul className="mt-3 space-y-2 border-t border-border pt-3">
                        {mentor.assignments.map((row) => (
                          <li key={row.id} className="flex items-center justify-between gap-3">
                            <span className="min-w-0">
                              <span className="block truncate text-sm font-medium text-primary"><span className="mr-1.5 rounded bg-accent-light px-1.5 py-0.5 text-[10px] font-semibold uppercase text-accent">{row.scope_type}</span>{row.target_name}</span>
                              <span className="block truncate text-xs text-muted-foreground">{[row.target_detail, row.scope_type !== "CLASS" ? row.class_name : null, row.scope_type !== "STUDENT" ? `${row.member_count} students` : null, `since ${dateOnly(row.assigned_at)}`].filter(Boolean).join(" · ")}</span>
                            </span>
                            <button type="button" disabled={busy} onClick={() => { if (window.confirm(`Remove ${mentor.mentor_name} as mentor of ${row.target_name}?`)) void run(() => removeMentorAssignment(row.id), "Could not remove the assignment."); }} aria-label={`Remove ${row.target_name} from ${mentor.mentor_name}`} className="shrink-0 rounded p-1 text-destructive-text hover:bg-destructive-light disabled:opacity-50"><X className="h-4 w-4" /></button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState text={resource.data.mentors.length ? "No mentor matches this filter." : "No mentor assignments yet for this academic year."} />
              )}
            </Card>
          </div>
        ) : null}
      </AsyncState>
    </div>
  );
}
