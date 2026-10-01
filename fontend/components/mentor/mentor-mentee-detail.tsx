"use client";

import Link from "next/link";
import { ArrowLeft, Mail, Phone } from "lucide-react";

import { Card, EmptyState, PageHeader } from "@/components/admin/ui";
import { useResource } from "@/hooks/use-resource";
import { fetchMentorMentee, type MentorMenteeDetail, type MentorNoteRow } from "@/lib/mentor";
import { AsyncState, MetricCard, dateOnly, dateTime, percent, statusLabel } from "@/components/principal/principal-ui";

import { MentorNoteComposer, MentorNoteItem } from "./mentor-note-form";
import { AttendanceBadge, MenteeAvatar, ScopeChips } from "./mentor-ui";

const tableHead = "px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-muted-foreground";
const tableCell = "px-3 py-2.5 text-sm text-foreground";

/** Mentee profile: contact & guardians, attendance, results, coursework, leave, mentoring log. */
export function MentorMenteeDetailPage({ studentId }: { studentId: string }) {
  const resource = useResource(() => fetchMentorMentee(studentId), [studentId]);

  const upsertNote = (note: MentorNoteRow) => {
    if (!resource.data) return;
    const rest = resource.data.notes.filter((row) => row.id !== note.id);
    const notes = [note, ...rest].sort((left, right) => right.note_date.localeCompare(left.note_date) || right.created_at.localeCompare(left.created_at));
    resource.setData({ ...resource.data, notes, profile: { ...resource.data.profile, note_count: notes.length } });
  };
  const dropNote = (noteId: string) => {
    if (!resource.data) return;
    const notes = resource.data.notes.filter((row) => row.id !== noteId);
    resource.setData({ ...resource.data, notes, profile: { ...resource.data.profile, note_count: notes.length } });
  };

  return (
    <div className="mx-auto max-w-6xl">
      <Link href="/mentor/mentees" className="mb-4 inline-flex items-center gap-1.5 text-sm font-semibold text-accent hover:underline"><ArrowLeft className="h-4 w-4" /> All mentees</Link>
      <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading mentee profile…">
        {resource.data ? <Detail data={resource.data} studentId={studentId} onNoteSaved={upsertNote} onNoteDeleted={dropNote} /> : null}
      </AsyncState>
    </div>
  );
}

