/**
 * Parent console — role gate + shell, the mobile counterpart of
 * fontend/app/parent/layout.tsx (InstitutionRoleConsole requiredRole PARENT
 * around ParentConsoleProvider around ParentShell).
 *
 * The provider sits inside the gate on purpose: the roster call is a
 * guardian-scoped request, and issuing it for an account that has just been
 * bounced to /login would leak a request (and a 403 render) before the redirect.
 */

import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { Stack, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { ParentNavDrawer, ParentShellHeader } from "@/components/parent-shell";
import { ParentConsoleProvider } from "@/lib/parent-console";
import { useInstitutionAuth } from "@/lib/session";
import { Colors } from "@/theme";

export default function ParentLayout() {
  const { isAuthenticated, isLoading, hasRole } = useInstitutionAuth();
  const router = useRouter();
  const [navOpen, setNavOpen] = useState(false);
  const authorised = hasRole("PARENT");

  useEffect(() => {
    if (!isLoading && (!isAuthenticated || !authorised)) router.replace("/login");
  }, [authorised, isAuthenticated, isLoading, router]);

  if (isLoading || !isAuthenticated || !authorised) {
    return (
      <View style={styles.gate}>
        <ActivityIndicator size="large" color={Colors.accent} />
        <Text style={styles.gateLabel}>Loading your portal…</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.shell} edges={["top"]}>
      <ParentConsoleProvider>
        <ParentShellHeader onOpenNav={() => setNavOpen(true)} />
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: Colors.background } }}>
          <Stack.Screen name="dashboard" />
          <Stack.Screen name="today" />
          <Stack.Screen name="attendance" />
          <Stack.Screen name="leave" />
          <Stack.Screen name="timetable" />
          <Stack.Screen name="exams" />
          <Stack.Screen name="results" />
          <Stack.Screen name="assignments" />
          <Stack.Screen name="notices" />
          <Stack.Screen name="notifications" />
          <Stack.Screen name="fees" />
          <Stack.Screen name="me" />
        </Stack>
        <ParentNavDrawer open={navOpen} onClose={() => setNavOpen(false)} />
      </ParentConsoleProvider>
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
