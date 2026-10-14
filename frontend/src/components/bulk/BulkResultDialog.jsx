import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Download, RotateCcw, ExternalLink, CheckCircle2, MinusCircle, XCircle, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../ui/dialog";
import { Button } from "../ui/button";

const OK = ["created", "sent", "linked"];
const CHIPS = [["all", "All"], ["ok", "Done"], ["skipped", "Skipped"], ["failed", "Failed"]];
const FIX = {
  open_ledger: ["Open ledger", (t) => `/app/fees?tab=accounts&account=${t}`],
  open_student: ["Open student", (t) => `/app/students/${t}`],
  enrol_student: ["Enrol student", (t) => `/app/students/${t}?enrol=1`],
  open_parent: ["Open parent", (t) => `/app/parents/${t}`],
};
const Icon = ({ s }) => (OK.includes(s) ? <CheckCircle2 size={14} className="text-emerald-600" /> : s === "failed" ? <XCircle size={14} className="text-rose-600" /> : <MinusCircle size={14} className="text-amber-500" />);

export const summaryText = (sm) => !sm ? "" : ["created", "sent", "linked", "skipped", "failed"].filter((k) => sm[k]).map((k) => `${sm[k]} ${k}`).join(" · ") || "Nothing to do";

export function BulkResultView({ run, onRetry, retrying, compact }) {
  const navigate = useNavigate();
  const [chip, setChip] = useState("all");
  const items = useMemo(() => (run?.items || []).filter((i) => chip === "all" || (chip === "ok" ? OK.includes(i.status) : i.status === chip)), [run, chip]);
  const count = (c) => (run?.items || []).filter((i) => (c === "all" ? true : c === "ok" ? OK.includes(i.status) : i.status === c)).length;
  const csv = () => {
    const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [["Item", "Details", "Result", "Reason"].map(esc).join(","), ...(run.items || []).map((i) => [i.label, i.sub_label, i.status, i.reason].map(esc).join(","))];
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    a.download = `${(run.title || "bulk-result").replace(/[^\w-]+/g, "_")}.csv`;
    a.click();
  };
  return (
    <div className="space-y-3" data-testid="bulk-result-view">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {CHIPS.map(([k, l]) => (
            <button key={k} onClick={() => setChip(k)} className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${chip === k ? "bg-slate-900 text-white border-slate-900 dark:bg-white dark:text-slate-900" : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300"}`} data-testid={`bulk-chip-${k}`}>
              {l} <span className="opacity-70">{count(k)}</span>
            </button>
          ))}
        </div>
        <div className="flex gap-1.5">
          {onRetry && <Button size="sm" variant="outline" onClick={onRetry} disabled={retrying} data-testid="bulk-retry-btn">{retrying ? <Loader2 size={13} className="mr-1 animate-spin" /> : <RotateCcw size={13} className="mr-1" />} Retry</Button>}
          <Button size="sm" variant="outline" onClick={csv} data-testid="bulk-csv-btn"><Download size={13} className="mr-1" /> CSV</Button>
        </div>
      </div>
      <div className={`overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-800 ${compact ? "max-h-80" : "max-h-[60vh]"}`}>
        <table className="w-full text-sm" data-testid="bulk-result-table">
          <thead className="bg-slate-50 dark:bg-slate-800/60 text-left text-[11px] uppercase tracking-wide text-slate-500 sticky top-0">
            <tr><th className="px-3 py-2">Item</th><th className="px-3 py-2">Result</th><th className="px-3 py-2">Reason</th><th className="px-3 py-2" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {items.length === 0 && <tr><td colSpan={4} className="px-3 py-6 text-center text-slate-400">Nothing here.</td></tr>}
            {items.map((i, n) => (
              <tr key={`${i.id}-${n}`} data-testid={`bulk-row-${i.id}`}>
                <td className="px-3 py-2"><p className="font-medium text-slate-800 dark:text-slate-100">{i.label}</p>{i.sub_label && <p className="text-xs text-slate-500">{i.sub_label}</p>}</td>
                <td className="px-3 py-2"><span className="inline-flex items-center gap-1 capitalize text-xs font-semibold" data-testid={`bulk-status-${i.id}`}><Icon s={i.status} /> {i.status}</span></td>
                <td className="px-3 py-2 text-slate-600 dark:text-slate-300" data-testid={`bulk-reason-${i.id}`}>{i.reason}</td>
                <td className="px-3 py-2 text-right">
                  {i.fix && FIX[i.fix.type] && (
                    <Button size="sm" variant="ghost" className="h-7 text-indigo-700 dark:text-indigo-300" onClick={() => navigate(FIX[i.fix.type][1](i.fix.target))} data-testid={`bulk-fix-${i.id}`}>
                      {FIX[i.fix.type][0]} <ExternalLink size={12} className="ml-1" />
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function BulkResultDialog({ run, open, onClose, onRetry, retrying }) {
  return (
    <Dialog open={open && Boolean(run)} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl" data-testid="bulk-result-dialog">
        <DialogHeader>
          <DialogTitle>{run?.title || "Result"}</DialogTitle>
          <DialogDescription data-testid="bulk-result-summary">{summaryText(run?.summary)}{run?.created_at ? ` · ${new Date(run.created_at).toLocaleString("en-IN")}` : ""}</DialogDescription>
        </DialogHeader>
        {run && <BulkResultView run={run} onRetry={onRetry} retrying={retrying} compact />}
      </DialogContent>
    </Dialog>
  );
}

// Toast-friendly helper: shows "summary — Details" with a button that opens the dialog.
export const resultToast = (toast, run, open) => toast.success(summaryText(run.summary), {
  action: { label: "View details", onClick: () => open(run) }, duration: 10000,
});

// Global host: any page can call showBulkResult(run, retry) / bulkToast(toast, run, retry).
let hostSet = null;
export const showBulkResult = (run, onRetry) => hostSet && hostSet({ run, onRetry });
export const bulkToast = (toast, run, onRetry, prefix = "") => {
  if (!run) return;
  const fn = run.summary?.failed ? toast.error : run.summary?.skipped && !(run.summary.created || run.summary.sent || run.summary.linked) ? toast.warning : toast.success;
  fn(`${prefix}${summaryText(run.summary)}`, { action: { label: "View details", onClick: () => showBulkResult(run, onRetry) }, duration: 12000 });
};

export function BulkResultHost() {
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  hostSet = setS;
  const retry = s?.onRetry ? async () => {
    setBusy(true);
    try { const run = await s.onRetry(); if (run) setS({ ...s, run }); } finally { setBusy(false); }
  } : null;
  return <BulkResultDialog run={s?.run} open={Boolean(s)} onClose={() => setS(null)} onRetry={retry} retrying={busy} />;
}
