/**
 * Header notification bell with unread badge (mobile) — counterpart of the
 * bell in the website's InstitutionConsoleShell. One shared component used by
 * the student / teacher / parent shell headers; it opens the current
 * console's /notifications screen and shows the shared unread count.
 */

import { Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { Bell } from "lucide-react-native";

import { useUnreadNotifications } from "@/hooks/use-unread-notifications";
import { Colors } from "@/theme";

export function NotificationBell() {
  const { unread } = useUnreadNotifications();
  const router = useRouter();

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
      hitSlop={8}
      onPress={() => router.push("/notifications" as never)}
      style={styles.bell}
    >
      <Bell size={18} color={Colors.mutedForeground} />
      {unread > 0 ? (
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{unread > 99 ? "99+" : unread}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  bell: {
    marginLeft: "auto",
    padding: 4,
  },
  badge: {
    position: "absolute",
    top: -3,
    right: -7,
    minWidth: 16,
    height: 16,
    borderRadius: 8,
    paddingHorizontal: 3,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: Colors.accent,
  },
  badgeText: {
    color: "#FFFFFF",
    fontSize: 9,
    fontWeight: "700",
  },
});
