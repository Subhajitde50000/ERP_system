/**
 * C-TC-14 — edit an assignment, manage milestones, publish / close / reopen.
 */

import { useState } from "react";
import { Alert, Linking, StyleSheet, Text, View } from "react-native";
import { Link, useLocalSearchParams } from "expo-router";
import { Ban, Pencil, Plus, RotateCcw, Send, Trash2 } from "lucide-react-native";

import { AsyncState } from "@/components/principal-ui";
import { Screen } from "@/components/screen";
import { TeacherGroupsSection } from "@/components/teacher-groups";
import { TextField } from "@/components/text-field";
import {
  ActionError,
  MetaRow,
  OutlineButton,
  PrimaryButton,
  WarningBanner,
} from "@/components/teacher-ui";
import { Card, PageHeader } from "@/components/ui";
import { dateTime, parseDatetimeLocal, statusLabel, toDatetimeLocal } from "@/lib/format";
import {
  addAssignmentMilestone,
  closeTeacherAssignment,
  deleteAssignmentMilestone,
  fetchTeacherAssignment,
  publishTeacherAssignment,
  reopenTeacherAssignment,
  updateAssignmentMilestone,
  updateTeacherAssignment,
  type TeacherAssignmentDetail,
  type TeacherMilestoneOut,
} from "@/lib/teacher";
import { useResource } from "@/hooks/use-resource";
import { Colors, Radius } from "@/theme";

