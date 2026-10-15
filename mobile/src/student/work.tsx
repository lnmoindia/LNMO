// Student homework/assignment helpers + card (list rows link to the detail screen).
import { StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, Card } from "@/src/ui/kit";
import { fmtDate, todayISO } from "@/src/lib/format";
import { fonts } from "@/src/theme";

export type Kind = "homework" | "assignment";
export const dueOf = (x: any) => String(x?.due_date || "").slice(0, 10);
export const isPending = (x: any) => x.status === "open" && (!x.my_submission || x.my_submission.status === "redo");

export const workBadge = (x: any): [string, string, string] => {
  const s = x.my_submission;
  if (!s) return isPending(x) && dueOf(x) && dueOf(x) < todayISO() ? ["Overdue", C.errorSoft, C.error] : ["Not submitted", C.surfaceTertiary, C.onSurfaceTertiary];
  if (s.status === "verified" || s.status === "graded") return [s.score != null ? `Reviewed · ${s.score}${x.max_marks ? `/${x.max_marks}` : ""}` : "Reviewed", C.successSoft, C.success];
  if (s.status === "redo") return ["Redo requested", C.warningSoft, C.warning];
  return [s.late ? "Submitted · Late" : "Submitted", C.infoSoft, C.info];
};

export function WorkCard({ x, kind, testID }: { x: any; kind: Kind; testID?: string }) {
  const [label, bg, fg] = workBadge(x);
  return (
    <Card onPress={() => router.push(`/student/work/${kind}/${x.id}`)} style={{ gap: 6 }} testID={testID || `work-card-${x.id}`}>
      <View style={s.top}>
        <Text style={s.subject} numberOfLines={1}>{kind === "assignment" ? "Assignment · " : ""}{x.subject}</Text>
        <View style={[s.badge, { backgroundColor: bg }]}><Text style={[s.badgeText, { color: fg }]}>{label}</Text></View>
      </View>
      <Text style={s.title}>{x.title}</Text>
      <View style={s.bottom}>
        <Feather name="calendar" size={14} color={C.muted} />
        <Text style={s.due}>Due {fmtDate(x.due_date, { weekday: true, year: false })}{kind === "assignment" && x.max_marks ? ` · ${x.max_marks} marks` : ""}</Text>
        {(x.attachments || []).length ? <><Feather name="paperclip" size={13} color={C.muted} /><Text style={s.due}>{x.attachments.length}</Text></> : null}
        <View style={{ flex: 1 }} />
        <Feather name="chevron-right" size={20} color={C.muted} />
      </View>
    </Card>
  );
}

const s = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  subject: { flex: 1, fontFamily: fonts.bodyBold, fontSize: 12, color: C.muted, textTransform: "uppercase", letterSpacing: 0.6 },
  title: { fontFamily: fonts.heading, fontSize: 17, color: C.onSurface },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  badgeText: { fontFamily: fonts.bodyBold, fontSize: 12 },
  bottom: { flexDirection: "row", alignItems: "center", gap: 6 },
  due: { fontFamily: fonts.bodyMedium, fontSize: 13, color: C.muted },
});
