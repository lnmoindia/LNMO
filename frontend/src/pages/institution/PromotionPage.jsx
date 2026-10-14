import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRightLeft, GraduationCap, UserMinus, RotateCcw, Play, Eye, CheckCircle2,
  Clock, MessageSquarePlus, Loader2, ChevronRight, AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { bulkToast } from "../../components/bulk/BulkResultDialog";
import { inr } from "../../lib/fees";
import { useAuth } from "../../context/AuthContext";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";
import { Textarea } from "../../components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "../../components/ui/alert-dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../../components/ui/tabs";

const DECISIONS = [
  { value: "promote", label: "Promote", icon: ChevronRight, cls: "text-emerald-600" },
  { value: "detain", label: "Detain", icon: Clock, cls: "text-amber-600" },
  { value: "transfer_out", label: "Transfer out", icon: UserMinus, cls: "text-rose-600" },
  { value: "graduate", label: "Graduate", icon: GraduationCap, cls: "text-indigo-600" },
];
const decMeta = (v) => DECISIONS.find((d) => d.value === v) || DECISIONS[0];

const DecisionBadge = ({ value }) => {
  const m = decMeta(value);
  const bg = {
    promote: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
    detain: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
    transfer_out: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400",
    graduate: "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400",
  }[value];
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${bg}`} data-testid={`promo-decision-badge-${value}`}>{m.label}</span>;
};

const RecBadge = ({ value }) => {
  if (!value) return <span className="text-xs text-slate-400">—</span>;
  const cls = value === "detain"
    ? "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400"
    : "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400";
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${cls}`}><MessageSquarePlus size={10} /> {value === "detain" ? "Detain" : "Promote"}</span>;
};

const SummaryBar = ({ summary }) => (
  <div className="flex flex-wrap gap-2" data-testid="promo-summary-bar">
    {DECISIONS.map((d) => (
      <div key={d.value} className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
        <d.icon size={15} className={d.cls} />
        <span className="text-sm text-slate-500 dark:text-slate-400">{d.label}</span>
        <span className="text-sm font-bold text-slate-900 dark:text-slate-100" data-testid={`promo-count-${d.value}`}>{summary?.[d.value] ?? 0}</span>
      </div>
    ))}
  </div>
);