export default function TeacherAssignmentDetailPage() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const assignmentId = id ?? "";
  const resource = useResource(
    () =>
      assignmentId
        ? fetchTeacherAssignment(assignmentId)
        : Promise.reject(new Error("No assignment ID provided")),
    [assignmentId],
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const data = resource.data;
  const [edit, setEdit] = useState<{
    title: string;
    description: string;
    due_date: string;
    total_marks: string;
    passing_marks: string;
  } | null>(null);

  async function run(action: string, task: () => Promise<TeacherAssignmentDetail>) {
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

  /* Reopen asks what to do with un-reviewed work already submitted: hand it
     back for revision (default) or only accept new submissions. */
  function confirmReopen() {
    Alert.alert(
      "Reopen assignment",
      "Students can submit again while it stays published. Hand already-submitted (un-reviewed) work back to students for revision?",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "New submissions only",
          onPress: () => run("reopen", () => reopenTeacherAssignment(assignmentId, false)),
        },
        {
          text: "Reopen & resubmit",
          onPress: () => run("reopen", () => reopenTeacherAssignment(assignmentId, true)),
        },
      ],
      { cancelable: true },
    );
  }

  return (
    <Screen>
      <PageHeader
        title={resource.data ? resource.data.title : "Assignment"}
        subtitle="Edit the draft, manage milestones and review submissions."
        action={
          resource.data ? (
            <View style={styles.headerActions}>
              <Link
                href={{ pathname: "/(teacher)/assignments/[id]/submissions", params: { id: assignmentId } }}
                style={styles.linkBtn}
              >
                Submissions ({resource.data.submission_count}/{resource.data.student_count})
              </Link>
              {resource.data.status === "DRAFT" ? (
                <PrimaryButton
                  label={busy === "publish" ? "Publishing…" : "Publish"}
                  icon={Send}
                  disabled={busy !== null}
                  loading={busy === "publish"}
                  onPress={() => run("publish", () => publishTeacherAssignment(assignmentId))}
                />
              ) : null}
              {resource.data.status === "PUBLISHED" ? (
                <OutlineButton
                  label={busy === "close" ? "Closing…" : "Close"}
                  icon={Ban}
                  warning
                  disabled={busy !== null}
                  onPress={() => run("close", () => closeTeacherAssignment(assignmentId))}
                />
              ) : null}
              {resource.data.status === "CLOSED" ? (
                <PrimaryButton
                  label={busy === "reopen" ? "Reopening…" : "Reopen assignment"}
                  icon={RotateCcw}
                  disabled={busy !== null}
                  loading={busy === "reopen"}
                  onPress={confirmReopen}
                />
              ) : null}
            </View>
          ) : undefined
        }
      />
      <ActionError message={actionError} />
      <AsyncState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
        loadingLabel="Loading assignment…"
      >
        {data ? (
          <View style={styles.stack}>
            {data.status === "DRAFT" ? (
              <WarningBanner>
                This assignment is in Draft mode and is not visible to students yet.
              </WarningBanner>
            ) : null}
            <Card>
              <View style={styles.detailsHead}>
                <Text style={styles.cardTitle}>Details</Text>
                {data.status === "DRAFT" ? (
                  <OutlineButton
                    label={edit ? "Cancel edit" : "Edit"}
                    onPress={() =>
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
                  />
                ) : null}
              </View>
              {edit ? (
                <View style={styles.form}>
                  <TextField label="Title" value={edit.title} onChangeText={(title) => setEdit({ ...edit, title })} />
                  <TextField
                    label="Instructions"
                    value={edit.description}
                    onChangeText={(description) => setEdit({ ...edit, description })}
                    multiline
                  />
                  <TextField
                    label="Total marks"
                    value={edit.total_marks}
                    onChangeText={(total_marks) => setEdit({ ...edit, total_marks })}
                    keyboardType="numeric"
                  />
                  <TextField
                    label="Passing marks"
                    value={edit.passing_marks}
                    onChangeText={(passing_marks) => setEdit({ ...edit, passing_marks })}
                    keyboardType="numeric"
                  />
                  <TextField
                    label="Due date"
                    value={edit.due_date}
                    onChangeText={(due_date) => setEdit({ ...edit, due_date })}
                    placeholder="YYYY-MM-DDTHH:MM"
                  />
                  <PrimaryButton
                    label={busy === "save" ? "Saving…" : "Save changes"}
                    loading={busy === "save"}
                    onPress={() => {
                      const due = parseDatetimeLocal(edit.due_date);
                      if (!due) return;
                      run("save", () =>
                        updateTeacherAssignment(assignmentId, {
                          title: edit.title.trim(),
                          description: edit.description.trim(),
                          due_date: due,
                          total_marks: Number(edit.total_marks),
                          passing_marks: Number(edit.passing_marks),
                        }),
                      ).then(() => setEdit(null));
                    }}
                  />
                </View>
              ) : (
                <View style={styles.meta}>
                  <MetaRow label="Class" value={`${data.class_name} · ${data.subject_code} ${data.subject_name}`} />
                  <MetaRow label="Type" value={statusLabel(data.assignment_type)} />
                  <MetaRow label="Marks" value={`${data.total_marks} total · pass ${data.passing_marks}`} />
                  <MetaRow label="Due" value={dateTime(data.due_date)} />
                  {data.assignment_type === "GROUP" ? (
                    <MetaRow label="Group size" value={`${data.min_group_size} to ${data.max_group_size} students`} />
                  ) : null}
                  <MetaRow
                    label="Late submissions"
                    value={data.allow_late_submission ? `Allowed (−${data.late_penalty_percent}%)` : "Not allowed"}
                  />
                  <MetaRow
                    label="File policy"
                    value={`${data.allowed_file_types.map((ext) => `.${ext}`).join(" ")} · up to ${data.max_file_size_mb} MB`}
                  />
                  <MetaRow label="Status" value={statusLabel(data.status)} />
                  <MetaRow label="Created" value={dateTime(data.created_at)} />
                </View>
              )}
              {!edit && data.description ? <Text style={styles.description}>{data.description}</Text> : null}
              {!edit && data.instructions_url ? (
                <Text style={styles.link} onPress={() => Linking.openURL(data.instructions_url!)}>
                  Reference link
                </Text>
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
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}

function MilestonesCard({
  assignmentId,
  milestones,
  editable,
  onChanged,
}: {
  assignmentId: string;
  milestones: TeacherMilestoneOut[];
  editable: boolean;
  onChanged: (detail: TeacherAssignmentDetail) => void;
}) {
  const [form, setForm] = useState({ title: "", description: "", marks: "10", due_date: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ title: "", description: "", marks: "10", due_date: "" });

  async function add() {
    setBusy(true);
    setError(null);
    try {
      const detail = await addAssignmentMilestone(assignmentId, {
        title: form.title.trim(),
        description: form.description.trim() || null,
        marks: Number(form.marks),
        due_date: parseDatetimeLocal(form.due_date),
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

  function startEditing(milestone: TeacherMilestoneOut) {
    setEditingId(milestone.id);
    setEditForm({
      title: milestone.title,
      description: milestone.description ?? "",
      marks: String(milestone.marks),
      due_date: toDatetimeLocal(milestone.due_date),
    });
  }

  async function saveEdit() {
    if (!editingId) return;
    setBusy(true);
    setError(null);
    try {
      const detail = await updateAssignmentMilestone(assignmentId, editingId, {
        title: editForm.title.trim(),
        description: editForm.description.trim() || null,
        marks: Number(editForm.marks),
        due_date: parseDatetimeLocal(editForm.due_date),
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
      <View style={styles.msHead}>
        <View>
          <Text style={styles.cardTitle}>Milestones</Text>
          <Text style={styles.msSub}>Stages unlock in order; students submit against each stage.</Text>
        </View>
        {milestones.length ? (
          <Text style={styles.stageCount}>{milestones.length} stages</Text>
        ) : null}
      </View>
      {milestones.length ? (
        <View>
          {milestones.map((milestone, idx) => {
            const isEditing = editingId === milestone.id;
            return (
              <View key={milestone.id} style={styles.stageRow}>
                <View style={styles.stageNum}>
                  <Text style={styles.stageNumText}>{idx + 1}</Text>
                </View>
                <View style={styles.stageBody}>
                  {isEditing ? (
                    <View style={styles.form}>
                      <Text style={styles.editStage}>Edit Stage {idx + 1}</Text>
                      <TextField
                        label="Stage title"
                        value={editForm.title}
                        onChangeText={(title) => setEditForm({ ...editForm, title })}
                      />
                      <TextField
                        label="Marks"
                        value={editForm.marks}
                        onChangeText={(marks) => setEditForm({ ...editForm, marks })}
                        keyboardType="numeric"
                      />
                      <TextField
                        label="Due date (optional)"
                        value={editForm.due_date}
                        onChangeText={(due_date) => setEditForm({ ...editForm, due_date })}
                        placeholder="YYYY-MM-DDTHH:MM"
                      />
                      <TextField
                        label="Description (optional)"
                        value={editForm.description}
                        onChangeText={(description) => setEditForm({ ...editForm, description })}
                      />
                      <View style={styles.stageActions}>
                        <PrimaryButton label="Save stage" disabled={busy} onPress={saveEdit} />
                        <OutlineButton label="Cancel" onPress={() => setEditingId(null)} />
                      </View>
                    </View>
                  ) : (
                    <View style={styles.stageCard}>
                      <View style={styles.stageText}>
                        <Text style={styles.stageTitle}>
                          {milestone.title}{" "}
                          <Text style={styles.stageMarks}>{milestone.marks} marks</Text>
                        </Text>
                        {milestone.description ? <Text style={styles.stageDesc}>{milestone.description}</Text> : null}
                        {milestone.due_date ? (
                          <Text style={styles.stageDue}>Due {dateTime(milestone.due_date)}</Text>
                        ) : null}
                      </View>
                      {editable ? (
                        <View style={styles.stageActions}>
                          <OutlineButton label="" icon={Pencil} disabled={busy} onPress={() => startEditing(milestone)} />
                          <OutlineButton label="" icon={Trash2} danger disabled={busy} onPress={() => remove(milestone.id)} />
                        </View>
                      ) : null}
                    </View>
                  )}
                </View>
              </View>
            );
          })}
        </View>
      ) : (
        <View style={styles.noStages}>
          <Text style={styles.noStagesText}>
            No milestones yet — add stages below, or leave empty for a single-submission assignment.
          </Text>
        </View>
      )}
      {editable ? (
        <View style={styles.addStage}>
          <Text style={styles.addStageLabel}>Add next stage</Text>
          <TextField
            label="Milestone title"
            value={form.title}
            onChangeText={(title) => setForm({ ...form, title })}
          />
          <TextField
            label="Marks"
            value={form.marks}
            onChangeText={(marks) => setForm({ ...form, marks })}
            keyboardType="numeric"
          />
          <TextField
            label="Due date (optional)"
            value={form.due_date}
            onChangeText={(due_date) => setForm({ ...form, due_date })}
            placeholder="YYYY-MM-DDTHH:MM"
          />
          <TextField
            label="Description (optional)"
            value={form.description}
            onChangeText={(description) => setForm({ ...form, description })}
          />
          <ActionError message={error} />
          <OutlineButton label={busy ? "Adding…" : "Add stage"} icon={Plus} disabled={busy} onPress={add} />
        </View>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  headerActions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  linkBtn: {
    height: 40,
    borderRadius: Radius.field,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 14,
    fontWeight: "600",
    color: Colors.primary,
    overflow: "hidden",
  },
  stack: {
    gap: 20,
  },
  detailsHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    marginBottom: 12,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: "700",
    color: Colors.primary,
  },
  form: {
    gap: 16,
  },
  meta: {
    gap: 4,
  },
  description: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    fontSize: 14,
    lineHeight: 20,
    color: Colors.mutedForeground,
  },
  link: {
    marginTop: 8,
    fontSize: 14,
    fontWeight: "600",
    color: Colors.accent,
  },
  msHead: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
    marginBottom: 16,
  },
  msSub: {
    marginTop: 2,
    fontSize: 12,
    color: Colors.mutedForeground,
  },
  stageCount: {
    borderRadius: 999,
    backgroundColor: Colors.muted,
    overflow: "hidden",
    paddingHorizontal: 10,
    paddingVertical: 4,
    fontSize: 12,
    fontWeight: "600",
    color: Colors.mutedForeground,
  },
  stageRow: {
    flexDirection: "row",
    gap: 12,
    marginBottom: 12,
  },
  stageNum: {
    width: 32,
    height: 32,
    borderRadius: 16,
    borderWidth: 2,
    borderColor: Colors.accent,
    backgroundColor: Colors.accentLight,
    alignItems: "center",
    justifyContent: "center",
  },
  stageNumText: {
    fontSize: 12,
    fontWeight: "700",
    color: Colors.accent,
  },
  stageBody: {
    flex: 1,
  },
  stageCard: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 8,
    borderRadius: Radius.field,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: 12,
  },
  stageText: {
    flex: 1,
  },
  stageTitle: {
    fontSize: 14,
    fontWeight: "600",
    color: Colors.primary,
  },
  stageMarks: {
    fontSize: 10,
    fontWeight: "700",
    color: Colors.mutedForeground,
  },
  stageDesc: {
    marginTop: 4,
    fontSize: 12,
    color: Colors.mutedForeground,
  },
  stageDue: {
    marginTop: 4,
    fontSize: 11,
    color: Colors.mutedForeground,
  },
  stageActions: {
    flexDirection: "row",
    gap: 6,
  },
  editStage: {
    fontSize: 12,
    fontWeight: "700",
    color: Colors.accent,
  },
  noStages: {
    borderRadius: Radius.field,
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: Colors.border,
    padding: 16,
  },
  noStagesText: {
    fontSize: 14,
    textAlign: "center",
    color: Colors.mutedForeground,
  },
  addStage: {
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    gap: 12,
  },
  addStageLabel: {
    fontSize: 12,
    fontWeight: "600",
    color: Colors.mutedForeground,
  },
});
