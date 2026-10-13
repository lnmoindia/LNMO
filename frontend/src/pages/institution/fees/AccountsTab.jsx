import { useCallback, useEffect, useState } from "react";
import { Search, Wallet, Printer, Undo2, BookOpenCheck, BellRing, FileDown, FileText } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { inr, StatusChip, printReceiptById, downloadReceiptPdf, downloadBlob, printInvoiceById, localToday } from "../../../lib/fees";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Switch } from "../../../components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../../../components/ui/dialog";

const sel = "h-9 rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-2 text-sm";

const REMIND_MSG = { sent: "Reminder sent (WhatsApp + bell)", deduped: "Already reminded today — skipped", bell_only_no_phone: "No phone on file — bell notification only", bell_only_failed: "Message failed — bell notification only" };

export const remindInvoice = async (invId) => {
  try { const { data } = await api.post(`/fees/invoices/${invId}/remind`); (data.status === "sent" ? toast.success : toast.info)(REMIND_MSG[data.status] || data.status); }
  catch (e) { toast.error(errText(e)); }
};

export function CollectDialog({ inv, onClose, onDone }) {
  const [f, setF] = useState({ amount: "", method: "cash", reference: "", note: "", paid_on: localToday() });
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (inv) setF({ amount: String(inv.balance), method: "cash", reference: "", note: "", paid_on: localToday() }); }, [inv]);
  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/fees/payments", { invoice_id: inv.id, amount: Number(f.amount), method: f.method, reference: f.reference || null, note: f.note || null, paid_on: f.paid_on });
      toast.success(`Receipt ${data.payment.receipt_no} · ${inr(data.payment.amount)}`, { action: { label: "Print", onClick: () => printReceiptById(data.payment.id) } });
      onDone(data);
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={Boolean(inv)} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="fee-collect-dialog">
        <DialogHeader><DialogTitle>Collect payment</DialogTitle>
          <DialogDescription>{inv?.student_name} · {inv?.period_label} · balance <b data-testid="fee-collect-balance">{inr(inv?.balance)}</b>
            {inv?.fine_projected ? ` (includes late fee ${inr(inv.fine_projected)})` : ""}</DialogDescription></DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5"><Label>Amount (₹)</Label><Input type="number" min="1" max={inv?.balance} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} data-testid="fee-collect-amount" /></div>
          <div className="space-y-1.5"><Label>Method</Label>
            <select className={`${sel} w-full`} value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })} data-testid="fee-collect-method">
              {["cash", "upi", "cheque", "bank", "other"].map((m) => <option key={m} value={m}>{m.toUpperCase()}</option>)}</select></div>
          <div className="space-y-1.5"><Label>Payment date</Label><Input type="date" max={localToday()} value={f.paid_on} onChange={(e) => setF({ ...f, paid_on: e.target.value })} data-testid="fee-collect-date" /></div>
          <div className="space-y-1.5"><Label>Reference (UPI txn / cheque no.)</Label><Input value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} data-testid="fee-collect-reference" /></div>
          <div className="space-y-1.5 col-span-2"><Label>Note</Label><Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} data-testid="fee-collect-note" /></div>
        </div>
        {f.paid_on && f.paid_on < localToday() && <p className="text-xs text-amber-700" data-testid="fee-collect-backdated">Backdated entry — it will appear in the Day Book on {f.paid_on} and is audit-logged.</p>}
        {Number(f.amount) > Number(inv?.balance) && <p className="text-xs text-rose-600" data-testid="fee-collect-over">Amount is more than the balance due.</p>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !(Number(f.amount) > 0) || Number(f.amount) > Number(inv?.balance)} onClick={save} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="fee-collect-save">{busy ? "Recording…" : "Record payment"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function ReverseDialog({ pay, onClose, onDone }) {
  const [reason, setReason] = useState("");
  useEffect(() => setReason(""), [pay]);
  const go = async () => {
    try { await api.post(`/fees/payments/${pay.id}/reverse`, { reason }); toast.success("Payment reversed — credit note recorded"); onDone(); }
    catch (e) { toast.error(errText(e)); }
  };
  return (
    <Dialog open={Boolean(pay)} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="fee-reverse-dialog">
        <DialogHeader><DialogTitle>Reverse {pay?.receipt_no}?</DialogTitle>
          <DialogDescription>The receipt stays on record, marked reversed with a credit note. The amount returns to the invoice balance.</DialogDescription></DialogHeader>
        <Input placeholder="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="fee-reverse-reason" />
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={reason.trim().length < 3} onClick={go} className="bg-rose-600 hover:bg-rose-700 text-white" data-testid="fee-reverse-confirm">Reverse payment</Button></div>
      </DialogContent>
    </Dialog>
  );
}

function AccountSettings({ led, onSaved }) {
  const optional = led.structure.heads.filter((h) => h.optional);
  const [inc, setInc] = useState(led.account.included_head_ids || []);
  const [disc, setDisc] = useState({ type: led.account.discount?.type || "flat", value: led.account.discount?.value || "", reason: led.account.discount?.reason || "" });
  const save = async (body) => { try { await api.put(`/fees/accounts/${led.account.id}`, body); toast.success("Saved — applies to invoices generated from now on"); onSaved(); } catch (e) { toast.error(errText(e)); } };
  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-3 text-sm" data-testid="fee-account-settings">
      {optional.length > 0 && (
        <div className="flex flex-wrap gap-4 items-center">
          {optional.map((h) => (
            <label key={h.id} className="flex items-center gap-2"><Switch checked={inc.includes(h.id)} onCheckedChange={(v) => setInc(v ? [...inc, h.id] : inc.filter((x) => x !== h.id))} data-testid={`fee-optional-${h.title}`} /> {h.title} ({inr(h.amount)})</label>
          ))}
          <Button size="sm" variant="outline" onClick={() => save({ included_head_ids: inc })} data-testid="fee-optional-save">Save heads</Button>
        </div>
      )}
      <div className="grid grid-cols-[110px_110px_1fr_auto_auto] gap-2 items-center">
        <select className={sel} value={disc.type} onChange={(e) => setDisc({ ...disc, type: e.target.value })} data-testid="fee-discount-type"><option value="flat">Flat ₹</option><option value="percent">Percent</option></select>
        <Input type="number" min="0" placeholder="Value" value={disc.value} onChange={(e) => setDisc({ ...disc, value: e.target.value })} data-testid="fee-discount-value" />
        <Input placeholder="Reason (e.g. sibling, staff ward)" value={disc.reason} onChange={(e) => setDisc({ ...disc, reason: e.target.value })} data-testid="fee-discount-reason" />
        <Button size="sm" variant="outline" disabled={!(Number(disc.value) > 0)} onClick={() => save({ discount: { ...disc, value: Number(disc.value) } })} data-testid="fee-discount-save">Set discount</Button>
        {led.account.discount && <Button size="sm" variant="ghost" onClick={() => save({ clear_discount: true })} data-testid="fee-discount-clear">Clear</Button>}
      </div>
    </div>
  );
}

