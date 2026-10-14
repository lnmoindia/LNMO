import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { MessagesSquare, Inbox } from "lucide-react";
import api, { errText } from "../../lib/api";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import ChatThread from "../../components/chat/ChatThread";
import { staffBase } from "./ParentsPage";

const when = (iso, tz) => (iso ? new Intl.DateTimeFormat("en-IN", { timeZone: tz, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(iso)) : "");

export default function ParentMessagesPage() {
  const { pathname } = useLocation();
  const base = staffBase(pathname);
  const [sp, setSp] = useSearchParams();
  const sel = sp.get("t");
  const [cls, setCls] = useState("all");
  const [status, setStatus] = useState("open");
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const load = useCallback(() => {
    api.get("/chat/threads", { params: { class_name: cls === "all" ? "" : cls, status: status === "all" ? "" : status } })
      .then((r) => setD(r.data)).catch((e) => setErr(errText(e)));
  }, [cls, status]);
  useEffect(() => { load(); const iv = setInterval(load, 15000); return () => clearInterval(iv); }, [load]);
  const [classes, setClasses] = useState([]);
  useEffect(() => { if (d && cls === "all") setClasses([...new Set(d.threads.map((t) => t.class_name).filter(Boolean))].sort()); }, [d, cls]);

  if (err) return <p className="py-16 text-center text-slate-400" data-testid="parent-inbox-error">{err}</p>;
  return (
    <div className="space-y-5" data-testid="parent-inbox-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50">Parent messages</h1>
          <p className="text-sm text-slate-500 mt-1">Conversations with parents about their children · unread first. Start one from a parent or student page.</p>
        </div>
        <div className="flex gap-2">
          <Select value={cls} onValueChange={setCls}>
            <SelectTrigger className="w-40" data-testid="inbox-class-filter"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="all">All classes</SelectItem>{classes.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-32" data-testid="inbox-status-filter"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="open">Open</SelectItem><SelectItem value="closed">Closed</SelectItem><SelectItem value="all">All</SelectItem></SelectContent>
          </Select>
        </div>
      </div>
      <div className="grid lg:grid-cols-[340px_1fr] gap-5">
        <ul className={`rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 divide-y divide-slate-100 dark:divide-slate-800/60 overflow-hidden self-start ${sel ? "hidden lg:block" : ""}`} data-testid="inbox-thread-list">
          {!d && <li className="p-6 text-sm text-slate-400">Loading…</li>}
          {d?.threads.length === 0 && <li className="p-10 text-center text-sm text-slate-400"><Inbox className="mx-auto mb-2" />No conversations.</li>}
          {d?.threads.map((t) => (
            <li key={t.id}>
              <button onClick={() => setSp({ t: t.id })} className={`w-full text-left px-4 py-3 ${sel === t.id ? "bg-indigo-50 dark:bg-indigo-500/10" : "hover:bg-slate-50 dark:hover:bg-slate-800/50"}`} data-testid={`inbox-thread-${t.id}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className={`text-sm truncate ${t.unread ? "font-bold text-slate-900 dark:text-white" : "font-medium text-slate-700 dark:text-slate-200"}`}>{t.parent_name} · {t.student_name}</span>
                  {t.unread > 0 && <span className="rounded-full bg-rose-500 text-white text-[10px] font-bold px-1.5 min-w-[18px] text-center" data-testid={`inbox-unread-${t.id}`}>{t.unread}</span>}
                </div>
                <p className="text-xs text-slate-500 truncate mt-0.5">{t.class_name}{t.section ? ` ${t.section}` : ""} · {t.last_sender_role === "parent" ? "Parent: " : ""}{t.last_message_preview || "—"}</p>
                <p className="text-[10px] text-slate-400 mt-0.5">{when(t.last_message_at, d.timezone)} · {t.status}</p>
              </button>
            </li>
          ))}
        </ul>
        <div className={sel ? "" : "hidden lg:block"}>
          {sel ? (
            <>
              <div className="flex items-center justify-between mb-2 text-sm">
                <button onClick={() => setSp({})} className="lg:hidden text-indigo-600" data-testid="inbox-back">← All conversations</button>
                {(() => { const t = d?.threads.find((x) => x.id === sel); return t ? <Link to={`${base}/parents/${t.parent_id}`} className="text-indigo-600 hover:underline ml-auto" data-testid="inbox-open-parent">Open parent profile</Link> : null; })()}
              </div>
              <ChatThread threadId={sel} onChanged={load} height="h-[56vh]" />
            </>
          ) : <div className="rounded-2xl border border-dashed border-slate-300 dark:border-slate-700 h-80 flex flex-col items-center justify-center text-slate-400 text-sm"><MessagesSquare className="mb-2" />Pick a conversation</div>}
        </div>
      </div>
    </div>
  );
}
