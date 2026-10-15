// Notice card (shared by Home preview and the Notices page); attachments download & share.
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Feather } from "@expo/vector-icons";
import { fonts } from "@/src/theme";
import { C, Card } from "@/src/ui/kit";
import { useBrand } from "@/src/state/auth";
import { useToast } from "@/src/state/toast";
import { fmtDate } from "@/src/lib/format";
import { openAuthedFile } from "@/src/lib/files";

export function NoticeCard({ n, compact, testID }: { n: any; compact?: boolean; testID?: string }) {
  const b = useBrand();
  const toast = useToast();
  const open = async (a: any, i: number) => {
    try { await openAuthedFile(`/notices/attachment/${n.id}/${i}`, a.name || `notice-${i}`, a.content_type || "application/octet-stream"); }
    catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <Card testID={testID} style={{ gap: 6 }}>
      <View style={s.top}>
        <View style={[s.dot, { backgroundColor: b.soft }]}><Feather name="bell" size={16} color={b.ink} /></View>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>{n.title}</Text>
          <Text style={s.date}>{fmtDate(n.created_at)}{n.author_name ? ` · ${n.author_name}` : ""}</Text>
        </View>
      </View>
      {n.body ? <Text style={s.body} numberOfLines={compact ? 2 : undefined}>{n.body}</Text> : null}
      {!compact && (n.attachments || []).map((a: any, i: number) => (
        <Pressable key={i} onPress={() => open(a, i)} style={s.file} testID={`${testID}-file-${i}`}>
          <Feather name="paperclip" size={15} color={b.ink} />
          <Text style={[s.fileText, { color: b.ink }]} numberOfLines={1}>{a.name || "Attachment"}</Text>
          <Feather name="download" size={15} color={b.ink} />
        </Pressable>
      ))}
      {compact && n.attachments?.length ? <Text style={s.date}>{n.attachments.length} attachment{n.attachments.length > 1 ? "s" : ""}</Text> : null}
    </Card>
  );
}

const s = StyleSheet.create({
  top: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  dot: { width: 36, height: 36, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.bodyBold, fontSize: 16, color: C.onSurface },
  date: { fontFamily: fonts.body, fontSize: 13, color: C.muted, marginTop: 1 },
  body: { fontFamily: fonts.body, fontSize: 15, color: C.onSurfaceSecondary, lineHeight: 21, marginLeft: 48 },
  file: { flexDirection: "row", alignItems: "center", gap: 8, marginLeft: 48, minHeight: 44, paddingHorizontal: 12, borderRadius: 12, backgroundColor: C.surfaceTertiary },
  fileText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 14 },
});
