// Fees for my divisions: Day Book · Defaulters (remind) · Payment proofs (approve/reject) · Fee issues (reply/resolve).
import { useEffect, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Image } from "expo-image";
import { API, api, authHeaders } from "@/src/lib/api";
import { useToast } from "@/src/state/toast";
import { TabScreen } from "@/src/ui/Screen";
import { Button, Card, Chip, Divider, Empty, ErrorState, SkeletonList, k } from "@/src/ui/kit";
import { Sheet, confirm } from "@/src/ui/brandbits";
import { TextField } from "@/src/ui/inputs";
import { fmtDate, fmtDateTime, inr, todayISO } from "@/src/lib/format";

const Row = ({ l, r, testID }: { l: string; r: string; testID?: string }) => (
  <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8, paddingVertical: 8 }} testID={testID}><Text style={[k.label, { flex: 1 }]}>{l}</Text><Text style={k.label}>{r}</Text></View>
);

function DayBook() {
  const q = useQuery({ queryKey: ["p-daybook", todayISO()], queryFn: () => api.get(`/fees/day-book?date=${todayISO()}`) });
  if (q.isLoading) return <SkeletonList n={2} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={q.refetch} />;
  const d = q.data;
  return (
    <>
      <Card style={{ gap: 4 }} testID="pbook-summary"><Text style={k.small}>Collected {fmtDate(d.date, { weekday: true })}</Text><Text style={k.h1} testID="pbook-total">{inr(d.summary?.total)}</Text><Text style={k.small}>{d.summary?.count || 0} payments{d.summary?.reversed_count ? ` · ${d.summary.reversed_count} reversed` : ""}</Text></Card>
      {(d.by_method || []).length > 0 && <Card style={{ paddingVertical: 6 }}>{d.by_method.map((m: any, i: number) => <View key={m.method || i}>{i > 0 && <Divider />}<Row l={String(m.method || m.label || "—").toUpperCase()} r={`${inr(m.total ?? m.amount)} · ${m.count}`} /></View>)}</Card>}
      {!(d.payments || []).length ? <Card><Empty icon="inbox" text="No payments recorded today." /></Card> : d.payments.map((p: any) => (
        <Card key={p.id || p.receipt_no} style={{ gap: 2 }} testID={`pbook-pay-${p.id || p.receipt_no}`}>
          <Row l={p.student_name || "—"} r={inr(p.amount)} />
          <Text style={k.small}>{[p.class_name && `${p.class_name} ${p.section || ""}`, String(p.method || "").toUpperCase(), p.receipt_no, p.reference].filter(Boolean).join(" · ")}</Text>
        </Card>
      ))}
    </>
  );
}

