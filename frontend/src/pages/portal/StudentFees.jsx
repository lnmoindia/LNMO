import { useEffect, useState } from "react";
import { Wallet, Printer, ChevronDown, FileDown } from "lucide-react";
import api from "../../lib/api";
import { inr, StatusChip, printReceiptById, downloadReceiptPdf } from "../../lib/fees";

const Tile = ({ label, value, tone, testid }) => (
  <div className="rounded-2xl bg-slate-50 dark:bg-slate-800/60 p-3">
    <p className="text-[11px] uppercase tracking-wider text-slate-500">{label}</p>
    <p className={`text-lg font-bold mt-0.5 ${tone}`} data-testid={testid}>{value}</p>
  </div>
);

export default function StudentFees({ endpoint, testid = "fees-card", defaultOpen = false }) {
  const [d, setD] = useState(null);
  const [open, setOpen] = useState(defaultOpen);
  useEffect(() => {
    setD(null);
    api.get(endpoint).then((r) => setD(r.data)).catch(() => setD({ invoices: [], payments: [] }));
  }, [endpoint]);
  const s = d?.summary;
  return (
    <div className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm" data-testid={testid}>
      <div className="px-6 pt-5 pb-4 flex items-center justify-between gap-3">
        <h3 className="font-heading font-bold text-slate-900 dark:text-white flex items-center gap-2"><Wallet size={17} className="text-emerald-600" /> Fees</h3>
        {d?.invoices.length > 0 && (
          <button onClick={() => setOpen((o) => !o)} className="text-xs font-semibold text-indigo-600 flex items-center gap-1" data-testid={`${testid}-toggle`}>
            {open ? "Hide details" : "View details"} <ChevronDown size={13} className={open ? "rotate-180" : ""} />
          </button>
        )}
      </div>
      {!d && <div className="h-20 mx-6 mb-5 rounded-2xl bg-slate-100 dark:bg-slate-800 animate-pulse" />}
      {d && !d.invoices.length && <p className="px-6 pb-5 text-sm text-slate-400">No fee invoices yet.</p>}
      {s && d.invoices.length > 0 && (
        <div className="px-6 pb-5 grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Tile label="Total payable" value={inr(s.total)} tone="text-slate-800 dark:text-slate-100" testid={`${testid}-total`} />
          <Tile label="Paid" value={inr(s.paid)} tone="text-emerald-600" testid={`${testid}-paid`} />
          <Tile label="Balance due" value={inr(s.balance)} tone={s.overdue ? "text-rose-600" : "text-amber-600"} testid={`${testid}-balance`} />
          <Tile label="Next due" value={s.next_due || "—"} tone="text-slate-800 dark:text-slate-100" testid={`${testid}-next-due`} />
        </div>
      )}
      {open && d && (
        <div className="border-t border-slate-100 dark:border-slate-800 px-6 py-4 space-y-4" data-testid={`${testid}-details`}>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {d.invoices.map((i) => (
              <li key={i.id} className="py-2.5 flex items-center justify-between gap-3 text-sm" data-testid={`${testid}-invoice-${i.id}`}>
                <div className="min-w-0">
                  <p className="font-medium text-slate-800 dark:text-slate-100">{i.period_label} <span className="text-xs text-slate-400">· due {i.due_date}</span></p>
                  <p className="text-xs text-slate-500 truncate">{i.items.map((x) => x.title).join(", ")}{i.discount_amount ? ` · discount ${inr(i.discount_amount)}` : ""}{i.fine_amount ? ` · late fee ${inr(i.fine_amount)}` : ""}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className="font-semibold text-slate-800 dark:text-slate-100">{inr(i.amount_due)}</p>
                  <StatusChip status={i.status} />
                </div>
              </li>
            ))}
          </ul>
          {d.payments.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Receipts</p>
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {d.payments.map((p) => (
                  <li key={p.id} className="py-2 flex items-center justify-between text-sm">
                    <span className="text-slate-700 dark:text-slate-200">{p.receipt_no} <span className="text-xs text-slate-400">· {p.period_label} · {(p.collected_at || "").slice(0, 10)} · {p.method.toUpperCase()}</span></span>
                    <span className="flex items-center gap-3"><b>{inr(p.amount)}</b>
                      <button onClick={() => printReceiptById(p.id)} className="text-indigo-600" title="Print receipt" data-testid={`${testid}-receipt-${p.id}`}><Printer size={15} /></button>
                      <button onClick={() => downloadReceiptPdf(p.id, p.receipt_no)} className="text-emerald-600" title="Download PDF" data-testid={`${testid}-receipt-pdf-${p.id}`}><FileDown size={15} /></button></span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
