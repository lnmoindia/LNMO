import { useEffect, useState } from "react";
import { CalendarCheck, ChevronLeft, ChevronRight } from "lucide-react";
import api from "../../lib/api";
import { PCard } from "./PortalShell";

const DOW = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const TONE = {
  present: "bg-emerald-500 text-white",
  absent: "bg-rose-500 text-white",
  late: "bg-amber-400 text-amber-950",
  leave: "bg-sky-400 text-white",
  holiday: "bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-300",
};
const ym = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;

// Month calendar shared by the parent and student portals.
export default function AttendanceCalendar({ endpoint, testid = "attendance-calendar" }) {
  const [cursor, setCursor] = useState(() => { const d = new Date(); d.setDate(1); return d; });
  const [data, setData] = useState(null);
  const month = ym(cursor);
  useEffect(() => {
    setData(null);
    api.get(endpoint, { params: { month } }).then((r) => setData(r.data)).catch(() => setData({ days: [], working_days: [] }));
  }, [endpoint, month]);
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const lead = (first.getDay() + 6) % 7;
  const n = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
  const byDate = Object.fromEntries((data?.days || []).map((d) => [d.date, d.status]));
  const today = new Date().toISOString().slice(0, 10);
  const shift = (k) => setCursor((c) => new Date(c.getFullYear(), c.getMonth() + k, 1));
  return (
    <div className="space-y-4" data-testid={testid}>
      <div className="grid grid-cols-2 gap-3">
        <Stat label="This month" pct={data?.month_pct} sub={data ? `${data.month_present}/${data.month_total} days present` : ""} testid="att-month-pct" />
        <Stat label="This year" pct={data?.year_pct} sub={data ? `${data.year_present}/${data.year_total} days present` : ""} testid="att-year-pct" />
      </div>
      <PCard title={cursor.toLocaleString("en-IN", { month: "long", year: "numeric" })} icon={CalendarCheck}
        right={<span className="flex gap-1">
          <button onClick={() => shift(-1)} className="h-7 w-7 rounded-lg border border-slate-200 dark:border-slate-700 flex items-center justify-center" data-testid="att-prev"><ChevronLeft size={14} /></button>
          <button onClick={() => shift(1)} className="h-7 w-7 rounded-lg border border-slate-200 dark:border-slate-700 flex items-center justify-center" data-testid="att-next"><ChevronRight size={14} /></button>
        </span>}>
        <div className="p-3 sm:p-5">
          <div className="grid grid-cols-7 gap-1 sm:gap-2 text-center text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1.5">
            {DOW.map((d) => <span key={d}>{d.slice(0, 2)}</span>)}
          </div>
          <div className={`grid grid-cols-7 gap-1 sm:gap-2 ${data ? "" : "animate-pulse"}`}>
            {Array.from({ length: lead }).map((_, i) => <span key={`l${i}`} />)}
            {Array.from({ length: n }).map((_, i) => {
              const date = `${month}-${String(i + 1).padStart(2, "0")}`;
              const dow = DOW[(lead + i) % 7];
              const st = byDate[date] || (data && !data.working_days.includes(dow) ? "holiday" : null);
              return (
                <div key={date} title={st || ""} data-testid={`att-day-${date}`} data-status={st || ""}
                  className={`aspect-square rounded-xl flex items-center justify-center text-xs sm:text-sm font-semibold ${st ? TONE[st] || TONE.present : "bg-slate-50 dark:bg-slate-800/60 text-slate-400"} ${date === today ? "ring-2 ring-[var(--brand)] ring-offset-1 dark:ring-offset-slate-900" : ""}`}>
                  {i + 1}
                </div>
              );
            })}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-4 text-[11px] text-slate-500">
            {[["present", "Present"], ["absent", "Absent"], ["late", "Late"], ["holiday", "No school"]].map(([k, l]) => (
              <span key={k} className="inline-flex items-center gap-1.5"><span className={`h-3 w-3 rounded ${TONE[k]}`} /> {l}</span>
            ))}
            <span className="inline-flex items-center gap-1.5"><span className="h-3 w-3 rounded bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700" /> Not marked</span>
          </div>
        </div>
      </PCard>
    </div>
  );
}

const Stat = ({ label, pct, sub, testid }) => (
  <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-4" data-testid={testid}>
    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</p>
    <p className="font-heading text-2xl font-bold text-slate-900 dark:text-white mt-1">{pct == null ? "—" : `${pct}%`}</p>
    <p className="text-xs text-slate-500 mt-0.5">{sub || " "}</p>
  </div>
);