const PromoRow = ({ d, due, editable, setDecision, setSectionOverride, onRecommend }) => (
  <tr className="hover:bg-slate-50 dark:hover:bg-slate-800/40" data-testid={`promo-row-${d.student_id}`}>
    <td className="px-4 py-2.5 font-medium text-slate-800 dark:text-slate-100">{d.student_name}
      {due > 0 && <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/30" title="Outstanding fee balance — promotion is still allowed; dues carry forward as arrears" data-testid={`promo-dues-badge-${d.student_id}`}><AlertTriangle size={10} /> Dues pending {inr(due)}</span>}
      <div className="text-xs text-slate-400">{d.admission_no || ""}</div></td>
    <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300">{d.from_class} · {d.from_section}</td>
    <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300">
      {d.to_class ? <>{d.to_class} · {editable && (d.decision === "promote" || d.decision === "detain") ? (
        <input className="w-10 ml-1 rounded border border-slate-200 dark:border-slate-700 bg-transparent px-1 py-0.5 text-xs" defaultValue={d.to_section || ""} onBlur={(e) => e.target.value !== (d.to_section || "") && setSectionOverride(d, e.target.value)} data-testid={`promo-section-override-${d.student_id}`} />
      ) : <span className="text-slate-400">{d.to_section}</span>}</> : <span className="text-slate-400">—</span>}
    </td>
    <td className="px-4 py-2.5"><RecBadge value={d.teacher_recommendation} />{d.recommendation_note ? <div className="text-[11px] text-slate-400 italic mt-0.5 max-w-[160px] truncate" title={d.recommendation_note}>“{d.recommendation_note}”</div> : null}</td>
    <td className="px-4 py-2.5">
      {editable ? (
        <Select value={d.decision} onValueChange={(v) => setDecision(d, v)}>
          <SelectTrigger className="w-[140px] h-8" data-testid={`promo-decision-select-${d.student_id}`}><SelectValue /></SelectTrigger>
          <SelectContent>{DECISIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
        </Select>
      ) : <DecisionBadge value={d.decision} />}
    </td>
    <td className="px-4 py-2.5 text-right">
      {editable && (
        <Button size="sm" variant="ghost" onClick={() => onRecommend(d)} data-testid={`promo-recommend-btn-${d.student_id}`}>
          <MessageSquarePlus size={14} className="mr-1" /> Recommend
        </Button>
      )}
    </td>
  </tr>
);

const SectionGroup = ({ cls, section, rows, dues, editable, setDecision, setSectionOverride, onRecommend, onBulk }) => {
  const [note, setNote] = useState("");
  const [override, setOverride] = useState(false);
  const key = `${cls}-${section}`;
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden" data-testid={`promo-group-${key}`}>
      <div className="flex flex-wrap items-center gap-3 px-4 py-2.5 border-b border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40">
        <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">{cls} · {section}</span>
        <span className="text-xs text-slate-400">{rows.length} student{rows.length === 1 ? "" : "s"}</span>
        {editable && (
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Input className="h-8 w-44" placeholder="Note for all (optional)" value={note} onChange={(e) => setNote(e.target.value)} data-testid={`promo-bulk-note-${key}`} />
            <label className="flex items-center gap-1 text-xs text-slate-500 cursor-pointer" data-testid={`promo-bulk-override-label-${key}`}>
              <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} data-testid={`promo-bulk-override-${key}`} /> override edited
            </label>
            <Button size="sm" variant="outline" className="h-8 border-emerald-300 text-emerald-700 hover:bg-emerald-50" onClick={() => onBulk(cls, section, "promote", note, override)} data-testid={`promo-bulk-promote-${key}`}>Mark all promote</Button>
            <Button size="sm" variant="outline" className="h-8 border-amber-300 text-amber-700 hover:bg-amber-50" onClick={() => onBulk(cls, section, "detain", note, override)} data-testid={`promo-bulk-detain-${key}`}>Recommend detain all</Button>
          </div>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-800/50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2.5">Student</th>
              <th className="px-4 py-2.5">From</th>
              <th className="px-4 py-2.5">To</th>
              <th className="px-4 py-2.5">Teacher rec.</th>
              <th className="px-4 py-2.5">Decision</th>
              <th className="px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows.map((d) => (
              <PromoRow key={d.id} d={d} due={dues?.[d.student_id] || 0} editable={editable} setDecision={setDecision} setSectionOverride={setSectionOverride} onRecommend={onRecommend} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default function PromotionPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "institution_admin";
  const [years, setYears] = useState([]);
  const [fromYear, setFromYear] = useState("");
  const [toYear, setToYear] = useState("");
  const [busy, setBusy] = useState(false);
  const [run, setRun] = useState(null);
  const [decisions, setDecisions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [recFor, setRecFor] = useState(null);
  const [recForm, setRecForm] = useState({ recommendation: "promote", note: "" });
  const [confirmExec, setConfirmExec] = useState(false);
  const [execText, setExecText] = useState("");
  const [confirmRollback, setConfirmRollback] = useState(false);
  const [dues, setDues] = useState({});
  const [duesSummary, setDuesSummary] = useState(null);
  const applyDues = (data) => { setDues(data.dues || {}); setDuesSummary(data.dues_summary || null); };

  useEffect(() => {
    api.get("/res/academic_years", { params: { limit: 100 } })
      .then(({ data }) => setYears((data.items || []).map((y) => y.name)))
      .catch(() => {});
    api.get("/promotion/runs").then(({ data }) => {
      const active = (data.runs || []).find((r) => r.status !== "rolled_back");
      if (active) loadRun(active.id);
    }).catch(() => {});
  }, []);

  const loadRun = useCallback(async (id) => {
    try {
      const { data } = await api.get(`/promotion/${id}`);
      setRun(data.run); setDecisions(data.decisions); setSummary(data.summary); applyDues(data);
      setFromYear(data.run.from_year); setToYear(data.run.to_year);
    } catch (e) { toast.error(errText(e)); }
  }, []);

  const runPreview = async () => {
    if (!fromYear || !toYear) { toast.error("Pick both years"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/promotion/preview", { from_year: fromYear, to_year: toYear });
      setRun(data.run); setDecisions(data.decisions); setSummary(data.summary); applyDues(data);
      toast.success(`Preview ready — ${data.decisions.length} students${data.structure.academic_year_created ? ` · created ${toYear}` : ""}`);
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const divisions = useMemo(() => {
    const set = [...new Set(decisions.map((d) => d.division || "Other"))];
    return set.sort();
  }, [decisions]);

  const patchDecision = (updated) => setDecisions((ds) => ds.map((d) => (d.id === updated.id ? updated : d)));
  useEffect(() => { setSummary(decisions.length ? decisions.reduce((a, d) => ({ ...a, [d.decision]: (a[d.decision] || 0) + 1 }), {}) : summary); }, [decisions]); // eslint-disable-line

  const setDecision = async (d, decision) => {
    try {
      const { data } = await api.put(`/promotion/decisions/${d.id}`, { decision });
      patchDecision(data);
    } catch (e) { toast.error(errText(e)); }
  };

  const setSectionOverride = async (d, to_section) => {
    try {
      const { data } = await api.put(`/promotion/decisions/${d.id}`, { decision: d.decision, to_section });
      patchDecision(data);
    } catch (e) { toast.error(errText(e)); }
  };

  const submitRec = async () => {
    try {
      const { data } = await api.put(`/promotion/decisions/${recFor.id}/recommend`, recForm);
      patchDecision(data);
      toast.success("Recommendation saved"); setRecFor(null);
    } catch (e) { toast.error(errText(e)); }
  };

  const bulkRecommend = async (class_name, section, recommendation, note, override) => {
    try {
      const { data } = await api.put(`/promotion/${run.id}/recommend-bulk`, { class_name, section, recommendation, note, override });
      toast.success(`Applied to ${data.applied}${data.skipped ? ` · skipped ${data.skipped} already-edited` : ""}`);
      loadRun(run.id);
    } catch (e) { toast.error(errText(e)); }
  };

  const openRecommend = (d) => { setRecFor(d); setRecForm({ recommendation: d.teacher_recommendation || "promote", note: d.recommendation_note || "" }); };

  const doExecute = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/promotion/${run.id}/execute`);
      const cf = data.dues_carry_forward;
      bulkToast(toast, { title: `Promotion ${run.from_year} → ${run.to_year}`, items: data.items, summary: data.run_summary }, null,
        `Executed — promoted ${data.summary.promote}, detained ${data.summary.detain}, graduated ${data.summary.graduate}, transferred ${data.summary.transfer_out}: `);
      if (cf?.items?.length) bulkToast(toast, { title: `Dues carry-forward ${run.from_year} → ${run.to_year}`, items: cf.items, summary: cf.summary }, null, `Dues carry-forward (${inr(cf.amount)}): `);
      setConfirmExec(false); setExecText(""); loadRun(run.id);
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const doRollback = async () => {
    setBusy(true);
    try {
      await api.post(`/promotion/${run.id}/rollback`);
      toast.success("Rolled back"); setConfirmRollback(false); loadRun(run.id);
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const editable = run?.status === "preview";

  return (
    <div className="space-y-6" data-testid="promotion-page">
      <div>
        <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50 flex items-center gap-2">
          <ArrowRightLeft className="text-indigo-600" /> Promotion & Year Rollover
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Preview the year-end promotion, let class teachers recommend, confirm decisions, then execute.</p>
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm flex flex-wrap items-end gap-4">
        <div className="space-y-1.5">
          <Label>From year</Label>
          <Select value={fromYear} onValueChange={setFromYear} disabled={!!run && editable}>
            <SelectTrigger className="w-[160px]" data-testid="promo-from-year"><SelectValue placeholder="Current year" /></SelectTrigger>
            <SelectContent>{years.map((y) => <SelectItem key={y} value={y}>{y}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <ArrowRightLeft size={18} className="text-slate-400 mb-2.5" />
        <div className="space-y-1.5">
          <Label>To year</Label>
          <Input className="w-[160px]" value={toYear} onChange={(e) => setToYear(e.target.value)} placeholder="e.g. 2027-28" data-testid="promo-to-year" />
        </div>
        <Button onClick={runPreview} disabled={busy} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="promo-preview-btn">
          {busy ? <Loader2 size={15} className="mr-1.5 animate-spin" /> : <Eye size={15} className="mr-1.5" />} Preview
        </Button>
        {run && (
          <div className="ml-auto flex items-center gap-2 text-sm">
            <span className="text-slate-500">Status:</span>
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${run.status === "executed" ? "bg-emerald-50 text-emerald-700" : run.status === "rolled_back" ? "bg-slate-100 text-slate-600" : "bg-amber-50 text-amber-700"}`} data-testid="promo-run-status">
              {run.status === "executed" ? <CheckCircle2 size={12} /> : null}{run.status}
            </span>
          </div>
        )}
      </div>

      {run && (
        <>
          {duesSummary && duesSummary.students > 0 && (
            <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50/70 dark:bg-amber-500/10 dark:border-amber-500/30 px-4 py-3" data-testid="promo-dues-summary">
              <AlertTriangle size={18} className="text-amber-600 mt-0.5 shrink-0" />
              <div className="text-sm">
                <p className="font-semibold text-amber-900 dark:text-amber-200"><span data-testid="promo-dues-count">{duesSummary.students}</span> student{duesSummary.students === 1 ? "" : "s"} with pending dues, <span data-testid="promo-dues-total">{inr(duesSummary.total)}</span></p>
                <p className="text-amber-800/80 dark:text-amber-300/80 text-xs mt-0.5">Warning only — promotion is not blocked. On execute, unpaid balances carry forward to the new year as a "Previous dues" arrears invoice (linked to the original invoices).</p>
              </div>
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <SummaryBar summary={summary} />
            <div className="flex gap-2">
              {isAdmin && editable && (
                <Button onClick={() => setConfirmExec(true)} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="promo-execute-btn">
                  <Play size={15} className="mr-1.5" /> Execute
                </Button>
              )}
              {isAdmin && run.status === "executed" && (
                <Button variant="outline" onClick={() => setConfirmRollback(true)} className="border-rose-300 text-rose-600 hover:bg-rose-50" data-testid="promo-rollback-btn">
                  <RotateCcw size={15} className="mr-1.5" /> Roll back
                </Button>
              )}
            </div>
          </div>

          <Tabs defaultValue={divisions[0]} className="w-full">
            <TabsList className="flex-wrap h-auto" data-testid="promo-division-tabs">
              {divisions.map((dv) => <TabsTrigger key={dv} value={dv} data-testid={`promo-tab-${dv}`}>{dv}</TabsTrigger>)}
            </TabsList>
            {divisions.map((dv) => {
              const dvRows = decisions.filter((d) => (d.division || "Other") === dv);
              const groups = [...new Set(dvRows.map((d) => `${d.from_class}||${d.from_section}`))];
              return (
                <TabsContent key={dv} value={dv} className="mt-4 space-y-4">
                  {groups.map((g) => {
                    const [cls, section] = g.split("||");
                    const rows = dvRows.filter((d) => `${d.from_class}||${d.from_section}` === g);
                    return (
                      <SectionGroup key={g} cls={cls} section={section} rows={rows} dues={dues} editable={editable}
                        setDecision={setDecision} setSectionOverride={setSectionOverride}
                        onRecommend={openRecommend} onBulk={bulkRecommend} />
                    );
                  })}
                </TabsContent>
              );
            })}
          </Tabs>
        </>
      )}

      {/* Recommend dialog */}
      <Dialog open={!!recFor} onOpenChange={(o) => !o && setRecFor(null)}>
        <DialogContent className="sm:max-w-md" data-testid="promo-recommend-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading">Recommend — {recFor?.student_name}</DialogTitle>
            <DialogDescription>A recommendation guides the principal. Detention only applies once the final decision is set to “Detain”.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-1">
            <Select value={recForm.recommendation} onValueChange={(v) => setRecForm((f) => ({ ...f, recommendation: v }))}>
              <SelectTrigger data-testid="promo-rec-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="promote">Recommend promote</SelectItem>
                <SelectItem value="detain">Recommend detain</SelectItem>
              </SelectContent>
            </Select>
            <Textarea placeholder="Note (optional)" value={recForm.note} onChange={(e) => setRecForm((f) => ({ ...f, note: e.target.value }))} data-testid="promo-rec-note" />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setRecFor(null)}>Cancel</Button>
              <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" onClick={submitRec} data-testid="promo-rec-save">Save recommendation</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Execute confirm */}
      <AlertDialog open={confirmExec} onOpenChange={setConfirmExec}>
        <AlertDialogContent data-testid="promo-execute-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Execute promotion {run?.from_year} → {run?.to_year}?</AlertDialogTitle>
            <AlertDialogDescription>
              This creates new-year enrollments, graduates Grade 12, and disables transferred-out logins. Type <b>EXECUTE</b> to confirm.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Input value={execText} onChange={(e) => setExecText(e.target.value)} placeholder="EXECUTE" data-testid="promo-execute-confirm-input" />
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setExecText("")}>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={execText !== "EXECUTE" || busy} onClick={doExecute} className="bg-emerald-600 hover:bg-emerald-700" data-testid="promo-execute-confirm-btn">Execute</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Rollback confirm */}
      <AlertDialog open={confirmRollback} onOpenChange={setConfirmRollback}>
        <AlertDialogContent data-testid="promo-rollback-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Roll back this promotion?</AlertDialogTitle>
            <AlertDialogDescription>Reverses all enrollments, restores previous placement, re-enables logins. Blocked if the new year already has timetable/marks/attendance data.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={busy} onClick={doRollback} className="bg-rose-600 hover:bg-rose-700" data-testid="promo-rollback-confirm-btn">Roll back</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
