import { CalendarClock, DoorOpen, FlaskConical, Megaphone, Paperclip, Award, TrendingUp, BookOpen } from "lucide-react";
import { CoverBadge, TodayChanges, coverFor } from "./CoverNotice";
import { ResultTrends } from "./PortalKit";
import { PCard, PEmpty } from "./PortalShell";

const API = process.env.REACT_APP_BACKEND_URL;
export const DAY_SHORT = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };
export const todayKey = () => ["sun", "mon", "tue", "wed", "thu", "fri", "sat"][new Date().getDay()];

export const todayRows = (tt) => {
  if (!tt?.config) return [];
  const day = tt.today_changes?.day || todayKey();
  return tt.config.periods.map((p, i) => ({ ...p, pno: i + 1 })).filter((p) => !p.is_break)
    .map((p) => ({ p, e: tt.entries.find((x) => x.day === day && x.period_no === p.pno), day })).filter((r) => r.e);
};

export function TodayList({ tt, prefix, title = "Today", testid }) {
  const rows = todayRows(tt);
  const day = tt?.today_changes?.day || todayKey();
  return (
    <PCard title={`${title} · ${DAY_SHORT[day]}`} icon={CalendarClock} right={tt?.class_name ? `${tt.class_name} ${tt.section || ""}` : ""} testid={testid}>
      <TodayChanges changes={tt?.today_changes} testid={`${prefix}-today-changes`} />
      {!tt?.config || !tt.config.working_days.includes(day) || rows.length === 0 ? <PEmpty icon={CalendarClock} text="No classes today." /> : (
        <ul className="px-4 sm:px-5 py-2 divide-y divide-slate-100 dark:divide-slate-800/60">
          {rows.map(({ p, e }) => (
            <li key={p.pno} className="py-2.5 flex items-start gap-3" data-testid={`${prefix}-today-p${p.pno}`}>
              <span className="w-14 shrink-0 text-xs font-bold text-[var(--brand-ink)] dark:text-[var(--brand)]">{p.label}<span className="block text-[10px] font-normal text-slate-400">{p.start}</span></span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{e.subject}{e.type === "lab" && <FlaskConical size={10} className="inline ml-1 text-amber-500" />}</p>
                <p className="text-xs text-slate-500">{e.teacher_name}{e.room ? ` · ${e.room}` : ""}</p>
                <CoverBadge item={coverFor(tt.today_changes, e.day, p.pno)} testid={`${prefix}-today-cover-${p.pno}`} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </PCard>
  );
}

export function WeekGrid({ tt, prefix, testid }) {
  const tk = tt?.today_changes?.day || todayKey();
  if (!tt?.config || !tt.entries?.length) return <PCard title="Week" icon={CalendarClock} testid={testid}><PEmpty icon={CalendarClock} text="The timetable hasn't been published yet." /></PCard>;
  return (
    <PCard title="Week" icon={CalendarClock} right={tt.academic_year} testid={testid}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse min-w-[640px]">
          <thead>
            <tr className="bg-slate-50 dark:bg-slate-900/60">
              <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-500 w-24">Period</th>
              {tt.config.working_days.map((d) => (
                <th key={d} className={`px-2.5 py-2 text-left text-[10px] font-semibold uppercase tracking-wider border-l border-slate-100 dark:border-slate-800 ${d === tk ? "text-[var(--brand-ink)] dark:text-[var(--brand)]" : "text-slate-500"}`}>{DAY_SHORT[d]}{d === tk ? " · today" : ""}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tt.config.periods.map((p, idx) => {
              const pno = idx + 1;
              if (p.is_break) return <tr key={pno} className="bg-slate-50 dark:bg-slate-800/40"><td colSpan={tt.config.working_days.length + 1} className="px-3 py-1 text-center text-[10px] uppercase tracking-widest text-slate-400">{p.label}</td></tr>;
              return (
                <tr key={pno} className="border-t border-slate-100 dark:border-slate-800/60">
                  <td className="px-3 py-2 text-xs text-slate-500 align-top">{p.label}<span className="block text-[10px] text-slate-400">{p.start}–{p.end}</span></td>
                  {tt.config.working_days.map((d) => {
                    const e = tt.entries.find((x) => x.day === d && x.period_no === pno);
                    return (
                      <td key={d} className={`px-2.5 py-2 align-top border-l border-slate-100 dark:border-slate-800 ${d === tk ? "bg-[var(--brand-soft)]" : ""}`}>
                        {e && (<><span className="block text-[13px] font-semibold text-slate-800 dark:text-slate-200 leading-tight">{e.subject}</span><span className="block text-[11px] text-slate-500">{e.teacher_name}</span>{e.room && <span className="text-[10px] text-slate-400 inline-flex items-center gap-0.5"><DoorOpen size={9} /> {e.room}</span>}<CoverBadge item={coverFor(tt.today_changes, d, pno)} testid={`${prefix}-tt-cover-${d}-${pno}`} /></>)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </PCard>
  );
}

export function NoticesList({ notices, limit, testid = "notices-list", prefix = "portal" }) {
  const list = limit ? (notices || []).slice(0, limit) : notices || [];
  if (notices === null) return <PCard title="Notices" icon={Megaphone} testid={testid}><div className="h-24 animate-pulse" /></PCard>;
  return (
    <PCard title={limit ? "Latest notices" : "School notices"} icon={Megaphone} right={notices.length ? `${notices.length}` : ""} testid={testid}>
      {list.length === 0 ? <PEmpty icon={Megaphone} text="No notices from the school right now." /> : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
          {list.map((n) => (
            <li key={n.id} className="px-4 sm:px-5 py-3.5" data-testid={`${prefix}-notice-${n.id}`}>
              <div className="flex items-start justify-between gap-4">
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{n.title}</p>
                <span className="text-xs text-slate-400 whitespace-nowrap">{(n.created_at || "").slice(0, 10)}</span>
              </div>
              {n.body && <p className={`text-xs text-slate-500 mt-0.5 whitespace-pre-line ${limit ? "line-clamp-2" : ""}`}>{n.body}</p>}
              {n.attachments?.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-1.5">
                  {n.attachments.map((a, i) => <a key={i} href={`${API}/api/notices/attachment/${n.id}/${i}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-[var(--brand-ink)] dark:text-[var(--brand)] hover:underline" data-testid={`${prefix}-notice-file-${n.id}-${i}`}><Paperclip size={11} /> {a.name}</a>)}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </PCard>
  );
}

export function ExamsList({ exams, testid = "exams-list", prefix = "portal" }) {
  return (
    <PCard title="Upcoming exams" icon={CalendarClock} right={exams?.length ? `${exams.length} paper${exams.length === 1 ? "" : "s"}` : ""} testid={testid}>
      {!exams?.length ? <PEmpty icon={CalendarClock} text="No exams scheduled right now." /> : (
        <div className="p-4 sm:px-5 space-y-2">
          {exams.map((x, i) => (
            <div key={i} className={`flex items-center justify-between gap-3 rounded-xl border px-3 py-2.5 ${x.status === "postponed" ? "border-amber-200 bg-amber-50/60 dark:border-amber-500/30 dark:bg-amber-500/10" : "border-slate-200 dark:border-slate-700"}`} data-testid={`${prefix}-exam-${i}`}>
              <div><p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{x.subject}</p><p className="text-xs text-slate-500">{x.exam_name}{x.room ? ` · ${x.room}` : ""}{x.status === "postponed" ? " · postponed" : ""}</p></div>
              <div className="text-right shrink-0"><p className="text-sm font-bold text-slate-800 dark:text-slate-100">{x.date}</p><p className="text-xs text-slate-500">{x.start}–{x.end}</p></div>
            </div>
          ))}
        </div>
      )}
    </PCard>
  );
}

export function ResultsBlock({ results = [], subjects = [], prefix = "portal" }) {
  return (
    <>
      {results.length > 0 && <PCard title="Score trends" icon={TrendingUp} testid={`${prefix}-trends`}><div className="px-3 pb-3"><ResultTrends results={results} testid={`${prefix}-trend-chart`} /></div></PCard>}
      <PCard title="Results" icon={Award} testid={`${prefix}-results`}>
        {results.length === 0 ? <PEmpty icon={Award} text="No published results yet — they appear here once the school publishes them." /> : (
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900/60 text-left"><tr>
              <th className="px-4 sm:px-5 py-2.5 text-[11px] font-semibold uppercase text-slate-500">Assessment</th>
              <th className="px-4 sm:px-5 py-2.5 text-[11px] font-semibold uppercase text-slate-500">Subject</th>
              <th className="px-4 sm:px-5 py-2.5 text-[11px] font-semibold uppercase text-slate-500 text-right">Score</th></tr></thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {results.map((r, i) => <tr key={i}><td className="px-4 sm:px-5 py-3 text-slate-700 dark:text-slate-300">{r.assessment}</td><td className="px-4 sm:px-5 py-3 text-slate-500">{r.subject || "—"}</td><td className="px-4 sm:px-5 py-3 font-semibold text-right text-slate-800 dark:text-slate-200">{r.score ?? "—"}{r.max_marks ? ` / ${r.max_marks}` : ""}</td></tr>)}
            </tbody>
          </table></div>
        )}
      </PCard>
      {subjects.length > 0 && (
        <PCard title="Subjects" icon={BookOpen} testid={`${prefix}-subjects`}>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {subjects.map((sub, i) => <li key={i} className="px-4 sm:px-5 py-3 flex items-center justify-between gap-4"><div><p className="text-sm font-medium text-slate-800 dark:text-slate-200">{sub.subject}</p><p className="text-xs text-slate-500">{sub.teacher_name || "Teacher to be assigned"}</p></div><span className="text-xs text-slate-400">Max {sub.max_marks}</span></li>)}
          </ul>
        </PCard>
      )}
    </>
  );
}

export const Field = ({ label, value, testid }) => (
  <div data-testid={testid}>
    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</p>
    <p className="text-sm font-medium text-slate-800 dark:text-slate-200 mt-0.5">{value || "—"}</p>
  </div>
);

export const Chips = ({ value, onChange, options, testid }) => (
  <div className="flex flex-wrap gap-2" data-testid={testid}>
    {options.map(([k, l, n]) => (
      <button key={k} onClick={() => onChange(k)} data-testid={`${testid}-${k}`}
        className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors ${value === k ? "bg-[var(--brand)] border-[var(--brand)] text-white" : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-[var(--brand-line)]"}`}>
        {l}{n != null ? ` · ${n}` : ""}
      </button>
    ))}
  </div>
);

// homework/assignments filter: due | submitted | overdue | all
export const filterWork = (items, f) => {
  const today = new Date().toISOString().slice(0, 10);
  const sub = (x) => Boolean(x.my_submission);
  if (!items) return items;
  if (f === "submitted") return items.filter(sub);
  if (f === "overdue") return items.filter((x) => !sub(x) && x.due_date && x.due_date < today);
  if (f === "due") return items.filter((x) => !sub(x) && (!x.due_date || x.due_date >= today) && x.status !== "closed");
  return items;
};
