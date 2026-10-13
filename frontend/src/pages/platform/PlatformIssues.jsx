import { useCallback, useEffect, useState } from "react";
import {
  Bug, MessageSquareWarning, Building2, Clock, CheckCircle2, X, Image as ImageIcon, RefreshCw,
} from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { StatCard } from "../../components/common/StatCard";
import { Button } from "../../components/ui/button";
import { Textarea } from "../../components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from "../../components/ui/sheet";

const STATUS = {
  open: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
  in_progress: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-400",
  resolved: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
  closed: "bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300",
};
const TypeBadge = ({ t }) => (
  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${t === "crash" ? "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400" : "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400"}`}>
    {t === "crash" ? <Bug size={11} /> : <MessageSquareWarning size={11} />} {t}
  </span>
);
const Pill = ({ s }) => <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${STATUS[s] || STATUS.open}`}>{s?.replace("_", " ")}</span>;
const fmt = (d) => (d ? new Date(d).toLocaleString() : "—");

export default function PlatformIssues() {
  const [stats, setStats] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ type: "", status: "" });
  const [active, setActive] = useState(null);
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, l] = await Promise.all([
        api.get("/support/issues/stats"),
        api.get("/support/issues", { params: { type: filters.type, status: filters.status } }),
      ]);
      setStats(s.data); setRows(l.data.issues);
    } catch (e) { toast.error(errText(e)); } finally { setLoading(false); }
  }, [filters]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    try { const { data } = await api.get(`/support/issues/${id}`); setActive(data); setNote(data.platform_note || ""); }
    catch (e) { toast.error(errText(e)); }
  };

  const setStatus = async (status) => {
    try {
      const { data } = await api.put(`/support/issues/${active.id}`, { status });
      setActive(data); toast.success(`Marked ${status.replace("_", " ")}`); load();
    } catch (e) { toast.error(errText(e)); }
  };
  const saveNote = async () => {
    try {
      const { data } = await api.put(`/support/issues/${active.id}`, { platform_note: note });
      setActive(data); toast.success("Note saved");
    } catch (e) { toast.error(errText(e)); }
  };

  return (
    <div className="space-y-6" data-testid="platform-issues">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 mb-1">Platform Console</p>
          <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">Issues & Crashes</h1>
        </div>
        <Button variant="outline" size="sm" onClick={load} data-testid="issues-refresh"><RefreshCw size={14} className="mr-1.5" /> Refresh</Button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
        <StatCard label="Open issues" value={stats?.open_issues ?? "—"} icon={MessageSquareWarning} accent="amber" testId="stat-open-issues" />
        <StatCard label="Crashes (7d)" value={stats?.crashes_7d ?? "—"} icon={Bug} accent="rose" testId="stat-crashes-7d" />
        <StatCard label="Schools affected" value={stats?.schools_affected ?? "—"} icon={Building2} accent="sky" testId="stat-schools-affected" />
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center gap-3">
          <Select value={filters.type || "__all__"} onValueChange={(v) => setFilters((f) => ({ ...f, type: v === "__all__" ? "" : v }))}>
            <SelectTrigger className="w-[150px]" data-testid="filter-type"><SelectValue placeholder="All types" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All types</SelectItem>
              <SelectItem value="crash">Crashes</SelectItem>
              <SelectItem value="report">Reports</SelectItem>
            </SelectContent>
          </Select>
          <Select value={filters.status || "__all__"} onValueChange={(v) => setFilters((f) => ({ ...f, status: v === "__all__" ? "" : v }))}>
            <SelectTrigger className="w-[160px]" data-testid="filter-status"><SelectValue placeholder="All statuses" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All statuses</SelectItem>
              {["open", "in_progress", "resolved", "closed"].map((s) => <SelectItem key={s} value={s}>{s.replace("_", " ")}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2.5">Title</th>
                <th className="px-4 py-2.5">Type</th>
                <th className="px-4 py-2.5">School</th>
                <th className="px-4 py-2.5">By</th>
                <th className="px-4 py-2.5">Count</th>
                <th className="px-4 py-2.5">Last seen</th>
                <th className="px-4 py-2.5">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {loading && <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>}
              {!loading && rows.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">No issues yet 🎉</td></tr>}
              {rows.map((r) => (
                <tr key={r.id} onClick={() => openDetail(r.id)} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 cursor-pointer" data-testid={`issue-row-${r.id}`}>
                  <td className="px-4 py-2.5 font-medium text-slate-800 dark:text-slate-100 max-w-[320px] truncate">{r.title}</td>
                  <td className="px-4 py-2.5"><TypeBadge t={r.type} /></td>
                  <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300">{r.institution_name || <span className="text-slate-400">—</span>}</td>
                  <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300">{r.user_name}<div className="text-[11px] text-slate-400">{r.role}</div></td>
                  <td className="px-4 py-2.5">{r.type === "crash" ? <span className="font-semibold">{r.occurrence_count}×</span> : "—"}</td>
                  <td className="px-4 py-2.5 text-slate-500 text-xs">{fmt(r.last_seen)}</td>
                  <td className="px-4 py-2.5"><Pill s={r.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Sheet open={!!active} onOpenChange={(o) => !o && setActive(null)}>
        <SheetContent className="w-full sm:max-w-xl overflow-y-auto" data-testid="issue-detail-drawer">
          {active && (
            <>
              <SheetHeader>
                <SheetTitle className="font-heading flex items-center gap-2 pr-6"><TypeBadge t={active.type} /> {active.title}</SheetTitle>
              </SheetHeader>
              <div className="space-y-4 py-4 text-sm">
                <div className="flex flex-wrap gap-2">
                  <Pill s={active.status} />
                  {active.category && <span className="px-2 py-0.5 rounded-full text-xs bg-slate-100 dark:bg-slate-800 capitalize">{active.category}</span>}
                  {active.type === "crash" && <span className="px-2 py-0.5 rounded-full text-xs bg-rose-50 text-rose-700 dark:bg-rose-500/10">{active.occurrence_count}× occurrences</span>}
                </div>
                <div className="grid grid-cols-2 gap-3 text-xs text-slate-500">
                  <div><p className="font-semibold text-slate-400 uppercase">School</p>{active.institution_name || "—"}</div>
                  <div><p className="font-semibold text-slate-400 uppercase">Reporter</p>{active.user_name} ({active.role})</div>
                  <div><p className="font-semibold text-slate-400 uppercase">First seen</p>{fmt(active.first_seen)}</div>
                  <div><p className="font-semibold text-slate-400 uppercase">Last seen</p>{fmt(active.last_seen)}</div>
                  <div className="col-span-2 break-all"><p className="font-semibold text-slate-400 uppercase">Page</p>{active.page_url || "—"}</div>
                  <div className="col-span-2 break-all"><p className="font-semibold text-slate-400 uppercase">User agent</p>{active.user_agent || "—"}</div>
                </div>
                {active.description && <div><p className="font-semibold text-slate-400 uppercase text-xs mb-1">Description</p><p className="text-slate-700 dark:text-slate-200 whitespace-pre-wrap">{active.description}</p></div>}
                {active.error_stack && (
                  <div>
                    <p className="font-semibold text-slate-400 uppercase text-xs mb-1">Stack trace</p>
                    <pre className="rounded-lg bg-slate-900 text-slate-100 p-3 text-[11px] overflow-x-auto max-h-64" data-testid="issue-stack">{active.error_message}{"\n\n"}{active.error_stack}</pre>
                  </div>
                )}
                {active.screenshot_path && (
                  <div>
                    <p className="font-semibold text-slate-400 uppercase text-xs mb-1 flex items-center gap-1"><ImageIcon size={12} /> Screenshot</p>
                    <img src={`${process.env.REACT_APP_BACKEND_URL}/api/support/issues/${active.id}/screenshot`} alt="screenshot" className="rounded-lg border border-slate-200 dark:border-slate-700 max-h-80" data-testid="issue-screenshot" />
                  </div>
                )}
                <div className="space-y-2">
                  <p className="font-semibold text-slate-400 uppercase text-xs">Internal note</p>
                  <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} data-testid="issue-note" />
                  <Button size="sm" variant="outline" onClick={saveNote} data-testid="issue-note-save">Save note</Button>
                </div>
                <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
                  <Button size="sm" variant="outline" onClick={() => setStatus("in_progress")} data-testid="issue-status-in_progress"><Clock size={14} className="mr-1" /> In progress</Button>
                  <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white" onClick={() => setStatus("resolved")} data-testid="issue-status-resolved"><CheckCircle2 size={14} className="mr-1" /> Resolve</Button>
                  <Button size="sm" variant="outline" onClick={() => setStatus("closed")} data-testid="issue-status-closed"><X size={14} className="mr-1" /> Close</Button>
                  <Button size="sm" variant="ghost" onClick={() => setStatus("open")} data-testid="issue-status-open">Reopen</Button>
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
