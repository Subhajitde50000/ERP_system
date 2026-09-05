/**
 * Student console shell — mobile port of the website's InstitutionConsoleShell
 * (fontend/components/institution-console/institution-console-shell.tsx +
 * fontend/components/student/student-shell.tsx).
 *
 * On the website the sidebar is hidden on phones and a hamburger opens the
 * same drawer; the app renders exactly that mobile layout: a 56px white
 * header with a menu button and the drawer with the console header, the 12
 * student nav items, the identity card and Sign out.
 */

import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { usePathname, useRouter } from "expo-router";
import {
  BookOpen,
  CalendarDays,
  ClipboardCheck,
  FileSpreadsheet,
  GraduationCap,
  IndianRupee,
  LayoutDashboard,
  LogOut,
  Megaphone,
  Menu,
  MessageSquare,
  Repeat2,
  UserRound,
  Users,
  Video,
  X,
  type LucideIcon,
} from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { NotificationBell } from "@/components/notification-bell";
import { isTeacherRole } from "@/lib/roles";
import { useInstitutionAuth } from "@/lib/session";
import { Colors } from "@/theme";

/** C-ST-01 … C-ST-20 navigation; everything is scoped to the signed-in student.
 * Group segments are transparent in expo-router URLs, so plain paths are used
 * (they resolve inside the (student) group and match `usePathname()`). */
const NAVIGATION: { label: string; href: string; icon: LucideIcon }[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Online classes", href: "/online-classes", icon: Video },
  { label: "Profile", href: "/profile", icon: UserRound },
  { label: "Attendance", href: "/attendance", icon: ClipboardCheck },
  { label: "Timetable", href: "/timetable", icon: CalendarDays },
  { label: "Examinations", href: "/examinations", icon: FileSpreadsheet },
  { label: "Assignments", href: "/assignments", icon: Repeat2 },
  { label: "Project Teams", href: "/teams", icon: Users },
  { label: "Content", href: "/content", icon: BookOpen },
  { label: "Results", href: "/results", icon: GraduationCap },
  { label: "Notices", href: "/notices", icon: Megaphone },
  { label: "Discussion", href: "/discussion", icon: MessageSquare },
  { label: "Fees", href: "/fees", icon: IndianRupee },
];

export function StudentShellHeader({ onOpenNav }: { onOpenNav: () => void }) {
  return (
    <View style={styles.header}>
      <TouchableOpacity
        accessibilityLabel="Open navigation"
        onPress={onOpenNav}
        style={styles.menuButton}
      >
        <Menu size={20} color={Colors.mutedForeground} />
      </TouchableOpacity>
      <GraduationCap size={16} color={Colors.mutedForeground} />
      <Text style={styles.headerTitle}>My learning</Text>
      <NotificationBell />
    </View>
  );
}

export function StudentNavDrawer({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { user, logout } = useInstitutionAuth();
  const router = useRouter();
  const pathname = usePathname();
  const insets = useSafeAreaInsets();

  if (!open) return null;

  const initials = (user?.name ?? "Student")
    .split(" ")
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <View style={StyleSheet.absoluteFill}>
      <Pressable
        accessibilityLabel="Close navigation"
        onPress={onClose}
        style={styles.backdrop}
      />
      <View style={[styles.drawer, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
        <View style={styles.drawerHeader}>
          <View style={styles.logoBox}>
            <GraduationCap size={16} color="#FFFFFF" />
          </View>
          <View style={styles.drawerHeaderText}>
            <Text style={styles.consoleTitle} numberOfLines={1}>
              Student console
            </Text>
            <Text style={styles.consoleName} numberOfLines={1}>
              {user?.name ?? "—"}
            </Text>
          </View>
          <TouchableOpacity accessibilityLabel="Close navigation" onPress={onClose} style={styles.closeButton}>
            <X size={18} color={Colors.mutedForeground} />
          </TouchableOpacity>
        </View>

        <ScrollView style={styles.nav} contentContainerStyle={styles.navContent}>
          {NAVIGATION.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <TouchableOpacity
                key={item.href}
                accessibilityState={{ selected: active }}
                onPress={() => {
                  onClose();
                  if (!active) router.push(item.href as never);
                }}
                style={[styles.navItem, active && styles.navItemActive]}
              >
                <item.icon size={16} color={active ? Colors.accent : Colors.mutedForeground} />
                <Text style={[styles.navLabel, active && styles.navLabelActive]}>{item.label}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        <View style={styles.drawerFooter}>
          <View style={styles.identity}>
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>{initials}</Text>
            </View>
            <View style={styles.identityText}>
              <Text style={styles.identityEmail} numberOfLines={1}>
                {user?.email ?? "—"}
              </Text>
              <Text style={styles.identityRole} numberOfLines={1}>
                Student
              </Text>
            </View>
          </View>
          {isTeacherRole(user?.roles) ? (
            <TouchableOpacity
              accessibilityRole="button"
              onPress={() => {
                onClose();
                router.replace("/(teacher)/dashboard");
              }}
              style={styles.signOut}
            >
              <GraduationCap size={16} color={Colors.mutedForeground} />
              <Text style={styles.signOutLabel}>Switch to teacher</Text>
            </TouchableOpacity>
          ) : null}
          <TouchableOpacity
            accessibilityRole="button"
            onPress={async () => {
              onClose();
              await logout();
              router.replace("/login");
            }}
            style={styles.signOut}
          >
            <LogOut size={16} color={Colors.mutedForeground} />
            <Text style={styles.signOutLabel}>Sign out</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    height: 56,
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
    backgroundColor: "#FFFFFF",
  },
  menuButton: {
    marginLeft: -4,
    padding: 8,
    borderRadius: 8,
  },
  headerTitle: {
    fontSize: 14,
    fontWeight: "700",
    color: Colors.primary,
  },
  backdrop: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(15,23,42,0.6)",
  },
  drawer: {
    position: "absolute",
    top: 0,
    bottom: 0,
    left: 0,
    width: 256,
    backgroundColor: "#FFFFFF",
    shadowColor: "#0F172A",
    shadowOpacity: 0.25,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 8 },
    elevation: 12,
  },
  drawerHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 20,
    paddingVertical: 20,
  },
  logoBox: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: Colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  drawerHeaderText: {
    flex: 1,
  },
  consoleTitle: {
    fontSize: 14,
    fontWeight: "700",
    color: Colors.primary,
  },
  consoleName: {
    fontSize: 11,
    color: Colors.mutedForeground,
  },
  closeButton: {
    padding: 4,
  },
  nav: {
    flex: 1,
  },
  navContent: {
    gap: 4,
    paddingHorizontal: 12,
    paddingBottom: 12,
  },
  navItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  navItemActive: {
    backgroundColor: Colors.accentLight,
  },
  navLabel: {
    fontSize: 14,
    fontWeight: "500",
    color: Colors.mutedForeground,
  },
  navLabelActive: {
    color: Colors.accent,
  },
  drawerFooter: {
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    padding: 12,
  },
  identity: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingHorizontal: 8,
    paddingVertical: 8,
  },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.accentLight,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: {
    fontSize: 13,
    fontWeight: "700",
    color: Colors.accent,
  },
  identityText: {
    flex: 1,
  },
  identityEmail: {
    fontSize: 13,
    fontWeight: "600",
    color: Colors.foreground,
  },
  identityRole: {
    fontSize: 11,
    color: Colors.mutedForeground,
  },
  signOut: {
    marginTop: 4,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  signOutLabel: {
    fontSize: 14,
    fontWeight: "500",
    color: Colors.mutedForeground,
  },
});
