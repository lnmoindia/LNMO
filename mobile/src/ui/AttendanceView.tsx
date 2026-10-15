import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Feather } from "@expo/vector-icons";
import { useChild } from "@/src/state/child";
import { useBrand } from "@/src/state/auth";
import { useAttendance } from "@/src/lib/queries";
import { StackScreen } from "./Screen";
import { C, Card, ErrorState, k } from "./kit";
import { MONTHS_LONG, todayISO } from "@/src/lib/format";
import { fonts } from "@/src/theme";

const DOW = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const TONE: Record<string, [string, string]> = {
  present: ["#10B981", "#fff"], absent: ["#F43F5E", "#fff"], late: ["#FBBF24", "#451A03"], leave: ["#38BDF8", "#fff"], holiday: ["#E2E8F0", "#64748B"],
};

export function AttendanceView({ useData, testID }: { useData: (month: string) => any; testID: string }) {
  const b = useBrand();
  const [cur, setCur] = useState(() => { const [y, m] = todayISO().split("-").map(Number); return { y, m }; });
  const month = `${cur.y}-${String(cur.m).padStart(2, "0")}`;
  const q = useData(month);
  const d = q.data;
  const shift = (n: number) => setCur((c) => { const t = c.y * 12 + (c.m - 1) + n; return { y: Math.floor(t / 12), m: (t % 12) + 1 }; });
  const lead = (new Date(Date.UTC(cur.y, cur.m - 1, 1)).getUTCDay() + 6) % 7;
  const n = new Date(Date.UTC(cur.y, cur.m, 0)).getUTCDate();
  const byDate = Object.fromEntries((d?.days || []).map((x: any) => [x.date, x.status]));
  const today = todayISO();
  const cells: (number | null)[] = [...Array(lead).fill(null), ...Array.from({ length: n }, (_, i) => i + 1)];
  while (cells.length % 7) cells.push(null);
  return (
    <StackScreen title="Attendance" testID={testID}>
      <View style={s.stats}>
        <Stat label="This month" pct={d?.month_pct} sub={d ? `${d.month_present}/${d.month_total} days present` : ""} testID="attendance-month-pct" />
        <Stat label="This year" pct={d?.year_pct} sub={d ? `${d.year_present}/${d.year_total} days present` : ""} testID="attendance-year-pct" />
      </View>
      {q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : (
        <Card style={{ gap: 12 }} testID="attendance-calendar">
          <View style={s.head}>
            <Pressable onPress={() => shift(-1)} style={s.nav} testID="attendance-prev-month" hitSlop={6}><Feather name="chevron-left" size={22} color={C.onSurface} /></Pressable>
            <Text style={k.h2} testID="attendance-month-label">{MONTHS_LONG[cur.m - 1]} {cur.y}</Text>
            <Pressable onPress={() => shift(1)} style={s.nav} testID="attendance-next-month" hitSlop={6}><Feather name="chevron-right" size={22} color={C.onSurface} /></Pressable>
          </View>
          <View style={s.week}>{DOW.map((x) => <Text key={x} style={s.dow}>{x.slice(0, 2).toUpperCase()}</Text>)}</View>
          <View style={[s.grid, !d && { opacity: 0.4 }]}>
            {cells.map((day, i) => {
              if (!day) return <View key={`e${i}`} style={s.cell} />;
              const date = `${month}-${String(day).padStart(2, "0")}`;
              const st = byDate[date] || (d && !d.working_days.includes(DOW[i % 7]) ? "holiday" : null);
              const [bg, fg] = st ? TONE[st] || TONE.present : [C.surfaceTertiary, C.muted];
              return (
                <View key={date} style={s.cell} testID={`attendance-day-${date}`}>
                  <View style={[s.day, { backgroundColor: bg }, date === today && { borderWidth: 2, borderColor: b.ink }]}>
                    <Text style={[s.dayText, { color: fg }]}>{day}</Text>
                  </View>
                </View>
              );
            })}
          </View>
          <View style={s.legend}>
            {[["present", "Present"], ["absent", "Absent"], ["late", "Late"], ["holiday", "No school"]].map(([key, l]) => (
              <View key={key} style={s.lItem}><View style={[s.lDot, { backgroundColor: TONE[key][0] }]} /><Text style={k.small}>{l}</Text></View>
            ))}
            <View style={s.lItem}><View style={[s.lDot, { backgroundColor: C.surfaceTertiary, borderWidth: 1, borderColor: C.border }]} /><Text style={k.small}>Not marked</Text></View>
          </View>
        </Card>
      )}
    </StackScreen>
  );
}

const Stat = ({ label, pct, sub, testID }: { label: string; pct?: number; sub: string; testID: string }) => (
  <Card style={{ flex: 1, gap: 2 }} testID={testID}>
    <Text style={s.statLabel}>{label}</Text>
    <Text style={s.statVal}>{pct == null ? "—" : `${pct}%`}</Text>
    <Text style={k.small}>{sub || " "}</Text>
  </Card>
);

const s = StyleSheet.create({
  stats: { flexDirection: "row", gap: 12 },
  statLabel: { fontFamily: fonts.bodyBold, fontSize: 12, color: C.muted, textTransform: "uppercase", letterSpacing: 0.6 },
  statVal: { fontFamily: fonts.heading, fontSize: 28, color: C.onSurface },
  head: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  nav: { width: 44, height: 44, borderRadius: 14, borderWidth: 1, borderColor: C.border, alignItems: "center", justifyContent: "center" },
  week: { flexDirection: "row" },
  dow: { flex: 1, textAlign: "center", fontFamily: fonts.bodyBold, fontSize: 11, color: C.muted },
  grid: { flexDirection: "row", flexWrap: "wrap" },
  cell: { width: `${100 / 7}%`, aspectRatio: 1, padding: 3 },
  day: { flex: 1, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  dayText: { fontFamily: fonts.bodyBold, fontSize: 14 },
  legend: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  lItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  lDot: { width: 12, height: 12, borderRadius: 4 },
});
