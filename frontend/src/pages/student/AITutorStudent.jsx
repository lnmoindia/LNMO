import { useEffect, useRef, useState } from "react";
import { Sparkles, Lock, Send, Loader2, BookOpen, FileText, Plus, MessageSquare, GraduationCap } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";

const API = process.env.REACT_APP_BACKEND_URL;

export function AITutorStudent() {
  const [subjects, setSubjects] = useState([]);
  const [layerOff, setLayerOff] = useState(false);
  const [subject, setSubject] = useState(null);
  const [chats, setChats] = useState([]);
  const [chatId, setChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef(null);

  useEffect(() => { api.get("/ai/tutor/subjects").then((r) => { setSubjects(r.data.subjects || []); setLayerOff(r.data.ai_layer_enabled === false); }).catch((e) => toast.error(errText(e))); }, []);
  useEffect(() => { if (subject) api.get(`/ai/tutor/chats?subject=${encodeURIComponent(subject)}`).then((r) => setChats(r.data.chats || [])).catch(() => {}); }, [subject]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, sending]);

  const openChat = async (id) => {
    setChatId(id);
    const { data } = await api.get(`/ai/tutor/chat/${id}`);
    setMessages(data.messages || []);
  };
  const newChat = () => { setChatId(null); setMessages([]); };

  const send = async () => {
    const msg = input.trim();
    if (!msg) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setSending(true);
    try {
      const { data } = await api.post("/ai/tutor/chat", { subject, message: msg, chat_id: chatId });
      setChatId(data.chat_id);
      setMessages((m) => [...m, { role: "assistant", content: data.answer, grounded: data.grounded, used_item_titles: data.used_item_titles }]);
      api.get(`/ai/tutor/chats?subject=${encodeURIComponent(subject)}`).then((r) => setChats(r.data.chats || []));
    } catch (e) {
      toast.error(errText(e));
      setMessages((m) => m.slice(0, -1));
    } finally { setSending(false); }
  };

  if (!subject) {
    return (
      <div data-testid="ai-tutor-student">
        <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Sparkles className="text-violet-600" size={20} /> AI Tutor</h2>
        <p className="text-sm text-slate-500 mt-1 mb-4">Pick a subject to start learning. Enabled subjects have your teachers' approved materials.</p>
        {layerOff && (
          <div className="rounded-xl border-2 border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 p-4 mb-4 flex items-center gap-3" data-testid="ai-layer-disabled-banner">
            <Lock className="text-amber-600 shrink-0" size={18} />
            <p className="text-sm text-amber-800 dark:text-amber-200">The AI Tutor isn't available for your school right now. Please check back later.</p>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {subjects.map((s) => (
            <button key={s.subject} disabled={!s.enabled} onClick={() => s.enabled && setSubject(s.subject)}
              data-testid={`ai-subject-${s.subject}`}
              className={`text-left rounded-2xl border-2 p-4 transition-all ${s.enabled ? "border-violet-200 dark:border-violet-800 bg-white dark:bg-slate-900 hover:border-violet-400 hover:shadow-md" : "border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 opacity-70 cursor-not-allowed"}`}>
              <div className="flex items-center justify-between">
                <GraduationCap size={20} className={s.enabled ? "text-violet-500" : "text-slate-400"} />
                {s.enabled ? <Sparkles size={14} className="text-violet-500" /> : <Lock size={14} className="text-slate-400" />}
              </div>
              <p className="mt-2 font-heading font-semibold text-slate-800 dark:text-slate-100">{s.subject}</p>
              <p className="text-xs text-slate-400 mt-0.5">{s.enabled ? "Tap to start" : "Not enabled yet"}</p>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col lg:flex-row gap-4 h-[calc(100vh-220px)] min-h-[520px]" data-testid="ai-tutor-chat">
      <aside className="lg:w-60 shrink-0 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 flex flex-col">
        <div className="flex items-center justify-between mb-2">
          <button onClick={() => setSubject(null)} className="text-xs text-slate-500 hover:text-violet-600">← Subjects</button>
          <Button size="sm" variant="outline" onClick={newChat} data-testid="ai-new-chat"><Plus size={13} className="mr-1" /> New</Button>
        </div>
        <p className="font-heading font-bold text-slate-800 dark:text-slate-100 px-1">{subject}</p>
        <div className="mt-2 space-y-1 overflow-y-auto">
          {chats.map((c) => (
            <button key={c.chat_id} onClick={() => openChat(c.chat_id)} data-testid={`ai-chat-${c.chat_id}`}
              className={`w-full text-left px-2.5 py-2 rounded-lg text-xs flex items-center gap-1.5 ${chatId === c.chat_id ? "bg-violet-50 dark:bg-violet-500/10 text-violet-700 dark:text-violet-300" : "text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"}`}>
              <MessageSquare size={12} /> <span className="truncate">{c.preview || "New chat"}</span>
            </button>
          ))}
        </div>
      </aside>

      <section className="flex-1 flex flex-col rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4 space-y-4" data-testid="ai-messages">
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center text-slate-400">
              <Sparkles size={34} className="text-violet-300" />
              <p className="mt-2 text-sm">Ask me anything about {subject}. I'll use your school's approved materials first.</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap ${m.role === "user" ? "bg-violet-600 text-white" : "bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-100"}`} data-testid={`ai-msg-${m.role}`}>
                {m.content}
                {m.role === "assistant" && m.grounded && m.used_item_titles?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5" data-testid="ai-based-on">
                    {m.used_item_titles.map((t, j) => (
                      <span key={j} className="inline-flex items-center gap-1 text-[10px] rounded-full bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300 px-2 py-0.5">
                        <BookOpen size={9} /> Based on: {t.title}{t.contributor_name ? ` — ${t.contributor_name}` : ""}
                      </span>
                    ))}
                  </div>
                )}
                {m.role === "assistant" && m.grounded === false && (
                  <p className="mt-2 text-[10px] text-amber-600 dark:text-amber-400 flex items-center gap-1" data-testid="ai-general-note">⚠ General explanation — not from your school's materials</p>
                )}
              </div>
            </div>
          ))}
          {sending && <div className="flex justify-start"><div className="rounded-2xl px-4 py-2.5 bg-slate-100 dark:bg-slate-800 text-slate-500 text-sm flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Thinking…</div></div>}
          <div ref={endRef} />
        </div>
        <div className="border-t border-slate-100 dark:border-slate-800 p-3 flex gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && !sending && send()}
            placeholder={`Ask about ${subject}…`} data-testid="ai-input"
            className="flex-1 rounded-xl border border-slate-300 dark:border-slate-700 bg-transparent px-3 py-2 text-sm focus:outline-none focus:border-violet-500" />
          <Button onClick={send} disabled={sending || !input.trim()} data-testid="ai-send"><Send size={16} /></Button>
        </div>
      </section>
    </div>
  );
}

export function AILibraryStudent() {
  const [lib, setLib] = useState(null);
  useEffect(() => { api.get("/ai/library").then((r) => setLib(r.data)).catch((e) => toast.error(errText(e))); }, []);
  if (!lib) return <p className="text-sm text-slate-400">Loading…</p>;
  return (
    <div data-testid="ai-library">
      <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2"><BookOpen className="text-violet-600" size={20} /> Resource Library</h2>
      <p className="text-sm text-slate-500 mt-1 mb-4">Approved materials for {lib.class_name}, organised by subject and chapter.</p>
      {lib.subjects.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 dark:border-slate-700 p-10 text-center text-slate-400">No materials available yet.</div>}
      {lib.subjects.map((s) => (
        <div key={s.curriculum_id} className="mb-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid={`ai-lib-${s.subject}`}>
          <h3 className="font-heading font-bold text-slate-800 dark:text-slate-100">{s.subject}</h3>
          {s.chapters.map((ch) => (
            <div key={ch.chapter} className="mt-3">
              <p className="text-sm font-semibold text-violet-700 dark:text-violet-300">{ch.chapter}</p>
              <ul className="mt-1.5 space-y-1.5">
                {ch.materials.map((m) => (
                  <li key={m.id} className="flex items-center gap-2 text-sm" data-testid={`ai-lib-item-${m.id}`}>
                    <span className="text-[10px] uppercase font-bold text-slate-400 w-24 shrink-0">{m.item_type.replace("_", " ")}</span>
                    <span className="text-slate-700 dark:text-slate-200">{m.title || m.topic}</span>
                    {m.has_file && <a href={`${API}/api/ai/items/${m.id}/file`} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline inline-flex items-center gap-0.5"><FileText size={12} /> {m.file_name}</a>}
                    <span className="ml-auto text-xs text-slate-400">{m.contributor_name}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
