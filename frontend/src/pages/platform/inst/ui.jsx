import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Skeleton } from "../../../components/ui/skeleton";

export const Card = ({ title, action, children, className = "", testid }) => (
  <section className={`rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 ${className}`} data-testid={testid}>
    {title && (
      <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-slate-100 dark:border-slate-800">
        <h3 className="font-heading font-semibold text-slate-900 dark:text-slate-50 text-sm">{title}</h3>
        {action}
      </div>
    )}
    <div className="p-5">{children}</div>
  </section>
);

export const Metric = ({ label, value, hint, testid, tone = "slate" }) => {
  const tones = { slate: "text-slate-900 dark:text-slate-50", indigo: "text-indigo-700 dark:text-indigo-300", emerald: "text-emerald-700 dark:text-emerald-300", amber: "text-amber-700 dark:text-amber-300", red: "text-red-600 dark:text-red-400" };
  const missing = value === null || value === undefined;
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 bg-white dark:bg-slate-900" data-testid={testid}>
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</p>
      <p className={`font-heading text-2xl font-bold mt-1.5 tabular-nums ${missing ? "text-slate-300 dark:text-slate-600 text-base" : tones[tone]}`}>{missing ? "Not tracked" : value}</p>
      {hint && <p className="text-xs text-slate-500 mt-1">{hint}</p>}
    </div>
  );
};

export const SkeletonGrid = ({ n = 4 }) => (
  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="skeleton-grid">
    {Array.from({ length: n }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
  </div>
);

export const Empty = ({ children, testid }) => (
  <div className="text-center py-10 text-sm text-slate-400" data-testid={testid}>{children}</div>
);

export const TrendChart = ({ data, testid = "logins-trend-chart", height = 200 }) => (
  <div style={{ height }} data-testid={testid}>
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="lg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4f46e5" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#4f46e5" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} tick={{ fontSize: 11, fill: "#94a3b8" }} interval={6} />
        <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#94a3b8" }} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
        <Area type="monotone" dataKey="logins" name="Sign-ins" stroke="#4f46e5" strokeWidth={2} fill="url(#lg)" />
        <Area type="monotone" dataKey="users" name="Distinct users" stroke="#10b981" strokeWidth={2} fillOpacity={0} />
      </AreaChart>
    </ResponsiveContainer>
  </div>
);

export const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString([], { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
export const fmtDay = (iso) => (iso ? new Date(iso).toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" }) : "—");
export const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN")}`;

export const StatusPill = ({ status }) => {
  const s = status || "active";
  const cls = s === "active" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
    : s === "suspended" ? "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300" : "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300";
  return <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold capitalize ${cls}`} data-testid="status-pill">{s}</span>;
};

export const PlanBadge = ({ name }) => (
  <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold ${name ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300" : "bg-slate-100 text-slate-500 dark:bg-slate-800"}`} data-testid="plan-badge">{name || "No plan"}</span>
);
