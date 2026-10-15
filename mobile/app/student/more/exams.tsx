import { StyleSheet, Text, View } from "react-native";
import { useMyExams } from "@/src/lib/queries";
import { StackScreen } from "@/src/ui/Screen";
import { C, Card, Empty, ErrorState, SectionTitle, SkeletonList, k } from "@/src/ui/kit";
import { useBrand } from "@/src/state/auth";
import { daysUntil, fmtDate, fmtTime, todayISO } from "@/src/lib/format";
import { fonts } from "@/src/theme";

export default function Exams() {
  const q = useMyExams();
  const b = useBrand();
  const up = (q.data || []).filter((x: any) => x.date >= todayISO()).sort((a: any, c: any) => a.date.localeCompare(c.date));
  const groups: Record<string, any[]> = {};
  up.forEach((x: any) => { (groups[x.exam_name] = groups[x.exam_name] || []).push(x); });
  return (
    <StackScreen title="Exams" testID="student-exams-screen">
      {q.isLoading ? <SkeletonList n={3} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !up.length ? (
        <Card><Empty icon="calendar" title="No exams coming up" text="Upcoming exams will appear here once the school schedules them." testID="student-exams-empty" /></Card>
      ) : Object.entries(groups).map(([name, rows]) => (
        <View key={name} style={{ gap: 10 }} testID={`student-exam-group-${name}`}>
          <SectionTitle title={name} />
          {rows.map((x, i) => {
            const d = daysUntil(x.date);
            return (
              <Card key={i} style={[s.row, x.status === "postponed" && { backgroundColor: C.warningSoft }]} testID={`student-exam-${x.subject}`}>
                <View style={[s.date, { backgroundColor: b.soft }]}>
                  <Text style={[s.day, { color: b.ink }]}>{x.date.slice(8, 10)}</Text>
                  <Text style={[s.mon, { color: b.ink }]}>{fmtDate(x.date, { year: false }).split(" ")[1]}</Text>
                </View>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={s.subject}>{x.subject}</Text>
                  <Text style={k.small}>{fmtDate(x.date, { weekday: true, year: false }).split(",")[0]} · {fmtTime(x.start)}–{fmtTime(x.end)}{x.room ? ` · ${x.room}` : ""}</Text>
                  {x.status === "postponed" && <Text style={[k.small, { color: C.warning }]}>Postponed</Text>}
                </View>
                <Text style={s.count}>{d === 0 ? "Today" : d === 1 ? "Tomorrow" : `in ${d}d`}</Text>
              </Card>
            );
          })}
        </View>
      ))}
    </StackScreen>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: 14 },
  date: { width: 56, height: 56, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  day: { fontFamily: fonts.heading, fontSize: 20, lineHeight: 22 },
  mon: { fontFamily: fonts.bodyBold, fontSize: 12 },
  subject: { fontFamily: fonts.bodyBold, fontSize: 16, color: C.onSurface },
  count: { fontFamily: fonts.bodyBold, fontSize: 13, color: C.muted },
});
