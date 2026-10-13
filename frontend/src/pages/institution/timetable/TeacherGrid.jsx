import { FlaskConical, DoorOpen } from "lucide-react";
import { DAY_SHORT } from "./days";

export default function TeacherGrid({ config, entries, testid = "tt-teacher-matrix" }) {
  const entriesAt = (day, pno) => entries.filter((e) => e.day === day && e.period_no === pno);
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
      <table className="w-full text-sm border-collapse" data-testid={testid}>
        <thead>
          <tr className="bg-slate-50 dark:bg-slate-900/60">
            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 w-32 border-b border-slate-200 dark:border-slate-800">Period</th>
            {config.working_days.map((d) => (
              <th key={d} className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 border-b border-l border-slate-200 dark:border-slate-800">{DAY_SHORT[d]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {config.periods.map((p, idx) => {
            const pno = idx + 1;
            if (p.is_break) {
              return (
                <tr key={pno} className="bg-slate-100/70 dark:bg-slate-800/40">
                  <td className="px-3 py-1.5 text-xs text-slate-400 font-medium border-b border-slate-200 dark:border-slate-800">{p.label}</td>
                  <td colSpan={config.working_days.length} className="px-3 py-1.5 text-center text-[11px] uppercase tracking-widest text-slate-400 border-b border-l border-slate-200 dark:border-slate-800">{p.label}</td>
                </tr>
              );
            }
            return (
              <tr key={pno}>
                <td className="px-3 py-2 text-xs text-slate-500 font-medium border-b border-slate-200 dark:border-slate-800 align-top">
                  {p.label}<span className="block text-[10px] text-slate-400">{p.start}–{p.end}</span>
                </td>
                {config.working_days.map((d) => (
                  <td key={d} className="border-b border-l border-slate-200 dark:border-slate-800 p-1 align-top">
                    {entriesAt(d, pno).map((e) => (
                      <div key={e.id} className="rounded-md bg-emerald-50 dark:bg-emerald-500/10 px-2 py-1.5 mb-1 last:mb-0">
                        <span className="block text-[13px] font-semibold text-emerald-800 dark:text-emerald-300 leading-tight">
                          {e.class_name} {e.section}
                        </span>
                        <span className="block text-[11px] text-slate-500">
                          {e.subject}{e.type === "lab" && <FlaskConical size={10} className="inline ml-1 text-amber-500" />}
                        </span>
                        {e.room && <span className="text-[10px] text-slate-400 inline-flex items-center gap-0.5"><DoorOpen size={10} /> {e.room}</span>}
                      </div>
                    ))}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
