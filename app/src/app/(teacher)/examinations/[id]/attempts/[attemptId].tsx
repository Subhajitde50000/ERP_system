/**
 * Grade one exam attempt. Dedicated screen (not a modal overlay) so every
 * question stem, student answer and score field is fully visible.
 */

import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

import { AsyncState } from "@/components/principal-ui";
import { Screen } from "@/components/screen";
import { TextField } from "@/components/text-field";
import { ActionError, OutlineButton, PrimaryButton } from "@/components/teacher-ui";
import { Card, PageHeader } from "@/components/ui";
import { dateTime, statusLabel } from "@/lib/format";
import {
  fetchExamAttempt,
  gradeExamAttempt,
  type TeacherAnswerOption,
  type TeacherAnswerRow,
  type TeacherAttemptDetail,
} from "@/lib/teacher";
import { useResource } from "@/hooks/use-resource";
import { Colors, Radius } from "@/theme";

export default function TeacherGradeAttemptPage() {
  const { id, attemptId } = useLocalSearchParams<{ id: string; attemptId: string }>();
  const examId = id ?? "";
  const aid = attemptId ?? "";
  const detail = useResource(
    () =>
      examId && aid
        ? fetchExamAttempt(examId, aid)
        : Promise.reject(new Error("Exam and attempt IDs are required")),
    [examId, aid],
  );

  return (
    <Screen>
      <PageHeader
        title="Grade attempt"
        subtitle="Objective answers are auto-graded; set scores for the rest. Every question is shown in full."
      />
      <AsyncState
        loading={detail.loading}
        error={detail.error}
        onRetry={detail.reload}
        loadingLabel="Loading answers…"
      >
        {detail.data ? <GradingForm examId={examId} detail={detail.data} /> : null}
      </AsyncState>
    </Screen>
  );
}

