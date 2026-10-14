import { useCallback, useEffect, useMemo, useState } from "react";
import { Zap, Search, Trash2, Save, Sparkles, Plus, Pencil } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";

export const fill = (text, vals) => text.replace(/\{(\w+)\}/g, (m, k) => (vals && vals[k] != null && vals[k] !== "" ? vals[k] : m));

export function useQuickReplies() {
  const [d, setD] = useState(null);
  const load = useCallback(() => api.get("/chat/quick-replies").then((r) => setD(r.data)).catch(() => setD({ replies: [] })), []);
  useEffect(() => { load(); }, [load]);
  return [d, load];
}

// Picker shown above the chat composer (staff only). `onPick(text)` gets the filled text.
export function QuickReplyPicker({ threadId, initialQuery = "", draft, onPick, onClose }) {
  const [d, load] = useQuickReplies();
  const [vals, setVals] = useState(null);
  const [q, setQ] = useState(initialQuery);
  useEffect(() => { api.get(`/chat/threads/${threadId}/placeholders`).then((r) => setVals(r.data)).catch(() => setVals({})); }, [threadId]);
  const rows = useMemo(() => (d?.replies || []).filter((r) => `${r.title} ${r.text}`.toLowerCase().includes(q.toLowerCase())), [d, q]);
  const savePersonal = async () => {
    const title = window.prompt("Name this personal quick reply");
    if (!title) return;
    try { await api.post("/chat/quick-replies", { title, text: draft, scope: "personal" }); toast.success("Saved to your quick replies"); load(); } catch (e) { toast.error(errText(e)); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete "${r.title}"?`)) return;
    try { await api.delete(`/chat/quick-replies/${r.id}`); load(); } catch (e) { toast.error(errText(e)); }
  };
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg p-2 space-y-2" data-testid="quick-reply-picker">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Escape" && onClose()} placeholder="Search quick replies…" className="h-8 pl-8 text-sm" data-testid="quick-reply-search" />
        </div>
        {draft?.trim() && <Button size="sm" variant="outline" className="h-8" onClick={savePersonal} title="Save the current message as a personal quick reply" data-testid="quick-reply-save-personal"><Save size={13} /></Button>}
        <Button size="sm" variant="ghost" className="h-8" onClick={onClose} data-testid="quick-reply-close">Close</Button>
      </div>
      <ul className="max-h-56 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
        {!d && <li className="p-3 text-xs text-slate-400">Loading…</li>}
        {d && rows.length === 0 && <li className="p-3 text-xs text-slate-400" data-testid="quick-reply-empty">No quick replies{d.can_manage ? " — add some in Settings → Parent chat" : ""}.</li>}
        {rows.map((r) => (
          <li key={r.id} className="flex items-start gap-2 p-2 hover:bg-slate-50 dark:hover:bg-slate-800/60 rounded-lg">
            <button className="flex-1 text-left" onClick={() => onPick(fill(r.text, vals))} data-testid={`quick-reply-${r.id}`}>
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{r.title} <span className="text-[10px] uppercase text-slate-400">{r.scope === "personal" ? "mine" : "school"}</span></p>
              <p className="text-xs text-slate-500 line-clamp-2">{fill(r.text, vals)}</p>
            </button>
            {r.mine && <button onClick={() => remove(r)} className="text-slate-400 hover:text-rose-600 p-1" data-testid={`quick-reply-delete-${r.id}`}><Trash2 size={12} /></button>}
          </li>
        ))}
      </ul>
    </div>
  );
}

// Settings → Parent chat → Quick replies (school-wide, admin only).
export function QuickRepliesSettingsCard() {
  const [d, load] = useQuickReplies();
  const [edit, setEdit] = useState(null);
  const school = (d?.replies || []).filter((r) => r.scope === "school");
  const save = async () => {
    try {
      if (edit.id) await api.patch(`/chat/quick-replies/${edit.id}`, { title: edit.title, text: edit.text });
      else await api.post("/chat/quick-replies", { ...edit, scope: "school" });
      setEdit(null); load(); toast.success("Saved");
    } catch (e) { toast.error(errText(e)); }
  };
  const suggest = async () => {
    try { const { data } = await api.post("/chat/quick-replies/suggested"); toast.success(data.added ? `Added ${data.added} suggested replies` : "Suggested replies are already there"); load(); } catch (e) { toast.error(errText(e)); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete "${r.title}"?`)) return;
    try { await api.delete(`/chat/quick-replies/${r.id}`); load(); } catch (e) { toast.error(errText(e)); }
  };
  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4" data-testid="quick-replies-settings">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="font-heading text-lg font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Zap size={16} className="text-indigo-600" /> Parent chat · Quick replies</h2>
          <p className="text-sm text-slate-500 mt-1">School-wide replies staff can insert in parent chat (max {d?.max || 50}). Placeholders: {(d?.placeholders || []).map((p) => `{${p}}`).join(" ")}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={suggest} data-testid="quick-replies-suggest-btn"><Sparkles size={14} className="mr-1.5" /> Add suggested replies</Button>
          <Button onClick={() => setEdit({ title: "", text: "" })} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="quick-replies-new-btn"><Plus size={14} className="mr-1.5" /> New</Button>
        </div>
      </div>
      {edit && (
        <div className="rounded-xl border border-indigo-200 dark:border-indigo-500/30 p-3 space-y-2" data-testid="quick-reply-editor">
          <Input value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} placeholder="Title" data-testid="quick-reply-title" />
          <Textarea rows={3} value={edit.text} onChange={(e) => setEdit({ ...edit, text: e.target.value })} placeholder="Dear {parent_name}, …" data-testid="quick-reply-text" />
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setEdit(null)}>Cancel</Button><Button onClick={save} data-testid="quick-reply-save">Save</Button></div>
        </div>
      )}
      <ul className="divide-y divide-slate-100 dark:divide-slate-800" data-testid="quick-replies-list">
        {d && school.length === 0 && <li className="py-4 text-sm text-slate-400">No school-wide quick replies yet.</li>}
        {school.map((r) => (
          <li key={r.id} className="py-2.5 flex items-start justify-between gap-3" data-testid={`quick-reply-row-${r.id}`}>
            <div className="min-w-0"><p className="text-sm font-medium text-slate-800 dark:text-slate-100">{r.title}</p><p className="text-xs text-slate-500 whitespace-pre-wrap">{r.text}</p></div>
            <div className="flex gap-1 shrink-0">
              <Button size="icon" variant="ghost" onClick={() => setEdit(r)} data-testid={`quick-reply-edit-${r.id}`}><Pencil size={13} /></Button>
              <Button size="icon" variant="ghost" onClick={() => remove(r)} data-testid={`quick-reply-remove-${r.id}`}><Trash2 size={13} /></Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
