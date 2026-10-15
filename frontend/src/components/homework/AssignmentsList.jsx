import { useRef, useState } from "react";
import { FileText, Paperclip, Loader2, Upload, RotateCcw, Star } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../ui/button";

const API = process.env.REACT_APP_BACKEND_URL;

const badge = (a) => {
  const s = a.my_submission;
  if (!s) return { label: "Not submitted", cls: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300" };
  if (s.status === "verified") return { label: `Scored ${s.score ?? "?"}/${a.max_marks}`, cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300" };
  if (s.status === "redo") return { label: "Needs redo", cls: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300" };
  return { label: s.late ? "Submitted · Late" : "Submitted", cls: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300" };
};

export default function AssignmentsList({ items, canSubmit = false, onChanged }) {
  if (!items) return <p className="px-6 py-6 text-sm text-slate-400">Loading…</p>;
  if (items.length === 0) return <p className="px-6 py-6 text-sm text-slate-400" data-testid="assignments-empty">No assignments right now.</p>;
  return (
    <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
      {items.map((a) => <AsgRow key={a.id} a={a} canSubmit={canSubmit} onChanged={onChanged} />)}
    </div>
  );
}

function AsgRow({ a, canSubmit, onChanged }) {
  const b = badge(a);
  const s = a.my_submission;
  const canAct = canSubmit && ((!s && a.status === "open") || s?.status === "redo");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const fileRef = useRef(null);

  const submit = async () => {
    const files = fileRef.current?.files;
    if ((!files || files.length === 0) && !note.trim()) { toast.error("Attach a file or add a note"); return; }
    const fd = new FormData();
    fd.append("note", note);
    [...(files || [])].slice(0, 5).forEach((f) => fd.append("files", f));
    setBusy(true);
    try { const r = await api.post(`/assignments/${a.id}/submit`, fd); toast.success(r.data.message); setOpen(false); setNote(""); onChanged?.(); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <div className="px-6 py-4" data-testid={`asg-row-${a.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 flex items-center gap-1.5">{a.title}
            {a.counts_toward_report && <Star size={12} className="text-amber-500" title="Counts toward report card" />}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">{a.subject} · max {a.max_marks} · due {String(a.due_date).slice(0, 10)}{a.status === "closed" ? " · closed" : ""}</p>
          {a.instructions && <p className="text-xs text-slate-500 mt-1 whitespace-pre-line">{a.instructions}</p>}
          <div className="flex flex-wrap gap-2 mt-2">
            {(a.attachments || []).map((f, i) => (
              <a key={i} href={`${API}/api/assignments/attachment/${a.id}/${i}?kind=assignment`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-fuchsia-600 hover:underline" data-testid={`asg-file-${a.id}-${i}`}><FileText size={12} /> {f.name}</a>
            ))}
          </div>
          {s?.status === "redo" ? (
            <div className="mt-2 rounded-lg border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 px-3 py-2" data-testid={`asg-redo-${a.id}`}>
              <p className="text-xs font-semibold text-amber-800 dark:text-amber-200">Redo requested: {s.feedback}</p>
              <p className="text-[11px] text-amber-700/80 dark:text-amber-300/80 mt-0.5">Attempt {s.version || 1} was sent back{s.redo_due_date ? ` · resubmit by ${s.redo_due_date}` : ""} · your earlier attempts are kept</p>
            </div>
          ) : s?.feedback && <p className="text-xs text-amber-600 mt-1.5" data-testid={`asg-feedback-${a.id}`}>Teacher: {s.feedback}{s.version > 1 ? ` · attempt ${s.version}` : ""}</p>}
          {s?.attachments?.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-1.5">
              {s.attachments.map((f, i) => (
                <a key={i} href={`${API}/api/assignments/attachment/${s.id}/${i}?kind=submission`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:underline"><Paperclip size={11} /> {f.name}</a>
              ))}
            </div>
          )}
        </div>
        <span className={`text-[10px] font-bold uppercase rounded-full px-2 py-0.5 whitespace-nowrap ${b.cls}`} data-testid={`asg-badge-${a.id}`}>{b.label}</span>
      </div>

      {canAct && !open && (
        <Button size="sm" variant="outline" className="mt-3" onClick={() => setOpen(true)} data-testid={`asg-submit-open-${a.id}`}>
          {s?.status === "redo" ? <><RotateCcw size={13} className="mr-1.5" /> Resubmit</> : <><Upload size={13} className="mr-1.5" /> Submit</>}
        </Button>
      )}
      {canAct && open && (
        <div className="mt-3 rounded-xl border border-slate-200 dark:border-slate-700 p-3 space-y-2" data-testid={`asg-submit-box-${a.id}`}>
          <label className="flex items-center gap-2 text-sm text-fuchsia-600 cursor-pointer">
            <Paperclip size={14} /> Attach files (≤5)
            <input ref={fileRef} type="file" multiple hidden accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx" data-testid={`asg-files-${a.id}`} />
          </label>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)" rows={2} className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-3 py-2 text-sm" data-testid={`asg-note-${a.id}`} />
          <div className="flex gap-2">
            <Button size="sm" disabled={busy} onClick={submit} data-testid={`asg-submit-send-${a.id}`}>{busy ? <Loader2 size={14} className="animate-spin" /> : "Send"}</Button>
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          </div>
        </div>
      )}
    </div>
  );
}
