"use client";

import Link from "next/link";

import { Card, EmptyState, PageHeader } from "@/components/admin/ui";
import { useResource } from "@/hooks/use-resource";
import { fetchMentorClasses } from "@/lib/mentor";
import { AsyncState, dateOnly, percent } from "@/components/principal/principal-ui";

/** Classes the mentor is responsible for as a whole (every active student is a mentee). */
export function MentorClassesPage() {
  const resource = useResource(fetchMentorClasses, []);
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Classes" subtitle="Classes assigned to you as mentor. Every actively enrolled student in these classes appears in your mentee list." />
      <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading classes…">
        {resource.data ? resource.data.length ? (
          <div className="grid gap-4 md:grid-cols-2">
            {resource.data.map((row) => (
              <Card key={row.assignment_id}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="truncate font-display text-base font-bold text-primary">{row.class_name}</h2>
                    <p className="text-xs text-muted-foreground">{row.class_code}{row.department_name ? ` · ${row.department_name}` : ""}{row.room_no ? ` · Room ${row.room_no}` : ""}</p>
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${row.at_risk_count ? "bg-destructive-light text-destructive-text" : "bg-success-light text-success-text"}`}>{row.at_risk_count} at risk</span>
                </div>
                <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
                  <div><dt className="text-[11px] uppercase tracking-wide text-muted-foreground">Students</dt><dd className="font-display text-lg font-bold text-primary">{row.student_count}</dd></div>
                  <div><dt className="text-[11px] uppercase tracking-wide text-muted-foreground">Avg attendance</dt><dd className="font-display text-lg font-bold text-primary">{percent(row.average_attendance)}</dd></div>
                  <div><dt className="text-[11px] uppercase tracking-wide text-muted-foreground">Class teacher</dt><dd className="truncate font-medium text-primary">{row.class_teacher_name ?? "—"}</dd></div>
                </dl>
                <div className="mt-4 flex items-center justify-between border-t border-border pt-3 text-xs text-muted-foreground">
                  <span>Mentor since {dateOnly(row.assigned_at)}</span>
                  <Link href={`/mentor/mentees?class=${row.class_id}`} className="font-semibold text-accent hover:underline">View students</Link>
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <Card><EmptyState text="No class is assigned to you as a whole. Class-level mentoring is allocated by the Academic Coordinator." /></Card>
        ) : null}
      </AsyncState>
    </div>
  );
}
