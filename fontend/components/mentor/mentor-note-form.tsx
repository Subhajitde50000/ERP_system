"use client";

import { useState } from "react";
import { Pencil, Save, Trash2, X } from "lucide-react";

import { inputClass, labelClass } from "@/components/admin/ui";
import { dateOnly, dateTime } from "@/components/principal/principal-ui";
import {
  createMentorNote,
  deleteMentorNote,
  updateMentorNote,
  type MentorNoteCreate,
  type MentorNoteRow,
} from "@/lib/mentor";

import { PrivacyTag, primaryButtonClass, secondaryButtonClass } from "./mentor-ui";

const today = () => new Date().toISOString().slice(0, 10);

function errorText(caught: unknown, fallback: string) {
  return caught instanceof Error ? caught.message : fallback;
}

/** Write a mentoring-log entry (meeting summary, follow-up, concern) for one mentee. */
export function MentorNoteComposer({ studentId, onSaved }: { studentId: string; onSaved: (note: MentorNoteRow) => void }) {
  const [form, setForm] = useState<MentorNoteCreate>({ body: "", is_private: true, note_date: today() });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!form.body.trim()) {
      setError("Write the note before saving.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSaved(await createMentorNote(studentId, { ...form, body: form.body.trim() }));
      setForm({ body: "", is_private: true, note_date: today() });
    } catch (caught) {
      setError(errorText(caught, "Could not save the note."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div>
        <label htmlFor="mentor-note-body" className={labelClass}>Log a conversation or follow-up</label>
        <textarea id="mentor-note-body" value={form.body} onChange={(event) => setForm({ ...form, body: event.target.value })} rows={4} maxLength={5000} className={`${inputClass} min-h-[96px]`} placeholder="What was discussed, agreed actions, concerns to follow up…" />
      </div>
      <div className="grid gap-3 sm:grid-cols-[180px_minmax(0,1fr)_auto] sm:items-end">
        <div>
          <label htmlFor="mentor-note-date" className={labelClass}>Date</label>
          <input id="mentor-note-date" type="date" value={form.note_date ?? ""} max={today()} onChange={(event) => setForm({ ...form, note_date: event.target.value || null })} className={inputClass} />
        </div>
        <label className="flex items-center gap-2 text-sm text-foreground sm:pb-2.5">
          <input type="checkbox" checked={form.is_private} onChange={(event) => setForm({ ...form, is_private: event.target.checked })} className="h-4 w-4 rounded border-border accent-accent" />
          Keep private (only you can read it)
        </label>
        <button type="submit" disabled={busy} className={primaryButtonClass}><Save className="h-4 w-4" /> {busy ? "Saving…" : "Save note"}</button>
      </div>
      {error ? <p role="alert" className="text-sm text-destructive-text">{error}</p> : null}
    </form>
  );
}

/** One log entry; the author can edit or delete it inline. */
export function MentorNoteItem({
  note,
  showStudent = false,
  onChanged,
  onDeleted,
}: {
  note: MentorNoteRow;
  showStudent?: boolean;
  onChanged: (note: MentorNoteRow) => void;
  onDeleted: (noteId: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ body: note.body, is_private: note.is_private, note_date: note.note_date });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (!draft.body.trim()) {
      setError("The note cannot be empty.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onChanged(await updateMentorNote(note.id, { ...draft, body: draft.body.trim() }));
      setEditing(false);
    } catch (caught) {
      setError(errorText(caught, "Could not update the note."));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm("Delete this note permanently?")) return;
    setBusy(true);
    setError(null);
    try {
      await deleteMentorNote(note.id);
      onDeleted(note.id);
    } catch (caught) {
      setError(errorText(caught, "Could not delete the note."));
      setBusy(false);
    }
  }

  return (
    <li className="rounded-field border border-border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 text-xs text-muted-foreground">
          {showStudent ? <span className="mr-2 font-semibold text-primary">{note.student_name}{note.class_name ? ` · ${note.class_name}` : ""}</span> : null}
          <time dateTime={note.note_date}>{dateOnly(note.note_date)}</time>
          {" · "}
          {note.is_own ? "You" : note.author_name ?? "Mentor"}
          {note.updated_at !== note.created_at ? ` · edited ${dateTime(note.updated_at)}` : ""}
        </div>
        <div className="flex items-center gap-2">
          <PrivacyTag isPrivate={note.is_private} />
          {note.is_own && !editing ? (
            <>
              <button type="button" onClick={() => setEditing(true)} aria-label="Edit note" className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-primary"><Pencil className="h-4 w-4" /></button>
              <button type="button" onClick={remove} disabled={busy} aria-label="Delete note" className="rounded p-1 text-destructive-text hover:bg-destructive-light disabled:opacity-50"><Trash2 className="h-4 w-4" /></button>
            </>
          ) : null}
        </div>
      </div>
      {editing ? (
        <div className="mt-3 space-y-3">
          <textarea value={draft.body} onChange={(event) => setDraft({ ...draft, body: event.target.value })} rows={4} maxLength={5000} className={`${inputClass} min-h-[96px]`} aria-label="Note text" />
          <div className="flex flex-wrap items-center gap-3">
            <input type="date" value={draft.note_date} max={today()} onChange={(event) => setDraft({ ...draft, note_date: event.target.value })} className={`${inputClass} !w-auto`} aria-label="Note date" />
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.is_private} onChange={(event) => setDraft({ ...draft, is_private: event.target.checked })} className="h-4 w-4 rounded border-border accent-accent" /> Private</label>
            <span className="ml-auto flex gap-2">
              <button type="button" onClick={() => { setEditing(false); setDraft({ body: note.body, is_private: note.is_private, note_date: note.note_date }); }} className={secondaryButtonClass}><X className="h-4 w-4" /> Cancel</button>
              <button type="button" onClick={save} disabled={busy} className={primaryButtonClass}><Save className="h-4 w-4" /> {busy ? "Saving…" : "Save"}</button>
            </span>
          </div>
        </div>
      ) : (
        <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-foreground">{note.body}</p>
      )}
      {error ? <p role="alert" className="mt-2 text-sm text-destructive-text">{error}</p> : null}
    </li>
  );
}
