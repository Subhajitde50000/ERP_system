/**
 * Parent console shell (mobile) — the counterpart of the website's
 * `fontend/components/parent/parent-shell.tsx`.
 *
 * Same 56px header + drawer as the student and teacher consoles, with two things
 * they do not need:
 *
 *  * the nav is filtered by the selected child's `access_scope`, so a tab the school
 *    never granted is not shown at all — while the server still 403s it if the URL is
 *    typed in. Hiding is courtesy; the check is the control;
 *  * the header carries the child switcher, because "your child" is ambiguous and a
 *    guardian with two children must never wonder which one they just screenshotted.
 */

import { useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { usePathname, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  CalendarDays,
  Check,
  ChevronDown,
  ClipboardCheck,
  FileText,
  GraduationCap,
  IndianRupee,
  LogOut,
  Megaphone,
  Menu,
  NotebookPen,
  Repeat2,
  ShieldCheck,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react-native";

import { NotificationBell } from "@/components/notification-bell";
import { useInstitutionAuth } from "@/lib/session";
import type { ParentChildRow } from "@/lib/parent";
import { useParentConsole } from "@/lib/parent-console";
import { Colors, Radius } from "@/theme";

/** `{ module }` means the tab appears only when the selected child's link grants it. */
export const PARENT_NAVIGATION: { label: string; href: string; icon: LucideIcon; module?: string }[] = [
  { label: "My family", href: "/dashboard", icon: ShieldCheck },
  { label: "Today", href: "/today", icon: GraduationCap },
  { label: "Attendance", href: "/attendance", icon: ClipboardCheck, module: "attendance" },
  { label: "Leave", href: "/leave", icon: NotebookPen, module: "attendance" },
  { label: "Timetable", href: "/timetable", icon: CalendarDays, module: "timetable" },
  { label: "Examinations", href: "/exams", icon: FileText, module: "examination" },
  { label: "Results", href: "/results", icon: GraduationCap, module: "results" },
  { label: "Assignments", href: "/assignments", icon: Repeat2, module: "assignment" },
  { label: "Notices", href: "/notices", icon: Megaphone, module: "notice" },
  { label: "Fees", href: "/fees", icon: IndianRupee, module: "finance" },
  { label: "My details", href: "/me", icon: UserRound },
];

export function ParentShellHeader({ onOpenNav }: { onOpenNav: () => void }) {
  const { activeChild } = useParentConsole();
  const [switcher, setSwitcher] = useState(false);

  return (
    <View style={styles.header}>
      <TouchableOpacity accessibilityLabel="Open navigation" onPress={onOpenNav} style={styles.menuButton}>
        <Menu size={20} color={Colors.mutedForeground} />
      </TouchableOpacity>
      <TouchableOpacity
        accessibilityRole="button"
        accessibilityLabel="Change child"
        onPress={() => setSwitcher(true)}
        style={styles.childButton}
      >
        <Text style={styles.childName} numberOfLines={1}>
          {activeChild ? activeChild.name : "Parent portal"}
        </Text>
        {activeChild?.class_name ? <Text style={styles.childMeta}>{activeChild.class_name}</Text> : null}
        <ChevronDown size={14} color={Colors.mutedForeground} />
      </TouchableOpacity>
      <NotificationBell />
      <ChildSwitcher open={switcher} onClose={() => setSwitcher(false)} />
    </View>
  );
}

/**
 * The child picker. Only live links are selectable; a suspended or expired one is
 * listed greyed with its reason, because the guardian needs to know the record
 * exists and why it is closed rather than finding it quietly missing.
 */
function ChildSwitcher({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data, activeChild, selectChild } = useParentConsole();
  const rows = data?.children ?? [];

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable accessibilityLabel="Close child picker" onPress={onClose} style={styles.sheetBackdrop}>
        <View style={styles.sheet} onStartShouldSetResponder={() => true}>
          <View style={styles.sheetHeader}>
            <Text style={styles.sheetTitle}>Choose a child</Text>
            <TouchableOpacity accessibilityLabel="Close" onPress={onClose}>
              <X size={18} color={Colors.mutedForeground} />
            </TouchableOpacity>
          </View>
          {rows.length === 0 ? (
            <Text style={styles.sheetEmpty}>No student is linked to your account yet.</Text>
          ) : (
            <ScrollView contentContainerStyle={styles.sheetList}>
              {rows.map((child) => (
                <SheetRow
                  key={child.link_id}
                  child={child}
                  active={child.student_id === activeChild?.student_id}
                  onSelect={() => {
                    selectChild(child.student_id);
                    onClose();
                  }}
                />
              ))}
            </ScrollView>
          )}
        </View>
      </Pressable>
    </Modal>
  );
}

function SheetRow({
  child,
  active,
  onSelect,
}: {
  child: ParentChildRow;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <TouchableOpacity
      accessibilityRole="button"
      accessibilityState={{ selected: active, disabled: !child.is_live }}
      disabled={!child.is_live}
      onPress={onSelect}
      style={[styles.sheetRow, active && styles.sheetRowActive, !child.is_live && styles.sheetRowDead]}
    >
      <View style={styles.sheetRowText}>
        <Text style={styles.sheetRowName}>{child.name}</Text>
        <Text style={styles.sheetRowMeta} numberOfLines={2}>
          {[
            child.class_name,
            child.relation,
            child.is_live ? `${child.access_scope.length} areas` : `${child.blocked_reason?.toLowerCase().replace("_", " ") ?? "closed"}`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </Text>
      </View>
      {active ? <Check size={18} color={Colors.accent} /> : null}
    </TouchableOpacity>
  );
}

export function ParentNavDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, logout } = useInstitutionAuth();
  const { activeChild } = useParentConsole();
  const router = useRouter();
  const pathname = usePathname();
  const insets = useSafeAreaInsets();

  if (!open) return null;

  const scope = new Set(activeChild?.access_scope ?? []);
  const initials = (user?.name ?? "Guardian")
    .split(" ")
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <View style={StyleSheet.absoluteFill}>
      <Pressable accessibilityLabel="Close navigation" onPress={onClose} style={styles.backdrop} />
      <View style={[styles.drawer, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
        <View style={styles.drawerHeader}>
          <View style={styles.logoBox}>
            <ShieldCheck size={16} color="#FFFFFF" />
          </View>
          <View style={styles.drawerHeaderText}>
            <Text style={styles.consoleTitle} numberOfLines={1}>
              Parent portal
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
          {PARENT_NAVIGATION.filter((item) => !item.module || (activeChild ? scope.has(item.module) : false)).map(
            (item) => {
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
            },
          )}
          {activeChild ? (
            <Text style={styles.navFootnote}>
              {(() => {
                const hidden = PARENT_NAVIGATION.filter(
                  (item) => item.module && !scope.has(item.module),
                ).map((item) => item.label);
                return hidden.length
                  ? `${hidden.join(", ")} is hidden because the school has not granted it for ${activeChild.name}. Ask the office if that looks wrong.`
                  : `Every area is open for ${activeChild.name}.`;
              })()}
            </Text>
          ) : null}
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
                Guardian
              </Text>
            </View>
          </View>
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
    gap: 8,
    minHeight: 56,
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
  childButton: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    minWidth: 0,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: Radius.field,
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.background,
  },
  childName: {
    fontSize: 14,
    fontWeight: "700",
    color: Colors.primary,
    flexShrink: 1,
  },
  childMeta: {
    fontSize: 11,
    color: Colors.mutedForeground,
    flexShrink: 1,
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
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  drawerHeaderText: { flex: 1, minWidth: 0 },
  logoBox: {
    height: 32,
    width: 32,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: Colors.accent,
  },
  consoleTitle: { fontSize: 13, fontWeight: "700", color: Colors.primary },
  consoleName: { fontSize: 11, color: Colors.mutedForeground, marginTop: 1 },
  closeButton: { padding: 6, borderRadius: 8 },
  nav: { flex: 1 },
  navContent: { paddingVertical: 8, gap: 2 },
  navItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 11,
  },
  navItemActive: { backgroundColor: Colors.accentLight, borderRightWidth: 2, borderRightColor: Colors.accent },
  navLabel: { fontSize: 14, color: Colors.mutedForeground, fontWeight: "500" },
  navLabelActive: { color: Colors.accent, fontWeight: "700" },
  navFootnote: {
    paddingHorizontal: 16,
    paddingTop: 10,
    fontSize: 11,
    lineHeight: 16,
    color: Colors.mutedForeground,
  },
  drawerFooter: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 12,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    gap: 10,
  },
  identity: { flexDirection: "row", alignItems: "center", gap: 10 },
  identityText: { flex: 1, minWidth: 0 },
  avatar: {
    height: 32,
    width: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: Colors.muted,
  },
  avatarText: { fontSize: 12, fontWeight: "700", color: Colors.mutedForeground },
  identityEmail: { fontSize: 12, color: Colors.foreground },
  identityRole: { fontSize: 11, color: Colors.mutedForeground, marginTop: 1 },
  signOut: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 8,
  },
  signOutLabel: { fontSize: 13, color: Colors.mutedForeground, fontWeight: "600" },
  sheetBackdrop: {
    flex: 1,
    backgroundColor: "rgba(15,23,42,0.4)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: "#FFFFFF",
    borderTopLeftRadius: Radius.card,
    borderTopRightRadius: Radius.card,
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 24,
    maxHeight: "70%",
  },
  sheetHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 8,
  },
  sheetTitle: { fontSize: 16, fontWeight: "800", color: Colors.primary },
  sheetEmpty: { fontSize: 13, color: Colors.mutedForeground, paddingVertical: 16 },
  sheetList: { gap: 8 },
  sheetRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    padding: 14,
    borderRadius: Radius.field,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  sheetRowActive: { borderColor: Colors.accent, backgroundColor: Colors.accentLight },
  sheetRowDead: { opacity: 0.55 },
  sheetRowText: { flex: 1, minWidth: 0 },
  sheetRowName: { fontSize: 14, fontWeight: "700", color: Colors.foreground },
  sheetRowMeta: { fontSize: 11, color: Colors.mutedForeground, marginTop: 2 },
});
