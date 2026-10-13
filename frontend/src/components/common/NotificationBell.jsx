import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bell, CheckCheck, UserX, CalendarCheck2, Repeat, CalendarClock, XCircle, CheckCircle2, Clock,
} from "lucide-react";
import api from "../../lib/api";
import { useAuth } from "../../context/AuthContext";

const ICONS = {
  absence_request: { icon: UserX, cls: "text-amber-500" },
  absence_approved: { icon: CheckCircle2, cls: "text-emerald-500" },
  absence_rejected: { icon: XCircle, cls: "text-red-500" },
  sub_requested: { icon: Clock, cls: "text-blue-500" },
  sub_request_closed: { icon: XCircle, cls: "text-slate-400" },
  sub_assigned: { icon: Repeat, cls: "text-violet-500" },
  sub_cancelled: { icon: XCircle, cls: "text-slate-400" },
  sub_response: { icon: CalendarCheck2, cls: "text-blue-500" },
  timetable_published: { icon: CalendarClock, cls: "text-indigo-500" },
};

const relTime = (iso) => {
  const s = Math.max(1, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

export default function NotificationBell() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isTeacher = user?.role === "teacher" && !user?.is_principal;
  const [open, setOpen] = useState(false);
  const [data, setData] = useState({ notifications: [], unread: 0 });
  const ref = useRef(null);

  const target = useCallback((n) => {
    const t = n.type || "";
    if (t.startsWith("absence") || t.startsWith("sub_"))
      return isTeacher ? "/teacher/substitutions" : "/app/substitutions";
    if (t === "timetable_published") return isTeacher ? "/teacher/timetable" : "/app/timetable";
    return isTeacher ? "/teacher/substitutions" : "/app/substitutions";
  }, [isTeacher]);

  const load = useCallback(() => {
    api.get("/notifications", { params: { limit: 12 } }).then((r) => setData(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const iv = setInterval(load, 45000);
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => { clearInterval(iv); window.removeEventListener("focus", onFocus); };
  }, [load]);

  useEffect(() => {
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const openPanel = () => { setOpen((o) => !o); if (!open) load(); };

  const clickItem = async (n) => {
    setOpen(false);
    if (!n.read) { try { await api.post(`/notifications/${n.id}/read`); } catch { /* noop */ } load(); }
    navigate(target(n));
  };

  const markAll = async () => { try { await api.post("/notifications/mark-read", { all: true }); } catch { /* noop */ } load(); };

  return (
    <div className="relative" ref={ref}>
      <button data-testid="notification-bell-btn" onClick={openPanel}
        className="relative h-9 w-9 rounded-lg flex items-center justify-center text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
        <Bell size={17} />
        {data.unread > 0 && (
          <span data-testid="notification-unread-badge"
            className="absolute -top-0.5 -right-0.5 min-w-[17px] h-[17px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
            {data.unread > 9 ? "9+" : data.unread}
          </span>
        )}
      </button>

      {open && (
        <div data-testid="notification-panel"
          className="absolute right-0 mt-2 w-80 max-w-[90vw] rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xl z-50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-100 dark:border-slate-800">
            <span className="font-heading font-semibold text-sm text-slate-900 dark:text-slate-50">Notifications</span>
            <button onClick={markAll} data-testid="notification-mark-all" className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline inline-flex items-center gap-1">
              <CheckCheck size={13} /> Mark all read
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto divide-y divide-slate-50 dark:divide-slate-800/60">
            {data.notifications.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-slate-400" data-testid="notification-empty">You're all caught up.</p>
            ) : data.notifications.map((n) => {
              const meta = ICONS[n.type] || { icon: Bell, cls: "text-slate-400" };
              const I = meta.icon;
              return (
                <button key={n.id} onClick={() => clickItem(n)} data-testid={`notification-item-${n.id}`}
                  className={`w-full text-left px-4 py-3 flex gap-3 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors ${n.read ? "" : "bg-indigo-50/40 dark:bg-indigo-500/5"}`}>
                  <I size={16} className={`mt-0.5 shrink-0 ${meta.cls}`} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{n.title}</span>
                    <span className="block text-xs text-slate-500 dark:text-slate-400 line-clamp-2">{n.body}</span>
                    <span className="block text-[11px] text-slate-400 mt-0.5">{relTime(n.created_at)}</span>
                  </span>
                  {!n.read && <span className="mt-1 h-2 w-2 rounded-full bg-indigo-500 shrink-0" />}
                </button>
              );
            })}
          </div>
          <button onClick={() => { setOpen(false); navigate(isTeacher ? "/teacher/notifications" : "/app/notifications"); }}
            data-testid="notification-view-all"
            className="w-full px-4 py-2.5 text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:bg-slate-50 dark:hover:bg-slate-800/40 border-t border-slate-100 dark:border-slate-800 transition-colors">
            View all
          </button>
        </div>
      )}
    </div>
  );
}
