// Principal Today: a snapshot for MY divisions only (all numbers come from principal-scoped endpoints).
import { Pressable, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Feather } from "@expo/vector-icons";
import { useAuth, useBrand } from "@/src/state/auth";
import { api } from "@/src/lib/api";
import { usePSections, useTodayAttendance } from "@/src/principal/hooks";
import { TabScreen } from "@/src/ui/Screen";
import { ViewPill } from "@/src/ui/ViewSwitch";
import { Avatar } from "@/src/ui/brandbits";
import { C, Card, SectionTitle, Skeleton, StatusChip, k, type IconName } from "@/src/ui/kit";
import { fmtDate, inr, todayISO } from "@/src/lib/format";
import { fonts } from "@/src/theme";

function Tile({ icon, label, value, sub, onPress, testID, tone }: { icon: IconName; label: string; value: any; sub?: string; onPress?: () => void; testID: string; tone?: string }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.tile, pressed && { opacity: 0.85 }]} testID={testID}>
      <Feather name={icon} size={20} color={tone || C.onSurface} />
      <Text style={[s.num, tone ? { color: tone } : null]} testID={`${testID}-value`}>{value}</Text>
      <Text style={s.lbl}>{label}</Text>
      {sub ? <Text style={k.small} numberOfLines={1}>{sub}</Text> : null}
    </Pressable>
  );
}

export default function PrincipalToday() {
  const { user } = useAuth();
  const b = useBrand();
  const sec = usePSections();
  const att = useTodayAttendance(sec.data || []);
  const dash = useQuery({ queryKey: ["p-subdash"], queryFn: () => api.get("/substitutions/dashboard") });
  const book = useQuery({ queryKey: ["p-daybook", todayISO()], queryFn: () => api.get(`/fees/day-book?date=${todayISO()}`) });
  const proofs = useQuery({ queryKey: ["p-proofstats"], queryFn: () => api.get("/fees/proofs/stats") });
  const unread = useQuery({ queryKey: ["unread"], queryFn: async () => (await api.get("/chat/unread")).unread || 0 });
  const exams = useQuery({ queryKey: ["p-exams"], queryFn: async () => (await api.get("/exams")).exams || [] });
  const d = dash.data;
  const scope = user?.principal?.scope_type === "whole_school" ? "Whole school" : "My divisions";
  const loading = sec.isLoading || att.loading;
  return (
    <TabScreen testID="principal-today-screen" title="Today" showSwitcher={false} right={<View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}><ViewPill to="teacher" /><Avatar name={user?.name || "P"} uri={user?.thumb_url} size={40} testID="principal-today-photo" /></View>}>
      <View style={{ gap: 4 }}>
        <Text style={k.h1} testID="principal-greeting">Hello, {user?.name?.split(" ")[0]}</Text>
        <Text style={k.small}>{fmtDate(todayISO(), { weekday: true })} · Principal · {scope}</Text>
      </View>
      <Card onPress={() => router.push("/principal/attendance")} style={{ gap: 8, backgroundColor: b.soft }} testID="ptoday-attendance">
        <Text style={k.label}>Attendance today</Text>
        {loading ? <Skeleton height={40} /> : (
          <View style={{ flexDirection: "row", alignItems: "baseline", gap: 10 }}>
            <Text style={[s.big, { color: b.ink }]} testID="ptoday-att-pct">{att.pct === null ? "—" : `${att.pct}%`}</Text>
            <Text style={k.small} testID="ptoday-att-marked">{att.marked} of {att.rows.length} classes marked</Text>
          </View>
        )}
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
          {att.rows.map((r) => (
            <View key={`${r.class_name}${r.section}`} style={[s.pill, { backgroundColor: r.marked ? "#E7F6EF" : "#FDF3E1" }]} testID={`ptoday-att-${r.class_name}-${r.section}`.replace(/\s/g, "")}>
              <Text style={[s.pillText, { color: r.marked ? "#047857" : "#B45309" }]}>{r.class_name.replace(/^Grade\s*/i, "")}{r.section} · {r.marked ? (r.final ? "final" : "draft") : "not marked"}</Text>
            </View>
          ))}
        </View>
      </Card>
      <View style={s.grid}>
        <Tile icon="user-x" label="Teachers absent" value={d?.absent_today ?? "—"} onPress={() => router.push("/principal/cover")} testID="ptoday-absent" />
        <Tile icon="alert-circle" label="Periods need cover" value={d ? d.open + d.requested : "—"} sub={d ? `${d.assigned} covered` : ""} tone={d && d.open + d.requested ? C.error : undefined} onPress={() => router.push("/principal/cover")} testID="ptoday-cover" />
        <Tile icon="dollar-sign" label="Collected today" value={book.data ? inr(book.data.summary?.total) : "—"} sub={book.data ? `${book.data.summary?.count || 0} payments` : ""} onPress={() => router.push({ pathname: "/principal/fees", params: { tab: "book" } })} testID="ptoday-collected" />
        <Tile icon="image" label="Pending proofs" value={proofs.data?.pending_proofs ?? "—"} sub={proofs.data ? `${proofs.data.open_issues} open issues` : ""} onPress={() => router.push({ pathname: "/principal/fees", params: { tab: "proofs" } })} testID="ptoday-proofs" />
        <Tile icon="message-circle" label="Unread parent messages" value={unread.data ?? "—"} onPress={() => router.push("/principal/messages")} testID="ptoday-unread" />
        <Tile icon="clipboard" label="Exams" value={exams.data?.length ?? "—"} sub="this year" onPress={() => {}} testID="ptoday-exams" />
      </View>
      <SectionTitle title="Exams" />
      {(exams.data || []).slice(0, 4).map((e: any) => (
        <Card key={e.id} style={{ flexDirection: "row", alignItems: "center", gap: 12 }} testID={`ptoday-exam-${e.id}`}>
          <View style={{ flex: 1 }}><Text style={k.label}>{e.name}</Text><Text style={k.small}>{(e.division_names || []).join(", ") || e.type}</Text></View>
          <StatusChip status={e.status === "published" ? "approved" : e.status} />
        </Card>
      ))}
    </TabScreen>
  );
}

const s = StyleSheet.create({
  big: { fontFamily: fonts.heading, fontSize: 34 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  tile: { width: "47.5%", flexGrow: 1, backgroundColor: "#fff", borderRadius: 20, borderWidth: 1, borderColor: C.border, padding: 16, gap: 4, minHeight: 120 },
  num: { fontFamily: fonts.heading, fontSize: 24, color: C.onSurface, marginTop: 4 },
  lbl: { fontFamily: fonts.bodySemi, fontSize: 13, color: C.onSurface },
  pill: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 },
  pillText: { fontFamily: fonts.bodyBold, fontSize: 12 },
});
