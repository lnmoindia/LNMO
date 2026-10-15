import { StyleSheet, Text, View } from "react-native";
import { useChild } from "@/src/state/child";
import { useExams, useSnap } from "@/src/lib/queries";
import { StackScreen } from "@/src/ui/Screen";
import { C, Card, Empty, ErrorState, SectionTitle, SkeletonList, k } from "@/src/ui/kit";
import { fmtDate, fmtTime, todayISO } from "@/src/lib/format";
import { fonts } from "@/src/theme";
import { Trends } from "@/src/parent/Trends";

export default function Results() {
  const { childId } = useChild();
  const snap = useSnap(childId);
  const exams = useExams(childId);
  const today = todayISO();
  const upcoming = (exams.data || []).filter((x: any) => x.date >= today);
  const results = snap.data?.results || [];
  return (
    <StackScreen title="Results" testID="results-screen">
      <SectionTitle title="Upcoming exams" />
      {exams.isLoading ? <SkeletonList n={1} /> : !upcoming.length ? <Card><Empty icon="calendar" text="No exams scheduled right now." testID="results-no-exams" /></Card> : (
        upcoming.map((x: any, i: number) => (
          <Card key={i} style={[s.exam, x.status === "postponed" && { backgroundColor: C.warningSoft }]} testID={`results-exam-${i}`}>
            <View style={{ flex: 1 }}><Text style={s.tSub}>{x.subject}</Text><Text style={k.small}>{x.exam_name}{x.room ? ` · ${x.room}` : ""}{x.status === "postponed" ? " · postponed" : ""}</Text></View>
            <View style={{ alignItems: "flex-end" }}><Text style={s.tSub}>{fmtDate(x.date, { weekday: true, year: false })}</Text><Text style={k.small}>{fmtTime(x.start)}–{fmtTime(x.end)}</Text></View>
          </Card>
        ))
      )}
      {snap.isLoading ? <SkeletonList n={2} /> : snap.isError ? <ErrorState error={snap.error} onRetry={snap.refetch} /> : (
        <>
          {results.length > 0 && <SectionTitle title="Score trends" />}
          <Trends results={results} />
          <SectionTitle title="Results" />
          {!results.length ? <Card><Empty icon="award" text="No published results yet — they appear here once the school publishes them." testID="results-empty" /></Card> : (
            <Card style={{ padding: 0 }} testID="results-list">
              {results.map((r: any, i: number) => (
                <View key={i} style={[s.res, i < results.length - 1 && s.line]}>
                  <View style={{ flex: 1 }}><Text style={s.tSub}>{r.subject || "—"}</Text><Text style={k.small} numberOfLines={2}>{r.assessment}</Text></View>
                  <Text style={s.score}>{r.score ?? "—"}{r.max_marks ? <Text style={k.small}> / {r.max_marks}</Text> : null}</Text>
                </View>
              ))}
            </Card>
          )}
        </>
      )}
    </StackScreen>
  );
}

const s = StyleSheet.create({
  tRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  tSub: { fontFamily: fonts.bodyBold, fontSize: 15, color: C.onSurface },
  bars: { flexDirection: "row", alignItems: "flex-end", gap: 4, height: 38 },
  bar: { width: 9, borderRadius: 3 },
  tPct: { fontFamily: fonts.heading, fontSize: 17 },
  delta: { fontFamily: fonts.bodyBold, fontSize: 11 },
  exam: { flexDirection: "row", alignItems: "center", gap: 12 },
  res: { flexDirection: "row", alignItems: "center", gap: 12, padding: 16, minHeight: 64 },
  line: { borderBottomWidth: 1, borderBottomColor: C.divider },
  score: { fontFamily: fonts.heading, fontSize: 18, color: C.onSurface },
});
