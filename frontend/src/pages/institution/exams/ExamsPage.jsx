import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CalendarClock, Plus, Trash2, FileSpreadsheet, ChevronRight, X } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "../../../components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../../components/ui/select";

const TYPE_LABELS = { model: "Model Exam", term: "Term Exam", unit: "Unit Test", other: "Other" };
const TYPE_COLORS = {
  model: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  term: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300",
  unit: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  other: "bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300",
};

export default function ExamsPage() {
  const navigate = useNavigate();
  const [exams, setExams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [units, setUnits] = useState([]);
  const [open, setOpen] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api.get("/exams").then((r) => setExams(r.data.exams || []))
      .catch((e) => toast.error(errText(e))).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    api.get("/res/academic_units", { params: { limit: 200 } }).then((r) => setUnits(r.data.items || [])).catch(() => {});
  }, [load]);

  return (
    <div className="space-y-6" data-testid="exams-page">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-500">Assessment</p>
          <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50">Exams</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Plan exam timetables per division, auto-schedule every subject, and publish to students & parents.</p>
        </div>
        <Button onClick={() => setOpen(true)} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="exam-create-btn">
          <Plus size={15} className="mr-1" /> New exam
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-slate-400 py-12 text-center">Loading…</p>
      ) : exams.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 dark:border-slate-700 p-12 text-center" data-testid="exams-empty">
          <CalendarClock className="mx-auto text-slate-300 dark:text-slate-600" size={34} />
          <p className="mt-3 text-sm text-slate-500">No exams yet. Create one to schedule papers across divisions.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="exams-list">
          {exams.map((e) => (
            <button key={e.id} onClick={() => navigate(`/app/exams/${e.id}`)} data-testid={`exam-card-${e.id}`}
              className="text-left rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-indigo-400 hover:shadow-md transition-all group">
              <div className="flex items-center justify-between">
                <span className={`text-[10px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5 ${TYPE_COLORS[e.type] || TYPE_COLORS.other}`}>{TYPE_LABELS[e.type] || e.type}</span>
                <span className={`text-[10px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5 ${e.status === "published" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300" : "bg-slate-100 text-slate-500 dark:bg-slate-700/40"}`} data-testid={`exam-status-${e.id}`}>{e.status}</span>
              </div>
              {e.editable === false && (
                <span className="mt-2 inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5 bg-slate-100 text-slate-500 dark:bg-slate-700/40 dark:text-slate-400" data-testid={`exam-readonly-${e.id}`}>Read-only · other division</span>
              )}
              <h3 className="mt-3 font-heading text-lg font-bold text-slate-900 dark:text-slate-50 group-hover:text-indigo-700 dark:group-hover:text-indigo-300 transition-colors">{e.name}</h3>
              <p className="text-xs text-slate-500 mt-1">{e.academic_year}</p>
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                {(e.division_names || []).map((d) => (
                  <span key={d} className="text-[11px] rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-2 py-0.5">{d}</span>
                ))}
              </div>
              <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
                <span className="inline-flex items-center gap-1"><FileSpreadsheet size={13} /> {e.entry_count} papers</span>
                <ChevronRight size={15} className="text-slate-300 group-hover:text-indigo-500 transition-colors" />
              </div>
            </button>
          ))}
        </div>
      )}

      <CreateExamDialog open={open} onOpenChange={setOpen} units={units} onCreated={(id) => { setOpen(false); navigate(`/app/exams/${id}`); }} />
    </div>
  );
}

