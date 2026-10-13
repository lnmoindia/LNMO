import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, CheckCircle2, History } from "lucide-react";
import api, { errText } from "../lib/api";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "../components/ui/alert-dialog";

export default function MarksEntryPage({ teacherMode = false }) {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [rows, setRows] = useState({});
  const [saving, setSaving] = useState(false);
  const [confirmPublish, setConfirmPublish] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState(null);
  const inputRefs = useRef({});

  const load = () => {
    api.get(`/assessments/${id}/marks`).then((r) => {
      setData(r.data);
      const m = {};
      r.data.students.forEach((s) => {
        const mark = r.data.marks.find((x) => x.student_id === s.id);
        m[s.id] = { score: mark?.score ?? "", status: mark?.status || "present" };
      });
      setRows(m);
    }).catch((e) => toast.error(errText(e)));
  };

  useEffect(load, [id]); // eslint-disable-line

  if (!data) return <div className="space-y-3">{[...Array(6)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>;

  const { assessment, students } = data;
  const maxMarks = parseFloat(assessment.max_marks) || 100;
  const published = assessment.status === "published";
  const canCorrect = !!data.can_correct;
  const editable = !published || canCorrect;

  const openHistory = async () => {
    setHistoryOpen(true);
    try { const { data: h } = await api.get(`/assessments/${id}/history`); setHistory(h.history || []); }
    catch (e) { toast.error(errText(e)); }
  };

  const setRow = (sid, patch) => setRows((r) => ({ ...r, [sid]: { ...r[sid], ...patch } }));
  const invalid = (sid) => {
    const v = rows[sid]?.score;
    if (v === "" || v === null || rows[sid]?.status !== "present") return false;
    const n = parseFloat(v);
    return Number.isNaN(n) || n < 0 || n > maxMarks;
  };
  const hasInvalid = students.some((s) => invalid(s.id));

  const onKeyDown = (e, idx) => {
    if (e.key === "Enter" || e.key === "ArrowDown") {
      e.preventDefault();
      inputRefs.current[students[Math.min(idx + 1, students.length - 1)]?.id]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      inputRefs.current[students[Math.max(idx - 1, 0)]?.id]?.focus();
    }
  };

  const save = async () => {
    if (hasInvalid) { toast.error(`Scores must be between 0 and ${maxMarks}`); return; }
    setSaving(true);
    try {
      const entries = students.map((s) => ({ student_id: s.id, score: rows[s.id]?.score, status: rows[s.id]?.status }));
      await api.post(`/assessments/${id}/marks`, { entries });
      toast.success(published ? "Correction saved" : "Marks saved");
      load();
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setSaving(false);
    }
  };

  const togglePublish = async (publish) => {
    try {
      await api.post(`/assessments/${id}/publish`, { publish });
      toast.success(publish ? "Results published" : "Assessment unpublished");
      setConfirmPublish(false);
      load();
    } catch (e) {
      toast.error(errText(e));
    }
  };

  return (
    <div className="space-y-6" data-testid="marks-entry-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link to={teacherMode ? "/teacher/marks" : "/app/assessments"} className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-indigo-600 mb-2 transition-colors" data-testid="back-to-assessments-link">
            <ArrowLeft size={13} /> {teacherMode ? "My assessments" : "Assessments"}
          </Link>
          <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">{assessment.name}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {[assessment.subject, assessment.class_name, assessment.section].filter(Boolean).join(" · ")} — max {maxMarks} marks
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={openHistory} data-testid="marks-history-btn"><History size={15} className="mr-1" /> History</Button>
          {published && <span className="flex items-center gap-1 text-xs font-medium text-emerald-600" data-testid="published-badge"><CheckCircle2 size={14} /> Published</span>}
          {editable && <Button variant="outline" disabled={saving} onClick={save} data-testid="save-marks-btn">{saving ? "Saving…" : (published ? "Save correction" : "Save marks")}</Button>}
          {!teacherMode && !published && <Button onClick={() => setConfirmPublish(true)} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="publish-btn">Publish results</Button>}
          {!teacherMode && published && <Button variant="outline" onClick={() => togglePublish(false)} data-testid="unpublish-btn">Unpublish</Button>}
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-x-auto">
        {students.length === 0 ? (
          <p className="px-4 py-10 text-sm text-slate-400 text-center" data-testid="marks-empty">No students in this class/section. Enroll students first.</p>
        ) : (
          <table className="w-full text-xs md:text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800">
                <th className="text-left px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500 w-8">#</th>
                <th className="text-left px-2 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Student</th>
                <th className="text-left px-2 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500 w-32">Status</th>
                <th className="text-left px-2 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500 w-32">Score / {maxMarks}</th>
              </tr>
            </thead>
            <tbody>
              {students.map((s, idx) => (
                <tr key={s.id} className="border-b border-slate-100 dark:border-slate-800/60" data-testid={`marks-row-${s.id}`}>
                  <td className="px-3 py-1.5 text-slate-400 font-mono">{idx + 1}</td>
                  <td className="px-2 py-1.5 text-slate-700 dark:text-slate-300 whitespace-nowrap">
                    {`${s.first_name || ""} ${s.last_name || ""}`.trim()}
                    {s.admission_no && <span className="ml-2 text-slate-400 font-mono text-xs">{s.admission_no}</span>}
                  </td>
                  <td className="px-2 py-1.5">
                    <Select
                      value={rows[s.id]?.status || "present"}
                      disabled={!editable}
                      onValueChange={(v) => setRow(s.id, { status: v, ...(v !== "present" ? { score: "" } : {}) })}
                    >
                      <SelectTrigger className="h-7 w-28 text-xs" data-testid={`marks-status-${s.id}`}><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="present">Present</SelectItem>
                        <SelectItem value="absent">Absent</SelectItem>
                        <SelectItem value="exempt">Exempt</SelectItem>
                      </SelectContent>
                    </Select>
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      ref={(el) => { inputRefs.current[s.id] = el; }}
                      type="number"
                      value={rows[s.id]?.score ?? ""}
                      disabled={!editable || rows[s.id]?.status !== "present"}
                      onChange={(e) => setRow(s.id, { score: e.target.value })}
                      onKeyDown={(e) => onKeyDown(e, idx)}
                      data-testid={`marks-score-${s.id}`}
                      className={`h-7 w-24 rounded border px-2 text-xs font-mono bg-transparent text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-40 ${
                        invalid(s.id) ? "border-red-500 text-red-600" : "border-slate-200 dark:border-slate-700"
                      }`}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {hasInvalid && <p className="text-sm text-red-600" data-testid="marks-validation-error">Some scores are outside 0–{maxMarks}. Fix them before saving.</p>}
      <p className="text-xs text-slate-400">Tip: use Enter / ↑ ↓ to move between score cells.</p>

      <AlertDialog open={confirmPublish} onOpenChange={setConfirmPublish}>
        <AlertDialogContent data-testid="publish-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Publish results?</AlertDialogTitle>
            <AlertDialogDescription>Unsaved changes will not be included — save marks first. Publishing locks mark editing until unpublished.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="publish-cancel-btn">Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => togglePublish(true)} className="bg-indigo-700 hover:bg-indigo-800" data-testid="publish-confirm-btn">Publish</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="sm:max-w-lg max-h-[80vh] overflow-y-auto" data-testid="marks-history-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><History size={17} className="text-indigo-600" /> Change history</DialogTitle>
            <DialogDescription>Every mark change for this assessment — who changed what, and when.</DialogDescription>
          </DialogHeader>
          {history === null ? (
            <p className="text-sm text-slate-400 py-6 text-center">Loading…</p>
          ) : history.length === 0 ? (
            <p className="text-sm text-slate-400 py-6 text-center" data-testid="marks-history-empty">No changes recorded yet.</p>
          ) : (
            <ul className="space-y-2" data-testid="marks-history-list">
              {history.map((h) => (
                <li key={h.id} className="rounded-lg border border-slate-200 dark:border-slate-800 px-3 py-2 text-xs" data-testid={`marks-history-${h.id}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-700 dark:text-slate-200">{h.student_name}</span>
                    {h.is_correction && <span className="text-[10px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5 bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">correction</span>}
                  </div>
                  <div className="mt-0.5 text-slate-600 dark:text-slate-300">
                    {h.old_score ?? "—"}{h.old_status && h.old_status !== "present" ? ` (${h.old_status})` : ""}
                    <span className="mx-1 text-slate-400">→</span>
                    <span className="font-semibold">{h.new_score ?? "—"}{h.new_status && h.new_status !== "present" ? ` (${h.new_status})` : ""}</span>
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-400">{h.editor_email} · {h.editor_role} · {new Date(h.timestamp).toLocaleString()}</div>
                </li>
              ))}
            </ul>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
