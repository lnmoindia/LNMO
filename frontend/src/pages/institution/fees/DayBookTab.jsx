import { useCallback, useEffect, useState } from "react";
import { Printer, Banknote, UserRound, School } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { inr } from "../../../lib/fees";
import { printDayBook } from "../../../lib/printDoc";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";

const Group = ({ title, icon: Icon, rows, testid, upper }) => (
  <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4" data-testid={testid}>
    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5 mb-2"><Icon size={13} /> {title}</p>
    {rows.length === 0 && <p className="text-sm text-slate-400">—</p>}
    <ul className="space-y-1.5">
      {rows.map((r) => (
        <li key={r.key} className="flex justify-between text-sm" data-testid={`${testid}-${r.key}`}>
          <span className="text-slate-700 dark:text-slate-200">{upper ? r.key.toUpperCase() : r.key} <span className="text-xs text-slate-400">× {r.count}</span></span>
          <b>{inr(r.total)}</b>
        </li>
      ))}
    </ul>
  </div>
);

export default function DayBookTab() {
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10));
  const [d, setD] = useState(null);
  const load = useCallback(() => api.get("/fees/day-book", { params: { date: day } }).then((r) => setD(r.data)).catch((e) => toast.error(errText(e))), [day]);
  useEffect(() => { load(); }, [load]);
  return (
    <div className="space-y-4 pt-2" data-testid="fees-daybook-tab">
      <div className="flex flex-wrap items-center gap-3">
        <Input type="date" className="w-44" value={day} onChange={(e) => setDay(e.target.value)} data-testid="daybook-date" />
        <Button variant="outline" disabled={!d} onClick={() => printDayBook(d)} data-testid="daybook-print"><Printer size={14} className="mr-1.5" /> Print / PDF</Button>
        <p className="text-xs text-slate-400">Dates are UTC, matching receipt dates.</p>
      </div>
      {d && (<>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="rounded-xl bg-emerald-600 text-white p-4"><p className="text-xs opacity-80">Total collected</p><p className="text-2xl font-bold" data-testid="daybook-total">{inr(d.summary.total)}</p></div>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4"><p className="text-xs text-slate-500">Receipts</p><p className="text-2xl font-bold" data-testid="daybook-count">{d.summary.count}</p></div>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 md:col-span-2"><p className="text-xs text-slate-500">Reversed (excluded)</p>
            <p className="text-sm mt-1" data-testid="daybook-reversed">{d.summary.reversed_count ? `${d.summary.reversed_count} · ${inr(d.summary.reversed_amount)} — ${d.reversed.map((p) => p.receipt_no).join(", ")}` : "None"}</p></div>
        </div>
        <div className="grid md:grid-cols-3 gap-3">
          <Group title="By method" icon={Banknote} rows={d.by_method} testid="daybook-method" upper />
          <Group title="By collector" icon={UserRound} rows={d.by_collector} testid="daybook-collector" />
          <Group title="By class" icon={School} rows={d.by_class} testid="daybook-class" />
        </div>
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-slate-500 text-left border-b border-slate-100 dark:border-slate-800"><tr>
              <th className="px-4 py-2">Receipt</th><th>Student</th><th>Class</th><th>Period</th><th>Method</th><th>Collector</th><th className="text-right pr-4">Amount</th></tr></thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {d.payments.length === 0 && <tr><td colSpan={7} className="text-center text-slate-400 py-8">No collections on this date.</td></tr>}
              {d.payments.map((p) => (
                <tr key={p.id} data-testid={`daybook-row-${p.receipt_no}`}>
                  <td className="px-4 py-2 font-medium">{p.receipt_no}</td><td>{p.student_name}</td><td>{p.class_name} {p.section}</td><td>{p.period_label}</td>
                  <td>{p.method.toUpperCase()}{p.reference ? <span className="text-xs text-slate-400"> {p.reference}</span> : null}</td><td>{p.collected_by}</td>
                  <td className="text-right pr-4 font-semibold">{inr(p.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>)}
    </div>
  );
}
