import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarClock, FlaskConical, DoorOpen, ArrowRight, Coffee, Sun, Repeat, CalendarDays } from "lucide-react";
import api from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { DAY_LABELS } from "../institution/timetable/days";
import { Input } from "../../components/ui/input";

const JS_DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
const todayISO = () => new Date().toISOString().slice(0, 10);

export default function TeacherTimetable() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [viewDate, setViewDate] = useState(todayISO()); // '' = weekly template

  const load = useCallback(() => {
    if (!user?.id) return;
    const params = viewDate ? { date: viewDate } : {};
    api.get(`/timetable/teacher/${user.id}`, { params }).then((r) => { setData(r.data); setError(false); }).catch(() => setError(true));
  }, [user?.id, viewDate]);
  useEffect(() => { load(); }, [load]);

  const today = JS_DAYS[new Date().getDay()];
  const overlayDay = data?.overlay_day;
  // "Today" card reflects the picked date's weekday when a date is chosen, else real today
  const focusDay = viewDate ? overlayDay : today;
  const focusRow = data?.schedule?.find((d) => d.day === focusDay);
  const focusEntries = (focusRow?.periods || []).filter((p) => p.entry).map((p) => ({ ...p.entry, _p: p }));

  return (
    <div className="space-y-6" data-testid="teacher-timetable">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">Teaching</p>
          <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50">My Timetable</h1>
          {data?.academic_year && <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Academic year {data.academic_year}</p>}
        </div>
        <div className="flex items-center gap-2" data-testid="teacher-tt-dateview">
          <CalendarDays size={15} className="text-slate-400" />
          <Input type="date" value={viewDate} onChange={(e) => setViewDate(e.target.value)} className="w-40 h-9" data-testid="teacher-tt-date" />
          {viewDate
            ? <button onClick={() => setViewDate("")} className="text-xs text-indigo-600 hover:underline" data-testid="teacher-tt-template">Weekly template</button>
            : <button onClick={() => setViewDate(todayISO())} className="text-xs text-indigo-600 hover:underline" data-testid="teacher-tt-today">Today</button>}
        </div>
      </div>

      {error && <p className="text-sm text-amber-600">Could not load your timetable. Please try again later.</p>}
      {!error && !data && <p className="text-sm text-slate-400">Loading…</p>}

      {data && (
        <>
          {/* Focus day (today or picked date) */}
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid="teacher-today-card">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2">
                <CalendarClock size={16} className="text-indigo-600" /> {viewDate ? `${viewDate} — ${DAY_LABELS[focusDay] || ""}` : `Today — ${DAY_LABELS[today]}`}
              </h2>
              <Link to="/teacher/attendance" className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline inline-flex items-center gap-1" data-testid="today-attendance-link">
                Mark attendance <ArrowRight size={13} />
              </Link>
            </div>
            {!focusRow ? (
              <p className="text-sm text-slate-400 flex items-center gap-2" data-testid="today-off"><Coffee size={15} /> No school — enjoy the day off.</p>
            ) : focusEntries.length === 0 ? (
              <p className="text-sm text-slate-400" data-testid="today-free">No periods scheduled for you.</p>
            ) : (
              <div className="flex gap-3 overflow-x-auto pb-1" data-testid="today-periods">
                {focusEntries.map((e, i) => {
                  const isSub = e.is_substitution;
                  const covered = e.substitution?.covered_by;
                  return (
                    <div key={e.id || i} data-testid={`today-period-${e._p.period_no}`}
                      className={`min-w-[180px] rounded-lg border px-3 py-2.5 ${isSub ? "border-violet-300 dark:border-violet-500/40 bg-violet-50/70 dark:bg-violet-500/10" : covered ? "border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50" : "border-indigo-200 dark:border-indigo-500/30 bg-indigo-50/60 dark:bg-indigo-500/10"}`}>
                      <p className="text-[11px] font-semibold text-indigo-600 dark:text-indigo-400">{e._p.label}{e._p.start ? ` · ${e._p.start}–${e._p.end}` : ""}</p>
                      <p className={`text-sm font-semibold mt-0.5 ${covered ? "text-slate-400 line-through" : "text-slate-800 dark:text-slate-100"}`}>{e.class_name} {e.section}</p>
                      <p className={`text-xs ${covered ? "text-slate-400" : "text-slate-500"}`}>{e.subject}{e.type === "lab" && <FlaskConical size={10} className="inline ml-1 text-amber-500" />}</p>
                      {isSub && <p className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-violet-700 bg-violet-100 dark:bg-violet-500/15 rounded px-1 py-0.5" data-testid={`today-sub-${e._p.period_no}`}><Repeat size={10} /> Substitution · covering {e.substitution?.covering_for || "—"}</p>}
                      {covered && <p className="mt-1 text-[10px] font-medium text-amber-600" data-testid={`today-covered-${e._p.period_no}`}>Covered by {covered}</p>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Weekly, day-grouped */}
          <div className="space-y-3">
            <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50">Weekly schedule{viewDate ? <span className="ml-2 text-xs font-normal text-violet-600">overlaying {viewDate}</span> : null}</h2>
            {data.entries.length === 0 && !viewDate && (
              <p className="text-sm text-slate-400 py-6 text-center rounded-xl border border-dashed border-slate-200 dark:border-slate-800" data-testid="teacher-tt-empty">
                No periods scheduled for you yet. The timetable is managed by your institution admin.
              </p>
            )}
            <div className="grid gap-3 lg:grid-cols-2">
              {data.schedule.map((d) => (
                <div key={d.day} className={`rounded-xl border bg-white dark:bg-slate-900 overflow-hidden ${viewDate && d.day === overlayDay ? "border-violet-300 dark:border-violet-500/40" : "border-slate-200 dark:border-slate-800"}`} data-testid={`teacher-day-${d.day}`}>
                  <div className="px-4 py-2.5 border-b border-slate-100 dark:border-slate-800 font-semibold text-sm text-slate-700 dark:text-slate-200">{d.label}</div>
                  <ul className="divide-y divide-slate-50 dark:divide-slate-800/60">
                    {d.periods.filter((p) => !p.is_break).map((p) => {
                      const e = p.entry;
                      const isSub = e?.is_substitution;
                      const covered = e?.substitution?.covered_by;
                      return (
                        <li key={p.period_no} className="flex items-center gap-3 px-4 py-2 text-sm">
                          <span className="w-24 shrink-0 text-xs text-slate-400">{p.label} <span className="block">{p.start}–{p.end}</span></span>
                          {e ? (
                            <span className="flex-1">
                              <span className={`font-medium ${covered ? "text-slate-400 line-through" : "text-slate-800 dark:text-slate-200"}`}>{e.class_name} {e.section}</span>
                              <span className={covered ? "text-slate-400" : "text-slate-500"}> · {e.subject}</span>
                              {e.room && <span className="text-xs text-slate-400 inline-flex items-center gap-0.5 ml-1"><DoorOpen size={10} /> {e.room}</span>}
                              {isSub && <span className="ml-2 inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-violet-700 bg-violet-100 dark:bg-violet-500/15 rounded px-1 py-0.5" data-testid={`teacher-sub-${d.day}-${p.period_no}`}><Repeat size={10} /> Sub · covering {e.substitution?.covering_for || "—"}</span>}
                              {covered && <span className="ml-2 text-[10px] font-medium text-amber-600" data-testid={`teacher-covered-${d.day}-${p.period_no}`}>Covered by {covered}</span>}
                            </span>
                          ) : (
                            <span className="flex-1 inline-flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-medium" data-testid={`teacher-free-${d.day}-${p.period_no}`}>
                              <Sun size={13} /> Free
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