function Defaulters() {
  const toast = useToast();
  const [cls, setCls] = useState(""); const [bucket, setBucket] = useState(""); const [sel, setSel] = useState<string[]>([]); const [busy, setBusy] = useState(false); const [res, setRes] = useState<any>(null);
  const q = useQuery({ queryKey: ["p-def", cls, bucket], queryFn: () => api.get(`/fees/defaulters?page_size=200${cls ? `&class_name=${encodeURIComponent(cls)}` : ""}${bucket ? `&bucket=${encodeURIComponent(bucket)}` : ""}`) });
  const rows = q.data?.rows || [];
  const remind = async (ids: string[]) => {
    if (!(await confirm("Send reminders?", `Remind the parents of ${ids.length} student(s). Recently reminded ones are skipped automatically.`, "Send"))) return;
    setBusy(true);
    try { const r = await api.post("/fees/defaulters/remind", { student_ids: ids }); setRes(r); setSel([]); } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  return (
    <>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        <Chip label="All classes" active={!cls} onPress={() => setCls("")} testID="pdef-class-all" />
        {(q.data?.filters?.classes || []).map((c: any) => { const v = c.value ?? c; return <Chip key={v} label={c.label ?? v} active={cls === v} onPress={() => setCls(v)} testID={`pdef-class-${v}`.replace(/\s/g, "")} />; })}
      </ScrollView>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {["", "1-30", "31-60", "60+"].map((b) => <Chip key={b || "any"} label={b ? `${b} days` : "Any age"} count={b ? q.data?.buckets?.[b] : undefined} active={bucket === b} onPress={() => setBucket(b)} testID={`pdef-bucket-${b || "any"}`} />)}
      </ScrollView>
      {q.data && <Text style={k.small} testID="pdef-totals">{q.data.totals?.students} students · {inr(q.data.totals?.overdue)} overdue</Text>}
      {q.data?.can_remind && rows.length > 0 && <Button icon="bell" label={sel.length ? `Remind selected (${sel.length})` : `Remind all shown (${rows.length})`} loading={busy} onPress={() => remind(sel.length ? sel : rows.map((r: any) => r.student_id))} testID="pdef-remind-btn" />}
      {q.isLoading ? <SkeletonList n={3} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !rows.length ? <Card><Empty icon="check-circle" text="No overdue fees here." /></Card> : rows.map((r: any) => (
        <Card key={r.student_id} onPress={() => setSel((s) => (s.includes(r.student_id) ? s.filter((x) => x !== r.student_id) : [...s, r.student_id]))}
          style={{ gap: 2, borderWidth: sel.includes(r.student_id) ? 2 : 1, borderColor: sel.includes(r.student_id) ? "#3F6B8A" : undefined }} testID={`pdef-row-${r.student_id}`}>
          <Row l={r.student_name} r={inr(r.overdue_amount)} />
          <Text style={k.small}>{r.admission_no} · {r.class_name} {r.section} · {r.days_late} days late · {r.parent_name || "no parent"}</Text>
        </Card>
      ))}
      <Sheet open={Boolean(res)} onClose={() => setRes(null)} title="Reminder results" testID="pdef-results">
        <ScrollView style={{ maxHeight: 460 }} contentContainerStyle={{ gap: 6 }}>
          {res?.summary && <Text style={k.label} testID="pdef-results-summary">{Object.entries(res.summary).map(([a, b]) => `${a.replace(/_/g, " ")}: ${b}`).join(" · ")}</Text>}
          {(res?.results || []).map((x: any, i: number) => <Row key={x.student_id || i} l={x.student_name || x.student_id} r={String(x.status || "").replace(/_/g, " ")} />)}
        </ScrollView>
      </Sheet>
    </>
  );
}

function ProofSheet({ p, onClose, onDone }: { p: any; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [amount, setAmount] = useState(""); const [utr, setUtr] = useState(""); const [reason, setReason] = useState(""); const [busy, setBusy] = useState("");
  useEffect(() => { setAmount(p ? String(p.amount ?? "") : ""); setUtr(p?.utr || ""); setReason(""); }, [p]);
  if (!p) return null;
  const go = async (kind: "approve" | "reject") => {
    if (kind === "reject" && !(await confirm("Reject this proof?", "The parent sees your reason and can upload again.", "Reject"))) return;
    setBusy(kind);
    try {
      await api.post(`/fees/proofs/${p.id}/${kind}`, kind === "approve" ? { amount: Number(amount) || undefined, utr: utr.trim() || undefined } : { reason: reason.trim() });
      toast(kind === "approve" ? "Approved — payment recorded" : "Proof rejected"); onDone(); onClose();
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(""); }
  };
  return (
    <Sheet open onClose={onClose} title={`${p.student_name} · ${p.period_label}`} testID="pproof-sheet">
      <ScrollView style={{ maxHeight: 560 }} contentContainerStyle={{ gap: 10 }} keyboardShouldPersistTaps="handled">
        <Image source={{ uri: `${API}/fees/proofs/${p.id}/file`, headers: authHeaders() }} style={{ width: "100%", height: 260, borderRadius: 12, backgroundColor: "#EEF1F4" }} contentFit="contain" testID="pproof-image" />
        <Text style={k.small}>Paid on {fmtDate(p.paid_on)} · submitted {fmtDateTime(p.created_at)}{p.note ? ` · “${p.note}”` : ""}</Text>
        <TextField label="Amount (₹)" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" testID="pproof-amount" />
        <TextField label="UTR / reference" value={utr} onChangeText={setUtr} autoCapitalize="characters" testID="pproof-utr" />
        <Button icon="check" label="Approve" loading={busy === "approve"} disabled={!(Number(amount) > 0)} onPress={() => go("approve")} testID="pproof-approve" />
        <TextField label="Reason to reject (min 3 characters)" value={reason} onChangeText={setReason} testID="pproof-reason" />
        <Button variant="outline" icon="x" label="Reject" loading={busy === "reject"} disabled={reason.trim().length < 3} onPress={() => go("reject")} testID="pproof-reject" />
      </ScrollView>
    </Sheet>
  );
}

function Proofs() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["p-proofs"], queryFn: async () => (await api.get("/fees/proofs?status=pending")).proofs || [] });
  const [p, setP] = useState<any>(null);
  const done = () => ["p-proofs", "p-proofstats", "p-daybook"].forEach((x) => qc.invalidateQueries({ queryKey: [x] }));
  return (
    <>
      {q.isLoading ? <SkeletonList n={2} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !q.data.length ? <Card><Empty icon="check-circle" text="No payment proofs waiting." /></Card> : q.data.map((x: any) => (
        <Card key={x.id} onPress={() => setP(x)} style={{ gap: 2 }} testID={`pproof-${x.id}`}>
          <Row l={x.student_name} r={inr(x.amount)} /><Text style={k.small}>{x.class_name} {x.section} · {x.period_label} · UTR {x.utr || "—"}</Text>
        </Card>
      ))}
      <ProofSheet p={p} onClose={() => setP(null)} onDone={done} />
    </>
  );
}

