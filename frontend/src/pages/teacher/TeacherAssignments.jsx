import { useCallback, useEffect, useState } from "react";
import { ClipboardCheck, Plus, Paperclip, X, Check, RotateCcw, Lock, Unlock, FileText, Loader2, Inbox, Star } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import SubmissionBoard from "../../components/homework/SubmissionBoard";

const API = process.env.REACT_APP_BACKEND_URL;
const STATUS_BADGE = {
  submitted: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
  verified: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  redo: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
};

export default function TeacherAssignments() {
  const [list, setList] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [inbox, setInbox] = useState(null);

  const load = useCallback(() => {
    api.get("/assignments").then((r) => setList(r.data.assignments)).catch(() => setList([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6" data-testid="teacher-assignments-page">
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2"><ClipboardCheck className="text-fuchsia-600" size={24} /> Assignments</h1>
        <Button onClick={() => setShowCreate(true)} data-testid="assignment-create-btn"><Plus size={16} className="mr-1.5" /> New assignment</Button>
      </div>

      {list === null && <p className="text-sm text-slate-400">Loading…</p>}
      {list?.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 dark:border-slate-700 p-10 text-center text-slate-400" data-testid="assignment-empty">No assignments yet. Create your first scored task.</div>}

      <div className="grid gap-4 md:grid-cols-2">
        {list?.map((a) => (
          <div key={a.id} className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid={`assignment-card-${a.id}`}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h3 className="font-heading font-semibold text-slate-900 dark:text-slate-50 truncate">{a.title}</h3>
                <p className="text-xs text-slate-500 mt-0.5">{a.subject} · {a.class_name} {a.section} · max {a.max_marks} · due {String(a.due_date).slice(0, 10)}</p>
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0">
                <span className={`text-[10px] font-bold uppercase rounded-full px-2 py-0.5 ${a.status === "open" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300" : "bg-slate-200 text-slate-600 dark:bg-slate-700"}`}>{a.status}</span>
                {a.counts_toward_report && <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-600" data-testid={`assignment-report-flag-${a.id}`}><Star size={10} /> On report</span>}
              </div>
            </div>
            <div className="flex flex-wrap gap-3 mt-3 text-xs text-slate-500">
              <span>Submitted <b className="text-slate-800 dark:text-slate-200">{a.counts.submitted}/{a.counts.total_students}</b></span>
              <span>Verified <b className="text-emerald-600">{a.counts.verified}</b></span>
              <span>Redo <b className="text-amber-600">{a.counts.redo}</b></span>
              <span>Late <b className="text-rose-600">{a.counts.late}</b></span>
            </div>
            <div className="flex flex-wrap gap-2 mt-4">
              <Button size="sm" variant="outline" onClick={() => setInbox(a)} data-testid={`assignment-inbox-${a.id}`}><Inbox size={14} className="mr-1.5" /> Submissions</Button>
              {a.can_edit && (a.status === "open"
                ? <Button size="sm" variant="outline" onClick={() => api.post(`/assignments/${a.id}/close`).then(() => { toast.success("Closed"); load(); })} data-testid={`assignment-close-${a.id}`}><Lock size={14} className="mr-1.5" /> Close</Button>
                : <Button size="sm" variant="outline" onClick={() => api.post(`/assignments/${a.id}/reopen`).then(() => { toast.success("Reopened"); load(); })} data-testid={`assignment-reopen-${a.id}`}><Unlock size={14} className="mr-1.5" /> Reopen</Button>)}
            </div>
          </div>
        ))}
      </div>

      {showCreate && <CreateDialog onClose={() => setShowCreate(false)} onDone={() => { setShowCreate(false); load(); }} />}
      {inbox && <SubmissionBoard kind="assignments" item={inbox} onClose={() => setInbox(null)} onChange={load} />}
    </div>
  );
}

function CreateDialog({ onClose, onDone }) {
  const [opts, setOpts] = useState([]);
  const [sel, setSel] = useState("");
  const [title, setTitle] = useState("");
  const [instructions, setInstructions] = useState("");
  const [due, setDue] = useState("");
  const [maxMarks, setMaxMarks] = useState("25");
  const [counts, setCounts] = useState(false);
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/teacher/teaching-options").then((r) => setOpts(r.data.options || [])).catch(() => setOpts([])); }, []);

  const submit = async () => {
    const opt = opts[Number(sel)];
    const mm = parseInt(maxMarks, 10);
    if (!opt || !title.trim() || !due) { toast.error("Pick a class, title and due date"); return; }
    if (!mm || mm < 1) { toast.error("Max marks must be at least 1"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/assignments", { class_name: opt.class_name, section: opt.section, subject: opt.subject, title, instructions, due_date: due, max_marks: mm, counts_toward_report: counts });
      if (files.length) {
        const fd = new FormData();
        files.slice(0, 5).forEach((f) => fd.append("files", f));
        await api.post(`/assignments/${data.assignment.id}/attachments`, fd);
      }
      toast.success("Assignment created"); onDone();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Modal title="New assignment" onClose={onClose} testid="assignment-create-dialog">
      <label className="text-xs font-medium text-slate-400">Class · Section · Subject</label>
      <select className="w-full mt-1 rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-3 py-2 text-sm" value={sel} onChange={(e) => setSel(e.target.value)} data-testid="assignment-class-select">
        <option value="">Select…</option>
        {opts.map((o, i) => <option key={i} value={i}>{`${o.class_name} · ${o.section} · ${o.subject}${o.student_count != null ? ` (${o.student_count} students)` : ""}`}</option>)}
      </select>
      <Input className="mt-3" placeholder="Title (e.g. Algebra Project)" value={title} onChange={(e) => setTitle(e.target.value)} data-testid="assignment-title-input" />
      <Textarea className="mt-3" placeholder="Instructions (optional)" value={instructions} onChange={(e) => setInstructions(e.target.value)} data-testid="assignment-instructions-input" />
      <div className="grid grid-cols-2 gap-3 mt-3">
        <div>
          <label className="text-xs font-medium text-slate-400 block">Due date</label>
          <Input type="datetime-local" className="mt-1" value={due} onChange={(e) => setDue(e.target.value)} data-testid="assignment-due-input" />
        </div>
        <div>
          <label className="text-xs font-medium text-slate-400 block">Max marks</label>
          <Input type="number" min="1" className="mt-1" value={maxMarks} onChange={(e) => setMaxMarks(e.target.value)} data-testid="assignment-maxmarks-input" />
        </div>
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300 cursor-pointer" data-testid="assignment-counts-toggle">
        <input type="checkbox" checked={counts} onChange={(e) => setCounts(e.target.checked)} className="h-4 w-4 rounded" />
        <Star size={14} className="text-amber-500" /> Count verified scores toward the report card
      </label>
      <label className="mt-3 flex items-center gap-2 text-sm text-fuchsia-600 cursor-pointer">
        <Paperclip size={15} /> Attach files (PDF/images/Word, ≤5)
        <input type="file" multiple hidden accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx" onChange={(e) => setFiles([...e.target.files])} data-testid="assignment-files-input" />
      </label>
      {files.length > 0 && <p className="text-xs text-slate-500">{files.length} file(s) selected</p>}
      <Button className="w-full mt-4" disabled={busy} onClick={submit} data-testid="assignment-create-submit">{busy ? <Loader2 className="animate-spin" size={16} /> : "Create assignment"}</Button>
    </Modal>
  );
}

function Modal({ title, children, onClose, testid, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" data-testid={testid}>
      <div className={`w-full ${wide ? "max-w-2xl" : "max-w-md"} max-h-[85vh] overflow-y-auto rounded-3xl bg-white dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-800 shadow-2xl p-6`}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-white">{title}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" data-testid="modal-close"><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}
