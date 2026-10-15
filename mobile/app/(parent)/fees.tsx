import { Pressable, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useChild } from "@/src/state/child";
import { useBrand } from "@/src/state/auth";
import { useToast } from "@/src/state/toast";
import { useFees } from "@/src/lib/queries";
import { openAuthedFile } from "@/src/lib/files";
import { TabScreen } from "@/src/ui/Screen";
import { Button, C, Card, Empty, ErrorState, SectionTitle, SkeletonList, StatusChip, k } from "@/src/ui/kit";
import { fmtDate, inr } from "@/src/lib/format";
import { fonts } from "@/src/theme";

export const invStatus = (inv: any, proofs: any[]) => {
  const p = (proofs || []).filter((x) => x.invoice_id === inv.id)[0];
  return p?.status === "pending" ? "verification_pending" : inv.status;
};

export default function Fees() {
  const { childId } = useChild();
  const q = useFees(childId);
  const toast = useToast();
  const d = q.data;
  const statement = async () => {
    try { await openAuthedFile(`/parent/child/${childId}/fees/statement.pdf`, "fee-statement.pdf"); } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <TabScreen testID="fees-screen" title="Fees">
      {q.isLoading || !childId ? <SkeletonList n={4} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !d?.invoices?.length ? (
        <Card><Empty icon="credit-card" title="No fee invoices yet" text="Invoices from the school will show up here." /></Card>
      ) : (
        <>
          <Summary s={d.summary} />
          <Button label="Download statement (PDF)" icon="file-text" variant="outline" onPress={statement} testID="fees-statement-btn" />
          <SectionTitle title="Invoices" />
          {d.invoices.map((i: any) => <InvoiceCard key={i.id} inv={i} status={invStatus(i, d.proofs)} />)}
          {d.payments?.length > 0 && (
            <>
              <SectionTitle title="Receipts" />
              <Card style={{ padding: 0 }} testID="fees-receipts">
                {d.payments.map((p: any, idx: number) => <ReceiptRow key={p.id} p={p} last={idx === d.payments.length - 1} />)}
              </Card>
            </>
          )}
        </>
      )}
    </TabScreen>
  );
}

function Summary({ s: sm }: { s: any }) {
  const b = useBrand();
  return (
    <View style={[st.summary, { backgroundColor: b.ink }]} testID="fees-summary">
      <Text style={st.sumLabel}>Balance due</Text>
      <Text style={st.sumBig} testID="fees-balance">{inr(sm.balance)}</Text>
      {sm.overdue ? <View style={st.overdue}><Feather name="alert-circle" size={13} color="#fff" /><Text style={st.overdueText}>{sm.overdue} overdue</Text></View> : null}
      <View style={st.sumRow}>
        <Tile label="Total" value={inr(sm.total)} testID="fees-total" />
        <Tile label="Paid" value={inr(sm.paid)} testID="fees-paid" />
        <Tile label="Next due" value={sm.next_due ? fmtDate(sm.next_due, { year: false }) : "—"} testID="fees-next-due" />
      </View>
    </View>
  );
}
const Tile = ({ label, value, testID }: { label: string; value: string; testID: string }) => (
  <View style={{ flex: 1 }}><Text style={st.tileLabel}>{label}</Text><Text style={st.tileValue} testID={testID} numberOfLines={1}>{value}</Text></View>
);

function InvoiceCard({ inv, status }: { inv: any; status: string }) {
  const b = useBrand();
  return (
    <Card onPress={() => router.push(`/invoice/${inv.id}`)} testID={`fees-invoice-${inv.id}`} style={{ gap: 10 }}>
      <View style={st.invTop}>
        <View style={{ flex: 1 }}>
          <Text style={st.invTitle}>{inv.period_label}</Text>
          <Text style={k.small}>Due {fmtDate(inv.due_date)}</Text>
        </View>
        <StatusChip status={status} testID={`fees-invoice-status-${inv.id}`} />
      </View>
      <Text style={k.small} numberOfLines={1}>{(inv.items || []).map((x: any) => x.title).join(", ")}</Text>
      <View style={st.invBottom}>
        <View>
          <Text style={st.amount}>{inr(inv.amount_due)}</Text>
          {inv.balance > 0 && inv.paid_amount > 0 ? <Text style={k.small}>Balance {inr(inv.balance)}</Text> : null}
        </View>
        {inv.balance > 0 && status !== "verification_pending" ? (
          <View style={[st.payPill, { backgroundColor: b.color }]}><Text style={[st.payText, { color: b.onColor }]}>Pay</Text></View>
        ) : <Feather name="chevron-right" size={22} color={C.muted} />}
      </View>
    </Card>
  );
}

