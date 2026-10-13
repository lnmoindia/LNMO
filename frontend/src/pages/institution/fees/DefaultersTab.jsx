import { useCallback, useEffect, useState } from "react";
import { BellRing, Download, Printer, AlertTriangle, Loader2, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { inr } from "../../../lib/fees";
import { printDefaulters } from "../../../lib/printDoc";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Checkbox } from "../../../components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../components/ui/select";

const ALL = "__all";
const PAGE = 50;
const BUCKET_TONE = { "1-30": "bg-amber-50 text-amber-700", "31-60": "bg-orange-50 text-orange-700", "60+": "bg-rose-50 text-rose-700" };

const Pick = ({ value, onChange, options, placeholder, testid, width = "w-36" }) => (
  <Select value={value || ALL} onValueChange={(v) => onChange(v === ALL ? "" : v)}>
    <SelectTrigger className={`${width} h-9`} data-testid={testid}><SelectValue placeholder={placeholder} /></SelectTrigger>
    <SelectContent>
      <SelectItem value={ALL}>{placeholder}</SelectItem>
      {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
    </SelectContent>
  </Select>
);

const RESULT_LABEL = { sent: "sent", skipped_throttled: "already reminded today", no_contact: "no phone on file", failed: "failed", no_dues: "no dues", out_of_scope: "out of scope", not_found: "not found" };

const fmtAt = (s) => (s ? s.slice(0, 16).replace("T", " ") : "—");

export default function DefaultersTab() {
  const [f, setF] = useState({ academic_unit_id: "", class_name: "", section: "", bucket: "", min_amount: "", sort: "amount" });
  const [page, setPage] = useState(1);
  const [d, setD] = useState(null);
  const [sel, setSel] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [denied, setDenied] = useState(null);
  const params = useCallback((extra = {}) => Object.fromEntries(Object.entries({ ...f, ...extra }).filter(([, v]) => v !== "" && v !== null)), [f]);
  const load = useCallback(() => api.get("/fees/defaulters", { params: params({ page, page_size: PAGE }) })
    .then((r) => { setD(r.data); setDenied(null); })
    .catch((e) => { if (e?.response?.status === 403) setDenied(errText(e)); else toast.error(errText(e)); }), [params, page]);
  useEffect(() => { load(); }, [load]);
  const set = (k) => (v) => { setF((x) => ({ ...x, [k]: v })); setPage(1); setSel(new Set()); };

  const remind = async (ids) => {
    setBusy(true);
    try {
      const { data } = await api.post("/fees/defaulters/remind", { student_ids: ids });
      if (ids.length === 1) {
        const r = data.results[0];
        (r.status === "sent" ? toast.success : toast.message)(`${r.student_name || "Student"}: ${RESULT_LABEL[r.status] || r.status}`);
      } else {
        toast.success(`Sent ${data.sent} · already reminded today ${data.skipped_throttled} · no contact ${data.no_contact}${data.failed ? ` · failed ${data.failed}` : ""}`);
      }
      setSel(new Set()); load();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const exportCsv = async () => {
    try {
      const { data } = await api.get("/fees/defaulters/export.csv", { params: params(), responseType: "blob" });
      const url = URL.createObjectURL(new Blob([data], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url; a.download = `fee-defaulters-${d?.as_of || "list"}.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (e) { toast.error(errText(e)); }
  };

  const print = async () => {
    try {
      const { data } = await api.get("/fees/defaulters", { params: params({ page: 1, page_size: 1000 }) });
      const unit = data.filters.units.find((u) => u.id === f.academic_unit_id)?.name;
      const label = [unit, f.class_name, f.section && `Section ${f.section}`, f.bucket && `${f.bucket} days`, f.min_amount && `≥ ${inr(f.min_amount)}`].filter(Boolean).join(" · ");
      printDefaulters(data, label);
    } catch (e) { toast.error(errText(e)); }
  };

  const canRemind = d?.can_remind;
  const rows = d?.rows || [];
  const allSel = rows.length > 0 && rows.every((r) => sel.has(r.student_id));
  const toggleAll = () => setSel(allSel ? new Set() : new Set(rows.map((r) => r.student_id)));
  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const pages = d ? Math.max(1, Math.ceil(d.total / PAGE)) : 1;
  const filtered = Object.entries(f).some(([k, v]) => k !== "sort" && v !== "");
  const up = d?.upcoming;

  if (denied) return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 text-center" data-testid="defaulters-denied">
      <AlertTriangle className="mx-auto text-amber-500 mb-2" size={22} />
      <p className="font-medium text-slate-800 dark:text-slate-100">The fee defaulter list is only available to class teachers, principals and the school office.</p>
      <p className="text-sm text-slate-500 mt-1">You are not assigned as the class teacher of any section. Ask your administrator if this is wrong.</p>
    </div>
  );

  return (
    <div className="space-y-4 pt-2" data-testid="fees-defaulters-tab">
      <div className="flex flex-wrap items-center gap-2">
        {d?.filters.units.length > 0 && <Pick value={f.academic_unit_id} onChange={set("academic_unit_id")} placeholder="All divisions" testid="defaulters-filter-unit" options={d.filters.units.map((u) => ({ value: u.id, label: u.name }))} />}
        <Pick value={f.class_name} onChange={set("class_name")} placeholder="All classes" testid="defaulters-filter-class" options={(d?.filters.classes || []).map((c) => ({ value: c, label: c }))} />
        <Pick value={f.section} onChange={set("section")} placeholder="All sections" testid="defaulters-filter-section" width="w-32" options={(d?.filters.sections || []).map((s) => ({ value: s, label: `Section ${s}` }))} />
        <Pick value={f.bucket} onChange={set("bucket")} placeholder="Any ageing" testid="defaulters-filter-bucket" options={["1-30", "31-60", "60+"].map((b) => ({ value: b, label: `${b} days late` }))} />
        <Input type="number" min="0" className="w-32 h-9" placeholder="Min ₹ overdue" value={f.min_amount} onChange={(e) => set("min_amount")(e.target.value)} data-testid="defaulters-filter-min" />
        <Select value={f.sort} onValueChange={set("sort")}>
          <SelectTrigger className="w-44 h-9" data-testid="defaulters-sort"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="amount">Highest amount first</SelectItem><SelectItem value="days_late">Most days late first</SelectItem></SelectContent>
        </Select>
        <div className="ml-auto flex gap-2">
          <Button variant="outline" size="sm" onClick={exportCsv} disabled={!d} data-testid="defaulters-export-csv"><Download size={14} className="mr-1.5" /> CSV</Button>
          <Button variant="outline" size="sm" onClick={print} disabled={!d} data-testid="defaulters-print"><Printer size={14} className="mr-1.5" /> Print / PDF</Button>
        </div>
      </div>

      {d && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <div className="rounded-xl bg-rose-600 text-white p-4 md:col-span-2"><p className="text-xs opacity-80">Overdue (as of {d.as_of})</p><p className="text-2xl font-bold" data-testid="defaulters-total-overdue">{inr(d.totals.overdue)}</p><p className="text-xs opacity-80 mt-0.5">Total outstanding {inr(d.totals.outstanding)}</p></div>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4"><p className="text-xs text-slate-500">Students</p><p className="text-2xl font-bold" data-testid="defaulters-count">{d.totals.students}</p></div>
          {["1-30", "31-60", "60+"].map((b) => (
            <button key={b} type="button" onClick={() => set("bucket")(f.bucket === b ? "" : b)} className={`rounded-xl border p-4 text-left transition-colors ${f.bucket === b ? "border-rose-400 bg-rose-50/60 dark:bg-rose-500/10" : "border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40"}`} data-testid={`defaulters-bucket-${b}`}>
              <p className="text-xs text-slate-500">{b} days late</p><p className="text-xl font-bold" data-testid={`defaulters-bucket-count-${b}`}>{d.buckets[b]}</p>
            </button>
          ))}
        </div>
      )}
      {d && <p className="text-xs text-slate-500 -mt-2" data-testid="defaulters-note">Partly paid invoices count only the remaining balance; concessions/waivers are excluded.{!canRemind ? " View only — reminders are sent by the office / principal." : ""}</p>}

      {canRemind && sel.size > 0 && (
        <div className="flex items-center gap-3 rounded-xl border border-indigo-200 bg-indigo-50/60 dark:bg-indigo-500/10 dark:border-indigo-500/30 px-4 py-2" data-testid="defaulters-bulk-bar">
          <span className="text-sm font-medium">{sel.size} selected</span>
          <Button size="sm" disabled={busy} onClick={() => remind([...sel])} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="defaulters-remind-selected">
            {busy ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <BellRing size={14} className="mr-1.5" />} Remind selected
          </Button>
          <span className="text-xs text-slate-500">Max one fee reminder per student per day (shared with automatic reminders).</span>
        </div>
      )}

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-500 text-left border-b border-slate-100 dark:border-slate-800"><tr>
            {canRemind && <th className="pl-4 py-2 w-8"><Checkbox checked={allSel} onCheckedChange={toggleAll} data-testid="defaulters-select-all" /></th>}
            <th className="px-4 py-2">Student</th><th>Class</th><th>Parent</th><th className="text-right">Overdue</th><th className="text-right">Outstanding</th><th className="pl-4">Oldest due</th><th className="text-right">Days late</th><th className="pl-4">Last reminder</th>{canRemind && <th />}</tr></thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {!d && <tr><td colSpan={10} className="text-center text-slate-400 py-8"><Loader2 className="inline animate-spin" size={16} /></td></tr>}
            {d && rows.length === 0 && <tr><td colSpan={10} className="text-center py-10" data-testid="defaulters-empty">
              <p className="font-medium text-slate-700 dark:text-slate-200"><CheckCircle2 size={16} className="inline mr-1.5 text-emerald-500" />No overdue fees{filtered ? " for these filters" : ""} as of {d.as_of}.</p>
              <p className="text-sm text-slate-500 mt-1" data-testid="defaulters-empty-detail">{up?.next_due_date
                ? `${up.not_yet_due_invoices} open invoice${up.not_yet_due_invoices === 1 ? "" : "s"} (${inr(up.not_yet_due_amount)}) not yet due — earliest due date is ${new Date(up.next_due_date + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}. Students appear here the day after a due date passes with a balance.`
                : "There are no unpaid invoices in your scope."}</p>
            </td></tr>}
            {rows.map((r) => (
              <tr key={r.student_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40" data-testid={`defaulter-row-${r.student_id}`}>
                {canRemind && <td className="pl-4"><Checkbox checked={sel.has(r.student_id)} onCheckedChange={() => toggle(r.student_id)} data-testid={`defaulter-select-${r.student_id}`} /></td>}
                <td className="px-4 py-2"><p className="font-medium text-slate-800 dark:text-slate-100">{r.student_name}</p><p className="text-xs text-slate-400">{r.admission_no}</p></td>
                <td>{r.class_name} · {r.section}</td>
                <td><p>{r.parent_name || "—"}</p><p className="text-xs text-slate-400">{r.parent_phone || "no phone"}</p></td>
                <td className="text-right font-semibold text-rose-700" data-testid={`defaulter-overdue-${r.student_id}`}>{inr(r.overdue_amount)}</td>
                <td className="text-right" data-testid={`defaulter-outstanding-${r.student_id}`}>{inr(r.total_outstanding)}</td>
                <td className="pl-4">{r.oldest_due_date}</td>
                <td className="text-right"><span className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-semibold ${BUCKET_TONE[r.bucket]}`} data-testid={`defaulter-days-${r.student_id}`}>{r.days_late}d</span></td>
                <td className="pl-4 text-xs text-slate-500" data-testid={`defaulter-last-reminder-${r.student_id}`}>{fmtAt(r.last_reminder_at)}</td>
                {canRemind && <td className="pr-3 text-right"><Button size="sm" variant="ghost" disabled={busy} onClick={() => remind([r.student_id])} data-testid={`defaulter-remind-${r.student_id}`}><BellRing size={13} className="mr-1" /> Remind</Button></td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {d && pages > 1 && (
        <div className="flex items-center justify-end gap-2 text-sm" data-testid="defaulters-pagination">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)} data-testid="defaulters-prev">Prev</Button>
          <span className="text-slate-500">Page {page} / {pages}</span>
          <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)} data-testid="defaulters-next">Next</Button>
        </div>
      )}
    </div>
  );
}
