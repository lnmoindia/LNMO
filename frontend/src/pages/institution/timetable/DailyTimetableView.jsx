import { useCallback, useEffect, useState } from "react";
import { CalendarDays } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../../components/ui/select";
import { ALL_DAYS, DAY_LABELS } from "./days";

export default function DailyTimetableView({ year }) {
  const [day, setDay] = useState("mon");
  const [data, setData] = useState(null);

  const load = useCallback(() => {
    if (!year) { setData(null); return; }
    api.get("/timetable/day", { params: { day, academic_year: year } })
      .then((r) => setData(r.data)).catch((e) => toast.error(errText(e)));
  }, [day, year]);

  useEffect(() => { load(); }, [load]);

  const periods = (data?.config?.periods || []).map((p, i) => ({ ...p, pno: i + 1 }));

  return (
    <div className="space-y-4" data-testid="tt-day-view">
      <div className="flex items-center gap-2">
        <CalendarDays size={15} className="text-slate-400" />
        <Select value={day} onValueChange={setDay}>
          <SelectTrigger className="w-48" data-testid="day-select"><SelectValue /></SelectTrigger>
          <SelectContent>{ALL_DAYS.map((d) => <SelectItem key={d} value={d}>{DAY_LABELS[d]}</SelectItem>)}</SelectContent>
        </Select>
        {data && <span className="text-xs text-slate-400">{data.rows.length} class-sections</span>}
      </div>

      {!data ? <p className="text-sm text-slate-400 py-8 text-center">Loading…</p>
        : data.rows.length === 0 ? <p className="text-sm text-slate-400 py-8 text-center" data-testid="day-empty">No classes to show.</p>
        : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
          <table className="w-full text-xs border-collapse" data-testid="day-matrix">
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-900/60">
                <th className="px-2 py-2 text-left font-semibold uppercase tracking-wider text-slate-500 border-b border-slate-200 dark:border-slate-800 sticky left-0 bg-slate-50 dark:bg-slate-900/60">Class</th>
                {periods.map((p) => (
                  <th key={p.pno} className={`px-2 py-2 text-left font-semibold uppercase tracking-wider border-b border-l border-slate-200 dark:border-slate-800 ${p.is_break ? "text-slate-300" : "text-slate-500"}`}>{p.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={`${row.class_name}-${row.section}`} data-testid={`day-row-${row.class_name}-${row.section}`}>
                  <td className="px-2 py-2 font-medium text-slate-700 dark:text-slate-200 border-b border-slate-200 dark:border-slate-800 whitespace-nowrap sticky left-0 bg-white dark:bg-slate-900">{row.class_name} {row.section}</td>
                  {periods.map((p) => {
                    const e = row.cells[String(p.pno)];
                    if (p.is_break) return <td key={p.pno} className="border-b border-l border-slate-200 dark:border-slate-800 bg-slate-100/60 dark:bg-slate-800/40" />;
                    return (
                      <td key={p.pno} className="border-b border-l border-slate-200 dark:border-slate-800 p-1 align-top">
                        {e ? (
                          <div className="rounded bg-indigo-50 dark:bg-indigo-500/10 px-1.5 py-1">
                            <span className="block font-semibold text-indigo-800 dark:text-indigo-300 leading-tight">{e.subject}</span>
                            <span className="block text-slate-500 truncate">{e.teacher_name || "—"}</span>
                          </div>
                        ) : <span className="block text-center text-slate-300 dark:text-slate-700">·</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