function ReceiptRow({ p, last }: { p: any; last: boolean }) {
  const b = useBrand();
  const toast = useToast();
  const dl = async () => {
    try { await openAuthedFile(`/fees/payments/${p.id}/receipt.pdf`, `receipt-${p.receipt_no || p.id}.pdf`); } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <Pressable onPress={dl} testID={`fees-receipt-${p.id}`} style={({ pressed }) => [st.receipt, !last && st.receiptLine, pressed && { backgroundColor: C.surfaceTertiary }]}>
      <View style={[st.rIcon, { backgroundColor: C.successSoft }]}><Feather name="check" size={18} color={C.success} /></View>
      <View style={{ flex: 1 }}>
        <Text style={st.rTitle}>{p.receipt_no}</Text>
        <Text style={k.small}>{p.period_label} · {fmtDate(p.paid_on || p.collected_at)} · {String(p.method || "").toUpperCase()}</Text>
      </View>
      <View style={{ alignItems: "flex-end", gap: 4 }}>
        <Text style={st.rAmt}>{inr(p.amount)}</Text>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}><Feather name="share" size={13} color={b.ink} /><Text style={[st.rShare, { color: b.ink }]}>PDF</Text></View>
      </View>
    </Pressable>
  );
}

const st = StyleSheet.create({
  summary: { borderRadius: 24, padding: 20, gap: 4 },
  sumLabel: { fontFamily: fonts.bodySemi, fontSize: 13, color: "rgba(255,255,255,0.75)", textTransform: "uppercase", letterSpacing: 0.8 },
  sumBig: { fontFamily: fonts.heading, fontSize: 34, color: "#fff" },
  overdue: { flexDirection: "row", gap: 5, alignItems: "center", alignSelf: "flex-start", backgroundColor: "rgba(190,18,60,0.85)", paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999 },
  overdueText: { fontFamily: fonts.bodyBold, fontSize: 12, color: "#fff" },
  sumRow: { flexDirection: "row", gap: 12, marginTop: 14, paddingTop: 14, borderTopWidth: 1, borderTopColor: "rgba(255,255,255,0.18)" },
  tileLabel: { fontFamily: fonts.body, fontSize: 12, color: "rgba(255,255,255,0.7)" },
  tileValue: { fontFamily: fonts.bodyBold, fontSize: 15, color: "#fff", marginTop: 2 },
  invTop: { flexDirection: "row", alignItems: "flex-start", gap: 10 },
  invTitle: { fontFamily: fonts.heading, fontSize: 18, color: C.onSurface },
  invBottom: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  amount: { fontFamily: fonts.heading, fontSize: 20, color: C.onSurface },
  payPill: { paddingHorizontal: 22, minHeight: 42, borderRadius: 14, justifyContent: "center" },
  payText: { fontFamily: fonts.bodyBold, fontSize: 15 },
  receipt: { flexDirection: "row", alignItems: "center", gap: 12, padding: 14, minHeight: 68 },
  receiptLine: { borderBottomWidth: 1, borderBottomColor: C.divider },
  rIcon: { width: 38, height: 38, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  rTitle: { fontFamily: fonts.bodyBold, fontSize: 15, color: C.onSurface },
  rAmt: { fontFamily: fonts.bodyBold, fontSize: 15, color: C.onSurface },
  rShare: { fontFamily: fonts.bodySemi, fontSize: 12 },
});
