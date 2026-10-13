import { useCallback, useEffect, useState } from "react";
import { GraduationCap, School, Rows3, Users, BookOpen } from "lucide-react";
import api from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { Skeleton } from "../../components/ui/skeleton";
import { ScopeChip } from "../../components/layout/ScopeChip";

const CARDS = [
  { key: "students", label: "Students", icon: GraduationCap },
  { key: "classes", label: "Classes", icon: School },
  { key: "sections", label: "Sections", icon: Rows3 },
  { key: "teachers", label: "Teachers", icon: Users },
  { key: "subjects", label: "Subjects", icon: BookOpen },
];

export default function PrincipalDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/institution/stats");
      setData(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const counts = data?.counts || {};
  const recent = data?.recent_activity || [];

  return (
    <div className="space-y-8" data-testid="principal-dashboard">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">
            Principal overview
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Welcome{user?.name ? `, ${user.name}` : ""}. Figures below are limited to your assigned scope.
          </p>
        </div>
        <ScopeChip user={user} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4" data-testid="principal-stat-cards">
        {CARDS.map((c) => (
          <div key={c.key} className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm">
            <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
              <c.icon size={16} strokeWidth={1.8} />
              <span className="text-[11px] font-semibold uppercase tracking-wider">{c.label}</span>
            </div>
            {loading
              ? <Skeleton className="h-8 w-16 mt-3" />
              : <p className="mt-2 font-heading text-3xl font-bold text-slate-900 dark:text-slate-50" data-testid={`stat-${c.key}`}>{counts[c.key] ?? 0}</p>}
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
          <h2 className="font-heading font-semibold text-slate-900 dark:text-slate-100">Recent activity</h2>
        </div>
        <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
          {loading && <div className="p-5 space-y-2">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-5 w-full" />)}</div>}
          {!loading && recent.length === 0 && (
            <p className="p-6 text-sm text-slate-400 text-center">No recent activity in your scope yet.</p>
          )}
          {!loading && recent.map((a) => (
            <div key={a.id} className="flex items-center justify-between px-5 py-3 text-sm">
              <span className="text-slate-700 dark:text-slate-300">
                <span className="font-medium">{a.actor_email}</span> {a.action} {a.resource}
                {a.entity_name ? ` · ${a.entity_name}` : ""}
              </span>
              <span className="text-xs text-slate-400">{a.timestamp ? new Date(a.timestamp).toLocaleString() : ""}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
