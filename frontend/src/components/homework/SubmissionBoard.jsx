import { useCallback, useEffect, useState } from "react";
import { Check, RotateCcw, X, Loader2, FileText, Clock, History, Paperclip } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";
import { Avatar } from "../common/Avatar";

const API = process.env.REACT_APP_BACKEND_URL;
const CHIPS = [["", "All"], ["submitted", "Submitted"], ["late", "Late"], ["redo_requested", "Redo requested"], ["reviewed", "Reviewed"], ["not_submitted", "Not submitted"]];
const STATE = {
  submitted: ["Submitted", "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300"],
  redo_requested: ["Redo requested", "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300"],
  reviewed: ["Reviewed ✓", "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"],
  not_submitted: ["Not submitted", "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"],
};
const when = (s) => (s ? new Date(s).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—");

export const StateBadge = ({ state, late, testid }) => (
  <span className="inline-flex gap-1" data-testid={testid}>
    <span className={`text-[10px] font-bold uppercase rounded-full px-2 py-0.5 whitespace-nowrap ${STATE[state]?.[1]}`}>{STATE[state]?.[0] || state}</span>
    {late && state !== "not_submitted" && <span className="text-[10px] font-bold uppercase rounded-full px-2 py-0.5 bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300">Late</span>}
  </span>
);

export default function SubmissionBoard({ kind, item, onClose, onChange }) {
  const [filter, setFilter] = useState("");
  const [d, setD] = useState(null);
  const [openSub, setOpenSub] = useState(null);
  const load = useCallback(() => {
    api.get(`/${kind}/${item.id}/submission-board`, { params: filter ? { filter } : {} }).then((r) => setD(r.data)).catch((e) => toast.error(errText(e)));
  }, [kind, item.id, filter]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-sm" data-testid="submission-board">
      <div className="w-full max-w-3xl h-full overflow-y-auto bg-white dark:bg-slate-900 shadow-2xl">
        <div className="sticky top-0 z-10 bg-white/95 dark:bg-slate-900/95 backdrop-blur border-b border-slate-200 dark:border-slate-800 px-6 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">{kind === "homework" ? "Homework" : "Assignment"} submissions</p>
              <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-white truncate">{item.title}</h2>
              <p className="text-xs text-slate-500">{item.class_name}{item.section ? ` ${item.section}` : ""} · {item.subject} · due {String(item.due_date).slice(0, 10)}</p>
            </div>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600" data-testid="submission-board-close"><X size={20} /></button>
          </div>
          <div className="flex flex-wrap gap-1.5 mt-3" data-testid="submission-filter-chips">
            {CHIPS.map(([k, label]) => (
              <button key={k || "all"} onClick={() => setFilter(k)} data-testid={`submission-chip-${k || "all"}`}
                className={`rounded-full px-3 py-1 text-xs font-semibold border transition-colors ${filter === k ? "bg-slate-900 text-white border-slate-900 dark:bg-white dark:text-slate-900" : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-slate-400"}`}>
                {label} <span className="opacity-70">{d ? (k ? d.counts[k] : d.counts.all) : ""}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
          {!d && <p className="px-6 py-8 text-sm text-slate-400">Loading…</p>}
          {d && d.rows.length === 0 && <p className="px-6 py-8 text-sm text-slate-400" data-testid="submission-board-empty">No students in this filter.</p>}
          {d?.rows.map((r) => (
            <button key={r.student_id} disabled={!r.submission_id} onClick={() => setOpenSub(r.submission_id)} data-testid={`submission-row-${r.student_id}`}
              className="w-full text-left px-6 py-3 flex items-center gap-3 hover:bg-slate-50 dark:hover:bg-slate-800/40 disabled:cursor-default disabled:hover:bg-transparent">
              <Avatar src={r.thumb_url} name={r.student_name} />
              <span className="flex-1 min-w-0">
                <span className="block text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{r.student_name}</span>
                <span className="block text-xs text-slate-500">{r.admission_no || ""}{r.submitted_at ? ` · ${when(r.submitted_at)}` : ""}{r.attempt > 1 ? ` · attempt ${r.attempt}` : ""}{r.score != null ? ` · ${r.score}${d.item.max_marks ? `/${d.item.max_marks}` : ""}` : ""}</span>
              </span>
              <StateBadge state={r.state} late={r.late} testid={`submission-state-${r.student_id}`} />
            </button>
          ))}
        </div>
      </div>
      {openSub && <SubmissionDetail kind={kind} subId={openSub} onClose={() => setOpenSub(null)} onDone={() => { load(); onChange?.(); }} />}
    </div>
  );
}

function Files({ files, testid }) {
  if (!files?.length) return <p className="text-xs text-slate-400">No files attached.</p>;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2" data-testid={testid}>
      {files.map((f) => (
        <a key={f.url} href={`${API}${f.url}`} target="_blank" rel="noreferrer" className="group rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden hover:border-slate-400" data-testid={`${testid}-${f.idx}`}>
          {f.is_image ? <img src={`${API}${f.url}`} alt={f.name} className="h-28 w-full object-cover bg-slate-100" loading="lazy" />
            : <span className="h-28 flex flex-col items-center justify-center gap-1 bg-slate-50 dark:bg-slate-800 text-slate-500"><FileText size={26} />{f.is_pdf ? "Open PDF" : "Open file"}</span>}
          <span className="block px-2 py-1 text-[11px] text-slate-600 dark:text-slate-300 truncate">{f.name}</span>
        </a>
      ))}
    </div>
  );
}

function SubmissionDetail({ kind, subId, onClose, onDone }) {
  const [d, setD] = useState(null);
  const [mode, setMode] = useState(null);
  const load = useCallback(() => { api.get(`/submissions/${kind}/${subId}`).then((r) => setD(r.data)).catch((e) => toast.error(errText(e))); }, [kind, subId]);
  useEffect(() => { load(); }, [load]);
  const s = d?.submission;
  return (
    <div className="fixed inset-0 z-[60] flex justify-end bg-black/30" data-testid="submission-detail">
      <div className="w-full max-w-xl h-full overflow-y-auto bg-white dark:bg-slate-900 shadow-2xl border-l border-slate-200 dark:border-slate-800">
        {!d ? <p className="p-6 text-sm text-slate-400">Loading…</p> : (
          <div className="p-6 space-y-5">
            <div className="flex items-start gap-3">
              <Avatar src={d.student.thumb_url} name={d.student.name} size="lg" />
              <div className="flex-1 min-w-0">
                <h3 className="font-heading text-lg font-bold text-slate-900 dark:text-white" data-testid="submission-detail-student">{d.student.name}</h3>
                <p className="text-xs text-slate-500">{d.student.admission_no} · {d.student.class_name} {d.student.section} · {d.item.title}</p>
                <div className="mt-1.5 flex items-center gap-2 flex-wrap"><StateBadge state={s.state} late={s.late} testid="submission-detail-state" />
                  <span className="text-[11px] text-slate-500" data-testid="submission-detail-attempt">Attempt {s.attempt}</span></div>
              </div>
              <button onClick={onClose} className="text-slate-400 hover:text-slate-600" data-testid="submission-detail-close"><X size={20} /></button>
            </div>
            <div className="rounded-2xl bg-slate-50 dark:bg-slate-800/50 p-4 space-y-3">
              <p className="text-xs text-slate-500 flex items-center gap-1.5"><Clock size={12} /> Submitted {when(s.submitted_at)}{s.late ? " · after the due date" : ""}</p>
              <div><p className="text-[11px] font-semibold uppercase text-slate-400 mb-1">Answer</p>
                <p className="text-sm text-slate-800 dark:text-slate-100 whitespace-pre-line" data-testid="submission-detail-note">{s.note || <span className="text-slate-400">No text answer.</span>}</p></div>
              <div><p className="text-[11px] font-semibold uppercase text-slate-400 mb-1.5 flex items-center gap-1"><Paperclip size={11} /> Attachments</p><Files files={s.attachments} testid="submission-detail-file" /></div>
            </div>
            {(s.feedback || s.score != null) && (
              <div className="rounded-2xl border border-amber-200 dark:border-amber-500/30 bg-amber-50/60 dark:bg-amber-500/5 p-4 text-sm" data-testid="submission-detail-feedback">
                {s.score != null && <p className="font-semibold">Marks: {s.score}{d.item.max_marks ? `/${d.item.max_marks}` : ""}</p>}
                {s.feedback && <p className="whitespace-pre-line">{s.state === "redo_requested" ? "Redo requested: " : "Feedback: "}{s.feedback}</p>}
                {s.redo_due_date && s.state === "redo_requested" && <p className="text-xs text-slate-500 mt-1">New due date: {s.redo_due_date}</p>}
                {s.reviewed_by_name && <p className="text-xs text-slate-500 mt-1">— {s.reviewed_by_name}, {when(s.verified_at)}</p>}
              </div>
            )}
            {d.can_review && !mode && (
              <div className="flex gap-2">
                <Button onClick={() => setMode("review")} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="submission-mark-reviewed"><Check size={15} className="mr-1.5" /> Mark reviewed</Button>
                <Button variant="outline" onClick={() => setMode("redo")} data-testid="submission-request-redo"><RotateCcw size={15} className="mr-1.5" /> Request redo</Button>
              </div>
            )}
            {mode && <ActionForm mode={mode} kind={kind} d={d} onCancel={() => setMode(null)} onSaved={(nd) => { setD(nd); setMode(null); onDone(); }} />}
            {d.previous_attempts.length > 0 && (
              <div data-testid="submission-history">
                <p className="text-[11px] font-semibold uppercase text-slate-400 mb-2 flex items-center gap-1"><History size={12} /> Previous attempts (read-only)</p>
                <div className="space-y-3">
                  {d.previous_attempts.map((a) => (
                    <div key={a.attempt} className="rounded-xl border border-slate-200 dark:border-slate-700 p-3 space-y-2" data-testid={`submission-attempt-${a.attempt}`}>
                      <p className="text-xs font-semibold text-slate-600 dark:text-slate-300">Attempt {a.attempt} · {when(a.submitted_at)}{a.late ? " · late" : ""}</p>
                      {a.note && <p className="text-sm text-slate-700 dark:text-slate-200 whitespace-pre-line">{a.note}</p>}
                      <Files files={a.attachments} testid={`submission-attempt-${a.attempt}-file`} />
                      {a.feedback && <p className="text-xs text-amber-700 dark:text-amber-300">{a.state === "redo_requested" ? "Redo requested" : "Feedback"}: {a.feedback}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ActionForm({ mode, kind, d, onCancel, onSaved }) {
  const [feedback, setFeedback] = useState(mode === "review" ? d.submission.feedback || "" : "");
  const [score, setScore] = useState(d.submission.score ?? "");
  const [due, setDue] = useState("");
  const [busy, setBusy] = useState(false);
  const redo = mode === "redo";
  const save = async () => {
    if (redo && !feedback.trim()) { toast.error("Tell the student what to fix"); return; }
    setBusy(true);
    try {
      const body = redo ? { feedback: feedback.trim(), due_date: due || null } : { feedback: feedback.trim(), score: score === "" ? null : Number(score) };
      const r = await api.post(`/submissions/${kind}/${d.submission.id}/${redo ? "redo" : "review"}`, body);
      toast.success(redo ? "Redo requested — the student and parents were notified" : "Marked reviewed");
      onSaved(r.data);
    } catch (e) { toast.error(errText(e)); setBusy(false); }
  };
  return (
    <div className={`rounded-2xl border-2 p-4 space-y-3 ${redo ? "border-amber-300 dark:border-amber-500/40" : "border-emerald-300 dark:border-emerald-500/40"}`} data-testid={redo ? "redo-dialog" : "review-dialog"}>
      <p className="font-semibold text-sm text-slate-800 dark:text-slate-100">{redo ? "Request a redo" : "Mark as reviewed"}</p>
      {!redo && d.supports_marks && (
        <label className="block text-xs text-slate-500">Marks {d.item.max_marks ? `(out of ${d.item.max_marks})` : "(optional)"}
          <Input type="number" min={0} max={d.item.max_marks || undefined} value={score} onChange={(e) => setScore(e.target.value)} className="mt-1 w-32" data-testid="review-score-input" /></label>
      )}
      <label className="block text-xs text-slate-500">{redo ? "What should the student fix? (required)" : "Feedback (optional)"}
        <Textarea rows={3} value={feedback} onChange={(e) => setFeedback(e.target.value)} className="mt-1" placeholder={redo ? "e.g. Label the nucleus and cell wall, and show your working." : "Well done!"} data-testid={redo ? "redo-feedback-input" : "review-feedback-input"} /></label>
      {redo && (
        <label className="block text-xs text-slate-500">New due date (optional)
          <Input type="date" value={due} min={new Date().toISOString().slice(0, 10)} onChange={(e) => setDue(e.target.value)} className="mt-1 w-44" data-testid="redo-due-input" /></label>
      )}
      <div className="flex gap-2">
        <Button disabled={busy || (redo && !feedback.trim())} onClick={save} className={redo ? "bg-amber-500 hover:bg-amber-600 text-white" : "bg-emerald-600 hover:bg-emerald-700 text-white"} data-testid={redo ? "redo-submit-btn" : "review-submit-btn"}>
          {busy ? <Loader2 size={15} className="animate-spin" /> : redo ? "Send back for redo" : "Save review"}</Button>
        <Button variant="ghost" onClick={onCancel} data-testid="action-cancel-btn">Cancel</Button>
      </div>
    </div>
  );
}