function Ledger({ aid, readOnly, canCollect, onClose }) {
  const [led, setLed] = useState(null);
  const [collect, setCollect] = useState(null);
  const [rev, setRev] = useState(null);
  const load = useCallback(() => api.get(`/fees/accounts/${aid}`).then((r) => setLed(r.data)).catch((e) => toast.error(errText(e))), [aid]);
  useEffect(() => { setLed(null); if (aid) load(); }, [aid, load]);
  const s = led?.summary;
  return (
    <Dialog open={Boolean(aid)} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="fee-ledger-dialog">
        <DialogHeader><DialogTitle>{led?.account.student_name || "Ledger"}</DialogTitle>
          <DialogDescription>{led ? `${led.account.class_name} ${led.account.section || ""} · ${led.structure.name}${led.account.discount ? ` · discount ${led.account.discount.type === "flat" ? inr(led.account.discount.value) : `${led.account.discount.value}%`}` : ""}` : "Loading…"}</DialogDescription></DialogHeader>
        {led && (<>
          <div className="grid grid-cols-4 gap-3 text-sm">
            {[["Billed", s.total, ""], ["Paid", s.paid, "text-emerald-600"], ["Balance", s.balance, "text-rose-600"], ["Next due", s.next_due || "—", ""]].map(([l, v, t]) => (
              <div key={l} className="rounded-lg bg-slate-50 dark:bg-slate-800/60 p-3"><p className="text-xs text-slate-500">{l}</p><p className={`font-bold ${t}`} data-testid={`fee-ledger-${l.toLowerCase().replace(" ", "-")}`}>{typeof v === "number" ? inr(v) : v}</p></div>
            ))}
          </div>
          <div className="flex justify-end"><Button size="sm" variant="outline" onClick={() => downloadBlob(`/fees/students/${led.account.student_id}/statement.pdf?academic_year=${encodeURIComponent(led.account.academic_year || "")}`, `fee-statement-${led.account.student_name}.pdf`)} data-testid="fee-ledger-statement"><FileText size={13} className="mr-1.5" /> Download statement</Button></div>
          {!readOnly && <AccountSettings key={led.account.id + JSON.stringify(led.account.discount)} led={led} onSaved={load} />}
          <table className="w-full text-sm">
            <thead className="text-xs text-slate-500 text-left"><tr><th className="py-1">Period</th><th>Due</th><th className="text-right">Amount</th><th className="text-right">Paid</th><th className="text-right">Balance</th><th>Status</th><th /></tr></thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {led.invoices.map((i) => (
                <tr key={i.id} data-testid={`fee-invoice-${i.period_label}`}>
                  <td className="py-2"><p className="font-medium">{i.period_label}</p><p className="text-xs text-slate-500">{i.items.map((x) => `${x.title} ${inr(x.amount)}`).join(" · ")}{i.discount_amount ? ` · −${inr(i.discount_amount)}` : ""}{i.fine_amount ? ` · late +${inr(i.fine_amount)}` : ""}</p></td>
                  <td>{i.due_date}</td><td className="text-right">{inr(i.amount_due)}</td><td className="text-right">{inr(i.paid_amount)}</td><td className="text-right font-semibold">{inr(i.balance)}</td>
                  <td><StatusChip status={i.status} testid={`fee-invoice-status-${i.period_label}`} /></td>
                  <td className="text-right whitespace-nowrap">
                    <Button size="sm" variant="ghost" title="Print invoice (with UPI QR)" onClick={() => printInvoiceById(i.id)} data-testid={`fee-print-invoice-${i.period_label}`}><Printer size={13} /></Button>
                    {!readOnly && i.balance > 0 && <Button size="sm" variant="ghost" title="Send reminder" onClick={() => remindInvoice(i.id)} data-testid={`fee-remind-${i.period_label}`}><BellRing size={13} /></Button>}
                    {canCollect && i.balance > 0 && <Button size="sm" variant="outline" onClick={() => setCollect(i)} data-testid={`fee-collect-${i.period_label}`}><Wallet size={13} className="mr-1" /> Collect</Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Payments</p>
            {led.payments.length === 0 && <p className="text-sm text-slate-400">No payments yet.</p>}
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {led.payments.map((p) => (
                <li key={p.id} className="py-2 flex items-center justify-between gap-3 text-sm" data-testid={`fee-payment-${p.receipt_no}`}>
                  <span><b>{p.receipt_no}</b> <span className="text-xs text-slate-500">· {p.period_label} · {p.method.toUpperCase()}{p.reference ? ` ${p.reference}` : ""} · {p.paid_on || (p.collected_at || "").slice(0, 10)}{p.backdated ? " (backdated)" : ""} · {p.collected_by}</span>
                    {p.reversed && <> <StatusChip status="reversed" /> <span className="text-xs text-amber-700">{p.credit_note_no} · {p.reverse_reason}</span></>}</span>
                  <span className="flex items-center gap-2"><b className={p.reversed ? "line-through text-slate-400" : ""}>{inr(p.amount)}</b>
                    <Button size="sm" variant="ghost" onClick={() => printReceiptById(p.id)} data-testid={`fee-print-${p.receipt_no}`}><Printer size={14} /></Button>
                    <Button size="sm" variant="ghost" title="Download PDF" onClick={() => downloadReceiptPdf(p.id, p.receipt_no)} data-testid={`fee-pdf-${p.receipt_no}`}><FileDown size={14} /></Button>
                    {canCollect && !p.reversed && <Button size="sm" variant="ghost" onClick={() => setRev(p)} data-testid={`fee-reverse-${p.receipt_no}`}><Undo2 size={14} /></Button>}</span>
                </li>
              ))}
            </ul>
          </div>
        </>)}
        <CollectDialog inv={collect} onClose={() => setCollect(null)} onDone={() => { setCollect(null); load(); }} />
        <ReverseDialog pay={rev} onClose={() => setRev(null)} onDone={() => { setRev(null); load(); }} />
      </DialogContent>
    </Dialog>
  );
}

export default function AccountsTab({ readOnly, canCollect }) {
  const [structures, setStructures] = useState([]);
  const [sid, setSid] = useState("");
  const [cls, setCls] = useState("");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(null);
  const load = useCallback(() => api.get("/fees/accounts", { params: { structure_id: sid, class_name: cls, q } }).then((r) => setRows(r.data.accounts)).catch(() => setRows([])), [sid, cls, q]);
  const [classes, setClasses] = useState([]);
  useEffect(() => { api.get("/res/classes", { params: { limit: 500 } }).then((r) => setClasses(r.data.items || [])).catch(() => {}); }, []);
  const remindClass = async () => {
    if (!window.confirm(`Send a fee reminder to every parent in ${cls} with an unpaid balance? Each student gets at most one reminder per day.`)) return;
    try {
      const { data } = await api.post("/fees/reminders/class", { class_name: cls });
      toast.success(`${cls}: ${data.sent} sent · ${data.deduped} already reminded today · ${data.bell_only_no_phone} bell-only (no phone)`);
    } catch (e) { toast.error(errText(e)); }
  };
  useEffect(() => { api.get("/fees/structures").then((r) => setStructures(r.data.structures)).catch(() => {}); }, []);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);
  return (
    <div className="space-y-3 pt-2" data-testid="fees-accounts-tab">
      <div className="flex flex-wrap gap-2">
        <select className={sel} value={sid} onChange={(e) => setSid(e.target.value)} data-testid="fee-accounts-structure">
          <option value="">All structures</option>{structures.map((s) => <option key={s.id} value={s.id}>{s.name}{s.archived ? " (archived)" : ""}</option>)}</select>
        <select className={sel} value={cls} onChange={(e) => setCls(e.target.value)} data-testid="fee-accounts-class">
          <option value="">All classes</option>{classes.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}</select>
        {!readOnly && cls && <Button variant="outline" onClick={remindClass} data-testid="fee-remind-class-btn"><BellRing size={14} className="mr-1.5" /> Remind {cls}</Button>}
        <div className="relative"><Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
          <Input className="pl-8 w-64" placeholder="Student or admission no." value={q} onChange={(e) => setQ(e.target.value)} data-testid="fee-accounts-search" /></div>
      </div>
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-500 text-left border-b border-slate-100 dark:border-slate-800"><tr>
            <th className="px-4 py-2">Student</th><th>Class</th><th className="text-right">Billed</th><th className="text-right">Paid</th><th className="text-right">Balance</th><th className="px-3">Next due</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows?.length === 0 && <tr><td colSpan={7} className="text-center text-slate-400 py-8">No fee accounts.</td></tr>}
            {rows?.map((a) => (
              <tr key={a.id} data-testid={`fee-account-row-${a.id}`}>
                <td className="px-4 py-2"><p className="font-medium text-slate-800 dark:text-slate-100">{a.student_name}</p><p className="text-xs text-slate-400">{a.admission_no}{a.discount ? " · discount" : ""}</p></td>
                <td>{a.class_name} {a.section}</td><td className="text-right">{inr(a.summary.total)}</td><td className="text-right text-emerald-600">{inr(a.summary.paid)}</td>
                <td className="text-right font-semibold">{inr(a.summary.balance)} {a.summary.overdue > 0 && <StatusChip status="overdue" />}</td>
                <td className="px-3">{a.summary.next_due || "—"}</td>
                <td className="pr-3 text-right"><Button size="sm" variant="outline" onClick={() => setOpen(a.id)} data-testid={`fee-account-open-${a.id}`}><BookOpenCheck size={13} className="mr-1" /> Ledger</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Ledger aid={open} readOnly={readOnly} canCollect={canCollect} onClose={() => { setOpen(null); load(); }} />
    </div>
  );
}
