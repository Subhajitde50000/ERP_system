/**
 * Student class detail — waiting room, live participation (chat, raise hand,
 * materials) and automatic attendance. Audio/video joins via the web console
 * (deep-linked from the InClass screen); staying connected here still records
 * attendance.
 */

import { useEffect, useState } from "react";
import { Linking, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Hand, Paperclip } from "lucide-react-native";

import { AsyncState } from "@/components/principal-ui";
import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Card, PageHeader } from "@/components/ui";
import { useLiveChat } from "@/hooks/use-live-chat";
import { useResource } from "@/hooks/use-resource";
import { dateTime } from "@/lib/format";
import {
  fileHref,
  fetchStudentChatHistory,
  fetchStudentClassView,
  joinOnlineClass,
  leaveOnlineClass,
  resolveClassWebUrl,
  webClassUrl,
  type OnlineClassDetail,
} from "@/lib/online-class";
import * as WebBrowser from "expo-web-browser";
import { Colors, Radius } from "@/theme";

export default function StudentOnlineClassDetailPage() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const detail = useResource(() => fetchStudentClassView(id), [id]);

  return (
    <Screen>
      <AsyncState loading={detail.loading} error={detail.error} onRetry={detail.reload} loadingLabel="Loading class…">
        {detail.data ? <Body key={detail.data.join_state === "IN_CLASS" ? "live" : "pre"} classId={id} detail={detail.data} onChanged={detail.reload} /> : null}
      </AsyncState>
    </Screen>
  );
}

function Body({ classId, detail, onChanged }: { classId: string; detail: OnlineClassDetail; onChanged: () => void }) {
  if (detail.status !== "LIVE") return <NotLive detail={detail} />;
  if (detail.join_state === "IN_CLASS") return <InClass classId={classId} detail={detail} onLeft={onChanged} />;
  return <WaitingRoom classId={classId} detail={detail} onChanged={onChanged} />;
}

function NotLive({ detail }: { detail: OnlineClassDetail }) {
  return (
    <>
      <PageHeader
        title={`${detail.subject_code} · ${detail.topic}`}
        subtitle={
          detail.status === "SCHEDULED" && detail.scheduled_at
            ? `Starts ${dateTime(detail.scheduled_at)} — come back when it goes live.`
            : detail.status === "COMPLETED"
              ? "Ended — your attendance was recorded automatically."
              : "This class was cancelled."
        }
      />
      {detail.recording_url ? (
        <Card>
          <Button variant="secondary" onPress={() => Linking.openURL(fileHref(detail.recording_url!))}>
            Watch the recording
          </Button>
        </Card>
      ) : null}
    </>
  );
}

