import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { MessageSquare, Plus, Send, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Textarea } from "../../components/ui/textarea";
import { PCard, PEmpty } from "../portal/PortalShell";
import ChatThread from "../../components/chat/ChatThread";
import { useChatSocket } from "../../lib/chatSocket";

const fullName = (c) => `${c?.first_name || ""} ${c?.last_name || ""}`.trim();

function NewMessage({ kids, onSent, onCancel, childId }) {
  const [child, setChild] = useState(childId || kids[0]?.id || "");
  const [target, setTarget] = useState("class_teacher");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const send = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("student_id", child); fd.append("target", target); fd.append("body", text);
      const { data } = await api.post("/chat/threads", fd);
      toast.success("Message sent"); onSent(data.thread.id);
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const sel = "w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm";
  return (
    <PCard title="New message" icon={Plus} testid="parent-new-message">
      <div className="p-4 space-y-3">
        <div className="grid sm:grid-cols-2 gap-3">
          <label className="text-xs font-semibold text-slate-500 space-y-1">About
            <select value={child} onChange={(e) => setChild(e.target.value)} className={sel} data-testid="parent-new-child">
              {kids.map((c) => <option key={c.id} value={c.id}>{fullName(c)} · {c.class_name}{c.section ? ` ${c.section}` : ""}</option>)}
            </select>
          </label>
          <label className="text-xs font-semibold text-slate-500 space-y-1">To
            <select value={target} onChange={(e) => setTarget(e.target.value)} className={sel} data-testid="parent-new-target">
              <option value="class_teacher">Class teacher</option><option value="office">School office</option>
            </select>
          </label>
        </div>
        <Textarea rows={3} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} placeholder="Write your message…" data-testid="parent-new-body" />
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel} data-testid="parent-new-cancel">Cancel</Button>
          <Button disabled={busy || !text.trim() || !child} onClick={send} className="bg-[var(--brand)] hover:opacity-90 text-white" data-testid="parent-new-send">
            {busy ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <Send size={14} className="mr-1.5" />} Send
          </Button>
        </div>
      </div>
    </PCard>
  );
}

export default function ParentMessages({ kids, childId }) {
  const [sp, setSp] = useSearchParams();
  const sel = sp.get("t");
  const [d, setD] = useState(null);
  const [composing, setComposing] = useState(!!sp.get("compose"));
  const load = useCallback(() => { api.get("/chat/threads", { params: { status: "", student_id: childId || "" } }).then((r) => setD(r.data)).catch(() => setD({ threads: [] })); }, [childId]);
  const kid = kids.find((k) => k.id === childId);
  const live = useChatSocket(useCallback((ev) => { if (ev.type === "unread" || ev.type === "message") load(); }, [load]));
  useEffect(() => { load(); if (live === "live") return undefined; const iv = setInterval(load, 15000); return () => clearInterval(iv); }, [load, live]);
  const open = (id) => { const n = new URLSearchParams(sp); n.set("t", id); setSp(n); };
  const back = () => { const n = new URLSearchParams(sp); n.delete("t"); setSp(n); load(); };

  if (sel) return (
    <div className="space-y-3" data-testid="parent-thread-view">
      <button onClick={back} className="text-sm font-medium text-[var(--brand-ink)]" data-testid="parent-thread-back">← All messages</button>
      <ChatThread threadId={sel} onChanged={load} height="h-[52vh]" />
    </div>
  );
  return (
    <div className="space-y-4" data-testid="parent-messages">
      {composing ? <NewMessage kids={kids} childId={childId} onCancel={() => setComposing(false)} onSent={(id) => { setComposing(false); open(id); }} /> : (
        <div className="flex justify-end">
          <Button onClick={() => setComposing(true)} disabled={!kids.length} className="bg-[var(--brand)] hover:opacity-90 text-white" data-testid="parent-new-message-btn"><Plus size={14} className="mr-1" /> New message</Button>
        </div>
      )}
      <PCard title={kid ? `Conversations · ${kid.first_name}` : "Conversations"} icon={MessageSquare} testid="parent-thread-list">
        {!d ? <div className="h-24 animate-pulse" /> : d.threads.length === 0 ? <PEmpty icon={MessageSquare} text={kid ? `No messages about ${kid.first_name} yet. Write to the class teacher or the school office.` : "No messages yet. Write to your child's class teacher or the school office."} /> : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {d.threads.map((t) => (
              <li key={t.id}>
                <button onClick={() => open(t.id)} className="w-full text-left px-5 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/40" data-testid={`parent-thread-${t.id}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-sm ${t.unread ? "font-bold text-slate-900 dark:text-white" : "font-medium text-slate-700 dark:text-slate-200"}`}>{t.student_name} · {t.target === "office" ? "School office" : "Class teacher"}</span>
                    {t.unread > 0 && <span className="rounded-full bg-rose-500 text-white text-[10px] font-bold px-1.5 min-w-[18px] text-center" data-testid={`parent-thread-unread-${t.id}`}>{t.unread}</span>}
                  </div>
                  <p className="text-xs text-slate-500 truncate mt-0.5">{t.last_message_preview || "—"}{t.status === "closed" ? " · closed" : ""}</p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </PCard>
    </div>
  );
}
