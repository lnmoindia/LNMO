import { useEffect, useState } from "react";
import { MessageSquareWarning, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { useReportIssue } from "../../context/ReportIssue";

const STATUS = {
  open: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
  in_progress: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-400",
  resolved: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
  closed: "bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300",
};
const fmt = (d) => (d ? new Date(d).toLocaleString() : "—");

export default function SupportPage() {
  const { openReport } = useReportIssue();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api.get("/support/my-school-issues")
      .then(({ data }) => setRows(data.issues))
      .catch((e) => toast.error(errText(e)))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  return (
    <div className="space-y-6" data-testid="support-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">Support</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Issues reported by your school's staff and students. The platform team reviews and resolves them.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} data-testid="support-refresh"><RefreshCw size={14} className="mr-1.5" /> Refresh</Button>
          <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" size="sm" onClick={openReport} data-testid="support-report-btn"><MessageSquareWarning size={14} className="mr-1.5" /> Report an issue</Button>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-800/50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2.5">Title</th>
              <th className="px-4 py-2.5">Category</th>
              <th className="px-4 py-2.5">By</th>
              <th className="px-4 py-2.5">Reported</th>
              <th className="px-4 py-2.5">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {loading && <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-400">No issues reported yet.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} data-testid={`support-row-${r.id}`}>
                <td className="px-4 py-2.5 font-medium text-slate-800 dark:text-slate-100">{r.title}<div className="text-[11px] text-slate-400 max-w-[360px] truncate">{r.description}</div></td>
                <td className="px-4 py-2.5 capitalize text-slate-600 dark:text-slate-300">{r.category}</td>
                <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300">{r.user_name}<div className="text-[11px] text-slate-400">{r.role}</div></td>
                <td className="px-4 py-2.5 text-slate-500 text-xs">{fmt(r.created_at)}</td>
                <td className="px-4 py-2.5"><span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${STATUS[r.status] || STATUS.open}`}>{r.status?.replace("_", " ")}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