function Detail({ data, studentId, onNoteSaved, onNoteDeleted }: { data: MentorMenteeDetail; studentId: string; onNoteSaved: (note: MentorNoteRow) => void; onNoteDeleted: (id: string) => void }) {
  const { profile } = data;
  return (
    <div className="space-y-6">
      <PageHeader
        title={profile.student_name}
        subtitle={`${profile.roll_number ?? "No roll number"} · ${profile.class_name ?? "No active class"}${profile.department_name ? ` · ${profile.department_name}` : ""}`}
        action={<AttendanceBadge value={profile.attendance_percentage} atRisk={profile.is_at_risk} />}
      />

      <section className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <div className="flex items-center gap-3">
            <MenteeAvatar name={profile.student_name} avatarUrl={profile.avatar_url} size="h-14 w-14" />
            <div className="min-w-0">
              <p className="truncate font-display text-base font-bold text-primary">{profile.student_name}</p>
              <ScopeChips sources={profile.sources} />
            </div>
          </div>
          <dl className="mt-4 space-y-2 text-sm">
            {profile.email ? <div className="flex items-center gap-2"><Mail className="h-4 w-4 shrink-0 text-muted-foreground" /><a href={`mailto:${profile.email}`} className="truncate text-accent hover:underline">{profile.email}</a></div> : null}
            {profile.phone ? <div className="flex items-center gap-2"><Phone className="h-4 w-4 shrink-0 text-muted-foreground" /><a href={`tel:${profile.phone}`} className="text-accent hover:underline">{profile.phone}</a></div> : null}
            {data.gender ? <div className="flex gap-2"><dt className="w-24 shrink-0 text-muted-foreground">Gender</dt><dd className="text-foreground">{statusLabel(data.gender)}</dd></div> : null}
            {data.date_of_birth ? <div className="flex gap-2"><dt className="w-24 shrink-0 text-muted-foreground">Born</dt><dd className="text-foreground">{dateOnly(data.date_of_birth)}</dd></div> : null}
            {data.address ? <div className="flex gap-2"><dt className="w-24 shrink-0 text-muted-foreground">Address</dt><dd className="text-foreground">{data.address}</dd></div> : null}
          </dl>
          <h3 className="mt-5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Guardians</h3>
          {data.guardians.length ? (
            <ul className="mt-2 space-y-2">
              {data.guardians.map((guardian, index) => (
                <li key={`${guardian.email ?? guardian.name ?? index}`} className="rounded-field bg-muted px-3 py-2 text-sm">
                  <p className="font-semibold text-primary">{guardian.name ?? "Guardian"} <span className="font-normal text-muted-foreground">· {guardian.relation}{guardian.is_primary ? " · primary" : ""}</span></p>
                  <p className="text-xs text-muted-foreground">{[guardian.phone, guardian.email].filter(Boolean).join(" · ") || "No contact details"}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">No guardian linked.</p>
          )}
        </Card>

        <div className="space-y-4 lg:col-span-2">
          <div className="grid gap-4 sm:grid-cols-4">
            <MetricCard label="Attendance" value={percent(data.attendance.percentage)} hint={`${data.attendance.total} sessions`} tone={profile.is_at_risk ? "danger" : "default"} />
            <MetricCard label="Present" value={data.attendance.present} hint={`${data.attendance.late} late · ${data.attendance.excused} excused`} tone="success" />
            <MetricCard label="Absent" value={data.attendance.absent} tone={data.attendance.absent ? "warning" : "default"} />
            <MetricCard label="Pending leave" value={profile.pending_leave_count} tone={profile.pending_leave_count ? "warning" : "default"} />
          </div>
          <Card>
            <h2 className="font-display text-base font-bold text-primary">Attendance by subject</h2>
            {data.subjects.length ? (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[480px]">
                  <thead><tr className="border-b border-border"><th className={tableHead}>Subject</th><th className={tableHead}>Present</th><th className={tableHead}>Absent</th><th className={tableHead}>Late</th><th className={tableHead}>Attendance</th></tr></thead>
                  <tbody>
                    {data.subjects.map((row) => (
                      <tr key={row.subject_id} className="border-b border-border last:border-none">
                        <td className={tableCell}><span className="font-medium text-primary">{row.subject_name}</span> <span className="text-xs text-muted-foreground">{row.subject_code}</span></td>
                        <td className={tableCell}>{row.present}</td><td className={tableCell}>{row.absent}</td><td className={tableCell}>{row.late}</td>
                        <td className={tableCell}><span className="font-semibold">{percent(row.percentage)}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState text="No attendance recorded this year." />
            )}
          </Card>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-display text-base font-bold text-primary">Published results</h2>
          {data.results.length ? (
            <ul className="mt-3 divide-y divide-border">
              {data.results.map((row) => (
                <li key={row.publication_id} className="flex items-center justify-between gap-3 py-2.5">
                  <span className="min-w-0"><span className="block truncate text-sm font-semibold text-primary">{row.title}</span><span className="block text-xs text-muted-foreground">{row.total_marks_obtained}/{row.total_marks_possible}{row.grade ? ` · Grade ${row.grade}` : ""}{row.rank ? ` · Rank ${row.rank}` : ""}{row.published_at ? ` · ${dateOnly(row.published_at)}` : ""}</span></span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${row.result === "PASS" ? "bg-success-light text-success-text" : "bg-destructive-light text-destructive-text"}`}>{percent(row.percentage)} · {statusLabel(row.result)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState text="No published results yet." />
          )}
        </Card>
        <Card>
          <h2 className="font-display text-base font-bold text-primary">Coursework</h2>
          {data.coursework.length ? (
            <ul className="mt-3 divide-y divide-border">
              {data.coursework.map((row) => (
                <li key={row.id} className="flex items-center justify-between gap-3 py-2.5">
                  <span className="min-w-0"><span className="block truncate text-sm font-semibold text-primary">{row.title}</span><span className="block text-xs text-muted-foreground">{row.subject_name ?? "General"} · due {dateTime(row.due_date)}</span></span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${row.is_overdue ? "bg-destructive-light text-destructive-text" : row.submission_status ? "bg-success-light text-success-text" : "bg-muted text-muted-foreground"}`}>
                    {row.is_overdue ? "Overdue" : row.submission_status ? `${statusLabel(row.submission_status)}${row.score !== null ? ` · ${row.score}` : ""}` : "Not submitted"}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState text="No coursework published for this class." />
          )}
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-display text-base font-bold text-primary">Upcoming exams</h2>
          {data.upcoming_exams.length ? (
            <ol className="mt-3 space-y-3">{data.upcoming_exams.map((exam) => <li key={exam.id} className="border-l-2 border-accent pl-3"><p className="text-sm font-semibold text-primary">{exam.title}</p><p className="text-xs text-muted-foreground">{exam.subject_name ?? exam.class_name} · {statusLabel(exam.status)} · {dateTime(exam.scheduled_at)}</p></li>)}</ol>
          ) : (
            <EmptyState text="No upcoming exams." />
          )}
        </Card>
        <Card>
          <h2 className="font-display text-base font-bold text-primary">Leave requests</h2>
          {data.leaves.length ? (
            <ul className="mt-3 divide-y divide-border">
              {data.leaves.map((leave) => (
                <li key={leave.id} className="flex items-center justify-between gap-3 py-2.5">
                  <span className="min-w-0"><span className="block text-sm font-semibold text-primary">{dateOnly(leave.from_date)}{leave.to_date !== leave.from_date ? ` → ${dateOnly(leave.to_date)}` : ""}</span><span className="block truncate text-xs text-muted-foreground">{leave.reason}</span></span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${leave.status === "APPROVED" ? "bg-success-light text-success-text" : leave.status === "PENDING" ? "bg-warning-light text-warning-text" : "bg-muted text-muted-foreground"}`}>{statusLabel(leave.status)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState text="No leave requests filed." />
          )}
        </Card>
      </section>

      <Card>
        <h2 className="font-display text-base font-bold text-primary">Mentoring log</h2>
        <p className="mt-1 text-xs text-muted-foreground">Meeting summaries, agreed actions and concerns. Private notes are visible only to you; shared notes are visible to any mentor of this student.</p>
        <div className="mt-4 border-b border-border pb-5"><MentorNoteComposer studentId={studentId} onSaved={onNoteSaved} /></div>
        {data.notes.length ? (
          <ul className="mt-5 space-y-3">{data.notes.map((note) => <MentorNoteItem key={note.id} note={note} onChanged={onNoteSaved} onDeleted={onNoteDeleted} />)}</ul>
        ) : (
          <p className="mt-5 text-sm text-muted-foreground">No log entries yet.</p>
        )}
      </Card>
    </div>
  );
}