function GradingForm({ examId, detail }: { examId: string; detail: TeacherAttemptDetail }) {
  const router = useRouter();
  const manual = detail.answers.filter((answer) => !answer.is_auto_graded);
  const [scores, setScores] = useState<Record<string, string>>(
    Object.fromEntries(manual.map((answer) => [answer.answer_id, answer.score !== null ? String(answer.score) : ""])),
  );
  const [feedback, setFeedback] = useState<Record<string, string>>(
    Object.fromEntries(manual.map((answer) => [answer.answer_id, answer.feedback ?? ""])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    const grades = [];
    for (const answer of manual) {
      const raw = (scores[answer.answer_id] ?? "").trim();
      if (raw === "") {
        setError(`Enter a score for every pending answer (Q: “${answer.question_text.slice(0, 40)}…”).`);
        return;
      }
      const score = Number(raw);
      if (Number.isNaN(score) || score < 0 || score > answer.marks) {
        setError(`Score must be between 0 and ${answer.marks}.`);
        return;
      }
      grades.push({
        answer_id: answer.answer_id,
        score,
        feedback: (feedback[answer.answer_id] ?? "").trim() || null,
      });
    }
    if (!grades.length) {
      router.back();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await gradeExamAttempt(examId, detail.attempt_id, grades);
      router.back();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save the grades.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.stack}>
      <Text style={styles.student}>
        <Text style={styles.studentName}>{detail.student_name}</Text>
        {detail.roll_number ? ` · ${detail.roll_number}` : ""} · submitted{" "}
        {detail.submitted_at ? dateTime(detail.submitted_at) : "—"}
        {detail.tab_switch_count
          ? ` · left the exam ${detail.tab_switch_count} time${detail.tab_switch_count === 1 ? "" : "s"}`
          : ""}
      </Text>
      {detail.answers.some((answer) => answer.is_auto_graded) ? (
        <AutoGradedSummary answers={detail.answers} />
      ) : null}
      {manual.length ? (
        manual.map((answer) => (
          <Card key={answer.answer_id}>
            <Text style={styles.qMeta}>
              {statusLabel(answer.question_type)} · {answer.marks} marks
            </Text>
            <Text style={styles.qText}>{answer.question_text || "(question text unavailable)"}</Text>
            {answer.text_answer?.trim() ? (
              <View style={styles.answerBox}>
                <Text style={styles.answerText}>{answer.text_answer}</Text>
              </View>
            ) : answer.selected_option_text ? (
              <View style={styles.answerBox}>
                <Text style={styles.answerText}>
                  Student picked: <Text style={styles.answerPick}>{answer.selected_option_text}</Text>
                </Text>
              </View>
            ) : answer.matched_pairs && Object.keys(answer.matched_pairs).length ? (
              <View style={styles.answerBox}>
                {Object.entries(answer.matched_pairs).map(([left, right]) => (
                  <Text key={left} style={styles.answerText}>
                    {left} → {right}
                  </Text>
                ))}
              </View>
            ) : (
              <View style={styles.answerBox}>
                <Text style={styles.answerMuted}>(no answer written)</Text>
              </View>
            )}
            <AnswerKeyOptions answer={answer} />
            <View style={styles.gradeFields}>
              <TextField
                label={`Score (0–${answer.marks})`}
                value={scores[answer.answer_id] ?? ""}
                onChangeText={(value) => setScores({ ...scores, [answer.answer_id]: value })}
                keyboardType="numeric"
              />
              <TextField
                label="Feedback (optional)"
                value={feedback[answer.answer_id] ?? ""}
                onChangeText={(value) => setFeedback({ ...feedback, [answer.answer_id]: value })}
              />
            </View>
          </Card>
        ))
      ) : (
        <View style={styles.autoDone}>
          <Text style={styles.autoDoneText}>Every answer is auto-graded — nothing is waiting on you.</Text>
        </View>
      )}
      <ActionError message={error} />
      {manual.length ? (
        <View style={styles.actions}>
          <PrimaryButton label={busy ? "Saving…" : "Save grades"} loading={busy} onPress={submit} />
          <OutlineButton label="Cancel" onPress={() => router.back()} />
        </View>
      ) : (
        <OutlineButton label="Back to results" onPress={() => router.back()} />
      )}
    </View>
  );
}

function AutoGradedSummary({ answers }: { answers: TeacherAnswerRow[] }) {
  const auto = answers.filter((answer) => answer.is_auto_graded);
  const earned = auto.reduce((sum, answer) => sum + (answer.score ?? 0), 0);
  const possible = auto.reduce((sum, answer) => sum + answer.marks, 0);
  return (
    <View style={styles.autoSummary}>
      <Text style={styles.autoSummaryText}>
        Auto-graded objective answers: {earned} / {possible} marks across {auto.length} question(s).
      </Text>
      {auto.map((answer) => {
        const unanswered = !answer.selected_option_id;
        const correct = Boolean(
          answer.selected_option_id && answer.correct_option_text === answer.selected_option_text,
        );
        return (
          <View key={answer.answer_id} style={styles.autoRow}>
            <Text style={styles.autoQ}>{answer.question_text || "(question text unavailable)"}</Text>
            <Text
              style={[
                styles.autoVerdict,
                unanswered
                  ? { color: Colors.mutedForeground }
                  : correct
                    ? { color: Colors.successText }
                    : { color: Colors.destructiveText },
              ]}
            >
              {unanswered ? "NOT ANSWERED" : correct ? "CORRECT" : "WRONG"}
              {` · ${answer.score ?? 0}/${answer.marks}`}
            </Text>
            <AnswerKeyOptions answer={answer} />
          </View>
        );
      })}
    </View>
  );
}

/**
 * The full answer key for one question: every option in authoring order with
 * the correct one and the student's pick flagged. Plain-text badges (no symbol
 * glyphs) so the screen stays readable in every font.
 */
function AnswerKeyOptions({ answer }: { answer: TeacherAnswerRow }) {
  const options: TeacherAnswerOption[] = [...answer.options].sort((a, b) => a.sort_order - b.sort_order);
  if (!options.length) return null;
  return (
    <View style={styles.keyList}>
      {options.map((option) => {
        const isPicked = option.id === answer.selected_option_id;
        return (
          <View
            key={option.id}
            style={[styles.keyRow, isPicked ? styles.keyRowPicked : null]}
          >
            <Text style={styles.keyText}>{option.text}</Text>
            {option.is_correct ? <Text style={[styles.keyBadge, { color: Colors.successText }]}>CORRECT</Text> : null}
            {isPicked ? (
              <Text
                style={[
                  styles.keyBadge,
                  { color: option.is_correct ? Colors.successText : Colors.destructiveText },
                ]}
              >
                STUDENT&apos;S PICK
              </Text>
            ) : null}
          </View>
        );
      })}
      {!answer.selected_option_id && !answer.options.length ? null : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: {
    gap: 16,
  },
  student: {
    fontSize: 14,
    color: Colors.mutedForeground,
  },
  studentName: {
    fontWeight: "600",
    color: Colors.primary,
  },
  qMeta: {
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.4,
    color: Colors.mutedForeground,
  },
  qText: {
    marginTop: 8,
    fontSize: 15,
    fontWeight: "600",
    lineHeight: 22,
    color: Colors.primary,
  },
  answerBox: {
    marginTop: 12,
    borderRadius: Radius.field,
    backgroundColor: Colors.muted,
    padding: 12,
  },
  answerText: {
    fontSize: 14,
    lineHeight: 20,
    color: Colors.mutedForeground,
  },
  gradeFields: {
    marginTop: 12,
    gap: 12,
  },
  autoDone: {
    borderRadius: Radius.field,
    borderWidth: 1,
    borderColor: Colors.successBorder,
    backgroundColor: Colors.successLight,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  autoDoneText: {
    fontSize: 14,
    color: Colors.successText,
  },
  autoSummary: {
    borderRadius: Radius.field,
    backgroundColor: Colors.muted,
    padding: 16,
    gap: 10,
  },
  autoSummaryText: {
    fontSize: 12,
    fontWeight: "600",
    color: Colors.mutedForeground,
  },
  autoVerdict: {
    marginTop: 2,
    fontSize: 11,
    fontWeight: "700",
  },
  keyList: {
    marginTop: 6,
    gap: 6,
  },
  keyRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.field,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  keyRowPicked: {
    borderColor: Colors.accent,
    backgroundColor: Colors.accentLight,
  },
  keyText: {
    flex: 1,
    minWidth: 120,
    fontSize: 13,
    color: Colors.primary,
  },
  keyBadge: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.3,
  },
  answerPick: {
    fontWeight: "600",
    color: Colors.primary,
  },
  answerMuted: {
    fontSize: 14,
    lineHeight: 20,
    fontStyle: "italic",
    color: Colors.mutedForeground,
  },
  autoRow: {
    gap: 2,
  },
  autoQ: {
    fontSize: 13,
    fontWeight: "600",
    color: Colors.primary,
  },
  autoA: {
    fontSize: 12,
    color: Colors.mutedForeground,
  },
  actions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
  },
});