function Issues() {
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["p-issues"], queryFn: async () => (await api.get("/fees/issues")).issues || [] });
  const [it, setIt] = useState<any>(null); const [text, setText] = useState(""); const [busy, setBusy] = useState(false);
  const send = async (resolve: boolean) => {
    setBusy(true);
    try { await api.post(`/fees/issues/${it.id}/reply`, { text: text.trim(), resolve }); toast(resolve ? "Replied and resolved" : "Reply sent"); setIt(null); setText(""); qc.invalidateQueries({ queryKey: ["p-issues"] }); qc.invalidateQueries({ queryKey: ["p-proofstats"] }); }
    catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  return (
    <>
      {q.isLoading ? <SkeletonList n={2} /> : !q.data?.length ? <Card><Empty icon="check-circle" text="No fee issues." /></Card> : q.data.map((x: any) => (
        <Card key={x.id} onPress={() => { setText(""); setIt(x); }} style={{ gap: 2 }} testID={`pissue-${x.id}`}>
          <Row l={x.student_name} r={x.status} /><Text style={k.small}>{x.class_name} {x.section} · {x.period_label} · by {x.raised_by_name}</Text>
        </Card>
      ))}
      <Sheet open={Boolean(it)} onClose={() => setIt(null)} title={it ? `${it.student_name} · ${it.period_label}` : ""} testID="pissue-sheet">
        <ScrollView style={{ maxHeight: 520 }} contentContainerStyle={{ gap: 8 }} keyboardShouldPersistTaps="handled">
          {(it?.messages || []).map((m: any) => <Card key={m.id} style={{ padding: 12 }}><Text style={k.small}>{m.by_name} · {fmtDateTime(m.at)}</Text><Text style={k.body}>{m.text}</Text></Card>)}
          <TextField label="Reply" value={text} onChangeText={setText} multiline testID="pissue-reply-input" />
          <Button icon="send" label="Reply" loading={busy} disabled={!text.trim()} onPress={() => send(false)} testID="pissue-reply-btn" />
          <Button variant="outline" icon="check-circle" label="Reply & resolve" loading={busy} disabled={!text.trim()} onPress={() => send(true)} testID="pissue-resolve-btn" />
        </ScrollView>
      </Sheet>
    </>
  );
}

const TABS = [["book", "Day Book"], ["defaulters", "Defaulters"], ["proofs", "Proofs"], ["issues", "Issues"]] as const;

export default function PrincipalFees() {
  const { tab: initial } = useLocalSearchParams<{ tab?: string }>();
  const [tab, setTab] = useState<string>(initial || "book");
  useEffect(() => { if (initial) setTab(initial); }, [initial]);
  return (
    <TabScreen testID="principal-fees-screen" title="Fees" showSwitcher={false}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {TABS.map(([key, label]) => <Chip key={key} label={label} active={tab === key} onPress={() => setTab(key)} testID={`pfees-tab-${key}`} />)}
      </ScrollView>
      {tab === "book" ? <DayBook /> : tab === "defaulters" ? <Defaulters /> : tab === "proofs" ? <Proofs /> : <Issues />}
      <Text style={k.small}>Counter collection stays on the web (receipt printing).</Text>
    </TabScreen>
  );
}
