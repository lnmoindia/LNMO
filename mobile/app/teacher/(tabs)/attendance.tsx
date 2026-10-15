// Daily class attendance (same /attendance/sheet API as the web): tap to cycle P → A → L, save draft or submit final.
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useQueryClient } from "@tanstack/react-query";
import { Feather } from "@expo/vector-icons";
import { useMyClass, useTeachingOptions, useAttendanceSheet } from "@/src/lib/queries";
import { useToast } from "@/src/state/toast";
import { api } from "@/src/lib/api";
import { TabScreen } from "@/src/ui/Screen";
import { Button, C, Card, Chip, Empty, ErrorState, SkeletonList, k } from "@/src/ui/kit";
import { confirm } from "@/src/ui/brandbits";
import { addDaysISO, fmtDate, fullName, todayISO } from "@/src/lib/format";
import { fonts } from "@/src/theme";

const NEXT: Record<string, string> = { present: "absent", absent: "late", late: "present" };
const TONE: Record<string, [string, string, string]> = { present: ["#E7F6EF", "#047857", "P"], absent: ["#FDECEF", "#BE123C", "A"], late: ["#FDF3E1", "#B45309", "L"] };
const shift = (iso: string, n: number) => { const d = new Date(`${iso}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };

export default function TeacherAttendance() {
  const homes = useMyClass();
  const opts = useTeachingOptions();
  const classes = useMemo(() => {
    const m = new Map<string, [string, string]>();
    (homes.data || []).forEach((h: any) => m.set(`${h.class_name}|${h.name}`, [h.class_name, h.name]));
    (opts.data || []).forEach((o: any) => m.set(`${o.class_name}|${o.section}`, [o.class_name, o.section]));
    return [...m.values()];
  }, [homes.data, opts.data]);
  const [sel, setSel] = useState<[string, string] | null>(null);
  const [date, setDate] = useState(todayISO());
  useEffect(() => { if (!sel && classes.length) setSel(classes[0]); }, [classes, sel]);
  const q = useAttendanceSheet(sel?.[0] || "", sel?.[1] || "", date);
  const [marks, setMarks] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const qc = useQueryClient();
  useEffect(() => { setMarks(q.data?.record?.entries || {}); setDirty(false); }, [q.data]);
  const locked = Boolean(q.data?.record?.finalized);
  const students = q.data?.students || [];
  const counts = { present: 0, absent: 0, late: 0 } as Record<string, number>;
  students.forEach((st: any) => { const v = marks[st.id]; if (v) counts[v] += 1; });
  const guard = async (fn: () => void) => { if (!dirty || (await confirm("Discard changes?", "You have unsaved attendance changes.", "Discard"))) fn(); };
  const save = async (finalized: boolean) => {
    setBusy(true);
    try {
      await api.post("/attendance/sheet", { class_name: sel![0], section: sel![1], date, entries: marks, finalized });
      toast(finalized ? "Attendance submitted as final" : "Draft saved"); setDirty(false);
      qc.invalidateQueries({ queryKey: ["t-att"] });
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  const unmarked = students.filter((st: any) => !marks[st.id]).length;
  return (
    <TabScreen testID="teacher-attendance-screen" title="Attendance" showSwitcher={false}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {classes.map(([c, sct]) => <Chip key={`${c}${sct}`} label={`${c} ${sct}`} active={sel?.[0] === c && sel?.[1] === sct} onPress={() => guard(() => setSel([c, sct]))} testID={`att-class-${c}-${sct}`.replace(/\s/g, "")} />)}
      </ScrollView>
      <View style={s.dateRow}>
        <Pressable onPress={() => guard(() => setDate(shift(date, -1)))} style={s.nav} testID="att-prev-day"><Feather name="chevron-left" size={22} color={C.onSurface} /></Pressable>
        <View style={{ flex: 1, alignItems: "center" }}><Text style={k.h2} testID="att-date">{fmtDate(date, { weekday: true })}</Text>{date === todayISO() && <Text style={k.small}>Today</Text>}</View>
        <Pressable onPress={() => guard(() => setDate(shift(date, 1)))} disabled={date >= todayISO()} style={[s.nav, date >= todayISO() && { opacity: 0.3 }]} testID="att-next-day"><Feather name="chevron-right" size={22} color={C.onSurface} /></Pressable>
      </View>
      {q.isLoading || !sel ? <SkeletonList n={4} height={60} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !students.length ? <Card><Empty icon="users" text="No students in this class." /></Card> : (
        <>
          <View style={s.summary} testID="att-summary">
            {(["present", "absent", "late"] as const).map((st) => <View key={st} style={[s.sumBox, { backgroundColor: TONE[st][0] }]}><Text style={[s.sumNum, { color: TONE[st][1] }]}>{counts[st]}</Text><Text style={[s.sumLbl, { color: TONE[st][1] }]}>{st}</Text></View>)}
          </View>
          <Text style={k.small} testID="att-state">
            {locked ? "Final — locked. Ask an administrator to make corrections." : q.data.record ? `Draft saved by ${q.data.record.marked_by}` : "Not marked yet"}{unmarked && !locked ? ` · ${unmarked} not marked` : ""}{dirty ? " · unsaved changes" : ""}
          </Text>
          {!locked && <Button small variant="outline" icon="check-circle" label="Mark all present" onPress={() => { setMarks(Object.fromEntries(students.map((st: any) => [st.id, "present"]))); setDirty(true); }} testID="att-all-present" />}
          <Card style={{ padding: 0 }}>
            {students.map((st: any, i: number) => {
              const v = marks[st.id];
              const t = v ? TONE[v] : [C.surfaceTertiary, C.muted, "–"];
              return (
                <Pressable key={st.id} disabled={locked} onPress={() => { setMarks((mm) => ({ ...mm, [st.id]: v ? NEXT[v] : "present" })); setDirty(true); }}
                  style={[s.row, i > 0 && s.line]} testID={`att-student-${st.id}`}>
                  <View style={{ flex: 1 }}><Text style={s.name}>{fullName(st)}</Text><Text style={k.small}>{st.admission_no}</Text></View>
                  <View style={[s.toggle, { backgroundColor: t[0] }]}><Text style={[s.toggleText, { color: t[1] }]} testID={`att-status-${st.id}`}>{t[2]}</Text></View>
                </Pressable>
              );
            })}
          </Card>
          {!locked && (
            <View style={{ gap: 8 }}>
              <Button label="Save draft" variant="outline" icon="save" onPress={() => save(false)} loading={busy} testID="att-save-draft" />
              <Button label="Submit as final" icon="lock" onPress={() => save(true)} loading={busy} disabled={unmarked > 0} testID="att-submit-final" />
            </View>
          )}
        </>
      )}
      {date < addDaysISO(-30) && <Text style={k.small}>Older dates can only be corrected by an administrator once final.</Text>}
    </TabScreen>
  );
}

const s = StyleSheet.create({
  dateRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  nav: { width: 44, height: 44, borderRadius: 14, borderWidth: 1, borderColor: C.border, alignItems: "center", justifyContent: "center", backgroundColor: "#fff" },
  summary: { flexDirection: "row", gap: 10 },
  sumBox: { flex: 1, borderRadius: 16, padding: 12, alignItems: "center" },
  sumNum: { fontFamily: fonts.heading, fontSize: 24 },
  sumLbl: { fontFamily: fonts.bodyBold, fontSize: 12, textTransform: "capitalize" },
  row: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingVertical: 10, minHeight: 64 },
  line: { borderTopWidth: 1, borderTopColor: C.divider },
  name: { fontFamily: fonts.bodySemi, fontSize: 16, color: C.onSurface },
  toggle: { width: 56, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  toggleText: { fontFamily: fonts.heading, fontSize: 18 },
});