function WaitingRoom({ classId, detail, onChanged }: { classId: string; detail: OnlineClassDetail; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const waiting = detail.join_state === "WAITING";

  useEffect(() => {
    if (!waiting) return;
    const timer = setInterval(onChanged, 4000);
    return () => clearInterval(timer);
  }, [waiting, onChanged]);

  return (
    <>
      <PageHeader title={`${detail.subject_code} · ${detail.topic}`} subtitle={`${detail.class_name} · ${detail.teacher_name} · live now`} />
      {waiting ? (
        <Card style={styles.center}>
          <Text style={styles.waitTitle}>You are in the waiting room</Text>
          <Text style={styles.waitMeta}>The teacher will admit you in a moment — keep this screen open.</Text>
        </Card>
      ) : (
        <Card style={styles.stack}>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          {detail.allow_join ? (
            <Button
              onPress={async () => {
                setError(null);
                try {
                  await joinOnlineClass(classId);
                  onChanged();
                } catch (caught) {
                  setError(caught instanceof Error ? caught.message : "Could not join.");
                }
              }}
            >
              Join class
            </Button>
          ) : (
            <Text style={styles.waitMeta}>The teacher has paused joining — wait for the class to open.</Text>
          )}
        </Card>
      )}
    </>
  );
}

function InClass({ classId, detail, onLeft }: { classId: string; detail: OnlineClassDetail; onLeft: () => void }) {
  const [ended, setEnded] = useState(false);
  const [handRaised, setHandRaised] = useState(false);
  const [draft, setDraft] = useState("");
  const history = useResource(() => fetchStudentChatHistory(classId), [classId]);
  const chat = useLiveChat(classId, !ended, () => setEnded(true));

  async function handleOpenLiveClass() {
    const url = resolveClassWebUrl(classId, "student");
    try {
      await WebBrowser.openBrowserAsync(url);
    } catch {
      await Linking.openURL(url);
    }
  }

  if (ended) {
    return (
      <>
        <PageHeader title="Class ended" subtitle="Your attendance was recorded automatically. Thanks for joining!" />
        <Card>
          <Button variant="secondary" onPress={onLeft}>Back to my classes</Button>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader title={`${detail.subject_code} · ${detail.topic}`} subtitle={`${detail.class_name} · ${detail.teacher_name} · live`} />

      <Card style={styles.stack}>
        <Text style={styles.note}>
          🎥 Live classroom runs with full video, audio & whiteboard. Tapping below opens the live stream while your attendance and chat remain active here.
        </Text>
        <Button onPress={handleOpenLiveClass}>Join Live Audio & Video</Button>
        <View style={styles.row}>
          <TouchableOpacity
            style={[styles.handButton, handRaised && styles.handButtonActive]}
            onPress={() => {
              chat.setHand(!handRaised);
              setHandRaised(!handRaised);
            }}
          >
            <Hand size={16} color={handRaised ? Colors.amber700 : Colors.primary} />
            <Text style={[styles.handText, handRaised && styles.handTextActive]}>{handRaised ? "Hand raised" : "Raise hand"}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.leaveButton}
            onPress={async () => {
              try {
                await leaveOnlineClass(classId);
              } catch {
                /* attendance still settles at class end */
              }
              onLeft();
            }}
          >
            <Text style={styles.leaveText}>Leave class</Text>
          </TouchableOpacity>
        </View>
      </Card>

      <Card style={styles.stack}>
        <Text style={styles.sectionTitle}>Materials</Text>
        {detail.files.length === 0 ? <Text style={styles.meta}>Nothing shared yet.</Text> : null}
        {detail.files.map((file) => (
          <TouchableOpacity key={file.id} style={styles.fileRow} onPress={() => Linking.openURL(fileHref(file.url))}>
            <Paperclip size={14} color={Colors.mutedForeground} />
            <Text style={styles.fileLink} numberOfLines={1}> {file.file_name}</Text>
          </TouchableOpacity>
        ))}
      </Card>

      <Card style={styles.stack}>
        <Text style={styles.sectionTitle}>Class chat {chat.connected ? "" : "(reconnecting…)"}</Text>
        <ScrollView style={styles.chatList}>
          {(history.data ?? []).map((m) => (
            <Text key={m.id} style={styles.chatLine}>
              <Text style={m.sender_role === "TEACHER" ? styles.chatTeacher : styles.chatStudent}>{m.sender_name}: </Text>
              {m.body}
            </Text>
          ))}
          {chat.messages.map((m, i) => (
            <Text key={`live-${i}`} style={styles.chatLine}>
              <Text style={m.sender_role === "TEACHER" ? styles.chatTeacher : styles.chatStudent}>{m.sender_name}: </Text>
              {m.body}
            </Text>
          ))}
        </ScrollView>
        <View style={styles.chatInputRow}>
          <TextInput style={styles.chatInput} value={draft} onChangeText={setDraft} placeholder="Message the class…" placeholderTextColor={Colors.placeholder} maxLength={1000} />
          <TouchableOpacity
            style={styles.sendButton}
            onPress={() => {
              chat.sendMessage(draft);
              setDraft("");
            }}
          >
            <Text style={styles.sendText}>Send</Text>
          </TouchableOpacity>
        </View>
      </Card>
    </>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 10, marginBottom: 12 },
  center: { alignItems: "center", gap: 6, marginBottom: 12 },
  waitTitle: { fontSize: 15, fontWeight: "700", color: Colors.primary },
  waitMeta: { fontSize: 12, color: Colors.mutedForeground, textAlign: "center" },
  error: { color: Colors.destructive, fontSize: 13 },
  row: { flexDirection: "row", gap: 8 },
  handButton: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, borderWidth: 1, borderColor: Colors.border, borderRadius: Radius.field, paddingVertical: 10 },
  handButtonActive: { backgroundColor: Colors.amber50, borderColor: Colors.warningBorder },
  handText: { fontSize: 12, fontWeight: "700", color: Colors.primary },
  handTextActive: { color: Colors.amber700 },
  leaveButton: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: Colors.destructive, borderRadius: Radius.field, paddingVertical: 10 },
  leaveText: { color: "#FFFFFF", fontSize: 12, fontWeight: "700" },
  note: { fontSize: 12, color: Colors.bodyText, lineHeight: 17 },
  sectionTitle: { fontSize: 14, fontWeight: "700", color: Colors.primary },
  meta: { fontSize: 12, color: Colors.mutedForeground },
  fileRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  fileLink: { fontSize: 13, color: Colors.accent, flex: 1 },
  chatList: { maxHeight: 220 },
  chatLine: { fontSize: 13, color: Colors.primary, marginBottom: 4 },
  chatTeacher: { fontWeight: "700", color: Colors.accent },
  chatStudent: { fontWeight: "600" },
  chatInputRow: { flexDirection: "row", gap: 8 },
  chatInput: { flex: 1, borderWidth: 1, borderColor: Colors.border, borderRadius: Radius.field, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13, color: Colors.primary },
  sendButton: { backgroundColor: Colors.accent, borderRadius: Radius.field, paddingHorizontal: 16, alignItems: "center", justifyContent: "center" },
  sendText: { color: "#FFFFFF", fontSize: 12, fontWeight: "700" },
});
