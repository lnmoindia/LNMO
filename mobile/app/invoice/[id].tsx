// Invoice detail: UPI QR (pay-info), Open UPI app, I've paid (proof), proof status, fee issue + thread.
import { useState } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { Image } from "expo-image";
import * as Clipboard from "expo-clipboard";
import { Feather } from "@expo/vector-icons";
import { useQueryClient } from "@tanstack/react-query";
import { useChild } from "@/src/state/child";
import { useBrand } from "@/src/state/auth";
import { useToast } from "@/src/state/toast";
import { useFees, usePayInfo } from "@/src/lib/queries";
import { api } from "@/src/lib/api";
import { openAuthedFile } from "@/src/lib/files";
import { StackScreen } from "@/src/ui/Screen";
import { Button, C, Card, Empty, SectionTitle, SkeletonList, StatusChip, k } from "@/src/ui/kit";
import { TextField } from "@/src/ui/inputs";
import { fmtDate, fmtDateTime, inr } from "@/src/lib/format";
import { fonts } from "@/src/theme";

export default function InvoiceDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { childId } = useChild();
  const fees = useFees(childId);
  const pay = usePayInfo(id);
  const inv = fees.data?.invoices?.find((i: any) => i.id === id);
  if (fees.isLoading || pay.isLoading) return <StackScreen title="Invoice" testID="invoice-screen"><SkeletonList n={3} height={140} /></StackScreen>;
  if (!inv) return <StackScreen title="Invoice" testID="invoice-screen"><Card><Empty icon="file" text="This invoice isn't available for the selected child." /></Card></StackScreen>;
  const proofs = (fees.data.proofs || []).filter((p: any) => p.invoice_id === id);
  const issues = (fees.data.issues || []).filter((x: any) => x.invoice_id === id);
  const last = proofs[0];
  const pending = last?.status === "pending";
  const openIssue = issues.find((i: any) => i.status === "open");
  const stale = pending && Date.now() - new Date(last.submitted_at).getTime() > 3 * 86400000;
  const canIssue = !openIssue && (inv.balance > 0 || last?.status === "rejected" || stale);
  const upi = pay.data?.upi || inv.upi;
  return (
    <StackScreen title={inv.period_label} testID="invoice-screen">
      <Card style={{ gap: 8 }} testID="invoice-summary">
        <View style={s.row}>
          <Text style={k.small}>Due {fmtDate(inv.due_date)}</Text>
          <StatusChip status={pending ? "verification_pending" : inv.status} testID="invoice-status" />
        </View>
        <Text style={s.big} testID="invoice-balance">{inr(inv.balance > 0 ? inv.balance : inv.amount_due)}</Text>
        <Text style={k.small}>{inv.balance > 0 ? `Balance of ${inr(inv.amount_due)}` : "Fully paid"}</Text>
        <View style={s.items}>
          {(inv.items || []).map((x: any, i: number) => <Line key={i} l={x.title} v={inr(x.amount)} />)}
          {inv.discount_amount ? <Line l="Discount" v={`- ${inr(inv.discount_amount)}`} /> : null}
          {inv.fine_amount ? <Line l="Late fee" v={inr(inv.fine_amount)} /> : null}
          {inv.paid_amount ? <Line l="Paid so far" v={inr(inv.paid_amount)} /> : null}
        </View>
      </Card>
      {last && <ProofStatus p={last} />}
      {upi && !pending && inv.balance > 0 && <UpiBlock upi={upi} invId={id} />}
      {inv.balance > 0 && !pending && (
        <Button label="I've paid — upload proof" icon="upload" variant="success" onPress={() => router.push(`/proof/${id}`)} testID="invoice-ive-paid-btn" />
      )}
      {canIssue && <Button label="I have already paid" icon="alert-circle" variant="outline" onPress={() => router.push(`/issue/${id}`)} testID="invoice-raise-issue-btn" />}
      {issues.map((i: any) => <IssueThread key={i.id} issue={i} />)}
    </StackScreen>
  );
}

const Line = ({ l, v }: { l: string; v: string }) => (
  <View style={s.row}><Text style={k.body}>{l}</Text><Text style={[k.body, { fontFamily: fonts.bodySemi }]}>{v}</Text></View>
);

