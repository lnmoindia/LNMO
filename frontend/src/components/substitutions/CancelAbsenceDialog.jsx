import { useEffect, useState } from "react";
import { Ban, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../ui/dialog";

export const CancelAbsenceDialog = ({ absence, onClose, onDone }) => {
  const [prev, setPrev] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get(`/absences/${absence.id}/cancel-preview`).then((r) => setPrev(r.data))
      .catch((e) => { toast.error(errText(e)); onClose(); });
  }, [absence.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const ok = reason.trim().length >= 3 && reason.trim().length <= 300;
  const confirm = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/absences/${absence.id}/cancel`, { reason: reason.trim() });
      toast.success(`Absence cancelled · ${data.substitutions_cancelled} cover(s) cancelled`);
      onDone();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const live = prev?.periods.filter((p) => p.cancellable) || [];
  const kept = prev?.periods.filter((p) => !p.cancellable) || [];
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md" data-testid="cancel-absence-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Ban size={17} className="text-red-600" /> Cancel absence</DialogTitle>
          <DialogDescription>{absence.teacher_name} · {absence.date}</DialogDescription>
        </DialogHeader>
        {!prev ? <p className="text-sm text-slate-400 py-4"><Loader2 size={14} className="inline animate-spin mr-1" /> Loading…</p> : (
          <div className="space-y-3 text-sm">
            <div data-testid="cancel-affected">
              <p className="font-medium text-slate-700 dark:text-slate-200">Periods affected ({live.length})</p>
              {live.length === 0 ? <p className="text-slate-400 text-xs mt-1">No upcoming periods to change.</p> : (
                <ul className="mt-1 space-y-0.5 text-xs text-slate-600 dark:text-slate-300">
                  {live.map((p) => <li key={p.id}>{p.period_label || `P${p.period_no}`} · {p.class_name} {p.section} · {p.subject}{p.substitute_name ? ` · ${p.substitute_name}` : ""}</li>)}
                </ul>
              )}
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-300" data-testid="cancel-counts">
              {prev.assigned_count} assigned substitute(s) and {prev.asked_count} asked teacher(s) will be notified.
            </p>
            {kept.length > 0 && (
              <p className="text-xs rounded-lg bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300 px-3 py-2" data-testid="cancel-kept">
                Already started — kept as history: {kept.map((p) => p.period_label || `P${p.period_no}`).join(", ")}
              </p>
            )}
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Reason <span className="text-red-500">*</span></label>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value.slice(0, 300))} rows={2} placeholder="e.g. Teacher recovered and is back at school" data-testid="cancel-reason-input" />
              <p className="text-[11px] text-slate-400">{reason.trim().length}/300 · minimum 3 characters</p>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={onClose}>Keep absence</Button>
              <Button className="bg-red-600 hover:bg-red-700 text-white" disabled={!ok || busy} onClick={confirm} data-testid="cancel-absence-confirm">
                {busy ? <Loader2 size={14} className="animate-spin" /> : "Cancel absence"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};
