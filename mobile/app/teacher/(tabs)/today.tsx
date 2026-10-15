import { Pressable, StyleSheet, Text, View } from "react-native";
import { router, type Href } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth, useBrand } from "@/src/state/auth";
import { useToast } from "@/src/state/toast";
import { useAttendanceSheet, useMyClass, useMySubs, useTeacherTT, useTeacherWork, useUnread } from "@/src/lib/queries";
import { api } from "@/src/lib/api";
import { TabScreen } from "@/src/ui/Screen";
import { Button, C, Card, Empty, ErrorState, SectionTitle, SkeletonList, k } from "@/src/ui/kit";
import { DAY_SHORT, fmtDate, fmtTime, hourNow, minutesNow, toMin, todayISO, todayKey } from "@/src/lib/format";
import { fonts } from "@/src/theme";

const greet = () => { const h = hourNow(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };

export default function TeacherToday() {
  const { user } = useAuth();
  const today = todayISO();
  const tt = useTeacherTT(user?.id, today);
  const subs = useMySubs();
  const unread = useUnread(true);
  const work = useTeacherWork();
  const homes = useMyClass();
  const home = homes.data?.[0];
  const att = useAttendanceSheet(home?.class_name || "", home?.name || "", today);
  const day = (tt.data?.schedule || []).find((d: any) => d.day === (tt.data?.overlay_day || todayKey()));
  const periods = withCovers(day?.periods || [], subs.data?.assigned || [], today);
  const m = minutesNow();
  const cur = periods.find((p: any) => toMin(p.start) <= m && m < toMin(p.end)) || periods.find((p: any) => toMin(p.start) > m);
  const toReview = (work.data || []).reduce((a: number, x: any) => a + Math.max(0, (x.counts?.submitted || 0) - (x.counts?.verified || 0) - (x.counts?.graded || 0)), 0);
  const alerts: [string, string, string, Href][] = [];
  if (unread.data) alerts.push(["unread", "message-circle", `${unread.data} unread parent message${unread.data > 1 ? "s" : ""}`, "/teacher/messages"]);
  if (toReview) alerts.push(["review", "inbox", `${toReview} submission${toReview > 1 ? "s" : ""} to review`, "/teacher/homework"]);
  if (home && att.data && !att.data.record && working(tt.data)) alerts.push(["attendance", "check-square", `Attendance not marked yet for ${home.class_name} ${home.name}`, "/teacher/attendance"]);
  return (
    <TabScreen testID="teacher-today-screen" showSwitcher={false}>
      <View style={{ gap: 2 }}>
        <Text style={k.h1} testID="teacher-greeting">{greet()}, {(user?.name || "").split(" ")[0]}</Text>
        <Text style={k.small}>{fmtDate(today, { weekday: true })}{home ? ` · Class teacher of ${home.class_name} ${home.name}` : ""}</Text>
      </View>
      <View style={s.quick}>
        <Button label="Mark attendance" icon="check-square" onPress={() => router.push("/teacher/attendance")} style={{ flex: 1 }} testID="teacher-quick-attendance" />
        <Button label="New homework" icon="plus" variant="outline" onPress={() => router.push("/teacher/hw-new")} style={{ flex: 1 }} testID="teacher-quick-homework" />
      </View>
      {alerts.length > 0 && (
        <View style={{ gap: 8 }} testID="teacher-alerts">
          {alerts.map(([key, icon, text, to]) => (
            <Pressable key={key} onPress={() => router.push(to)} style={s.alert} testID={`teacher-alert-${key}`}>
              <Feather name={icon as any} size={18} color="#8A4B08" /><Text style={s.alertText}>{text}</Text><Feather name="chevron-right" size={18} color="#8A4B08" />
            </Pressable>
          ))}
        </View>
      )}
      <CoverRequests requests={subs.data?.requests} uid={user?.id} />
      <SectionTitle title={`Today's periods${day ? ` · ${DAY_SHORT[day.day]}` : ""}`} action="Week" onAction={() => router.push("/teacher/more/timetable")} testID="teacher-open-timetable" />
      {!user?.id || tt.isPending ? <SkeletonList n={3} height={70} />
        : tt.isError ? <ErrorState error={tt.error} onRetry={tt.refetch} testID="teacher-periods-error" />
        : !periods.length ? <Card><Empty icon="coffee" title="No classes today" text={working(tt.data) ? "You have no periods or covers on today's timetable." : "Today is not a school day."} testID="teacher-no-periods" /></Card>
        : periods.map((p: any) => <PeriodCard key={`${p.period_no}-${p.entry.id}`} p={p} tag={cur?.period_no === p.period_no ? (toMin(p.start) <= m ? "Now" : "Next") : ""} />)}
    </TabScreen>
  );
}

const working = (tt: any) => (tt?.config?.working_days || []).includes(tt?.overlay_day || todayKey());

// The dated timetable overlay already contains covers; also merge today's assigned covers from /me/substitutions in case one is missing.
function withCovers(slots: any[], assigned: any[], today: string) {
  const out = slots.filter((p) => p.entry);
  for (const c of assigned.filter((r) => r.date === today && r.status === "assigned")) {
    if (out.some((p) => p.entry?.id === c.id || (p.period_no === c.period_no && p.entry?.is_substitution))) continue;
    const slot = slots.find((p) => p.period_no === c.period_no) || {};
    const entry = { ...c, is_substitution: true, substitution: { covering_for: c.original_teacher_name } };
    out.push({ ...slot, period_no: c.period_no, label: slot.label || `P${c.period_no}`, entry });
  }
  return out.sort((a, b) => toMin(a.start) - toMin(b.start) || a.period_no - b.period_no);
}

function PeriodCard({ p, tag }: { p: any; tag: string }) {
  const b = useBrand();
  const e = p.entry;
  const sub = e.is_substitution;
  const covered = e.substitution?.covered_by;
  return (
    <View style={[s.period, tag && { borderColor: b.color, backgroundColor: b.soft }, covered && { opacity: 0.6 }]} testID={`teacher-period-${p.period_no}`}>
      <View style={{ width: 62 }}>
        <Text style={[s.pl, { color: b.ink }]}>{p.label}</Text><Text style={k.small}>{fmtTime(p.start)}</Text>
        {tag ? <View style={[s.tag, { backgroundColor: b.color }]}><Text style={[s.tagText, { color: b.onColor }]}>{tag}</Text></View> : null}
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[s.cls, covered && { textDecorationLine: "line-through" }]}>{e.class_name} {e.section}</Text>
        <Text style={k.small}>{e.subject}{e.room ? ` · ${e.room}` : ""}</Text>
        {sub && <View style={s.cover} testID={`teacher-cover-${p.period_no}`}><Feather name="repeat" size={11} color="#5B21B6" /><Text style={s.coverText}>Cover · for {e.substitution?.covering_for || "a colleague"}</Text></View>}
        {covered ? <Text style={[k.small, { color: C.warning }]}>Covered by {covered}</Text> : null}
      </View>
    </View>
  );
}

