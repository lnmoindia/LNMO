// Student's own fees — read-only (the web student portal is read-only too; payments are done by parents).
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Feather } from "@expo/vector-icons";
import { useMyFees } from "@/src/lib/queries";
import { useBrand } from "@/src/state/auth";
import { useToast } from "@/src/state/toast";
import { openAuthedFile } from "@/src/lib/files";
import { StackScreen } from "@/src/ui/Screen";
import { C, Card, Empty, ErrorState, SectionTitle, SkeletonList, StatusChip, k } from "@/src/ui/kit";
import { fmtDate, inr } from "@/src/lib/format";
import { fonts } from "@/src/theme";

export default function StudentFees() {
  const q = useMyFees();
  const b = useBrand();
  const toast = useToast();
  const d = q.data;
  const sm = d?.summary;
  const receipt = (p: any) => openAuthedFile(`/fees/payments/${p.id}/receipt.pdf`, `receipt-${p.receipt_no || p.id}.pdf`).catch((e) => toast(e.message, "error"));
  return (
    <StackScreen title="Fees" testID="student-fees-screen">
      {q.isLoading ? <SkeletonList n={3} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !d?.invoices?.length ? (
        <Card><Empty icon="credit-card" text="No fee invoices yet." testID="student-fees-empty" /></Card>
      ) : (
        <>
          <View style={[s.summary, { backgroundColor: b.ink }]} testID="student-fees-summary">
            <Text style={s.label}>Balance due</Text>
            <Text style={s.big} testID="student-fees-balance">{inr(sm.balance)}</Text>
            <View style={s.tiles}>
              {[["Total", inr(sm.total)], ["Paid", inr(sm.paid)], ["Next due", sm.next_due ? fmtDate(sm.next_due, { year: false }) : "—"]].map(([l, v]) => (
                <View key={l} style={{ flex: 1 }}><Text style={s.tLabel}>{l}</Text><Text style={s.tVal} numberOfLines={1}>{v}</Text></View>
              ))}
            </View>
          </View>
          <Text style={k.small}>Payments are made by your parent in the parent app.</Text>
          <SectionTitle title="Invoices" />
          {d.invoices.map((i: any) => {
            const pending = (d.proofs || []).find((p: any) => p.invoice_id === i.id)?.status === "pending";
            return (
              <Card key={i.id} style={{ gap: 6 }} testID={`student-fees-invoice-${i.id}`}>
                <View style={s.row}><Text style={s.title}>{i.period_label}</Text><StatusChip status={pending ? "verification_pending" : i.status} /></View>
                <Text style={k.small}>Due {fmtDate(i.due_date)} · {(i.items || []).map((x: any) => x.title).join(", ")}</Text>
                <Text style={s.amt}>{inr(i.amount_due)}{i.balance > 0 && i.paid_amount > 0 ? <Text style={k.small}>  · balance {inr(i.balance)}</Text> : null}</Text>
              </Card>
            );
          })}
          {d.payments?.length > 0 && <SectionTitle title="Receipts" />}
          {(d.payments || []).map((p: any) => (
            <Pressable key={p.id} onPress={() => receipt(p)} style={({ pressed }) => [s.receipt, pressed && { opacity: 0.85 }]} testID={`student-fees-receipt-${p.id}`}>
              <Feather name="check-circle" size={20} color={C.success} />
              <View style={{ flex: 1 }}><Text style={s.title}>{p.receipt_no}</Text><Text style={k.small}>{p.period_label} · {fmtDate(p.paid_on || p.collected_at)}</Text></View>
              <Text style={s.amt}>{inr(p.amount)}</Text>
              <Feather name="share" size={16} color={b.ink} />
            </Pressable>
          ))}
        </>
      )}
    </StackScreen>
  );
}

const s = StyleSheet.create({
  summary: { borderRadius: 24, padding: 20, gap: 4 },
  label: { fontFamily: fonts.bodySemi, fontSize: 13, color: "rgba(255,255,255,0.75)", textTransform: "uppercase", letterSpacing: 0.8 },
  big: { fontFamily: fonts.heading, fontSize: 32, color: "#fff" },
  tiles: { flexDirection: "row", gap: 12, marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: "rgba(255,255,255,0.18)" },
  tLabel: { fontFamily: fonts.body, fontSize: 12, color: "rgba(255,255,255,0.7)" },
  tVal: { fontFamily: fonts.bodyBold, fontSize: 15, color: "#fff" },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  title: { fontFamily: fonts.bodyBold, fontSize: 16, color: C.onSurface },
  amt: { fontFamily: fonts.heading, fontSize: 17, color: C.onSurface },
  receipt: { flexDirection: "row", alignItems: "center", gap: 12, padding: 14, borderRadius: 18, backgroundColor: "#fff", borderWidth: 1, borderColor: C.border, minHeight: 64 },
});
