import { useCallback, useEffect, useMemo, useState } from "react";
import {
  UserX, CalendarRange, Plus, CheckCircle2, Clock, AlertTriangle, Users2, Zap,
  ChevronDown, ChevronRight, Check, X, Send, Ban, Undo2,
} from "lucide-react";
import { CancelAbsenceDialog } from "../../components/substitutions/CancelAbsenceDialog";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";

const today = () => new Date().toISOString().slice(0, 10);
const STATUS = {
  open: { label: "Needs cover", cls: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400", icon: AlertTriangle },
  requested: { label: "Requested", cls: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400", icon: Clock },
  assigned: { label: "Covered", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400", icon: CheckCircle2 },
  cancelled: { label: "Cancelled", cls: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400", icon: Ban },
};

export default function SubstitutionsPage() {
  const [date, setDate] = useState(today());
  const [dash, setDash] = useState(null);
  const [absences, setAbsences] = useState([]);
  const [pending, setPending] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [markOpen, setMarkOpen] = useState(false);
  const [mark, setMark] = useState({ teacher_id: "", date: today(), reason: "" });
  const [expanded, setExpanded] = useState({});
  const [sugFor, setSugFor] = useState(null); // substitution row for suggestions modal
  const [cancelFor, setCancelFor] = useState(null);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const [d, a, p] = await Promise.all([
        api.get("/substitutions/dashboard", { params: { date } }),
        api.get("/absences", { params: { date } }),
        api.get("/absences", { params: { status: "requested" } }),
      ]);
      setDash(d.data);
      setAbsences(a.data.absences.filter((x) => x.status === "approved" || x.status === "cancelled"));
      setPending(p.data.absences);
    } catch (e) { toast.error(errText(e)); }
  }, [date]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { api.get("/lookup/teachers_by_id").then((r) => setTeachers(r.data)).catch(() => {}); }, []);

  const doMark = async () => {
    try {
      await api.post("/absences", mark);
      toast.success("Teacher marked absent — cover periods detected");
      setMarkOpen(false); setMark({ teacher_id: "", date, reason: "" });
      refresh();
    } catch (e) { toast.error(errText(e)); }
  };

  const approve = async (id) => { try { await api.post(`/absences/${id}/approve`); toast.success("Approved"); refresh(); } catch (e) { toast.error(errText(e)); } };
  const reject = async (id) => { try { await api.post(`/absences/${id}/reject`); toast.success("Rejected"); refresh(); } catch (e) { toast.error(errText(e)); } };
  const autoAssign = async (id) => {
    try { const { data } = await api.post(`/absences/${id}/auto-assign`); toast.success(`Auto-assigned ${data.assigned} period(s)${data.skipped ? `, ${data.skipped} unstaffed` : ""}`); refresh(); }
    catch (e) { toast.error(errText(e)); }
  };

  return (
    <div className="space-y-6" data-testid="substitutions-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">Operations</p>
          <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50">Substitutions</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Mark teachers absent, auto-detect affected periods, and cover them with free teachers.</p>
        </div>
        <div className="flex items-center gap-2">
          <CalendarRange size={15} className="text-slate-400" />
          <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-44" data-testid="sub-date" />
          <Button onClick={() => { setMark({ teacher_id: "", date, reason: "" }); setMarkOpen(true); }} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="mark-absent-btn">
            <Plus size={14} className="mr-1" /> Mark absent
          </Button>
        </div>
      </div>

      {dash && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="sub-dashboard">
          <Card icon={UserX} label="Absent today" value={dash.absent_today} tone="slate" />
          <Card icon={AlertTriangle} label="Needs cover" value={dash.open} tone="amber" />
          <Card icon={Clock} label="Requested" value={dash.requested} tone="blue" />
          <Card icon={CheckCircle2} label="Covered" value={dash.assigned} tone="emerald" />
          <Card icon={Clock} label="Leave requests" value={dash.pending_requests} tone="indigo" />
        </div>
      )}

      {pending.length > 0 && (
        <div className="rounded-xl border border-blue-200 dark:border-blue-500/30 bg-blue-50/50 dark:bg-blue-500/5 p-5" data-testid="pending-requests">
          <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 mb-3 flex items-center gap-2"><Clock size={16} className="text-blue-600" /> Leave requests awaiting approval</h2>
          <ul className="space-y-2">
            {pending.map((a) => (
              <li key={a.id} className="flex items-center justify-between text-sm" data-testid={`pending-${a.id}`}>
                <span><span className="font-medium text-slate-800 dark:text-slate-200">{a.teacher_name}</span> · {a.date}{a.reason ? ` · ${a.reason}` : ""}</span>
                <span className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => approve(a.id)} data-testid={`approve-${a.id}`}><Check size={13} className="mr-1" /> Approve</Button>
                  <Button size="sm" variant="ghost" onClick={() => reject(a.id)} data-testid={`reject-${a.id}`} className="text-red-600"><X size={13} className="mr-1" /> Reject</Button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-3">
        <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50">Absent on {date}</h2>
        {absences.length === 0 ? (
          <p className="text-sm text-slate-400" data-testid="no-absences">No approved absences for this date.</p>
        ) : absences.map((a) => (
          <AbsenceRow key={a.id} absence={a} expanded={!!expanded[a.id]}
            onToggle={() => setExpanded((e) => ({ ...e, [a.id]: !e[a.id] }))}
            onAuto={() => autoAssign(a.id)} onSuggest={(sub) => setSugFor(sub)} refreshKey={`${date}-${tick}`}
            onCancel={() => setCancelFor(a)} onChanged={() => { setTick((t) => t + 1); refresh(); }} />
        ))}
      </div>

      <Dialog open={markOpen} onOpenChange={setMarkOpen}>
        <DialogContent className="sm:max-w-md" data-testid="mark-absent-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><UserX size={17} className="text-indigo-600" /> Mark a teacher absent</DialogTitle>
            <DialogDescription>Their published periods that day become cover slots automatically.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-1">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Teacher <span className="text-red-500">*</span></label>
              <Select value={mark.teacher_id} onValueChange={(v) => setMark((m) => ({ ...m, teacher_id: v }))}>
                <SelectTrigger data-testid="mark-teacher-select"><SelectValue placeholder="Pick a teacher" /></SelectTrigger>
                <SelectContent>{teachers.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Date <span className="text-red-500">*</span></label>
              <Input type="date" value={mark.date} onChange={(e) => setMark((m) => ({ ...m, date: e.target.value }))} data-testid="mark-date-input" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Reason</label>
              <Input value={mark.reason} onChange={(e) => setMark((m) => ({ ...m, reason: e.target.value }))} placeholder="Optional" data-testid="mark-reason-input" />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={() => setMarkOpen(false)}>Cancel</Button>
              <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" disabled={!mark.teacher_id || !mark.date} onClick={doMark} data-testid="mark-confirm-btn">Mark absent</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {sugFor && <SuggestDialog sub={sugFor} onClose={() => setSugFor(null)} onDone={() => { setSugFor(null); setTick((t) => t + 1); refresh(); }} />}
      {cancelFor && <CancelAbsenceDialog absence={cancelFor} onClose={() => setCancelFor(null)} onDone={() => { setCancelFor(null); setTick((t) => t + 1); refresh(); }} />}
    </div>
  );
}

const Card = ({ icon: Icon, label, value, tone }) => {
  const tones = {
    slate: "text-slate-500", amber: "text-amber-600", blue: "text-blue-600", emerald: "text-emerald-600", indigo: "text-indigo-600",
  };
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4" data-testid={`card-${label.split(" ")[0].toLowerCase()}`}>
      <div className="flex items-center gap-2 text-slate-400 text-xs font-medium uppercase tracking-wide"><Icon size={13} className={tones[tone]} /> {label}</div>
      <p className="mt-1.5 font-heading text-2xl font-bold text-slate-900 dark:text-slate-50">{value ?? 0}</p>
    </div>
  );
};

const Chip = ({ status }) => {
  const s = STATUS[status] || STATUS.open; const I = s.icon;
  return <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${s.cls}`}><I size={11} /> {s.label}</span>;
};

const AbsenceRow = ({ absence, expanded, onToggle, onAuto, onSuggest, refreshKey, onCancel, onChanged }) => {
  const cancelled = absence.status === "cancelled";
  const removeCover = async (s) => {
    if (!window.confirm(`Remove the cover for ${s.period_label || `P${s.period_no}`} ${s.class_name} ${s.section}? ${s.status === "assigned" ? s.substitute_name : "The asked teachers"} will be notified.`)) return;
    try { await api.post(`/substitutions/${s.id}/remove-cover`, {}); toast.success("Cover removed — back to Needs cover"); onChanged(); }
    catch (e) { toast.error(errText(e)); }
  };
  const [subs, setSubs] = useState(null);
  const load = useCallback(() => {
    api.get(`/absences/${absence.id}`).then((r) => setSubs(r.data.substitutions)).catch(() => setSubs([]));
  }, [absence.id]);
  useEffect(() => { if (expanded) load(); }, [expanded, load, refreshKey]);

  const openCount = subs ? subs.filter((s) => s.status !== "assigned").length : null;

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900" data-testid={`absence-${absence.id}`}>
      <div className="flex items-center justify-between px-5 py-3.5">
        <button onClick={onToggle} className="flex items-center gap-2 text-left" data-testid={`absence-toggle-${absence.id}`}>
          {expanded ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
          <span className="font-medium text-slate-800 dark:text-slate-200">{absence.teacher_name}</span>
          {absence.reason && <span className="text-sm text-slate-400">· {absence.reason}</span>}
          {cancelled && <Chip status="cancelled" />}
        </button>
        {!cancelled && (
          <span className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={onAuto} data-testid={`auto-assign-${absence.id}`}><Zap size={13} className="mr-1" /> Auto-cover all</Button>
            <Button size="sm" variant="ghost" className="text-red-600" onClick={onCancel} data-testid={`cancel-absence-${absence.id}`}><Ban size={13} className="mr-1" /> Cancel absence</Button>
          </span>
        )}
      </div>
      {cancelled && (
        <p className="px-5 pb-3 -mt-1 text-xs text-slate-500" data-testid={`cancelled-info-${absence.id}`}>
          Cancelled by {absence.cancelled_by_name || "—"} · {(absence.cancelled_at || "").slice(0, 16).replace("T", " ")} · {absence.cancel_reason}
          {absence.kept_periods?.length > 0 && ` · kept as history: ${absence.kept_periods.map((p) => `P${p}`).join(", ")}`}
        </p>
      )}
      {expanded && (
        <div className="border-t border-slate-100 dark:border-slate-800 divide-y divide-slate-100 dark:divide-slate-800/60">
          {subs === null ? <p className="px-5 py-4 text-sm text-slate-400">Loading…</p>
            : subs.length === 0 ? <p className="px-5 py-4 text-sm text-slate-400">No published periods on this day — nothing to cover.</p>
            : subs.map((s) => (
              <div key={s.id} className="flex items-center justify-between px-5 py-3 text-sm" data-testid={`sub-${s.id}`}>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs bg-slate-100 dark:bg-slate-800 rounded px-1.5 py-0.5" title={`Slot ${s.period_no}`}>{s.period_label || `P${s.period_no}`}</span>
                  <span className="text-slate-700 dark:text-slate-200">{s.class_name} {s.section} · {s.subject}</span>
                  <Chip status={s.status} />
                  {s.substitute_name && <span className="text-xs text-emerald-600">→ {s.substitute_name}</span>}
                </div>
                {s.status !== "cancelled" && !cancelled && (
                  <span className="flex items-center gap-1.5">
                    {(s.status === "assigned" || s.status === "requested") && (
                      <Button size="sm" variant="ghost" className="text-slate-500" onClick={() => removeCover(s)} data-testid={`remove-cover-${s.id}`}><Undo2 size={13} className="mr-1" /> Remove cover</Button>
                    )}
                    <Button size="sm" variant="outline" onClick={() => onSuggest(s)} data-testid={`cover-${s.id}`}>
                      <Users2 size={13} className="mr-1" /> {s.status === "assigned" ? "Change" : "Find cover"}
                    </Button>
                  </span>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );
};

const SuggestDialog = ({ sub, onClose, onDone }) => {
  const [sug, setSug] = useState(null);
  const [picked, setPicked] = useState([]);
  useEffect(() => {
    api.get(`/substitutions/${sub.id}/suggestions`).then((r) => setSug(r.data.suggestions)).catch((e) => { toast.error(errText(e)); setSug([]); });
  }, [sub.id]);

  const assign = async (tid) => { try { await api.post(`/substitutions/${sub.id}/assign`, { teacher_id: tid }); toast.success("Covered"); onDone(); } catch (e) { toast.error(errText(e)); } };
  const request = async () => {
    if (!picked.length) return;
    try { await api.post(`/substitutions/${sub.id}/request`, { teacher_ids: picked }); toast.success(`Asked ${picked.length} teacher(s)`); onDone(); } catch (e) { toast.error(errText(e)); }
  };
  const toggle = (tid) => setPicked((p) => (p.includes(tid) ? p.filter((x) => x !== tid) : [...p, tid]));

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-lg" data-testid="suggest-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Users2 size={17} className="text-indigo-600" /> Cover {sub.class_name} {sub.section} · {sub.subject} (P{sub.period_no})</DialogTitle>
          <DialogDescription>Free teachers on {sub.date}, ranked by subject match and lighter load.</DialogDescription>
        </DialogHeader>
        <div className="max-h-96 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800/60">
          {sug === null ? <p className="py-6 text-center text-sm text-slate-400">Finding free teachers…</p>
            : sug.length === 0 ? <p className="py-6 text-center text-sm text-slate-400" data-testid="no-suggestions">No free teachers at this period.</p>
            : sug.map((t) => (
              <div key={t.teacher_id} className="flex items-center justify-between py-2.5 px-1" data-testid={`suggestion-${t.teacher_id}`}>
                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input type="checkbox" checked={picked.includes(t.teacher_id)} onChange={() => toggle(t.teacher_id)} data-testid={`pick-${t.teacher_id}`} className="accent-indigo-600" />
                  <span>
                    <span className="font-medium text-slate-800 dark:text-slate-200">{t.name}</span>
                    <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${t.match === 2 ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400" : t.match === 1 ? "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400" : "bg-slate-100 text-slate-500 dark:bg-slate-800"}`}>{t.match_label}</span>
                    <span className="ml-2 text-xs text-slate-400">{t.day_periods} periods today · {t.subs_today} subs</span>
                    {t.response && <span className="ml-2 text-xs font-medium text-emerald-600">{t.response}</span>}
                  </span>
                </label>
                <Button size="sm" className="bg-indigo-700 hover:bg-indigo-800 text-white" onClick={() => assign(t.teacher_id)} data-testid={`assign-${t.teacher_id}`}>Assign</Button>
              </div>
            ))}
        </div>
        <div className="flex justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
          <Button variant="outline" onClick={onClose}>Close</Button>
          <Button className="bg-blue-600 hover:bg-blue-700 text-white" disabled={!picked.length} onClick={request} data-testid="request-btn"><Send size={13} className="mr-1" /> Ask selected ({picked.length})</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
