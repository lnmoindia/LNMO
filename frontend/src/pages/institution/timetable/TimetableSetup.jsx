import { useCallback, useEffect, useState } from "react";
import { Plus, Trash2, Save } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Checkbox } from "../../../components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../../components/ui/select";
import { ALL_DAYS, DAY_SHORT } from "./days";

const INST_DEFAULT = "__default__";

export default function TimetableSetup({ year }) {
  const [units, setUnits] = useState([]);
  const [unitId, setUnitId] = useState(INST_DEFAULT);
  const [workingDays, setWorkingDays] = useState([]);
  const [periods, setPeriods] = useState([]);
  const [explicit, setExplicit] = useState(null);
  const [overrides, setOverrides] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/lookup/academic_units").then((r) => setUnits(r.data)).catch(() => setUnits([]));
  }, []);

  const load = useCallback(() => {
    api.get("/timetable/config", { params: { academic_year: year, academic_unit_id: unitId === INST_DEFAULT ? "" : unitId } })
      .then((r) => {
        setWorkingDays(r.data.config.working_days);
        setPeriods(r.data.config.periods.map((p) => ({ ...p })));
        setExplicit(r.data.explicit);
        setOverrides(r.data.unit_overrides || []);
      })
      .catch((e) => toast.error(errText(e)));
  }, [year, unitId]);

  useEffect(() => { load(); }, [load]);

  const toggleDay = (d) => setWorkingDays((w) => (w.includes(d) ? w.filter((x) => x !== d) : [...ALL_DAYS.filter((x) => [...w, d].includes(x))]));
  const setPeriod = (i, k, v) => setPeriods((ps) => ps.map((p, idx) => (idx === i ? { ...p, [k]: v } : p)));
  const removePeriod = (i) => setPeriods((ps) => ps.filter((_, idx) => idx !== i));
  const addPeriod = () => setPeriods((ps) => [...ps, { label: `P${ps.filter((p) => !p.is_break).length + 1}`, start: "", end: "", is_break: false }]);

  const save = async () => {
    setSaving(true);
    try {
      await api.post("/timetable/config", {
        academic_year: year,
        academic_unit_id: unitId === INST_DEFAULT ? null : unitId,
        working_days: workingDays,
        periods,
      });
      toast.success("Timetable setup saved");
      load();
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5 max-w-3xl" data-testid="tt-setup">
      <div className="flex flex-wrap items-center gap-3">
        <Select value={unitId} onValueChange={setUnitId}>
          <SelectTrigger className="w-64" data-testid="tt-unit-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={INST_DEFAULT}>Institution default</SelectItem>
            {units.map((u) => (
              <SelectItem key={u.value} value={u.value}>{u.label}{overrides.includes(u.value) ? " · customised" : ""}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${explicit ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400" : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"}`} data-testid="tt-config-badge">
          {explicit === null ? "Loading…" : explicit ? "Saved configuration" : unitId === INST_DEFAULT ? "Built-in defaults (not saved yet)" : "Inheriting — save to customise this unit"}
        </span>
      </div>

      <div className="space-y-2">
        <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">Working days</p>
        <div className="flex flex-wrap gap-2">
          {ALL_DAYS.map((d) => (
            <button key={d} onClick={() => toggleDay(d)} data-testid={`tt-day-${d}`}
              className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                workingDays.includes(d) ? "bg-indigo-700 text-white border-indigo-700" : "border-slate-200 dark:border-slate-700 text-slate-500 hover:border-indigo-400"
              }`}>
              {DAY_SHORT[d]}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">Periods <span className="text-xs font-normal text-slate-400">(order = daily sequence; mark breaks/lunch)</span></p>
          <Button variant="outline" size="sm" onClick={addPeriod} data-testid="tt-add-period"><Plus size={14} className="mr-1" /> Add period</Button>
        </div>
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 divide-y divide-slate-100 dark:divide-slate-800/60">
          {periods.map((p, i) => (
            <div key={i} className={`flex items-center gap-2 px-3 py-2 ${p.is_break ? "bg-slate-50 dark:bg-slate-800/40" : ""}`} data-testid={`tt-period-row-${i}`}>
              <span className="text-xs text-slate-400 w-5">{i + 1}</span>
              <Input value={p.label} onChange={(e) => setPeriod(i, "label", e.target.value)} className="w-28 h-8 text-sm" data-testid={`tt-period-label-${i}`} />
              <Input type="time" value={p.start} onChange={(e) => setPeriod(i, "start", e.target.value)} className="w-28 h-8 text-sm" data-testid={`tt-period-start-${i}`} />
              <span className="text-slate-300">–</span>
              <Input type="time" value={p.end} onChange={(e) => setPeriod(i, "end", e.target.value)} className="w-28 h-8 text-sm" data-testid={`tt-period-end-${i}`} />
              <label className="flex items-center gap-1.5 text-xs text-slate-500 ml-2 cursor-pointer">
                <Checkbox checked={p.is_break} onCheckedChange={(v) => setPeriod(i, "is_break", Boolean(v))} data-testid={`tt-period-break-${i}`} /> Break
              </label>
              <button onClick={() => removePeriod(i)} className="ml-auto text-slate-300 hover:text-red-500 transition-colors" data-testid={`tt-period-remove-${i}`}><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
      </div>

      <Button onClick={save} disabled={saving} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="tt-setup-save">
        <Save size={14} className="mr-1" /> {saving ? "Saving…" : `Save ${unitId === INST_DEFAULT ? "institution default" : "unit override"}`}
      </Button>
      <p className="text-xs text-slate-400">
        Changing periods later does not delete existing timetable entries — slots beyond the new period count simply stop rendering. Existing entries keep their period number.
      </p>
    </div>
  );
}
