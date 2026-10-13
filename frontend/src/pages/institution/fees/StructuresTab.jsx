import { useCallback, useEffect, useState } from "react";
import { Plus, Copy, Pencil, Users, FileStack, Trash2 } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { inr, FREQ_LABEL } from "../../../lib/fees";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Switch } from "../../../components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../../../components/ui/dialog";

const sel = "h-9 rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-2 text-sm";
const blankHead = () => ({ title: "", amount: "", frequency: "annual", optional: false });
const blank = { name: "", academic_year: "", target: "unit", academic_unit_id: "", class_name: "", heads: [blankHead()],
  late_fee: { enabled: false, type: "flat", value: 0, grace_days: 0 }, active: true };

function HeadRow({ h, i, set, remove }) {
  return (
    <div className="grid grid-cols-[1fr_110px_120px_auto_auto] gap-2 items-center" data-testid={`fee-head-row-${i}`}>
      <Input placeholder="Title (e.g. Tuition, Bus fee)" value={h.title} onChange={(e) => set({ title: e.target.value })} data-testid={`fee-head-title-${i}`} />
      <Input type="number" min="0" placeholder="Amount" value={h.amount} onChange={(e) => set({ amount: e.target.value })} data-testid={`fee-head-amount-${i}`} />
      <select className={sel} value={h.frequency} onChange={(e) => set({ frequency: e.target.value })} data-testid={`fee-head-frequency-${i}`}>
        {Object.entries(FREQ_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <label className="flex items-center gap-1.5 text-xs text-slate-500"><Switch checked={h.optional} onCheckedChange={(v) => set({ optional: v })} data-testid={`fee-head-optional-${i}`} /> Optional</label>
      <button onClick={remove} className="text-slate-400 hover:text-rose-600" data-testid={`fee-head-remove-${i}`}><Trash2 size={15} /></button>
    </div>
  );
}

function StructureDialog({ open, initial, onClose, onSaved, units, classes }) {
  const [f, setF] = useState(blank);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setF(initial ? { ...initial, target: initial.class_name ? "class" : "unit", academic_unit_id: initial.academic_unit_id || "", class_name: initial.class_name || "" } : blank);
  }, [open, initial]);
  const setHead = (i, patch) => setF((s) => ({ ...s, heads: s.heads.map((h, j) => (j === i ? { ...h, ...patch } : h)) }));
  const setLate = (patch) => setF((s) => ({ ...s, late_fee: { ...s.late_fee, ...patch } }));
  const save = async () => {
    setBusy(true);
    const body = { name: f.name, academic_year: f.academic_year, active: f.active,
      academic_unit_id: f.target === "unit" ? f.academic_unit_id || null : null, class_name: f.target === "class" ? f.class_name || null : null,
      heads: f.heads.map((h) => ({ ...(h.id ? { id: h.id } : {}), title: h.title, amount: Number(h.amount || 0), frequency: h.frequency, optional: h.optional })),
      late_fee: { ...f.late_fee, value: Number(f.late_fee.value || 0), grace_days: Number(f.late_fee.grace_days || 0) } };
    try {
      if (initial) await api.put(`/fees/structures/${initial.id}`, body); else await api.post("/fees/structures", body);
      toast.success("Fee structure saved"); onSaved();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="fee-structure-dialog">
        <DialogHeader><DialogTitle>{initial ? "Edit fee structure" : "New fee structure"}</DialogTitle>
          <DialogDescription>Applies to every enrolled student of the chosen academic unit or class.</DialogDescription></DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5"><Label>Name</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="HS Fee Structure 2026-27" data-testid="fee-structure-name" /></div>
          <div className="space-y-1.5"><Label>Academic year</Label><Input value={f.academic_year} onChange={(e) => setF({ ...f, academic_year: e.target.value })} placeholder="2026-27" data-testid="fee-structure-year" /></div>
          <div className="space-y-1.5"><Label>Applies to</Label>
            <select className={`${sel} w-full`} value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} data-testid="fee-structure-target">
              <option value="unit">An academic unit</option><option value="class">A specific class</option></select></div>
          <div className="space-y-1.5"><Label>{f.target === "unit" ? "Academic unit" : "Class"}</Label>
            {f.target === "unit" ? (
              <select className={`${sel} w-full`} value={f.academic_unit_id} onChange={(e) => setF({ ...f, academic_unit_id: e.target.value })} data-testid="fee-structure-unit">
                <option value="">Select…</option>{units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select>
            ) : (
              <select className={`${sel} w-full`} value={f.class_name} onChange={(e) => setF({ ...f, class_name: e.target.value })} data-testid="fee-structure-class">
                <option value="">Select…</option>{classes.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}</select>
            )}</div>
        </div>
        <div className="space-y-2">
          <Label>Fee heads</Label>
          {f.heads.map((h, i) => <HeadRow key={i} h={h} i={i} set={(p) => setHead(i, p)} remove={() => setF({ ...f, heads: f.heads.filter((_, j) => j !== i) })} />)}
          <Button size="sm" variant="outline" onClick={() => setF({ ...f, heads: [...f.heads, blankHead()] })} data-testid="fee-head-add"><Plus size={13} className="mr-1" /> Add head</Button>
        </div>
        <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-3 grid grid-cols-4 gap-3 items-end">
          <label className="flex items-center gap-2 text-sm col-span-4"><Switch checked={f.late_fee.enabled} onCheckedChange={(v) => setLate({ enabled: v })} data-testid="fee-late-enabled" /> Late fee after due date</label>
          {f.late_fee.enabled && (<>
            <div className="space-y-1"><Label className="text-xs">Type</Label><select className={`${sel} w-full`} value={f.late_fee.type} onChange={(e) => setLate({ type: e.target.value })} data-testid="fee-late-type"><option value="flat">Flat ₹</option><option value="percent">% of invoice</option></select></div>
            <div className="space-y-1"><Label className="text-xs">Value</Label><Input type="number" min="0" value={f.late_fee.value} onChange={(e) => setLate({ value: e.target.value })} data-testid="fee-late-value" /></div>
            <div className="space-y-1"><Label className="text-xs">Grace days</Label><Input type="number" min="0" value={f.late_fee.grace_days} onChange={(e) => setLate({ grace_days: e.target.value })} data-testid="fee-late-grace" /></div>
          </>)}
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !f.name || !f.academic_year} onClick={save} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="fee-structure-save">{busy ? "Saving…" : "Save structure"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

const DEFAULTS = { term: ["Term 1", "Term 2", "Term 3"], monthly: ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"], annual: ["Annual"], one_time: ["One-time"] };

function GenerateDialog({ st, onClose, onDone }) {
  const freqs = st ? [...new Set(st.heads.map((h) => h.frequency))] : [];
  const [freq, setFreq] = useState("");
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const pick = useCallback((fq) => { setFreq(fq); setRows((DEFAULTS[fq] || []).map((l) => ({ label: fq === "annual" ? `Annual ${st?.academic_year || ""}`.trim() : l, due_date: "" }))); }, [st]);
  useEffect(() => { if (st) pick([...new Set(st.heads.map((h) => h.frequency))][0]); }, [st, pick]);
  const run = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/fees/structures/${st.id}/generate`, { frequency: freq, periods: rows });
      toast.success(`${data.created} invoices generated${data.skipped_existing ? ` · ${data.skipped_existing} already existed` : ""}`); onDone();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={Boolean(st)} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg" data-testid="fee-generate-dialog">
        <DialogHeader><DialogTitle>Generate invoices</DialogTitle><DialogDescription>One invoice per student per period. Re-running never duplicates a period.</DialogDescription></DialogHeader>
        <select className={`${sel} w-full`} value={freq} onChange={(e) => pick(e.target.value)} data-testid="fee-generate-frequency">
          {freqs.map((fq) => <option key={fq} value={fq}>{FREQ_LABEL[fq]} heads</option>)}
        </select>
        <div className="space-y-2 max-h-72 overflow-y-auto">
          {rows.map((r, i) => (
            <div key={i} className="grid grid-cols-[1fr_160px_auto] gap-2" data-testid={`fee-period-row-${i}`}>
              <Input value={r.label} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} data-testid={`fee-period-label-${i}`} />
              <Input type="date" value={r.due_date} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, due_date: e.target.value } : x)))} data-testid={`fee-period-due-${i}`} />
              <button onClick={() => setRows(rows.filter((_, j) => j !== i))} className="text-slate-400 hover:text-rose-600"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
        {!["annual", "one_time"].includes(freq) && <Button size="sm" variant="outline" onClick={() => setRows([...rows, { label: "", due_date: "" }])}><Plus size={13} className="mr-1" /> Add period</Button>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !rows.length || rows.some((r) => !r.label || !r.due_date)} onClick={run} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="fee-generate-run">{busy ? "Generating…" : "Generate"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function StructureCard({ st, readOnly, onEdit, onClone, onApply, onGenerate }) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3" data-testid={`fee-structure-${st.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-slate-900 dark:text-slate-100">{st.name}</p>
          <p className="text-xs text-slate-500">{st.academic_year} · {st.class_name || st.unit_name || "Unit"} · {st.account_count} accounts · {st.invoice_count} invoices
            {st.late_fee?.enabled ? ` · late fee ${st.late_fee.type === "flat" ? inr(st.late_fee.value) : `${st.late_fee.value}%`} after ${st.late_fee.grace_days} days` : ""}</p>
        </div>
        {!readOnly && (
          <div className="flex flex-wrap gap-1.5">
            <Button size="sm" variant="outline" disabled={st.invoice_count > 0} title={st.invoice_count ? "Invoices exist — clone to change" : ""} onClick={onEdit} data-testid={`fee-structure-edit-${st.id}`}><Pencil size={13} className="mr-1" /> Edit</Button>
            <Button size="sm" variant="outline" onClick={onClone} data-testid={`fee-structure-clone-${st.id}`}><Copy size={13} className="mr-1" /> Clone</Button>
            <Button size="sm" variant="outline" onClick={onApply} data-testid={`fee-structure-apply-${st.id}`}><Users size={13} className="mr-1" /> Apply to students</Button>
            <Button size="sm" onClick={onGenerate} disabled={!st.account_count} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid={`fee-structure-generate-${st.id}`}><FileStack size={13} className="mr-1" /> Generate invoices</Button>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {st.heads.map((h) => (
          <span key={h.id} className="text-xs rounded-full border border-slate-200 dark:border-slate-700 px-2.5 py-1 text-slate-600 dark:text-slate-300">
            {h.title} · <b>{inr(h.amount)}</b> · {FREQ_LABEL[h.frequency]}{h.optional ? " · optional" : ""}</span>
        ))}
      </div>
    </div>
  );
}

export default function StructuresTab({ readOnly }) {
  const [rows, setRows] = useState(null);
  const [units, setUnits] = useState([]);
  const [classes, setClasses] = useState([]);
  const [editing, setEditing] = useState(undefined);
  const [gen, setGen] = useState(null);
  const load = useCallback(() => api.get("/fees/structures").then((r) => setRows(r.data.structures)).catch((e) => { toast.error(errText(e)); setRows([]); }), []);
  useEffect(() => {
    load();
    api.get("/res/academic_units", { params: { limit: 200 } }).then((r) => setUnits(r.data.items || [])).catch(() => {});
    api.get("/res/classes", { params: { limit: 500 } }).then((r) => setClasses(r.data.items || [])).catch(() => {});
  }, [load]);
  const act = async (fn, msg) => { try { const r = await fn(); toast.success(msg(r.data)); load(); } catch (e) { toast.error(errText(e)); } };
  return (
    <div className="space-y-4 pt-2" data-testid="fees-structures-tab">
      {!readOnly && <Button onClick={() => setEditing(null)} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="fee-structure-new-btn"><Plus size={15} className="mr-1.5" /> New structure</Button>}
      {rows?.length === 0 && <p className="text-sm text-slate-400 py-8 text-center">No fee structures yet.</p>}
      {rows?.map((st) => (
        <StructureCard key={st.id} st={st} readOnly={readOnly} onEdit={() => setEditing(st)} onGenerate={() => setGen(st)}
          onClone={() => act(() => api.post(`/fees/structures/${st.id}/clone`), () => "Cloned — edit the copy")}
          onApply={() => act(() => api.post(`/fees/structures/${st.id}/apply`), (d) => `${d.created} accounts created${d.skipped.length ? ` · ${d.skipped.length} skipped` : ""}`)} />
      ))}
      <StructureDialog open={editing !== undefined} initial={editing} units={units} classes={classes} onClose={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); load(); }} />
      <GenerateDialog st={gen} onClose={() => setGen(null)} onDone={() => { setGen(null); load(); }} />
    </div>
  );
}
