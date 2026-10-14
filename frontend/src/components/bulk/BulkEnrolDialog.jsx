import { useEffect, useState } from "react";
import { Loader2, UserPlus } from "lucide-react";
import api, { errText } from "../../lib/api";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../ui/dialog";

const sel = "h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 text-sm";

// Review → enrol the run's "not enrolled" students with the existing enrollment rules, then optionally retry the original action.
export function BulkEnrolDialog({ runId, open, onClose, onDone }) {
  const [d, setD] = useState(null);
  const [rows, setRows] = useState([]);
  const [year, setYear] = useState("");
  const [retry, setRetry] = useState(true);
  const [all, setAll] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  useEffect(() => {
    if (!open) return;
    setD(null); setErr(null);
    api.get(`/bulk-runs/${runId}/enrol-preview`).then((r) => { setD(r.data); setRows(r.data.rows); setYear(r.data.academic_year || ""); }).catch((e) => setErr(errText(e)));
  }, [open, runId]);
  const upd = (i, patch) => setRows(rows.map((r, n) => (n === i ? { ...r, ...patch } : r)));
  const setAllSections = (v) => {
    setAll(v);
    const [cn, sec] = v.split("||");
    setRows(rows.map((r) => (r.status === "skip" ? r : { ...r, class_name: cn, section: sec || null })));
  };
  const ready = rows.filter((r) => r.status !== "skip");
  const missing = ready.filter((r) => !r.class_name || ((d?.classes[r.class_name] || []).length && !r.section));
  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/bulk-runs/${runId}/enrol`, { academic_year: year, retry, rows: ready.map(({ student_id, class_name, section }) => ({ student_id, class_name, section })) });
      onDone(data);
    } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  const opts = d ? Object.entries(d.classes).flatMap(([c, ss]) => (ss.length ? ss.map((s) => [`${c}||${s}`, `${c} · ${s}`]) : [[`${c}||`, c]])) : [];
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl" data-testid="bulk-enrol-dialog">
        <DialogHeader>
          <DialogTitle>Enrol not-enrolled students</DialogTitle>
          <DialogDescription>Uses the normal enrolment rules. Inactive students and students already enrolled this year are skipped.</DialogDescription>
        </DialogHeader>
        {err && <p className="text-sm text-rose-600" data-testid="bulk-enrol-error">{err}</p>}
        {!d && !err && <Loader2 className="animate-spin text-slate-400" />}
        {d && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <label className="flex items-center gap-2">Academic year <input value={year} onChange={(e) => setYear(e.target.value)} className={`${sel} w-28`} data-testid="bulk-enrol-year" /></label>
              <label className="flex items-center gap-2">Set section for all
                <select value={all} onChange={(e) => setAllSections(e.target.value)} className={sel} data-testid="bulk-enrol-set-all">
                  <option value="">—</option>{opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </label>
            </div>
            <div className="max-h-80 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-800/60 text-left text-[11px] uppercase tracking-wide text-slate-500 sticky top-0"><tr><th className="px-3 py-2">Student</th><th className="px-3 py-2">Class / section</th><th className="px-3 py-2">Note</th></tr></thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {rows.map((r, i) => (
                    <tr key={r.student_id} data-testid={`bulk-enrol-row-${r.student_id}`}>
                      <td className="px-3 py-2"><p className="font-medium">{r.name}</p><p className="text-xs text-slate-500">{r.admission_no || "—"}</p></td>
                      <td className="px-3 py-2">
                        {r.status === "skip" ? <span className="text-xs text-slate-400">—</span> : (
                          <select value={r.class_name ? `${r.class_name}||${r.section || ""}` : ""} onChange={(e) => { const [c, s] = e.target.value.split("||"); upd(i, { class_name: c || null, section: s || null }); }}
                            className={`${sel} ${!r.class_name || ((d.classes[r.class_name] || []).length && !r.section) ? "border-amber-400" : ""}`} data-testid={`bulk-enrol-class-${r.student_id}`}>
                            <option value="">Pick…</option>{opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                          </select>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs" data-testid={`bulk-enrol-note-${r.student_id}`}>
                        {r.status === "skip" ? <span className="text-amber-700">{r.reason}</span>
                          : !r.class_name ? <span className="text-amber-700">{r.reason || "Pick a class/section"}</span>
                          : (d.classes[r.class_name] || []).length && !r.section ? <span className="text-amber-700">Pick a section</span>
                          : r.warning || <span className="text-slate-400">Ready</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {d.can_retry && <label className="flex items-center gap-2 text-sm"><Checkbox checked={retry} onCheckedChange={(v) => setRetry(Boolean(v))} data-testid="bulk-enrol-retry" /> Retry fee apply for these students after enrolling</label>}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={onClose}>Cancel</Button>
              <Button disabled={busy || !ready.length || missing.length > 0 || !year} onClick={submit} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="bulk-enrol-confirm">
                {busy ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <UserPlus size={14} className="mr-1.5" />} Enrol {ready.length}{missing.length ? ` (${missing.length} need a class)` : ""}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
