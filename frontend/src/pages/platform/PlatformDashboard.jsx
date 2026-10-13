import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Building2, CreditCard, Users, ArrowRight } from "lucide-react";
import api from "../../lib/api";
import { StatCard, ActivityFeed } from "../../components/common/StatCard";

export default function PlatformDashboard() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.get("/platform/stats").then((r) => setStats(r.data)).catch(() => setStats({ counts: {}, recent_activity: [] }));
  }, []);

  const c = stats?.counts || {};
  const quick = [
    { label: "Onboard an institution", path: "/platform/institutions" },
    { label: "Define a plan", path: "/platform/plans" },
  ];

  return (
    <div className="space-y-8" data-testid="platform-dashboard">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 mb-1">Platform Console</p>
        <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">Global overview</h1>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
        <StatCard label="Institutions" value={c.institutions ?? "—"} icon={Building2} accent="amber" testId="stat-institutions" />
        <StatCard label="Plans" value={c.plans ?? "—"} icon={CreditCard} accent="emerald" testId="stat-plans" />
        <StatCard label="Users" value={c.users ?? "—"} icon={Users} accent="sky" testId="stat-users" />
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
