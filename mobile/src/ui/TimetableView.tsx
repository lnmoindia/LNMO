import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { StackScreen, TabScreen } from "./Screen";
import { Card, Chip, Empty, ErrorState, SkeletonList, k } from "./kit";
import { PeriodRow, TodayChanges, coverFor, dayRows, nowNext, ttDay } from "@/src/parent/timetable";
import { DAY_LONG, DAY_SHORT } from "@/src/lib/format";

export function TimetableView({ tt, ready = true, testID, stack }: { tt: any; ready?: boolean; testID: string; stack?: boolean }) {
  const Shell: any = stack ? StackScreen : TabScreen;
  const [mode, setMode] = useState<"today" | "week">("today");
  const today = ttDay(tt.data);
  const days: string[] = tt.data?.config?.working_days || [];
  const [day, setDay] = useState(today);
  useEffect(() => { setDay(days.includes(today) ? today : days[0] || today); }, [today, days.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const shown = mode === "today" ? today : day;
  const rows = dayRows(tt.data, shown);
  const working = days.includes(shown);
  const hasAny = rows.some((r: any) => r.e);
  const nn = shown === today ? nowNext(rows) : null;
  return (
    <Shell testID={testID} title="Timetable">
      <View style={s.seg} testID="timetable-mode">
        <Chip label="Today" active={mode === "today"} onPress={() => setMode("today")} testID="timetable-mode-today" />
        <Chip label="Week" active={mode === "week"} onPress={() => setMode("week")} testID="timetable-mode-week" />
        {tt.data?.class_name ? <Text style={[k.small, { marginLeft: "auto" }]}>{tt.data.class_name} {tt.data.section || ""}</Text> : null}
      </View>
      {mode === "week" && days.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} testID="timetable-day-picker">
          {days.map((d) => <Chip key={d} label={d === today ? `${DAY_SHORT[d]} · today` : DAY_SHORT[d]} active={d === day} onPress={() => setDay(d)} testID={`timetable-day-${d}`} />)}
        </ScrollView>
      )}
      {tt.isLoading || !ready ? <SkeletonList n={4} height={72} /> : tt.isError ? <ErrorState error={tt.error} onRetry={tt.refetch} /> : !tt.data?.config || !tt.data.entries?.length ? (
        <Card><Empty icon="calendar" title="Not published yet" text="The timetable hasn't been published yet." /></Card>
      ) : (
        <>
          <Text style={k.h2}>{DAY_LONG[shown]}{shown === today ? " · Today" : ""}</Text>
          {shown === today && <TodayChanges changes={tt.data.today_changes} testID="timetable-today-changes" />}
          {!working || !hasAny ? <Card><Empty icon="coffee" text="No classes on this day." /></Card> : (
            <View style={{ gap: 10 }} testID="timetable-periods">
              {rows.map((r: any) => (
                <PeriodRow key={r.pno} p={r.p} e={r.e} cover={coverFor(tt.data.today_changes, shown, r.pno)}
                  now={nn?.pno === r.pno} tag={nn?.pno === r.pno ? nn.tag : undefined} testID={`timetable-${shown}-p${r.pno}`} />
              ))}
            </View>
          )}
        </>
      )}
    </Shell>
  );
}

const s = StyleSheet.create({
  seg: { flexDirection: "row", gap: 8, alignItems: "center" },
});
