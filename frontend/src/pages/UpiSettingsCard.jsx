import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { errText } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";

const VPA_RX = /^[A-Za-z0-9][A-Za-z0-9.\-_]{1,255}@[A-Za-z][A-Za-z0-9.-]{1,63}$/;

export function UpiCard() {
  const [v, setV] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/fees/upi-settings").then((r) => setV(r.data)).catch(() => setV({ enabled: false, vpa: "", payee_name: "", instructions: "" })); }, []);
  if (!v) return null;
  const vpaBad = v.vpa && !VPA_RX.test(v.vpa);
  const save = async () => {
    setBusy(true);
    try { const { data } = await api.put("/fees/upi-settings", v); setV(data); toast.success(data.enabled ? "UPI payments enabled — parents now see a QR on unpaid invoices" : "UPI settings saved"); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4" data-testid="settings-upi-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-heading font-semibold text-slate-900 dark:text-slate-100">UPI payments</h2>
          <p className="text-sm text-slate-500 mt-1">Parents see a UPI QR for the exact balance on each unpaid invoice, then upload the payment screenshot for verification. No payment gateway — money goes straight to this UPI ID.</p>
        </div>
        <label className="flex items-center gap-2 text-sm shrink-0"><Switch checked={v.enabled} onCheckedChange={(x) => setV({ ...v, enabled: x })} data-testid="upi-enabled" /> Enabled</label>
      </div>
      <div className="grid sm:grid-cols-2 gap-4">
        <div className="space-y-1.5"><Label>UPI ID (VPA)</Label><Input placeholder="schoolname@okaxis" value={v.vpa} onChange={(e) => setV({ ...v, vpa: e.target.value.trim() })} data-testid="upi-vpa" />
          {vpaBad && <p className="text-xs text-rose-600" data-testid="upi-vpa-error">Should look like name@bank</p>}</div>
        <div className="space-y-1.5"><Label>Payee name</Label><Input placeholder="As registered with the bank" value={v.payee_name} onChange={(e) => setV({ ...v, payee_name: e.target.value })} data-testid="upi-payee" /></div>
        <div className="space-y-1.5 sm:col-span-2"><Label>Instructions for parents (optional)</Label><Input placeholder="e.g. Mention the admission number in the note" value={v.instructions} onChange={(e) => setV({ ...v, instructions: e.target.value })} data-testid="upi-instructions" /></div>
      </div>
      <div className="flex justify-end"><Button disabled={busy || vpaBad} onClick={save} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="upi-save">{busy ? "Saving…" : "Save UPI settings"}</Button></div>
    </div>
  );
}
