import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { School, BookOpen, GraduationCap, ArrowRight, Inbox, Megaphone, CalendarClock, DoorOpen } from "lucide-react";
import api from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { Skeleton } from "../../components/ui/skeleton";
import { StatCard } from "../../components/common/StatCard";

export default function TeacherDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [notices, setNotices] = useState([]);
  const [grid, setGrid] = useState(null);

  useEffect(() => {
    api.get("/teacher/overview").then((r) => setData(r.data)).catch(() => setData({ assignments: [], stats: {} }));
    api.get("/notices/feed").then((r) => setNotices(r.data.notices || [])).catch(() => setNotices([]));
    api.get("/timetable/teacher-grid").then((r) => setGrid(r.data)).catch(() => setGrid(null));
  }, []);

  const todayKey = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"][new Date().getDay()];
  const nowHM = new Date().toTimeString().slice(0, 5);
  const todayClasses = (grid?.entries || [])
    .filter((e) => e.day === todayKey)
    .map((e) => ({ ...e, period: grid.config.periods[e.period_no - 1] || {} }))
    .sort((a, b) => a.period_no - b.period_no);
  const current = todayClasses.find((e) => e.period.start && e.period.end && e.period.start <= nowHM && nowHM < e.period.end);
  const upNext = todayClasses.find((e) => e.period.start && e.period.start > nowHM);

  const stats = data?.stats || {};
  const assignments = data?.assignments || [];

  if (data === null) {
    return (
      <div className="space-y-4" data-testid="teacher-dashboard-loading">
        <Skeleton className="h-9 w-64" />
        <div className="grid grid-cols-3 gap-4 max-w-2xl">
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
        </div>
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-8" data-testid="teacher-dashboard">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 mb-1">
          {user?.institution_name || "Teacher Workspace"}
        </p>
        <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">
          Welcome, {user?.name?.split(" ")[0]}
        </h1>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 md:gap-4 max-w-2xl">
        <StatCard label="My Classes" value={stats.classes ?? "—"} icon={School} accent="indigo" testId="stat-my-classes" />
        <StatCard label="Subjects" value={stats.subjects ?? "—"} icon={BookOpen} accent="amber" testId="stat-my-subjects" />
        <StatCard label="Students" value={stats.students ?? "—"} icon={GraduationCap} accent="emerald" testId="stat-my-students" />
      </div>

      {grid && todayClasses.length > 0 && (
        <div className="rounded-xl border border-indigo-200 dark:border-indigo-500/30 bg-indigo-50/60 dark:bg-indigo-500/10 p-5" data-testid="dashboard-today-classes">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-heading font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2">
              <CalendarClock size={16} className="text-indigo-600" /> Today's classes
            </h3>
            <Link to="/teacher/timetable" className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline inline-flex items-center gap-1" data-testid="dashboard-timetable-link">
              Full timetable <ArrowRight size={13} />
            </Link>
          </div>
          {(current || upNext) && (
            <p className="text-sm font-medium text-indigo-800 dark:text-indigo-300 mb-3" data-testid="dashboard-up-next">
              {current
                ? `Now: ${current.subject} — ${current.class_name} ${current.section} (${current.period.label}, until ${current.period.end})`
                : `Up next: ${upNext.subject} — ${upNext.class_name} ${upNext.section} (${upNext.period.label} at ${upNext.period.start})`}
            </p>
          )}
          <div className="flex gap-3 overflow-x-auto pb-1">
            {todayClasses.map((e) => {
              const done = e.period.end && e.period.end <= nowHM;
              const active = current?.id === e.id;
              return (
                <div key={e.id} className={`min-w-[160px] rounded-lg border px-3 py-2 bg-white dark:bg-slate-900 ${active ? "border-indigo-500 ring-1 ring-indigo-400" : "border-slate-200 dark:border-slate-700"} ${done ? "opacity-50" : ""}`} data-testid={`today-class-${e.id}`}>
                  <p className="text-[11px] font-semibold text-indigo-600 dark:text-indigo-400">{e.period.label}{e.period.start ? ` · ${e.period.start}` : ""}</p>
                  <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{e.class_name} {e.section}</p>
                  <p className="text-xs text-slate-500">{e.subject}{e.room ? <span className="inline-flex items-center gap-0.5 ml-1 text-slate-400"><DoorOpen size={9} /> {e.room}</span> : ""}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-6 items-start">
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
          <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
            <h3 className="font-heading font-semibold text-slate-900 dark:text-slate-50">My assignments</h3>
          </div>
          {assignments.length === 0 ? (
            <div className="flex flex-col items-center py-12 text-center" data-testid="no-assignments">
              <Inbox className="text-slate-300 dark:text-slate-600 mb-3" size={32} strokeWidth={1.2} />
              <p className="text-sm text-slate-600 dark:text-slate-300 font-medium">No classes assigned yet</p>
              <p className="text-xs text-slate-400 mt-1">Ask your institution administrator to assign you to classes.</p>
            </div>
          ) : (
            <table className="w-full text-sm" data-testid="assignments-table">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800">
                  {["Class", "Section", "Subject"].map((h) => (
                    <th key={h} className="text-left px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {assignments.map((a) => (
                  <tr key={a.id} className="border-b border-slate-100 dark:border-slate-800/60">
                    <td className="px-5 py-2.5 text-slate-700 dark:text-slate-300">{a.class_name}</td>
                    <td className="px-5 py-2.5 text-slate-700 dark:text-slate-300">{a.section || "—"}</td>
                    <td className="px-5 py-2.5 text-slate-700 dark:text-slate-300">{a.subject || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="space-y-6">
          {notices.length > 0 && (
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm" data-testid="teacher-notices">
              <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center gap-2">
                <Megaphone size={15} className="text-indigo-600" />
                <h3 className="font-heading font-semibold text-slate-900 dark:text-slate-50">Notices</h3>
              </div>
              <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {notices.slice(0, 5).map((n) => (
                  <li key={n.id} className="px-5 py-3" data-testid={`teacher-notice-${n.id}`}>
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{n.title}</p>
                      <span className="text-[11px] text-slate-400 whitespace-nowrap">{(n.created_at || "").slice(0, 10)}</span>
                    </div>
                    {n.body && <p className="text-xs text-slate-500 mt-0.5 whitespace-pre-line line-clamp-2">{n.body}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
          <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
            <h3 className="font-heading font-semibold text-slate-900 dark:text-slate-50">Quick actions</h3>
          </div>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {[
              { label: "Mark today's attendance", path: "/teacher/attendance" },
              { label: "My weekly timetable", path: "/teacher/timetable" },
              { label: "View my students", path: "/teacher/students" },
            ].map((q) => (
              <li key={q.path}>
                <Link to={q.path} data-testid={`quick-action-${q.path.split("/").pop()}`} className="flex items-center justify-between px-5 py-3.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors group">
                  {q.label}
                  <ArrowRight size={15} className="text-slate-300 group-hover:text-indigo-600 group-hover:translate-x-0.5 transition-all" />
                </Link>
              </li>
            ))}
          </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
