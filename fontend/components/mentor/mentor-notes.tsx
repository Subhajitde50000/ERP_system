"use client";

import { useState } from "react";

import { Card, EmptyState, PageHeader, inputClass } from "@/components/admin/ui";
import { useResource } from "@/hooks/use-resource";
import { fetchMentorMentees, fetchMentorNotes, type MentorNoteRow } from "@/lib/mentor";
import { AsyncState } from "@/components/principal/principal-ui";

import { MentorNoteItem } from "./mentor-note-form";
import { secondaryButtonClass } from "./mentor-ui";

const PAGE_SIZE = 20;

/** Mentoring log across every mentee — searchable, paginated, editable inline. */
export function MentorNotesPage() {
  const [query, setQuery] = useState("");
  const [studentId, setStudentId] = useState("");
  const [offset, setOffset] = useState(0);
  const mentees = useResource(() => fetchMentorMentees(), []);
  const resource = useResource(
    () => fetchMentorNotes({ query: query || undefined, studentId: studentId || undefined, limit: PAGE_SIZE, offset }),
    [query, studentId, offset],
  );

  const replace = (note: MentorNoteRow) => resource.data && resource.setData({ ...resource.data, items: resource.data.items.map((row) => (row.id === note.id ? note : row)) });
  const drop = (noteId: string) => resource.data && resource.setData({ ...resource.data, total: resource.data.total - 1, items: resource.data.items.filter((row) => row.id !== noteId) });

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Mentoring log" subtitle="Your conversation notes and follow-ups, plus notes other mentors chose to share. Add new entries from a mentee's profile." />
      <Card className="mb-5 !p-4">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_260px]">
          <div><label htmlFor="note-search" className="sr-only">Search notes</label><input id="note-search" type="search" value={query} onChange={(event) => { setQuery(event.target.value); setOffset(0); }} className={inputClass} placeholder="Search note text" /></div>
          <div><label htmlFor="note-student" className="sr-only">Mentee</label><select id="note-student" value={studentId} onChange={(event) => { setStudentId(event.target.value); setOffset(0); }} className={inputClass}><option value="">All mentees</option>{(mentees.data?.items ?? []).map((row) => <option key={row.student_id} value={row.student_id}>{row.student_name}{row.class_name ? ` · ${row.class_name}` : ""}</option>)}</select></div>
        </div>
      </Card>
      <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading your log…">
        {resource.data ? (
          <>
            {resource.data.items.length ? (
              <ul className="space-y-3">{resource.data.items.map((note) => <MentorNoteItem key={note.id} note={note} showStudent onChanged={replace} onDeleted={drop} />)}</ul>
            ) : (
              <Card><EmptyState text="No notes match this filter." /></Card>
            )}
            {resource.data.total > PAGE_SIZE ? (
              <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
                <span>{offset + 1}–{Math.min(offset + PAGE_SIZE, resource.data.total)} of {resource.data.total}</span>
                <span className="flex gap-2">
                  <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} className={secondaryButtonClass}>Previous</button>
                  <button type="button" disabled={offset + PAGE_SIZE >= resource.data.total} onClick={() => setOffset(offset + PAGE_SIZE)} className={secondaryButtonClass}>Next</button>
                </span>
              </div>
            ) : null}
          </>
        ) : null}
      </AsyncState>
    </div>
  );
}
