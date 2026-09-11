"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Ban, Pencil, Plus, RotateCcw, Send, Trash2 } from "lucide-react";

import { Card, PageHeader, inputClass, labelClass } from "@/components/admin/ui";
import { useResource } from "@/hooks/use-resource";
import {
  addAssignmentMilestone,
  closeTeacherAssignment,
  createTeacherAssignment,
  deleteAssignmentMilestone,
  fetchTeacherAssignment,
  fetchTeacherAssignments,
  fetchTeachingAssignments,
  publishTeacherAssignment,
  reopenTeacherAssignment,
  updateAssignmentMilestone,
  updateTeacherAssignment,
} from "@/lib/teacher";
import { AsyncState, EmptyTable, dateTime, statusLabel } from "@/components/principal/principal-ui";
import { TeacherGroupsSection } from "@/components/assignment/group-management";

const STATUS_FILTERS = ["", "DRAFT", "PUBLISHED", "CLOSED"] as const;

/** C-TC-12 — every assignment this teacher created. */
export function TeacherAssignmentsPage() {
  const [status, setStatus] = useState<string>("");
  const [busyPublishId, setBusyPublishId] = useState<string | null>(null);
  const resource = useResource(
    () => fetchTeacherAssignments({ status: status || undefined, limit: 100 }),
    [status],
  );

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Assignments"
        subtitle="Assignments you created for your classes, with submission progress."
        action={
          <Link
            href="/teacher/assignments/new"
            className="inline-flex h-10 items-center gap-2 rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover"
          >
            <Plus className="h-4 w-4" /> Create assignment
          </Link>
        }
      />
      <div className="mb-5 flex flex-wrap gap-2">
        {STATUS_FILTERS.map((option) => (
          <button
            key={option || "ALL"}
            type="button"
            onClick={() => setStatus(option)}
            aria-pressed={status === option}
            className={`h-9 rounded-field border px-4 text-xs font-semibold transition ${
              status === option
                ? "border-accent bg-accent-light text-accent"
                : "border-border text-muted-foreground hover:border-accent hover:text-accent"
            }`}
          >
            {option ? statusLabel(option) : "All"}
          </button>
        ))}
      </div>
      <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading your assignments…">
        {resource.data ? (
          <Card className="!p-0">
            {resource.data.items.length ? (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                      <th className="px-5 py-3">Assignment</th>
                      <th className="px-5 py-3">Class · Subject</th>
                      <th className="px-5 py-3">Due</th>
                      <th className="px-5 py-3">Submissions</th>
                      <th className="px-5 py-3">Status</th>
                      <th className="px-5 py-3"><span className="sr-only">Open</span></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {resource.data.items.map((assignment) => (
                      <tr key={assignment.id} className="hover:bg-muted/40">
                        <td className="px-5 py-3 font-semibold text-primary">
                          {assignment.title}
                          <span className="block text-[11px] font-normal text-muted-foreground">
                            {statusLabel(assignment.assignment_type)} · {assignment.total_marks} marks
                            {assignment.milestone_count ? ` · ${assignment.milestone_count} milestones` : ""}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-muted-foreground">{assignment.class_name} · {assignment.subject_code}</td>
                        <td className="px-5 py-3 text-muted-foreground">{dateTime(assignment.due_date)}</td>
                        <td className="px-5 py-3 text-muted-foreground">
                          {assignment.submission_count}/{assignment.student_count}
                          {assignment.pending_review_count ? (
                            <span className="block text-[11px] font-semibold text-warning-text">{assignment.pending_review_count} to review</span>
                          ) : null}
                        </td>
                        <td className="px-5 py-3">
                          <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${
                            assignment.status === "PUBLISHED"
                              ? "bg-success-light text-success-text"
                              : assignment.status === "DRAFT"
                                ? "bg-muted text-muted-foreground"
                                : "bg-warning-light text-warning-text"
                          }`}>
                            {statusLabel(assignment.status)}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-right">
                          <div className="flex items-center justify-end gap-2">
                            {assignment.status === "DRAFT" ? (
                              <button
                                type="button"
                                disabled={busyPublishId === assignment.id}
                                onClick={async () => {
                                  setBusyPublishId(assignment.id);
                                  try {
                                    await publishTeacherAssignment(assignment.id);
                                    await resource.reload();
                                  } catch (err) {
                                    alert(err instanceof Error ? err.message : "Could not publish assignment");
                                  } finally {
                                    setBusyPublishId(null);
                                  }
                                }}
                                className="inline-flex h-7 items-center gap-1 rounded-field bg-accent px-2.5 text-xs font-semibold text-white shadow-accent hover:bg-accent-hover disabled:opacity-60"
                              >
                                <Send className="h-3 w-3" /> {busyPublishId === assignment.id ? "Publishing…" : "Publish"}
                              </button>
                            ) : null}
                            <Link href={`/teacher/assignments/${assignment.id}`} className="text-xs font-semibold text-accent hover:underline">
                              {assignment.status === "DRAFT" ? "Edit" : "Open"}
                            </Link>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyTable text="No assignments here yet. Create your first assignment." />
            )}
          </Card>
        ) : null}
      </AsyncState>
    </div>
  );
}

function toDatetimeLocal(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "";
  const pad = (n: number) => `${n}`.padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** C-TC-13 — create assignment form. */
export function TeacherCreateAssignmentPage() {
  const router = useRouter();
  const assignments = useResource(fetchTeachingAssignments, []);
  const [form, setForm] = useState({
    title: "",
    description: "",
    classSubject: "",
    assignment_type: "REGULAR",
    total_marks: "50",
    passing_marks: "20",
    due_date: "",
    allow_late_submission: false,
    late_penalty_percent: "0",
    max_file_size_mb: "10",
    allowed_file_types: "pdf, doc, docx, zip",
    min_group_size: "2",
    max_group_size: "6",
    instructions_url: "",
    publish: true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options = useMemo(
    () =>
      (assignments.data ?? []).map((assignment) => ({
        key: `${assignment.subject_id}:${assignment.class_id}`,
        subjectId: assignment.subject_id,
        classId: assignment.class_id,
        label: `${assignment.subject_code} · ${assignment.class_name}`,
      })),
    [assignments.data],
  );

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const [subjectId, classId] = form.classSubject.split(":");
    if (!subjectId || !classId) {
      setError("Select the class and subject for this assignment.");
      return;
    }
    if (!form.due_date) {
      setError("Pick a due date.");
      return;
    }
    const total = Number(form.total_marks);
    if (Number(form.passing_marks) > total) {
      setError("Passing marks cannot exceed total marks.");
      return;
    }
    const minGrp = Number(form.min_group_size);
    const maxGrp = Number(form.max_group_size);
    if (form.assignment_type === "GROUP" && minGrp > maxGrp) {
      setError("Minimum group size cannot exceed maximum group size.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await createTeacherAssignment({
        title: form.title.trim(),
        description: form.description.trim(),
        subject_id: subjectId,
        class_id: classId,
        assignment_type: form.assignment_type as "REGULAR" | "MILESTONE" | "GROUP",
        total_marks: total,
        passing_marks: Number(form.passing_marks),
        due_date: new Date(form.due_date).toISOString(),
        allow_late_submission: form.allow_late_submission,
        late_penalty_percent: Number(form.late_penalty_percent),
        max_file_size_mb: Number(form.max_file_size_mb),
        allowed_file_types: form.allowed_file_types.split(",").map((ext) => ext.trim().toLowerCase()).filter(Boolean),
        min_group_size: minGrp,
        max_group_size: maxGrp,
        instructions_url: form.instructions_url.trim() || null,
        publish: form.publish,
      });
      router.replace(`/teacher/assignments/${created.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create this assignment.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Create assignment" subtitle="Publish now, or keep it a draft and publish from the detail page." />
      <AsyncState loading={assignments.loading} error={assignments.error} onRetry={assignments.reload} loadingLabel="Loading your teaching scope…">
        <Card>
          <form onSubmit={submit} className="space-y-5">
            <div>
              <label htmlFor="assignment-title" className={labelClass}>Title</label>
              <input id="assignment-title" className={inputClass} maxLength={255} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required />
            </div>
            <div>
              <label htmlFor="assignment-description" className={labelClass}>Instructions</label>
              <textarea id="assignment-description" className={`${inputClass} min-h-32 py-3`} maxLength={20000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} required />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="assignment-class-subject" className={labelClass}>Class &amp; subject</label>
                <select id="assignment-class-subject" className={inputClass} value={form.classSubject} onChange={(event) => setForm({ ...form, classSubject: event.target.value })} required>
                  <option value="">Select class and subject</option>
                  {options.map((option) => (
                    <option key={option.key} value={option.key}>{option.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="assignment-type" className={labelClass}>Type</label>
                <select id="assignment-type" className={inputClass} value={form.assignment_type} onChange={(event) => setForm({ ...form, assignment_type: event.target.value })}>
                  <option value="REGULAR">Regular</option>
                  <option value="MILESTONE">Milestone-based</option>
                  <option value="GROUP">Group</option>
                </select>
              </div>
            </div>
            {form.assignment_type === "GROUP" ? (
              <div className="grid gap-4 rounded-field border border-accent/20 bg-accent-light/10 p-3 sm:grid-cols-2">
                <div>
                  <label htmlFor="assignment-min-group" className={labelClass}>Minimum students per group</label>
                  <input
                    id="assignment-min-group"
                    type="number"
                    min={2}
                    max={50}
                    className={inputClass}
                    value={form.min_group_size}
                    onChange={(event) => setForm({ ...form, min_group_size: event.target.value })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="assignment-max-group" className={labelClass}>Maximum students per group</label>
                  <input
                    id="assignment-max-group"
                    type="number"
                    min={2}
                    max={50}
                    className={inputClass}
                    value={form.max_group_size}
                    onChange={(event) => setForm({ ...form, max_group_size: event.target.value })}
                    required
                  />
                </div>
              </div>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <label htmlFor="assignment-total" className={labelClass}>Total marks</label>
                <input id="assignment-total" type="number" min={1} max={1000} className={inputClass} value={form.total_marks} onChange={(event) => setForm({ ...form, total_marks: event.target.value })} required />
              </div>
              <div>
                <label htmlFor="assignment-passing" className={labelClass}>Passing marks</label>
                <input id="assignment-passing" type="number" min={0} max={1000} className={inputClass} value={form.passing_marks} onChange={(event) => setForm({ ...form, passing_marks: event.target.value })} required />
              </div>
              <div>
                <label htmlFor="assignment-due" className={labelClass}>Due date</label>
                <input id="assignment-due" type="datetime-local" className={inputClass} value={form.due_date} onChange={(event) => setForm({ ...form, due_date: event.target.value })} required />
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <label htmlFor="assignment-max-size" className={labelClass}>Max file size (MB)</label>
                <input id="assignment-max-size" type="number" min={1} max={100} className={inputClass} value={form.max_file_size_mb} onChange={(event) => setForm({ ...form, max_file_size_mb: event.target.value })} required />
              </div>
              <div className="sm:col-span-2">
                <label htmlFor="assignment-file-types" className={labelClass}>Allowed file types (comma separated)</label>
                <input id="assignment-file-types" className={inputClass} value={form.allowed_file_types} onChange={(event) => setForm({ ...form, allowed_file_types: event.target.value })} placeholder="pdf, doc, docx, zip" />
              </div>
            </div>
            <div>
              <label htmlFor="assignment-instructions-url" className={labelClass}>Reference link (optional)</label>
              <input id="assignment-instructions-url" type="url" className={inputClass} value={form.instructions_url} onChange={(event) => setForm({ ...form, instructions_url: event.target.value })} placeholder="https://…" />
            </div>
            <fieldset className="grid gap-3 sm:grid-cols-2">
              <label className="flex items-center gap-2 text-sm font-medium text-primary">
                <input type="checkbox" className="h-4 w-4 rounded border-border accent-accent" checked={form.allow_late_submission} onChange={(event) => setForm({ ...form, allow_late_submission: event.target.checked })} />
                Allow late submissions
              </label>
              <label className="flex items-center gap-2 text-sm font-medium text-primary">
                <input type="checkbox" className="h-4 w-4 rounded border-border accent-accent" checked={form.publish} onChange={(event) => setForm({ ...form, publish: event.target.checked })} />
                Publish immediately
              </label>
            </fieldset>
            {form.allow_late_submission ? (
              <div className="max-w-56">
                <label htmlFor="assignment-penalty" className={labelClass}>Late penalty (%)</label>
                <input id="assignment-penalty" type="number" min={0} max={100} className={inputClass} value={form.late_penalty_percent} onChange={(event) => setForm({ ...form, late_penalty_percent: event.target.value })} />
              </div>
            ) : null}
            {error ? <p role="alert" className="text-sm text-destructive-text">{error}</p> : null}
            <div className="flex flex-wrap gap-3">
              <button type="submit" disabled={busy} className="inline-flex h-11 items-center rounded-field bg-accent px-5 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60">
                {busy ? "Creating…" : "Create assignment"}
              </button>
              <Link href="/teacher/assignments" className="inline-flex h-11 items-center rounded-field border border-border px-5 text-sm font-semibold text-muted-foreground hover:border-accent hover:text-accent">
                Cancel
              </Link>
            </div>
          </form>
        </Card>
      </AsyncState>
    </div>
  );
}

/** C-TC-14 — edit an assignment, manage milestones, publish / close. */
export function TeacherAssignmentDetailPage() {
  const params = useParams<{ id?: string }>();
  const assignmentId = params?.id ?? "";
  const resource = useResource(
    () => (assignmentId ? fetchTeacherAssignment(assignmentId) : Promise.reject(new Error("No assignment ID provided"))),
    [assignmentId],
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reopenPrompt, setReopenPrompt] = useState(false);
  const data = resource.data;

  const [edit, setEdit] = useState<{ title: string; description: string; due_date: string; total_marks: string; passing_marks: string } | null>(null);

  async function run(action: string, task: () => Promise<Awaited<ReturnType<typeof fetchTeacherAssignment>>>) {
    setBusy(action);
    setActionError(null);
    try {
      const updated = await task();
      if (resource.data) resource.setData({ ...resource.data, ...updated });
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "The action failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title={resource.data ? resource.data.title : "Assignment"}
        subtitle="Edit the draft, manage milestones and review submissions."
        action={
          resource.data ? (
            <div className="flex flex-wrap gap-2">
              <Link href={`/teacher/assignments/${assignmentId}/submissions`} className="inline-flex h-10 items-center rounded-field border border-border px-4 text-sm font-semibold text-primary hover:border-accent hover:text-accent">
                Submissions ({resource.data.submission_count}/{resource.data.student_count})
              </Link>
              {resource.data.status === "DRAFT" ? (
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => run("publish", () => publishTeacherAssignment(assignmentId))}
                  className="inline-flex h-10 items-center gap-2 rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60"
                >
                  <Send className="h-4 w-4" /> {busy === "publish" ? "Publishing…" : "Publish"}
                </button>
              ) : null}
              {resource.data.status === "PUBLISHED" ? (
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => run("close", () => closeTeacherAssignment(assignmentId))}
                  className="inline-flex h-10 items-center gap-2 rounded-field border border-warning-border px-4 text-sm font-semibold text-warning-text transition hover:bg-warning-light disabled:opacity-60"
                >
                  <Ban className="h-4 w-4" /> {busy === "close" ? "Closing…" : "Close"}
                </button>
              ) : null}
              {resource.data.status === "CLOSED" ? (
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => setReopenPrompt(true)}
                  className="inline-flex h-10 items-center gap-2 rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60"
                >
                  <RotateCcw className="h-4 w-4" /> Reopen assignment
                </button>
              ) : null}
            </div>
          ) : undefined
        }
      />
      {actionError ? <p role="alert" className="mb-3 text-sm text-destructive-text">{actionError}</p> : null}
      {reopenPrompt && data?.status === "CLOSED" ? (
        <div className="mb-5 grid gap-3 rounded-field border border-border bg-muted/40 p-4" role="dialog" aria-label="Reopen assignment">
          <div>
            <h2 className="text-sm font-bold text-primary">Reopen this assignment?</h2>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Students can submit again while it stays published. You choose what happens to work that is
              already in but has not been reviewed yet:
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy !== null}
              onClick={async () => {
                setReopenPrompt(false);
                await run("reopen", () => reopenTeacherAssignment(assignmentId, true));
              }}
              className="inline-flex h-10 items-center gap-2 rounded-field bg-accent px-4 text-xs font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60"
            >
              <RotateCcw className="h-4 w-4" /> {busy === "reopen" ? "Reopening…" : "Reopen & ask students to resubmit"}
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={async () => {
                setReopenPrompt(false);
                await run("reopen", () => reopenTeacherAssignment(assignmentId, false));
              }}
              className="inline-flex h-10 items-center gap-2 rounded-field border border-border px-4 text-xs font-semibold text-primary transition hover:border-accent hover:text-accent disabled:opacity-60"
            >
              Reopen for new submissions only
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => setReopenPrompt(false)}
              className="inline-flex h-10 items-center rounded-field px-4 text-xs font-semibold text-muted-foreground hover:text-primary disabled:opacity-60"
            >
              Cancel
            </button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            &ldquo;Resubmit&rdquo; sends already-submitted (un-reviewed) work back to students as
            &ldquo;changes requested&rdquo;; approved or rejected work is never changed.
          </p>
        </div>
      ) : null}
      <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading assignment…">
        {data ? (
          <div className="space-y-5">
            {data.status === "DRAFT" ? (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-field border border-warning-border/40 bg-warning-light/40 p-4 text-warning-text">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Send className="h-4 w-4 text-warning-text" />
                  <span>This assignment is in <strong>Draft mode</strong> and is not visible to students yet.</span>
                </div>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => run("publish", () => publishTeacherAssignment(assignmentId))}
                  className="inline-flex h-9 items-center gap-1.5 rounded-field bg-accent px-4 text-xs font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60"
                >
                  <Send className="h-3.5 w-3.5" /> {busy === "publish" ? "Publishing…" : "Publish Assignment"}
                </button>
              </div>
            ) : null}
            <Card>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-display text-base font-bold text-primary">Details</h2>
                {data.status === "DRAFT" ? (
                  <button
                    type="button"
                    onClick={() =>
                      setEdit(
                        edit
                          ? null
                          : {
                              title: data.title,
                              description: data.description,
                              due_date: toDatetimeLocal(data.due_date),
                              total_marks: String(data.total_marks),
                              passing_marks: String(data.passing_marks),
                            },
                      )
                    }
                    className="inline-flex h-8 items-center rounded-field border border-border px-2.5 text-xs font-semibold text-primary hover:border-accent hover:text-accent"
                  >
                    {edit ? "Cancel edit" : "Edit"}
                  </button>
                ) : null}
              </div>
              {edit ? (
                <form
                  className="space-y-4"
                  onSubmit={(event) => {
                    event.preventDefault();
                    run("save", () =>
                      updateTeacherAssignment(assignmentId, {
                        title: edit.title.trim(),
                        description: edit.description.trim(),
                        due_date: new Date(edit.due_date).toISOString(),
                        total_marks: Number(edit.total_marks),
                        passing_marks: Number(edit.passing_marks),
                      }),
                    ).then(() => setEdit(null));
                  }}
                >
                  <div>
                    <label htmlFor="edit-title" className={labelClass}>Title</label>
                    <input id="edit-title" className={inputClass} maxLength={255} value={edit.title} onChange={(event) => setEdit({ ...edit, title: event.target.value })} required />
                  </div>
                  <div>
                    <label htmlFor="edit-description" className={labelClass}>Instructions</label>
                    <textarea id="edit-description" className={`${inputClass} min-h-28 py-3`} maxLength={20000} value={edit.description} onChange={(event) => setEdit({ ...edit, description: event.target.value })} required />
                  </div>
                  <div className="grid gap-4 sm:grid-cols-3">
                    <div>
                      <label htmlFor="edit-total" className={labelClass}>Total marks</label>
                      <input id="edit-total" type="number" min={1} max={1000} className={inputClass} value={edit.total_marks} onChange={(event) => setEdit({ ...edit, total_marks: event.target.value })} required />
                    </div>
                    <div>
                      <label htmlFor="edit-passing" className={labelClass}>Passing marks</label>
                      <input id="edit-passing" type="number" min={0} max={1000} className={inputClass} value={edit.passing_marks} onChange={(event) => setEdit({ ...edit, passing_marks: event.target.value })} required />
                    </div>
                    <div>
                      <label htmlFor="edit-due" className={labelClass}>Due date</label>
                      <input id="edit-due" type="datetime-local" className={inputClass} value={edit.due_date} onChange={(event) => setEdit({ ...edit, due_date: event.target.value })} required />
                    </div>
                  </div>
                  <button type="submit" disabled={busy !== null} className="inline-flex h-10 items-center rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60">
                    {busy === "save" ? "Saving…" : "Save changes"}
                  </button>
                </form>
              ) : (
                <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                  <Meta label="Class" value={`${data.class_name} · ${data.subject_code} ${data.subject_name}`} />
                  <Meta label="Type" value={statusLabel(data.assignment_type)} />
                  <Meta label="Marks" value={`${data.total_marks} total · pass ${data.passing_marks}`} />
                  <Meta label="Due" value={dateTime(data.due_date)} />
                  {data.assignment_type === "GROUP" ? (
                    <Meta label="Group size" value={`${data.min_group_size} to ${data.max_group_size} students`} />
                  ) : null}
                  <Meta label="Late submissions" value={data.allow_late_submission ? `Allowed (−${data.late_penalty_percent}%)` : "Not allowed"} />
                  <Meta label="File policy" value={`${data.allowed_file_types.map((ext) => `.${ext}`).join(" ")} · up to ${data.max_file_size_mb} MB`} />
                  <Meta label="Status" value={statusLabel(data.status)} />
                  <Meta label="Created" value={dateTime(data.created_at)} />
                </dl>
              )}
              {!edit && data.description ? (
                <p className="mt-3 whitespace-pre-wrap border-t border-border pt-3 text-sm text-muted-foreground">{data.description}</p>
              ) : null}
              {!edit && data.instructions_url ? (
                <a href={data.instructions_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm font-semibold text-accent hover:underline">
                  Reference link
                </a>
              ) : null}
            </Card>
            {data.assignment_type === "GROUP" ? (
              <TeacherGroupsSection
                assignmentId={assignmentId}
                minGroupSize={data.min_group_size}
                maxGroupSize={data.max_group_size}
              />
            ) : null}
            <MilestonesCard
              assignmentId={assignmentId}
              milestones={data.milestones}
              editable={data.status !== "CLOSED"}
              onChanged={(detail) => resource.setData({ ...data, ...detail })}
            />
          </div>
        ) : null}
      </AsyncState>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-32 shrink-0 font-medium text-muted-foreground">{label}</dt>
      <dd className="font-medium text-primary">{value}</dd>
    </div>
  );
}

function MilestonesCard({
  assignmentId,
  milestones,
  editable,
  onChanged,
}: {
  assignmentId: string;
  milestones: Awaited<ReturnType<typeof fetchTeacherAssignment>>["milestones"];
  editable: boolean;
  onChanged: (detail: Awaited<ReturnType<typeof fetchTeacherAssignment>>) => void;
}) {
  const [form, setForm] = useState({ title: "", description: "", marks: "10", due_date: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const detail = await addAssignmentMilestone(assignmentId, {
        title: form.title.trim(),
        description: form.description.trim() || null,
        marks: Number(form.marks),
        due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
      });
      onChanged(detail);
      setForm({ title: "", description: "", marks: "10", due_date: "" });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not add this milestone.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(milestoneId: string) {
    setBusy(true);
    setError(null);
    try {
      const detail = await deleteAssignmentMilestone(assignmentId, milestoneId);
      onChanged(detail);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not remove this milestone.");
    } finally {
      setBusy(false);
    }
  }

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ title: "", description: "", marks: "10", due_date: "" });

  function startEditing(milestone: (typeof milestones)[number]) {
    setEditingId(milestone.id);
    setEditForm({
      title: milestone.title,
      description: milestone.description ?? "",
      marks: String(milestone.marks),
      due_date: toDatetimeLocal(milestone.due_date),
    });
  }

  async function saveEdit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingId) return;
    setBusy(true);
    setError(null);
    try {
      const detail = await updateAssignmentMilestone(assignmentId, editingId, {
        title: editForm.title.trim(),
        description: editForm.description.trim() || null,
        marks: Number(editForm.marks),
        due_date: editForm.due_date ? new Date(editForm.due_date).toISOString() : null,
      });
      onChanged(detail);
      setEditingId(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update this milestone.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-base font-bold text-primary">Milestones</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">Stages unlock in order; students submit against each stage.</p>
        </div>
        {milestones.length ? (
          <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-semibold text-muted-foreground">{milestones.length} stages</span>
        ) : null}
      </div>

      {milestones.length ? (
        <ol className="relative">
          {milestones.map((milestone, idx) => {
            const isLast = idx === milestones.length - 1;
            const isEditing = editingId === milestone.id;

            return (
              <li key={milestone.id} className="flex gap-4">
                {/* Connector column */}
                <div className="flex flex-col items-center">
                  <div className="relative z-10 mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 border-accent bg-accent-light text-accent">
                    <span className="text-xs font-bold">{idx + 1}</span>
                  </div>
                  {!isLast && <div className="w-0.5 flex-1 bg-border" style={{ minHeight: "1.5rem" }} />}
                </div>

                {/* Content */}
                <div className={`flex-1 ${isLast ? "pb-0" : "pb-5"}`}>
                  {isEditing ? (
                    <form onSubmit={saveEdit} className="space-y-3 rounded-field border border-accent bg-accent-light/10 p-3">
                      <p className="text-xs font-bold text-accent">Edit Stage {idx + 1}</p>
                      <div className="grid gap-3 sm:grid-cols-3">
                        <div className="sm:col-span-2">
                          <label htmlFor={`edit-stage-title-${milestone.id}`} className={labelClass}>Stage title</label>
                          <input
                            id={`edit-stage-title-${milestone.id}`}
                            className={inputClass}
                            maxLength={255}
                            value={editForm.title}
                            onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                            required
                          />
                        </div>
                        <div>
                          <label htmlFor={`edit-stage-marks-${milestone.id}`} className={labelClass}>Marks</label>
                          <input
                            id={`edit-stage-marks-${milestone.id}`}
                            type="number"
                            min={0}
                            max={1000}
                            className={inputClass}
                            value={editForm.marks}
                            onChange={(e) => setEditForm({ ...editForm, marks: e.target.value })}
                            required
                          />
                        </div>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div>
                          <label htmlFor={`edit-stage-due-${milestone.id}`} className={labelClass}>Due date (optional)</label>
                          <input
                            id={`edit-stage-due-${milestone.id}`}
                            type="datetime-local"
                            className={inputClass}
                            value={editForm.due_date}
                            onChange={(e) => setEditForm({ ...editForm, due_date: e.target.value })}
                          />
                        </div>
                        <div>
                          <label htmlFor={`edit-stage-desc-${milestone.id}`} className={labelClass}>Description (optional)</label>
                          <input
                            id={`edit-stage-desc-${milestone.id}`}
                            className={inputClass}
                            maxLength={5000}
                            value={editForm.description}
                            onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                          />
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="submit"
                          disabled={busy}
                          className="inline-flex h-8 items-center rounded-field bg-accent px-3 text-xs font-semibold text-white transition hover:bg-accent-hover disabled:opacity-60"
                        >
                          Save stage
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="inline-flex h-8 items-center rounded-field border border-border px-3 text-xs font-semibold text-muted-foreground hover:border-accent hover:text-accent"
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  ) : (
                    <div className="flex items-start justify-between gap-3 rounded-field border border-border p-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-primary">
                          {milestone.title}
                          <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold text-muted-foreground">{milestone.marks} marks</span>
                        </p>
                        {milestone.description ? <p className="mt-1 text-xs text-muted-foreground">{milestone.description}</p> : null}
                        {milestone.due_date ? <p className="mt-1 text-[11px] text-muted-foreground">Due {dateTime(milestone.due_date)}</p> : null}
                      </div>
                      {editable ? (
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => startEditing(milestone)}
                            aria-label={`Edit milestone ${milestone.title}`}
                            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-field border border-border text-muted-foreground hover:border-accent hover:text-accent disabled:opacity-60"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => remove(milestone.id)}
                            aria-label={`Remove milestone ${milestone.title}`}
                            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-field border border-border text-muted-foreground hover:border-destructive-border hover:text-destructive-text disabled:opacity-60"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      ) : (
        <div className="mt-2 rounded-field border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
          No milestones yet — add stages below, or leave empty for a single-submission assignment.
        </div>
      )}

      {editable ? (
        <form onSubmit={add} className="mt-4 space-y-3 border-t border-border pt-4">
          <p className="text-xs font-semibold text-muted-foreground">Add next stage</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="sm:col-span-2">
              <label htmlFor="milestone-title" className={labelClass}>Milestone title</label>
              <input id="milestone-title" className={inputClass} maxLength={255} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required />
            </div>
            <div>
              <label htmlFor="milestone-marks" className={labelClass}>Marks</label>
              <input id="milestone-marks" type="number" min={0} max={1000} className={inputClass} value={form.marks} onChange={(event) => setForm({ ...form, marks: event.target.value })} required />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="milestone-due" className={labelClass}>Due date (optional)</label>
              <input id="milestone-due" type="datetime-local" className={inputClass} value={form.due_date} onChange={(event) => setForm({ ...form, due_date: event.target.value })} />
            </div>
            <div>
              <label htmlFor="milestone-description" className={labelClass}>Description (optional)</label>
              <input id="milestone-description" className={inputClass} maxLength={5000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
            </div>
          </div>
          {error ? <p role="alert" className="text-sm text-destructive-text">{error}</p> : null}
          <button type="submit" disabled={busy} className="inline-flex h-10 items-center gap-2 rounded-field border border-border px-4 text-sm font-semibold text-primary hover:border-accent hover:text-accent disabled:opacity-60">
            <Plus className="h-4 w-4" /> {busy ? "Adding…" : "Add stage"}
          </button>
        </form>
      ) : null}
    </Card>
  );
}
