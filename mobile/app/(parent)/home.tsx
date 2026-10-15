import { Pressable, StyleSheet, Text, View } from "react-native";
import { router, type Href } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useAuth, useBrand } from "@/src/state/auth";
import { useChild } from "@/src/state/child";
import { useAssignments, useExams, useFees, useHomework, useNotices, pendingItems, useSnap, useTimetable } from "@/src/lib/queries";
import { TabScreen } from "@/src/ui/Screen";
import { C, Card, Empty, ErrorState, SectionTitle, SkeletonList, k } from "@/src/ui/kit";
import { ClassTeacherCard } from "@/src/parent/ClassTeacherCard";
import { Avatar } from "@/src/ui/brandbits";
import { buildAlerts, TONE } from "@/src/parent/alerts";
import { PeriodRow, coverFor, todayClasses, ttDay, TodayChanges } from "@/src/parent/timetable";
import { NoticeCard } from "@/src/parent/NoticeCard";
import { fmtDate, fullName, hourNow, todayISO } from "@/src/lib/format";
import { fonts } from "@/src/theme";

const greet = () => { const h = hourNow(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };

export default function Home() {
  const { user } = useAuth();
  const { children, childId } = useChild();
  const snap = useSnap(childId);
  const tt = useTimetable(childId);
  const hw = useHomework(childId);
  const asg = useAssignments(childId);
  const fees = useFees(childId);
  const exams = useExams(childId);
  const notices = useNotices();
  if (children && children.length === 0) {
    return (
      <TabScreen testID="home-screen" title="Home">
        <Card testID="no-children"><Empty icon="users" title="No children linked yet" text="Link a child from My account, or contact the school office." /></Card>
      </TabScreen>
    );
  }
  const alerts = buildAlerts({ fees: fees.data, hw: hw.data, asg: asg.data, tt: tt.data, notices: notices.data, exams: exams.data });
  return (
    <TabScreen testID="home-screen">
      <View style={{ gap: 2 }}>
        <Text style={k.h1} testID="home-greeting">{greet()}, {(user?.name || "").split(" ")[0]}</Text>
        <Text style={k.small}>{fmtDate(todayISO(), { weekday: true })}</Text>
      </View>
      {!childId || snap.isLoading ? <SkeletonList n={1} height={110} /> : snap.isError ? <ErrorState error={snap.error} onRetry={snap.refetch} /> : (
        <>
          <ChildHero s={snap.data.student} leader={snap.data.leader_role} />
          <ClassTeacherCard t={snap.data.class_teacher} childId={childId} cls={`${snap.data.student.class_name}${snap.data.student.section ? ` ${snap.data.student.section}` : ""}`} testID="home-class-teacher" />
        </>
      )}
      <View style={{ gap: 10 }} testID="home-today-alerts">
        <SectionTitle title="Today" />
        {fees.isLoading || hw.isLoading ? <SkeletonList n={1} height={60} /> : alerts.length === 0 ? (
          <Card style={s.calm} testID="home-all-clear">
            <Feather name="sun" size={20} color={C.success} />
            <Text style={[k.body, { flex: 1 }]}>All clear today — nothing needs your attention.</Text>
          </Card>
        ) : alerts.map((a) => <AlertRow key={a.k} a={a} />)}
      </View>
      <QuickStats snap={snap.data} hw={hw.data} asg={asg.data} />
      <TodayPreview tt={tt.data} />
      <View style={{ gap: 10 }}>
        <SectionTitle title="Latest notices" action={notices.data?.length ? "See all" : undefined} onAction={() => router.push("/more/notices")} testID="home-notices-see-all" />
        {notices.isLoading ? <SkeletonList n={2} height={70} /> : !notices.data?.length
          ? <Card><Empty icon="bell" text="No notices from the school right now." /></Card>
          : notices.data.slice(0, 3).map((n: any) => <NoticeCard key={n.id} n={n} compact testID={`home-notice-${n.id}`} />)}
      </View>
    </TabScreen>
  );
}

function ChildHero({ s: st, leader }: { s: any; leader?: string }) {
  const b = useBrand();
  return (
    <View style={[s.hero, { backgroundColor: b.color }]} testID="home-child-card">
      <View style={[s.heroBlob, { backgroundColor: b.onColor === "#FFFFFF" ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.3)" }]} />
      <Avatar name={st.first_name} uri={st.thumb_url || st.photo_url} size={52} light={b.onColor === "#FFFFFF"} testID="home-child-photo" />
      <View style={{ flex: 1 }}>
        <Text style={[s.heroLabel, { color: b.onColor }]}>Your child</Text>
        <Text style={[s.heroName, { color: b.onColor }]} testID="home-child-name">{fullName(st)}</Text>
        <Text style={[s.heroSub, { color: b.onColor }]}>{st.class_name}{st.section ? ` · Section ${st.section}` : ""}{st.admission_no ? ` · Adm. ${st.admission_no}` : ""}</Text>
        {leader && (
          <View style={s.leader} testID="home-leader-badge">
            <Feather name="award" size={12} color="#451A03" />
            <Text style={s.leaderText}>{leader === "class_leader" ? "Class Leader" : "Second Leader"}</Text>
          </View>
        )}
      </View>
    </View>
  );
}

function AlertRow({ a }: { a: ReturnType<typeof buildAlerts>[number] }) {
  const b = useBrand();
  const [bg, fg] = TONE[a.tone];
  return (
    <Pressable onPress={() => router.push(a.to as Href)} testID={`home-alert-${a.k}`} style={({ pressed }) => [s.alert, { backgroundColor: bg }, pressed && { opacity: 0.85 }]}>
      <Feather name={a.icon as any} size={20} color={fg} />
      <Text style={[s.alertText, { color: fg }]}>{a.text}</Text>
      {a.action ? (
        <View style={[s.pay, { backgroundColor: b.color }]} testID={`home-alert-${a.k}-pay-btn`}><Text style={[s.payText, { color: b.onColor }]}>{a.action}</Text></View>
      ) : <Feather name="chevron-right" size={20} color={fg} />}
    </Pressable>
  );
}

function QuickStats({ snap, hw, asg }: any) {
  const r = snap?.results?.[0];
  const att = snap?.attendance || {};
  const stats = [
    { k: "attendance", icon: "check-square", label: "Attendance", value: att.pct != null ? `${att.pct}%` : "—", sub: !snap ? "Loading…" : att.total ? `${att.present}/${att.total} days` : "No records", to: "/more/attendance", tone: TONE.emerald },
    { k: "homework", icon: "book-open", label: "Homework", value: hw ? String(pendingItems(hw).length) : "—", sub: asg ? `${pendingItems(asg).length} assignment(s)` : "", to: "/more/homework", tone: TONE.indigo },
    { k: "results", icon: "award", label: "Latest result", value: r ? `${r.score ?? "—"}${r.max_marks ? `/${r.max_marks}` : ""}` : "—", sub: !snap ? "Loading…" : r?.subject || "No results yet", to: "/more/results", tone: TONE.sky },
  ];
  return (
    <View style={s.stats} testID="home-quick-stats">
      {stats.map((x) => (
        <Pressable key={x.k} onPress={() => router.push(x.to as Href)} testID={`home-stat-${x.k}`} style={({ pressed }) => [s.stat, { backgroundColor: x.tone[0] }, pressed && { opacity: 0.85 }]}>
          <Feather name={x.icon as any} size={18} color={x.tone[1]} />
          <Text style={[s.statValue, { color: x.tone[1] }]} numberOfLines={1}>{x.value}</Text>
          <Text style={[s.statLabel, { color: x.tone[1] }]} numberOfLines={1}>{x.label}</Text>
          <Text style={s.statSub} numberOfLines={1}>{x.sub}</Text>
        </Pressable>
      ))}
    </View>
  );
}

function TodayPreview({ tt }: { tt: any }) {
  const rows = todayClasses(tt);
  const day = ttDay(tt);
  return (
    <View style={{ gap: 10 }} testID="home-today-classes">
      <SectionTitle title="Today's classes" action="Full timetable" onAction={() => router.push("/timetable")} testID="home-open-timetable" />
      <TodayChanges changes={tt?.today_changes} testID="home-today-changes" />
      {!tt ? <SkeletonList n={2} height={70} /> : rows.length === 0
        ? <Card><Empty icon="coffee" text="No classes today." /></Card>
        : rows.slice(0, 4).map((r: any) => <PeriodRow key={r.pno} p={r.p} e={r.e} cover={coverFor(tt.today_changes, day, r.pno)} testID={`home-period-${r.pno}`} />)}
      {rows.length > 4 && <Text style={[k.small, { textAlign: "center" }]}>+{rows.length - 4} more periods</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  hero: { borderRadius: 24, padding: 20, flexDirection: "row", gap: 16, alignItems: "center", overflow: "hidden" },
  heroBlob: { position: "absolute", width: 160, height: 160, borderRadius: 80, right: -50, top: -60 },
  heroLabel: { fontFamily: fonts.bodySemi, fontSize: 12, letterSpacing: 0.8, textTransform: "uppercase", opacity: 0.8 },
  heroName: { fontFamily: fonts.heading, fontSize: 24, marginTop: 2 },
  heroSub: { fontFamily: fonts.bodyMedium, fontSize: 14, opacity: 0.9, marginTop: 2 },
  leader: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start", backgroundColor: "#FCD34D", paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999, marginTop: 8 },
  leaderText: { fontFamily: fonts.bodyBold, fontSize: 12, color: "#451A03" },
  calm: { flexDirection: "row", gap: 12, alignItems: "center" },
  alert: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 60, paddingHorizontal: 16, paddingVertical: 12, borderRadius: 18 },
  alertText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 15, lineHeight: 20 },
  pay: { paddingHorizontal: 18, minHeight: 38, borderRadius: 12, justifyContent: "center" },
  payText: { fontFamily: fonts.bodyBold, fontSize: 14 },
  stats: { flexDirection: "row", gap: 10 },
  stat: { flex: 1, borderRadius: 20, padding: 14, gap: 3, minHeight: 120 },
  statValue: { fontFamily: fonts.heading, fontSize: 22, marginTop: 6 },
  statLabel: { fontFamily: fonts.bodyBold, fontSize: 12 },
  statSub: { fontFamily: fonts.body, fontSize: 12, color: C.muted },
});
