import { useCallback, useEffect, useState } from "react";
import { X, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";

export function LinkChildDialog({ onClose, onLinked }) {
  const [stage, setStage] = useState("details"); // details | code
  const [phone, setPhone] = useState("");
  const [adm, setAdm] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [err, setErr] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [cooldown, setCooldown] = useState(0);
  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const t = setInterval(() => setCooldown((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [cooldown]);
  const request = async () => {
    if (busy) return;
    setBusy(true); setErr("");
    try {
      const r = await api.post("/verify/request", { purpose: "parent_link", phone, admission_no: adm });
      if (r.data.sent === false) { setErr(r.data.message || "Couldn't send the code — check the details."); return; }
      setStage("code"); setCode(""); setSentTo(r.data.sent_to || ""); setCooldown(60); toast.success(r.data.message);
    } catch (e) { setErr("Something went wrong — try again."); } finally { setBusy(false); }
  };
  const confirm = useCallback(async (val) => {
    setConfirming(true); setErr("");
    try {
      await api.post("/verify/confirm", { purpose: "parent_link", phone, admission_no: adm, code: (val ?? "").toString() });
      toast.success("Child linked"); onLinked();
    } catch (e) { setErr(errText(e)); } finally { setConfirming(false); }
  }, [phone, adm, onLinked]);
  useEffect(() => {
    if (stage === "code" && code.length === 6 && !confirming) confirm(code);
  }, [code, stage, confirming, confirm]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" data-testid="link-child-dialog">
      <div className="w-full max-w-md rounded-3xl bg-white dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-800 shadow-2xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-white">Link a child</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" data-testid="link-child-close"><X size={18} /></button>
        </div>
        {stage === "details" ? (
          <>
            <p className="text-sm text-slate-500">Enter the phone number on your child's school record and their admission number. We'll email you a verification code.</p>
            <div className="space-y-2">
              <Input value={phone} onChange={(e) => { setPhone(e.target.value); setErr(""); }} placeholder="Guardian phone on record" data-testid="link-child-phone" />
              <Input value={adm} onChange={(e) => { setAdm(e.target.value); setErr(""); }} placeholder="Student admission number" data-testid="link-child-admission" />
            </div>
            {err && <p className="text-sm text-red-600 dark:text-red-400" data-testid="link-child-error">{err}</p>}
            <Button className="w-full" disabled={busy || !phone.trim() || !adm.trim()} onClick={request} data-testid="link-child-request-btn">
              {busy ? <span className="inline-flex items-center gap-2"><Loader2 className="animate-spin" size={15} /> Sending…</span> : "Send code"}
            </Button>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-500">Enter the 6-digit code sent to <span className="font-medium">{sentTo}</span>.</p>
            <Input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="Verification code" maxLength={6} inputMode="numeric" data-testid="link-child-code" />
            {err && <p className="text-sm text-red-600 dark:text-red-400" data-testid="link-child-error">{err}</p>}
            <div className="flex items-center justify-between">
              <button type="button" className="text-xs text-indigo-600 underline disabled:text-slate-400 disabled:no-underline" disabled={cooldown > 0 || busy} onClick={request} data-testid="link-child-resend">
                {cooldown > 0 ? `Resend in ${cooldown}s` : (busy ? "Sending…" : "Resend code")}
              </button>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" disabled={confirming} onClick={() => { setStage("details"); setErr(""); }} data-testid="link-child-back">Back</Button>
              <Button className="flex-1" disabled={confirming || code.length < 4} onClick={() => confirm(code)} data-testid="link-child-confirm-btn">
                {confirming ? <span className="inline-flex items-center gap-2"><Loader2 className="animate-spin" size={15} /> Linking…</span> : "Link child"}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

