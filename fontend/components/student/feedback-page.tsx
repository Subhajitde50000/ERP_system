"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState, Loading } from "@/components/admin/ui";
import { dateTime } from "@/components/principal/principal-ui";
import { CheckCircle2, ChevronRight, Loader2, MessageSquareMore, Star, X } from "lucide-react";

import {
  type StudentFeedbackCampaign,
  type StudentFeedbackTarget,
  type FeedbackSubmit,
  getStudentFeedbackCampaigns,
  submitStudentFeedback,
} from "@/lib/feedback";

import { inputClass, labelClass } from "@/components/admin/ui";

function StarRating({
  value,
  onChange,
  disabled,
}: {
  value: number | null;
  onChange: (v: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          disabled={disabled}
          onClick={() => onChange(n)}
          aria-label={`${n} star${n !== 1 ? "s" : ""}`}
          className={`flex h-9 w-9 items-center justify-center rounded-lg transition
            ${n <= (value ?? 0) ? "text-amber-400" : "text-muted-foreground/30"}
            ${disabled ? "cursor-not-allowed" : "hover:text-amber-400 cursor-pointer hover:bg-muted"}`}
        >
          <Star className="h-5 w-5 fill-current" />
        </button>
      ))}
    </div>
  );
}

interface RatingFormState {
  teaching_clarity: number | null;
  subject_knowledge: number | null;
  interaction: number | null;
  overall: number | null;
  comment: string;
}

const EMPTY_FORM: RatingFormState = {
  teaching_clarity: null,
  subject_knowledge: null,
  interaction: null,
  overall: null,
  comment: "",
};

