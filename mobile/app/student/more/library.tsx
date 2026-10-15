import { StyleSheet, Text, View } from "react-native";
import { useLibrary } from "@/src/lib/queries";
import { useToast } from "@/src/state/toast";
import { useBrand } from "@/src/state/auth";
import { openAuthedFile } from "@/src/lib/files";
import { StackScreen } from "@/src/ui/Screen";
import { Button, C, Card, Empty, ErrorState, SkeletonList, k } from "@/src/ui/kit";
import { fonts } from "@/src/theme";

export default function Library() {
  const q = useLibrary();
  const toast = useToast();
  const b = useBrand();
  const subjects = q.data?.subjects || [];
  const open = (m: any) => openAuthedFile(`/ai/items/${m.id}/file`, m.file_name || "material", "application/octet-stream").catch((e) => toast(e.message, "error"));
  return (
    <StackScreen title="Library" testID="student-library-screen">
      {q.data?.class_name ? <Text style={k.small}>Approved materials for {q.data.class_name}</Text> : null}
      {q.isLoading ? <SkeletonList n={3} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !subjects.length ? (
        <Card><Empty icon="book" text="No materials available yet." testID="student-library-empty" /></Card>
      ) : subjects.map((sub: any) => (
        <Card key={sub.curriculum_id} style={{ gap: 12 }} testID={`student-library-${sub.subject}`}>
          <Text style={k.h2}>{sub.subject}</Text>
          {sub.chapters.map((ch: any) => (
            <View key={ch.chapter} style={{ gap: 8 }}>
              <Text style={[s.chapter, { color: b.ink }]}>{ch.chapter}</Text>
              {ch.materials.map((m: any) => (
                <View key={m.id} style={s.item} testID={`student-library-item-${m.id}`}>
                  <View style={{ flex: 1, gap: 2 }}>
                    <Text style={s.type}>{String(m.item_type || "").replace(/_/g, " ")}</Text>
                    <Text style={s.title}>{m.title || m.topic}</Text>
                    {m.contributor_name ? <Text style={k.small}>{m.contributor_name}</Text> : null}
                  </View>
                  {m.has_file && <Button small variant="outline" icon="download" label="Open" onPress={() => open(m)} testID={`student-library-open-${m.id}`} />}
                </View>
              ))}
            </View>
          ))}
        </Card>
      ))}
    </StackScreen>
  );
}

const s = StyleSheet.create({
  chapter: { fontFamily: fonts.bodyBold, fontSize: 15 },
  item: { flexDirection: "row", alignItems: "center", gap: 10, padding: 12, borderRadius: 14, backgroundColor: C.surfaceTertiary },
  type: { fontFamily: fonts.bodyBold, fontSize: 11, color: C.muted, textTransform: "uppercase", letterSpacing: 0.6 },
  title: { fontFamily: fonts.bodySemi, fontSize: 15, color: C.onSurface },
});
