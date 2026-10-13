import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, XCircle, AlertTriangle, ImageIcon, Wallet } from "lucide-react";
import api, { errText } from "../../../lib/api";
import { inr, StatusChip, localToday } from "../../../lib/fees";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../../../components/ui/dialog";
import { IssueThread, openAuthedFile } from "../../portal/InvoicePay";

const sel = "h-9 rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-2 text-sm";

function Thumb({ proof }) {
  const [src, setSrc] = useState(null);
  const heic = /heic|heif/.test(proof.file_type);
  useEffect(() => {
    if (heic) return undefined;
    let url;
    api.get(`/fees/proofs/${proof.id}/file`, { responseType: "blob" }).then((r) => { url = URL.createObjectURL(r.data); setSrc(url); }).catch(() => {});
    return () => url && URL.revokeObjectURL(url);
  }, [proof.id, heic]);
  return (
    <button onClick={() => openAuthedFile(`/fees/proofs/${proof.id}/file`)} className="w-24 h-24 shrink-0 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-slate-50 dark:bg-slate-800 flex items-center justify-center" title="Open full screenshot" data-testid={`proof-thumb-${proof.id}`}>
      {src ? <img src={src} alt="Payment screenshot" className="w-full h-full object-cover" /> : <span className="text-[10px] text-slate-400 flex flex-col items-center gap-1"><ImageIcon size={18} />{heic ? "HEIC · open" : "…"}</span>}
    </button>
  );
}

function PayDialog({ title, desc, init, onClose, onSubmit, testid }) {
  const [f, setF] = useState(init);
  const [busy, setBusy] = useState(false);
  const go = async () => { setBusy(true); try { await onSubmit(f); } finally { setBusy(false); } };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid={testid}>
        <DialogHeader><DialogTitle>{title}</DialogTitle><DialogDescription>{desc}</DialogDescription></DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5"><Label>Amount (₹)</Label><Input type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} data-testid={`${testid}-amount`} /></div>
          <div className="space-y-1.5"><Label>Payment date</Label><Input type="date" max={localToday()} value={f.paid_on} onChange={(e) => setF({ ...f, paid_on: e.target.value })} data-testid={`${testid}-date`} /></div>
          <div className="space-y-1.5 col-span-2"><Label>UTR / reference</Label><Input value={f.utr} onChange={(e) => setF({ ...f, utr: e.target.value })} data-testid={`${testid}-utr`} /></div>
        </div>
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !(Number(f.amount) > 0)} onClick={go} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid={`${testid}-confirm`}>{busy ? "Saving…" : "Create receipt"}</Button></div>
      </DialogContent>
    </Dialog>
  );
}

function ProofCard({ p, onApprove, onReject }) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 flex gap-4" data-testid={`proof-card-${p.id}`}>
      <Thumb proof={p} />
      <div className="flex-1 min-w-0 text-sm space-y-1">
        <div className="flex flex-wrap items-center gap-2"><b className="text-slate-800 dark:text-slate-100">{p.student_name}</b><span className="text-xs text-slate-500">{p.class_name} {p.section} · {p.period_label}</span><StatusChip status={p.status} testid={`proof-status-chip-${p.id}`} /></div>
        <p className="tabular-nums"><b className="text-lg">{inr(p.amount)}</b> <span className="text-xs text-slate-500">paid {p.paid_on} · UTR {p.utr || "—"} · invoice balance {inr(p.invoice_balance)}</span></p>
        <p className="text-xs text-slate-500">Submitted by {p.submitted_by_name} · {(p.submitted_at || "").slice(0, 16).replace("T", " ")}{p.note ? ` · “${p.note}”` : ""}</p>
        {p.utr_duplicate?.length > 0 && <p className="text-xs text-amber-700 flex items-center gap-1" data-testid={`proof-utr-warning-${p.id}`}><AlertTriangle size={12} /> UTR already used: {p.utr_duplicate.map((x) => x.kind === "payment" ? `receipt ${x.receipt_no} (${x.student_name})` : `${x.status} proof (${x.student_name})`).join(", ")}</p>}
        {p.status === "approved" && <p className="text-xs text-emerald-700">Receipt {p.receipt_no} · {inr(p.approved_amount)} · by {p.reviewed_by}</p>}
        {p.status === "rejected" && <p className="text-xs text-rose-700">Rejected by {p.reviewed_by}: {p.reject_reason}</p>}
      </div>
      {p.status === "pending" && (
        <div className="flex flex-col gap-2 shrink-0">
          <Button size="sm" onClick={() => onApprove(p)} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid={`proof-approve-${p.id}`}><CheckCircle2 size={13} className="mr-1" /> Approve</Button>
          <Button size="sm" variant="outline" onClick={() => onReject(p)} data-testid={`proof-reject-${p.id}`}><XCircle size={13} className="mr-1" /> Reject</Button>
        </div>
      )}
    </div>
  );
}

