// "I have already paid" — raise a fee issue with an optional screenshot.
import { useState } from "react";
import { Text } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { useChild } from "@/src/state/child";
import { useToast } from "@/src/state/toast";
import { useFees } from "@/src/lib/queries";
import { api } from "@/src/lib/api";
import { appendFile, type Picked } from "@/src/lib/files";
import { StackScreen } from "@/src/ui/Screen";
import { Button, Card, k } from "@/src/ui/kit";
import { TextField } from "@/src/ui/inputs";
import { PhotoPicker } from "@/src/ui/PhotoPicker";

export default function RaiseIssue() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { childId } = useChild();
  const inv = useFees(childId).data?.invoices?.find((i: any) => i.id === id);
  const qc = useQueryClient();
  const toast = useToast();
  const [msg, setMsg] = useState("");
  const [file, setFile] = useState<Picked | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("message", msg);
      if (file) await appendFile(fd, "file", file);
      await api.postForm(`/parent/fees/invoices/${id}/issues`, fd);
      toast("Issue sent to the school office");
      await qc.invalidateQueries({ queryKey: ["fees"] });
      router.back();
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  return (
    <StackScreen title="I have already paid" testID="raise-issue-screen" keyboard>
      <Card><Text style={k.body}>Tell the school what happened ({inv?.period_label || "this invoice"}). Add a screenshot if you have one.</Text></Card>
      <TextField label="What happened?" multiline value={msg} onChangeText={setMsg}
        placeholder="e.g. Paid ₹1,500 on 12 Oct via PhonePe, UTR 123456789012" testID="issue-message-input" />
      <PhotoPicker file={file} setFile={setFile} testID="issue-file" label="Screenshot (optional)" />
      <Button label={busy ? "Sending…" : "Send to school"} icon="send" onPress={submit} loading={busy} disabled={msg.trim().length < 3} testID="issue-submit-btn" />
    </StackScreen>
  );
}
