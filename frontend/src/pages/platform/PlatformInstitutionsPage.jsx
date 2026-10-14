import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowDown, ArrowUp, Plus, Search } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Skeleton } from "../../components/ui/skeleton";
import { FormDialog } from "../../components/common/FormDialog";
import { institutionsConfig } from "./config";
import { Empty, PlanBadge, StatusPill, fmtDay } from "./inst/ui";

const API = process.env.REACT_APP_BACKEND_URL;
const COLS = [["name", "School"], ["plan_name", "Plan"], ["status", "Status"], ["students", "Students"], ["teachers", "Teachers"], ["created_at", "Created"]];

export default function PlatformInstitutionsPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [q, setQ] = useState("");
  const [plan, setPlan] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState(["name", 1]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.get("/platform/institutions-list").then((r) => setData(r.data)).catch((e) => toast.error(errText(e))), []);
  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => {
    if (!data) return [];
    const t = q.trim().toLowerCase();
    const list = data.items.filter((i) => (!t || [i.name, i.code, i.city, i.domain].some((v) => (v || "").toLowerCase().includes(t)))
      && (!plan || (plan === "none" ? !i.plan_id : i.plan_id === plan)) && (!status || i.status === status));
    const [k, dir] = sort;
    return [...list].sort((a, b) => {
      const x = a[k] ?? "", y = b[k] ?? "";
      return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))) * dir;
    });
  }, [data, q, plan, status, sort]);

  const create = async (values) => {
    setBusy(true); setErr("");
    try { const { data: d } = await api.post("/res/institutions", values); toast.success("Institution created"); setOpen(false); navigate(`/platform/institutions/${d.id}`); }
    catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  const sel = "h-9 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 text-sm";
  return (
    <div className="space-y-6" data-testid="institutions-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">Institutions</h1>
          <p className="text-sm text-slate-500 mt-1">Every school on LNMO. Click a row for analytics, plan, admins and settings.</p></div>
        <Button onClick={() => setOpen(true)} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="add-institution-btn"><Plus size={15} className="mr-1.5" /> New institution</Button>
      </div>
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[14rem] max-w-md"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, code, city or domain" className="pl-9" data-testid="inst-search" /></div>
        <select className={sel} value={plan} onChange={(e) => setPlan(e.target.value)} data-testid="inst-filter-plan">
          <option value="">All plans</option><option value="none">No plan</option>{data?.plans.map((p) => <option key={p.id} value={p.id} label={p.name} />)}
        </select>
        <select className={sel} value={status} onChange={(e) => setStatus(e.target.value)} data-testid="inst-filter-status">
          <option value="">All statuses</option><option value="active">Active</option><option value="suspended">Suspended</option><option value="inactive">Inactive</option>
        </select>
      </div>
      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-x-auto">
        <table className="w-full text-sm min-w-[720px]" data-testid="institutions-table">
          <thead><tr className="border-b border-slate-100 dark:border-slate-800 text-left">
            {COLS.map(([k, l]) => (
              <th key={k} className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                <button onClick={() => setSort(([sk, d]) => [k, sk === k ? -d : 1])} className="inline-flex items-center gap-1 hover:text-slate-800 dark:hover:text-slate-200" data-testid={`sort-${k}`}>
                  {l}{sort[0] === k && (sort[1] > 0 ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}</button>
              </th>
            ))}
          </tr></thead>
          <tbody>
            {!data && [0, 1, 2].map((i) => <tr key={i}><td colSpan={6} className="px-4 py-3"><Skeleton className="h-8" /></td></tr>)}
            {rows.map((i) => (
              <tr key={i.id} onClick={() => navigate(`/platform/institutions/${i.id}`)} className="border-b border-slate-50 dark:border-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-800/40 cursor-pointer transition-colors" data-testid={`inst-row-${i.id}`}>
                <td className="px-4 py-3"><div className="flex items-center gap-3">
                  {i.logo_url ? <img src={`${API}${i.logo_url}`} alt="" className="h-9 w-9 rounded-lg object-contain bg-white border border-slate-200 p-0.5" />
                    : <div className="h-9 w-9 rounded-lg bg-indigo-600 text-white font-bold flex items-center justify-center">{(i.name || "?")[0]}</div>}
                  <div><p className="font-medium text-slate-900 dark:text-slate-50">{i.name}{i.is_demo && <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">Demo</span>}</p>
                    <p className="text-xs text-slate-500">{[i.code, i.city, i.domain].filter(Boolean).join(" · ")}</p></div></div></td>
                <td className="px-4 py-3"><PlanBadge name={i.plan_name} /></td>
                <td className="px-4 py-3"><StatusPill status={i.status} /></td>
                <td className="px-4 py-3 tabular-nums">{i.students}</td>
                <td className="px-4 py-3 tabular-nums">{i.teachers}</td>
                <td className="px-4 py-3 text-slate-500">{fmtDay(i.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && !rows.length && <Empty testid="institutions-empty">No schools match these filters.</Empty>}
      </div>
      <FormDialog open={open} onClose={() => setOpen(false)} title="Institution" fields={institutionsConfig.fields} initial={null} onSubmit={create} submitting={busy} error={err} />
    </div>
  );
}