export default function ProofsTab({ onCounts }) {
  const [kind, setKind] = useState("proofs");
  const [status, setStatus] = useState("pending");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState(null);
  const [approve, setApprove] = useState(null);
  const [reject, setReject] = useState(null);
  const [reason, setReason] = useState("");
  const [payIssue, setPayIssue] = useState(null);
  const load = useCallback(() => {
    const req = kind === "proofs" ? api.get("/fees/proofs", { params: { status, q } }).then((r) => r.data.proofs)
      : api.get("/fees/issues", { params: { status: status === "pending" ? "open" : status } }).then((r) => r.data.issues);
    req.then(setRows).catch((e) => { toast.error(errText(e)); setRows([]); });
    onCounts?.();
  }, [kind, status, q, onCounts]);
  useEffect(() => { setRows(null); const t = setTimeout(load, 200); return () => clearTimeout(t); }, [load]);
  const doApprove = async (f) => {
    try {
      const { data } = await api.post(`/fees/proofs/${approve.id}/approve`, { amount: Number(f.amount), utr: f.utr || null, paid_on: f.paid_on });
      toast.success(`Approved — receipt ${data.payment.receipt_no}`); setApprove(null); load();
    } catch (e) { toast.error(errText(e)); }
  };
  const doReject = async () => {
    try { await api.post(`/fees/proofs/${reject.id}/reject`, { reason }); toast.success("Rejected — parent notified"); setReject(null); setReason(""); load(); }
    catch (e) { toast.error(errText(e)); }
  };
  const doIssuePay = async (f) => {
    try {
      const { data } = await api.post(`/fees/issues/${payIssue.id}/record-payment`, { amount: Number(f.amount), utr: f.utr || null, paid_on: f.paid_on });
      toast.success(`Receipt ${data.payment.receipt_no} — issue resolved`); setPayIssue(null); load();
    } catch (e) { toast.error(errText(e)); }
  };
  const setIssueStatus = async (i, st) => { try { await api.post(`/fees/issues/${i.id}/status`, { status: st }); load(); } catch (e) { toast.error(errText(e)); } };
  const statuses = kind === "proofs" ? [["pending", "Pending"], ["approved", "Approved"], ["rejected", "Rejected"], ["all", "All"]] : [["pending", "Open"], ["resolved", "Resolved"], ["all", "All"]];
  return (
    <div className="space-y-4 pt-2" data-testid="fees-proofs-tab">
      <div className="flex flex-wrap gap-2 items-center">
        <div className="inline-flex rounded-lg border border-slate-200 dark:border-slate-700 p-0.5">
          {[["proofs", "Payment proofs"], ["issues", "Issues"]].map(([k, l]) => (
            <button key={k} onClick={() => { if (k !== kind) { setRows(null); setKind(k); setStatus("pending"); } }} className={`px-3 py-1.5 text-sm rounded-md transition-colors ${kind === k ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : "text-slate-600 dark:text-slate-300"}`} data-testid={`proofs-kind-${k}`}>{l}</button>
          ))}
        </div>
        <select className={sel} value={status} onChange={(e) => setStatus(e.target.value)} data-testid="proofs-status-filter">{statuses.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        {kind === "proofs" && <Input className="w-56" placeholder="Student or UTR" value={q} onChange={(e) => setQ(e.target.value)} data-testid="proofs-search" />}
      </div>
      {rows === null && <div className="h-24 rounded-xl bg-slate-100 dark:bg-slate-800 animate-pulse" />}
      {rows?.length === 0 && <p className="text-sm text-slate-400 py-8 text-center" data-testid="proofs-empty">Nothing here.</p>}
      {kind === "proofs" && rows?.filter((p) => !p.messages).map((p) => <ProofCard key={p.id} p={p} onApprove={setApprove} onReject={(x) => { setReject(x); setReason(""); }} />)}
      {kind === "issues" && rows?.filter((i) => Array.isArray(i.messages)).map((i) => (
        <div key={i.id} className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-2" data-testid={`issue-card-${i.id}`}>
          <div className="flex flex-wrap items-center gap-2 text-sm"><b>{i.student_name}</b><span className="text-xs text-slate-500">{i.class_name} {i.section} · {i.period_label} · raised by {i.raised_by_name}</span>
            <span className="ml-auto flex gap-2">
              {i.status === "open" && <Button size="sm" variant="outline" onClick={() => setPayIssue(i)} data-testid={`issue-record-payment-${i.id}`}><Wallet size={13} className="mr-1" /> Record payment</Button>}
              <Button size="sm" variant="ghost" onClick={() => setIssueStatus(i, i.status === "open" ? "resolved" : "open")} data-testid={`issue-toggle-${i.id}`}>{i.status === "open" ? "Mark resolved" : "Reopen"}</Button>
            </span></div>
          <IssueThread issue={i} replyUrl={`/fees/issues/${i.id}/reply`} asForm={false} onChanged={load} testid={`staff-issue-${i.id}`} />
        </div>
      ))}
      {approve && <PayDialog testid="proof-approve-dialog" title={`Approve ${approve.student_name}'s payment`} desc="Creates a normal UPI receipt (ledger, Day Book on the payment date, PDF). Adjust if the bank statement differs."
        init={{ amount: String(approve.amount), utr: approve.utr || "", paid_on: approve.paid_on }} onClose={() => setApprove(null)} onSubmit={doApprove} />}
      {payIssue && <PayDialog testid="issue-pay-dialog" title={`Record payment · ${payIssue.student_name}`} desc="Creates a UPI receipt and resolves this issue."
        init={{ amount: "", utr: "", paid_on: localToday() }} onClose={() => setPayIssue(null)} onSubmit={doIssuePay} />}
      {reject && (
        <Dialog open onOpenChange={(o) => !o && setReject(null)}>
          <DialogContent className="max-w-md" data-testid="proof-reject-dialog">
            <DialogHeader><DialogTitle>Reject proof?</DialogTitle><DialogDescription>The parent sees this reason and can upload a new proof.</DialogDescription></DialogHeader>
            <Input placeholder="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="proof-reject-reason" />
            <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setReject(null)}>Cancel</Button>
              <Button disabled={reason.trim().length < 3} onClick={doReject} className="bg-rose-600 hover:bg-rose-700 text-white" data-testid="proof-reject-confirm">Reject</Button></div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
