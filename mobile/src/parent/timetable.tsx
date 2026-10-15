// Timetable pieces shared by Home and the Timetable tab (same rules as the web portal).
import { StyleSheet, Text, View } from "react-native";
import { Feather } from "@expo/vector-icons";
import { fonts } from "@/src/theme";
import { C } from "@/src/ui/kit";
import { useBrand } from "@/src/state/auth";
import { fmtTime, minutesNow, toMin, todayKey } from "@/src/lib/format";

export const ttDay = (tt: any) => tt?.today_changes?.day || todayKey();
export const coverFor = (changes: any, day: string, pno: number) =>
  changes && changes.day === day ? (changes.items || []).find((i: any) => i.period_no === pno) : null;

// All periods for a day (breaks included) with the entry for each teaching period.
export const dayRows = (tt: any, day: string) => {
  if (!tt?.config) return [];
  return tt.config.periods.map((p: any, i: number) => ({ p, pno: i + 1, e: p.is_break ? null : (tt.entries || []).find((x: any) => x.day === day && x.period_no === i + 1) }));
};
export const todayClasses = (tt: any) => dayRows(tt, ttDay(tt)).filter((r: any) => r.e);

// Current period (start <= now < end) else the next one today → { pno, tag }
export const nowNext = (rows: any[]) => {
  const m = minutesNow();
  const cur = rows.find((r) => r.e && toMin(r.p.start) <= m && m < toMin(r.p.end));
  if (cur) return { pno: cur.pno, tag: "Now" };
  const nxt = rows.find((r) => r.e && toMin(r.p.start) > m);
  return nxt ? { pno: nxt.pno, tag: "Next" } : null;
};

export function CoverBadge({ item, testID }: { item: any; testID?: string }) {
  if (!item) return null;
  const sub = item.kind === "substitute";
  return (
    <View style={[s.badge, { backgroundColor: sub ? C.warningSoft : C.errorSoft }]} testID={testID}>
      <Feather name={sub ? "user-check" : "user-x"} size={12} color={sub ? C.warning : C.error} />
      <Text style={[s.badgeText, { color: sub ? C.warning : C.error }]}>
        {sub ? `Substitute: ${item.substitute_name}` : "Teacher absent — cover being arranged"}
      </Text>
    </View>
  );
}

export function TodayChanges({ changes, testID = "today-changes" }: { changes: any; testID?: string }) {
  const items = changes?.items || [];
  if (!items.length) return null;
  const subs = items.filter((i: any) => i.kind === "substitute").length;
  const open = items.length - subs;
  const parts: string[] = [];
  if (subs) parts.push(`${subs} period${subs > 1 ? "s have" : " has"} a substitute teacher today`);
  if (open) parts.push(`${open} period${open > 1 ? "s" : ""} awaiting cover`);
  return (
    <View style={s.changes} testID={testID}>
      <Feather name="alert-triangle" size={16} color={C.warning} />
      <Text style={s.changesText}>Today's changes: {parts.join(" · ")}</Text>
    </View>
  );
}

export function PeriodRow({ p, e, cover, now, tag, testID }: { p: any; e: any; cover?: any; now?: boolean; tag?: string; testID?: string }) {
  const b = useBrand();
  if (p.is_break) {
    return (
      <View style={s.break} testID={testID}>
        <View style={s.breakLine} /><Text style={s.breakText}>{p.label} · {fmtTime(p.start)}</Text><View style={s.breakLine} />
      </View>
    );
  }
  return (
    <View style={[s.row, now && { borderColor: b.color, backgroundColor: b.soft }]} testID={testID}>
      <View style={s.time}>
        <Text style={[s.pLabel, { color: b.ink }]}>{p.label}</Text>
        <Text style={s.pTime}>{fmtTime(p.start)}</Text>
        {tag ? <View style={[s.tag, { backgroundColor: b.color }]} testID={testID ? `${testID}-tag` : undefined}><Text style={[s.tagText, { color: b.onColor }]}>{tag}</Text></View> : null}
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        {e ? (
          <>
            <Text style={s.subject}>{e.subject}{e.type === "lab" ? " · Lab" : ""}</Text>
            <Text style={s.teacher}>{e.teacher_name}{e.room ? ` · ${e.room}` : ""}</Text>
            <CoverBadge item={cover} testID={testID ? `${testID}-cover` : undefined} />
          </>
        ) : <Text style={s.free}>Free period</Text>}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  badge: { flexDirection: "row", alignItems: "center", gap: 5, alignSelf: "flex-start", paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999, marginTop: 4 },
  badgeText: { fontFamily: fonts.bodyBold, fontSize: 12 },
  changes: { flexDirection: "row", gap: 10, alignItems: "flex-start", padding: 14, borderRadius: 16, backgroundColor: C.warningSoft },
  changesText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 14, color: "#7C3E06", lineHeight: 20 },
  row: { flexDirection: "row", gap: 14, alignItems: "flex-start", padding: 14, borderRadius: 18, backgroundColor: C.surfaceSecondary, borderWidth: 1, borderColor: C.border },
  time: { width: 62 },
  pLabel: { fontFamily: fonts.heading, fontSize: 16 },
  pTime: { fontFamily: fonts.body, fontSize: 12, color: C.muted, marginTop: 1 },
  subject: { fontFamily: fonts.bodyBold, fontSize: 16, color: C.onSurface },
  teacher: { fontFamily: fonts.body, fontSize: 14, color: C.muted },
  tag: { alignSelf: "flex-start", paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, marginTop: 4 },
  tagText: { fontFamily: fonts.bodyBold, fontSize: 11 },
  free: { fontFamily: fonts.bodyMedium, fontSize: 15, color: C.muted, paddingTop: 2 },
  break: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 2 },
  breakLine: { flex: 1, height: 1, backgroundColor: C.border },
  breakText: { fontFamily: fonts.bodySemi, fontSize: 12, color: C.muted, letterSpacing: 0.5, textTransform: "uppercase" },
});
