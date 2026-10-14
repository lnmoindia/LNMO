import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, Building2, CheckCircle2, GraduationCap, LifeBuoy, MessageSquare, UserCheck } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { ActivityFeed } from "../../components/common/StatCard";
import { Card, Metric, SkeletonGrid, TrendChart } from "./inst/ui";

const CARDS = [
  ["schools", "Total schools", Building2, "indigo"], ["active_schools", "Active schools", CheckCircle2, "emerald"],
  ["students", "Students", GraduationCap, "slate"], ["teachers", "Teachers", UserCheck, "slate"],
  ["active_users_7d", "Active users · 7d", Activity, "indigo"], ["open_issues", "Open support issues", LifeBuoy, "amber"],
  ["messages_month", "Messages this month", MessageSquare, "slate"],
];

export default function PlatformDashboard() {
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/platform/summary").then((r) => setS(r.data)).catch((e) => toast.error(errText(e))); }, []);
  return (
    <div className="space-y-8" data-testid="platform-dashboard">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 mb-1">Platform Console</p>
        <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">Global overview</h1>
      </div>
      {!s ? <SkeletonGrid n={7} /> : (
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-4">
          {CARDS.map(([k, label, Icon, tone]) => (
            <div key={k} className="relative">
              <Metric label={label} value={s[k]} tone={tone} testid={`stat-${k}`} />
              <Icon size={16} className="absolute top-4 right-4 text-slate-300" />
            </div>
          ))}
        </div>
      )}
      <div className="grid lg:grid-cols-3 gap-6 items-start">
        <Card title="Sign-ins across schools, last 30 days" className="lg:col-span-2" testid="dashboard-trend"
          action={<Link to="/platform/institutions" className="text-xs font-semibold text-indigo-600 hover:underline" data-testid="dashboard-view-schools">View schools →</Link>}>
          {s ? <TrendChart data={s.logins_trend} height={240} /> : <div className="h-60" />}
        </Card>
        <ActivityFeed items={s?.recent_activity || []} />
      </div>
      <p className="text-xs text-slate-400">Messages are counted from the message log; SMS/WhatsApp run in STUB mode, so they aren't really delivered.</p>
    </div>
  );
}
