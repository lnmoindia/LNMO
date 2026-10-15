// Link a child: guardian phone + admission number → emailed code → confirm (/verify/request, /verify/confirm).
import { useEffect, useState } from "react";
import { Text } from "react-native";
import { router } from "expo-router";
import { useChild } from "@/src/state/child";
import { useToast } from "@/src/state/toast";
import { api } from "@/src/lib/api";
import { StackScreen } from "@/src/ui/Screen";
import { Button, C, Card, k } from "@/src/ui/kit";
import { TextField } from "@/src/ui/inputs";

export default function LinkChild() {
  const { reload } = useChild();
  const toast = useToast();
  const [stage, setStage] = useState<"details" | "code">("details");
  const [phone, setPhone] = useState("");
  const [adm, setAdm] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [cool, setCool] = useState(0);
  useEffect(() => {
    if (cool <= 0) return undefined;
    const t = setInterval(() => setCool((v) => Math.max(0, v - 1)), 1000);
    return () => clearInterval(t);
  }, [cool]);
  const request = async () => {
    setBusy(true); setErr("");
    try {
      const r = await api.post("/verify/request", { purpose: "parent_link", phone, admission_no: adm });
      if (r.sent === false) { setErr(r.message || "Couldn't send the code — check the details."); return; }
      setStage("code"); setCode(""); setSentTo(r.sent_to || ""); setCool(60); toast(r.message || "Code sent");
    } catch { setErr("Something went wrong — try again."); } finally { setBusy(false); }
  };
  const confirmCode = async () => {
    setBusy(true); setErr("");
    try {
      await api.post("/verify/confirm", { purpose: "parent_link", phone, admission_no: adm, code });
      toast("Child linked"); reload(); router.back();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <StackScreen title="Link a child" testID="link-child-screen" keyboard>
      {stage === "details" ? (
        <>
          <Card><Text style={k.body}>{"Enter the phone number on your child's school record and their admission number. We'll email you a verification code."}</Text></Card>
          <TextField label="Guardian phone on record" keyboardType="phone-pad" value={phone} onChangeText={(v) => { setPhone(v); setErr(""); }} testID="link-child-phone-input" />
          <TextField label="Student admission number" autoCapitalize="characters" value={adm} onChangeText={(v) => { setAdm(v); setErr(""); }} testID="link-child-admission-input" />
          {err ? <Text style={{ color: C.error }} testID="link-child-error">{err}</Text> : null}
          <Button label={busy ? "Sending…" : "Send code"} onPress={request} loading={busy} disabled={!phone.trim() || !adm.trim()} testID="link-child-request-btn" />
        </>
      ) : (
        <>
          <Card><Text style={k.body}>Enter the 6-digit code sent to {sentTo || "your email"}.</Text></Card>
          <TextField label="Verification code" keyboardType="number-pad" maxLength={6} value={code} onChangeText={(v) => setCode(v.replace(/\D/g, "").slice(0, 6))} testID="link-child-code-input" />
          {err ? <Text style={{ color: C.error }} testID="link-child-error">{err}</Text> : null}
          <Button label={busy ? "Linking…" : "Link child"} onPress={confirmCode} loading={busy} disabled={code.length < 4} testID="link-child-confirm-btn" />
          <Button variant="ghost" label={cool > 0 ? `Resend in ${cool}s` : "Resend code"} onPress={request} disabled={cool > 0 || busy} testID="link-child-resend-btn" />
          <Button variant="outline" label="Back" onPress={() => { setStage("details"); setErr(""); }} testID="link-child-back-btn" />
        </>
      )}
    </StackScreen>
  );
}
