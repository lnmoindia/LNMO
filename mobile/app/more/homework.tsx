import { useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Feather } from "@expo/vector-icons";
import { useChild } from "@/src/state/child";
import { useBrand } from "@/src/state/auth";
import { useToast } from "@/src/state/toast";
import { filterWork, useAssignments, useHomework } from "@/src/lib/queries";
import { openAuthedFile } from "@/src/lib/files";
import { StackScreen } from "@/src/ui/Screen";
import { C, Card, Chip, Empty, SectionTitle, SkeletonList, k } from "@/src/ui/kit";
import { fmtDate, todayISO } from "@/src/lib/format";
import { fonts } from "@/src/theme";

const FILTERS: [string, string][] = [["due", "Due"], ["submitted", "Submitted"], ["overdue", "Overdue"], ["all", "All"]];

const badge = (hw: any) => {
  const s = hw.my_submission;
  if (!s) return ["Not submitted", C.surfaceTertiary, C.onSurfaceTertiary];
  if (s.status === "verified" || s.status === "graded") return [s.score != null ? `Reviewed · ${s.score}${hw.max_marks ? `/${hw.max_marks}` : ""}` : "Reviewed", C.successSoft, C.success];
  if (s.status === "redo") return ["Redo requested", C.warningSoft, C.warning];
  return [s.late ? "Submitted · Late" : "Submitted", C.infoSoft, C.info];
};

function WorkCard({ hw, kind }: { hw: any; kind: "homework" | "assignment" }) {
  const b = useBrand();
  const toast = useToast();
  const [label, bg, fg] = badge(hw);
  const overdue = !hw.my_submission && hw.due_date && String(hw.due_date).slice(0, 10) < todayISO();
  const open = async (a: any, i: number) => {
    try { await openAuthedFile(`/${kind === "assignment" ? "assignments" : "homework"}/attachment/${hw.id}/${i}?kind=${kind}`, a.name || "attachment", a.content_type || "application/octet-stream"); }
    catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <Card style={{ gap: 6 }} testID={`hw-card-${hw.id}`}>
      <View style={st.top}>
        <Text style={st.subject}>{hw.subject}</Text>
        <View style={[st.badge, { backgroundColor: bg }]}><Text style={[st.badgeText, { color: fg }]}>{label}</Text></View>
      </View>
      <Text style={st.title}>{hw.title}</Text>
      <Text style={[k.small, overdue && { color: C.error, fontFamily: fonts.bodySemi }]}>
        Due {fmtDate(hw.due_date, { weekday: true })}{overdue ? " · overdue" : ""}{hw.status === "closed" ? " · closed" : ""}
      </Text>
      {hw.instructions ? <Text style={k.body}>{hw.instructions}</Text> : null}
      {hw.my_submission?.feedback ? <Text style={[k.small, { color: hw.my_submission.status === "redo" ? C.warning : C.onSurfaceSecondary }]} testID={`hw-feedback-${hw.id}`}>
        {hw.my_submission.status === "redo" ? "Redo requested: " : "Teacher: "}{hw.my_submission.feedback}</Text> : null}
      {hw.my_submission?.status === "redo" && hw.my_submission.redo_due_date ? <Text style={k.small} testID={`hw-redo-due-${hw.id}`}>Resubmit by {fmtDate(hw.my_submission.redo_due_date, { weekday: true })}</Text> : null}
      {hw.my_submission?.version > 1 ? <Text style={k.small}>Version {hw.my_submission.version}</Text> : null}
      {(hw.attachments || []).map((a: any, i: number) => (
        <Pressable key={i} onPress={() => open(a, i)} style={st.file} testID={`hw-file-${hw.id}-${i}`}>
          <Feather name="paperclip" size={14} color={b.ink} /><Text style={[st.fileText, { color: b.ink }]} numberOfLines={1}>{a.name}</Text>
        </Pressable>
      ))}
    </Card>
  );
}

export default function Homework() {
  const { childId } = useChild();
  const hw = useHomework(childId);
  const asg = useAssignments(childId);
  const [f, setF] = useState("due");
  const today = todayISO();
  const h = useMemo(() => filterWork(hw.data, f, today), [hw.data, f, today]);
  const a = useMemo(() => filterWork(asg.data, f, today), [asg.data, f, today]);
  return (
    <StackScreen title="Homework" testID="homework-screen">
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} testID="homework-filter">
        {FILTERS.map(([key, l]) => <Chip key={key} label={l} active={f === key} onPress={() => setF(key)} testID={`homework-filter-${key}`} />)}
      </ScrollView>
      {hw.isLoading ? <SkeletonList n={3} /> : !h?.length ? (
        <Card><Empty icon="check-circle" title="All caught up" text="No homework in this list right now." testID="homework-empty" /></Card>
      ) : h.map((x: any) => <WorkCard key={x.id} hw={x} kind="homework" />)}
      {(a?.length || 0) > 0 && <SectionTitle title="Assignments" />}
      {a?.map((x: any) => <WorkCard key={x.id} hw={x} kind="assignment" />)}
    </StackScreen>
  );
}

const st = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  subject: { fontFamily: fonts.bodyBold, fontSize: 13, color: C.muted, textTransform: "uppercase", letterSpacing: 0.6 },
  title: { fontFamily: fonts.heading, fontSize: 17, color: C.onSurface },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  badgeText: { fontFamily: fonts.bodyBold, fontSize: 12 },
  file: { flexDirection: "row", alignItems: "center", gap: 8, minHeight: 40, paddingHorizontal: 12, borderRadius: 12, backgroundColor: C.surfaceTertiary },
  fileText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 14 },
});
