import { useCallback, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { useThreads } from "@/src/lib/queries";
import { useChatSocket } from "@/src/lib/chat";
import { TabScreen } from "@/src/ui/Screen";
import { C, Card, Chip, Empty, ErrorState, SkeletonList, k } from "@/src/ui/kit";
import { Avatar } from "@/src/ui/brandbits";
import { LiveBadge } from "@/src/parent/LiveBadge";
import { fmtDateTime } from "@/src/lib/format";
import { fonts } from "@/src/theme";

export default function TeacherMessages() {
  const qc = useQueryClient();
  const onEv = useCallback((ev: any) => {
    if (ev.type === "unread" || ev.type === "message") { qc.invalidateQueries({ queryKey: ["threads"] }); qc.invalidateQueries({ queryKey: ["unread"] }); }
  }, [qc]);
  const live = useChatSocket(onEv);
  const q = useThreads(live !== "live");
  const [cls, setCls] = useState("");
  const all = q.data?.threads || [];
  const classes = [...new Set(all.map((t: any) => `${t.class_name} ${t.section || ""}`.trim()))] as string[];
  const list = all.filter((t: any) => !cls || `${t.class_name} ${t.section || ""}`.trim() === cls)
    .sort((a: any, b: any) => (b.unread > 0 ? 1 : 0) - (a.unread > 0 ? 1 : 0) || String(b.last_message_at).localeCompare(String(a.last_message_at)));
  return (
    <TabScreen testID="teacher-messages-screen" title="Messages" showSwitcher={false}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <LiveBadge status={live} /><Text style={k.small}>Start a chat from More → My class</Text>
      </View>
      {classes.length > 1 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
          <Chip label="All" active={!cls} onPress={() => setCls("")} testID="tmsg-class-all" />
          {classes.map((c) => <Chip key={c} label={c} active={cls === c} onPress={() => setCls(c)} />)}
        </ScrollView>
      )}
      {q.isLoading ? <SkeletonList n={3} height={76} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !list.length ? <Card><Empty icon="message-circle" text="No parent messages yet." /></Card> : (
        <Card style={{ padding: 0 }} testID="tmsg-list">
          {list.map((t: any, i: number) => (
            <Pressable key={t.id} onPress={() => router.push(`/thread/${t.id}`)} style={[s.row, i > 0 && s.line]} testID={`tmsg-thread-${t.id}`}>
              <Avatar name={t.parent_name || "P"} size={42} />
              <View style={{ flex: 1, gap: 2 }}>
                <View style={s.top}><Text style={[s.name, t.unread > 0 && { fontFamily: fonts.bodyBold }]} numberOfLines={1}>{t.parent_name} · {t.student_name}</Text><Text style={k.small}>{fmtDateTime(t.last_message_at)}</Text></View>
                <View style={s.top}>
                  <Text style={[k.small, { flex: 1 }]} numberOfLines={1}>{t.class_name} {t.section} · {t.last_message_preview}{t.status === "closed" ? " · closed" : ""}</Text>
                  {t.unread > 0 && <View style={s.badge}><Text style={s.badgeText}>{t.unread}</Text></View>}
                </View>
              </View>
            </Pressable>
          ))}
        </Card>
      )}
    </TabScreen>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: "row", gap: 12, padding: 14, alignItems: "center", minHeight: 72 },
  line: { borderTopWidth: 1, borderTopColor: C.divider },
  top: { flexDirection: "row", alignItems: "center", gap: 8, justifyContent: "space-between" },
  name: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 15, color: C.onSurface },
  badge: { minWidth: 22, height: 22, borderRadius: 11, paddingHorizontal: 6, backgroundColor: C.error, alignItems: "center", justifyContent: "center" },
  badgeText: { fontFamily: fonts.bodyBold, fontSize: 12, color: "#fff" },
});
