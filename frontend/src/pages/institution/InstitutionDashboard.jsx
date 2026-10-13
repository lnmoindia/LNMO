import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { GraduationCap, Users, School, Rows3, BookOpen, UserCog, ArrowRight, AlertTriangle, CheckCircle2 } from "lucide-react";
import api from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { StatCard, ActivityFeed } from "../../components/common/StatCard";

export default function InstitutionDashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [setup, setSetup] = useState(null);

  useEffect(() => {
    api.get("/institution/stats").then((r) => setStats(r.data)).catch(() => setStats({ counts: {}, recent_activity: [] }));
    api.get("/institution/setup-status").then((r) => setSetup(r.data)).catch(() => setSetup(null));
  }, []);

  const c = stats?.counts || {};
  const quick = [
    { label: "Admit a student", path: "/app/students" },
    { label: "Add a teacher", path: "/app/teachers" },
    { label: "Create a class", path: "/app/classes" },
    { label: "Invite a user", path: "/app/users" },
  ];

  return (
    <div className="space-y-8" data-testid="institution-dashboard">
      {setup?.migrated_general_unit && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10 p-4" data-testid="migration-banner">
          <AlertTriangle size={18} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
          <div className="flex-1 text-sm">
            <p className="font-medium text-amber-800 dark:text-amber-200">Existing academic data was assigned to a “General” unit.</p>
            <p className="text-amber-700/80 dark:text-amber-300/80 mt-0.5">Please review your setup and reorganise classes into the right academic units.</p>
          </div>
          <Link to="/app/setup" data-testid="migration-review-link" className="text-sm font-medium text-amber-800 dark:text-amber-200 underline underline-offset-2 shrink-0">Review setup</Link>
        </div>
      )}
      {setup && setup.setup_complete && !setup.operationally_ready && (
        <div className="flex items-start gap-3 rounded-xl border border-indigo-200 bg-indigo-50 dark:border-indigo-500/30 dark:bg-indigo-500/10 p-4" data-testid="readiness-banner">
          <CheckCircle2 size={18} className="text-indigo-600 dark:text-indigo-400 mt-0.5 shrink-0" />
          <div className="flex-1 text-sm">
            <p className="font-medium text-indigo-800 dark:text-indigo-200">Setup complete — one step from operational.</p>
            <p className="text-indigo-700/80 dark:text-indigo-300/80 mt-0.5">Add at least one teacher and one teacher assignment to become <span className="font-medium">Operationally Ready</span>.</p>
          </div>
          <Link to="/app/teachers" className="text-sm font-medium text-indigo-800 dark:text-indigo-200 underline underline-offset-2 shrink-0">Add teachers</Link>
        </div>
      )}
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 mb-1">
          {user?.institution_name || "Institution Console"}
        </p>
        <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">Institution overview</h1>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3 md:gap-4">
        <StatCard label="Students" value={c.students ?? "—"} icon={GraduationCap} accent="indigo" testId="stat-students" />
        <StatCard label="Teachers" value={c.teachers ?? "—"} icon={Users} accent="amber" testId="stat-teachers" />
        <StatCard label="Classes" value={c.classes ?? "—"} icon={School} accent="emerald" testId="stat-classes" />
        <StatCard label="Sections" value={c.sections ?? "—"} icon={Rows3} accent="sky" testId="stat-sections" />
        <StatCard label="Subjects" value={c.subjects ?? "—"} icon={BookOpen} accent="indigo" testId="stat-subjects" />
        <StatCard label="Users" value={c.users ?? "—"} icon={UserCog} accent="amber" testId="stat-institution-users" />
      </div>
      <div className="grid lg:grid-cols-2 gap-6 items-start">
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
          <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
            <h3 className="font-heading font-semibold text-slate-900 dark:text-slate-50">Quick actions</h3>
          </div>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {quick.map((q) => (
              <li key={q.path}>
                <Link to={q.path} data-testid={`quick-action-${q.path.split("/").pop()}`} className="flex items-center justify-between px-5 py-3.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors group">
                  {q.label}
                  <ArrowRight size={15} className="text-slate-300 group-hover:text-indigo-600 group-hover:translate-x-0.5 transition-all" />
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <ActivityFeed items={stats?.recent_activity || []} />
      </div>
    </div>
  );
}
