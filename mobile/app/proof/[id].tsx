// "I've paid" — screenshot (gallery/camera) + UTR + amount + date → POST /parent/fees/invoices/{id}/proofs
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { useChild } from "@/src/state/child";
import { useToast } from "@/src/state/toast";
import { useFees } from "@/src/lib/queries";
import { api } from "@/src/lib/api";
import { appendFile, type Picked } from "@/src/lib/files";
import { PhotoPicker } from "@/src/ui/PhotoPicker";
import { StackScreen } from "@/src/ui/Screen";
import { Button, C, Card, Chip, k } from "@/src/ui/kit";
import { TextField } from "@/src/ui/inputs";
import { addDaysISO, inr, todayISO } from "@/src/lib/format";
import { fonts } from "@/src/theme";

export default function ProofUpload() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { childId } = useChild();
  const fees = useFees(childId);
  const inv = fees.data?.invoices?.find((i: any) => i.id === id);
  const qc = useQueryClient();
  const toast = useToast();
  const [file, setFile] = useState<Picked | null>(null);
  const [amount, setAmount] = useState(inv ? String(inv.balance) : "");
  const [utr, setUtr] = useState("");
  const [paidOn, setPaidOn] = useState(todayISO());
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const amt = Number(amount);
  const bal = inv?.balance || 0;
  const badAmt = !(amt > 0) || amt > bal;
  const badDate = !/^\d{4}-\d{2}-\d{2}$/.test(paidOn) || paidOn > todayISO();

  const submit = async () => {
    if (!file) return toast("Please attach the payment screenshot", "error");
    setBusy(true);
    try {
      const fd = new FormData();
      await appendFile(fd, "file", file);
      fd.append("amount", String(amt)); fd.append("paid_on", paidOn); fd.append("utr", utr); fd.append("note", note);
      const d = await api.postForm(`/parent/fees/invoices/${id}/proofs`, fd);
      toast(d?.utr_warning?.length ? "Submitted — this UTR was used before; the school will check it." : "Thanks! The school will verify your payment and send a receipt.");
      await qc.invalidateQueries({ queryKey: ["fees"] });
      await qc.invalidateQueries({ queryKey: ["payinfo", id] });
      router.back();
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };

  return (
    <StackScreen title="I've paid" testID="proof-upload-screen" keyboard>
      <Card style={{ gap: 4 }}>
        <Text style={s.title}>{inv?.period_label || "Invoice"}</Text>
        <Text style={k.body}>Balance {inr(bal)}. Upload the UPI/bank screenshot — the school verifies it and issues a receipt.</Text>
      </Card>
      <PhotoPicker file={file} setFile={setFile} testID="proof-file" />
      <TextField label="Amount paid (₹)" keyboardType="decimal-pad" value={amount} onChangeText={setAmount} testID="proof-amount-input"
        error={amount && badAmt ? `Amount must be more than 0 and at most ${inr(bal)}.` : undefined} />
      <View style={{ gap: 8 }}>
        <TextField label="Payment date (YYYY-MM-DD)" value={paidOn} onChangeText={setPaidOn} autoCapitalize="none" testID="proof-date-input"
          error={badDate ? "Enter a valid date, not in the future." : undefined} />
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Chip label="Today" active={paidOn === todayISO()} onPress={() => setPaidOn(todayISO())} testID="proof-date-today" />
          <Chip label="Yesterday" active={paidOn === addDaysISO(-1)} onPress={() => setPaidOn(addDaysISO(-1))} testID="proof-date-yesterday" />
        </View>
      </View>
      <TextField label="UTR / transaction ID (recommended)" keyboardType="number-pad" value={utr} onChangeText={(v) => setUtr(v.replace(/\s/g, ""))}
        hint="Usually 12 digits — find it in your UPI app's payment details." testID="proof-utr-input" />
      <TextField label="Note (optional)" value={note} onChangeText={setNote} testID="proof-note-input" />
      <Button label={busy ? "Uploading…" : "Submit for verification"} variant="success" icon="check" onPress={submit} loading={busy}
        disabled={badAmt || badDate || !file} testID="proof-submit-btn" />
      <Text style={[k.small, { color: C.muted, textAlign: "center" }]}>{'You\'ll see "Verification pending" until the school checks it.'}</Text>
    </StackScreen>
  );
}

const s = StyleSheet.create({
  title: { fontFamily: fonts.heading, fontSize: 18, color: C.onSurface },
});
