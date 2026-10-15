import { useCallback, useEffect, useState } from "react";
import { BookMarked, Plus, Paperclip, X, Check, RotateCcw, Lock, Unlock, FileText, Loader2, Inbox } from "lucide-react";
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

export default function TeacherHomework() {
  const [list, setList] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [inbox, setInbox] = useState(null);

  const load = useCallback(() => {
    api.get("/homework").then((r) => setList(r.data.homework)).catch(() => setList([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6" data-testid="teacher-homework-page">
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2"><BookMarked className="text-indigo-600" size={24} /> Homework</h1>
        <Button onClick={() => setShowCreate(true)} data-testid="homework-create-btn"><Plus size={16} className="mr-1.5" /> New homework</Button>
      </div>

      {list === null && <p className="text-sm text-slate-400">Loading…</p>}
      {list?.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 dark:border-slate-700 p-10 text-center text-slate-400" data-testid="homework-empty">No homework yet. Create your first assignment.</div>}

      <div className="grid gap-4 md:grid-cols-2">
        {list?.map((hw) => (
          <div key={hw.id} className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid={`homework-card-${hw.id}`}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h3 className="font-heading font-semibold text-slate-900 dark:text-slate-50 truncate">{hw.title}</h3>
                <p className="text-xs text-slate-500 mt-0.5">{hw.subject} · {hw.class_name} {hw.section} · due {String(hw.due_date).slice(0, 10)}</p>
              </div>
              <span className={`text-[10px] font-bold uppercase rounded-full px-2 py-0.5 ${hw.status === "open" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300" : "bg-slate-200 text-slate-600 dark:bg-slate-700"}`}>{hw.status}</span>
            </div>
            <div className="flex flex-wrap gap-3 mt-3 text-xs text-slate-500">
              <span>Submitted <b className="text-slate-800 dark:text-slate-200">{hw.counts.submitted}/{hw.counts.total_students}</b></span>
              <span>Verified <b className="text-emerald-600">{hw.counts.verified}</b></span>
              <span>Redo <b className="text-amber-600">{hw.counts.redo}</b></span>
              <span>Late <b className="text-rose-600">{hw.counts.late}</b></span>
            </div>
            <div className="flex flex-wrap gap-2 mt-4">
              <Button size="sm" variant="outline" onClick={() => setInbox(hw)} data-testid={`homework-inbox-${hw.id}`}><Inbox size={14} className="mr-1.5" /> Submissions</Button>
              {hw.can_edit && (hw.status === "open"
                ? <Button size="sm" variant="outline" onClick={() => api.post(`/homework/${hw.id}/close`).then(() => { toast.success("Closed"); load(); })} data-testid={`homework-close-${hw.id}`}><Lock size={14} className="mr-1.5" /> Close</Button>
                : <Button size="sm" variant="outline" onClick={() => api.post(`/homework/${hw.id}/reopen`).then(() => { toast.success("Reopened"); load(); })} data-testid={`homework-reopen-${hw.id}`}><Unlock size={14} className="mr-1.5" /> Reopen</Button>)}
            </div>
          </div>
        ))}
      </div>

      {showCreate && <CreateDialog onClose={() => setShowCreate(false)} onDone={() => { setShowCreate(false); load(); }} />}
      {inbox && <SubmissionBoard kind="homework" item={inbox} onClose={() => setInbox(null)} onChange={load} />}
    </div>
  );
}

function CreateDialog({ onClose, onDone }) {
  const [opts, setOpts] = useState([]);
  const [sel, setSel] = useState("");
  const [title, setTitle] = useState("");
  const [instructions, setInstructions] = useState("");
  const [due, setDue] = useState("");
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [notifyParents, setNotifyParents] = useState(false);
  useEffect(() => { api.get("/teacher/teaching-options").then((r) => setOpts(r.data.options || [])).catch(() => setOpts([])); }, []);

  const submit = async () => {
    const opt = opts[Number(sel)];
    if (!opt || !title.trim() || !due) { toast.error("Pick a class, title and due date"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/homework", { class_name: opt.class_name, section: opt.section, subject: opt.subject, title, instructions, due_date: due });
      if (files.length) {
        const fd = new FormData();
        files.slice(0, 5).forEach((f) => fd.append("files", f));
        await api.post(`/homework/${data.homework.id}/attachments`, fd);
      }
      toast.success("Homework created");
      if (notifyParents) {
        try {
          const tpls = (await api.get("/comm/templates")).data.templates || [];
          const t = tpls.find((x) => x.category === "homework" && x.status === "approved");
          if (t) {
            const res = (await api.post("/comm/send", {
              channel: "whatsapp", template_id: t.id, module: "homework",
              target: { class_names: [opt.class_name] },
              vars: { homework_title: title, due_date: String(due).slice(0, 10) },
            })).data;
            if (res.ok !== false) toast.success(`Parents notified (${res.sent})`);
          }
        } catch (err) { toast.message("Homework saved. Parent alerts can be sent by an admin/principal from Communication."); }
      }
      onDone();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Modal title="New homework" onClose={onClose} testid="homework-create-dialog">
      <label className="text-xs font-medium text-slate-400">Class · Section · Subject</label>
      <select className="w-full mt-1 rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-3 py-2 text-sm" value={sel} onChange={(e) => setSel(e.target.value)} data-testid="homework-class-select">
        <option value="">Select…</option>
        {opts.map((o, i) => <option key={i} value={i}>{o.class_name} · {o.section} · {o.subject}{o.student_count != null ? ` (${o.student_count} students)` : ""}</option>)}
      </select>
      <Input className="mt-3" placeholder="Title (e.g. Algebra worksheet)" value={title} onChange={(e) => setTitle(e.target.value)} data-testid="homework-title-input" />
      <Textarea className="mt-3" placeholder="Instructions (optional)" value={instructions} onChange={(e) => setInstructions(e.target.value)} data-testid="homework-instructions-input" />
      <label className="text-xs font-medium text-slate-400 mt-3 block">Due date</label>
      <Input type="datetime-local" className="mt-1" value={due} onChange={(e) => setDue(e.target.value)} data-testid="homework-due-input" />
      <label className="mt-3 flex items-center gap-2 text-sm text-indigo-600 cursor-pointer">
        <Paperclip size={15} /> Attach files (PDF/images/Word, ≤5)
        <input type="file" multiple hidden accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx" onChange={(e) => setFiles([...e.target.files])} data-testid="homework-files-input" />
      </label>
      {files.length > 0 && <p className="text-xs text-slate-500">{files.length} file(s) selected</p>}
      <label className="mt-3 flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300 cursor-pointer">
        <input type="checkbox" checked={notifyParents} onChange={(e) => setNotifyParents(e.target.checked)} data-testid="homework-notify-parents" />
        Also notify parents via WhatsApp
      </label>
      <Button className="w-full mt-4" disabled={busy} onClick={submit} data-testid="homework-create-submit">{busy ? <Loader2 className="animate-spin" size={16} /> : "Create homework"}</Button>
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
