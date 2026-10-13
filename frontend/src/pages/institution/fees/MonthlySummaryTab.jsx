import { useCallback, useEffect, useState } from "react";
import { Printer, Banknote } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { inr } from "../../../lib/fees";
import { printMonthlySummary } from "../../../lib/printDoc";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";

const pct = (v) => (v === null || v === undefined ? "—" : `${v}%`);

const Row = ({ r, total }) => (
  <tr className={total ? "bg-slate-50 dark:bg-slate-800/50 font-semibold" : ""} data-testid={total ? "monthly-totals-row" : `monthly-row-${r.class_name}`}>
    <td className="px-4 py-2">{total ? "Grand total" : r.class_name}</td>
    <td className="text-right">{r.invoices}</td>
    <td className="text-right">{inr(r.gross)}</td>
    <td className="text-right text-violet-700">{r.concession ? `−${inr(r.concession)}` : "—"}</td>
    <td className="text-right">{inr(r.billed)}</td>
    <td className="text-right text-emerald-700" data-testid={total ? "monthly-total-collected" : undefined}>{inr(r.collected)}</td>
    <td className="text-right text-teal-700" data-testid={total ? "monthly-total-prev-dues" : `monthly-prev-dues-${r.class_name}`}>{inr(r.prev_dues_collected)}</td>
    <td className="text-right text-rose-700">{inr(r.outstanding)}</td>
    <td className="text-right pr-4">{pct(r.collection_pct)}</td>
  </tr>
);

export default function MonthlySummaryTab() {
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [d, setD] = useState(null);
  const load = useCallback(() => api.get("/fees/monthly-summary", { params: { month } }).then((r) => setD(r.data)).catch((e) => toast.error(errText(e))), [month]);
  useEffect(() => { if (/^\d{4}-\d{2}$/.test(month)) load(); }, [load, month]);
  return (
    <div className="space-y-4 pt-2" data-testid="fees-monthly-tab">
      <div className="flex flex-wrap items-center gap-3">
        <Input type="month" className="w-44" value={month} onChange={(e) => setMonth(e.target.value)} data-testid="monthly-month" />
        <Button variant="outline" disabled={!d} onClick={() => printMonthlySummary(d)} data-testid="monthly-print"><Printer size={14} className="mr-1.5" /> Print management report</Button>
        <p className="text-xs text-slate-400">Collected = receipts dated in the month (sum of daily Day Books, UTC).</p>
      </div>
      {d && (<>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="rounded-xl bg-emerald-600 text-white p-4"><p className="text-xs opacity-80">Collected</p><p className="text-2xl font-bold" data-testid="monthly-collected">{inr(d.totals.collected)}</p><p className="text-xs opacity-80">{d.totals.receipts} receipts</p></div>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4"><p className="text-xs text-slate-500">Billed (due this month, net)</p><p className="text-2xl font-bold" data-testid="monthly-billed">{inr(d.totals.billed)}</p></div>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4"><p className="text-xs text-slate-500">Outstanding of this month's billing</p><p className="text-2xl font-bold text-rose-700" data-testid="monthly-outstanding">{inr(d.totals.outstanding)}</p><p className="text-xs text-slate-500">Collection {pct(d.totals.collection_pct)}</p></div>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4"><p className="text-xs text-slate-500">Concessions / waivers</p><p className="text-2xl font-bold text-violet-700" data-testid="monthly-concession">{inr(d.totals.concession)}</p><p className="text-xs text-slate-500">excluded from dues</p></div>
        </div>
        <div className="grid md:grid-cols-4 gap-3">
          <div className="md:col-span-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-slate-500 text-left border-b border-slate-100 dark:border-slate-800"><tr>
                <th className="px-4 py-2">Class</th><th className="text-right">Invoices</th><th className="text-right">Gross</th><th className="text-right">Concession</th><th className="text-right">Billed</th><th className="text-right">Collected</th><th className="text-right" title="Part of Collected received against invoices due before this month (incl. carried-forward Previous dues)">of which previous dues</th><th className="text-right">Outstanding</th><th className="text-right pr-4">Collection %</th></tr></thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {d.rows.length === 0 && <tr><td colSpan={9} className="text-center text-slate-400 py-8" data-testid="monthly-empty">No billing or collections in this month.</td></tr>}
                {d.rows.map((r) => <Row key={r.class_name} r={r} />)}
                {d.rows.length > 0 && <Row r={d.totals} total />}
              </tbody>
            </table>
          </div>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4" data-testid="monthly-methods">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5 mb-2"><Banknote size={13} /> By method</p>
            {d.by_method.length === 0 && <p className="text-sm text-slate-400">—</p>}
            <ul className="space-y-1.5">{d.by_method.map((m) => (
              <li key={m.key} className="flex justify-between text-sm" data-testid={`monthly-method-${m.key}`}><span>{m.key.toUpperCase()} <span className="text-xs text-slate-400">× {m.count}</span></span><b>{inr(m.total)}</b></li>
            ))}</ul>
            {d.reversed.count > 0 && <p className="text-xs text-amber-700 mt-3">Reversed (excluded): {d.reversed.count} · {inr(d.reversed.amount)}</p>}
            {d.totals.carried_forward > 0 && <p className="text-xs text-violet-700 mt-2">Carried forward to next year: {inr(d.totals.carried_forward)}</p>}
          </div>
        </div>
        <p className="text-xs text-slate-500" data-testid="monthly-footnote">Billed = invoices due this month, net of concessions. Collected = all payments received this month; "of which previous dues" = the part paid against invoices due before this month (incl. carried-forward Previous dues). Outstanding and Collection % refer to this month's billing only.</p>
      </>)}
    </div>
  );
}
