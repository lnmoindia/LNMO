// Cover: absences in my divisions (today + upcoming), per-period cover with ranked suggestions, leave approvals.
import { useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/lib/api";
import { useToast } from "@/src/state/toast";
import { useAbsences, useSubsDay, useTeachers } from "@/src/principal/hooks";
import { TabScreen } from "@/src/ui/Screen";
import { Button, Card, Chip, Empty, ErrorState, SectionTitle, SkeletonList, StatusChip, k } from "@/src/ui/kit";
import { Sheet, confirm } from "@/src/ui/brandbits";
import { TextField } from "@/src/ui/inputs";
import { addDaysISO, fmtDate, todayISO } from "@/src/lib/format";

const LABEL: Record<string, string> = { open: "Needs cover", requested: "Asked", assigned: "Covered" };
const TONE: Record<string, string> = { open: "overdue", requested: "pending", assigned: "approved" };

function PeriodSheet({ sub, onClose, onDone }: { sub: any; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const q = useQuery({ queryKey: ["p-sugg", sub?.id], queryFn: () => api.get(`/substitutions/${sub.id}/suggestions`), enabled: Boolean(sub) });
  const [sel, setSel] = useState<string[]>([]);
  const [busy, setBusy] = useState("");
  const act = async (key: string, fn: () => Promise<any>, msg: string) => {
    setBusy(key);
    try { await fn(); toast(msg); onDone(); onClose(); } catch (e: any) { toast(e.message, "error"); } finally { setBusy(""); }
  };
  if (!sub) return null;
  const list = (q.data?.suggestions || []).filter((x: any) => x.match >= 0);
  return (
    <Sheet open={Boolean(sub)} onClose={onClose} title={`P${sub.period_no} · ${sub.class_name} ${sub.section || ""} · ${sub.subject}`} testID="pcover-sheet">
      <ScrollView style={{ maxHeight: 520 }} contentContainerStyle={{ gap: 10 }}>
        <Text style={k.small}>{LABEL[sub.status] || sub.status}{sub.substitute_name ? ` · ${sub.substitute_name}` : ""}</Text>
        {sub.status === "assigned" && <Button variant="outline" icon="x-circle" label="Remove cover" loading={busy === "rm"} testID="pcover-remove-btn"
          onPress={async () => { if (await confirm("Remove cover?", `${sub.substitute_name} will no longer cover this period.`, "Remove")) act("rm", () => api.post(`/substitutions/${sub.id}/remove-cover`, {}), "Cover removed"); }} />}
        <SectionTitle title="Suggested substitutes" />
        {q.isLoading ? <SkeletonList n={2} height={56} /> : !list.length ? <Empty icon="user-x" text="Nobody is free this period." /> : list.slice(0, 12).map((t: any) => (
          <Card key={t.teacher_id} onPress={() => setSel((s) => (s.includes(t.teacher_id) ? s.filter((x) => x !== t.teacher_id) : [...s, t.teacher_id]))}
            style={{ flexDirection: "row", alignItems: "center", gap: 10, borderColor: sel.includes(t.teacher_id) ? "#3F6B8A" : undefined, borderWidth: sel.includes(t.teacher_id) ? 2 : 1 }} testID={`pcover-sugg-${t.teacher_id}`}>
            <View style={{ flex: 1 }}><Text style={k.label}>{t.name}</Text><Text style={k.small}>{t.match_label} · {t.day_periods} periods · {t.subs_today} covers today{t.response ? ` · ${t.response}` : t.requested ? " · asked" : ""}</Text></View>
            <Button small label="Assign" loading={busy === t.teacher_id} onPress={() => act(t.teacher_id, () => api.post(`/substitutions/${sub.id}/assign`, { teacher_id: t.teacher_id }), `${t.name} assigned`)} testID={`pcover-assign-${t.teacher_id}`} />
          </Card>
        ))}
        {sel.length > 0 && <Button icon="send" label={`Ask selected (${sel.length})`} loading={busy === "ask"} testID="pcover-ask-btn"
          onPress={() => act("ask", () => api.post(`/substitutions/${sub.id}/request`, { teacher_ids: sel }), "Cover request sent")} />}
      </ScrollView>
    </Sheet>
  );
}

function MarkAbsent({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const t = useTeachers();
  const toast = useToast();
  const [tid, setTid] = useState(""); const [date, setDate] = useState(addDaysISO(1)); const [reason, setReason] = useState(""); const [busy, setBusy] = useState(false);
  const ok = /^\d{4}-\d{2}-\d{2}$/.test(date) && tid;
  const save = async () => {
    setBusy(true);
    try { await api.post("/absences", { teacher_id: tid, date, reason }); toast("Absence recorded — periods listed for cover"); onDone(); onClose(); }
    catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  return (
    <Sheet open={open} onClose={onClose} title="Mark a teacher absent (full day)" testID="pcover-absent-sheet">
      <ScrollView style={{ maxHeight: 520 }} contentContainerStyle={{ gap: 10 }}>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {(t.data || []).filter((x: any) => x.status !== "inactive").map((x: any) => <Chip key={x.id} label={x.name} active={tid === x.id} onPress={() => setTid(x.id)} testID={`pabsent-teacher-${x.id}`} />)}
        </View>
        <TextField label="Date (YYYY-MM-DD)" value={date} onChangeText={setDate} autoCapitalize="none" testID="pabsent-date" />
        <TextField label="Reason" value={reason} onChangeText={setReason} testID="pabsent-reason" />
        <Button label="Mark absent" icon="user-x" onPress={save} loading={busy} disabled={!ok} testID="pabsent-save" />
      </ScrollView>
    </Sheet>
  );
}

export default function PrincipalCover() {
  const [date, setDate] = useState(todayISO());
  const subs = useSubsDay(date);
  const abs = useAbsences();
  const qc = useQueryClient();
  const toast = useToast();
  const [sub, setSub] = useState<any>(null);
  const [absentOpen, setAbsentOpen] = useState(false);
  const [cancelFor, setCancelFor] = useState<any>(null);
  const [reason, setReason] = useState("");
  const refresh = () => ["p-subs", "p-absences", "p-subdash"].forEach((x) => qc.invalidateQueries({ queryKey: [x] }));
  const days = [0, 1, 2, 3, 4, 5, 6].map((n) => addDaysISO(n));
  const rows: any[] = subs.data?.substitutions || subs.data?.items || [];
  const byAbs = new Map<string, any[]>(); rows.forEach((r) => byAbs.set(r.absence_id, [...(byAbs.get(r.absence_id) || []), r]));
  const absences = (abs.data || []).filter((a: any) => a.status === "approved" && a.date === date);
  const pending = (abs.data || []).filter((a: any) => a.status === "requested" && a.date >= todayISO());
  const review = async (a: any, ok: boolean) => {
    try { await api.post(`/absences/${a.id}/${ok ? "approve" : "reject"}`, {}); toast(ok ? "Leave approved" : "Leave rejected"); refresh(); } catch (e: any) { toast(e.message, "error"); }
  };
  const auto = async (a: any) => { try { const r = await api.post(`/absences/${a.id}/auto-assign`, {}); toast(`Auto-cover: ${r.assigned ?? r.count ?? "done"}`); refresh(); } catch (e: any) { toast(e.message, "error"); } };
  const cancel = async () => {
    try { await api.post(`/absences/${cancelFor.id}/cancel`, { reason: reason.trim() }); toast("Absence cancelled"); setCancelFor(null); setReason(""); refresh(); } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <TabScreen testID="principal-cover-screen" title="Cover" showSwitcher={false}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {days.map((d, i) => <Chip key={d} label={i === 0 ? "Today" : i === 1 ? "Tomorrow" : fmtDate(d, { weekday: true })} active={d === date} onPress={() => setDate(d)} testID={`pcover-day-${i}`} />)}
      </ScrollView>
      <Button variant="outline" icon="user-x" label="Mark a teacher absent" onPress={() => setAbsentOpen(true)} testID="pcover-mark-absent-btn" />
      {pending.length > 0 && <SectionTitle title={`Leave requests · ${pending.length}`} />}
      {pending.map((a: any) => (
        <Card key={a.id} style={{ gap: 8 }} testID={`pleave-${a.id}`}>
          <Text style={k.label}>{a.teacher_name} · {fmtDate(a.date, { weekday: true })}</Text>
          {a.reason ? <Text style={k.small}>{a.reason}</Text> : null}
          <View style={{ flexDirection: "row", gap: 8 }}>
            <Button small icon="check" label="Approve" onPress={() => review(a, true)} style={{ flex: 1 }} testID={`pleave-approve-${a.id}`} />
            <Button small variant="outline" icon="x" label="Reject" onPress={async () => { if (await confirm("Reject leave?", `${a.teacher_name} on ${a.date}`, "Reject")) review(a, false); }} style={{ flex: 1 }} testID={`pleave-reject-${a.id}`} />
          </View>
        </Card>
      ))}
      <SectionTitle title={`Absences · ${fmtDate(date, { weekday: true })}`} />
      {subs.isLoading || abs.isLoading ? <SkeletonList n={2} /> : subs.isError ? <ErrorState error={subs.error} onRetry={subs.refetch} /> : !absences.length ? <Card><Empty icon="check-circle" text="No teacher absences on this day." testID="pcover-empty" /></Card>
        : absences.map((a: any) => {
          const periods = (byAbs.get(a.id) || []).sort((x, y) => x.period_no - y.period_no);
          return (
            <Card key={a.id} style={{ gap: 10 }} testID={`pabsence-${a.id}`}>
              <Text style={k.h2}>{a.teacher_name}</Text>
              {a.reason ? <Text style={k.small}>{a.reason}</Text> : null}
              {!periods.length ? <Text style={k.small}>No timetabled periods in your divisions.</Text> : periods.map((p) => (
                <Card key={p.id} onPress={() => setSub(p)} style={{ flexDirection: "row", alignItems: "center", gap: 10, padding: 12 }} testID={`pperiod-${p.id}`}>
                  <Text style={[k.label, { width: 34 }]}>P{p.period_no}</Text>
                  <View style={{ flex: 1 }}><Text style={k.label}>{p.class_name} {p.section} · {p.subject}</Text>{p.substitute_name ? <Text style={k.small}>{p.substitute_name}</Text> : null}</View>
                  <StatusChip status={TONE[p.status] || p.status} testID={`pperiod-status-${p.id}`} />
                </Card>
              ))}
              <View style={{ flexDirection: "row", gap: 8 }}>
                <Button small icon="zap" label="Auto-cover all" onPress={() => auto(a)} style={{ flex: 1 }} testID={`pabsence-auto-${a.id}`} />
                <Button small variant="outline" icon="x-circle" label="Cancel absence" onPress={() => { setReason(""); setCancelFor(a); }} style={{ flex: 1 }} testID={`pabsence-cancel-${a.id}`} />
              </View>
            </Card>
          );
        })}
      <PeriodSheet sub={sub} onClose={() => setSub(null)} onDone={refresh} />
      <MarkAbsent open={absentOpen} onClose={() => setAbsentOpen(false)} onDone={refresh} />
      <Sheet open={Boolean(cancelFor)} onClose={() => setCancelFor(null)} title="Cancel absence" testID="pcancel-sheet">
        <View style={{ gap: 12 }}>
          <Text style={k.small}>{cancelFor ? `${cancelFor.teacher_name} · ${fmtDate(cancelFor.date, { weekday: true })}. Covers arranged for it are released.` : ""}</Text>
          <TextField label="Reason (required)" value={reason} onChangeText={setReason} testID="pcancel-reason" />
          <Button variant="danger" icon="x-circle" label="Cancel absence" onPress={cancel} disabled={reason.trim().length < 3} testID="pcancel-confirm" />
        </View>
      </Sheet>
    </TabScreen>
  );
}
