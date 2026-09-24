"use client";

import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";

import { Card, EmptyState, PageHeader } from "@/components/admin/ui";
import { useResource } from "@/hooks/use-resource";
import { fetchMentorTeam, fetchMentorTeams, type MentorTeamRow } from "@/lib/mentor";
import { AsyncState, dateOnly, dateTime, percent, statusLabel } from "@/components/principal/principal-ui";

function TeamCard({ row }: { row: MentorTeamRow }) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate font-display text-base font-bold text-primary">{row.team_name}</h2>
          <p className="truncate text-xs text-muted-foreground">{row.coursework_title} · {row.class_name}{row.subject_name ? ` · ${row.subject_name}` : ""}</p>
        </div>
        <span className="shrink-0 rounded-full bg-accent-light px-2 py-0.5 text-xs font-semibold text-accent">{statusLabel(row.coursework_status)}</span>
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
        <div><dt className="text-[11px] uppercase tracking-wide text-muted-foreground">Members</dt><dd className="font-display text-lg font-bold text-primary">{row.member_count}</dd></div>
        <div><dt className="text-[11px] uppercase tracking-wide text-muted-foreground">Open tasks</dt><dd className={`font-display text-lg font-bold ${row.open_task_count ? "text-warning-text" : "text-primary"}`}>{row.open_task_count}</dd></div>
        <div><dt className="text-[11px] uppercase tracking-wide text-muted-foreground">Submission</dt><dd className="truncate font-medium text-primary">{row.submission_status ? statusLabel(row.submission_status) : "Not yet"}</dd></div>
      </dl>
      <div className="mt-4 flex items-center justify-between border-t border-border pt-3 text-xs text-muted-foreground">
        <span>Due {dateTime(row.due_date)}</span>
        <Link href={`/mentor/teams/${row.team_id}`} className="font-semibold text-accent hover:underline">Open team</Link>
      </div>
    </Card>
  );
}

/** Project teams the mentor guides (one mentor per team). */
export function MentorTeamsPage() {
  const resource = useResource(fetchMentorTeams, []);
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Project teams" subtitle="Teams you mentor through their project coursework — members, task board, resources and recent discussion." />
      <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading teams…">
        {resource.data ? resource.data.length ? (
          <div className="grid gap-4 md:grid-cols-2">{resource.data.map((row) => <TeamCard key={row.assignment_id} row={row} />)}</div>
        ) : (
          <Card><EmptyState text="No project team is assigned to you." /></Card>
        ) : null}
      </AsyncState>
    </div>
  );
}

const taskTone: Record<string, string> = { DONE: "bg-success-light text-success-text", IN_PROGRESS: "bg-warning-light text-warning-text" };

/** Read-only team workspace view for the mentor. */
export function MentorTeamDetailPage({ teamId }: { teamId: string }) {
  const resource = useResource(() => fetchMentorTeam(teamId), [teamId]);
  return (
    <div className="mx-auto max-w-6xl">
      <Link href="/mentor/teams" className="mb-4 inline-flex items-center gap-1.5 text-sm font-semibold text-accent hover:underline"><ArrowLeft className="h-4 w-4" /> All teams</Link>
      <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading team…">
        {resource.data ? (
          <div className="space-y-6">
            <PageHeader title={resource.data.team_name} subtitle={`${resource.data.coursework_title} · ${resource.data.class_name}${resource.data.subject_name ? ` · ${resource.data.subject_name}` : ""} · due ${dateTime(resource.data.due_date)}`} action={<span className="rounded-full bg-accent-light px-3 py-1 text-xs font-semibold text-accent">{resource.data.submission_status ? `Submission ${statusLabel(resource.data.submission_status)}` : "No submission yet"}</span>} />
            <section className="grid gap-4 lg:grid-cols-2">
              <Card>
                <h2 className="font-display text-base font-bold text-primary">Members ({resource.data.members.length})</h2>
                <ul className="mt-3 divide-y divide-border">
                  {resource.data.members.map((member) => (
                    <li key={member.student_id}>
                      <Link href={`/mentor/mentees/${member.student_id}`} className="flex items-center justify-between gap-3 py-2.5 hover:text-accent">
                        <span className="min-w-0"><span className="block truncate text-sm font-semibold text-primary">{member.student_name}</span><span className="block text-xs text-muted-foreground">{member.roll_number ?? "—"} · joined {dateOnly(member.joined_at)}</span></span>
                        <span className="text-sm font-semibold text-primary">{percent(member.attendance_percentage)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </Card>
              <Card>
                <h2 className="font-display text-base font-bold text-primary">Task board</h2>
                {resource.data.tasks.length ? (
                  <ul className="mt-3 divide-y divide-border">
                    {resource.data.tasks.map((task) => (
                      <li key={task.id} className="flex items-center justify-between gap-3 py-2.5">
                        <span className="min-w-0"><span className="block truncate text-sm font-semibold text-primary">{task.title}</span><span className="block text-xs text-muted-foreground">{task.assigned_to_name ?? "Unassigned"}{task.due_date ? ` · due ${dateOnly(task.due_date)}` : ""}</span></span>
                        <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${taskTone[task.status] ?? "bg-muted text-muted-foreground"}`}>{statusLabel(task.status)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState text="The team has not created tasks yet." />
                )}
              </Card>
            </section>
            <section className="grid gap-4 lg:grid-cols-2">
              <Card>
                <h2 className="font-display text-base font-bold text-primary">Recent discussion</h2>
                {resource.data.recent_messages.length ? (
                  <ol className="mt-3 space-y-3">
                    {resource.data.recent_messages.map((message) => (
                      <li key={message.id} className="rounded-field bg-muted px-3 py-2">
                        <p className="text-xs font-semibold text-primary">{message.sender_name ?? "Member"} <span className="font-normal text-muted-foreground">· {dateTime(message.created_at)}</span></p>
                        <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">{message.message}</p>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <EmptyState text="No messages in the team chat yet." />
                )}
              </Card>
              <Card>
                <h2 className="font-display text-base font-bold text-primary">Shared resources</h2>
                {resource.data.resources.length ? (
                  <ul className="mt-3 space-y-2">
                    {resource.data.resources.map((item) => (
                      <li key={item.id}><a href={item.url} target="_blank" rel="noreferrer" className="flex items-center gap-2 rounded-field border border-border px-3 py-2 text-sm font-medium text-accent hover:border-accent"><span className="truncate">{item.title}</span><span className="ml-auto shrink-0 text-[11px] uppercase text-muted-foreground">{statusLabel(item.resource_type)}</span><ExternalLink className="h-4 w-4 shrink-0" /></a></li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState text="No resources shared yet." />
                )}
              </Card>
            </section>
          </div>
        ) : null}
      </AsyncState>
    </div>
  );
}
