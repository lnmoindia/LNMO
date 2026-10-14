import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Download, Loader2, ShieldOff } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { PasswordInput } from "../../components/common/PasswordInput";

const API = process.env.REACT_APP_BACKEND_URL;
const ACTION_CLS = { delete: "text-red-600", partial: "text-amber-600", keep: "text-emerald-600", unclassified: "text-violet-600" };

function PlanTable({ plan }) {
  return (
    <div className="max-h-72 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-800" data-testid="reset-plan-table">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-slate-50 dark:bg-slate-900"><tr className="text-left text-slate-500">
          <th className="px-3 py-2">Collection</th><th className="px-3 py-2">Action</th><th className="px-3 py-2 text-right">Total</th><th className="px-3 py-2 text-right">Delete</th><th className="px-3 py-2">Note</th></tr></thead>
        <tbody>{plan.map((p) => (
          <tr key={p.collection} className="border-t border-slate-100 dark:border-slate-800">
            <td className="px-3 py-1.5 font-mono">{p.collection}</td><td className={`px-3 py-1.5 font-semibold uppercase ${ACTION_CLS[p.action]}`}>{p.action}</td>
            <td className="px-3 py-1.5 text-right tabular-nums">{p.total}</td><td className="px-3 py-1.5 text-right tabular-nums">{p.delete}</td><td className="px-3 py-1.5 text-slate-500">{p.note}</td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function JobProgress({ job }) {
  if (!job) return null;
  const steps = Object.values(job.steps || {});
  const pct = job.total_steps ? Math.round((steps.filter((s) => s.done).length / job.total_steps) * 100) : 0;
  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-4 space-y-2" data-testid="reset-job">
      <p className="text-sm font-semibold">Last reset: <span className="capitalize" data-testid="reset-job-status">{job.status}</span> · {job.stage} {job.status === "running" && <Loader2 size={14} className="inline animate-spin" />}</p>
      <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden"><div className="h-full bg-red-600 transition-[width]" style={{ width: `${job.status === "completed" ? 100 : pct}%` }} /></div>
      {job.status === "completed" && <p className="text-xs text-slate-500" data-testid="reset-job-summary">Deleted {job.deleted_total} documents · final backup {job.final_backup_id?.slice(0, 8)} · {job.storage_orphans || 0} orphaned files left in storage · finished {new Date(job.finished_at).toLocaleString()}</p>}
      {job.status === "failed" && <p className="text-xs text-red-600">Interrupted: {job.error}. Confirm again to resume where it stopped.</p>}
    </div>
  );
}

export default function DangerZoneCard() {
  const [pv, setPv] = useState(null);
  const [blocked, setBlocked] = useState("");
  const [backup, setBackup] = useState(null);
  const [busy, setBusy] = useState("");
  const [pw, setPw] = useState("");
  const [phrase, setPhrase] = useState("");
  const [job, setJob] = useState(null);
  const timer = useRef(null);
  const load = () => api.get("/platform/reset/preview").then((r) => { setPv(r.data); setJob(r.data.last_job); }).catch((e) => setBlocked(e.response?.status === 409 ? errText(e) : `Couldn't load: ${errText(e)}`));
  useEffect(() => { load(); return () => clearInterval(timer.current); }, []);
  const poll = () => {
    clearInterval(timer.current);
    timer.current = setInterval(async () => {
      const { data } = await api.get("/platform/reset/status");
      setJob(data.job);
      if (data.job?.status !== "running") { clearInterval(timer.current); load(); }
    }, 2000);
  };
  const doBackup = async () => {
    setBusy("backup");
    try { const { data } = await api.post("/platform/reset/backup"); setBackup(data); toast.success("Backup created — download it before confirming"); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(""); }
  };
  const run = async () => {
    setBusy("run");
    try {
      const { data } = await api.post("/platform/reset/run", { password: pw, phrase, backup_id: backup?.id || "" });
      toast.success(data.resumed ? "Reset resumed" : "Reset started"); setPw(""); setPhrase(""); setBackup(null); poll();
    } catch (e) { toast.error(errText(e)); setPw(""); } finally { setBusy(""); }
  };
  const disabled = !!blocked;
  return (
    <div className={`rounded-2xl border-2 p-6 space-y-5 ${disabled ? "border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 opacity-80" : "border-red-300 dark:border-red-900 bg-white dark:bg-slate-900"}`} data-testid="danger-zone-card">
      <div className="flex items-start gap-3">
        <AlertTriangle className="text-red-600 shrink-0 mt-0.5" size={20} />
        <div>
          <h2 className="font-heading text-lg font-semibold text-red-700 dark:text-red-400">Danger zone: reset all data</h2>
          <p className="text-sm text-slate-500 mt-1 max-w-2xl">Permanently deletes every school (including LPGS), every non-platform user and all school data. Keeps platform manager logins, plans, platform settings/branding and the platform library. A backup is mandatory and downloadable first.</p>
        </div>
      </div>
      {disabled ? (
        <div className="flex items-center gap-2 rounded-lg bg-slate-100 dark:bg-slate-800 px-4 py-3 text-sm font-medium text-slate-600 dark:text-slate-300" data-testid="danger-zone-disabled"><ShieldOff size={16} /> {blocked}</div>
      ) : !pv ? <p className="text-sm text-slate-400">Loading dry run…</p> : (
        <div className="space-y-5">
          <div className="grid sm:grid-cols-3 gap-3 text-sm" data-testid="reset-dry-run">
            <div className="rounded-lg border p-3"><p className="text-xs text-slate-400">Database</p><p className="font-mono font-semibold" data-testid="reset-db">{pv.db}</p></div>
            <div className="rounded-lg border p-3"><p className="text-xs text-slate-400">Host</p><p className="font-mono font-semibold break-all">{pv.host}</p></div>
            <div className="rounded-lg border p-3"><p className="text-xs text-slate-400">Will delete / keep</p><p className="font-semibold tabular-nums"><span className="text-red-600">{pv.totals.delete}</span> / <span className="text-emerald-600">{pv.totals.keep}</span> docs</p></div>
          </div>
          {pv.unclassified.length > 0 && <p className="text-xs text-violet-700">Unclassified collections (only docs with institution_id are deleted): {pv.unclassified.join(", ")}</p>}
          <PlanTable plan={pv.plan} />
          <JobProgress job={job} />
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 space-y-3">
            <p className="text-sm font-semibold">Step 1: create and download a backup</p>
            <div className="flex flex-wrap gap-2 items-center">
              <Button variant="outline" onClick={doBackup} disabled={busy === "backup"} data-testid="reset-backup-btn">{busy === "backup" ? "Creating…" : "Create backup"}</Button>
              {backup && <a href={`${API}${backup.download_url}`} className="inline-flex items-center gap-1.5 text-sm font-semibold text-indigo-700 hover:underline" data-testid="reset-backup-download"><Download size={15} /> Download backup ({Math.round(backup.size / 1024)} KB)</a>}
              {backup && <span className="text-xs text-slate-500">valid for confirming until {new Date(backup.valid_until).toLocaleTimeString()}</span>}
            </div>
          </div>
          <div className="rounded-xl border border-red-200 dark:border-red-900 p-4 space-y-3">
            <p className="text-sm font-semibold">Step 2: confirm</p>
            <div className="grid sm:grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Your platform password</Label><PasswordInput value={pw} onChange={(e) => setPw(e.target.value)} data-testid="reset-password" autoComplete="current-password" /></div>
              <div className="space-y-1.5"><Label>Type <code className="font-bold">{pv.phrase}</code></Label><Input value={phrase} onChange={(e) => setPhrase(e.target.value)} data-testid="reset-phrase" autoComplete="off" /></div>
            </div>
            <Button onClick={run} disabled={!backup || !pw || phrase !== pv.phrase || busy === "run" || job?.status === "running"} className="bg-red-600 hover:bg-red-700 text-white" data-testid="reset-run-btn">
              {busy === "run" ? "Starting…" : "Reset all data"}</Button>
            {pv.next_allowed_at && <p className="text-xs text-amber-700">One reset per hour: next allowed at {new Date(pv.next_allowed_at).toLocaleTimeString()}.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
