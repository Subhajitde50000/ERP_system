/**
 * Student console — role gate + shell, the mobile counterpart of
 * fontend/app/student/layout.tsx (InstitutionRoleConsole requiredRole STUDENT)
 * and the StudentShell header/drawer.
 */

import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { Stack, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { StudentNavDrawer, StudentShellHeader } from "@/components/student-shell";
import { useInstitutionAuth } from "@/lib/session";
import { Colors } from "@/theme";

export default function StudentLayout() {
  const { isAuthenticated, isLoading, hasRole } = useInstitutionAuth();
  const router = useRouter();
  const [navOpen, setNavOpen] = useState(false);
  const authorised = hasRole("STUDENT");

  useEffect(() => {
    if (!isLoading && (!isAuthenticated || !authorised)) router.replace("/login");
  }, [authorised, isAuthenticated, isLoading, router]);

  if (isLoading || !isAuthenticated || !authorised) {
    return (
      <View style={styles.gate}>
        <ActivityIndicator size="large" color={Colors.accent} />
        <Text style={styles.gateLabel}>Loading student console…</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.shell} edges={["top"]}>
      <StudentShellHeader onOpenNav={() => setNavOpen(true)} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: Colors.background } }}>
        <Stack.Screen name="dashboard" />
        <Stack.Screen name="online-classes/index" />
        <Stack.Screen name="online-classes/[id]" />
        <Stack.Screen name="profile" />
        <Stack.Screen name="attendance/index" />
        <Stack.Screen name="attendance/calendar" />
        <Stack.Screen name="attendance/leaves/new" />
        <Stack.Screen name="timetable" />
        <Stack.Screen name="examinations/index" />
        <Stack.Screen name="examinations/[id]/attempt" />
        <Stack.Screen name="examinations/[id]/result" />
        <Stack.Screen name="assignments/index" />
        <Stack.Screen name="assignments/[id]/index" />
        <Stack.Screen name="assignments/[id]/milestones" />
        <Stack.Screen name="teams/index" />
        <Stack.Screen name="teams/[id]" />
        <Stack.Screen name="content/index" />
        <Stack.Screen name="content/[id]" />
        <Stack.Screen name="results/index" />
        <Stack.Screen name="results/[id]/index" />
        <Stack.Screen name="results/[id]/grade-card" />
        <Stack.Screen name="notices" />
        <Stack.Screen name="notifications" />
        <Stack.Screen name="discussion/index" />
        <Stack.Screen name="discussion/[id]" />
        <Stack.Screen name="fees/index" />
        <Stack.Screen name="fees/receipt/[paymentId]" />
      </Stack>
      <StudentNavDrawer open={navOpen} onClose={() => setNavOpen(false)} />
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
