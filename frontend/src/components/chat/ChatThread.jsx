import { useCallback, useEffect, useRef, useState } from "react";
import { Paperclip, Send, Lock, LockOpen, EyeOff, Eye, Flag, CheckCheck, Check, FileText, X, Loader2, Zap } from "lucide-react";
import { useChatSocket, sendChat, LiveBadge } from "../../lib/chatSocket";
import { QuickReplyPicker } from "./QuickReplies";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";

const API = process.env.REACT_APP_BACKEND_URL;
const MAX = 2000;
const fmt = (iso, tz) => {
  try { return new Intl.DateTimeFormat("en-IN", { timeZone: tz, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(iso)); }
  catch { return iso?.slice(0, 16); }
};

const Attachment = ({ m }) => {
  const url = `${API}/api/chat/messages/${m.id}/attachment`;
  if (m.attachment.content_type?.startsWith("image/"))
    return <a href={url} target="_blank" rel="noreferrer"><img src={url} alt={m.attachment.name} className="mt-2 max-h-48 rounded-lg border border-black/10" data-testid={`chat-attachment-img-${m.id}`} /></a>;
  return (
    <a href={url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-black/5 dark:bg-white/10 px-2.5 py-1.5 text-xs font-medium" data-testid={`chat-attachment-file-${m.id}`}>
      <FileText size={14} /> {m.attachment.name} · {Math.ceil(m.attachment.size / 1024)} KB
    </a>
  );
};

function Bubble({ m, tz, canModerate, onModerate }) {
  const mine = m.mine;
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`} data-testid={`chat-msg-${m.id}`}>
      <div className={`max-w-[82%] rounded-2xl px-3.5 py-2.5 text-sm ${mine ? "bg-indigo-600 text-white rounded-br-md" : "bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100 border border-slate-200 dark:border-slate-700 rounded-bl-md"} ${m.hidden ? "opacity-60" : ""}`}>
        {!mine && <p className="text-[11px] font-semibold mb-0.5 opacity-70">{m.sender_name} · {m.sender_title}</p>}
        {m.hidden && <p className="text-[11px] font-semibold flex items-center gap-1 mb-0.5" data-testid={`chat-hidden-${m.id}`}><EyeOff size={11} /> Hidden{m.hidden_by ? ` by ${m.hidden_by}` : ""}</p>}
        {m.body && <p className="whitespace-pre-wrap break-words">{m.body}</p>}
        {m.attachment && <Attachment m={m} />}
        <div className={`mt-1 flex items-center gap-1.5 text-[10px] ${mine ? "text-white/70 justify-end" : "text-slate-400"}`}>
          {fmt(m.created_at, tz)}
          {mine && (m.seen ? <span className="inline-flex items-center gap-0.5" data-testid={`chat-seen-${m.id}`}><CheckCheck size={12} /> Seen</span> : <Check size={12} />)}
          {canModerate && !mine && (
            <>
              <button onClick={() => onModerate(m, m.hidden ? "unhide" : "hide")} className="hover:text-slate-700" title={m.hidden ? "Unhide" : "Hide"} data-testid={`chat-hide-${m.id}`}>{m.hidden ? <Eye size={11} /> : <EyeOff size={11} />}</button>
              <button onClick={() => onModerate(m, "report")} className="hover:text-rose-600" title="Report" data-testid={`chat-report-${m.id}`}><Flag size={11} /></button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ChatThread({ threadId, onChanged, height = "h-[420px]" }) {
  const [d, setD] = useState(null);
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  const fileRef = useRef(null);
  const count = useRef(0);

  const [typing, setTyping] = useState(null);
  const [qr, setQr] = useState(null);
  const lastTyping = useRef(0);
  const load = useCallback(() => {
    api.get(`/chat/threads/${threadId}`).then((r) => setD(r.data)).catch((e) => setD({ error: errText(e) }));
  }, [threadId]);
  const onEvent = useCallback((ev) => {
    if (ev.thread_id !== threadId) return;
    if (ev.type === "typing") {
      setTyping(ev.name || "Someone");
      clearTimeout(window.__chatTypingT);
      window.__chatTypingT = setTimeout(() => setTyping(null), 4000);
    } else if (["message", "read", "status"].includes(ev.type)) {
      if (ev.type === "message") setTyping(null);
      load(); if (ev.type !== "read") onChanged?.();
    }
  }, [threadId, load, onChanged]);
  const live = useChatSocket(onEvent);
  useEffect(() => { setD(null); load(); }, [load]);
  useEffect(() => {
    if (live === "live") return undefined;
    const iv = setInterval(load, 10000);
    return () => clearInterval(iv);
  }, [live, load]);
  const onType = (v) => {
    setText(v);
    if (d?.can_moderate && v === "/") { setQr(""); return; }
    if (Date.now() - lastTyping.current > 2500 && v.trim()) { lastTyping.current = Date.now(); sendChat({ type: "typing", thread_id: threadId }); }
  };
  useEffect(() => {
    const n = d?.messages?.length || 0;
    if (n !== count.current) { count.current = n; end.current?.scrollIntoView({ block: "end" }); }
  }, [d]);

  const send = async () => {
    if (!text.trim() && !file) return;
    const fd = new FormData();
    fd.append("body", text);
    if (file) fd.append("file", file);
    setBusy(true);
    try {
      const { data } = await api.post(`/chat/threads/${threadId}/messages`, fd);
      setText(""); setFile(null);
      if (data.nudge?.status === "sent") toast.success(`Message sent · parent nudged by ${data.nudge.channel}`);
      load(); onChanged?.();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const pick = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) return toast.error("Attachments can be at most 5 MB");
    if (!/^(image\/(jpeg|png|webp)|application\/pdf)$/.test(f.type)) return toast.error("Attach a JPG, PNG, WEBP image or a PDF");
    setFile(f);
  };
  const setStatus = async (status) => {
    try { await api.post(`/chat/threads/${threadId}/status`, { status }); toast.success(status === "closed" ? "Conversation closed" : "Conversation reopened"); load(); onChanged?.(); }
    catch (e) { toast.error(errText(e)); }
  };
  const moderate = async (m, action) => {
    const reason = action === "unhide" ? "" : window.prompt(action === "hide" ? "Why hide this message? (kept in the audit log)" : "Why report this message?");
    if (reason === null) return;
    try { await api.post(`/chat/messages/${m.id}/moderate`, { action, reason }); toast.success(action === "report" ? "Reported to admins" : "Updated"); load(); }
    catch (e) { toast.error(errText(e)); }
  };

  if (!d) return <div className={`${height} rounded-xl bg-slate-100 dark:bg-slate-800/60 animate-pulse`} />;
  if (d.error) return <p className="py-10 text-center text-sm text-slate-400" data-testid="chat-error">{d.error}</p>;
  const t = d.thread;
  const closed = t.status === "closed";
  return (
    <div className="flex flex-col rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden bg-slate-50 dark:bg-slate-950" data-testid="chat-thread">
      <div className="flex items-center justify-between gap-2 px-4 py-2.5 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate" data-testid="chat-thread-title">{t.student_name} · {t.class_name}{t.section ? ` ${t.section}` : ""}</p>
          <p className="text-[11px] text-slate-500 truncate flex items-center gap-2">{d.can_moderate ? `With ${t.parent_name}` : t.target === "office" ? "School office" : "Class teacher"} · {closed ? "Closed" : "Open"} <LiveBadge status={live} /></p>
        </div>
        {d.can_moderate && (
          <Button size="sm" variant="outline" onClick={() => setStatus(closed ? "open" : "closed")} data-testid="chat-toggle-status">
            {closed ? <><LockOpen size={13} className="mr-1" /> Reopen</> : <><Lock size={13} className="mr-1" /> Close</>}
          </Button>
        )}
      </div>
      <div className={`${height} overflow-y-auto p-4 space-y-3`} data-testid="chat-messages">
        {d.messages.length === 0 && <p className="text-center text-sm text-slate-400 py-10">No messages yet — say hello.</p>}
        {d.messages.map((m) => <Bubble key={m.id} m={m} tz={d.timezone} canModerate={d.can_moderate} onModerate={moderate} />)}
        {typing && <p className="text-xs italic text-slate-500" data-testid="chat-typing">{typing} is typing…</p>}
        <div ref={end} />
      </div>
      {closed ? (
        <p className="px-4 py-3 text-xs text-slate-500 bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800" data-testid="chat-closed-note">
          This conversation is closed.{d.can_moderate ? " Reopen it to reply." : " Start a new message from the Messages page if you need to."}
        </p>
      ) : (
        <div className="p-3 bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 space-y-2">
          {file && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 px-2.5 py-1 text-xs" data-testid="chat-file-chip">
              <Paperclip size={12} /> {file.name} <button onClick={() => setFile(null)} data-testid="chat-file-remove"><X size={12} /></button>
            </span>
          )}
          {qr !== null && (
            <QuickReplyPicker threadId={threadId} initialQuery={qr} draft={text === "/" ? "" : text} onClose={() => { setQr(null); if (text === "/") setText(""); }}
              onPick={(v) => { setText(v.slice(0, MAX)); setQr(null); }} />
          )}
          <div className="flex items-end gap-2">
            {d.can_moderate && <Button size="icon" variant="ghost" onClick={() => setQr(qr === null ? "" : null)} title="Quick replies (or type /)" data-testid="chat-quick-replies-btn"><Zap size={17} /></Button>}
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" className="hidden" onChange={pick} data-testid="chat-file-input" />
            <Button size="icon" variant="ghost" onClick={() => fileRef.current?.click()} title="Attach image or PDF (max 5 MB)" data-testid="chat-attach-btn"><Paperclip size={17} /></Button>
            <div className="flex-1">
              <Textarea rows={2} maxLength={MAX} value={text} onChange={(e) => onType(e.target.value)} placeholder={d.can_moderate ? "Write a message… (type / for quick replies)" : "Write a message…"} className="resize-none"
                onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); }} data-testid="chat-input" />
              <p className="text-[10px] text-slate-400 text-right mt-0.5" data-testid="chat-char-count">{text.length}/{MAX}</p>
            </div>
            <Button onClick={send} disabled={busy || (!text.trim() && !file)} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="chat-send-btn">
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
