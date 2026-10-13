import { useCallback, useEffect, useState } from "react";
import { Megaphone, Plus, Paperclip, X, Loader2, Send, Trash2, FileText, Users } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";

const API = process.env.REACT_APP_BACKEND_URL;

const SCOPE_LABEL = { school: "Whole school", divisions: "Divisions", classes: "Specific classes" };

export default function NoticesPage() {
  const [notices, setNotices] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [sendFor, setSendFor] = useState(null);
  const [me, setMe] = useState(null);

  const load = useCallback(() => {
    api.get("/notices").then((r) => setNotices(r.data.notices)).catch((e) => { toast.error(errText(e)); setNotices([]); });
  }, []);
  useEffect(() => { load(); api.get("/auth/me").then((r) => setMe(r.data)).catch(() => {}); }, [load]);

  const remove = async (id) => {
    if (!window.confirm("Delete this notice?")) return;
    try { await api.delete(`/notices/${id}`); toast.success("Notice deleted"); load(); }
    catch (e) { toast.error(errText(e)); }
  };

  return (
    <div className="space-y-6" data-testid="notices-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Megaphone className="text-amber-600" size={24} /> Notices</h1>
          <p className="text-sm text-slate-500 mt-1">Circulars with attachments, targeted to the right classes — with bell alerts and parent messaging.</p>
        </div>
        <Button onClick={() => setShowCreate(true)} data-testid="notice-create-btn"><Plus size={16} className="mr-1.5" /> New notice</Button>
      </div>

      {notices === null && <p className="text-sm text-slate-400">Loading…</p>}
      {notices?.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 dark:border-slate-700 p-10 text-center text-slate-400" data-testid="notices-empty">No notices yet.</div>}

      <div className="grid gap-4 md:grid-cols-2">
        {notices?.map((n) => (
          <div key={n.id} className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid={`notice-card-${n.id}`}>
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-heading font-semibold text-slate-900 dark:text-slate-50">{n.title}</h3>
              <span className="text-[10px] font-bold uppercase rounded-full px-2 py-0.5 bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">{n.status}</span>
            </div>
            {n.body && <p className="text-sm text-slate-500 mt-1 whitespace-pre-line line-clamp-3">{n.body}</p>}
            <div className="flex items-center gap-2 mt-2 text-xs text-slate-400">
              <Users size={12} /> {SCOPE_LABEL[n.target?.scope] || "Whole school"}
              {n.target?.scope === "classes" && n.target.classes?.length > 0 && <span>· {n.target.classes.map((c) => c.class_name + (c.section ? ` ${c.section}` : "")).join(", ")}</span>}
            </div>
            {n.attachments?.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3" data-testid={`notice-attachments-${n.id}`}>
                {n.attachments.map((a, i) => (
                  <a key={i} href={`${API}/api/notices/attachment/${n.id}/${i}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:underline" data-testid={`notice-file-${n.id}-${i}`}><FileText size={12} /> {a.name}</a>
                ))}
              </div>
            )}
            <div className="flex flex-wrap gap-2 mt-4">
              <Button size="sm" variant="outline" onClick={() => setSendFor(n)} data-testid={`notice-send-${n.id}`}><Send size={14} className="mr-1.5" /> Send to parents</Button>
              {(me && (n.author_id === me.id || me.role === "institution_admin")) && (
                <Button size="sm" variant="outline" onClick={() => remove(n.id)} data-testid={`notice-delete-${n.id}`} className="text-rose-600"><Trash2 size={14} /></Button>
              )}
            </div>
          </div>
        ))}
      </div>

      {showCreate && <CreateDialog me={me} onClose={() => setShowCreate(false)} onDone={() => { setShowCreate(false); load(); }} />}
      {sendFor && <SendDialog notice={sendFor} onClose={() => setSendFor(null)} />}
    </div>
  );
}

function CreateDialog({ me, onClose, onDone }) {
  const isTeacher = me?.role === "teacher" && !me?.is_principal;
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [scope, setScope] = useState(isTeacher ? "classes" : "school");
  const [classes, setClasses] = useState([]);       // list of {class_name, section}
  const [divisions, setDivisions] = useState([]);
  const [files, setFiles] = useState([]);
  const [opts, setOpts] = useState({ classes: [], divisions: [], teaching: [] });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (me?.role === "teacher") {
      api.get("/teacher/teaching-options").then((r) => {
        const seen = new Set(); const list = [];
        (r.data.options || []).forEach((o) => { const k = o.class_name + "|" + o.section; if (!seen.has(k)) { seen.add(k); list.push({ class_name: o.class_name, section: o.section }); } });
        setOpts((p) => ({ ...p, teaching: list }));
      }).catch(() => {});
    }
    api.get("/comm/audiences").then((r) => setOpts((p) => ({ ...p, classes: r.data.classes || [], divisions: r.data.divisions || [] }))).catch(() => {});
  }, [me]);

  const toggleClass = (cn, sec) => {
    const exists = classes.some((c) => c.class_name === cn && c.section === sec);
    setClasses(exists ? classes.filter((c) => !(c.class_name === cn && c.section === sec)) : [...classes, { class_name: cn, section: sec }]);
  };
  const toggleDiv = (id) => setDivisions(divisions.includes(id) ? divisions.filter((x) => x !== id) : [...divisions, id]);

  const submit = async () => {
    if (!title.trim()) { toast.error("Enter a title"); return; }
    if (scope === "classes" && classes.length === 0) { toast.error("Pick at least one class"); return; }
    if (scope === "divisions" && divisions.length === 0) { toast.error("Pick at least one division"); return; }
    setBusy(true);
    try {
      const target = { scope, division_ids: scope === "divisions" ? divisions : [], classes: scope === "classes" ? classes : [] };
      const { data } = await api.post("/notices", { title, body, target, status: "published" });
      if (files.length) {
        const fd = new FormData();
        files.slice(0, 3).forEach((f) => fd.append("files", f));
        await api.post(`/notices/${data.notice.id}/attachments`, fd);
      }
      toast.success(`Notice posted — ${data.notified_students} student(s) alerted`);
      onDone();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const classChoices = isTeacher ? opts.teaching : opts.classes.map((c) => ({ class_name: c.name, section: null }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" data-testid="notice-create-dialog">
      <div className="w-full max-w-lg rounded-3xl bg-white dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-800 shadow-2xl p-6 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-white">New notice</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" data-testid="notice-create-close"><X size={18} /></button>
        </div>
        <Input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} data-testid="notice-title-input" />
        <Textarea className="mt-3" placeholder="Message (optional)" value={body} onChange={(e) => setBody(e.target.value)} data-testid="notice-body-input" />

        <label className="text-xs font-medium text-slate-400 mt-4 block">Audience</label>
        <select className="w-full mt-1 rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-3 py-2 text-sm" value={scope} onChange={(e) => setScope(e.target.value)} data-testid="notice-scope-select" disabled={isTeacher}>
          {!isTeacher && <option value="school">Whole school</option>}
          {!isTeacher && <option value="divisions">Specific divisions</option>}
          <option value="classes">Specific classes</option>
        </select>

        {scope === "divisions" && (
          <div className="mt-2 grid grid-cols-2 gap-1.5" data-testid="notice-divisions">
            {opts.divisions.map((d) => (
              <label key={d.id} className="flex items-center gap-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 px-2.5 py-1.5 cursor-pointer">
                <input type="checkbox" checked={divisions.includes(d.id)} onChange={() => toggleDiv(d.id)} /> <span className="truncate">{d.name}</span>
              </label>
            ))}
          </div>
        )}
        {scope === "classes" && (
          <div className="mt-2 grid grid-cols-2 gap-1.5 max-h-40 overflow-y-auto" data-testid="notice-classes">
            {classChoices.map((c, i) => {
              const checked = classes.some((x) => x.class_name === c.class_name && x.section === c.section);
              return (
                <label key={i} className="flex items-center gap-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 px-2.5 py-1.5 cursor-pointer">
                  <input type="checkbox" checked={checked} onChange={() => toggleClass(c.class_name, c.section)} data-testid={`notice-class-${c.class_name}-${c.section || "all"}`.replace(/\s/g, "")} />
                  <span className="truncate">{c.class_name}{c.section ? ` ${c.section}` : ""}</span>
                </label>
              );
            })}
          </div>
        )}

        <label className="mt-4 flex items-center gap-2 text-sm text-indigo-600 cursor-pointer">
          <Paperclip size={15} /> Attach circular (PDF/image, ≤3)
          <input type="file" multiple hidden accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={(e) => setFiles([...e.target.files])} data-testid="notice-files-input" />
        </label>
        {files.length > 0 && <p className="text-xs text-slate-500">{files.length} file(s) selected</p>}

        <Button className="w-full mt-4" disabled={busy} onClick={submit} data-testid="notice-submit">{busy ? <Loader2 className="animate-spin" size={16} /> : "Post notice"}</Button>
      </div>
    </div>
  );
}

function SendDialog({ notice, onClose }) {
  const [channel, setChannel] = useState("whatsapp");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  const review = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/notices/${notice.id}/send`, { channel, dry_run: true }); setPreview(data); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const send = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/notices/${notice.id}/send`, { channel });
      if (data.ok === false) toast.error(data.message || "Nothing sent");
      else toast.success(`Sent to ${data.sent} parent(s)${data.has_attachment ? " with attachment" : ""}${data.skipped_count ? ` · ${data.skipped_count} skipped` : ""}`);
      onClose();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" data-testid="notice-send-dialog">
      <div className="w-full max-w-md rounded-3xl bg-white dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-800 shadow-2xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-heading text-lg font-bold text-slate-900 dark:text-white">Send "{notice.title}"</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" data-testid="notice-send-close"><X size={18} /></button>
        </div>
        {!preview ? (
          <>
            <div className="flex gap-2">
              {["whatsapp", "sms"].map((c) => (
                <button key={c} onClick={() => setChannel(c)} data-testid={`notice-channel-${c}`}
                  className={`flex-1 rounded-xl border-2 px-3 py-2 text-sm font-semibold capitalize ${channel === c ? "border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300" : "border-slate-200 dark:border-slate-700 text-slate-500"}`}>{c}</button>
              ))}
            </div>
            <p className="text-xs text-slate-500 mt-2">{notice.attachment_count > 0 ? (channel === "whatsapp" ? "The attachment will be sent as a WhatsApp document." : "A secure link to the attachment will be included in the SMS.") : "No attachment on this notice."}</p>
            <Button className="w-full mt-4" onClick={review} disabled={busy} data-testid="notice-review-btn">{busy ? <Loader2 className="animate-spin" size={16} /> : "Review recipients"}</Button>
          </>
        ) : (
          <div data-testid="notice-send-confirm">
            <div className="rounded-2xl border-2 border-emerald-200 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10 p-4">
              <p className="text-sm font-semibold text-emerald-800 dark:text-emerald-200">Send to {preview.recipient_count} parent(s) via {channel.toUpperCase()}?</p>
              <p className="text-xs text-emerald-700 dark:text-emerald-300 mt-1">{preview.quota_remaining} remaining → {preview.quota_after} after.{preview.has_attachment ? " Attachment included." : ""}</p>
              {preview.skipped_count > 0 && <p className="text-xs text-amber-700 dark:text-amber-300 mt-1">{preview.skipped_count} skipped (no guardian phone).</p>}
            </div>
            <div className="flex gap-2 mt-4">
              <Button variant="outline" className="flex-1" onClick={() => setPreview(null)} disabled={busy}>Back</Button>
              <Button className="flex-1" onClick={send} disabled={busy || preview.recipient_count === 0 || preview.would_block} data-testid="notice-send-confirm-btn">{busy ? <Loader2 className="animate-spin" size={16} /> : "Send now"}</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
