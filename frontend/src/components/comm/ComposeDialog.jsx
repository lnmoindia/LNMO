import { useCallback, useEffect, useMemo, useState } from "react";
import { MessageSquare, X, Loader2, Send, Users, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";

const AUTO_VARS = ["school_name", "student_name", "parent_name", "class", "secure_link"];
const VAR_LABEL = {
  exam_name: "Exam name", exam_date: "Exam date", homework_title: "Homework title",
  due_date: "Due date", amount: "Amount",
};

// Reusable parent-notification composer used by Announcements, Exams and Homework.
export default function ComposeDialog({ onClose, onSent, module = "manual", title = "Notify parents",
  defaultChannel = "whatsapp", defaultVars = {}, defaultCategory = null, lockedClassNames = null }) {
  const [channel, setChannel] = useState(defaultChannel);
  const [templates, setTemplates] = useState([]);
  const [templateId, setTemplateId] = useState("");
  const [freeBody, setFreeBody] = useState("");
  const [audiences, setAudiences] = useState({ classes: [], divisions: [] });
  const [picked, setPicked] = useState([]);           // class ids
  const [vars, setVars] = useState(defaultVars || {});
  const [status, setStatus] = useState(null);
  const [preview, setPreview] = useState(null);       // dry-run result
  const [busy, setBusy] = useState(false);

  const locked = Array.isArray(lockedClassNames) && lockedClassNames.length > 0;

  useEffect(() => {
    api.get("/comm/templates").then((r) => setTemplates(r.data.templates || [])).catch(() => {});
    api.get("/comm/status").then((r) => setStatus(r.data)).catch(() => {});
    if (!locked) api.get("/comm/audiences").then((r) => setAudiences(r.data)).catch(() => {});
  }, [locked]);

  const usableTemplates = useMemo(() => templates.filter((t) => {
    if (defaultCategory && t.category !== defaultCategory) return false;
    if (t.channel !== "both" && t.channel !== channel) return false;
    if (channel === "whatsapp" && t.status !== "approved") return false;
    if (t.status === "disabled") return false;
    return true;
  }), [templates, channel, defaultCategory]);

  useEffect(() => {
    if (templateId && !usableTemplates.some((t) => t.id === templateId)) setTemplateId("");
    if (!templateId && channel === "whatsapp" && usableTemplates.length) setTemplateId(usableTemplates[0].id);
  }, [usableTemplates, channel]); // eslint-disable-line

  const selectedTemplate = usableTemplates.find((t) => t.id === templateId) || null;
  const bodyText = selectedTemplate ? selectedTemplate.body : freeBody;
  const promptVars = useMemo(() => {
    const found = [];
    (bodyText.match(/{{(\w+)}}/g) || []).forEach((m) => {
      const k = m.slice(2, -2);
      if (!AUTO_VARS.includes(k) && !found.includes(k)) found.push(k);
    });
    return found;
  }, [bodyText]);

  const target = useMemo(() => (locked ? { class_names: lockedClassNames } : { class_ids: picked }), [locked, lockedClassNames, picked]);
  const remaining = status ? (channel === "whatsapp" ? status.whatsapp?.remaining : status.sms?.remaining) : null;

  const payload = useCallback((dry) => ({
    channel, template_id: selectedTemplate ? templateId : null,
    body: selectedTemplate ? null : freeBody, target, vars, module, dry_run: dry,
  }), [channel, selectedTemplate, templateId, freeBody, target, vars, module]);

  const valid = () => {
    if (channel === "whatsapp" && !selectedTemplate) { toast.error("WhatsApp needs an approved template"); return false; }
    if (channel === "sms" && !selectedTemplate && !freeBody.trim()) { toast.error("Enter a message or pick a template"); return false; }
    if (!locked && picked.length === 0) { toast.error("Pick at least one class"); return false; }
    return true;
  };

  const review = async () => {
    if (!valid()) return;
    setBusy(true);
    try { const { data } = await api.post("/comm/send", payload(true)); setPreview(data); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const confirmSend = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/comm/send", payload(false));
      if (data.ok === false) { toast.error(data.message || "Nothing sent"); }
      else toast.success(`Sent to ${data.sent} parent(s)${data.skipped_count ? ` · ${data.skipped_count} skipped (no phone)` : ""}`);
      onSent && onSent(data); onClose();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const toggleClass = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const sortedClasses = [...(audiences.classes || [])].sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" data-testid="compose-dialog">
      <div className="w-full max-w-lg rounded-3xl bg-white dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-800 shadow-2xl p-6 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2"><MessageSquare size={18} className="text-emerald-600" /> {title}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" data-testid="compose-close"><X size={18} /></button>
        </div>

        {!preview ? (
          <>
            <div className="flex gap-2 mb-4">
              {["whatsapp", "sms"].map((c) => (
                <button key={c} onClick={() => setChannel(c)} data-testid={`compose-channel-${c}`}
                  className={`flex-1 rounded-xl border-2 px-3 py-2 text-sm font-semibold capitalize transition-colors ${channel === c ? "border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300" : "border-slate-200 dark:border-slate-700 text-slate-500"}`}>
                  {c}
                </button>
              ))}
            </div>
            {channel === "whatsapp" && (
              <p className="text-xs text-slate-500 mb-2 flex items-center gap-1.5"><AlertTriangle size={12} className="text-amber-500" /> WhatsApp uses approved templates only (policy). Use SMS for free text.</p>
            )}

            <label className="text-xs font-medium text-slate-400">Template</label>
            <select className="w-full mt-1 rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-3 py-2 text-sm" value={templateId} onChange={(e) => setTemplateId(e.target.value)} data-testid="compose-template">
              <option value="">{channel === "sms" ? "— Free text —" : "Select a template…"}</option>
              {usableTemplates.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.scope})</option>)}
            </select>

            {selectedTemplate ? (
              <div className="mt-2 rounded-lg bg-slate-50 dark:bg-slate-800/60 px-3 py-2 text-xs text-slate-600 dark:text-slate-300" data-testid="compose-template-body">{selectedTemplate.body}</div>
            ) : channel === "sms" ? (
              <Textarea className="mt-2" placeholder="Type your SMS. You can use {{parent_name}}, {{student_name}}, {{class}}." value={freeBody} onChange={(e) => setFreeBody(e.target.value)} data-testid="compose-free-body" />
            ) : null}

            {promptVars.map((k) => (
              <div key={k} className="mt-3">
                <label className="text-xs font-medium text-slate-400">{VAR_LABEL[k] || k}</label>
                <Input className="mt-1" value={vars[k] || ""} onChange={(e) => setVars((v) => ({ ...v, [k]: e.target.value }))} data-testid={`compose-var-${k}`} />
              </div>
            ))}

            {locked ? (
              <div className="mt-4 rounded-lg bg-slate-50 dark:bg-slate-800/60 px-3 py-2 text-sm text-slate-600 dark:text-slate-300 flex items-center gap-2" data-testid="compose-locked-target">
                <Users size={14} /> Parents of {lockedClassNames.join(", ")}
              </div>
            ) : (
              <>
                <label className="text-xs font-medium text-slate-400 mt-4 block">Send to classes</label>
                <div className="mt-1 grid grid-cols-2 gap-1.5 max-h-40 overflow-y-auto" data-testid="compose-classes">
                  {sortedClasses.map((c) => (
                    <label key={c.id} className="flex items-center gap-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 px-2.5 py-1.5 cursor-pointer">
                      <input type="checkbox" checked={picked.includes(c.id)} onChange={() => toggleClass(c.id)} data-testid={`compose-class-${c.id}`} />
                      <span className="truncate">{c.name}</span>
                      <span className="ml-auto text-xs text-slate-400">{c.student_count}</span>
                    </label>
                  ))}
                </div>
              </>
            )}

            {remaining != null && <p className="text-xs text-slate-400 mt-3">{remaining} {channel} messages remaining this month</p>}
            <Button className="w-full mt-4" onClick={review} disabled={busy} data-testid="compose-review-btn">{busy ? <Loader2 className="animate-spin" size={16} /> : "Review recipients"}</Button>
          </>
        ) : (
          <div data-testid="compose-confirm">
            <div className="rounded-2xl border-2 border-emerald-200 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10 p-4">
              <p className="text-sm font-semibold text-emerald-800 dark:text-emerald-200">Send to {preview.recipient_count} parent(s) via {channel.toUpperCase()}?</p>
              <p className="text-xs text-emerald-700 dark:text-emerald-300 mt-1">{preview.quota_remaining} remaining now → {preview.quota_after} after sending.</p>
              {preview.skipped_count > 0 && <p className="text-xs text-amber-700 dark:text-amber-300 mt-1">{preview.skipped_count} student(s) skipped — no guardian phone on file.</p>}
            </div>
            <div className="mt-3">
              <p className="text-xs font-medium text-slate-400 mb-1">Message preview</p>
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 px-3 py-2 text-sm text-slate-700 dark:text-slate-200 whitespace-pre-wrap" data-testid="compose-preview-text">{preview.preview}</div>
            </div>
            {preview.recipient_count === 0 && <p className="text-sm text-rose-600 mt-3" data-testid="compose-no-recipients">No recipients with a guardian phone in this selection.</p>}
            {preview.would_block && <p className="text-sm text-rose-600 mt-3">Not enough quota for all recipients. Request more or reduce the audience.</p>}
            <div className="flex gap-2 mt-4">
              <Button variant="outline" className="flex-1" onClick={() => setPreview(null)} disabled={busy} data-testid="compose-back-btn">Back</Button>
              <Button className="flex-1" onClick={confirmSend} disabled={busy || preview.recipient_count === 0 || preview.would_block} data-testid="compose-confirm-btn">{busy ? <Loader2 className="animate-spin" size={16} /> : <><Send size={15} className="mr-1.5" /> Send now</>}</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
