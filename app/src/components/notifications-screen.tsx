/**
 * Shared notifications inbox screen (mobile) — counterpart of the website's
 * fontend/components/notifications/notifications-page.tsx. Mounted by each
 * console under its own group route: (student)/notifications,
 * (teacher)/notifications and (parent)/notifications.
 *
 * Uses the app's standard data primitives (useResource + AsyncState) and the
 * shared badge store: after a read mutation the screen re-syncs the bell.
 */

import { useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { CheckCheck } from "lucide-react-native";

import { AsyncState } from "@/components/principal-ui";
import { Screen } from "@/components/screen";
import { Card, EmptyState, PageHeader } from "@/components/ui";
import { requestUnreadRefresh } from "@/hooks/use-unread-notifications";
import { useResource } from "@/hooks/use-resource";
import { timeAgo } from "@/lib/format";
import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type AppNotificationRow,
} from "@/lib/notifications";
import { Colors } from "@/theme";

export function NotificationsScreen() {
  const resource = useResource(() => fetchNotifications({ limit: 100, offset: 0 }), []);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function markRead(row: AppNotificationRow) {
    if (row.is_read || busyId) return;
    setBusyId(row.id);
    setActionError(null);
    try {
      const updated = await markNotificationRead(row.id);
      if (resource.data) {
        resource.setData({
          ...resource.data,
          unread_count: Math.max(0, resource.data.unread_count - 1),
          items: resource.data.items.map((item) =>
            item.id === row.id ? { ...item, ...updated, is_read: true } : item,
          ),
        });
        requestUnreadRefresh();
      }
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Could not mark this notification as read.");
    } finally {
      setBusyId(null);
    }
  }

  async function markAll() {
    if (!resource.data?.unread_count) return;
    setActionError(null);
    try {
      const updatedCount = await markAllNotificationsRead();
      if (resource.data) {
        const remainingUnread = Math.max(0, resource.data.unread_count - updatedCount);
        resource.setData({
          ...resource.data,
          unread_count: remainingUnread,
          items: resource.data.items.map((item) => ({
            ...item,
            is_read: true,
            read_at: new Date().toISOString(),
          })),
        });
        requestUnreadRefresh();
      }
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Could not clear your notifications.");
    }
  }

  const unread = resource.data?.unread_count ?? 0;

  return (
    <Screen>
      <PageHeader
        title="Notifications"
        subtitle={unread ? `${unread} unread` : "You're all caught up"}
        action={
          unread > 0 ? (
            <TouchableOpacity accessibilityRole="button" onPress={() => void markAll()} style={styles.markAll}>
              <CheckCheck size={14} color={Colors.accent} />
              <Text style={styles.markAllText}>Mark all read</Text>
            </TouchableOpacity>
          ) : undefined
        }
      />
      {actionError ? <Text style={styles.actionError}>{actionError}</Text> : null}
      <AsyncState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
        loadingLabel="Loading notifications…"
      >
        {resource.data && resource.data.items.length === 0 ? (
          <EmptyState text="No notifications yet — notices, class alerts and results will show up here and on your devices." />
        ) : resource.data ? (
          <View style={styles.list}>
            {resource.data.items.map((row) => (
              <TouchableOpacity
                key={row.id}
                accessibilityRole={row.is_read ? undefined : "button"}
                accessibilityLabel={row.is_read ? undefined : "Mark as read"}
                activeOpacity={row.is_read ? 1 : 0.7}
                disabled={row.is_read || busyId === row.id}
                onPress={() => void markRead(row)}
              >
                <Card style={[styles.card, !row.is_read && styles.cardUnread]}>
                  <View style={[styles.dot, row.is_read && styles.dotRead]} />
                  <View style={styles.cardBody}>
                    <View style={styles.cardTitleRow}>
                      <Text style={[styles.cardTitle, row.is_read && styles.cardTitleRead]} numberOfLines={2}>
                        {row.title}
                      </Text>
                      <Text style={styles.cardTime}>{timeAgo(row.created_at)}</Text>
                    </View>
                    {row.body ? (
                      <Text style={styles.cardBodyText} numberOfLines={3}>
                        {row.body}
                      </Text>
                    ) : null}
                  </View>
                </Card>
              </TouchableOpacity>
            ))}
          </View>
        ) : null}
      </AsyncState>
      {resource.data && resource.data.total > resource.data.items.length ? (
        <Text style={styles.moreHint}>Showing the latest {resource.data.items.length}</Text>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: 10,
  },
  markAll: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: "#FFFFFF",
  },
  markAllText: {
    fontSize: 12,
    fontWeight: "600",
    color: Colors.accent,
  },
  actionError: {
    color: Colors.destructiveText,
    fontSize: 12,
    marginBottom: 8,
  },
  card: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
  },
  cardUnread: {
    borderColor: Colors.accentBorder,
    backgroundColor: Colors.accentLight,
  },
  dot: {
    marginTop: 5,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.accent,
  },
  dotRead: {
    backgroundColor: "transparent",
  },
  cardBody: {
    flex: 1,
    gap: 2,
  },
  cardTitleRow: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: 8,
  },
  cardTitle: {
    flex: 1,
    fontSize: 14,
    fontWeight: "600",
    color: Colors.foreground,
  },
  cardTitleRead: {
    fontWeight: "500",
    color: Colors.mutedForeground,
  },
  cardTime: {
    fontSize: 11,
    color: Colors.mutedForeground,
  },
  cardBodyText: {
    fontSize: 13,
    lineHeight: 18,
    color: Colors.mutedForeground,
  },
  moreHint: {
    marginTop: 12,
    textAlign: "center",
    fontSize: 12,
    color: Colors.mutedForeground,
  },
});
