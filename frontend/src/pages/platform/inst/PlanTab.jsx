import { useCallback, useEffect, useState } from "react";
import { Pencil } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../../components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "../../../components/ui/alert-dialog";
import { Card, PlanBadge, SkeletonGrid, StatusPill, fmtDay } from "./ui";

const Row = ({ label, used, limit, testid }) => {
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  return (
    <div className="space-y-1.5" data-testid={testid}>
      <div className="flex justify-between text-sm"><span className="font-medium text-slate-700 dark:text-slate-200">{label}</span><span className="tabular-nums text-slate-500">{used} / {limit ?? "no limit set"}</span></div>
      <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden"><div className={`h-full ${pct >= 100 ? "bg-red-500" : "bg-indigo-600"}`} style={{ width: `${pct}%` }} /></div>
    </div>
  );
};

const num = (v) => (v === "" || v === null || v === undefined ? null : Number(v));

function EditPlan({ open, onClose, d, onSaved }) {
  const [f, setF] = useState({});
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) setF({ plan_id: d.plan?.id || "", max_students: d.overrides?.max_students ?? "", whatsapp_limit: d.limits.whatsapp ?? "", sms_limit: d.limits.sms ?? "",
      ai_messages_month: d.overrides?.ai_messages_month ?? "", status: d.status, expires_at: d.expires_at || "" });
  }, [open, d]);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.put(d.endpoint, { ...f, plan_id: f.plan_id || null, expires_at: f.expires_at || null, max_students: num(f.max_students),
        whatsapp_limit: num(f.whatsapp_limit), sms_limit: num(f.sms_limit), ai_messages_month: num(f.ai_messages_month) });
      toast.success("Plan updated"); onSaved(data); setConfirm(false); onClose();
    } catch (e) { toast.error(errText(e)); setConfirm(false); } finally { setBusy(false); }
  };
  const sel = "w-full h-9 rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 text-sm";
  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-lg" data-testid="edit-plan-dialog">
          <DialogHeader><DialogTitle>Edit plan</DialogTitle><DialogDescription>Change the plan, limits, status or expiry. Leave a limit blank to use the plan's default.</DialogDescription></DialogHeader>
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="space-y-1.5 sm:col-span-2"><Label>Plan</Label>
              <select className={sel} value={f.plan_id} onChange={set("plan_id")} data-testid="plan-select">
                <option value="">No plan</option>{d.plans.map((p) => <option key={p.id} value={p.id} label={`${p.name} · ₹${p.price_monthly}/mo · ${p.max_students} students`} />)}
              </select></div>
            <div className="space-y-1.5"><Label>Student limit override</Label><Input type="number" min="0" value={f.max_students} onChange={set("max_students")} placeholder="Plan default" data-testid="plan-max-students" /></div>
            <div className="space-y-1.5"><Label>AI questions / month</Label><Input type="number" min="0" value={f.ai_messages_month} onChange={set("ai_messages_month")} placeholder="No limit" data-testid="plan-ai-limit" /></div>
            <div className="space-y-1.5"><Label>WhatsApp limit / cycle</Label><Input type="number" min="0" value={f.whatsapp_limit} onChange={set("whatsapp_limit")} data-testid="plan-wa-limit" /></div>
            <div className="space-y-1.5"><Label>SMS limit / cycle</Label><Input type="number" min="0" value={f.sms_limit} onChange={set("sms_limit")} data-testid="plan-sms-limit" /></div>
            <div className="space-y-1.5"><Label>Status</Label>
              <select className={sel} value={f.status} onChange={set("status")} data-testid="plan-status-select">
                <option value="active">Active</option><option value="suspended">Suspended</option><option value="inactive">Inactive</option>
              </select></div>
            <div className="space-y-1.5"><Label>Expiry / renewal date</Label><Input type="date" value={f.expires_at} onChange={set("expires_at")} data-testid="plan-expiry" /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button className="bg-indigo-700 hover:bg-indigo-800 text-white" onClick={() => setConfirm(true)} data-testid="plan-save-btn">Save changes</Button></DialogFooter>
        </DialogContent>
      </Dialog>
      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent data-testid="plan-confirm-dialog">
          <AlertDialogHeader><AlertDialogTitle>Apply these plan changes?</AlertDialogTitle>
            <AlertDialogDescription>The change takes effect for this school immediately and is recorded in the audit log.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Back</AlertDialogCancel><AlertDialogAction onClick={(e) => { e.preventDefault(); save(); }} disabled={busy} data-testid="plan-confirm-btn">{busy ? "Saving…" : "Confirm"}</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

export default function PlanTab({ iid, onChanged }) {
  const [d, setD] = useState(null);
  const [open, setOpen] = useState(false);
  const endpoint = `/platform/institutions/${iid}/plan`;
  const load = useCallback(() => api.get(endpoint).then((r) => setD(r.data)).catch((e) => toast.error(errText(e))), [endpoint]);
  useEffect(() => { load(); }, [load]);
  if (!d) return <SkeletonGrid n={3} />;
  const p = d.plan;
  return (
    <div className="space-y-6" data-testid="inst-plan-tab">
      <Card title="Current plan" action={<Button size="sm" variant="outline" onClick={() => setOpen(true)} data-testid="edit-plan-btn"><Pencil size={14} className="mr-1.5" /> Edit plan</Button>}>
        <div className="flex flex-wrap items-center gap-3">
          <PlanBadge name={p?.name} /><StatusPill status={d.status} />
          <span className="text-sm text-slate-500" data-testid="plan-expiry-text">{d.expires_at ? `Renews / expires ${fmtDay(d.expires_at)}` : "No expiry date set"}</span>
          {p && <span className="text-sm text-slate-500">₹{p.price_monthly}/month · {p.description}</span>}
        </div>
      </Card>
      <Card title="Limits vs usage" testid="plan-usage">
        <div className="space-y-5">
          <Row label={`Students${d.overrides?.max_students ? " (override)" : ""}`} used={d.usage.students} limit={d.limits.students} testid="usage-students" />
          <Row label="WhatsApp messages (this cycle)" used={d.usage.whatsapp} limit={d.limits.whatsapp} testid="usage-whatsapp" />
          <Row label="SMS messages (this cycle)" used={d.usage.sms} limit={d.limits.sms} testid="usage-sms" />
          <Row label="AI Tutor questions (this month)" used={d.usage.ai_messages_month} limit={d.limits.ai_messages_month} testid="usage-ai" />
          <p className="text-xs text-slate-400">Limits are shown for planning; they aren't enforced automatically except the messaging quota.</p>
        </div>
      </Card>
      <EditPlan open={open} onClose={() => setOpen(false)} d={{ ...d, endpoint }} onSaved={(x) => { setD(x); onChanged?.(); }} />
    </div>
  );
}
