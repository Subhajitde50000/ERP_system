"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { CheckCircle2, Clock, Download, Play, Send } from "lucide-react";

import { Card, PageHeader, labelClass } from "@/components/admin/ui";
import { useResource } from "@/hooks/use-resource";
import {
  fetchAttemptPaper,
  fetchStudentExam,
  fetchStudentExams,
  fetchExamResult,
  reportExamTabSwitch,
  saveExamAnswer,
  startExamAttempt,
  submitExamAttempt,
  type StudentAttemptQuestion,
} from "@/lib/student";
import { AsyncState, EmptyTable, dateTime, percent, statusLabel } from "@/components/principal/principal-ui";

const WHEN_FILTERS = [
  ["", "All"],
  ["upcoming", "Upcoming"],
  ["completed", "Completed"],
] as const;

/** C-ST-07 — every published exam for the student's class. */
export function StudentExamsPage() {
  const [when, setWhen] = useState<string>("upcoming");
  const resource = useResource(
    () => fetchStudentExams({ when: (when || undefined) as "upcoming" | "completed" | "all" | undefined, limit: 100 }),
    [when],
  );

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Examinations" subtitle="Your published exams. Upcoming shows active and scheduled exams; Completed shows past ones." />
      <div className="mb-5 flex flex-wrap gap-2">
        {WHEN_FILTERS.map(([value, label]) => (
          <button
            key={value || "ALL"}
            type="button"
            onClick={() => setWhen(value)}
            aria-pressed={when === value}
            className={`h-9 rounded-field border px-4 text-xs font-semibold transition ${
              when === value
                ? "border-accent bg-accent-light text-accent"
                : "border-border text-muted-foreground hover:border-accent hover:text-accent"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading your exams…">
        {resource.data ? (
          <Card className="!p-0">
            {resource.data.items.length ? (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                      <th className="px-5 py-3">Exam</th>
                      <th className="px-5 py-3">Subject</th>
                      <th className="px-5 py-3">Schedule</th>
                      <th className="px-5 py-3">Marks</th>
                      <th className="px-5 py-3">Status</th>
                      <th className="px-5 py-3"><span className="sr-only">Action</span></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {resource.data.items.map((exam) => (
                      <tr key={exam.id} className="hover:bg-muted/40">
                        <td className="px-5 py-3 font-semibold text-primary">
                          {exam.title}
                          <span className="block text-[11px] font-normal text-muted-foreground">
                            {statusLabel(exam.exam_type)} · {exam.mode} · {exam.duration_minutes} min
                          </span>
                        </td>
                        <td className="px-5 py-3 text-muted-foreground">{exam.subject_code}</td>
                        <td className="px-5 py-3 text-muted-foreground">
                          {dateTime(exam.scheduled_at)}
                          {exam.window_end_at ? <span className="block text-[11px]">until {dateTime(exam.window_end_at)}</span> : null}
                        </td>
                        <td className="px-5 py-3 text-muted-foreground">
                          {exam.total_marks} (pass {exam.passing_marks})
                          {exam.my_score !== null ? <span className="block text-[11px] font-semibold text-success-text">Scored {exam.my_score}</span> : null}
                        </td>
                        <td className="px-5 py-3">
                          {exam.my_attempt_status ? (
                            <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${
                              exam.my_attempt_status === "GRADED"
                                ? "bg-success-light text-success-text"
                                : exam.my_attempt_status === "NOT_ATTEMPTED"
                                ? "bg-destructive-light text-destructive-text"
                                : exam.my_attempt_status === "SUBMITTED"
                                ? "bg-accent-light text-accent"
                                : exam.my_attempt_status === "IN_PROGRESS"
                                ? "bg-warning-light text-warning-text"
                                : "bg-muted text-muted-foreground"
                            }`}>
                              {statusLabel(exam.my_attempt_status)}
                            </span>
                          ) : (
                            <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${exam.status === "ONGOING" || exam.status === "PUBLISHED" ? "bg-accent-light text-accent" : "bg-muted text-muted-foreground"}`}>
                              {statusLabel(exam.status)}
                            </span>
                          )}
                        </td>
                        <td className="px-5 py-3 text-right">
                          {exam.can_attempt ? (
                            <Link href={`/student/examinations/${exam.id}/attempt`} className="inline-flex items-center gap-1 rounded-field bg-accent px-3 py-1.5 text-[11px] font-bold text-white hover:bg-accent-hover">
                              Start exam
                            </Link>
                          ) : exam.result_available ? (
                            <Link href={`/student/examinations/${exam.id}/result`} className="text-xs font-semibold text-accent hover:underline">
                              View result
                            </Link>
                          ) : exam.my_attempt_status === "IN_PROGRESS" ? (
                            <Link href={`/student/examinations/${exam.id}/attempt`} className="inline-flex items-center gap-1 rounded-field bg-warning-light px-3 py-1.5 text-[11px] font-bold text-warning-text hover:opacity-80">
                              Resume
                            </Link>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyTable text="No exams in this view yet." />
            )}
          </Card>
        ) : null}
      </AsyncState>
    </div>
  );
}

function secondsLeft(endsAt: string): number {
  return Math.max(0, Math.floor((new Date(endsAt).getTime() - Date.now()) / 1000));
}

function formatClock(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${`${minutes}`.padStart(2, "0")}:${`${seconds}`.padStart(2, "0")}`;
}

function formatCountdown(totalSeconds: number) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return {
    hours: `${hours}`.padStart(2, "0"),
    minutes: `${minutes}`.padStart(2, "0"),
    seconds: `${seconds}`.padStart(2, "0"),
  };
}

function CountdownToStart({ scheduledAt, onReached }: { scheduledAt: string; onReached: () => void }) {
  const [secondsLeft, setSecondsLeft] = useState<number>(() =>
    Math.max(0, Math.floor((new Date(scheduledAt).getTime() - Date.now()) / 1000))
  );

  useEffect(() => {
    const timer = setInterval(() => {
      const rem = Math.max(0, Math.floor((new Date(scheduledAt).getTime() - Date.now()) / 1000));
      setSecondsLeft(rem);
      if (rem <= 0) {
        clearInterval(timer);
        onReached();
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [scheduledAt, onReached]);

  const { hours, minutes, seconds } = formatCountdown(secondsLeft);

  return (
    <div className="w-full rounded-field border border-accent/30 bg-accent-light/40 p-4 text-center">
      <div className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-accent">
        <Clock className="h-4 w-4 animate-pulse" /> Exam starts in
      </div>
      <div className="mt-2 flex items-center justify-center gap-2 font-mono text-2xl font-bold tracking-tight text-primary">
        <div className="flex flex-col items-center">
          <span className="rounded bg-white px-2 py-1 shadow-sm border border-border">{hours}</span>
          <span className="mt-1 text-[10px] font-sans font-semibold text-muted-foreground uppercase">Hrs</span>
        </div>
        <span className="text-muted-foreground font-sans">:</span>
        <div className="flex flex-col items-center">
          <span className="rounded bg-white px-2 py-1 shadow-sm border border-border">{minutes}</span>
          <span className="mt-1 text-[10px] font-sans font-semibold text-muted-foreground uppercase">Mins</span>
        </div>
        <span className="text-muted-foreground font-sans">:</span>
        <div className="flex flex-col items-center">
          <span className="rounded bg-white px-2 py-1 shadow-sm border border-border text-accent">{seconds}</span>
          <span className="mt-1 text-[10px] font-sans font-semibold text-muted-foreground uppercase">Secs</span>
        </div>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        The &quot;Start exam&quot; button will unlock automatically when the countdown reaches 00:00:00.
      </p>
    </div>
  );
}

/** C-ST-08 — timed exam-attempt screen with autosave and a countdown. */
export function StudentExamAttemptPage() {
  const params = useParams<{ id?: string }>();
  const examId = params?.id ?? "";
  const router = useRouter();
  const exam = useResource(
    () => (examId ? fetchStudentExam(examId) : Promise.reject(new Error("No exam ID provided"))),
    [examId],
  );
  const [started, setStarted] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [startBusy, setStartBusy] = useState(false);

  const detail = exam.data;
  const hasLiveAttempt = detail?.my_attempt_status === "IN_PROGRESS" && (detail?.mode === "ONLINE");

  const isBeforeStart = useMemo(() => {
    if (!detail?.scheduled_at) return false;
    return new Date(detail.scheduled_at).getTime() > Date.now();
  }, [detail?.scheduled_at]);

  async function begin() {
    setStartBusy(true);
    setStartError(null);
    try {
      await startExamAttempt(examId);
      setStarted(true);
    } catch (caught) {
      setStartError(caught instanceof Error ? caught.message : "Could not start the attempt.");
    } finally {
      setStartBusy(false);
    }
  }

  if (started || hasLiveAttempt) {
    return <AttemptRunner examId={examId} onSubmitted={() => router.replace(`/student/examinations/${examId}/result`)} />;
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Exam instructions" subtitle="Read these carefully before you start." />
      <AsyncState loading={exam.loading} error={exam.error} onRetry={exam.reload} loadingLabel="Loading exam…">
        {detail ? (
          <Card>
            <h2 className="font-display text-lg font-bold text-primary">{detail.title}</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {detail.subject_name} · {detail.question_count} questions · {detail.total_marks} marks · {detail.duration_minutes} minutes
            </p>
            <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              <div className="flex gap-2">
                <dt className="w-28 shrink-0 font-medium text-muted-foreground">Starts</dt>
                <dd className="font-medium text-primary">{dateTime(detail.scheduled_at)}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-28 shrink-0 font-medium text-muted-foreground">Window ends</dt>
                <dd className="font-medium text-primary">{detail.window_end_at ? dateTime(detail.window_end_at) : `${detail.duration_minutes} min after start`}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-28 shrink-0 font-medium text-muted-foreground">Type</dt>
                <dd className="font-medium text-primary">{statusLabel(detail.exam_type)}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-28 shrink-0 font-medium text-muted-foreground">Passing</dt>
                <dd className="font-medium text-primary">{detail.passing_marks} marks</dd>
              </div>
            </dl>
            {detail.instructions ? (
              <div className="mt-4 rounded-field bg-muted p-4">
                <h3 className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Instructions</h3>
                <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">{detail.instructions}</p>
              </div>
            ) : null}
            <ul className="mt-4 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
              <li>Answers autosave as you go — you can refresh and resume.</li>
              <li>The attempt auto-submits when the timer ends.</li>
              <li>Objective answers are graded automatically; written answers are graded by your teacher.</li>
            </ul>
            {startError ? <p role="alert" className="mt-4 text-sm text-destructive-text">{startError}</p> : null}
            <div className="mt-5 space-y-4">
              {isBeforeStart ? (
                <CountdownToStart scheduledAt={detail.scheduled_at} onReached={() => exam.reload()} />
              ) : null}
              <div className="flex flex-wrap gap-3">
                {!isBeforeStart && detail.can_attempt ? (
                  <button
                    type="button"
                    disabled={startBusy}
                    onClick={begin}
                    className="inline-flex h-11 items-center gap-2 rounded-field bg-accent px-5 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60"
                  >
                    <Play className="h-4 w-4" /> {startBusy ? "Starting…" : "Start exam"}
                  </button>
                ) : !isBeforeStart ? (
                  <p className="text-sm font-semibold text-warning-text">
                    {detail.my_attempt_status
                      ? `Your attempt is ${statusLabel(detail.my_attempt_status).toLowerCase()}.`
                      : "This exam is not open for attempts right now."}
                  </p>
                ) : null}
                <Link href="/student/examinations" className="inline-flex h-11 items-center rounded-field border border-border px-5 text-sm font-semibold text-muted-foreground hover:border-accent hover:text-accent">
                  Back to exams
                </Link>
              </div>
            </div>
          </Card>
        ) : null}
      </AsyncState>
    </div>
  );
}

function AttemptRunner({ examId, onSubmitted }: { examId: string; onSubmitted: () => void }) {
  const paper = useResource(() => fetchAttemptPaper(examId), [examId]);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [submitBusy, setSubmitBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const endsAt = paper.data?.attempt.ends_at ?? null;

  // C-ST-08 anti-cheat: each time the student leaves the exam tab, the
  // server increments the attempt's tab-switch count (teacher sees it in
  // C-TC-11 results). Reporting must never block the exam itself.
  useEffect(() => {
    function onVisibilityChange() {
      if (document.visibilityState === "hidden") {
        reportExamTabSwitch(examId).catch(() => undefined);
      }
    }
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, [examId]);

  useEffect(() => {
    if (!endsAt) return;
    setRemaining(secondsLeft(endsAt));
    const timer = window.setInterval(() => {
      setRemaining((current) => {
        if (current === null) return secondsLeft(endsAt);
        if (current <= 1) {
          window.clearInterval(timer);
          return 0;
        }
        return current - 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [endsAt]);

  const questions = useMemo(() => paper.data?.questions ?? [], [paper.data]);

  async function save(question: StudentAttemptQuestion, patch: { selected_option_id?: string | null; text_answer?: string | null }) {
    if (!paper.data) return;
    setSaveState("saving");
    try {
      const updated = await saveExamAnswer(examId, {
        question_id: question.id,
        selected_option_id: patch.selected_option_id ?? null,
        text_answer: patch.text_answer ?? null,
      });
      paper.setData(updated);
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  }

  async function submit() {
    setSubmitBusy(true);
    setSubmitError(null);
    try {
      await submitExamAttempt(examId);
      onSubmitted();
    } catch (caught) {
      setSubmitError(caught instanceof Error ? caught.message : "Could not submit the attempt.");
    } finally {
      setSubmitBusy(false);
    }
  }

  const answered = questions.filter(
    (question) => question.my_selected_option_id !== null || (question.my_text_answer ?? "").trim() !== "",
  ).length;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="sticky top-0 z-10 -mx-2 mb-4 flex items-center justify-between gap-3 rounded-card border border-border bg-white px-4 py-3 shadow-sm">
        <div>
          <p className="text-xs font-semibold text-muted-foreground">
            {answered} of {questions.length} answered
            {saveState === "saving" ? " · saving…" : saveState === "saved" ? " · all answers saved" : saveState === "error" ? " · save failed — retry" : ""}
          </p>
        </div>
        <p className={`font-mono text-lg font-bold ${remaining !== null && remaining <= 300 ? "text-destructive-text" : "text-accent"}`} role="timer" aria-label="Time remaining">
          {remaining === null ? "--:--" : formatClock(remaining)}
        </p>
      </div>
      <AsyncState loading={paper.loading} error={paper.error} onRetry={paper.reload} loadingLabel="Loading your paper…">
        {remaining === 0 ? (
          <Card>
            <p className="text-sm font-semibold text-warning-text">Time is up — your answers are being submitted automatically.</p>
            <AutoSubmit examId={examId} onSubmitted={onSubmitted} />
          </Card>
        ) : (
          <div className="space-y-5">
            {questions.map((question, index) => (
              <Card key={question.id}>
                <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                  Question {index + 1} of {questions.length} · {question.marks} marks
                </p>
                <p className="mt-1.5 whitespace-pre-wrap text-sm font-semibold text-primary">{question.text}</p>
                {question.options.length ? (
                  <div className="mt-3 space-y-2" role="radiogroup" aria-label={`Options for question ${index + 1}`}>
                    {question.options.map((option) => {
                      const selected = question.my_selected_option_id === option.id;
                      return (
                        <button
                          key={option.id}
                          type="button"
                          aria-pressed={selected}
                          onClick={() => save(question, { selected_option_id: option.id })}
                          className={`flex w-full items-center gap-3 rounded-field border px-4 py-3 text-left text-sm transition ${
                            selected
                              ? "border-accent bg-accent-light font-semibold text-accent"
                              : "border-border text-primary hover:border-accent"
                          }`}
                        >
                          <span className={`inline-block h-3 w-3 rounded-full border-2 ${selected ? "border-accent bg-accent" : "border-border"}`} />
                          {option.text}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <AnswerTextarea question={question} onSave={(value) => save(question, { text_answer: value })} />
                )}
              </Card>
            ))}
            {submitError ? <p role="alert" className="text-sm text-destructive-text">{submitError}</p> : null}
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                disabled={submitBusy || !questions.length}
                onClick={submit}
                className="inline-flex h-11 items-center gap-2 rounded-field bg-accent px-5 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60"
              >
                <Send className="h-4 w-4" /> {submitBusy ? "Submitting…" : "Submit exam"}
              </button>
              <p className="text-xs text-muted-foreground">Answers are saved automatically; submit when you are done.</p>
            </div>
          </div>
        )}
      </AsyncState>
    </div>
  );
}

function AutoSubmit({ examId, onSubmitted }: { examId: string; onSubmitted: () => void }) {
  useEffect(() => {
    let cancelled = false;
    submitExamAttempt(examId)
      .then(() => {
        if (!cancelled) onSubmitted();
      })
      .catch(() => {
        // The backend also auto-finalises expired attempts; a conflict just
        // means it already ran, so the student still lands on the result.
        if (!cancelled) onSubmitted();
      });
    return () => {
      cancelled = true;
    };
  }, [examId, onSubmitted]);
  return null;
}

function AnswerTextarea({ question, onSave }: { question: StudentAttemptQuestion; onSave: (value: string) => void }) {
  const [value, setValue] = useState(question.my_text_answer ?? "");
  return (
    <div className="mt-3">
      <label htmlFor={`answer-${question.id}`} className={labelClass}>Your answer</label>
      <textarea
        id={`answer-${question.id}`}
        className="min-h-28 w-full rounded-field border border-[#E2E8F0] bg-white px-3.5 py-3 text-sm text-primary outline-none transition placeholder:text-[#94A3B8] focus:border-accent focus:ring-3 focus:ring-accent/15"
        maxLength={20000}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onBlur={() => {
          if (value.trim() !== (question.my_text_answer ?? "")) onSave(value);
        }}
      />
    </div>
  );
}

/** C-ST-09 — score, grade and answer-key review for a released result. */
export function StudentExamResultPage() {
  const params = useParams<{ id?: string }>();
  const examId = params?.id ?? "";
  const resource = useResource(
    () => (examId ? fetchExamResult(examId) : Promise.reject(new Error("No exam ID provided"))),
    [examId],
  );

  const [exportBusy, setExportBusy] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const gradeCardRef = useRef<HTMLDivElement | null>(null);

  /**
   * Grade-card export: render the score card to a PNG via html2canvas and
   * download it. Loaded dynamically so the ~180 KB library never enters the
   * main bundle — only browsers that actually click "Download" pay for it.
   */
  async function downloadGradeCard() {
    const node = gradeCardRef.current;
    if (!node) return;
    setExportBusy(true);
    setExportError(null);
    try {
      const html2canvas = (await import("html2canvas")).default;
      const canvas = await html2canvas(node, {
        backgroundColor: "#ffffff", // grade card must not export with a transparent background
        useCORS: true,              // avatars/logos from other origins, if any
        scale: 2,                   // crisp text on high-DPI screens
        logging: false,
      });
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("The grade card could not be rendered to an image.");
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `grade-card-${resource.data?.exam_id ?? examId}.png`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      // Give the browser a tick to start the download before revoking.
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (caught) {
      console.error("Grade-card export failed", caught);
      setExportError(
        caught instanceof Error ? caught.message : "Could not export the grade card. Please try again.",
      );
    } finally {
      setExportBusy(false);
    }
  }

  // Typed lifecycle from the API; the string fallback keeps older backends
  // (which answer 404 "Results are not released yet") on the right screen.
  const state =
    resource.data?.result_state ??
    (resource.error && resource.error.toLowerCase().includes("not released")
      ? ("UNDER_EVALUATION" as const)
      : undefined);

  if (state === "NOT_ATTEMPTED") {
    return (
      <div className="mx-auto max-w-2xl">
        <PageHeader title="Exam result" subtitle="Nothing to show for this exam yet." />
        <Card className="py-8 text-center">
          <Clock className="mx-auto h-12 w-12 text-muted-foreground" aria-hidden="true" />
          <h2 className="mt-3 font-display text-xl font-bold text-primary">You haven&apos;t attempted this exam</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            There is no submitted attempt for this exam on your record. If you believe this is a
            mistake, please contact your class teacher.
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Link
              href="/student/examinations"
              className="inline-flex h-11 items-center rounded-field bg-accent px-5 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover"
            >
              Back to examinations
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  if (state === "IN_PROGRESS") {
    return (
      <div className="mx-auto max-w-2xl">
        <PageHeader title="Exam result" subtitle="Your attempt is still open." />
        <Card className="py-8 text-center">
          <Clock className="mx-auto h-12 w-12 text-accent" aria-hidden="true" />
          <h2 className="mt-3 font-display text-xl font-bold text-primary">Your attempt is still in progress</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Results appear here once you submit your paper and your teacher releases them.
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Link
              href={`/student/examinations/${examId}`}
              className="inline-flex h-11 items-center rounded-field bg-accent px-5 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover"
            >
              Continue exam
            </Link>
            <Link
              href="/student/examinations"
              className="inline-flex h-11 items-center rounded-field border border-border px-5 text-sm font-semibold text-muted-foreground hover:border-accent hover:text-accent"
            >
              Back to examinations
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  if (state === "UNDER_EVALUATION") {
    return (
      <div className="mx-auto max-w-2xl">
        <PageHeader title="Exam submitted" subtitle="Your answers have been successfully recorded." />
        <Card className="py-8 text-center">
          <CheckCircle2 className="mx-auto h-12 w-12 text-success-text" />
          <h2 className="mt-3 font-display text-xl font-bold text-primary">Exam Submitted Successfully!</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Your attempt has been submitted and is <strong>under evaluation</strong>. Your teacher
            will release the results soon.
          </p>
          <div className="mx-auto mt-4 max-w-md rounded-field bg-muted/60 p-4 text-xs text-muted-foreground">
            Once results are released by your teacher, your score, grade, and answer review will appear right here.
          </div>
          <div className="mt-6 flex justify-center gap-3">
            <Link
              href="/student/examinations"
              className="inline-flex h-11 items-center rounded-field bg-accent px-5 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover"
            >
              Back to examinations
            </Link>
            <Link
              href="/student/dashboard"
              className="inline-flex h-11 items-center rounded-field border border-border px-5 text-sm font-semibold text-muted-foreground hover:border-accent hover:text-accent"
            >
              Dashboard
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Exam result" subtitle="Your score and, once released, the answer key." />
      <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading your result…">
        {resource.data ? (
          <div className="space-y-5">
            <div className="flex items-end justify-between gap-3">
              <h2 className="font-display text-lg font-bold text-primary">Grade card</h2>
              <button
                type="button"
                onClick={downloadGradeCard}
                disabled={exportBusy}
                className="inline-flex h-9 items-center gap-1.5 rounded-field border border-border px-3 text-xs font-semibold text-primary transition hover:border-accent hover:text-accent disabled:opacity-60"
              >
                <Download className="h-3.5 w-3.5" aria-hidden="true" />
                {exportBusy ? "Preparing…" : "Download grade card"}
              </button>
            </div>
            {exportError ? (
              <p role="alert" className="text-sm text-destructive-text">{exportError}</p>
            ) : null}
            <Card>
              <div ref={gradeCardRef} className="bg-white p-5">
                <h2 className="font-display text-lg font-bold text-primary">{resource.data.title}</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  {resource.data.subject_name} · {statusLabel(resource.data.status)} · submitted {resource.data.submitted_at ? dateTime(resource.data.submitted_at) : "—"}
                </p>
                <div className="mt-4 grid gap-4 sm:grid-cols-3">
                  <div className="rounded-field bg-muted p-4 text-center">
                    <p className="text-2xl font-bold text-primary">{resource.data.total_score ?? "—"}</p>
                    <p className="text-xs text-muted-foreground">of {resource.data.total_marks} marks</p>
                  </div>
                  <div className="rounded-field bg-muted p-4 text-center">
                    <p className="text-2xl font-bold text-primary">{resource.data.percentage !== null ? percent(resource.data.percentage) : "—"}</p>
                    <p className="text-xs text-muted-foreground">percentage</p>
                  </div>
                  <div className="rounded-field bg-muted p-4 text-center">
                    <p className={`text-2xl font-bold ${
                      resource.data.total_score !== null && resource.data.total_score >= resource.data.passing_marks
                        ? "text-success-text"
                        : "text-muted-foreground"
                    }`}>
                      {resource.data.grade ?? (resource.data.total_score !== null
                        ? resource.data.total_score >= resource.data.passing_marks
                          ? "PASS"
                          : "FAIL"
                        : "—")}
                    </p>
                    <p className="text-xs text-muted-foreground">{resource.data.grade ? "grade" : `pass mark ${resource.data.passing_marks}`}</p>
                  </div>
                </div>
              </div>
            </Card>
            {resource.data.answers.length ? (
              <Card>
                <h2 className="font-display text-base font-bold text-primary">Marks breakdown</h2>
                {!resource.data.show_answers ? (
                  <p className="mt-1 text-xs text-muted-foreground">Your teacher has hidden the correct answers for now — only your own answers and scores are shown.</p>
                ) : null}
                <ol className="mt-4 space-y-4">
                  {resource.data.answers.map((answer, index) => (
                    <li key={answer.question_id} className="border-l-2 border-accent pl-3">
                      <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                        Q{index + 1} · {statusLabel(answer.question_type)} · {answer.score ?? "—"}/{answer.marks} marks
                      </p>
                      <p className="mt-1 whitespace-pre-wrap text-sm font-semibold text-primary">{answer.question_text}</p>
                      <p className="mt-1.5 text-sm text-muted-foreground">
                        Your answer: <span className={`font-medium ${
                          answer.score !== null && answer.score === answer.marks
                            ? "text-success-text"
                            : answer.score !== null && answer.score < answer.marks
                              ? "text-destructive-text"
                              : "text-primary"
                        }`}>{answer.selected_option_text ?? answer.text_answer ?? "(unanswered)"}</span>
                      </p>
                      {answer.correct_option_text && (answer.score === null || answer.score < answer.marks) ? (
                        <p className="mt-1 text-sm text-success-text">Correct answer: {answer.correct_option_text}</p>
                      ) : null}
                      {answer.feedback ? <p className="mt-1 text-sm italic text-muted-foreground">Feedback: {answer.feedback}</p> : null}
                    </li>
                  ))}
                </ol>
              </Card>
            ) : null}
          </div>
        ) : null}
      </AsyncState>
    </div>
  );
}
