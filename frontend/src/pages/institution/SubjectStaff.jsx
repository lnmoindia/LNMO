import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Save, BookOpen, AlertTriangle, CheckCircle2, Layers, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Switch } from "../../components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../components/ui/dialog";

const NONE = "__none__";

/** Consolidated per-GRADE Subjects & Teachers surface with PER-SECTION offerings.
 *  A subject row shows a teacher dropdown for the sections that OFFER it, and a "+ offer" affordance
 *  for sections that don't. Teacher/period edits go to PUT subject-staff; offering add/remove hit the
 *  dedicated offering endpoints (teacher_assignments + subject_requirements mirrors kept consistent). */
export default function SubjectStaff({ className, year, onDirtyChange, initialSection = "all", lockSection = false }) {
  const [payload, setPayload] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [focusSec, setFocusSec] = useState(initialSection);
  const [addOpen, setAddOpen] = useState(false);
  const [addForm, setAddForm] = useState({ subject: "", section: "" });
  const baseline = useRef("");

  const load = useCallback(() => {
    if (!className || !year) return;
    setLoading(true);
    api.get(`/class-hub/${encodeURIComponent(className)}/subject-staff`, { params: { academic_year: year } })
      .then((r) => {
        setPayload(r.data);
        const rs = r.data.items.map((i) => ({ ...i, section_teachers: { ...i.section_teachers } }));
        setRows(rs);
        baseline.current = JSON.stringify(rs);
        setDirty(false);
      })
      .catch((e) => toast.error(errText(e)))
      .finally(() => setLoading(false));
  }, [className, year]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);

  const allSections = payload?.sections || [];
  const teachers = payload?.teachers || [];
  const catalog = payload?.catalog || [];
  const visSections = focusSec === "all" ? allSections : allSections.filter((s) => s === focusSec);
  const teacherName = (id) => teachers.find((t) => t.id === id)?.name || "?";

  const markDirty = (next) => setDirty(JSON.stringify(next) !== baseline.current);
  const setRow = (subject, patch) => setRows((rs) => { const next = rs.map((r) => (r.subject === subject ? { ...r, ...patch } : r)); markDirty(next); return next; });
  const setSectionTeacher = (subject, section, tid) => setRows((rs) => {
    const next = rs.map((r) => {
      if (r.subject !== subject) return r;
      const section_teachers = { ...r.section_teachers };
      if (tid === NONE) delete section_teachers[section]; else section_teachers[section] = tid;
      return { ...r, section_teachers };
    });
    markDirty(next);
    return next;
  });

  const unassignedCount = useMemo(
    () => rows.reduce((n, r) => n + (r.offered_sections || []).filter((s) => !r.section_teachers[s]).length, 0),
    [rows],
  );

  const shownRows = focusSec === "all" ? rows : rows.filter((r) => (r.offered_sections || []).includes(focusSec));

  const save = async () => {
    const items = rows.map((r) => ({
      subject: r.subject,
      section_teachers: Object.fromEntries((r.offered_sections || []).map((s) => [s, r.section_teachers[s] || ""])),
      periods_per_week: parseInt(r.periods_per_week, 10) || 0,
      consecutive_periods: parseInt(r.consecutive_periods, 10) || 1,
      must_be_consecutive: (parseInt(r.consecutive_periods, 10) || 1) > 1 ? !!r.must_be_consecutive : false,
      flexible: !!r.flexible,
      min_periods: r.min_periods === "" || r.min_periods == null ? 1 : parseInt(r.min_periods, 10),
      max_periods: r.max_periods === "" || r.max_periods == null ? (parseInt(r.periods_per_week, 10) || 0) + 2 : parseInt(r.max_periods, 10),
    }));
    setSaving(true);
    try {
      const { data } = await api.put(`/class-hub/${encodeURIComponent(className)}/subject-staff`, { academic_year: year, items });
      setPayload(data);
      const rs = data.items.map((i) => ({ ...i, section_teachers: { ...i.section_teachers } }));
      setRows(rs); baseline.current = JSON.stringify(rs); setDirty(false);
      toast.success(`Saved subjects & teachers for ${className}`);
    } catch (e) { toast.error(errText(e)); } finally { setSaving(false); }
  };

  const offerSubject = async (subject, section) => {
    try {
      await api.post(`/class-hub/${encodeURIComponent(className)}/offerings`, { subject, section });
      toast.success(`${subject} added to section ${section}`);
      load();
    } catch (e) { toast.error(errText(e)); }
  };

  const removeOffering = async (subject, section) => {
    if (!window.confirm(`Remove ${subject} from section ${section}? This clears its teacher for that section.`)) return;
    try {
      const { data } = await api.delete(`/class-hub/${encodeURIComponent(className)}/offerings`, { params: { subject, section } });
      const c = data.cascade || {};
      toast.success(`${subject} removed from ${section}` + (c.requirement_removed ? " — no sections left offering it, requirement cleared" : ""));
      setPayload(data);
      const rs = data.items.map((i) => ({ ...i, section_teachers: { ...i.section_teachers } }));
      setRows(rs); baseline.current = JSON.stringify(rs); setDirty(false);
    } catch (e) { toast.error(errText(e)); }
  };

  const doAdd = async () => {
    if (!addForm.subject || !addForm.section) return;
    await offerSubject(addForm.subject, addForm.section);
    setAddOpen(false); setAddForm({ subject: "", section: "" });
  };

  return (
    <div className="space-y-4" data-testid="subject-staff">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-500 dark:text-slate-400 flex items-center gap-2">
          <Layers size={14} className="text-slate-400" />
          Offerings are per section — a subject can differ across A/B/C. Assign a teacher per section and set weekly periods.
        </p>
        <div className="flex items-center gap-3">
          <span data-testid="staff-unassigned"
            className={`inline-flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-full ${
              unassignedCount === 0 ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400"
                : "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400"
            }`}>
            {unassignedCount === 0 ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
            {unassignedCount === 0 ? "All offered sections staffed" : `${unassignedCount} offered slot(s) unassigned`}
          </span>
          <Button onClick={save} disabled={saving || !dirty} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="staff-save-btn">
            <Save size={14} className="mr-1" /> {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </div>

      {/* section filter + add subject */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-1.5" data-testid="staff-section-filter">
          {(lockSection ? allSections.filter((s) => s === initialSection) : ["all", ...allSections]).map((s) => (
            <button key={s} onClick={() => setFocusSec(s)} data-testid={`staff-filter-${s}`}
              className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                focusSec === s ? "bg-indigo-700 text-white border-indigo-700" : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-indigo-400"
              }`}>
              {s === "all" ? "All sections" : `Section ${s}`}
            </button>
          ))}
        </div>
        <Button variant="outline" size="sm" onClick={() => { setAddForm({ subject: "", section: focusSec === "all" ? "" : focusSec }); setAddOpen(true); }} data-testid="staff-add-subject-btn">
          <Plus size={14} className="mr-1" /> Add subject to a section
        </Button>
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-x-auto">
        <table className="w-full text-sm min-w-[640px]">
          <thead className="bg-slate-50 dark:bg-slate-900/60 text-left">
            <tr>
              <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500">Subject</th>
              {visSections.map((s) => (
                <th key={s} className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500">Sec {s}</th>
              ))}
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500">Periods/wk</th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500">Consec.</th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500">Must</th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500" title="Auto-balance may trim or top up flexible subjects between min and max">Flexible</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {loading ? (
              <tr><td colSpan={visSections.length + 5} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>
            ) : shownRows.length === 0 ? (
              <tr><td colSpan={visSections.length + 5} className="px-4 py-8 text-center text-slate-400" data-testid="staff-empty">
                No subjects offered{focusSec !== "all" ? ` to section ${focusSec}` : ` for ${className}`} yet. Use “Add subject to a section”.
              </td></tr>
            ) : shownRows.map((r) => {
              const cons = parseInt(r.consecutive_periods, 10) || 1;
              const offered = new Set(r.offered_sections || []);
              return (
                <tr key={r.subject} className="hover:bg-slate-50 dark:hover:bg-slate-800/40" data-testid={`staff-row-${r.subject}`}>
                  <td className="px-4 py-2.5 font-medium text-slate-800 dark:text-slate-200">
                    <span className="flex items-center gap-2"><BookOpen size={14} className="text-indigo-500 shrink-0" /> {r.subject}</span>
                  </td>
                  {visSections.map((sec) => (
                    <td key={sec} className="px-3 py-2.5">
                      {offered.has(sec) ? (
                        <div className="flex items-center gap-1">
                          <Select value={r.section_teachers[sec] || NONE} onValueChange={(v) => setSectionTeacher(r.subject, sec, v)}>
                            <SelectTrigger className="w-36 h-8" data-testid={`staff-teacher-${r.subject}-${sec}`}>
                              <SelectValue>{r.section_teachers[sec] ? teacherName(r.section_teachers[sec]) : <span className="text-slate-400">Unassigned</span>}</SelectValue>
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value={NONE}><span className="text-slate-400">Unassigned</span></SelectItem>
                              {teachers.map((t) => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}
                            </SelectContent>
                          </Select>
                          <button onClick={() => removeOffering(r.subject, sec)} title={`Remove ${r.subject} from ${sec}`}
                            data-testid={`staff-remove-${r.subject}-${sec}`} className="text-slate-300 hover:text-red-600 transition-colors shrink-0"><Trash2 size={14} /></button>
                        </div>
                      ) : (
                        <button onClick={() => offerSubject(r.subject, sec)} data-testid={`staff-offer-${r.subject}-${sec}`}
                          className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-indigo-600 border border-dashed border-slate-200 dark:border-slate-700 rounded-md px-2 py-1.5 transition-colors">
                          <Plus size={12} /> offer
                        </button>
                      )}
                    </td>
                  ))}
                  <td className="px-3 py-2.5">
                    <Input type="number" min={0} value={r.periods_per_week || ""} placeholder="0"
                      onChange={(e) => setRow(r.subject, { periods_per_week: e.target.value })}
                      className="w-16 h-8" data-testid={`staff-ppw-${r.subject}`} />
                  </td>
                  <td className="px-3 py-2.5">
                    <Select value={String(cons)} onValueChange={(v) => setRow(r.subject, { consecutive_periods: v, must_be_consecutive: v === "1" ? false : r.must_be_consecutive })}>
                      <SelectTrigger className="w-14 h-8" data-testid={`staff-cons-${r.subject}`}><SelectValue /></SelectTrigger>
                      <SelectContent>{[1, 2, 3].map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}</SelectContent>
                    </Select>
                  </td>
                  <td className="px-3 py-2.5">
                    <Switch checked={cons > 1 && !!r.must_be_consecutive} disabled={cons <= 1}
                      onCheckedChange={(v) => setRow(r.subject, { must_be_consecutive: v })} data-testid={`staff-must-${r.subject}`} />
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <Switch checked={!!r.flexible} onCheckedChange={(v) => setRow(r.subject, { flexible: v })} data-testid={`staff-flexible-${r.subject}`} />
                      {r.flexible && (
                        <span className="flex items-center gap-1 text-xs text-slate-500">
                          <Input type="number" min={0} value={r.min_periods ?? ""} placeholder="min"
                            onChange={(e) => setRow(r.subject, { min_periods: e.target.value })}
                            className="w-12 h-8" data-testid={`staff-min-${r.subject}`} />
                          <span>–</span>
                          <Input type="number" min={0} value={r.max_periods ?? ""} placeholder="max"
                            onChange={(e) => setRow(r.subject, { max_periods: e.target.value })}
                            className="w-12 h-8" data-testid={`staff-max-${r.subject}`} />
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-400">
        Teacher picks write to the class's teacher assignments and feed the timetable instantly. Removing an offering clears that
        section's teacher for the subject; if no section offers it anymore, its timetable requirement is cleared too.
      </p>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="sm:max-w-md" data-testid="staff-add-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><BookOpen size={17} className="text-indigo-600" /> Add subject to a section</DialogTitle>
            <DialogDescription>Offer a catalog subject to one section of {className}. Sections can differ.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-1">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Subject <span className="text-red-500">*</span></label>
              <Select value={addForm.subject} onValueChange={(v) => setAddForm((f) => ({ ...f, subject: v }))}>
                <SelectTrigger data-testid="staff-add-subject-select"><SelectValue placeholder="Pick a subject" /></SelectTrigger>
                <SelectContent>{catalog.map((c) => <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Section <span className="text-red-500">*</span></label>
              <Select value={addForm.section} onValueChange={(v) => setAddForm((f) => ({ ...f, section: v }))}>
                <SelectTrigger data-testid="staff-add-section-select"><SelectValue placeholder="Pick a section" /></SelectTrigger>
                <SelectContent>{allSections.map((s) => <SelectItem key={s} value={s}>Section {s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={() => setAddOpen(false)} data-testid="staff-add-cancel">Cancel</Button>
              <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" disabled={!addForm.subject || !addForm.section} onClick={doAdd} data-testid="staff-add-confirm">Add offering</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
