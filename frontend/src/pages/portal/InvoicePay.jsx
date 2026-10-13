import { useState } from "react";
import { toast } from "sonner";
import { QrCode, Smartphone, Upload, MessageSquareWarning, Printer, Clock, XCircle, Paperclip, Send, CheckCircle2 } from "lucide-react";
import api, { errText } from "../../lib/api";
import { inr, StatusChip, printInvoiceById, localToday } from "../../lib/fees";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../../components/ui/dialog";

const MAX = 5 * 1024 * 1024;
const ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif";

export const openAuthedFile = async (url) => {
  try {
    const { data } = await api.get(url, { responseType: "blob" });
    window.open(URL.createObjectURL(data), "_blank", "noopener");
  } catch (e) { toast.error(errText(e)); }
};

const fileOk = (f) => {
  if (!f) return true;
  if (f.size > MAX) { toast.error("Image must be 5 MB or smaller"); return false; }
  return true;
};

function ProofDialog({ inv, open, onClose, onDone }) {
  const [f, setF] = useState({ amount: String(inv.balance), utr: "", paid_on: localToday(), note: "", file: null });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!f.file) return toast.error("Please attach the payment screenshot");
    if (!fileOk(f.file)) return;
    setBusy(true);
    const fd = new FormData();
    fd.append("file", f.file); fd.append("amount", f.amount); fd.append("paid_on", f.paid_on); fd.append("utr", f.utr); fd.append("note", f.note);
    try {
      const { data } = await api.post(`/parent/fees/invoices/${inv.id}/proofs`, fd);
      if (data.utr_warning?.length) toast.warning("Submitted — note: this UTR was already used on another payment, the school will check it.");
      else toast.success("Thanks! The school will verify your payment and send a receipt.");
      onDone();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const amt = Number(f.amount);
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="proof-dialog">
        <DialogHeader><DialogTitle>I've paid — upload proof</DialogTitle>
          <DialogDescription>{inv.period_label} · balance {inr(inv.balance)}. Upload the UPI/bank screenshot; the school verifies it and issues a receipt.</DialogDescription></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>Payment screenshot (JPG, PNG, HEIC, WEBP · max 5 MB)</Label>
            <Input type="file" accept={ACCEPT} onChange={(e) => setF({ ...f, file: e.target.files?.[0] || null })} data-testid="proof-file" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Amount paid (₹)</Label><Input type="number" min="1" max={inv.balance} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} data-testid="proof-amount" /></div>
            <div className="space-y-1.5"><Label>Payment date</Label><Input type="date" max={localToday()} value={f.paid_on} onChange={(e) => setF({ ...f, paid_on: e.target.value })} data-testid="proof-date" /></div>
          </div>
          <div className="space-y-1.5"><Label>UTR / transaction ID <span className="text-slate-400">(recommended, usually 12 digits)</span></Label>
            <Input inputMode="numeric" value={f.utr} onChange={(e) => setF({ ...f, utr: e.target.value.replace(/\s/g, "") })} data-testid="proof-utr" /></div>
          <div className="space-y-1.5"><Label>Note (optional)</Label><Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} data-testid="proof-note" /></div>
          {(amt > inv.balance || amt <= 0) && <p className="text-xs text-rose-600" data-testid="proof-amount-error">Amount must be more than 0 and at most {inr(inv.balance)}.</p>}
        </div>
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !(amt > 0) || amt > inv.balance || !f.file} onClick={submit} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="proof-submit">{busy ? "Uploading…" : "Submit for verification"}</Button></div>
      </DialogContent>
    </Dialog>
  );
}

function IssueDialog({ inv, open, onClose, onDone }) {
  const [msg, setMsg] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!fileOk(file)) return;
    setBusy(true);
    const fd = new FormData();
    fd.append("message", msg);
    if (file) fd.append("file", file);
    try { await api.post(`/parent/fees/invoices/${inv.id}/issues`, fd); toast.success("Issue sent to the school office"); onDone(); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="issue-dialog">
        <DialogHeader><DialogTitle>I have already paid</DialogTitle>
          <DialogDescription>Tell the school what happened ({inv.period_label}). Add a screenshot if you have one.</DialogDescription></DialogHeader>
        <Textarea rows={4} value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="e.g. Paid ₹1,500 on 12 Oct via PhonePe, UTR 123456789012" data-testid="issue-message" />
        <Input type="file" accept={ACCEPT} onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="issue-file" />
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={busy || msg.trim().length < 3} onClick={submit} data-testid="issue-submit">{busy ? "Sending…" : "Send to school"}</Button></div>
      </DialogContent>
    </Dialog>
  );
}

