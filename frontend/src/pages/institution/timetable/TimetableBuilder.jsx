import { useCallback, useEffect, useState } from "react";
import { Plus, FlaskConical, DoorOpen, Printer } from "lucide-react";
import api, { errText } from "../../../lib/api";
import { printTimetable } from "../../../lib/printDoc";
import { useAuth } from "../../../context/AuthContext";
import { toast } from "sonner";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../../components/ui/select";
import EntryDialog from "./EntryDialog";
import { DAY_SHORT } from "./days";

export default function TimetableBuilder({ year }) {
  const { user } = useAuth();
  const [classes, setClasses] = useState([]);
  const [sections, setSections] = useState([]);
  const [className, setClassName] = useState("");
  const [section, setSection] = useState("");
  const [grid, setGrid] = useState(null);
  const [slot, setSlot] = useState(null); // {day, period_no, periodLabel, entry}

  useEffect(() => {
    api.get("/lookup/classes").then((r) => setClasses(r.data)).catch(() => setClasses([]));
  }, []);

  useEffect(() => {
    setSection("");
    if (!className) { setSections([]); return; }
    api.get("/lookup/sections", { params: { class_name: className } }).then((r) => setSections(r.data)).catch(() => setSections([]));
  }, [className]);

  const load = useCallback(() => {
    if (!year || !className || !section) { setGrid(null); return; }
    api.get("/timetable/grid", { params: { academic_year: year, class_name: className, section } })
      .then((r) => setGrid(r.data))
      .catch((e) => { toast.error(errText(e)); setGrid(null); });
  }, [year, className, section]);

  useEffect(() => { load(); }, [load]);

  const entryAt = (day, pno) => grid?.entries.find((e) => e.day === day && e.period_no === pno);

  return (
    <div className="space-y-4" data-testid="tt-builder">
      <div className="flex flex-wrap items-center gap-3">
        <Select value={className} onValueChange={setClassName}>
          <SelectTrigger className="w-44" data-testid="tt-class-select"><SelectValue placeholder="Class" /></SelectTrigger>
          <SelectContent>{classes.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={section} onValueChange={setSection} disabled={!className}>
          <SelectTrigger className="w-40" data-testid="tt-section-select"><SelectValue placeholder="Section" /></SelectTrigger>
          <SelectContent>{sections.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent>
        </Select>
        {grid && (
          <>
            <button
              onClick={() => printTimetable({ schoolName: user?.institution_name, className, section, year, config: grid.config, entries: grid.entries })}
              data-testid="tt-print-btn"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-sm font-medium text-slate-600 dark:text-slate-300 hover:border-indigo-400 transition-colors"
            >
              <Printer size={14} /> Print
            </button>
            <p className="text-xs text-slate-400">
              {grid.offerings.length} offered {grid.offerings.length === 1 ? "subject" : "subjects"} · {grid.assignments.length} teacher {grid.assignments.length === 1 ? "assignment" : "assignments"}
              {grid.config.is_default && " · using default period setup (customise in Setup tab)"}
            </p>
          </>
        )}
      </div>

      {!grid ? (
        <p className="text-sm text-slate-400 py-8 text-center" data-testid="tt-builder-empty">Pick a class and section to build its weekly timetable.</p>
      ) : grid.offerings.length === 0 ? (
        <p className="text-sm text-amber-600 py-8 text-center" data-testid="tt-no-offerings">No subject offerings for {className} yet — add them in Class Hub → Subject Offerings first.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm border-collapse" data-testid="tt-matrix">
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-900/60">
                <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 w-32 border-b border-slate-200 dark:border-slate-800">Period</th>
                {grid.config.working_days.map((d) => (
                  <th key={d} className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 border-b border-l border-slate-200 dark:border-slate-800">{DAY_SHORT[d]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.config.periods.map((p, idx) => {
                const pno = idx + 1;
                if (p.is_break) {
                  return (
                    <tr key={pno} className="bg-slate-100/70 dark:bg-slate-800/40">
                      <td className="px-3 py-1.5 text-xs text-slate-400 font-medium border-b border-slate-200 dark:border-slate-800">{p.label}<span className="block text-[10px]">{p.start}–{p.end}</span></td>
                      <td colSpan={grid.config.working_days.length} className="px-3 py-1.5 text-center text-[11px] uppercase tracking-widest text-slate-400 border-b border-l border-slate-200 dark:border-slate-800">{p.label}</td>
                    </tr>
                  );
                }
                return (
                  <tr key={pno}>
                    <td className="px-3 py-2 text-xs text-slate-500 font-medium border-b border-slate-200 dark:border-slate-800 align-top">
                      {p.label}<span className="block text-[10px] text-slate-400">{p.start}–{p.end}</span>
                    </td>
                    {grid.config.working_days.map((d) => {
                      const e = entryAt(d, pno);
                      return (
                        <td key={d} className="border-b border-l border-slate-200 dark:border-slate-800 p-1 align-top">
                          <button
                            onClick={() => setSlot({ day: d, period_no: pno, periodLabel: p.label, entry: e || null })}
                            data-testid={`tt-cell-${d}-${pno}`}
                            className={`w-full min-h-[52px] rounded-md px-2 py-1.5 text-left transition-colors ${
                              e ? "bg-indigo-50 dark:bg-indigo-500/10 hover:bg-indigo-100 dark:hover:bg-indigo-500/20"
                                : "hover:bg-slate-50 dark:hover:bg-slate-800/60 group"
                            }`}
                          >
                            {e ? (
                              <>
                                <span className="block text-[13px] font-semibold text-indigo-800 dark:text-indigo-300 leading-tight">
                                  {e.subject}{e.type === "lab" && <FlaskConical size={11} className="inline ml-1 text-amber-500" />}
                                </span>
                                <span className="block text-[11px] text-slate-500 truncate">{e.teacher_name}</span>
                                {e.room && <span className="text-[10px] text-slate-400 inline-flex items-center gap-0.5"><DoorOpen size={10} /> {e.room}</span>}
                              </>
                            ) : (
                              <span className="flex items-center justify-center h-full text-slate-300 dark:text-slate-600 group-hover:text-indigo-400"><Plus size={15} /></span>
                            )}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {slot && grid && (
        <EntryDialog
          slot={slot}
          onClose={() => setSlot(null)}
          year={year}
          className={className}
          section={section}
          offerings={grid.offerings}
          assignments={grid.assignments}
          onSaved={() => { setSlot(null); load(); }}
        />
      )}
    </div>
  );
}