function CreateExamDialog({ open, onOpenChange, units, onCreated }) {
  const [name, setName] = useState("");
  const [type, setType] = useState("model");
  const [configs, setConfigs] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (open) { setName(""); setType("model"); setConfigs([]); } }, [open]);

  const addDivision = () => {
    const used = new Set(configs.map((c) => c.academic_unit_id));
    const avail = units.find((u) => !used.has(u.id));
    if (!avail) { toast.error("All divisions already added"); return; }
    setConfigs((c) => [...c, { academic_unit_id: avail.id, date_start: "", date_end: "", slots_per_day: [{ start: "09:30", end: "11:00", label: "" }] }]);
  };
  const setConfig = (i, patch) => setConfigs((cs) => cs.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  const removeDivision = (i) => setConfigs((cs) => cs.filter((_, idx) => idx !== i));
  const addSlot = (i) => setConfig(i, { slots_per_day: [...configs[i].slots_per_day, { start: "", end: "", label: "" }] });
  const setSlot = (i, si, patch) => setConfig(i, { slots_per_day: configs[i].slots_per_day.map((s, idx) => (idx === si ? { ...s, ...patch } : s)) });
  const removeSlot = (i, si) => setConfig(i, { slots_per_day: configs[i].slots_per_day.filter((_, idx) => idx !== si) });

  const submit = async () => {
    if (!name.trim()) { toast.error("Enter an exam name"); return; }
    if (configs.length === 0) { toast.error("Add at least one division"); return; }
    setSaving(true);
    try {
      const { data } = await api.post("/exams", { name: name.trim(), type, division_configs: configs });
      toast.success(`Created "${data.exam.name}"`);
      onCreated(data.exam.id);
    } catch (e) { toast.error(errText(e)); } finally { setSaving(false); }
  };

  const unitName = (id) => units.find((u) => u.id === id)?.name || "Division";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="exam-create-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><CalendarClock size={18} className="text-indigo-600" /> New exam</DialogTitle>
          <DialogDescription>Name the exam and configure dates & daily slots per division — divisions can differ.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-1">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Exam name <span className="text-red-500">*</span></label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Model Exam 2026" data-testid="exam-name-input" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Type</label>
              <Select value={type} onValueChange={setType}>
                <SelectTrigger data-testid="exam-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>{Object.entries(TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">Divisions</p>
              <Button type="button" variant="outline" size="sm" onClick={addDivision} data-testid="exam-add-division"><Plus size={13} className="mr-1" /> Add division</Button>
            </div>
            {configs.length === 0 && <p className="text-xs text-slate-400">No divisions added. Add a division to configure its dates and slots.</p>}
            {configs.map((c, i) => (
              <div key={i} className="rounded-lg border border-slate-200 dark:border-slate-800 p-3 space-y-3" data-testid={`exam-division-${i}`}>
                <div className="flex items-center gap-2">
                  <Select value={c.academic_unit_id} onValueChange={(v) => setConfig(i, { academic_unit_id: v })}>
                    <SelectTrigger className="w-44 h-8" data-testid={`exam-division-unit-${i}`}><SelectValue placeholder="Division" /></SelectTrigger>
                    <SelectContent>{units.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}</SelectContent>
                  </Select>
                  <button onClick={() => removeDivision(i)} className="ml-auto text-slate-400 hover:text-red-600" data-testid={`exam-remove-division-${i}`}><Trash2 size={15} /></button>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-[11px] font-medium text-slate-500">Start date</label>
                    <Input type="date" value={c.date_start} onChange={(e) => setConfig(i, { date_start: e.target.value })} className="h-8" data-testid={`exam-date-start-${i}`} />
                  </div>
                  <div className="space-y-1">
                    <label className="text-[11px] font-medium text-slate-500">End date</label>
                    <Input type="date" value={c.date_end} onChange={(e) => setConfig(i, { date_end: e.target.value })} className="h-8" data-testid={`exam-date-end-${i}`} />
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-medium text-slate-500">Daily slots ({unitName(c.academic_unit_id)})</span>
                    <button onClick={() => addSlot(i)} className="text-xs text-indigo-600 hover:underline inline-flex items-center gap-1" data-testid={`exam-add-slot-${i}`}><Plus size={12} /> slot</button>
                  </div>
                  {c.slots_per_day.map((s, si) => (
                    <div key={si} className="flex items-center gap-2" data-testid={`exam-slot-${i}-${si}`}>
                      <Input type="time" value={s.start} onChange={(e) => setSlot(i, si, { start: e.target.value })} className="h-8 w-28" data-testid={`exam-slot-start-${i}-${si}`} />
                      <span className="text-slate-400">–</span>
                      <Input type="time" value={s.end} onChange={(e) => setSlot(i, si, { end: e.target.value })} className="h-8 w-28" data-testid={`exam-slot-end-${i}-${si}`} />
                      <Input value={s.label || ""} onChange={(e) => setSlot(i, si, { label: e.target.value })} placeholder="label (optional)" className="h-8 flex-1" />
                      {c.slots_per_day.length > 1 && <button onClick={() => removeSlot(i, si)} className="text-slate-400 hover:text-red-600"><X size={14} /></button>}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={saving} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="exam-create-submit">{saving ? "Creating…" : "Create exam"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
