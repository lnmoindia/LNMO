import { useEffect, useState } from "react";
import { BellRing } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Switch } from "../../../components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../../../components/ui/dialog";

const NUMS = [["before_days", "Days before due date"], ["overdue_after_days", "Days after due date (first overdue)"], ["repeat_every_days", "Then repeat every (days) while overdue"]];

export default function ReminderSettings({ readOnly }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) api.get("/fees/reminder-settings").then((r) => setF(r.data)).catch((e) => toast.error(errText(e))); }, [open]);
  const save = async () => {
    setBusy(true);
    try { await api.put("/fees/reminder-settings", { ...f, ...Object.fromEntries(NUMS.map(([k]) => [k, Number(f[k])])) }); toast.success("Reminder schedule saved"); setOpen(false); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (<>
    <Button variant="outline" onClick={() => setOpen(true)} data-testid="fee-reminder-settings-btn"><BellRing size={14} className="mr-1.5" /> Reminders</Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-md" data-testid="fee-reminder-settings-dialog">
        <DialogHeader><DialogTitle>Automatic fee reminders</DialogTitle>
          <DialogDescription>Parents get a bell notification plus a WhatsApp/SMS message (counts toward the message quota). At most one reminder per invoice per day, from any source.</DialogDescription></DialogHeader>
        {f && (
          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm"><Switch disabled={readOnly} checked={f.enabled} onCheckedChange={(v) => setF({ ...f, enabled: v })} data-testid="fee-reminder-enabled" /> Send automatic reminders</label>
            {NUMS.map(([k, l]) => (
              <div key={k} className="grid grid-cols-[1fr_90px] items-center gap-3"><Label className="text-sm font-normal">{l}</Label>
                <Input type="number" min={k === "repeat_every_days" ? 1 : 0} disabled={readOnly} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`fee-reminder-${k}`} /></div>
            ))}
            <div className="grid grid-cols-[1fr_120px] items-center gap-3"><Label className="text-sm font-normal">Channel</Label>
              <select disabled={readOnly} className="h-9 rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-2 text-sm" value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })} data-testid="fee-reminder-channel">
                <option value="whatsapp">WhatsApp</option><option value="sms">SMS</option></select></div>
            {!readOnly && <div className="flex justify-end"><Button disabled={busy} onClick={save} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="fee-reminder-save">Save</Button></div>}
          </div>
        )}
      </DialogContent>
    </Dialog>
  </>);
}
