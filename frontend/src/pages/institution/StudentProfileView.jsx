import { useCallback, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  User, GraduationCap, CalendarCheck, Award, Trophy, Phone, Printer, ChevronRight,
  Users2, Link2Off, BookOpen, History, Crown, Medal, Send,
} from "lucide-react";
import api, { errText } from "../../lib/api";
import { toast } from "sonner";
import { Button } from "../../components/ui/button";
import { printReportCard } from "../../lib/printDoc";
import { AccountLock } from "../../components/common/AccountLock";

const API = process.env.REACT_APP_BACKEND_URL;
const fullName = (s) => `${s?.first_name || ""} ${s?.last_name || ""}`.trim() || "—";

export default function StudentProfileView() {
  const { id } = useParams();
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(() => {
    api.get(`/students/${id}/profile`).then((r) => setD(r.data))
      .catch((e) => { setErr(errText(e)); });
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const unlinkParent = async (email) => {
    if (!window.confirm(`Unlink ${email} from this student?`)) return;
    try { await api.post(`/students/${id}/unlink-parent`, { email }); toast.success("Parent unlinked"); load(); }
    catch (e) { toast.error(errText(e)); }
  };
  const printCard = async () => {
    try { const { data } = await api.get(`/students/${id}/report-card`); printReportCard(data); }
    catch (e) { toast.error(errText(e)); }
  };
  const [sending, setSending] = useState(false);
  const sendReportCard = async () => {
    if (!window.confirm("Send this student's report card to the guardian via WhatsApp?")) return;
    setSending(true);
    try {
      const { data } = await api.post("/comm/send-report-card", { student_id: id, channel: "whatsapp" });
      toast.success(data.ok === false ? (data.message || "Not sent") : `Report card sent to ${data.student_name}'s guardian`);
    } catch (e) { toast.error(errText(e)); } finally { setSending(false); }
  };

  if (err) return <div className="py-16 text-center text-slate-400" data-testid="student-profile-error">{err}</div>;
  if (!d) return <p className="py-16 text-center text-sm text-slate-400">Loading…</p>;
  const s = d.student;

  return (
    <div className="space-y-6" data-testid="student-profile-view">
      <nav className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400" data-testid="student-profile-breadcrumb">
        <Link to="/app/students" className="text-indigo-600 dark:text-indigo-400 hover:underline" data-testid="back-to-students">Students</Link>
        <ChevronRight size={14} />
        <span className="text-slate-700 dark:text-slate-200 font-medium">{fullName(s)}</span>
      </nav>

      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 flex items-center justify-between gap-5 flex-wrap" data-testid="student-profile-hero">
        <div className="flex items-center gap-5 min-w-0">
          <div className="h-20 w-20 rounded-full bg-indigo-600 flex items-center justify-center text-white shrink-0 overflow-hidden">
            {s.photo_path ? <img src={`${API}/api/students/${s.id}/photo`} alt="" className="h-full w-full object-cover" data-testid="student-profile-photo" /> : <User size={34} />}
          </div>
          <div className="min-w-0">
            <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2 flex-wrap" data-testid="student-profile-name">
              {fullName(s)}
              {d.leader_role === "class_leader" && <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300"><Crown size={12} /> Class Leader</span>}
              {d.leader_role === "second_leader" && <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"><Medal size={12} /> Second Leader</span>}
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              {s.admission_no ? `Adm. ${s.admission_no} · ` : ""}{s.class_name || "—"}{s.section ? ` · Section ${s.section}` : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <AccountLock userId={s.user_id || s.id} />
          <Button variant="outline" onClick={sendReportCard} disabled={sending} data-testid="student-send-report-card"><Send size={15} className="mr-1.5" /> {sending ? "Sending…" : "Send report card"}</Button>
          <Button variant="outline" onClick={printCard} data-testid="student-print-report-card"><Printer size={15} className="mr-1.5" /> Report card</Button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4" data-testid="student-profile-stats">
        <Stat icon={CalendarCheck} label="Attendance" value={d.attendance.pct !== null ? `${d.attendance.pct}%` : "—"} sub={d.attendance.total ? `${d.attendance.present}/${d.attendance.total} days` : "No records"} />
        <Stat icon={Award} label="Results" value={d.results.length} sub="published" />
        <Stat icon={Trophy} label="Achievements" value={d.achievements.length} sub="recorded" />
        <Stat icon={BookOpen} label="Upcoming exams" value={d.upcoming_exams.length} sub="published" />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <Panel icon={User} title="Details" testid="student-details">
          <dl className="px-5 py-3 text-sm divide-y divide-slate-100 dark:divide-slate-800/60">
            <Row k="Guardian" v={s.guardian_name} />
            <Row k="Guardian phone" v={s.guardian_phone} icon={Phone} />
            <Row k="Gender" v={s.gender} />
            <Row k="Enrollment" v={d.enrollment ? `${d.enrollment.class_name || ""}${d.enrollment.section ? " · " + d.enrollment.section : ""} (${d.enrollment.academic_year || ""})` : (s.enrollment_status || "—")} />
          </dl>
        </Panel>

        <Panel icon={Users2} title="Linked parent accounts" testid="student-parents">
          {d.parents.length ? (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {d.parents.map((p) => (
                <li key={p.id} className="px-5 py-3 flex items-center justify-between text-sm">
                  <span className="text-slate-700 dark:text-slate-200 truncate">{p.name || p.email} <span className="text-slate-400">· {p.email}</span></span>
                  <button onClick={() => unlinkParent(p.email)} className="inline-flex items-center gap-1 text-red-600 hover:text-red-700 text-xs font-medium" data-testid={`student-unlink-parent-${p.email}`}><Link2Off size={13} /> Unlink</button>
                </li>
              ))}
            </ul>
          ) : <p className="px-5 py-6 text-sm text-slate-400">No parent accounts linked.</p>}
        </Panel>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <Panel icon={Award} title="Published results" testid="student-results">
          {d.results.length ? (
            <table className="w-full text-sm"><tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {d.results.map((r, i) => (
                <tr key={i}><td className="px-5 py-2.5 text-slate-700 dark:text-slate-300">{r.assessment}</td>
                  <td className="px-5 py-2.5 text-slate-500">{r.subject || "—"}</td>
                  <td className="px-5 py-2.5 text-right font-medium text-slate-800 dark:text-slate-200">{r.score ?? "—"}{r.max_marks ? ` / ${r.max_marks}` : ""}</td></tr>
              ))}
            </tbody></table>
          ) : <p className="px-5 py-6 text-sm text-slate-400">No published results yet.</p>}
        </Panel>

        <Panel icon={BookOpen} title="Upcoming exams" testid="student-exams">
          {d.upcoming_exams.length ? (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {d.upcoming_exams.map((e, i) => (
                <li key={i} className="px-5 py-2.5 flex items-center justify-between text-sm">
                  <span className="font-medium text-slate-700 dark:text-slate-200">{e.subject}</span>
                  <span className="text-slate-500">{e.date} · {e.start}–{e.end}{e.room ? ` · ${e.room}` : ""}</span>
                </li>
              ))}
            </ul>
          ) : <p className="px-5 py-6 text-sm text-slate-400">No upcoming published exams.</p>}
        </Panel>
      </div>

      <Panel icon={History} title="Recent attendance" testid="student-attendance-history">
        {d.attendance_history.length ? (
          <div className="px-5 py-4 flex flex-wrap gap-2">
            {d.attendance_history.map((h, i) => {
              const st = String(h.status || "").toLowerCase();
              const cls = st.startsWith("p") ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300"
                : st.startsWith("l") ? "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300"
                : "bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-300";
              return <span key={i} className={`px-3 py-1 rounded-xl text-xs font-semibold ${cls}`}>{h.date} · {st.charAt(0).toUpperCase() + st.slice(1)}</span>;
            })}
          </div>
        ) : <p className="px-5 py-6 text-sm text-slate-400">No attendance records yet.</p>}
      </Panel>
    </div>
  );
}

const Stat = ({ icon: Icon, label, value, sub }) => (
  <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
    <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-400"><Icon size={13} /> {label}</div>
    <p className="mt-1.5 font-heading text-2xl font-bold text-slate-900 dark:text-slate-50">{value}</p>
    {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
  </div>
);
const Panel = ({ icon: Icon, title, children, testid }) => (
  <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden" data-testid={testid}>
    <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
      <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Icon size={15} className="text-indigo-600" /> {title}</h2>
    </div>
    {children}
  </div>
);
const Row = ({ k, v, icon: Icon }) => (
  <div className="py-2.5 flex items-center justify-between">
    <dt className="text-slate-400">{k}</dt>
    <dd className="text-slate-700 dark:text-slate-200 font-medium inline-flex items-center gap-1.5">{Icon && v && <Icon size={13} className="text-slate-400" />}{v || "—"}</dd>
  </div>
);