function CoverRequests({ requests, uid }: { requests?: any[]; uid: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const open = (requests || []).filter((r) => r.date >= todayISO() && !["assigned", "cancelled"].includes(r.status));
  if (!open.length) return null;
  const respond = async (id: string, accept: boolean) => {
    try { await api.post(`/substitutions/${id}/respond`, { accept }); toast(accept ? "Accepted" : "Declined"); qc.invalidateQueries({ queryKey: ["t-subs"] }); qc.invalidateQueries({ queryKey: ["t-tt"] }); }
    catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <View style={{ gap: 10 }} testID="teacher-cover-requests">
      <SectionTitle title="Cover requests" />
      {open.map((r) => {
        const mine = (r.responses || {})[uid];
        return (
          <Card key={r.id} style={{ gap: 8 }} testID={`cover-request-${r.id}`}>
            <Text style={s.cls}>{r.class_name} {r.section} · P{r.period_no} · {r.subject}</Text>
            <Text style={k.small}>{fmtDate(r.date, { weekday: true })}</Text>
            {mine ? <Text style={[k.label, { color: C.info }]}>You {String(mine.accept ?? mine) === "true" || mine.accept ? "accepted" : "declined"} — waiting for the office</Text> : (
              <View style={{ flexDirection: "row", gap: 8 }}>
                <Button small variant="success" icon="check" label="Accept" onPress={() => respond(r.id, true)} style={{ flex: 1 }} testID={`cover-accept-${r.id}`} />
                <Button small variant="outline" icon="x" label="Decline" onPress={() => respond(r.id, false)} style={{ flex: 1 }} testID={`cover-decline-${r.id}`} />
              </View>
            )}
          </Card>
        );
      })}
    </View>
  );
}

const s = StyleSheet.create({
  quick: { flexDirection: "row", gap: 10 },
  alert: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 54, paddingHorizontal: 16, borderRadius: 16, backgroundColor: "#FDF3E1" },
  alertText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 15, color: "#8A4B08" },
  period: { flexDirection: "row", gap: 12, padding: 14, borderRadius: 18, backgroundColor: "#fff", borderWidth: 1, borderColor: C.border },
  pl: { fontFamily: fonts.heading, fontSize: 16 },
  tag: { alignSelf: "flex-start", paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, marginTop: 4 },
  tagText: { fontFamily: fonts.bodyBold, fontSize: 11 },
  cls: { fontFamily: fonts.bodyBold, fontSize: 16, color: C.onSurface },
  cover: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start", backgroundColor: "#EDE9FE", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, marginTop: 3 },
  coverText: { fontFamily: fonts.bodyBold, fontSize: 11, color: "#5B21B6" },
});
