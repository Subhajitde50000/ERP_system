/**
 * Teacher console shell — mobile port of fontend/components/teacher/teacher-shell.tsx
 * + InstitutionConsoleShell. Same 12 C-TC nav items, same drawer layout as
 * the student console so the two roles feel like one app.
 */

import { Pressable, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { usePathname, useRouter } from "expo-router";
import {
  BookOpen,
  CalendarDays,
  ClipboardCheck,
  Database,
  FileSpreadsheet,
  GraduationCap,
  LayoutDashboard,
  LogOut,
  Megaphone,
  Menu,
  MessageSquare,
  PenSquare,
  Repeat2,
  UserRoundCheck,
  Users,
  Video,
  X,
  type LucideIcon,
} from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { NotificationBell } from "@/components/notification-bell";
import { useInstitutionAuth } from "@/lib/session";
import { isStudentRole, roleLabel } from "@/lib/roles";
import { Colors } from "@/theme";

/** C-TC-01 … C-TC-22 navigation; group segments are transparent in expo-router. */
const NAVIGATION: { label: string; href: string; icon: LucideIcon }[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Online classes", href: "/online-classes", icon: Video },
  { label: "My schedule", href: "/schedule", icon: CalendarDays },
  { label: "Mark attendance", href: "/attendance/mark", icon: PenSquare },
  { label: "Attendance sessions", href: "/attendance/sessions", icon: ClipboardCheck },
  { label: "Leave requests", href: "/attendance/leaves", icon: UserRoundCheck },
  { label: "Examinations", href: "/examinations", icon: FileSpreadsheet },
  { label: "Question Bank", href: "/question-bank", icon: Database },
  { label: "Assignments", href: "/assignments", icon: Repeat2 },
  { label: "Project Teams", href: "/teams", icon: Users },
  { label: "Content", href: "/content", icon: BookOpen },
  { label: "Notices", href: "/notices", icon: Megaphone },
  { label: "Discussion", href: "/discussion", icon: MessageSquare },
];

export function TeacherShellHeader({ onOpenNav }: { onOpenNav: () => void }) {
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
      <Text style={styles.headerTitle}>Classes, exams and assignments</Text>
      <NotificationBell />
    </View>
  );
}

export function TeacherNavDrawer({
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

  const initials = (user?.name ?? "Teacher")
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
              Teacher console
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
                {roleLabel(user?.roles)}
              </Text>
            </View>
          </View>
          {isStudentRole(user?.roles) ? (
            <TouchableOpacity
              accessibilityRole="button"
              onPress={() => {
                onClose();
                router.replace("/(student)/dashboard");
              }}
              style={styles.signOut}
            >
              <GraduationCap size={16} color={Colors.mutedForeground} />
              <Text style={styles.signOutLabel}>Switch to student</Text>
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
    flex: 1,
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
