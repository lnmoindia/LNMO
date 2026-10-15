import { StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useMe } from "@/src/lib/queries";
import { StackScreen } from "@/src/ui/Screen";
import { C, Card, Empty, Field, SkeletonList, k } from "@/src/ui/kit";
import { useBrand } from "@/src/state/auth";
import { fmtDate } from "@/src/lib/format";
import { fonts } from "@/src/theme";

export default function SubjectDetail() {
  const { name } = useLocalSearchParams<{ name: string }>();
  const q = useMe();
  const b = useBrand();
  const info = (q.data?.subjects || []).find((x: any) => x.subject === name);
  const rows = (q.data?.results || []).filter((r: any) => r.subject === name)
    .sort((a: any, c: any) => String(a.created_at || "").localeCompare(String(c.created_at || "")));
  const pcts = rows.filter((r: any) => r.score != null && r.max_marks).map((r: any) => Math.round((r.score / r.max_marks) * 100));
  const avg = pcts.length ? Math.round(pcts.reduce((a: number, c: number) => a + c, 0) / pcts.length) : null;
  return (
    <StackScreen title={name} testID="student-subject-screen">
      {q.isLoading ? <SkeletonList n={2} /> : (
        <>
          <Card style={s.top} testID="student-subject-summary">
            <View style={{ flex: 1 }}>
              <Field label="Teacher" value={info?.teacher_name} />
              <Field label="Assessments" value={String(rows.length)} />
            </View>
            <View style={[s.avg, { backgroundColor: b.soft }]}>
              <Text style={[s.avgNum, { color: b.ink }]}>{avg == null ? "—" : `${avg}%`}</Text>
              <Text style={[k.small, { color: b.ink }]}>average</Text>
            </View>
          </Card>
          {!rows.length ? <Card><Empty icon="award" text="No published results for this subject yet." /></Card> : rows.map((r: any, i: number) => {
            const p = r.max_marks && r.score != null ? Math.round((r.score / r.max_marks) * 100) : null;
            return (
              <Card key={i} style={{ gap: 8 }} testID={`student-subject-result-${i}`}>
                <View style={s.row}>
                  <View style={{ flex: 1 }}><Text style={s.name} numberOfLines={2}>{r.assessment}</Text>{r.date ? <Text style={k.small}>{fmtDate(r.date)}</Text> : null}</View>
                  <Text style={s.score}>{r.score ?? "—"}<Text style={k.small}>{r.max_marks ? ` / ${r.max_marks}` : ""}</Text></Text>
                </View>
                {p != null && <View style={s.track}><View style={[s.fill, { width: `${p}%`, backgroundColor: b.color }]} /></View>}
              </Card>
            );
          })}
        </>
      )}
    </StackScreen>
  );
}

const s = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", gap: 12 },
  avg: { width: 96, height: 96, borderRadius: 24, alignItems: "center", justifyContent: "center" },
  avgNum: { fontFamily: fonts.heading, fontSize: 26 },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  name: { fontFamily: fonts.bodySemi, fontSize: 15, color: C.onSurface },
  score: { fontFamily: fonts.heading, fontSize: 20, color: C.onSurface },
  track: { height: 8, borderRadius: 4, backgroundColor: C.surfaceTertiary, overflow: "hidden" },
  fill: { height: 8, borderRadius: 4 },
});
