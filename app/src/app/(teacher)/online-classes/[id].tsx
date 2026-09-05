/**
 * Teacher class detail — start/end controls, waiting-room admission, live
 * chat and the automatic attendance report. Media runs in the web console.
 */

import { useEffect, useState } from "react";
import { Linking, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { CheckCircle2, Send } from "lucide-react-native";
import * as WebBrowser from "expo-web-browser";

import { AsyncState } from "@/components/principal-ui";
import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Card, EmptyState, PageHeader } from "@/components/ui";
import { useLiveChat } from "@/hooks/use-live-chat";
import { useResource } from "@/hooks/use-resource";
import { dateTime } from "@/lib/format";
import {
  admitAllStudents,
  admitStudent,
  cancelOnlineClass,
  endOnlineClass,
  fetchAttendanceReport,
  fetchOnlineClassDetail,
  resolveClassWebUrl,
  startOnlineClass,
} from "@/lib/online-class";
import { Colors, Radius } from "@/theme";

export default function TeacherOnlineClassDetailPage() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const detail = useResource(() => fetchOnlineClassDetail(id), [id]);
  const [error, setError] = useState<string | null>(null);

  const live = detail.data?.status === "LIVE";
  const chat = useLiveChat(id, live, detail.reload);

  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => detail.reload(), 8000);
    return () => clearInterval(timer);
  }, [live, detail]);

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      await detail.reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong.");
    }
  }

  const waiting = detail.data?.participants.filter((p) => !p.joined_at) ?? [];
  const inClass = detail.data?.participants.filter((p) => p.joined_at) ?? [];

  return (
    <Screen>
      <AsyncState loading={detail.loading} error={detail.error} onRetry={detail.reload} loadingLabel="Loading class…">
        {detail.data ? (
          <>
            <PageHeader
              title={`${detail.data.subject_code} · ${detail.data.topic}`}
              subtitle={`${detail.data.class_name} · ${detail.data.status}${detail.data.started_at ? ` · started ${dateTime(detail.data.started_at)}` : ""}`}
            />
            {error ? <Text style={styles.error}>{error}</Text> : null}

            {detail.data.status === "SCHEDULED" ? (
              <Card style={styles.stack}>
                <Text style={styles.meta}>Scheduled for {detail.data.scheduled_at ? dateTime(detail.data.scheduled_at) : "—"} · {detail.data.duration_minutes} min.</Text>
                <Button onPress={() => act(() => startOnlineClass(id))}>Start class now</Button>
                <Button variant="secondary" onPress={() => act(() => cancelOnlineClass(id))}>Cancel class</Button>
              </Card>
            ) : null}

            {live ? (
              <>
                <Card style={styles.stack}>
                  <View style={styles.rowBetween}>
                    <Text style={styles.sectionTitle}>Waiting room ({waiting.length})</Text>
                    {waiting.length > 0 ? (
                      <TouchableOpacity onPress={() => act(() => admitAllStudents(id).then(detail.setData))}>
                        <Text style={styles.link}>Admit all</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                  {waiting.length === 0 ? <Text style={styles.meta}>No one waiting.</Text> : null}
                  {waiting.map((p) => (
                    <View key={p.student_id} style={styles.rowBetween}>
                      <Text style={styles.name}>{p.student_name}</Text>
                      <View style={styles.row}>
                        <TouchableOpacity style={styles.admitButton} onPress={() => act(() => admitStudent(id, p.student_id).then(detail.setData))}>
                          <CheckCircle2 size={16} color="#FFFFFF" />
                          <Text style={styles.admitText}>Admit</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  ))}
                </Card>

                <Card style={styles.stack}>
                  <Text style={styles.sectionTitle}>In class ({inClass.filter((p) => p.is_online).length}/{detail.data?.roster_size ?? 0})</Text>
                  {inClass.length === 0 ? <Text style={styles.meta}>No one admitted yet.</Text> : null}
                  {inClass.map((p) => (
                    <View key={p.student_id} style={styles.rowBetween}>
                      <Text style={styles.name}>
                        {p.is_online ? "🟢" : "⚪"} {p.student_name}
                      </Text>
                      {chat.raisedHands.includes(p.student_id) ? <Text style={styles.hand}>✋</Text> : null}
                    </View>
                  ))}
                </Card>

                <ChatBlock messages={chat.messages} connected={chat.connected} onSend={chat.sendMessage} />

                <Button
                  onPress={async () => {
                    const url = resolveClassWebUrl(id, "teacher");
                    try {
                      await WebBrowser.openBrowserAsync(url);
                    } catch {
                      await Linking.openURL(url);
                    }
                  }}
                >
                  Launch Live Classroom (Video & Screen Share)
                </Button>

                <Button
                  loading={false}
                  onPress={async () => {
                    try {
                      await endOnlineClass(id);
                      await detail.reload();
                    } catch (caught) {
                      setError(caught instanceof Error ? caught.message : "Could not end the class.");
                    }
                  }}
                  style={styles.endButton}
                >
                  End class & generate attendance
                </Button>
                <Text style={styles.note}>Video, screen share and whiteboard run in the web console; attendance and chat work here.</Text>
              </>
            ) : null}

            {detail.data.status === "COMPLETED" ? <AttendanceBlock classId={id} /> : null}
            {detail.data.status === "CANCELLED" ? <EmptyState text="This class was cancelled." /> : null}
          </>
        ) : null}
      </AsyncState>
    </Screen>
  );
}

function AttendanceBlock({ classId }: { classId: string }) {
  const report = useResource(() => fetchAttendanceReport(classId), [classId]);
  return (
    <AsyncState loading={report.loading} error={report.error} onRetry={report.reload} loadingLabel="Loading attendance…">
      {report.data ? (
        <Card style={styles.stack}>
          <Text style={styles.sectionTitle}>Attendance report</Text>
          <Text style={styles.meta}>
            {report.data.totals_present} present · {report.data.totals_late} late · {report.data.totals_absent} absent ·{" "}
            {Math.round(report.data.duration_seconds / 60)} min live
          </Text>
          <ScrollView horizontal>
            <View>
              <View style={styles.tableRow}>
                <Text style={[styles.tableCell, styles.tableHead, styles.nameCol]}>Student</Text>
                <Text style={[styles.tableCell, styles.tableHead]}>Duration</Text>
                <Text style={[styles.tableCell, styles.tableHead]}>%</Text>
                <Text style={[styles.tableCell, styles.tableHead]}>Status</Text>
              </View>
              {report.data.rows.map((row) => (
                <View key={row.student_id} style={styles.tableRow}>
                  <Text style={[styles.tableCell, styles.nameCol]} numberOfLines={1}>{row.student_name}</Text>
                  <Text style={styles.tableCell}>{Math.round(row.duration_seconds / 60)}m</Text>
                  <Text style={styles.tableCell}>{row.percent ?? 0}%</Text>
                  <Text style={[styles.tableCell, row.attendance_status === "PRESENT" ? styles.present : row.attendance_status === "LATE" ? styles.late : styles.absent]}>
                    {row.attendance_status}
                  </Text>
                </View>
              ))}
            </View>
          </ScrollView>
          <Text style={styles.note}>
            Policy: ≥{report.data.present_min_percent}% present · {report.data.late_min_percent}–{report.data.present_min_percent - 1}% late · &lt;{report.data.late_min_percent}% absent. Synced to the register.
          </Text>
        </Card>
      ) : null}
    </AsyncState>
  );
}

function ChatBlock({ messages, connected, onSend }: { messages: { sender_name: string; sender_role: string; body: string }[]; connected: boolean; onSend: (body: string) => void }) {
  const [draft, setDraft] = useState("");
  return (
    <Card style={styles.stack}>
      <Text style={styles.sectionTitle}>Class chat {connected ? "" : "(reconnecting…)"}</Text>
      <View style={styles.chatList}>
        {messages.slice(-30).map((m, i) => (
          <Text key={i} style={styles.chatLine}>
            <Text style={m.sender_role === "TEACHER" ? styles.chatTeacher : styles.chatStudent}>{m.sender_name}: </Text>
            {m.body}
          </Text>
        ))}
        {messages.length === 0 ? <Text style={styles.meta}>No messages yet.</Text> : null}
      </View>
      <View style={styles.chatInputRow}>
        <TextInput style={styles.chatInput} value={draft} onChangeText={setDraft} placeholder="Message the class…" placeholderTextColor={Colors.placeholder} maxLength={1000} />
        <TouchableOpacity
          style={styles.sendButton}
          onPress={() => {
            onSend(draft);
            setDraft("");
          }}
        >
          <Send size={16} color="#FFFFFF" />
        </TouchableOpacity>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 10, marginBottom: 12 },
  row: { flexDirection: "row", gap: 8 },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  sectionTitle: { fontSize: 14, fontWeight: "700", color: Colors.primary },
  meta: { fontSize: 12, color: Colors.mutedForeground },
  name: { fontSize: 13, color: Colors.primary },
  hand: { fontSize: 14 },
  link: { fontSize: 12, fontWeight: "700", color: Colors.accent },
  admitButton: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: Colors.accent, borderRadius: Radius.field, paddingHorizontal: 10, paddingVertical: 6 },
  admitText: { color: "#FFFFFF", fontSize: 12, fontWeight: "700" },
  error: { color: Colors.destructive, fontSize: 13, marginBottom: 8 },
  endButton: { backgroundColor: Colors.destructive, marginBottom: 8 },
  note: { fontSize: 11, color: Colors.mutedForeground },
  chatList: { maxHeight: 220, gap: 4 },
  chatLine: { fontSize: 13, color: Colors.primary },
  chatTeacher: { fontWeight: "700", color: Colors.accent },
  chatStudent: { fontWeight: "600" },
  chatInputRow: { flexDirection: "row", gap: 8 },
  chatInput: { flex: 1, borderWidth: 1, borderColor: Colors.border, borderRadius: Radius.field, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13, color: Colors.primary },
  sendButton: { backgroundColor: Colors.accent, borderRadius: Radius.field, width: 44, alignItems: "center", justifyContent: "center" },
  tableRow: { flexDirection: "row", borderBottomWidth: 1, borderBottomColor: Colors.border },
  tableCell: { paddingVertical: 6, paddingRight: 14, fontSize: 12, color: Colors.primary },
  tableHead: { fontWeight: "700", color: Colors.mutedForeground },
  nameCol: { width: 150 },
  present: { color: Colors.successText, fontWeight: "700" },
  late: { color: Colors.warningText, fontWeight: "700" },
  absent: { color: Colors.destructiveText, fontWeight: "700" },
});
