import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Users2, AlertTriangle, CheckCircle2, Layers, Pencil, Lock } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { Button } from "../../../components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../../components/ui/select";

/** Phase 7 editor → now a READ-ONLY overview. Editing lives in Class Hub → Subjects & Teachers.
 *  The backend PUT /api/timetable/requirements is unchanged and still used by the Class Hub save path. */
export default function TimetableRequirements({ year }) {
  const [classes, setClasses] = useState([]);
  const [className, setClassName] = useState("");
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/res/classes", { params: { limit: 500 } })
      .then((r) => {
        const items = (r.data.items || []).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
        setClasses(items);
        if (items.length) setClassName((c) => c || items[0].name);
      })
      .catch((e) => toast.error(errText(e)));
  }, []);

  const load = useCallback(() => {
    if (!className || !year) return;
    setLoading(true);
    api.get("/timetable/requirements", { params: { academic_year: year, class_name: className } })
      .then((r) => setPayload(r.data))
      .catch((e) => toast.error(errText(e)))
      .finally(() => setLoading(false));
  }, [className, year]);

  useEffect(() => { load(); }, [load]);

  const teachers = payload?.teachers || [];
  const sections = payload?.sections || [];
  const slots = payload?.slots || { total: 0, days: 0, periods_per_day: 0 };
  const rows = payload?.items || [];
  const teacherName = (id) => teachers.find((t) => t.id === id)?.name || "—";
  const totalRequired = useMemo(() => rows.reduce((s, r) => s + (r.periods_per_week || 0), 0), [rows]);
  const overBudget = totalRequired > slots.total;
  const currentClass = classes.find((c) => c.name === className);

  return (
    <div className="space-y-5" data-testid="tt-requirements">
      <div className="rounded-lg border border-indigo-200 dark:border-indigo-500/30 bg-indigo-50/60 dark:bg-indigo-500/10 px-4 py-2.5 flex items-center gap-2 text-sm text-indigo-700 dark:text-indigo-300" data-testid="req-readonly-banner">
        <Lock size={14} /> This is a read-only overview. Edit periods and teachers in <span className="font-semibold">Class Hub → Subjects &amp; Teachers</span>.
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Layers size={15} className="text-slate-400" />
          <Select value={className} onValueChange={setClassName}>
            <SelectTrigger className="w-56" data-testid="req-class-select"><SelectValue placeholder="Pick a grade/class" /></SelectTrigger>
            <SelectContent>
              {classes.map((c) => (
                <SelectItem key={c.id} value={c.name}>{c.name}{c.academic_unit_name ? ` · ${c.academic_unit_name}` : ""}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-3">
          <span data-testid="req-budget"
            className={`inline-flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-full ${
              overBudget ? "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400" : "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400"
            }`}>
            {overBudget ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
            {totalRequired} / {slots.total} periods·week
            <span className="opacity-60 font-normal">({slots.days}d × {slots.periods_per_day}p)</span>
          </span>
          {currentClass && (
            <Button asChild className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="req-edit-in-hub">
              <Link to={`/app/class-hub/${currentClass.id}?tab=subjects`}><Pencil size={14} className="mr-1" /> Edit in Class Hub</Link>
            </Button>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-900/60 text-left">
            <tr>
              {["Subject", "Periods / week", "Consecutive", "Must be consecutive", "Teachers"].map((h) => (
                <th key={h} className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {loading ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-400" data-testid="req-empty">No subjects offered for {className} yet.</td></tr>
            ) : rows.map((r) => {
              const cons = r.consecutive_periods || 1;
              const mapped = Object.keys(r.section_teachers || {});
              return (
                <tr key={r.subject} className="hover:bg-slate-50 dark:hover:bg-slate-800/40" data-testid={`req-row-${r.subject}`}>
                  <td className="px-4 py-2.5 font-medium text-slate-800 dark:text-slate-200">{r.subject}</td>
                  <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300" data-testid={`req-ppw-${r.subject}`}>{r.periods_per_week || 0}</td>
                  <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300">{cons}</td>
                  <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300">{cons > 1 && r.must_be_consecutive ? "Yes" : <span className="text-slate-400">—</span>}</td>
                  <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300">
                    {mapped.length === 0 ? (
                      r.teacher_ids?.length ? (
                        <span className="inline-flex items-center gap-1.5"><Users2 size={13} className="text-slate-400" />{r.teacher_ids.length === 1 ? teacherName(r.teacher_ids[0]) : `${r.teacher_ids.length} teachers`}</span>
                      ) : <span className="text-slate-400">Not assigned</span>
                    ) : (
                      <span className="flex flex-wrap gap-x-3 gap-y-1">
                        {sections.filter((s) => r.section_teachers[s]).map((s) => (
                          <span key={s} className="text-xs"><span className="text-slate-400">{s}:</span> {teacherName(r.section_teachers[s])}</span>
                        ))}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-400">
        Periods/week and consecutive rules feed the Smart Timetable generator. To change any value, open Class Hub → Subjects &amp; Teachers for this grade.
      </p>
    </div>
  );
}
