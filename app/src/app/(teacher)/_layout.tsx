/**
 * Teacher console — role gate + shell, the mobile counterpart of
 * fontend/app/teacher/layout.tsx (InstitutionRoleConsole requiredRole TEACHER,
 * alsoAllow MENTOR) and the TeacherShell header/drawer.
 */

import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { Stack, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { TeacherNavDrawer, TeacherShellHeader } from "@/components/teacher-shell";
import { isTeacherRole } from "@/lib/roles";
import { useInstitutionAuth } from "@/lib/session";
import { Colors } from "@/theme";

export default function TeacherLayout() {
  const { isAuthenticated, isLoading, user } = useInstitutionAuth();
  const router = useRouter();
  const [navOpen, setNavOpen] = useState(false);
  const authorised = isTeacherRole(user?.roles);

  useEffect(() => {
    if (!isLoading && (!isAuthenticated || !authorised)) router.replace("/login");
  }, [authorised, isAuthenticated, isLoading, router]);

  if (isLoading || !isAuthenticated || !authorised) {
    return (
      <View style={styles.gate}>
        <ActivityIndicator size="large" color={Colors.accent} />
        <Text style={styles.gateLabel}>Loading teacher console…</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.shell} edges={["top"]}>
      <TeacherShellHeader onOpenNav={() => setNavOpen(true)} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: Colors.background } }}>
        <Stack.Screen name="dashboard" />
        <Stack.Screen name="online-classes/index" />
        <Stack.Screen name="online-classes/new" />
        <Stack.Screen name="online-classes/[id]" />
        <Stack.Screen name="schedule" />
        <Stack.Screen name="attendance/mark" />
        <Stack.Screen name="attendance/sessions/index" />
        <Stack.Screen name="attendance/sessions/[id]" />
        <Stack.Screen name="attendance/leaves" />
        <Stack.Screen name="examinations/index" />
        <Stack.Screen name="examinations/new" />
        <Stack.Screen name="examinations/[id]/index" />
        <Stack.Screen name="examinations/[id]/questions" />
        <Stack.Screen name="examinations/[id]/results" />
        <Stack.Screen name="examinations/[id]/attempts/[attemptId]" />
        <Stack.Screen name="question-bank" />
        <Stack.Screen name="assignments/index" />
        <Stack.Screen name="assignments/new" />
        <Stack.Screen name="assignments/[id]/index" />
        <Stack.Screen name="assignments/[id]/submissions" />
        <Stack.Screen name="submissions/[id]" />
        <Stack.Screen name="teams/index" />
        <Stack.Screen name="teams/[id]" />
        <Stack.Screen name="content/index" />
        <Stack.Screen name="content/upload" />
        <Stack.Screen name="notices/index" />
        <Stack.Screen name="notices/new" />
        <Stack.Screen name="notifications" />
        <Stack.Screen name="discussion/index" />
        <Stack.Screen name="discussion/[id]" />
      </Stack>
      <TeacherNavDrawer open={navOpen} onClose={() => setNavOpen(false)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  shell: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  gate: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    backgroundColor: Colors.background,
  },
  gateLabel: {
    fontSize: 14,
    color: Colors.mutedForeground,
  },
});