export function StudentFeedbackPage() {
  const [campaigns, setCampaigns] = useState<StudentFeedbackCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTarget, setActiveTarget] = useState<{
    campaign: StudentFeedbackCampaign;
    target: StudentFeedbackTarget;
  } | null>(null);
  const [formState, setFormState] = useState<RatingFormState>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getStudentFeedbackCampaigns();
      setCampaigns(res ?? []);
    } catch {
      setError("Failed to load feedback campaigns.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openFeedback = (campaign: StudentFeedbackCampaign, target: StudentFeedbackTarget) => {
    if (target.already_submitted) return;
    setActiveTarget({ campaign, target });
    setFormState(EMPTY_FORM);
    setSubmitError(null);
  };

  const handleSubmit = async () => {
    if (!activeTarget) return;
    const { campaign, target } = activeTarget;

    if (
      formState.teaching_clarity === null &&
      formState.subject_knowledge === null &&
      formState.interaction === null &&
      formState.overall === null
    ) {
      setSubmitError("Please rate at least one area.");
      return;
    }

    const payload: FeedbackSubmit = {
      target_id: target.target_id,
      teaching_clarity: formState.teaching_clarity,
      subject_knowledge: formState.subject_knowledge,
      interaction: formState.interaction,
      overall: formState.overall,
      comment: formState.comment.trim() || null,
    };

    setSubmitting(true);
    setSubmitError(null);
    try {
      await submitStudentFeedback(campaign.id, payload);
      setActiveTarget(null);
      // Optimistically mark as submitted
      setCampaigns((prev) =>
        prev.map((c) =>
          c.id !== campaign.id
            ? c
            : {
                ...c,
                targets: c.targets.map((t) =>
                  t.target_id === target.target_id ? { ...t, already_submitted: true } : t
                ),
              }
        )
      );
    } catch (e: unknown) {
      setSubmitError(e instanceof Error ? e.message : "Submission failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <Loading label="Loading feedback campaigns…" />;

  if (error) {
    return (
      <div role="alert" className="rounded-card border border-destructive-border bg-destructive-light px-5 py-10 text-center text-sm font-medium text-destructive-text">
        {error}
      </div>
    );
  }

  if (!campaigns.length) {
    return (
      <div className="flex flex-col items-center py-20 text-center text-muted-foreground">
        <MessageSquareMore className="mb-4 h-12 w-12 opacity-30" aria-hidden="true" />
        <p className="font-medium">No active feedback campaigns</p>
        <p className="mt-1 text-sm">Your institution will notify you when a feedback window opens.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="mb-6">
        <h1 className="font-display text-2xl font-extrabold tracking-tight text-primary">Teacher Feedback</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Rate your teachers. Responses are private — teachers only see averaged results, not your individual reply.
        </p>
      </header>

      {campaigns.map((campaign) => {
        const done = campaign.targets.filter((t) => t.already_submitted).length;
        return (
          <div key={campaign.id} className="rounded-card border border-border bg-white">
            {/* Campaign header */}
            <div className="border-b border-border p-5">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="rounded-full bg-success-light px-2.5 py-1 text-[11px] font-bold text-success-text">Active</span>
                  </div>
                  <h2 className="font-display text-base font-bold text-primary">{campaign.title}</h2>
                  {campaign.description && (
                    <p className="mt-1 text-sm text-muted-foreground">{campaign.description}</p>
                  )}
                </div>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Available until {dateTime(campaign.ends_at)} · {done}/{campaign.targets.length} submitted
              </p>
            </div>

            {/* Targets list */}
            <ul className="divide-y divide-border">
              {campaign.targets.map((target) => (
                <li key={target.target_id}>
                  <button
                    type="button"
                    disabled={target.already_submitted}
                    onClick={() => openFeedback(campaign, target)}
                    className={`w-full flex items-center justify-between gap-3 px-5 py-4 text-left transition
                      ${target.already_submitted
                        ? "cursor-default opacity-70"
                        : "hover:bg-muted/50 cursor-pointer"
                      }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold
                        ${target.already_submitted ? "bg-success-light text-success-text" : "bg-accent-light text-accent"}`}>
                        {(target.teacher_name ?? "T").charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-primary">{target.teacher_name ?? "Teacher"}</p>
                        <p className="text-xs text-muted-foreground">
                          {target.subject_name ?? "All subjects"}
                          {target.class_name && ` · ${target.class_name}`}
                        </p>
                      </div>
                    </div>
                    {target.already_submitted ? (
                      <CheckCircle2 className="h-5 w-5 shrink-0 text-success-text" />
                    ) : (
                      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        );
      })}

      {/* Feedback form modal */}
      {activeTarget && (
        <div role="dialog" aria-modal="true" aria-label="Submit feedback" className="fixed inset-0 z-50 flex items-center justify-center bg-primary/50 p-4">
          <div className="w-full max-w-md rounded-card bg-white p-5 shadow-2xl sm:p-6">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <h2 className="font-display text-lg font-bold text-primary">
                  Rate: {activeTarget.target.teacher_name ?? "Teacher"}
                </h2>
                {activeTarget.target.subject_name && (
                  <p className="text-sm text-muted-foreground">
                    {activeTarget.target.subject_name}
                    {activeTarget.target.class_name && ` · ${activeTarget.target.class_name}`}
                  </p>
                )}
              </div>
              <button type="button" onClick={() => setActiveTarget(null)} aria-label="Close" className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-primary">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-5">
              {([
                { key: "teaching_clarity", label: "Teaching Clarity" },
                { key: "subject_knowledge", label: "Subject Knowledge" },
                { key: "interaction", label: "Interaction & Approachability" },
                { key: "overall", label: "Overall Rating" },
              ] as const).map(({ key, label }) => (
                <div key={key}>
                  <label className={labelClass}>{label}</label>
                  <StarRating
                    value={formState[key]}
                    onChange={(v) => setFormState((prev) => ({ ...prev, [key]: v }))}
                    disabled={submitting}
                  />
                </div>
              ))}

              <div>
                <label htmlFor="fb-comment" className={labelClass}>
                  Comment <span className="font-normal text-muted-foreground">(optional)</span>
                </label>
                <textarea
                  id="fb-comment"
                  rows={3}
                  className={`${inputClass} py-2`}
                  placeholder="Any suggestions or observations…"
                  value={formState.comment}
                  onChange={(e) => setFormState((prev) => ({ ...prev, comment: e.target.value }))}
                  disabled={submitting}
                />
              </div>

              <p className="text-xs text-muted-foreground">
                🔒 Your feedback is private. Teachers see only averaged results — never your individual response.
              </p>

              {submitError && (
                <p role="alert" className="text-sm text-destructive-text">{submitError}</p>
              )}

              <div className="flex flex-wrap gap-3 border-t border-border pt-4">
                <button
                  type="button"
                  onClick={() => setActiveTarget(null)}
                  disabled={submitting}
                  className="inline-flex h-10 items-center rounded-field border border-border px-4 text-sm font-semibold text-muted-foreground transition hover:border-accent hover:text-accent"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={submitting}
                  className="inline-flex h-10 items-center gap-2 rounded-field bg-accent px-5 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60"
                >
                  {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                  {submitting ? "Submitting…" : "Submit Feedback"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
