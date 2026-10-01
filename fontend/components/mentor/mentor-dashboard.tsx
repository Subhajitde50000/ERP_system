"use client";

import Link from "next/link";

import { Card, EmptyState, PageHeader } from "@/components/admin/ui";
import { useInstitutionAuth } from "@/hooks/use-institution-auth";
import { useResource } from "@/hooks/use-resource";
import { fetchMentorDashboard, type MentorDashboard } from "@/lib/mentor";
import { AsyncState, MetricCard, dateOnly, dateTime, percent, statusLabel } from "@/components/principal/principal-ui";

import { MenteeListItem, PrivacyTag } from "./mentor-ui";

function SectionHeader({ title, hint, href, linkLabel }: { title: string; hint: string; href: string; linkLabel: string }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <div>
        <h2 className="font-display text-base font-bold text-primary">{title}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      </div>
      <Link href={href} className="shrink-0 text-sm font-semibold text-accent hover:underline">{linkLabel}</Link>
    </div>
  );
}

/** Mentor home — mentee counts, at-risk alerts, recent log entries, upcoming exams, scope. */
export function MentorDashboardPage() {
  const { user } = useInstitutionAuth();
  const resource = useResource(fetchMentorDashboard, []);

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title={`Welcome, ${user?.name?.split(" ")[0] ?? "Mentor"}`}
        subtitle={resource.data?.academic_year ? `Academic year ${resource.data.academic_year} · your mentoring overview` : "Your mentoring overview"}
      />
      <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading your mentees…">
        {resource.data ? <DashboardContent data={resource.data} /> : null}
      </AsyncState>
    </div>
  );
}

function DashboardContent({ data }: { data: MentorDashboard }) {
  if (!data.mentee_count && !data.class_count && !data.team_count) {
    return (
      <Card>
        <EmptyState text={data.academic_year ? "No students, teams or classes are assigned to you for this academic year yet. Your Academic Coordinator or HOD allocates mentees." : "No current academic year is configured. Ask your Institution Admin to mark one as current."} />
      </Card>
    );
  }
  const scopeHint = [
    data.direct_count ? `${data.direct_count} direct` : null,
    data.team_count ? `${data.team_count} team${data.team_count === 1 ? "" : "s"}` : null,
    data.class_count ? `${data.class_count} class${data.class_count === 1 ? "" : "es"}` : null,
  ].filter(Boolean).join(" · ");

  return (
    <div className="space-y-6">
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Mentees" value={data.mentee_count} hint={scopeHint || "Distinct students in your scope"} />
        <MetricCard
          label="Needs attention"
          value={data.at_risk_count}
          hint={data.attendance_threshold !== null ? `Attendance below ${data.attendance_threshold}%` : "No attendance threshold configured"}
          tone={data.at_risk_count ? "danger" : "success"}
        />
        <MetricCard label="Average attendance" value={percent(data.average_attendance)} hint={`${data.pending_leave_count} pending leave request${data.pending_leave_count === 1 ? "" : "s"}`} tone={data.attendance_threshold !== null && data.average_attendance !== null && data.average_attendance < data.attendance_threshold ? "warning" : "default"} />
        <MetricCard label="Notes this month" value={data.notes_this_month} hint={`${data.upcoming_exam_count} upcoming exam${data.upcoming_exam_count === 1 ? "" : "s"} for your mentees`} />
      </section>

      <section className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <SectionHeader title="At-risk mentees" hint="Lowest attendance first — reach out early." href="/mentor/alerts" linkLabel="All alerts" />
          {data.at_risk_mentees.length ? (
            <ul className="divide-y divide-border">{data.at_risk_mentees.map((mentee) => <MenteeListItem key={mentee.student_id} mentee={mentee} />)}</ul>
          ) : (
            <EmptyState text="No mentee is below the attendance threshold." />
          )}
        </Card>
        <Card className="lg:col-span-2">
          <SectionHeader title="Upcoming exams" hint="For your mentees' classes." href="/mentor/mentees" linkLabel="Mentees" />
          {data.upcoming_exams.length ? (
            <ol className="space-y-3">
              {data.upcoming_exams.map((exam) => (
                <li key={exam.id} className="border-l-2 border-accent pl-3">
                  <p className="text-sm font-semibold text-primary">{exam.title}</p>
                  <p className="text-xs text-muted-foreground">{exam.class_name}{exam.subject_name ? ` · ${exam.subject_name}` : ""} · {statusLabel(exam.status)}</p>
                  <time className="mt-1 block text-[11px] font-medium text-accent">{dateTime(exam.scheduled_at)}</time>
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState text="No upcoming exams." />
          )}
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <SectionHeader title="Recent mentoring log" hint="Latest conversations and follow-ups." href="/mentor/notes" linkLabel="Full log" />
          {data.recent_notes.length ? (
            <ul className="space-y-3">
              {data.recent_notes.map((note) => (
                <li key={note.id} className="border-b border-border pb-3 last:border-none last:pb-0">
                  <div className="flex items-center justify-between gap-2">
                    <Link href={`/mentor/mentees/${note.student_id}`} className="truncate text-sm font-semibold text-primary hover:text-accent">{note.student_name}</Link>
                    <PrivacyTag isPrivate={note.is_private} />
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{note.body}</p>
                  <p className="mt-1 text-[11px] text-muted-foreground">{dateOnly(note.note_date)} · {note.is_own ? "You" : note.author_name ?? "Mentor"}</p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState text="No log entries yet. Open a mentee to record your first conversation." />
          )}
        </Card>
        <Card className="lg:col-span-2">
          <SectionHeader title="Your scope" hint="Classes and project teams you mentor." href="/mentor/classes" linkLabel="Classes" />
          {data.classes.length || data.teams.length ? (
            <ul className="space-y-2">
              {data.classes.map((row) => (
                <li key={row.assignment_id} className="flex items-center justify-between gap-3 rounded-field bg-muted px-3 py-2 text-sm">
                  <span className="min-w-0"><span className="block truncate font-semibold text-primary">{row.class_name}</span><span className="block text-xs text-muted-foreground">Class · {row.student_count} students · {row.at_risk_count} at risk</span></span>
                  <span className="text-xs font-semibold text-primary">{percent(row.average_attendance)}</span>
                </li>
              ))}
              {data.teams.map((row) => (
                <li key={row.assignment_id}>
                  <Link href={`/mentor/teams/${row.team_id}`} className="flex items-center justify-between gap-3 rounded-field bg-muted px-3 py-2 text-sm hover:bg-accent-light">
                    <span className="min-w-0"><span className="block truncate font-semibold text-primary">{row.team_name}</span><span className="block truncate text-xs text-muted-foreground">Team · {row.coursework_title} · {row.member_count} members</span></span>
                    <span className="shrink-0 text-xs text-muted-foreground">Due {dateOnly(row.due_date)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState text="Only direct student assignments so far." />
          )}
        </Card>
      </section>
    </div>
  );
}
