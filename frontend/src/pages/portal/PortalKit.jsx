import { motion } from "framer-motion";

// Shared polish kit for the student + parent portals (Phase 44). Frontend-only, reuses existing data.

export const Reveal = ({ children, delay = 0, className = "", ...rest }) => (
  <motion.div
    initial={{ opacity: 0, y: 14 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.4, delay, ease: [0.22, 1, 0.36, 1] }}
    className={className}
    {...rest}
  >
    {children}
  </motion.div>
);

export const AttendanceRing = ({ pct, size = 52, stroke = 6 }) => {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const val = pct == null ? 0 : Math.max(0, Math.min(100, pct));
  const tone = val >= 90 ? "#059669" : val >= 75 ? "#d97706" : "#e11d48";
  return (
    <svg width={size} height={size} className="shrink-0 -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} className="text-slate-200 dark:text-slate-700" stroke="currentColor" fill="none" />
      <motion.circle
        cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} stroke={tone} fill="none" strokeLinecap="round"
        strokeDasharray={circ}
        initial={{ strokeDashoffset: circ }}
        animate={{ strokeDashoffset: circ - (val / 100) * circ }}
        transition={{ duration: 0.9, ease: "easeOut" }}
      />
    </svg>
  );
};

const QTONE = {
  emerald: "bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200/80 dark:border-emerald-800/50 text-emerald-900 dark:text-emerald-100",
  indigo: "bg-indigo-50 dark:bg-indigo-950/40 border-indigo-200/80 dark:border-indigo-800/50 text-indigo-900 dark:text-indigo-100",
  fuchsia: "bg-fuchsia-50 dark:bg-fuchsia-950/40 border-fuchsia-200/80 dark:border-fuchsia-800/50 text-fuchsia-900 dark:text-fuchsia-100",
  sky: "bg-sky-50 dark:bg-sky-950/40 border-sky-200/80 dark:border-sky-800/50 text-sky-900 dark:text-sky-100",
  purple: "bg-purple-50 dark:bg-purple-950/40 border-purple-200/80 dark:border-purple-800/50 text-purple-900 dark:text-purple-100",
  amber: "bg-amber-50 dark:bg-amber-950/40 border-amber-200/80 dark:border-amber-800/50 text-amber-900 dark:text-amber-100",
  rose: "bg-rose-50 dark:bg-rose-950/40 border-rose-200/80 dark:border-rose-800/50 text-rose-900 dark:text-rose-100",
};

export const QuickCard = ({ icon: Icon, tone = "indigo", label, value, sub, onClick, testid, children }) => {
  const Comp = onClick ? motion.button : motion.div;
  return (
    <Comp
      onClick={onClick}
      data-testid={testid}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      whileHover={onClick ? { y: -3 } : undefined}
      whileTap={onClick ? { scale: 0.98 } : undefined}
      className={`w-full text-left rounded-2xl border p-4 shadow-sm transition-shadow hover:shadow-md ${QTONE[tone]} ${onClick ? "cursor-pointer" : ""}`}
    >
      <div className="flex items-center justify-between min-h-[40px]">
        <span className="h-9 w-9 rounded-xl bg-white/70 dark:bg-black/20 flex items-center justify-center"><Icon size={17} /></span>
        {children}
      </div>
      <p className="mt-3 font-heading text-2xl font-bold leading-none">{value}</p>
      <p className="text-xs font-semibold opacity-70 mt-1">{label}</p>
      {sub && <p className="text-[11px] opacity-60 mt-0.5 line-clamp-1">{sub}</p>}
    </Comp>
  );
};

export const PortalSkeleton = () => (
  <div className="space-y-6" data-testid="portal-skeleton">
    <div className="h-28 rounded-3xl bg-slate-200/70 dark:bg-slate-800 animate-pulse" />
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
      {[...Array(5)].map((_, i) => <div key={i} className="h-28 rounded-2xl bg-slate-200/70 dark:bg-slate-800 animate-pulse" />)}
    </div>
    <div className="h-40 rounded-3xl bg-slate-200/70 dark:bg-slate-800 animate-pulse" />
  </div>
);

