export const StatCard = ({ label, value, icon: Icon, accent = "indigo", testId }) => {
  const accents = {
    indigo: "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400",
    amber: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
    emerald: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
    sky: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-400",
  };
  return (
    <div className="min-w-0 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 md:p-5 shadow-sm hover:border-slate-300 dark:hover:border-slate-700 transition-colors" data-testid={testId}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 truncate">{label}</p>
        <div className={`h-8 w-8 shrink-0 rounded-lg flex items-center justify-center ${accents[accent]}`}>
          <Icon size={15} />
        </div>
      </div>
      <p className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50 mt-3">{value}</p>
    </div>
  );
};

const ACTION_LABELS = { create: "created", update: "updated", delete: "deleted", login: "signed in to" };

export const ActivityFeed = ({ items }) => (
  <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm" data-testid="recent-activity">
    <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
      <h3 className="font-heading font-semibold text-slate-900 dark:text-slate-50">Recent activity</h3>
    </div>
    {items.length === 0 ? (
      <p className="px-5 py-8 text-sm text-slate-400 text-center">No activity recorded yet.</p>
    ) : (
      <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
        {items.map((a) => (
          <li key={a.id} className="px-5 py-3 flex items-center gap-3">
            <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${
              a.action === "create" ? "bg-emerald-500" : a.action === "delete" ? "bg-red-500" : a.action === "update" ? "bg-amber-500" : "bg-sky-500"
            }`} />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-slate-700 dark:text-slate-300 truncate">
                <span className="font-medium">{a.actor_email}</span> {ACTION_LABELS[a.action] || a.action} {a.resource}
                {a.entity_name ? ` · ${a.entity_name}` : ""}
              </p>
              <p className="text-xs text-slate-400">{new Date(a.timestamp).toLocaleString()}</p>
            </div>
          </li>
        ))}
      </ul>
    )}
  </div>
);
