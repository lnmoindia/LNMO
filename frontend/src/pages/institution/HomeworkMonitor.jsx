import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, BookMarked, ClipboardCheck, Clock, TrendingUp, AlertTriangle, Users } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Input } from "../../components/ui/input";

const firstOfMonth = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10); };
const todayStr = () => new Date().toISOString().slice(0, 10);

export default function HomeworkMonitor() {
  const [type, setType] = useState("homework");
  const [from, setFrom] = useState(firstOfMonth());
  const [to, setTo] = useState(todayStr());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api.get("/homework/monitor", { params: { type, from, to } })
      .then((r) => setData(r.data))
      .catch((e) => toast.error(errText(e)))
      .finally(() => setLoading(false));
  }, [type, from, to]);
  useEffect(() => { load(); }, [load]);

  const s = data?.stats;
  const Tab = ({ v, icon: Icon, label }) => (
    <button data-testid={`monitor-tab-${v}`} onClick={() => setType(v)}
      className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-colors ${type === v ? "bg-indigo-600 text-white" : "bg-white dark:bg-slate-900 text-slate-500 border border-slate-200 dark:border-slate-800 hover:text-indigo-600"}`}>
      <Icon size={16} /> {label}
    </button>
  );

  return (
    <div className="space-y-6" data-testid="homework-monitor-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Activity className="text-indigo-600" size={24} /> Homework Monitor</h1>
          <p className="text-sm text-slate-500 mt-1">Read-only oversight of homework &amp; assignment activity across your classes.</p>
        </div>
        <div className="flex items-center gap-2">
          <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="w-[150px]" data-testid="monitor-from" />
          <span className="text-slate-400">→</span>
          <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-[150px]" data-testid="monitor-to" />
        </div>
      </div>

      <div className="flex gap-2">
        <Tab v="homework" icon={BookMarked} label="Homework" />
        <Tab v="assignment" icon={ClipboardCheck} label="Assignments" />
      </div>

      {loading && <p className="text-sm text-slate-400">Loading…</p>}

      {s && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Stat tone="indigo" icon={Activity} label={`Active ${type === "homework" ? "homework" : "assignments"}`} value={s.active} testid="stat-active" />
            <Stat tone="emerald" icon={TrendingUp} label="Submission rate" value={`${s.submission_rate}%`} testid="stat-rate" />
            <Stat tone="amber" icon={Clock} label="Pending verification" value={s.pending_verifications} testid="stat-pending" />
            <Stat tone="rose" icon={AlertTriangle} label="Late rate" value={`${s.late_rate}%`} testid="stat-late" />
          </div>

          <Section title="Teacher activity" icon={Users} testid="monitor-teachers">
            {data.teachers.length === 0 ? <Empty /> : (
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-slate-400">
                  <tr><th className="px-5 py-2">Teacher</th><th className="px-3 py-2">Created</th><th className="px-3 py-2">Submissions</th><th className="px-3 py-2">Verified</th><th className="px-3 py-2">Pending</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                  {data.teachers.map((t) => (
                    <tr key={t.teacher_id} data-testid={`teacher-row-${t.teacher_id}`}>
                      <td className="px-5 py-2.5 font-medium text-slate-800 dark:text-slate-200">{t.teacher_name}</td>
                      <td className="px-3 py-2.5">{t.items_created}</td>
                      <td className="px-3 py-2.5">{t.submissions_received}</td>
                      <td className="px-3 py-2.5 text-emerald-600">{t.verified}</td>
                      <td className="px-3 py-2.5 text-amber-600 font-semibold">{t.pending}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>

          <Section title="Class submission rates" icon={TrendingUp} testid="monitor-classes">
            {data.classes.length === 0 ? <Empty /> : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {data.classes.map((c, i) => (
                  <div key={i} className="px-5 py-3" data-testid={`class-row-${c.class_name}-${c.section}`}>
                    <div className="flex items-center justify-between text-sm mb-1.5">
                      <span className="font-medium text-slate-800 dark:text-slate-200">{c.class_name} · {c.section} <span className="text-xs text-slate-400">({c.items} items · {c.submitted}/{c.assigned})</span></span>
                      <span className="text-xs text-slate-500">{c.submitted_pct}% submitted · {c.late_pct}% late · {c.redo} redo</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                      <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-emerald-500 transition-all" style={{ width: `${Math.min(100, c.submitted_pct)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section title="Pending verifications" icon={Clock} testid="monitor-pending">
            {data.pending.length === 0 ? <p className="px-5 py-6 text-sm text-slate-400">Nothing awaiting review — all caught up.</p> : (
              <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {data.pending.map((p) => (
                  <li key={p.submission_id} className="px-5 py-3 flex items-center justify-between gap-3" data-testid={`pending-${p.submission_id}`}>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{p.title} <span className="text-xs text-slate-400">· {p.subject} · {p.class_name} {p.section}</span></p>
                      <p className="text-xs text-slate-500">{p.student_name} → {p.teacher_name}</p>
                    </div>
                    <span className={`text-xs font-bold rounded-full px-2.5 py-1 whitespace-nowrap ${p.age_days >= 3 ? "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300" : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"}`}>{p.age_days === 0 ? "today" : `${p.age_days}d old`}</span>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </>
      )}
    </div>
  );
}

const TONES = {
  indigo: "text-indigo-600 bg-indigo-500/10", emerald: "text-emerald-600 bg-emerald-500/10",
  amber: "text-amber-600 bg-amber-500/10", rose: "text-rose-600 bg-rose-500/10",
};
function Stat({ tone, icon: Icon, label, value, testid }) {
  return (
    <div className="rounded-2xl border-2 border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm" data-testid={testid}>
      <div className={`h-9 w-9 rounded-xl flex items-center justify-center ${TONES[tone]}`}><Icon size={17} /></div>
      <p className="mt-2.5 font-heading text-2xl font-bold text-slate-900 dark:text-slate-50">{value}</p>
      <p className="text-xs text-slate-400 mt-0.5">{label}</p>
    </div>
  );
}
function Section({ title, icon: Icon, children, testid }) {
  return (
    <div className="rounded-3xl border-2 border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-md overflow-hidden" data-testid={testid}>
      <div className="px-5 py-3.5 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
        <Icon size={16} className="text-indigo-600" />
        <h2 className="font-heading text-base font-bold text-slate-900 dark:text-slate-50">{title}</h2>
      </div>
      {children}
    </div>
  );
}
const Empty = () => <p className="px-5 py-6 text-sm text-slate-400">No activity in this range.</p>;
