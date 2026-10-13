import { useState } from "react";
import { Trash2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../../components/ui/dialog";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../../components/ui/select";
import { DAY_LABELS } from "./days";

export default function EntryDialog({ slot, onClose, year, className, section, offerings, assignments, onSaved }) {
  const e = slot.entry;
  const [form, setForm] = useState({
    offering_id: e?.offering_id || "",
    teacher_assignment_id: e?.teacher_assignment_id || "",
    room: e?.room || "",
    type: e?.type || "regular",
    effective_from: e?.effective_from || "",
    effective_to: e?.effective_to || "",
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [showDates, setShowDates] = useState(Boolean(e?.effective_from || e?.effective_to));

  const offering = offerings.find((o) => o.id === form.offering_id);
  const validAssignments = offering ? assignments.filter((a) => a.subject === offering.subject) : [];

  const set = (k, v) => {
    setForm((f) => {
      const next = { ...f, [k]: v };
      if (k === "offering_id") next.teacher_assignment_id = "";
      return next;
    });
    setError("");
  };

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      const payload = {
        academic_year: year, class_name: className, section,
        day: slot.day, period_no: slot.period_no, ...form,
      };
      if (e) await api.put(`/timetable/entries/${e.id}`, payload);
      else await api.post("/timetable/entries", payload);
      toast.success("Timetable saved");
      onSaved();
    } catch (err) {
      setError(errText(err));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    setSaving(true);
    try {
      await api.delete(`/timetable/entries/${e.id}`);
      toast.success("Slot cleared");
      onSaved();
    } catch (err) {
      setError(errText(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md" data-testid="tt-entry-dialog">
        <DialogHeader>
          <DialogTitle>{className} {section} — {DAY_LABELS[slot.day]} · {slot.periodLabel}</DialogTitle>
          <DialogDescription>{e ? "Edit or clear this period." : "Schedule a subject for this period."}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-1">
          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Subject offering <span className="text-red-500">*</span></label>
            <Select value={form.offering_id} onValueChange={(v) => set("offering_id", v)}>
              <SelectTrigger data-testid="tt-offering-select"><SelectValue placeholder="Pick a subject" /></SelectTrigger>
              <SelectContent>
                {offerings.map((o) => (
                  <SelectItem key={o.id} value={o.id}>{o.subject}{o.section ? ` (Sec ${o.section})` : ""}{o.has_practical ? " · lab" : ""}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Teacher <span className="text-red-500">*</span></label>
            <Select value={form.teacher_assignment_id} onValueChange={(v) => set("teacher_assignment_id", v)} disabled={!offering}>
              <SelectTrigger data-testid="tt-assignment-select"><SelectValue placeholder={offering ? "Pick an assigned teacher" : "Pick a subject first"} /></SelectTrigger>
              <SelectContent>
                {validAssignments.map((a) => (
                  <SelectItem key={a.id} value={a.id}>{a.teacher_name}{a.section ? ` (Sec ${a.section})` : ""}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {offering && validAssignments.length === 0 && (
              <p className="text-xs text-amber-600">No teacher is assigned to {offering.subject} for this class — add one in Class Hub → Teachers.</p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Room / Lab</label>
              <Input value={form.room} onChange={(ev) => set("room", ev.target.value)} placeholder="e.g. Room 204" data-testid="tt-room-input" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Type</label>
              <Select value={form.type} onValueChange={(v) => set("type", v)}>
                <SelectTrigger data-testid="tt-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="regular">Regular</SelectItem>
                  <SelectItem value="lab">Lab / Practical</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          {showDates ? (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Effective from</label>
                <Input type="date" value={form.effective_from} onChange={(ev) => set("effective_from", ev.target.value)} data-testid="tt-from-input" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Effective to</label>
                <Input type="date" value={form.effective_to} onChange={(ev) => set("effective_to", ev.target.value)} data-testid="tt-to-input" />
              </div>
            </div>
          ) : (
            <button className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline" onClick={() => setShowDates(true)} data-testid="tt-show-dates">
              + Set effective date range (optional)
            </button>
          )}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-500/10 dark:border-red-500/30 p-3 text-sm text-red-700 dark:text-red-300 flex items-start gap-2" data-testid="tt-entry-error">
              <AlertTriangle size={15} className="mt-0.5 shrink-0" /> {error}
            </div>
          )}
          <div className="flex justify-between pt-1">
            {e ? (
              <Button variant="outline" onClick={remove} disabled={saving} className="text-red-600 border-red-200 hover:bg-red-50 dark:border-red-500/30" data-testid="tt-delete-btn">
                <Trash2 size={14} className="mr-1" /> Clear slot
              </Button>
            ) : <span />}
            <div className="flex gap-2">
              <Button variant="outline" onClick={onClose} data-testid="tt-cancel-btn">Cancel</Button>
              <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" onClick={save}
                disabled={saving || !form.offering_id || !form.teacher_assignment_id} data-testid="tt-save-btn">
                {saving ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
