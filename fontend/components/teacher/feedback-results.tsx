"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState, Loading } from "@/components/admin/ui";
import { dateTime, statusLabel } from "@/components/principal/principal-ui";
import { MessageSquareMore } from "lucide-react";

import { type TeacherFeedbackResult, getTeacherFeedbackResults } from "@/lib/feedback";

const STATUS_CLASS: Record<string, string> = {
  ACTIVE: "bg-success-light text-success-text",
  CLOSED: "bg-muted text-muted-foreground",
  DRAFT: "bg-warning-light text-warning-text",
};

function RatingRow({ label, value }: { label: string; value: number | null }) {
  if (value === null) return null;
  const pct = Math.round((value / 5) * 100);
  return (
    <div className="flex items-center gap-3">
      <span className="w-44 shrink-0 text-sm text-muted-foreground">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
        <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-12 shrink-0 text-right text-sm font-semibold text-primary">
        {value.toFixed(1)}/5
      </span>
    </div>
  );
}

export function TeacherFeedbackResultsPage() {
  const [results, setResults] = useState<TeacherFeedbackResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getTeacherFeedbackResults();
      setResults(res.data ?? []);
    } catch {
      setError("Failed to load feedback results.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <Loading label="Loading feedback results…" />;

  if (error) {
    return (
      <div role="alert" className="rounded-card border border-destructive-border bg-destructive-light px-5 py-10 text-center text-sm font-medium text-destructive-text">
        {error}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <h1 className="font-display text-2xl font-extrabold tracking-tight text-primary">My Feedback Results</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Aggregated student feedback for campaigns you appear in.
          Individual student responses are never shown here.
        </p>
      </header>

      {!results.length ? (
        <div className="flex flex-col items-center py-20 text-center text-muted-foreground">
          <MessageSquareMore className="mb-4 h-12 w-12 opacity-30" aria-hidden="true" />
          <p className="font-medium">No feedback yet</p>
          <p className="mt-1 text-sm">Results appear here once a campaign closes or students start submitting.</p>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {results.map((r) => (
            <div key={r.campaign_id} className="rounded-card border border-border bg-white p-5">
              {/* Card header */}
              <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${STATUS_CLASS[r.status] ?? "bg-muted text-muted-foreground"}`}>
                      {statusLabel(r.status)}
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      {r.response_count} response{r.response_count !== 1 ? "s" : ""}
                    </span>
                  </div>
                  <h2 className="font-display text-base font-bold text-primary">{r.campaign_title}</h2>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {dateTime(r.starts_at)} → {dateTime(r.ends_at)}
                  </p>
                </div>
              </div>

              {/* Ratings */}
              {r.response_count === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">No responses yet</p>
              ) : (
                <div className="space-y-3">
                  <RatingRow label="Teaching Clarity" value={r.teaching_clarity_avg} />
                  <RatingRow label="Subject Knowledge" value={r.subject_knowledge_avg} />
                  <RatingRow label="Interaction" value={r.interaction_avg} />
                  <RatingRow label="Overall" value={r.overall_avg} />

                  {r.comments && r.comments.length > 0 && (
                    <div className="pt-3">
                      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                        Student Comments
                      </p>
                      <ul className="space-y-1.5">
                        {r.comments.map((comment, i) => (
                          <li
                            key={i}
                            className="rounded-field bg-muted px-3 py-2 text-xs italic text-foreground"
                          >
                            "{comment}"
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