export function IssueThread({ issue, replyUrl, asForm = true, onChanged, testid = "issue-thread" }) {
  const [text, setText] = useState("");
  const send = async () => {
    try {
      if (asForm) { const fd = new FormData(); fd.append("message", text); await api.post(replyUrl, fd); }
      else await api.post(replyUrl, { text });
      setText(""); onChanged();
    } catch (e) { toast.error(errText(e)); }
  };
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-700 p-3 space-y-2" data-testid={testid}>
      <div className="flex items-center justify-between text-xs"><span className="font-semibold text-slate-600 dark:text-slate-300 flex items-center gap-1"><MessageSquareWarning size={13} /> Fee issue</span><StatusChip status={issue.status} testid={`${testid}-status`} /></div>
      <ul className="space-y-1.5">
        {issue.messages.map((m) => (
          <li key={m.id} className={`text-sm rounded-lg px-3 py-2 ${m.by === "staff" ? "bg-indigo-50 dark:bg-indigo-500/10" : "bg-slate-50 dark:bg-slate-800/60"}`} data-testid={`${testid}-msg-${m.id}`}>
            <p className="text-[11px] text-slate-500">{m.by === "staff" ? "School" : m.by_name} · {(m.at || "").slice(0, 16).replace("T", " ")}</p>
            <p className="text-slate-800 dark:text-slate-100 whitespace-pre-wrap">{m.text}</p>
            {m.has_file && <button className="text-xs text-indigo-600 flex items-center gap-1 mt-1" onClick={() => openAuthedFile(`/fees/issues/${issue.id}/messages/${m.id}/file`)} data-testid={`${testid}-file-${m.id}`}><Paperclip size={12} /> Attachment</button>}
          </li>
        ))}
      </ul>
      {replyUrl && (
        <div className="flex gap-2"><Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Write a reply…" data-testid={`${testid}-reply`} />
          <Button size="sm" disabled={!text.trim()} onClick={send} data-testid={`${testid}-send`}><Send size={13} /></Button></div>
      )}
    </div>
  );
}

const ProofStatus = ({ p }) => (
  <div className={`rounded-xl px-3 py-2 text-sm flex items-start gap-2 ${p.status === "rejected" ? "bg-rose-50 text-rose-800 dark:bg-rose-500/10 dark:text-rose-300" : p.status === "approved" ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300" : "bg-amber-50 text-amber-900 dark:bg-amber-500/10 dark:text-amber-200"}`} data-testid={`proof-status-${p.id}`}>
    {p.status === "rejected" ? <XCircle size={15} className="mt-0.5" /> : p.status === "approved" ? <CheckCircle2 size={15} className="mt-0.5" /> : <Clock size={15} className="mt-0.5" />}
    <span>{p.status === "pending" && <>Verification pending — {inr(p.amount)} paid on {p.paid_on}{p.utr ? ` · UTR ${p.utr}` : ""}</>}
      {p.status === "approved" && <>Verified — receipt {p.receipt_no}</>}
      {p.status === "rejected" && <>Proof not accepted: <b>{p.reject_reason}</b>. You can upload a new proof.</>}</span>
  </div>
);

export default function InvoicePay({ inv, proofs, issues, onChanged }) {
  const [dlg, setDlg] = useState(null);
  const last = proofs[0];
  const pending = last && last.status === "pending";
  const openIssue = issues.find((i) => i.status === "open");
  const stale = pending && Date.now() - new Date(last.submitted_at).getTime() > 3 * 86400000;
  const canIssue = !openIssue && (inv.balance > 0 || last?.status === "rejected" || stale);
  const upi = inv.upi;
  return (
    <div className="mt-2 space-y-2" data-testid={`invoice-pay-${inv.id}`}>
      {last && <ProofStatus p={last} />}
      {upi && !pending && (
        <div className="rounded-2xl border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50/40 dark:bg-emerald-500/5 p-3 flex flex-col sm:flex-row gap-3 items-center" data-testid={`upi-block-${inv.id}`}>
          <img src={upi.qr} alt={`UPI QR for ${inr(upi.amount)}`} className="w-40 h-40 rounded-lg bg-white p-1" data-testid={`upi-qr-${inv.id}`} />
          <div className="text-sm space-y-1 text-center sm:text-left">
            <p className="font-semibold text-slate-800 dark:text-slate-100 flex items-center gap-1.5 justify-center sm:justify-start"><QrCode size={15} /> Pay with any UPI app</p>
            <p className="text-2xl font-bold text-emerald-700 tabular-nums" data-testid={`upi-amount-${inv.id}`}>{inr(upi.amount)}</p>
            <p className="text-xs text-slate-600 dark:text-slate-300">UPI ID <b data-testid={`upi-vpa-${inv.id}`}>{upi.vpa}</b> · {upi.payee_name}</p>
            <p className="text-xs text-slate-500">Note: {upi.note}</p>
            {upi.instructions && <p className="text-xs text-slate-500">{upi.instructions}</p>}
            <a href={upi.uri} className="sm:hidden inline-flex items-center gap-1.5 mt-1 rounded-full bg-emerald-600 text-white px-4 py-2 text-sm font-semibold" data-testid={`upi-open-app-${inv.id}`}><Smartphone size={14} /> Open UPI app</a>
          </div>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {inv.balance > 0 && !pending && <Button size="sm" onClick={() => setDlg("proof")} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid={`ive-paid-${inv.id}`}><Upload size={13} className="mr-1.5" /> I've paid</Button>}
        {canIssue && <Button size="sm" variant="outline" onClick={() => setDlg("issue")} data-testid={`raise-issue-${inv.id}`}><MessageSquareWarning size={13} className="mr-1.5" /> I have already paid</Button>}
        <Button size="sm" variant="ghost" onClick={() => printInvoiceById(inv.id)} data-testid={`print-invoice-${inv.id}`}><Printer size={13} className="mr-1.5" /> Invoice</Button>
      </div>
      {issues.map((i) => <IssueThread key={i.id} issue={i} replyUrl={`/parent/fees/issues/${i.id}/messages`} onChanged={onChanged} testid={`parent-issue-${i.id}`} />)}
      {dlg === "proof" && <ProofDialog inv={inv} open onClose={() => setDlg(null)} onDone={() => { setDlg(null); onChanged(); }} />}
      {dlg === "issue" && <IssueDialog inv={inv} open onClose={() => setDlg(null)} onDone={() => { setDlg(null); onChanged(); }} />}
    </div>
  );
}
