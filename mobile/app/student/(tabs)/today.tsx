import { Pressable, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useAuth, useBrand } from "@/src/state/auth";
import { useMe, useMyAssignments, useMyExams, useMyHomework, useMyTimetable, useNotices } from "@/src/lib/queries";
import { TabScreen } from "@/src/ui/Screen";
import { C, Card, Empty, ErrorState, SectionTitle, SkeletonList, k } from "@/src/ui/kit";
import { Avatar } from "@/src/ui/brandbits";
import { NoticeCard } from "@/src/parent/NoticeCard";
import { PeriodRow, TodayChanges, coverFor, dayRows, nowNext, ttDay } from "@/src/parent/timetable";
import { WorkCard, dueOf, isPending, type Kind } from "@/src/student/work";
import { addDaysISO, daysUntil, fmtDate, hourNow, todayISO } from "@/src/lib/format";
import { fonts } from "@/src/theme";

const greet = () => { const h = hourNow(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };

export default function Today() {
  const me = useMe();
  const tt = useMyTimetable();
  const hw = useMyHomework();
  const asg = useMyAssignments();
  const exams = useMyExams();
  const notices = useNotices();
  const st = me.data?.student;
  return (
    <TabScreen testID="student-today-screen" showSwitcher={false}>
      {me.isLoading ? <SkeletonList n={1} height={110} /> : me.isError ? <ErrorState error={me.error} onRetry={me.refetch} /> : (
        <Hero st={st} leader={me.data.leader_role} att={me.data.attendance} />
      )}
      <TodayClasses tt={tt.data} loading={tt.isLoading} />
      <DueSoon hw={hw.data} asg={asg.data} loading={hw.isLoading || asg.isLoading} />
      <ExamCountdown exams={exams.data} />
      <LatestResult results={me.data?.results} />
      <TutorShortcut />
      <View style={{ gap: 10 }}>
        <SectionTitle title="Latest notices" action={notices.data?.length ? "See all" : undefined} onAction={() => router.push("/more/notices")} testID="student-notices-see-all" />
        {notices.isLoading ? <SkeletonList n={2} height={70} /> : !notices.data?.length
          ? <Card><Empty icon="bell" text="No notices from the school right now." /></Card>
          : notices.data.slice(0, 2).map((n: any) => <NoticeCard key={n.id} n={n} compact testID={`student-notice-${n.id}`} />)}
      </View>
    </TabScreen>
  );
}

function Hero({ st, leader, att }: any) {
  const b = useBrand();
  const { user } = useAuth();
  const light = b.onColor === "#FFFFFF";
  return (
    <View style={[s.hero, { backgroundColor: b.color }]} testID="student-hero">
      <View style={[s.blob, { backgroundColor: light ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.3)" }]} />
      <Avatar name={st.first_name} uri={st.thumb_url || st.photo_url || user?.thumb_url} size={52} light={light} testID="student-today-photo" />
      <View style={{ flex: 1 }}>
        <Text style={[s.heroLabel, { color: b.onColor }]}>{greet()}</Text>
        <Text style={[s.heroName, { color: b.onColor }]} testID="student-greeting-name">{st.first_name}</Text>
        <Text style={[s.heroSub, { color: b.onColor }]}>{st.class_name}{st.section ? ` · Section ${st.section}` : ""} · {fmtDate(todayISO(), { weekday: true, year: false })}</Text>
        <View style={{ flexDirection: "row", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
          {att?.pct != null && <View style={s.pill}><Text style={[s.pillText, { color: b.onColor }]}>Attendance {att.pct}%</Text></View>}
          {leader && <View style={[s.pill, { backgroundColor: "#FCD34D" }]}><Text style={[s.pillText, { color: "#451A03" }]}>{leader === "class_leader" ? "Class Leader" : "Second Leader"}</Text></View>}
        </View>
      </View>
    </View>
  );
}

function TodayClasses({ tt, loading }: { tt: any; loading: boolean }) {
  const day = ttDay(tt);
  const rows = dayRows(tt, day).filter((r: any) => r.e);
  const nn = nowNext(rows);
  return (
    <View style={{ gap: 10 }} testID="student-today-classes">
      <SectionTitle title="Today's classes" action="Week" onAction={() => router.push("/student/timetable")} testID="student-open-timetable" />
      <TodayChanges changes={tt?.today_changes} testID="student-today-changes" />
      {loading ? <SkeletonList n={2} height={70} /> : !rows.length ? <Card><Empty icon="coffee" text="No classes today." /></Card>
        : rows.map((r: any) => <PeriodRow key={r.pno} p={r.p} e={r.e} cover={coverFor(tt.today_changes, day, r.pno)} now={nn?.pno === r.pno} tag={nn?.pno === r.pno ? nn.tag : undefined} testID={`student-period-${r.pno}`} />)}
    </View>
  );
}

function DueSoon({ hw, asg, loading }: any) {
  const today = todayISO();
  const limit = addDaysISO(2);
  const all: [any, Kind][] = [...(hw || []).map((x: any) => [x, "homework"]), ...(asg || []).map((x: any) => [x, "assignment"])] as any;
  const pending = all.filter(([x]) => isPending(x));
  const overdue = pending.filter(([x]) => dueOf(x) && dueOf(x) < today).length;
  const soon = pending.filter(([x]) => dueOf(x) >= today && dueOf(x) <= limit).sort((a, b) => dueOf(a[0]).localeCompare(dueOf(b[0])));
  return (
    <View style={{ gap: 10 }} testID="student-due-soon">
      <SectionTitle title="Due soon" action="All homework" onAction={() => router.push("/student/homework")} testID="student-open-homework" />
      {overdue > 0 && (
        <Pressable onPress={() => router.push({ pathname: "/student/homework", params: { f: "overdue" } })} style={s.overdue} testID="student-overdue-count">
          <Feather name="alert-circle" size={18} color={C.error} />
          <Text style={s.overdueText}>{overdue} overdue — finish {overdue > 1 ? "them" : "it"} soon</Text>
          <Feather name="chevron-right" size={18} color={C.error} />
        </Pressable>
      )}
      {loading ? <SkeletonList n={1} height={90} /> : !soon.length ? <Card><Empty icon="check-circle" text="Nothing due in the next 2 days." testID="student-due-empty" /></Card>
        : soon.map(([x, kind]) => <WorkCard key={x.id} x={x} kind={kind} testID={`student-due-${x.id}`} />)}
    </View>
  );
}

function ExamCountdown({ exams }: { exams?: any[] }) {
  const b = useBrand();
  const up = (exams || []).filter((x) => x.date >= todayISO()).sort((a, c) => a.date.localeCompare(c.date));
  if (!up.length) return null;
  const name = up[0].exam_name;
  const group = up.filter((x) => x.exam_name === name);
  const d = daysUntil(group[0].date);
  const when = d === 0 ? "Today" : d === 1 ? "Tomorrow" : `In ${d} days`;
  return (
    <Card onPress={() => router.push("/student/more/exams")} style={s.exam} testID="student-exam-countdown">
      <View style={[s.examDays, { backgroundColor: b.soft }]}>
        <Text style={[s.examNum, { color: b.ink }]}>{d}</Text>
        <Text style={[s.examUnit, { color: b.ink }]}>{d === 1 ? "day" : "days"}</Text>
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={k.small}>{when}</Text>
        <Text style={s.examName} numberOfLines={2}>{name}</Text>
        <Text style={k.small}>{fmtDate(group[0].date, { year: false })}{group.length > 1 ? ` – ${fmtDate(group[group.length - 1].date, { year: false })}` : ""} · {group.length} subject{group.length > 1 ? "s" : ""}</Text>
        <Text style={k.small} numberOfLines={1}>First: {group[0].subject}</Text>
      </View>
    </Card>
  );
}

function LatestResult({ results }: { results?: any[] }) {
  const r = [...(results || [])].sort((a, c) => String(c.created_at || "").localeCompare(String(a.created_at || "")))[0];
  if (!r) return null;
  const pct = r.max_marks && r.score != null ? Math.round((r.score / r.max_marks) * 100) : null;
  return (
    <Card onPress={() => router.push("/student/more/results")} style={{ gap: 8 }} testID="student-latest-result">
      <SectionTitle title="Latest result" />
      <View style={s.resRow}>
        <View style={{ flex: 1 }}><Text style={s.resSub}>{r.subject}</Text><Text style={k.small} numberOfLines={2}>{r.assessment}</Text></View>
        <Text style={s.resScore}>{r.score ?? "—"}<Text style={k.small}>{r.max_marks ? ` / ${r.max_marks}` : ""}</Text></Text>
      </View>
      {pct != null && <View style={s.track}><View style={[s.fill, { width: `${pct}%`, backgroundColor: pct >= 75 ? C.success : pct >= 50 ? C.info : C.warning }]} /></View>}
    </Card>
  );
}

function TutorShortcut() {
  const b = useBrand();
  return (
    <Pressable onPress={() => router.push("/student/tutor")} testID="student-tutor-shortcut" style={({ pressed }) => [s.tutor, { backgroundColor: b.ink }, pressed && { opacity: 0.9 }]}>
      <View style={s.tutorIcon}><Feather name="zap" size={22} color="#fff" /></View>
      <View style={{ flex: 1 }}>
        <Text style={s.tutorTitle}>Stuck on something?</Text>
        <Text style={s.tutorSub}>Ask the AI Tutor — it uses your school's materials first.</Text>
      </View>
      <Feather name="arrow-right" size={20} color="#fff" />
    </Pressable>
  );
}

const s = StyleSheet.create({
  hero: { borderRadius: 24, padding: 20, flexDirection: "row", gap: 16, alignItems: "center", overflow: "hidden" },
  blob: { position: "absolute", width: 160, height: 160, borderRadius: 80, right: -50, top: -60 },
  heroLabel: { fontFamily: fonts.bodySemi, fontSize: 13, opacity: 0.85 },
  heroName: { fontFamily: fonts.heading, fontSize: 26 },
  heroSub: { fontFamily: fonts.bodyMedium, fontSize: 14, opacity: 0.9 },
  pill: { backgroundColor: "rgba(255,255,255,0.25)", paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999 },
  pillText: { fontFamily: fonts.bodyBold, fontSize: 12, color: "#fff" },
  overdue: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 52, paddingHorizontal: 16, borderRadius: 16, backgroundColor: C.errorSoft },
  overdueText: { flex: 1, fontFamily: fonts.bodyBold, fontSize: 15, color: C.error },
  exam: { flexDirection: "row", gap: 16, alignItems: "center" },
  examDays: { width: 76, height: 76, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  examNum: { fontFamily: fonts.heading, fontSize: 30, lineHeight: 34 },
  examUnit: { fontFamily: fonts.bodyBold, fontSize: 12 },
  examName: { fontFamily: fonts.heading, fontSize: 17, color: C.onSurface },
  resRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  resSub: { fontFamily: fonts.bodyBold, fontSize: 16, color: C.onSurface },
  resScore: { fontFamily: fonts.heading, fontSize: 26, color: C.onSurface },
  track: { height: 8, borderRadius: 4, backgroundColor: C.surfaceTertiary, overflow: "hidden" },
  fill: { height: 8, borderRadius: 4 },
  tutor: { flexDirection: "row", alignItems: "center", gap: 14, padding: 18, borderRadius: 22 },
  tutorIcon: { width: 44, height: 44, borderRadius: 14, backgroundColor: "rgba(255,255,255,0.18)", alignItems: "center", justifyContent: "center" },
  tutorTitle: { fontFamily: fonts.heading, fontSize: 17, color: "#fff" },
  tutorSub: { fontFamily: fonts.body, fontSize: 13, color: "rgba(255,255,255,0.85)", marginTop: 2 },
});
