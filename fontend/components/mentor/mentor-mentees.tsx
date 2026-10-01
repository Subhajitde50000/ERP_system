"use client";

import { useMemo, useState } from "react";

import { Card, EmptyState, PageHeader, inputClass } from "@/components/admin/ui";
import { useResource } from "@/hooks/use-resource";
import { MENTOR_SCOPE_LABEL, fetchMentorMentees, type MentorScope } from "@/lib/mentor";
import { AsyncState } from "@/components/principal/principal-ui";

import { MenteeListItem } from "./mentor-ui";

/**
 * Mentee directory. `atRiskOnly` renders the same list as the "At-risk alerts"
 * page — one component, one API, two entry points.
 */
export function MentorMenteesPage({ atRiskOnly = false, initialClassId = "" }: { atRiskOnly?: boolean; initialClassId?: string }) {
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<"" | MentorScope>("");
  const [classId, setClassId] = useState(initialClassId);
  const resource = useResource(
    () => fetchMentorMentees({ query: query || undefined, scope: scope || undefined, classId: classId || undefined, atRisk: atRiskOnly }),
    [query, scope, classId, atRiskOnly],
  );
  // Class filter options come from the unfiltered result so they don't vanish as you narrow.
  const all = useResource(() => fetchMentorMentees({ atRisk: atRiskOnly }), [atRiskOnly]);
  const classOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const row of all.data?.items ?? []) if (row.class_id && row.class_name) seen.set(row.class_id, row.class_name);
    return [...seen.entries()].sort((left, right) => left[1].localeCompare(right[1]));
  }, [all.data]);

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title={atRiskOnly ? "At-risk alerts" : "My mentees"}
        subtitle={
          atRiskOnly
            ? resource.data?.attendance_threshold !== null && resource.data?.attendance_threshold !== undefined
              ? `Mentees whose attendance is below the institution threshold of ${resource.data.attendance_threshold}%.`
              : "Mentees flagged for attendance. No threshold is configured, so nothing is flagged yet."
            : "Every student in your mentoring scope — assigned directly, through a project team or through a class."
        }
      />
      <Card className="mb-5 !p-4">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px_200px]">
          <div><label htmlFor="mentee-search" className="sr-only">Search mentees</label><input id="mentee-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} className={inputClass} placeholder="Search by name, roll number or email" /></div>
          <div><label htmlFor="mentee-scope" className="sr-only">Assignment type</label><select id="mentee-scope" value={scope} onChange={(event) => setScope(event.target.value as typeof scope)} className={inputClass}><option value="">All assignment types</option>{(Object.keys(MENTOR_SCOPE_LABEL) as MentorScope[]).map((key) => <option key={key} value={key}>{key === "STUDENT" ? "Direct" : MENTOR_SCOPE_LABEL[key]}</option>)}</select></div>
          <div><label htmlFor="mentee-class" className="sr-only">Class</label><select id="mentee-class" value={classId} onChange={(event) => setClassId(event.target.value)} className={inputClass}><option value="">All classes</option>{classOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></div>
        </div>
      </Card>
      <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading mentees…">
        {resource.data ? (
          <Card>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{resource.data.total} student{resource.data.total === 1 ? "" : "s"}</p>
            {resource.data.items.length ? (
              <ul className="divide-y divide-border">{resource.data.items.map((mentee) => <MenteeListItem key={mentee.student_id} mentee={mentee} />)}</ul>
            ) : (
              <EmptyState text={atRiskOnly ? "No mentee is currently below the attendance threshold." : "No mentees match this filter."} />
            )}
          </Card>
        ) : null}
      </AsyncState>
    </div>
  );
}
