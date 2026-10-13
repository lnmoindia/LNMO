import { useCallback, useEffect, useState } from "react";
import { School, Trophy, Plus, Trash2, Crown, Medal, Printer, GraduationCap } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { printReportCard } from "../../lib/printDoc";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";

export default function TeacherMyClass() {
  const [homerooms, setHomerooms] = useState(null);
  const [sectionId, setSectionId] = useState("");
  const [detail, setDetail] = useState(null);
  const [achOpen, setAchOpen] = useState(false);
  const [ach, setAch] = useState({ student_id: "", title: "", description: "", date: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/teacher/my-class").then((r) => {
      setHomerooms(r.data.homerooms);
      if (r.data.homerooms.length) setSectionId(r.data.homerooms[0].id);
    }).catch(() => setHomerooms([]));
  }, []);

  const load = useCallback(() => {
    if (!sectionId) { setDetail(null); return; }
    api.get(`/teacher/my-class/${sectionId}`).then((r) => setDetail(r.data)).catch((e) => toast.error(errText(e)));
  }, [sectionId]);

  useEffect(() => { load(); }, [load]);

  const openReport = async (studentId) => {
    try {
      const { data } = await api.get(`/students/${studentId}/report-card`);
      printReportCard(data);
    } catch (e) {
      toast.error(errText(e));
    }
  };

  const addAchievement = async () => {
    setSaving(true);
    try {
      await api.post("/teacher/achievements", ach);
      toast.success("Achievement added");
      setAchOpen(false);
      setAch({ student_id: "", title: "", description: "", date: "" });
      load();
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setSaving(false);
    }
  };

  const removeAchievement = async (id) => {
    if (!window.confirm("Delete this achievement? This cannot be undone.")) return;
    try {
      await api.delete(`/teacher/achievements/${id}`);
      toast.success("Achievement removed");
      load();
    } catch (e) {
      toast.error(errText(e));
    }
  };

  if (homerooms === null) return <p className="text-sm text-slate-400 py-10 text-center">Loading…</p>;

  if (homerooms.length === 0) {
    return (
      <div className="py-16 text-center space-y-2" data-testid="myclass-empty">
        <School size={28} className="mx-auto text-slate-300" />
        <p className="font-heading font-semibold text-slate-700 dark:text-slate-300">You are not a class teacher yet</p>
        <p className="text-sm text-slate-400 max-w-md mx-auto">When your admin assigns you as the class teacher of a section (Class Hub → class page → Leadership), your homeroom will appear here.</p>
      </div>
    );
  }

  const sec = detail?.section;
  const studentOpts = (detail?.students || []).map((s) => ({
    value: s.id,
    label: `${s.first_name || ""} ${s.last_name || ""}`.trim() + (s.admission_no ? ` · ${s.admission_no}` : ""),
  }));

  return (
    <div className="space-y-6" data-testid="teacher-myclass">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">Homeroom</p>
          <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50">My Class</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">You are the class teacher — roster, attendance health, achievements and report cards.</p>
        </div>
        {homerooms.length > 1 && (
          <Select value={sectionId} onValueChange={setSectionId}>
            <SelectTrigger className="w-56" data-testid="myclass-section-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              {homerooms.map((h) => <SelectItem key={h.id} value={h.id}>{h.class_name} · Section {h.name}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
      </div>

      {detail && (
        <>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 flex flex-wrap items-center gap-x-8 gap-y-2" data-testid="myclass-header">
            <div>
              <p className="text-xs text-slate-400">Section</p>
              <p className="font-heading font-bold text-slate-900 dark:text-slate-50">{sec.class_name} · {sec.name}{sec.room ? ` · ${sec.room}` : ""}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400 flex items-center gap-1"><Crown size={11} className="text-amber-500" /> Class leader</p>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300">{sec.class_leader || "Not set"}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400 flex items-center gap-1"><Medal size={11} /> Second leader</p>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300">{sec.second_leader || "Not set"}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400 flex items-center gap-1"><GraduationCap size={11} /> Students</p>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300">{detail.students.length}</p>
            </div>
            <Button size="sm" variant="outline" className="ml-auto" onClick={() => { setAch({ student_id: "", title: "", description: "", date: "" }); setAchOpen(true); }} data-testid="myclass-add-ach-btn">
              <Trophy size={14} className="mr-1" /> Add achievement
            </Button>
          </div>

          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden" data-testid="myclass-roster">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-900/60 text-left">
                <tr>
                  {["Student", "Adm. No.", "Attendance", "Achievements", ""].map((h) => (
                    <th key={h} className="px-4 py-2 text-xs font-semibold uppercase tracking-wider text-slate-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {detail.students.length === 0 ? (
                  <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-400">No students in this section yet.</td></tr>
                ) : detail.students.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40" data-testid={`myclass-student-${s.id}`}>
                    <td className="px-4 py-2.5 text-slate-700 dark:text-slate-200 font-medium">
                      {`${s.first_name || ""} ${s.last_name || ""}`.trim()}
                      {sec.class_leader_id === s.id && <span className="ml-2 inline-flex items-center gap-1 text-[11px] font-medium text-amber-600"><Crown size={11} /> Leader</span>}
                      {sec.second_leader_id === s.id && <span className="ml-2 inline-flex items-center gap-1 text-[11px] font-medium text-slate-500"><Medal size={11} /> 2nd</span>}
                    </td>
                    <td className="px-4 py-2.5 text-slate-500">{s.admission_no || "—"}</td>
                    <td className="px-4 py-2.5">
                      {s.attendance_pct === null ? <span className="text-slate-300 dark:text-slate-600">—</span> : (
                        <span className={`font-medium ${s.attendance_pct >= 90 ? "text-emerald-600" : s.attendance_pct >= 75 ? "text-amber-600" : "text-red-600"}`}>
                          {s.attendance_pct}% <span className="text-xs text-slate-400 font-normal">({s.attendance_present}/{s.attendance_total})</span>
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-slate-500">
                      {s.achievements_count ? <span className="inline-flex items-center gap-1 text-amber-600 font-medium"><Trophy size={12} /> {s.achievements_count}</span> : <span className="text-slate-300 dark:text-slate-600">—</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right whitespace-nowrap">
                      <button onClick={() => openReport(s.id)} title="Print report card" data-testid={`myclass-report-${s.id}`}
                        className="text-slate-400 hover:text-indigo-600 transition-colors mr-2"><Printer size={15} /></button>
                      <button onClick={() => { setAch({ student_id: s.id, title: "", description: "", date: "" }); setAchOpen(true); }} title="Add achievement" data-testid={`myclass-ach-${s.id}`}
                        className="text-slate-400 hover:text-amber-600 transition-colors"><Plus size={15} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden" data-testid="myclass-achievements">
            <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
              <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Trophy size={16} className="text-amber-500" /> Achievements</h2>
            </div>
            {detail.achievements.length === 0 ? (
              <p className="px-5 py-6 text-sm text-slate-400">No achievements yet — celebrate your students with “Add achievement”.</p>
            ) : (
              <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {detail.achievements.map((a) => (
                  <li key={a.id} className="px-5 py-3 flex items-start justify-between gap-4" data-testid={`myclass-ach-row-${a.id}`}>
                    <div>
                      <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{a.student_name} — {a.title}</p>
                      {a.description && <p className="text-xs text-slate-500 mt-0.5">{a.description}</p>}
                      {a.awarded_by && <p className="text-[11px] text-slate-400 mt-0.5">Awarded by {a.awarded_by}</p>}
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className="text-xs text-slate-400">{a.date || ""}</span>
                      <button onClick={() => removeAchievement(a.id)} data-testid={`myclass-ach-del-${a.id}`}
                        className="text-slate-300 hover:text-red-500 transition-colors"><Trash2 size={14} /></button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}

      <Dialog open={achOpen} onOpenChange={setAchOpen}>
        <DialogContent className="sm:max-w-md" data-testid="myclass-ach-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Trophy size={17} className="text-amber-500" /> Add achievement</DialogTitle>
            <DialogDescription>Record an award or recognition for a student in your homeroom.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-1">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Student <span className="text-red-500">*</span></label>
              <Select value={ach.student_id} onValueChange={(v) => setAch((a) => ({ ...a, student_id: v }))}>
                <SelectTrigger data-testid="myclass-ach-student"><SelectValue placeholder="Pick a student" /></SelectTrigger>
                <SelectContent>{studentOpts.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Title <span className="text-red-500">*</span></label>
              <Input value={ach.title} onChange={(e) => setAch((a) => ({ ...a, title: e.target.value }))} placeholder="e.g. 1st place — Elocution" data-testid="myclass-ach-title" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Details</label>
              <Input value={ach.description} onChange={(e) => setAch((a) => ({ ...a, description: e.target.value }))} placeholder="Optional description" data-testid="myclass-ach-desc" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Date</label>
              <Input type="date" value={ach.date} onChange={(e) => setAch((a) => ({ ...a, date: e.target.value }))} data-testid="myclass-ach-date" />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={() => setAchOpen(false)} data-testid="myclass-ach-cancel">Cancel</Button>
              <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" disabled={!ach.student_id || !ach.title.trim() || saving} onClick={addAchievement} data-testid="myclass-ach-save">
                {saving ? "Saving…" : "Save achievement"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
