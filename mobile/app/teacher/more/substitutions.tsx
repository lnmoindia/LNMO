// My substitutions — mirrors web TeacherSubstitutions: cover requests (accept/decline), assigned cover, my leave (+cancel), request leave.
import { useState } from "react";
import { Text, View } from "react-native";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/src/state/auth";
import { useToast } from "@/src/state/toast";
import { useMySubs } from "@/src/lib/queries";
import { api } from "@/src/lib/api";
import { StackScreen } from "@/src/ui/Screen";
import { Button, Card, Empty, ErrorState, SectionTitle, SkeletonList, StatusChip, k } from "@/src/ui/kit";
import { Sheet } from "@/src/ui/brandbits";
import { TextField } from "@/src/ui/inputs";
import { fmtDate, todayISO } from "@/src/lib/format";

const label = (r: any) => `${r.class_name} ${r.section || ""} · P${r.period_no} · ${r.subject}`;

function Request({ r, onDone }: { r: any; onDone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<"" | "y" | "n">("");
  const respond = async (accept: boolean) => {
    setBusy(accept ? "y" : "n");
    try { await api.post(`/substitutions/${r.id}/respond`, { accept }); toast(accept ? "Accepted" : "Declined"); onDone(); }
    catch (e: any) { toast(e.message, "error"); } finally { setBusy(""); }
  };
  return (
    <Card style={{ gap: 10 }} testID={`tsub-request-${r.id}`}>
      <Text style={k.label}>{label(r)}</Text>
      <Text style={k.small}>{fmtDate(r.date, { weekday: true })}</Text>
      <View style={{ flexDirection: "row", gap: 8 }}>
        <Button small icon="check" label="Accept" onPress={() => respond(true)} loading={busy === "y"} disabled={Boolean(busy)} style={{ flex: 1 }} testID={`tsub-accept-${r.id}`} />
        <Button small icon="x" label="Decline" variant="outline" onPress={() => respond(false)} loading={busy === "n"} disabled={Boolean(busy)} style={{ flex: 1 }} testID={`tsub-decline-${r.id}`} />
      </View>
    </Card>
  );
}

const Assigned = ({ r }: { r: any }) => (
  <Card style={{ gap: 4 }} testID={`tsub-assigned-${r.id}`}>
    <Text style={k.label}>{label(r)}</Text>
    <Text style={k.small}>{fmtDate(r.date, { weekday: true })}</Text>
  </Card>
);

function Leave({ a, onCancel }: { a: any; onCancel: () => void }) {
  return (
    <Card style={{ gap: 6 }} testID={`tsub-leave-${a.id}`}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <Text style={[k.label, { flex: 1 }]}>{fmtDate(a.date, { weekday: true, year: true })}</Text>
        <StatusChip status={a.status} testID={`tsub-leave-status-${a.id}`} />
      </View>
      {a.reason ? <Text style={k.small}>{a.reason}</Text> : null}
      {(a.status === "requested" || a.status === "approved") && a.date > todayISO() && (
        <Button small variant="outline" icon="x-circle" label="Cancel leave" onPress={onCancel} testID={`tsub-cancel-leave-${a.id}`} />
      )}
    </Card>
  );
}

export default function TeacherSubs() {
  const { user } = useAuth();
  const q = useMySubs();
  const mine = useQuery({ queryKey: ["t-absences"], queryFn: async () => (await api.get("/absences")).absences || [] });
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [cancelFor, setCancelFor] = useState<any>(null);
  const [date, setDate] = useState(todayISO());
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["t-subs"] }); qc.invalidateQueries({ queryKey: ["t-absences"] }); };
  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(date.trim());
  const requestLeave = async () => {
    setBusy(true);
    try { await api.post("/absences", { teacher_id: user.id, date: date.trim(), reason: reason.trim() }); toast("Leave requested — awaiting approval"); setOpen(false); setReason(""); setDate(todayISO()); refresh(); }
    catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  const cancelLeave = async () => {
    setBusy(true);
    try { await api.post(`/absences/${cancelFor.id}/cancel`, { reason: reason.trim() }); toast("Leave cancelled"); setCancelFor(null); setReason(""); refresh(); }
    catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  const requests = q.data?.requests || [];
  const assigned = q.data?.assigned || [];
  const myLeave = (mine.data || []).filter((a: any) => a.teacher_id === user?.id);
  return (
    <StackScreen title="My substitutions" testID="teacher-subs-screen">
      <Button icon="plus" label="Request leave" onPress={() => { setReason(""); setOpen(true); }} testID="tsub-request-leave-btn" />
      {q.isLoading ? <SkeletonList n={3} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : (
        <>
          <SectionTitle title={`Cover requests${requests.length ? ` · ${requests.length}` : ""}`} />
          {!requests.length ? <Card><Empty icon="clock" text="No pending cover requests." /></Card> : requests.map((r: any) => <Request key={r.id} r={r} onDone={refresh} />)}
          <SectionTitle title="My assigned cover" />
          {!assigned.length ? <Card><Empty icon="check-circle" text="You have no assigned substitutions." /></Card> : assigned.map((r: any) => <Assigned key={r.id} r={r} />)}
        </>
      )}
      <SectionTitle title="My leave" />
      {mine.isLoading ? <SkeletonList n={1} /> : !myLeave.length ? <Card><Empty icon="calendar" text="No leave on record." /></Card>
        : myLeave.map((a: any) => <Leave key={a.id} a={a} onCancel={() => { setReason(""); setCancelFor(a); }} />)}

      <Sheet open={open} onClose={() => setOpen(false)} title="Request leave" testID="tsub-leave-sheet">
        <View style={{ gap: 12 }}>
          <Text style={k.small}>Your principal or admin will approve it and arrange cover.</Text>
          <TextField label="Date (YYYY-MM-DD)" value={date} onChangeText={setDate} autoCapitalize="none" keyboardType="numbers-and-punctuation" error={date && !validDate ? "Use the format 2026-10-21" : undefined} testID="leave-date-input" />
          <TextField label="Reason (optional)" value={reason} onChangeText={setReason} testID="leave-reason-input" />
          <Button label="Request" icon="send" onPress={requestLeave} loading={busy} disabled={!validDate} testID="leave-submit-btn" />
        </View>
      </Sheet>
      <Sheet open={Boolean(cancelFor)} onClose={() => setCancelFor(null)} title="Cancel leave" testID="tsub-cancel-sheet">
        <View style={{ gap: 12 }}>
          <Text style={k.small}>{cancelFor ? `Leave on ${fmtDate(cancelFor.date, { weekday: true })}. Any cover arranged for it will be released.` : ""}</Text>
          <TextField label="Reason (min 3 characters)" value={reason} onChangeText={(t) => setReason(t.slice(0, 300))} placeholder="e.g. Plans changed, I'll be at school" testID="cancel-reason-input" />
          <Button label="Cancel leave" icon="x-circle" variant="danger" onPress={cancelLeave} loading={busy} disabled={reason.trim().length < 3} testID="cancel-leave-confirm-btn" />
        </View>
      </Sheet>
    </StackScreen>
  );
}
