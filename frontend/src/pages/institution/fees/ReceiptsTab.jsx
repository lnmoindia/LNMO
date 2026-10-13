import { useCallback, useEffect, useState } from "react";
import { Search, Printer, Undo2, FileDown } from "lucide-react";
import api from "../../../lib/api";
import { inr, StatusChip, printReceiptById, downloadReceiptPdf } from "../../../lib/fees";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { ReverseDialog } from "./AccountsTab";

export default function ReceiptsTab({ readOnly }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState(null);
  const [rev, setRev] = useState(null);
  const load = useCallback(() => api.get("/fees/payments", { params: { q } }).then((r) => setRows(r.data.payments)).catch(() => setRows([])), [q]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);
  const total = (rows || []).filter((p) => !p.reversed).reduce((s, p) => s + p.amount, 0);
  return (
    <div className="space-y-3 pt-2" data-testid="fees-receipts-tab">
      <div className="flex items-center justify-between gap-3">
        <div className="relative"><Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
          <Input className="pl-8 w-72" placeholder="Receipt no., student or reference" value={q} onChange={(e) => setQ(e.target.value)} data-testid="fee-receipts-search" /></div>
        <p className="text-sm text-slate-500">Shown: <b className="text-slate-800 dark:text-slate-100" data-testid="fee-receipts-total">{inr(total)}</b> collected</p>
      </div>
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-500 text-left border-b border-slate-100 dark:border-slate-800"><tr>
            <th className="px-4 py-2">Receipt</th><th>Date</th><th>Student</th><th>Period</th><th>Method</th><th className="text-right">Amount</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows?.length === 0 && <tr><td colSpan={7} className="text-center text-slate-400 py-8">No receipts found.</td></tr>}
            {rows?.map((p) => (
              <tr key={p.id} data-testid={`fee-receipt-row-${p.receipt_no}`}>
                <td className="px-4 py-2 font-medium">{p.receipt_no} {p.reversed && <StatusChip status="reversed" />}</td>
                <td>{(p.collected_at || "").slice(0, 10)}</td><td>{p.student_name} <span className="text-xs text-slate-400">{p.class_name} {p.section}</span></td>
                <td>{p.period_label}</td><td>{p.method.toUpperCase()}{p.reference ? <span className="text-xs text-slate-400"> {p.reference}</span> : null}</td>
                <td className={`text-right font-semibold ${p.reversed ? "line-through text-slate-400" : ""}`}>{inr(p.amount)}</td>
                <td className="pr-3 text-right whitespace-nowrap">
                  <Button size="sm" variant="ghost" onClick={() => printReceiptById(p.id)} data-testid={`fee-receipt-print-${p.receipt_no}`}><Printer size={14} /></Button>
                  <Button size="sm" variant="ghost" title="Download PDF" onClick={() => downloadReceiptPdf(p.id, p.receipt_no)} data-testid={`fee-receipt-pdf-${p.receipt_no}`}><FileDown size={14} /></Button>
                  {!readOnly && !p.reversed && <Button size="sm" variant="ghost" onClick={() => setRev(p)} data-testid={`fee-receipt-reverse-${p.receipt_no}`}><Undo2 size={14} /></Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ReverseDialog pay={rev} onClose={() => setRev(null)} onDone={() => { setRev(null); load(); }} />
    </div>
  );
}