export const PortalEmpty = ({ icon: Icon, text }) => (
  <div className="px-6 py-8 flex flex-col items-center gap-2 text-center" data-testid="portal-empty">
    {Icon && <Icon size={26} className="text-slate-300 dark:text-slate-600" />}
    <p className="text-sm text-slate-400">{text}</p>
  </div>
);

export const BottomNav = ({ items, active, onSelect }) => (
  <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl border-t border-slate-200 dark:border-slate-800 flex pb-[env(safe-area-inset-bottom)]" data-testid="portal-bottom-nav">
    {items.map((it) => {
      const on = active === it.key;
      return (
        <button
          key={it.key}
          onClick={() => onSelect(it.key)}
          data-testid={`portal-bnav-${it.key}`}
          className={`flex-1 flex flex-col items-center justify-center gap-0.5 py-2 min-h-[54px] text-[10px] font-semibold transition-colors ${on ? "text-indigo-600 dark:text-indigo-400" : "text-slate-400 dark:text-slate-500"}`}
        >
          <it.icon size={20} strokeWidth={on ? 2.4 : 1.9} />
          {it.label}
        </button>
      );
    })}
  </nav>
);

// data helpers (homework/assignments share shape: {status:"open"|"closed", due_date, my_submission:{status,late}})
export const pendingItems = (items = []) =>
  (items || []).filter((h) => h.status === "open" && (!h.my_submission || h.my_submission.status === "redo"));

export const nearestDue = (items = []) => {
  const ds = (items || []).map((h) => h.due_date).filter(Boolean).map((d) => String(d).slice(0, 10)).sort();
  return ds[0] || null;
};

export const Sparkline = ({ points = [], width = 100, height = 30, color = "#6366f1" }) => {
  if (!points.length) return null;
  const n = points.length;
  const x = (i) => (n > 1 ? (i * width) / (n - 1) : width / 2);
  const y = (v) => height - (Math.max(0, Math.min(100, v)) / 100) * height;
  const d = points.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <svg width={width} height={height} className="shrink-0 overflow-visible" aria-hidden>
      {n > 1 && <path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />}
      <circle cx={x(n - 1)} cy={y(points[n - 1])} r="2.8" fill={color} />
    </svg>
  );
};

const TREND_PALETTE = ["#6366f1", "#ec4899", "#0ea5e9", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#14b8a6"];

export const ResultTrends = ({ results = [], testid = "result-trends" }) => {
  const bySub = {};
  (results || []).forEach((r) => {
    if (r.score != null && r.max_marks) (bySub[r.subject || "—"] = bySub[r.subject || "—"] || []).push(r);
  });
  const subs = Object.keys(bySub).sort();
  if (!subs.length) return null;
  return (
    <div className="space-y-2" data-testid={testid}>
      {subs.map((s, idx) => {
        const items = [...bySub[s]].sort((a, b) =>
          String(a.created_at || a.date || "").localeCompare(String(b.created_at || b.date || "")));
        const pcts = items.map((r) => Math.round((r.score / r.max_marks) * 100));
        const last = pcts[pcts.length - 1];
        const delta = last - pcts[0];
        const color = TREND_PALETTE[idx % TREND_PALETTE.length];
        return (
          <div key={s} className="flex items-center gap-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2" data-testid={`trend-row`}>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">{s}</p>
              <p className="text-[11px] text-slate-400">{items.length} assessment{items.length > 1 ? "s" : ""}</p>
            </div>
            <Sparkline points={pcts} color={color} />
            <div className="text-right w-12 shrink-0">
              <p className="text-sm font-bold" style={{ color }}>{last}%</p>
              {pcts.length > 1 && (
                <p className={`text-[10px] font-semibold ${delta >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500"}`}>
                  {delta >= 0 ? "▲" : "▼"}{Math.abs(delta)}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
