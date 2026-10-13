import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, FlaskConical, DoorOpen, Trash2, AlertTriangle, GripVertical, Layers, Sparkles, CheckCircle2, Send, EyeOff, ChevronDown, ChevronRight, ArrowRight, Scale } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../../components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "../../../components/ui/dialog";
import { DAY_SHORT } from "./days";

const NO_TEACHER = "__none__";

export default function GradeTimetable({ year, initialClass = "", initialSection = "" }) {
  const [classes, setClasses] = useState([]);
  const [className, setClassName] = useState(initialClass);
  const [section, setSection] = useState(initialSection);
  const [grid, setGrid] = useState(null);
  const [req, setReq] = useState(null);
  const [cell, setCell] = useState(null);      // {day, period_no, label, entry}
  const [form, setForm] = useState({ subject: "", teacher_id: NO_TEACHER, room: "" });
  const [conflict, setConflict] = useState(null); // {conflicts, onConfirm, title}
  const [drag, setDrag] = useState(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState("published");
  const [draftBatch, setDraftBatch] = useState(null);
  const [report, setReport] = useState(null);
  const [confirmAction, setConfirmAction] = useState(null);
  const [subDate, setSubDate] = useState("");  // date-aware substitution overlay ('' = weekly template)
  const [autoBalance, setAutoBalance] = useState(false);  // Phase 12 opt-in balancer (default off)

  useEffect(() => {
    api.get("/res/classes", { params: { limit: 500 } }).then((r) => {
      const items = (r.data.items || []).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
      setClasses(items);
      if (items.length) setClassName((c) => c || initialClass || items[0].name);
    }).catch((e) => toast.error(errText(e)));
  }, []);

  const sections = useMemo(() => req?.sections || [], [req]);
  useEffect(() => {
    if (!sections.length) return;
    // Honor an embedded preselected section (Section detail page) before falling back to the first.
    if (initialSection && sections.includes(initialSection) && section !== initialSection && !section) {
      setSection(initialSection);
    } else if (!sections.includes(section)) {
      setSection(initialSection && sections.includes(initialSection) ? initialSection : sections[0]);
    }
  }, [sections]); // eslint-disable-line

  const loadReq = useCallback(() => {
    if (!className || !year) return;
    api.get("/timetable/requirements", { params: { academic_year: year, class_name: className } })
      .then((r) => setReq(r.data)).catch((e) => toast.error(errText(e)));
  }, [className, year]);

  const loadGrid = useCallback(() => {
    if (!className || !section || !year) { setGrid(null); return; }
    const params = { academic_year: year, class_name: className, section, mode };
    if (subDate) params.date = subDate;
    api.get("/timetable/grid", { params })
      .then((r) => {
        setGrid(r.data);
        setDraftBatch(r.data.draft_batch || null);
        if (r.data.mode !== "draft" && mode === "draft") setMode("published");
        if (r.data.draft_batch?.summary) setReport(r.data.draft_batch.summary);
        else if (r.data.mode !== "draft") setReport(null);
      })
      .catch((e) => { toast.error(errText(e)); setGrid(null); });
  }, [className, section, year, mode, subDate]);

  useEffect(() => { loadReq(); }, [loadReq]);
  useEffect(() => { loadGrid(); }, [loadGrid]);

  const reload = () => { loadGrid(); };
  const entryAt = (day, pno) => grid?.entries.find((e) => e.day === day && e.period_no === pno);
  const teachers = req?.teachers || [];
  const subjects = (req?.items || []).map((i) => i.subject);
  const poolFor = (subject) => {
    const item = (req?.items || []).find((i) => i.subject === subject);
    return item ? item.teacher_ids : [];
  };
  const sectionTeacher = (subject) => {
    const item = (req?.items || []).find((i) => i.subject === subject);
    return item?.section_teachers?.[section] || "";
  };

  const openCell = (day, pno, label, entry) => {
    setCell({ day, period_no: pno, label, entry });
    if (entry) setForm({ subject: entry.subject, teacher_id: entry.teacher_id || NO_TEACHER, room: entry.room || "" });
    else setForm({ subject: subjects[0] || "", teacher_id: NO_TEACHER, room: "" });
  };

  // when subject changes in the editor, preselect its section teacher / first pool teacher
  const onSubjectChange = (subject) => {
    const st = sectionTeacher(subject);
    const pool = poolFor(subject);
    setForm((f) => ({ ...f, subject, teacher_id: st || (pool[0] || NO_TEACHER) }));
  };

  const draftMode = mode === "draft" && !!draftBatch;

  const doPlace = async (override) => {
    const body = {
      academic_year: year, class_name: className, section,
      day: cell.day, period_no: cell.period_no, subject: form.subject,
      teacher_id: form.teacher_id === NO_TEACHER ? "" : form.teacher_id,
      room: form.room, entry_id: cell.entry?.id || null, override,
      publish_state: draftMode ? "draft" : "published",
      batch_id: draftMode ? draftBatch.id : null,
    };
    setBusy(true);
    try {
      const { data } = await api.post("/timetable/place", body);
      if (!data.ok) {
        setConflict({
          title: `Conflicts placing ${form.subject}`,
          conflicts: data.conflicts,
          onConfirm: () => doPlace(true),
        });
        return;
      }
      setConflict(null); setCell(null); reload();
      toast.success(override ? "Saved with override" : "Period saved");
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const removeEntry = async () => {
    if (!cell?.entry) return;
    setBusy(true);
    try {
      await api.delete(`/timetable/entries/${cell.entry.id}`);
      setCell(null); reload(); toast.success("Period cleared");
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const doMove = async (entryId, toDay, toP, override) => {
    setBusy(true);
    try {
      const { data } = await api.post("/timetable/move", { entry_id: entryId, to_day: toDay, to_period_no: toP, override });
      if (!data.ok) {
        setConflict({
          title: data.swap ? "Conflicts swapping periods" : "Conflicts moving period",
          conflicts: data.conflicts,
          onConfirm: () => doMove(entryId, toDay, toP, true),
        });
        return;
      }
      setConflict(null); reload();
      toast.success(data.swap ? "Periods swapped" : "Period moved");
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const onDrop = (day, pno) => {
    if (!drag) return;
    if (drag.day === day && drag.period_no === pno) { setDrag(null); return; }
    doMove(drag.id, day, pno, false);
    setDrag(null);
  };

  const runGenerate = async () => {
    setConfirmAction(null);
    setBusy(true);
    try {
      const { data } = await api.post("/timetable/generate", { academic_year: year, class_name: className, auto_balance: autoBalance });
      setReport(data);
      setMode("draft");
      toast.success(`Draft generated — ${data.placed_count} periods placed`);
      loadGrid();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const onGenerateClick = () => {
    if (draftBatch) {
      setConfirmAction({
        title: "Replace existing draft?",
        body: `A draft already exists for ${className}. Regenerating wipes and rebuilds the draft only — published timetables are untouched.`,
        cta: "Regenerate draft", onConfirm: runGenerate,
      });
    } else runGenerate();
  };

  const approve = async () => {
    setBusy(true);
    try {
      await api.post("/timetable/approve", { batch_id: draftBatch.id });
      toast.success("Draft approved — ready to publish");
      loadGrid();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const publish = async () => {
    setConfirmAction(null);
    setBusy(true);
    try {
      const { data } = await api.post("/timetable/publish", { batch_id: draftBatch.id });
      toast.success(`Published — ${data.published} periods are now live to teachers, students & parents`);
      setMode("published"); setDraftBatch(null); setReport(null); loadGrid();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const unpublish = async () => {
    setConfirmAction(null);
    setBusy(true);
    try {
      await api.post("/timetable/unpublish", { class_name: className, academic_year: year });
      toast.success(`${className} pulled from students & parents`);
      loadGrid();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4" data-testid="tt-grade">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Layers size={15} className="text-slate-400" />
          <Select value={className} onValueChange={setClassName}>
            <SelectTrigger className="w-52" data-testid="grade-class-select"><SelectValue placeholder="Grade" /></SelectTrigger>
            <SelectContent>
              {classes.map((c) => <SelectItem key={c.id} value={c.name}>{c.name}{c.academic_unit_name ? ` · ${c.academic_unit_name}` : ""}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-1.5" data-testid="grade-section-tabs">
          {sections.map((s) => (
            <button key={s} onClick={() => setSection(s)} data-testid={`grade-section-${s}`}
              className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                section === s ? "bg-indigo-700 text-white border-indigo-700" : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-indigo-400"
              }`}>{s}</button>
          ))}
          {sections.length === 0 && <span className="text-sm text-slate-400">No sections yet.</span>}
        </div>
        <p className="text-xs text-slate-400 ml-auto">Click a cell to assign · drag a period to move/swap</p>
      </div>

      {initialClass && (
        <div className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/30 px-3 py-1 text-xs font-medium text-indigo-700 dark:text-indigo-300" data-testid="tt-context-chip">
          <Layers size={12} /> Viewing: {className || initialClass}{section ? ` · Section ${section}` : ""}
        </div>
      )}

      {/* Date-aware substitution overlay control */}
      <div className="flex flex-wrap items-center gap-2" data-testid="grade-date-overlay">
        <span className="text-xs font-medium text-slate-500">View a date:</span>
        <Input type="date" value={subDate} onChange={(e) => setSubDate(e.target.value)} className="w-40 h-8" data-testid="grade-date-picker" />
        {subDate ? (
          <button onClick={() => setSubDate("")} className="text-xs text-indigo-600 hover:underline" data-testid="grade-clear-date">Back to weekly template</button>
        ) : <span className="text-xs text-slate-400">showing weekly template — pick a date to see that day's substitutions</span>}
      </div>

      {/* Generate / lifecycle control bar */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/40 px-3 py-2">
        <Button size="sm" onClick={onGenerateClick} disabled={busy || !className} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="tt-generate-btn">
          <Sparkles size={14} className="mr-1" /> {draftBatch ? "Regenerate draft" : "Generate draft"}
        </Button>
        <label className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-300 cursor-pointer select-none" data-testid="tt-autobalance-label">
          <input type="checkbox" checked={autoBalance} onChange={(e) => setAutoBalance(e.target.checked)} data-testid="tt-autobalance-checkbox"
            className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
          Auto-balance flexible subjects
        </label>
        {draftBatch && (
          <div className="inline-flex rounded-full border border-slate-200 dark:border-slate-700 overflow-hidden" data-testid="tt-mode-toggle">
            <button onClick={() => setMode("published")} className={`px-3 py-1 text-xs font-medium ${!draftMode ? "bg-indigo-700 text-white" : "text-slate-500"}`} data-testid="tt-mode-published">Published</button>
            <button onClick={() => setMode("draft")} className={`px-3 py-1 text-xs font-medium ${draftMode ? "bg-amber-500 text-white" : "text-slate-500"}`} data-testid="tt-mode-draft">Draft</button>
          </div>
        )}
        {draftMode && (
          <>
            <span className="text-xs font-medium text-slate-500" data-testid="tt-draft-state">State: {draftBatch.state}</span>
            {draftBatch.state === "generated" && (
              <Button size="sm" variant="outline" onClick={approve} disabled={busy} data-testid="tt-approve-btn"><CheckCircle2 size={14} className="mr-1" /> Approve</Button>
            )}
            <Button size="sm" onClick={() => setConfirmAction({ title: "Publish this timetable?", body: `This replaces the live ${className} timetable and makes it visible to teachers, students and parents.`, cta: "Publish", onConfirm: publish })} disabled={busy} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="tt-publish-btn"><Send size={14} className="mr-1" /> Publish</Button>
          </>
        )}
        {!draftMode && grid && grid.entries.length > 0 && (
          <Button size="sm" variant="outline" onClick={() => setConfirmAction({ title: "Unpublish timetable?", body: `Students and parents will stop seeing the ${className} timetable. You can regenerate/publish again later.`, cta: "Unpublish", onConfirm: unpublish })} disabled={busy} className="ml-auto text-red-600 border-red-200 hover:bg-red-50" data-testid="tt-unpublish-btn"><EyeOff size={14} className="mr-1" /> Unpublish</Button>
        )}
      </div>

      {draftMode && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-500/10 dark:border-amber-500/40 px-4 py-2.5 text-sm text-amber-800 dark:text-amber-300 flex items-center gap-2" data-testid="tt-draft-banner">
          <AlertTriangle size={15} /> Draft — not visible to teachers, students or parents until you publish.
        </div>
      )}

      {draftMode && report && (
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-4 space-y-2" data-testid="tt-report-panel">
          <div className="flex items-center gap-4 text-sm">
            <span className="font-semibold text-slate-700 dark:text-slate-200">{report.placed_count} periods placed</span>
            {report.per_section_summary && Object.entries(report.per_section_summary).map(([s, v]) => (
              <span key={s} className="text-slate-500">Sec {s}: {v.placed}/{v.required}</span>
            ))}
          </div>
          {(report.unplaced || []).length > 0 ? (
            <ul className="space-y-1.5" data-testid="tt-unplaced-list">
              {report.unplaced.map((u, i) => <UnplacedRow key={i} u={u} idx={i} />)}
            </ul>
          ) : <p className="text-xs text-emerald-600 dark:text-emerald-400">Everything configured fit — no shortfalls.</p>}
          {(report.auto_adjustments || []).length > 0 && (
            <div className="mt-2 rounded-lg border border-blue-200 dark:border-blue-500/30 bg-blue-50/60 dark:bg-blue-500/10 p-3 space-y-1.5" data-testid="tt-autobalance-report">
              <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-blue-700 dark:text-blue-300">
                <Scale size={13} /> Auto-balance adjustments ({report.auto_adjustments.length})
              </p>
              <ul className="space-y-1" data-testid="tt-autobalance-list">
                {report.auto_adjustments.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-300" data-testid={`tt-adjustment-${i}`}>
                    <span className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                      a.type === "trim" ? "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300"
                      : a.type === "topup" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
                      : "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300"}`}>
                      {a.type === "relax_consecutive" ? "relax" : a.type}
                    </span>
                    <span><span className="font-medium">Sec {a.section}</span> — {a.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {!grid ? (
        <p className="text-sm text-slate-400 py-8 text-center" data-testid="grade-empty">Pick a grade and section.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm border-collapse" data-testid="grade-matrix">
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-900/60">
                <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 w-28 border-b border-slate-200 dark:border-slate-800">Period</th>
                {grid.config.working_days.map((d) => (
                  <th key={d} className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 border-b border-l border-slate-200 dark:border-slate-800">{DAY_SHORT[d]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.config.periods.map((p, idx) => {
                const pno = idx + 1;
                if (p.is_break) {
                  return (
                    <tr key={pno} className="bg-slate-100/70 dark:bg-slate-800/40">
                      <td className="px-3 py-1.5 text-xs text-slate-400 font-medium border-b border-slate-200 dark:border-slate-800">{p.label}<span className="block text-[10px]">{p.start}–{p.end}</span></td>
                      <td colSpan={grid.config.working_days.length} className="px-3 py-1.5 text-center text-[11px] uppercase tracking-widest text-slate-400 border-b border-l border-slate-200 dark:border-slate-800">{p.label}</td>
                    </tr>
                  );
                }
                return (
                  <tr key={pno}>
                    <td className="px-3 py-2 text-xs text-slate-500 font-medium border-b border-slate-200 dark:border-slate-800 align-top">
                      {p.label}<span className="block text-[10px] text-slate-400">{p.start}–{p.end}</span>
                    </td>
                    {grid.config.working_days.map((d) => {
                      const e = entryAt(d, pno);
                      const flagged = e && (e.conflict_flags || []).length > 0;
                      return (
                        <td key={d} className="border-b border-l border-slate-200 dark:border-slate-800 p-1 align-top"
                          onDragOver={(ev) => ev.preventDefault()} onDrop={() => onDrop(d, pno)}>
                          <button
                            draggable={!!e}
                            onDragStart={() => e && setDrag(e)}
                            onClick={() => openCell(d, pno, p.label, e || null)}
                            data-testid={`grade-cell-${d}-${pno}`}
                            className={`w-full min-h-[54px] rounded-md px-2 py-1.5 text-left transition-colors relative ${
                              e ? (flagged ? "bg-amber-50 dark:bg-amber-500/10 ring-1 ring-amber-400 hover:bg-amber-100"
                                           : "bg-indigo-50 dark:bg-indigo-500/10 hover:bg-indigo-100 dark:hover:bg-indigo-500/20")
                                : "hover:bg-slate-50 dark:hover:bg-slate-800/60 group"}`}
                          >
                            {e ? (
                              <>
                                {flagged && <AlertTriangle size={12} className="absolute top-1 right-1 text-amber-500" data-testid={`grade-flag-${d}-${pno}`} />}
                                <span className="block text-[13px] font-semibold text-slate-800 dark:text-slate-200 leading-tight pr-3">
                                  {e.subject}{e.type === "lab" && <FlaskConical size={11} className="inline ml-1 text-amber-500" />}
                                </span>
                                {e.substitution ? (
                                  <>
                                    <span className="block text-[11px] text-slate-400 line-through truncate" data-testid={`grade-orig-${d}-${pno}`}>{e.substitution.original_teacher_name || e.teacher_name}</span>
                                    <span className="block text-[11px] font-medium text-violet-600 dark:text-violet-400 truncate" data-testid={`grade-sub-${d}-${pno}`}>→ {e.substitution.substitute_name}</span>
                                    <span className="inline-flex items-center gap-0.5 mt-0.5 text-[9px] font-semibold uppercase tracking-wide text-violet-600 bg-violet-100 dark:bg-violet-500/15 rounded px-1 py-0.5">Substitution</span>
                                  </>
                                ) : (
                                  <span className="block text-[11px] text-slate-500 truncate">{e.teacher_name || <span className="italic text-slate-400">no teacher</span>}</span>
                                )}
                                {e.room && <span className="text-[10px] text-slate-400 inline-flex items-center gap-0.5"><DoorOpen size={10} /> {e.room}</span>}
                                <GripVertical size={11} className="absolute bottom-1 right-1 text-slate-300 dark:text-slate-600" />
                              </>
                            ) : (
                              <span className="flex items-center justify-center h-full text-slate-300 dark:text-slate-600 group-hover:text-indigo-400"><Plus size={15} /></span>
                            )}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Cell editor */}
      <Dialog open={!!cell} onOpenChange={(o) => !o && setCell(null)}>
        <DialogContent className="sm:max-w-md" data-testid="grade-cell-dialog">
          <DialogHeader>
            <DialogTitle>{className} {section} · {cell?.label} · {cell && DAY_SHORT[cell.day]}</DialogTitle>
            <DialogDescription>Assign a subject and teacher for this slot.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-1">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Subject</label>
              <Select value={form.subject} onValueChange={onSubjectChange}>
                <SelectTrigger data-testid="grade-subject-select"><SelectValue placeholder="Pick a subject" /></SelectTrigger>
                <SelectContent>{subjects.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Teacher</label>
              <Select value={form.teacher_id} onValueChange={(v) => setForm((f) => ({ ...f, teacher_id: v }))}>
                <SelectTrigger data-testid="grade-teacher-select"><SelectValue placeholder="Pick a teacher" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_TEACHER}><span className="text-slate-400">No teacher</span></SelectItem>
                  {(() => {
                    const pool = poolFor(form.subject);
                    const poolSet = new Set(pool);
                    const ordered = [...teachers].sort((a, b) => (poolSet.has(b.id) ? 1 : 0) - (poolSet.has(a.id) ? 1 : 0));
                    return ordered.map((t) => (
                      <SelectItem key={t.id} value={t.id}>{t.name}{poolSet.has(t.id) ? " · pool" : " · other"}</SelectItem>
                    ));
                  })()}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Room (optional)</label>
              <Input value={form.room} onChange={(e) => setForm((f) => ({ ...f, room: e.target.value }))} placeholder="e.g. 101" data-testid="grade-room-input" />
            </div>
          </div>
          <DialogFooter className="gap-2">
            {cell?.entry && <Button variant="outline" onClick={removeEntry} disabled={busy} data-testid="grade-remove-btn" className="mr-auto text-red-600 border-red-200 hover:bg-red-50"><Trash2 size={14} className="mr-1" /> Clear</Button>}
            <Button variant="outline" onClick={() => setCell(null)} data-testid="grade-cancel-btn">Cancel</Button>
            <Button onClick={() => doPlace(false)} disabled={busy || !form.subject} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="grade-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Conflict dialog */}
      <Dialog open={!!conflict} onOpenChange={(o) => !o && setConflict(null)}>
        <DialogContent className="sm:max-w-md" data-testid="grade-conflict-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-amber-600"><AlertTriangle size={18} /> {conflict?.title}</DialogTitle>
            <DialogDescription>Review the conflicts below. You can cancel, or save anyway (the change will be flagged).</DialogDescription>
          </DialogHeader>
          <ul className="space-y-2 py-1" data-testid="grade-conflict-list">
            {(conflict?.conflicts || []).map((c, i) => (
              <li key={i} className={`flex items-start gap-2 text-sm rounded-md px-3 py-2 ${c.severity === "hard" ? "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300" : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"}`}>
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <span><span className="font-semibold capitalize">{c.type}:</span> {c.message}</span>
              </li>
            ))}
          </ul>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setConflict(null)} data-testid="grade-conflict-cancel">Cancel</Button>
            <Button onClick={() => conflict?.onConfirm?.()} disabled={busy} className="bg-amber-600 hover:bg-amber-700 text-white" data-testid="grade-conflict-save-anyway">Save anyway</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {/* Generic confirm dialog (generate-replace / publish / unpublish) */}
      <Dialog open={!!confirmAction} onOpenChange={(o) => !o && setConfirmAction(null)}>
        <DialogContent className="sm:max-w-md" data-testid="tt-confirm-dialog">
          <DialogHeader>
            <DialogTitle>{confirmAction?.title}</DialogTitle>
            <DialogDescription>{confirmAction?.body}</DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setConfirmAction(null)} data-testid="tt-confirm-cancel">Cancel</Button>
            <Button onClick={() => confirmAction?.onConfirm?.()} disabled={busy} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="tt-confirm-ok">{confirmAction?.cta || "Confirm"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}


const CAUSE = {
  no_teacher: { label: "No teacher", cls: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400" },
  pool_exhausted: { label: "Teachers busy", cls: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400" },
  slots_full: { label: "Week full", cls: "bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-400" },
  consecutive_unplaceable: { label: "Block won't fit", cls: "bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-400" },
  ct_first_period_shortfall: { label: "Period 1 rule", cls: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400" },
};

function UnplacedRow({ u, idx }) {
  const [open, setOpen] = useState(false);
  const cause = CAUSE[u.cause] || { label: u.cause || "Shortfall", cls: "bg-slate-100 text-slate-600 dark:bg-slate-800" };
  const sugs = u.suggestions || [];
  return (
    <li className="rounded-lg border border-amber-200 dark:border-amber-500/30 bg-amber-50/50 dark:bg-amber-500/5" data-testid={`tt-unplaced-${idx}`}>
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-start gap-2 px-3 py-2 text-left" data-testid={`tt-unplaced-toggle-${idx}`}>
        {open ? <ChevronDown size={13} className="mt-0.5 text-amber-600 shrink-0" /> : <ChevronRight size={13} className="mt-0.5 text-amber-600 shrink-0" />}
        <span className={`text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded-full shrink-0 ${cause.cls}`} data-testid={`tt-cause-${u.cause}`}>{cause.label}</span>
        <span className="text-xs text-amber-800 dark:text-amber-300">Sec {u.section} · {u.reason}</span>
      </button>
      {open && sugs.length > 0 && (
        <div className="px-3 pb-2.5 pl-8 flex flex-wrap gap-2" data-testid={`tt-unplaced-fixes-${idx}`}>
          {sugs.map((s, i) => (
            <Link key={i} to={s.href} data-testid={`tt-fix-${idx}-${i}`}
              className="inline-flex items-center gap-1 text-xs font-medium rounded-md border border-indigo-300 dark:border-indigo-500/40 text-indigo-700 dark:text-indigo-300 px-2.5 py-1 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition-colors">
              {s.label} <ArrowRight size={11} />
            </Link>
          ))}
        </div>
      )}
    </li>
  );
}
