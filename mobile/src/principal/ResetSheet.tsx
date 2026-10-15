// Password help for a user in my divisions (server returns 403 for admins / other principals / out-of-scope users).
import { useState } from "react";
import { Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import * as Clipboard from "expo-clipboard";
import { api } from "@/src/lib/api";
import { useToast } from "@/src/state/toast";
import { Button, ErrorState, SkeletonList, k } from "@/src/ui/kit";
import { Sheet, confirm } from "@/src/ui/brandbits";

export function ResetSheet({ uid, onClose }: { uid: string | null; onClose: () => void }) {
  const toast = useToast();
  const q = useQuery({ queryKey: ["p-reset", uid], queryFn: () => api.get(`/users/${uid}/reset-info`), enabled: Boolean(uid), retry: false });
  const [busy, setBusy] = useState(""); const [pw, setPw] = useState("");
  const gen = async () => {
    if (!(await confirm("Set a new password?", "Their current password stops working. They must change it at next sign-in.", "Set password"))) return;
    setBusy("gen");
    try { const r = await api.post(`/users/${uid}/set-password`, { generate: true }); setPw(r.password || r.temp_password || ""); toast("New password set"); } catch (e: any) { toast(e.message, "error"); } finally { setBusy(""); }
  };
  const link = async () => {
    setBusy("link");
    try { await api.post(`/users/${uid}/reset-link`, {}); toast("Reset link emailed"); } catch (e: any) { toast(e.message, "error"); } finally { setBusy(""); }
  };
  return (
    <Sheet open={Boolean(uid)} onClose={() => { setPw(""); onClose(); }} title="Password help" testID="preset-sheet">
      {q.isLoading ? <SkeletonList n={1} height={80} /> : q.isError ? <ErrorState error={q.error} testID="preset-error" /> : (
        <View style={{ gap: 10 }}>
          <Text style={k.label}>{q.data?.name} · {q.data?.role}</Text>
          <Text style={k.small}>{q.data?.email || "No email on file"}</Text>
          {pw ? <Button variant="outline" icon="copy" label={`Copy: ${pw}`} onPress={() => Clipboard.setStringAsync(pw).then(() => toast("Copied"))} testID="preset-copy" /> : null}
          <Button icon="key" label="Set a new password" loading={busy === "gen"} onPress={gen} testID="preset-generate" />
          {q.data?.email ? <Button variant="outline" icon="mail" label="Email a reset link" loading={busy === "link"} onPress={link} testID="preset-link" /> : null}
        </View>
      )}
    </Sheet>
  );
}
