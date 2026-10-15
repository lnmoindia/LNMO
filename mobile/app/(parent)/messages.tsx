import { useCallback } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useQueryClient } from "@tanstack/react-query";
import { useChild } from "@/src/state/child";
import { useBrand } from "@/src/state/auth";
import { useThreads } from "@/src/lib/queries";
import { useChatSocket } from "@/src/lib/chat";
import { TabScreen } from "@/src/ui/Screen";
import { Button, C, Card, Empty, ErrorState, SkeletonList, k } from "@/src/ui/kit";
import { LiveBadge } from "@/src/parent/LiveBadge";
import { fmtDateTime } from "@/src/lib/format";
import { fonts } from "@/src/theme";

export default function Messages() {
  const { children, child, childId } = useChild();
  const qc = useQueryClient();
  const onEv = useCallback((ev: any) => {
    if (ev.type === "unread" || ev.type === "message") {
      qc.invalidateQueries({ queryKey: ["threads"] });
      qc.invalidateQueries({ queryKey: ["unread"] });
    }
  }, [qc]);
  const live = useChatSocket(onEv);
  const q = useThreads(live !== "live", childId);
  const many = (children?.length || 0) > 1;
  return (
    <TabScreen testID="messages-screen" title="Messages">
      {many && child && <Text style={k.small} testID="messages-child-filter">Showing messages about {child.first_name} · switch child at the top</Text>}
      <View style={s.top}>
        <LiveBadge status={live} />
        <Button small label="New message" icon="edit" onPress={() => router.push("/new-message")} disabled={!children?.length} testID="messages-new-btn" />
      </View>
      {q.isLoading ? <SkeletonList n={3} height={76} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !q.data?.threads?.length ? (
        <Card><Empty icon="message-circle" title={many ? `No messages about ${child?.first_name || "this child"} yet` : "No messages yet"} text="Write to your child's class teacher or the school office." testID="messages-empty" /></Card>
      ) : (
        <Card style={{ padding: 0 }} testID="messages-thread-list">
          {q.data.threads.map((t: any, i: number) => <ThreadRow key={t.id} t={t} last={i === q.data.threads.length - 1} />)}
        </Card>
      )}
    </TabScreen>
  );
}

function ThreadRow({ t, last }: { t: any; last: boolean }) {
  const b = useBrand();
  const office = t.target === "office";
  return (
    <Pressable onPress={() => router.push(`/thread/${t.id}`)} testID={`messages-thread-${t.id}`}
      style={({ pressed }) => [s.row, !last && s.line, pressed && { backgroundColor: C.surfaceTertiary }]}>
      <View style={[s.icon, { backgroundColor: b.soft }]}><Feather name={office ? "briefcase" : "user"} size={20} color={b.ink} /></View>
      <View style={{ flex: 1, gap: 2 }}>
        <View style={s.titleRow}>
          <Text style={[s.title, t.unread ? { fontFamily: fonts.bodyBold, color: C.onSurface } : null]} numberOfLines={1}>
            {office ? "School office" : "Class teacher"} · {t.student_name}
          </Text>
          <Text style={k.small}>{fmtDateTime(t.last_message_at || t.created_at)}</Text>
        </View>
        {t.subject ? <Text style={s.subject} numberOfLines={1}>{t.subject}</Text> : null}
        <View style={s.titleRow}>
          <Text style={[k.small, { flex: 1 }]} numberOfLines={1}>{t.last_message_preview || "—"}{t.status === "closed" ? " · closed" : ""}</Text>
          {t.unread > 0 && <View style={s.badge} testID={`messages-thread-unread-${t.id}`}><Text style={s.badgeText}>{t.unread}</Text></View>}
        </View>
      </View>
    </Pressable>
  );
}

const s = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  row: { flexDirection: "row", gap: 12, padding: 16, alignItems: "center", minHeight: 76 },
  line: { borderBottomWidth: 1, borderBottomColor: C.divider },
  icon: { width: 44, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 8, justifyContent: "space-between" },
  title: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 15, color: C.onSurfaceSecondary },
  subject: { fontFamily: fonts.bodyMedium, fontSize: 13, color: C.onSurfaceTertiary },
  badge: { minWidth: 22, height: 22, borderRadius: 11, paddingHorizontal: 6, backgroundColor: C.error, alignItems: "center", justifyContent: "center" },
  badgeText: { fontFamily: fonts.bodyBold, fontSize: 12, color: "#fff" },
});