function UpiBlock({ upi, invId }: { upi: any; invId: string }) {
  const toast = useToast();
  const openUpi = async () => {
    try {
      await Linking.openURL(upi.uri);
    } catch { toast("No UPI app found on this device — scan the QR from another phone or pay to the UPI ID.", "error"); }
  };
  const copy = async () => { await Clipboard.setStringAsync(upi.vpa); toast("UPI ID copied"); };
  return (
    <Card style={s.upi} testID={`upi-block-${invId}`}>
      <View style={s.upiHead}><Feather name="smartphone" size={18} color={C.success} /><Text style={s.upiTitle}>Pay with any UPI app</Text></View>
      <View style={s.qrWrap}><Image source={{ uri: upi.qr }} style={s.qr} contentFit="contain" testID={`upi-qr-${invId}`} /></View>
      <Text style={s.upiAmt} testID={`upi-amount-${invId}`}>{inr(upi.amount)}</Text>
      <Pressable onPress={copy} style={s.vpa} testID={`upi-copy-vpa-${invId}`}>
        <Text style={s.vpaText}>UPI ID: <Text style={{ fontFamily: fonts.bodyBold }} testID={`upi-vpa-${invId}`}>{upi.vpa}</Text></Text>
        <Feather name="copy" size={15} color={C.success} />
      </Pressable>
      <Text style={[k.small, { textAlign: "center" }]}>{upi.payee_name} · Note: {upi.note}</Text>
      {upi.instructions ? <Text style={[k.small, { textAlign: "center" }]}>{upi.instructions}</Text> : null}
      <Button label="Open UPI app" icon="external-link" variant="success" onPress={openUpi} testID={`upi-open-app-${invId}`} style={{ alignSelf: "stretch" }} />
    </Card>
  );
}

function ProofStatus({ p }: { p: any }) {
  const tone = p.status === "rejected" ? [C.errorSoft, C.error, "x-circle"] : p.status === "approved" ? [C.successSoft, C.success, "check-circle"] : [C.warningSoft, C.warning, "clock"];
  return (
    <View style={[s.proof, { backgroundColor: tone[0] }]} testID={`proof-status-${p.id}`}>
      <Feather name={tone[2] as any} size={20} color={tone[1]} />
      <Text style={[s.proofText, { color: tone[1] }]}>
        {p.status === "pending" && `Verification pending — ${inr(p.amount)} paid on ${fmtDate(p.paid_on)}${p.utr ? ` · UTR ${p.utr}` : ""}. The school will verify it and send a receipt.`}
        {p.status === "approved" && `Verified — receipt ${p.receipt_no}`}
        {p.status === "rejected" && `Proof not accepted: ${p.reject_reason}. You can upload a new proof.`}
      </Text>
    </View>
  );
}

function IssueThread({ issue }: { issue: any }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();
  const b = useBrand();
  const send = async () => {
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("message", text);
      await api.postForm(`/parent/fees/issues/${issue.id}/messages`, fd);
      setText(""); qc.invalidateQueries({ queryKey: ["fees"] });
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  const file = async (m: any) => {
    try { await openAuthedFile(`/fees/issues/${issue.id}/messages/${m.id}/file`, `attachment-${m.id}`, "image/jpeg"); } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <Card style={{ gap: 10 }} testID={`issue-thread-${issue.id}`}>
      <View style={s.row}><SectionTitle title="Fee issue" /><StatusChip status={issue.status} testID={`issue-status-${issue.id}`} /></View>
      {issue.messages.map((m: any) => (
        <View key={m.id} style={[s.msg, { backgroundColor: m.by === "staff" ? b.soft : C.surfaceTertiary }]} testID={`issue-msg-${m.id}`}>
          <Text style={k.small}>{m.by === "staff" ? "School" : m.by_name} · {fmtDateTime(m.at)}</Text>
          <Text style={k.body}>{m.text}</Text>
          {m.has_file && <Pressable onPress={() => file(m)} hitSlop={8}><Text style={[k.label, { color: b.ink }]}>View attachment</Text></Pressable>}
        </View>
      ))}
      {issue.status === "open" && (
        <View style={{ gap: 8 }}>
          <TextField value={text} onChangeText={setText} placeholder="Write a reply…" multiline testID={`issue-reply-input-${issue.id}`} style={{ minHeight: 70 }} />
          <Button small label="Send reply" icon="send" onPress={send} loading={busy} disabled={!text.trim()} testID={`issue-reply-send-${issue.id}`} />
        </View>
      )}
    </Card>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 },
  big: { fontFamily: fonts.heading, fontSize: 32, color: C.onSurface },
  items: { gap: 6, marginTop: 6, paddingTop: 12, borderTopWidth: 1, borderTopColor: C.divider },
  upi: { alignItems: "center", gap: 10, borderColor: "#A7F3D0", backgroundColor: "#F3FBF7" },
  upiHead: { flexDirection: "row", gap: 8, alignItems: "center" },
  upiTitle: { fontFamily: fonts.bodyBold, fontSize: 16, color: C.onSurface },
  qrWrap: { backgroundColor: "#fff", padding: 10, borderRadius: 18, borderWidth: 1, borderColor: C.border },
  qr: { width: 210, height: 210 },
  upiAmt: { fontFamily: fonts.heading, fontSize: 28, color: C.success },
  vpa: { flexDirection: "row", alignItems: "center", gap: 8, minHeight: 40, paddingHorizontal: 14, borderRadius: 12, backgroundColor: "#fff", borderWidth: 1, borderColor: "#A7F3D0" },
  vpaText: { fontFamily: fonts.body, fontSize: 14, color: C.onSurface },
  proof: { flexDirection: "row", gap: 10, alignItems: "flex-start", padding: 16, borderRadius: 18 },
  proofText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 14, lineHeight: 20 },
  msg: { padding: 12, borderRadius: 14, gap: 3 },
});
