import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ArrowLeft, CalendarClock, Sparkles, Send, EyeOff, FileSpreadsheet, Printer,
  AlertTriangle, Pencil, Ban, History, ChevronDown, MoreVertical, LayoutGrid, CalendarDays, MessageSquare,
} from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "../../../components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../../components/ui/select";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator,
} from "../../../components/ui/dropdown-menu";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../../../components/ui/tabs";
import { printExamClass } from "../../../lib/printDoc";
import ComposeDialog from "../../../components/comm/ComposeDialog";

const STATUS_CHIP = {
  scheduled: "bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300",
  postponed: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  cancelled: "bg-red-100 text-red-600 dark:bg-red-500/15 dark:text-red-300",
};
const DAY_OF = (d) => { try { return new Date(d + "T00:00:00").toLocaleDateString(undefined, { weekday: "short" }); } catch (e) { return ""; } };
const classKey = (e) => e.class_name + (e.section ? " - " + e.section : "");

export default function ExamDetailPage() {
  const { examId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [brand, setBrand] = useState(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [editEntry, setEditEntry] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [selClass, setSelClass] = useState("");
  const [dayDate, setDayDate] = useState("");
  const [notify, setNotify] = useState(null);   // {classNames, examName}

  const load = useCallback(() => {
    api.get(`/exams/${examId}`).then((r) => setData(r.data)).catch((e) => { toast.error(errText(e)); navigate("/app/exams"); });
  }, [examId, navigate]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get("/institution/brand-lite").then((r) => setBrand(r.data)).catch(() => {}); }, []);

  const exam = data?.exam;
  const entries = data?.entries || [];
  const editable = exam ? (exam.editable !== false) : false;

  const classes = useMemo(() => Array.from(new Set(entries.map(classKey))).sort(), [entries]);
  useEffect(() => { if (classes.length && !classes.includes(selClass)) setSelClass(classes[0]); }, [classes]); // eslint-disable-line

  const act = async (fn, okMsg) => {
    setBusy(true);
    try { const r = await fn(); if (okMsg) toast.success(typeof okMsg === "function" ? okMsg(r) : okMsg); load(); return r; }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const generate = (createRegisters) => act(async () => {
    const { data: res } = await api.post(`/exams/${examId}/generate`, { create_registers: createRegisters });
    setReport(res); return res;
  }, (res) => "Scheduled " + res.generated + " papers" + (res.registers_created ? " · " + res.registers_created + " registers" : ""));
  const publish = (pub) => act(() => api.post(`/exams/${examId}/${pub ? "publish" : "unpublish"}`), pub ? "Published to students & parents" : "Unpublished");
  const makeRegisters = () => act(async () => { const { data: res } = await api.post(`/exams/${examId}/registers`); return res; }, (r) => r.registers_created + " register(s) created");
  const publishResults = () => act(async () => { const { data: res } = await api.post(`/exams/${examId}/publish-results`, { publish: true }); return res; }, (r) => "Published results for " + r.updated + " register(s)" + (r.skipped ? " · " + r.skipped + " out of scope" : ""));

  const logoUrl = brand ? (brand.logo_url || (brand.has_logo && brand.slug
    ? `${process.env.REACT_APP_BACKEND_URL}/api/public/institution-logo?slug=${brand.slug}` : "")) : "";

  const printClass = (clsLabel) => {
    const list = entries.filter((e) => classKey(e) === clsLabel && e.status !== "cancelled")
      .sort((a, b) => (a.date + a.start).localeCompare(b.date + b.start));
    const [cn, sec] = clsLabel.split(" - ");
    printExamClass({
      schoolName: brand?.name, logoUrl, examName: exam.name, className: cn, section: sec || "",
      rows: list.map((e) => ({ date: e.date, day: DAY_OF(e.date), time: `${e.start}–${e.end}`, subject: e.subject, room: e.room })),
    });
  };

  if (!data) return <div className="py-16 text-center text-slate-400" data-testid="exam-detail-loading">Loading…</div>;

  const divForClass = (clsLabel) => {
    const e = entries.find((x) => classKey(x) === clsLabel);
    if (!e) return null;
    const dc = (exam.division_configs || []).find((c) => c.academic_unit_id === e.academic_unit_id);
    return dc ? { name: (exam.unit_names || {})[e.academic_unit_id], cfg: dc } : null;
  };

  return (
    <div className="space-y-6" data-testid="exam-detail-page">
      <Link to="/app/exams" className="inline-flex items-center gap-1.5 text-sm text-indigo-600 dark:text-indigo-400 hover:underline" data-testid="exam-back"><ArrowLeft size={14} /> All exams</Link>

      {/* Header + single primary action + overflow */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50">{exam.name}</h1>
              <span className={`text-[11px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5 ${exam.status === "published" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300" : "bg-slate-100 text-slate-500 dark:bg-slate-700/40"}`} data-testid="exam-detail-status">{exam.status}</span>
            </div>
            <p className="text-sm text-slate-500 mt-1">{exam.academic_year} · {(exam.division_names || []).join(", ")} · {entries.length} papers</p>
          </div>
          {editable ? (
            <div className="flex items-center gap-2" data-testid="exam-actions">
              <Button size="sm" onClick={() => generate(true)} disabled={busy} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="exam-generate-btn">
                <Sparkles size={14} className="mr-1" /> {entries.length ? "Regenerate" : "Generate"} + registers
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="sm" variant="outline" data-testid="exam-overflow-btn"><MoreVertical size={15} /></Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-52">
                  <DropdownMenuItem onClick={() => generate(false)} data-testid="exam-generate-noreg">Generate only (no registers)</DropdownMenuItem>
                  <DropdownMenuItem onClick={makeRegisters} data-testid="exam-registers-btn">Create mark registers</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setNotify({ classNames: Array.from(new Set(entries.map((e) => e.class_name))), examName: exam.name })} data-testid="exam-notify-parents-btn"><MessageSquare size={14} className="mr-2" /> Notify parents</DropdownMenuItem>
                  <DropdownMenuSeparator />
                  {exam.status === "published"
                    ? <DropdownMenuItem onClick={() => publish(false)} data-testid="exam-unpublish-btn" className="text-red-600"><EyeOff size={14} className="mr-2" /> Unpublish schedule</DropdownMenuItem>
                    : <DropdownMenuItem onClick={() => publish(true)} disabled={!entries.length} data-testid="exam-publish-btn"><Send size={14} className="mr-2" /> Publish schedule</DropdownMenuItem>}
                  <DropdownMenuItem onClick={publishResults} data-testid="exam-publish-results-btn"><FileSpreadsheet size={14} className="mr-2" /> Publish all results</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          ) : <span className="text-xs text-amber-600 bg-amber-50 dark:bg-amber-500/10 rounded-full px-3 py-1" data-testid="exam-readonly">Read-only — spans divisions outside your scope</span>}
        </div>
      </div>

      {report && (
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-4 space-y-2" data-testid="exam-report">
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">{report.generated} papers scheduled{report.registers_created ? ` · ${report.registers_created} registers created` : ""}</p>
          {(report.unplaced || []).length > 0 ? (
            <ul className="space-y-1.5" data-testid="exam-unplaced">
              {report.unplaced.map((u, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-300">
                  <AlertTriangle size={13} className="text-amber-500 mt-0.5 shrink-0" />
                  <span>{u.reason} {(u.suggestions || []).map((s, j) => <Link key={j} to={s.href} className="text-indigo-600 hover:underline ml-1">{s.label}</Link>)}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-xs text-emerald-600 dark:text-emerald-400">Every offered subject fit into the schedule.</p>}
        </div>
      )}

      {entries.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 dark:border-slate-700 p-12 text-center" data-testid="exam-no-entries">
          <CalendarClock className="mx-auto text-slate-300 dark:text-slate-600" size={32} />
          <p className="mt-3 text-sm text-slate-500">No papers scheduled yet. Click <strong>Generate</strong> to build the exam timetable.</p>
        </div>
      ) : (
        <Tabs defaultValue="class" data-testid="exam-view-tabs">
          <TabsList>
            <TabsTrigger value="class" data-testid="exam-tab-class"><CalendarClock size={14} className="mr-1.5" /> Class view</TabsTrigger>
            <TabsTrigger value="overview" data-testid="exam-tab-overview"><LayoutGrid size={14} className="mr-1.5" /> Division overview</TabsTrigger>
            <TabsTrigger value="day" data-testid="exam-tab-day"><CalendarDays size={14} className="mr-1.5" /> Day view</TabsTrigger>
          </TabsList>

          {/* CLASS-FIRST default view */}
          <TabsContent value="class" className="mt-4">
            <ClassView classes={classes} selClass={selClass} setSelClass={setSelClass} entries={entries}
              div={divForClass(selClass)} editable={editable} onEdit={setEditEntry} onCancel={setConfirm} onPrint={() => printClass(selClass)} />
          </TabsContent>

          <TabsContent value="overview" className="mt-4">
            <DivisionGrids exam={exam} entries={entries} onPrintClass={printClass} />
          </TabsContent>

          <TabsContent value="day" className="mt-4">
            <DayView entries={entries} dayDate={dayDate} setDayDate={setDayDate} />
          </TabsContent>
        </Tabs>
      )}

      <EntryEditDialog exam={exam} entry={editEntry} onClose={() => setEditEntry(null)} onDone={() => { setEditEntry(null); load(); }} />

      <Dialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent data-testid="exam-cancel-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Ban size={17} className="text-red-600" /> Cancel this paper?</DialogTitle>
            <DialogDescription>{confirm && `${confirm.subject} for ${confirm.class_name}${confirm.section ? " - " + confirm.section : ""} on ${confirm.date} will be marked cancelled.`}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(null)}>Keep it</Button>
            <Button className="bg-red-600 hover:bg-red-700 text-white" data-testid="exam-cancel-confirm"
              onClick={async () => { try { await api.post(`/exam-entries/${confirm.id}/cancel`); toast.success("Paper cancelled"); setConfirm(null); load(); } catch (e) { toast.error(errText(e)); } }}>Cancel paper</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {notify && (
        <ComposeDialog module="exam" title="Notify parents about this exam" defaultCategory="exam"
          defaultVars={{ exam_name: notify.examName }} lockedClassNames={notify.classNames}
          onClose={() => setNotify(null)} />
      )}
    </div>
  );
}

function ClassView({ classes, selClass, setSelClass, entries, div, editable, onEdit, onCancel, onPrint }) {
  const rows = entries.filter((e) => classKey(e) === selClass)
    .sort((a, b) => (a.date + a.start).localeCompare(b.date + b.start));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5" data-testid="exam-class-selector">
          {classes.map((c) => (
            <button key={c} onClick={() => setSelClass(c)} data-testid={`exam-class-chip-${c}`}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${selClass === c ? "bg-indigo-700 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"}`}>{c}</button>
          ))}
        </div>
        <Button size="sm" variant="outline" onClick={onPrint} data-testid="exam-class-print-btn"><Printer size={14} className="mr-1" /> Download PDF</Button>
      </div>
      {div && <p className="text-xs text-slate-500" data-testid="exam-class-divline">{div.name} · {div.cfg.date_start} → {div.cfg.date_end} · {div.cfg.slots_per_day.length} slot/day</p>}

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden" data-testid="exam-class-table">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-900/60 text-left">
            <tr>{["Date", "Day", "Time", "Subject", "Room", "Status", ""].map((h, i) => <th key={i} className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500">{h}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {rows.map((e) => (
              <tr key={e.id} className={e.status === "cancelled" ? "opacity-50" : ""} data-testid={`exam-entry-${e.id}`}>
                <td className="px-4 py-2.5 font-medium text-slate-700 dark:text-slate-200 whitespace-nowrap">{e.date}</td>
                <td className="px-4 py-2.5 text-slate-500">{DAY_OF(e.date)}</td>
                <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap">{e.start}–{e.end}</td>
                <td className="px-4 py-2.5 font-semibold text-slate-800 dark:text-slate-100">{e.subject}</td>
                <td className="px-4 py-2.5 text-slate-500">{e.room || "—"}</td>
                <td className="px-4 py-2.5">
                  <span className={`text-[10px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5 ${STATUS_CHIP[e.status]}`}>{e.status}</span>
                  {e.status === "postponed" && e.original_date && <span className="ml-1.5 text-[10px] text-slate-400">was {e.original_date}</span>}
                </td>
                <td className="px-4 py-2.5 text-right">
                  {editable && e.status !== "cancelled" && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button className="text-slate-400 hover:text-indigo-600" data-testid={`exam-row-menu-${e.id}`}><MoreVertical size={15} /></button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => onEdit(e)} data-testid={`exam-edit-${e.id}`}><Pencil size={13} className="mr-2" /> Reschedule / room</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => onCancel(e)} data-testid={`exam-cancel-${e.id}`} className="text-red-600"><Ban size={13} className="mr-2" /> Cancel paper</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DivisionGrids({ exam, entries, onPrintClass }) {
  const units = exam.unit_names || {};
  const byDivision = useMemo(() => {
    const m = {};
    for (const dc of exam.division_configs) m[dc.academic_unit_id] = { cfg: dc, entries: [] };
    for (const e of entries) (m[e.academic_unit_id] = m[e.academic_unit_id] || { cfg: null, entries: [] }).entries.push(e);
    return m;
  }, [exam, entries]);

  return (
    <div className="space-y-6" data-testid="exam-division-grids">
      {Object.entries(byDivision).map(([unitId, { cfg, entries: dentries }]) => {
        const byClass = {};
        for (const e of dentries) (byClass[classKey(e)] = byClass[classKey(e)] || []).push(e);
        return (
          <div key={unitId} className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden" data-testid={`exam-division-grid-${units[unitId] || unitId}`}>
            <div className="bg-slate-50 dark:bg-slate-900/60 px-4 py-2.5 flex items-center justify-between">
              <h3 className="font-heading font-bold text-slate-800 dark:text-slate-100">{units[unitId] || "Division"}</h3>
              {cfg && <span className="text-xs text-slate-500">{cfg.date_start} → {cfg.date_end} · {cfg.slots_per_day.length} slot/day</span>}
            </div>
            <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {Object.entries(byClass).sort().map(([cls, list]) => (
                <div key={cls} className="px-4 py-3" data-testid={`exam-class-row-${cls}`}>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">{cls}</p>
                    <button onClick={() => onPrintClass(cls)} className="text-slate-400 hover:text-indigo-600" title="Download PDF" data-testid={`exam-print-${cls}`}><Printer size={14} /></button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {list.sort((a, b) => (a.date + a.start).localeCompare(b.date + b.start)).map((e) => (
                      <div key={e.id} className={`rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-xs ${e.status === "cancelled" ? "opacity-50 line-through" : ""}`}>
                        <div className="font-semibold">{e.subject}</div>
                        <div className="opacity-80">{e.date} · {e.start}–{e.end}{e.room ? ` · ${e.room}` : ""}</div>
                        {e.status === "postponed" && <div className="text-[10px] text-amber-600 mt-0.5">postponed</div>}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DayView({ entries, dayDate, setDayDate }) {
  const dates = useMemo(() => Array.from(new Set(entries.filter((e) => e.status !== "cancelled").map((e) => e.date))).sort(), [entries]);
  const date = dayDate || dates[0] || "";
  const rows = entries.filter((e) => e.date === date && e.status !== "cancelled")
    .sort((a, b) => (a.start + classKey(a)).localeCompare(b.start + classKey(b)));
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-slate-600 dark:text-slate-300">Exams on</span>
        <Select value={date} onValueChange={setDayDate}>
          <SelectTrigger className="w-56" data-testid="exam-day-select"><SelectValue placeholder="Pick a date" /></SelectTrigger>
          <SelectContent>{dates.map((d) => <SelectItem key={d} value={d}>{d} · {DAY_OF(d)}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden" data-testid="exam-day-table">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-900/60 text-left">
            <tr>{["Time", "Class", "Subject", "Room"].map((h) => <th key={h} className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500">{h}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {rows.length === 0 ? <tr><td colSpan={4} className="px-4 py-8 text-center text-sm text-slate-400">No exams on this date.</td></tr>
              : rows.map((e) => (
                <tr key={e.id} data-testid={`exam-day-row-${e.id}`}>
                  <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap">{e.start}–{e.end}</td>
                  <td className="px-4 py-2.5 font-medium text-slate-700 dark:text-slate-200">{classKey(e)}</td>
                  <td className="px-4 py-2.5 font-semibold text-slate-800 dark:text-slate-100">{e.subject}</td>
                  <td className="px-4 py-2.5 text-slate-500">{e.room || "—"}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EntryEditDialog({ exam, entry, onClose, onDone }) {
  const [date, setDate] = useState("");
  const [slotIndex, setSlotIndex] = useState(0);
  const [room, setRoom] = useState("");
  const [conflicts, setConflicts] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (entry) { setDate(entry.date); setSlotIndex(entry.slot_index); setRoom(entry.room || ""); setConflicts([]); }
  }, [entry]);

  if (!entry) return null;
  const dc = (exam.division_configs || []).find((c) => c.academic_unit_id === entry.academic_unit_id);
  const slots = (dc && dc.slots_per_day) || [];

  const saveRoom = async () => {
    setBusy(true);
    try { await api.put(`/exam-entries/${entry.id}`, { room }); toast.success("Saved"); onDone(); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const move = async (override) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/exam-entries/${entry.id}/move`, { date, slot_index: slotIndex, override });
      if (data.ok) { toast.success("Paper rescheduled"); onDone(); }
      else { setConflicts(data.conflicts || []); }
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={!!entry} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="exam-edit-dialog">
        <DialogHeader>
          <DialogTitle>{entry.subject} — {entry.class_name}{entry.section ? ` - ${entry.section}` : ""}</DialogTitle>
          <DialogDescription>Reschedule (postpone), or edit the room. Moving keeps the original date in the audit trail.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-1">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Date</label>
              <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} data-testid="exam-edit-date" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Slot</label>
              <Select value={String(slotIndex)} onValueChange={(v) => setSlotIndex(parseInt(v, 10))}>
                <SelectTrigger data-testid="exam-edit-slot"><SelectValue /></SelectTrigger>
                <SelectContent>{slots.map((s, i) => <SelectItem key={i} value={String(i)}>{s.start}–{s.end}{s.label ? ` (${s.label})` : ""}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-600">Room</label>
            <div className="flex gap-2">
              <Input value={room} onChange={(e) => setRoom(e.target.value)} placeholder="e.g. Hall A" data-testid="exam-edit-room" />
              <Button variant="outline" onClick={saveRoom} disabled={busy}>Save room</Button>
            </div>
          </div>
          {conflicts.length > 0 && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-500/10 p-3 space-y-1" data-testid="exam-edit-conflicts">
              <p className="text-xs font-semibold text-amber-700 dark:text-amber-300 flex items-center gap-1"><AlertTriangle size={13} /> Conflicts</p>
              {conflicts.map((c, i) => <p key={i} className="text-xs text-amber-700 dark:text-amber-300">• {c.message}</p>)}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
          {conflicts.length > 0
            ? <Button className="bg-amber-600 hover:bg-amber-700 text-white" onClick={() => move(true)} disabled={busy} data-testid="exam-move-override">Save anyway</Button>
            : <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" onClick={() => move(false)} disabled={busy} data-testid="exam-move-btn">Reschedule</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
