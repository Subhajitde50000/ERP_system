/**
 * C-ST-09 exam result — port of StudentExamResultPage in
 * fontend/components/student/student-examinations.tsx: score, grade and
 * answer-key review for a released result.
 */

import { Share, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Link, useLocalSearchParams } from "expo-router";
import { CircleCheck, Clock } from "lucide-react-native";

import { AsyncState } from "@/components/principal-ui";
import { Screen } from "@/components/screen";
import { Card, PageHeader } from "@/components/ui";
import { dateTime, percent, statusLabel } from "@/lib/format";
import { fetchExamResult, gradeCardText } from "@/lib/student";
import { useResource } from "@/hooks/use-resource";
import { Colors, Radius, Shadow } from "@/theme";

export default function StudentExamResultPage() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const examId = id ?? "";
  const resource = useResource(
    () => (examId ? fetchExamResult(examId) : Promise.reject(new Error("No exam ID provided"))),
    [examId],
  );

  // Typed lifecycle from the API; the string fallback keeps older backends
  // (which answer 404 "Results are not released yet") on the right screen.
  const state =
    resource.data?.result_state ??
    (resource.error && resource.error.toLowerCase().includes("not released")
      ? ("UNDER_EVALUATION" as const)
      : undefined);

  if (state === "NOT_ATTEMPTED") {
    return (
      <Screen>
        <PageHeader title="Exam result" subtitle="Nothing to show for this exam yet." />
        <Card style={styles.pendingCard}>
          <Clock size={48} color={Colors.mutedForeground} />
          <Text style={styles.pendingTitle}>You haven&apos;t attempted this exam</Text>
          <Text style={styles.pendingBody}>
            There is no submitted attempt for this exam on your record. If you believe this is a mistake, please contact your class teacher.
          </Text>
          <View style={styles.pendingActions}>
            <Link href="/(student)/examinations" style={styles.pendingPrimary}>
              Back to examinations
            </Link>
          </View>
        </Card>
      </Screen>
    );
  }

  if (state === "IN_PROGRESS") {
    return (
      <Screen>
        <PageHeader title="Exam result" subtitle="Your attempt is still open." />
        <Card style={styles.pendingCard}>
          <Clock size={48} color={Colors.accent} />
          <Text style={styles.pendingTitle}>Your attempt is still in progress</Text>
          <Text style={styles.pendingBody}>
            Results appear here once you submit your paper and your teacher releases them.
          </Text>
          <View style={styles.pendingActions}>
            <Link href={{ pathname: "/(student)/examinations/[id]", params: { id: examId } }} style={styles.pendingPrimary}>
              Continue exam
            </Link>
            <Link href="/(student)/examinations" style={styles.pendingSecondary}>
              Back
            </Link>
          </View>
        </Card>
      </Screen>
    );
  }

  if (state === "UNDER_EVALUATION") {
    return (
      <Screen>
        <PageHeader title="Exam submitted" subtitle="Your answers have been successfully recorded." />
        <Card style={styles.pendingCard}>
          <CircleCheck size={48} color={Colors.successText} />
          <Text style={styles.pendingTitle}>Exam Submitted Successfully!</Text>
          <Text style={styles.pendingBody}>
            Your attempt has been submitted and is under evaluation. Your teacher will release the results soon.
          </Text>
          <View style={styles.pendingNote}>
            <Text style={styles.pendingNoteText}>
              Once results are released by your teacher, your score, grade, and answer review will appear right here.
            </Text>
          </View>
          <View style={styles.pendingActions}>
            <Link href="/(student)/examinations" style={styles.pendingPrimary}>
              Back to examinations
            </Link>
            <Link href="/(student)/dashboard" style={styles.pendingSecondary}>
              Dashboard
            </Link>
          </View>
        </Card>
      </Screen>
    );
  }

  return (
    <Screen>
      <PageHeader title="Exam result" subtitle="Your score, grade card and marks breakdown." />
      <AsyncState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
        loadingLabel="Loading your result…"
      >
        {resource.data ? (
          <View style={styles.stack}>
            <Card>
              <Text style={styles.title}>{resource.data.title}</Text>
              <Text style={styles.meta}>
                {resource.data.subject_name} · {statusLabel(resource.data.status)} · submitted{" "}
                {resource.data.submitted_at ? dateTime(resource.data.submitted_at) : "—"}
              </Text>
              <TouchableOpacity
                style={styles.shareButton}
                onPress={() =>
                  Share.share({ message: gradeCardText(resource.data!) }).catch(() => {
                    /* user cancelled the share sheet — nothing to do */
                  })
                }
              >
                <Text style={styles.shareText}>Share result</Text>
              </TouchableOpacity>
              <View style={styles.scoreRow}>
                <View style={styles.scoreBox}>
                  <Text style={styles.scoreValue}>{resource.data.total_score ?? "—"}</Text>
                  <Text style={styles.scoreLabel}>of {resource.data.total_marks} marks</Text>
                </View>
                <View style={styles.scoreBox}>
                  <Text style={styles.scoreValue}>
                    {resource.data.percentage !== null ? percent(resource.data.percentage) : "—"}
                  </Text>
                  <Text style={styles.scoreLabel}>percentage</Text>
                </View>
                <View style={styles.scoreBox}>
                  <Text
                    style={[
                      styles.scoreValue,
                      resource.data.total_score !== null && resource.data.total_score >= resource.data.passing_marks
                        ? { color: Colors.successText }
                        : { color: Colors.mutedForeground },
                    ]}
                  >
                    {resource.data.grade ??
                      (resource.data.total_score !== null
                        ? resource.data.total_score >= resource.data.passing_marks
                          ? "PASS"
                          : "FAIL"
                        : "—")}
                  </Text>
                  <Text style={styles.scoreLabel}>
                    {resource.data.grade ? "grade" : `pass mark ${resource.data.passing_marks}`}
                  </Text>
                </View>
              </View>
            </Card>
            {resource.data.answers.length ? (
              <Card>
                <Text style={styles.reviewTitle}>Marks breakdown</Text>
                {!resource.data.show_answers ? (
                  <Text style={styles.reviewNote}>
                    Your teacher has hidden the correct answers for now — only your own answers and scores are shown.
                  </Text>
                ) : null}
                <View style={styles.answers}>
                  {resource.data.answers.map((answer, index) => (
                    <View key={answer.question_id} style={styles.answer}>
                      <Text style={styles.answerMeta}>
                        Q{index + 1} · {statusLabel(answer.question_type)} · {answer.score ?? "—"}/{answer.marks} marks
                      </Text>
                      <Text style={styles.answerQuestion}>{answer.question_text}</Text>
                      <Text style={styles.answerLine}>
                        Your answer:{" "}
                        <Text style={styles.answerValue}>
                          {answer.selected_option_text ?? answer.text_answer ?? "(unanswered)"}
                        </Text>
                      </Text>
                      {answer.correct_option_text ? (
                        <Text style={styles.correctAnswer}>Correct answer: {answer.correct_option_text}</Text>
                      ) : null}
                      {answer.feedback ? <Text style={styles.feedback}>Feedback: {answer.feedback}</Text> : null}
                    </View>
                  ))}
                </View>
              </Card>
            ) : null}
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}

const styles = StyleSheet.create({
  stack: {
    gap: 20,
  },
  pendingCard: {
    paddingVertical: 32,
    alignItems: "center",
  },
  pendingTitle: {
    marginTop: 12,
    fontSize: 20,
    fontWeight: "700",
    color: Colors.primary,
    textAlign: "center",
  },
  pendingBody: {
    marginTop: 8,
    fontSize: 14,
    lineHeight: 20,
    color: Colors.mutedForeground,
    textAlign: "center",
  },
  pendingNote: {
    marginTop: 16,
    maxWidth: 448,
    borderRadius: Radius.field,
    backgroundColor: "rgba(241,245,249,0.6)",
    padding: 16,
  },
  pendingNoteText: {
    fontSize: 12,
    color: Colors.mutedForeground,
    textAlign: "center",
  },
  pendingActions: {
    marginTop: 24,
    flexDirection: "row",
    justifyContent: "center",
    gap: 12,
  },
  pendingPrimary: {
    height: 44,
    lineHeight: 44,
    borderRadius: Radius.field,
    backgroundColor: Colors.accent,
    paddingHorizontal: 20,
    fontSize: 14,
    fontWeight: "600",
    color: "#FFFFFF",
    overflow: "hidden",
    ...Shadow.accent,
  },
  pendingSecondary: {
    height: 44,
    lineHeight: 42,
    borderRadius: Radius.field,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: 20,
    fontSize: 14,
    fontWeight: "600",
    color: Colors.mutedForeground,
    overflow: "hidden",
    textAlign: "center",
  },
  shareButton: {
    alignSelf: "flex-start",
    marginTop: 12,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.field,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  shareText: {
    fontSize: 12,
    fontWeight: "700",
    color: Colors.accent,
  },
  title: {
    fontSize: 18,
    fontWeight: "700",
    color: Colors.primary,
  },
  meta: {
    marginTop: 4,
    fontSize: 12,
    color: Colors.mutedForeground,
  },
  scoreRow: {
    marginTop: 16,
    gap: 16,
  },
  scoreBox: {
    borderRadius: Radius.field,
    backgroundColor: Colors.muted,
    padding: 16,
    alignItems: "center",
  },
  scoreValue: {
    fontSize: 24,
    fontWeight: "700",
    color: Colors.primary,
  },
  scoreLabel: {
    fontSize: 12,
    color: Colors.mutedForeground,
  },
  reviewTitle: {
    fontSize: 16,
    fontWeight: "700",
    color: Colors.primary,
  },
  reviewNote: {
    marginTop: 4,
    fontSize: 12,
    color: Colors.mutedForeground,
  },
  answers: {
    marginTop: 16,
    gap: 16,
  },
  answer: {
    borderLeftWidth: 2,
    borderLeftColor: Colors.accent,
    paddingLeft: 12,
  },
  answerMeta: {
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.4,
    color: Colors.mutedForeground,
  },
  answerQuestion: {
    marginTop: 4,
    fontSize: 14,
    fontWeight: "600",
    lineHeight: 20,
    color: Colors.primary,
  },
  answerLine: {
    marginTop: 6,
    fontSize: 14,
    color: Colors.mutedForeground,
  },
  answerValue: {
    fontWeight: "500",
    color: Colors.primary,
  },
  correctAnswer: {
    marginTop: 4,
    fontSize: 14,
    color: Colors.successText,
  },
  feedback: {
    marginTop: 4,
    fontSize: 14,
    fontStyle: "italic",
    color: Colors.mutedForeground,
  },
});
