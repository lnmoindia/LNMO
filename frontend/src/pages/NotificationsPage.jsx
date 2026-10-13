import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, CheckCheck, UserX, CalendarCheck2, Repeat, CalendarClock, XCircle, CheckCircle2, Clock } from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";

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

export default function NotificationsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isTeacher = user?.role === "teacher" && !user?.is_principal;
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const LIMIT = 25;

  const load = useCallback((reset = false) => {
    const s = reset ? 0 : skip;
    api.get("/notifications", { params: { limit: LIMIT, skip: s } }).then((r) => {
      setTotal(r.data.total);
      setItems((prev) => (reset ? r.data.notifications : [...prev, ...r.data.notifications]));
    }).catch(() => {});
  }, [skip]);

  useEffect(() => { load(true); /* eslint-disable-next-line */ }, []);

  const target = (n) => {
    const t = n.type || "";
    if (t === "timetable_published") return isTeacher ? "/teacher/timetable" : "/app/timetable";
    return isTeacher ? "/teacher/substitutions" : "/app/substitutions";
  };
  const click = async (n) => {
    if (!n.read) { try { await api.post(`/notifications/${n.id}/read`); } catch { /* noop */ } }
    navigate(target(n));
  };
  const markAll = async () => { try { await api.post("/notifications/mark-read", { all: true }); } catch { /* noop */ } load(true); };
  const more = () => { setSkip((s) => s + LIMIT); setTimeout(() => load(false), 0); };

  return (
    <div className="space-y-5 max-w-3xl" data-testid="notifications-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50">Notifications</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{total} total</p>
        </div>
        <Button variant="outline" onClick={markAll} data-testid="notifications-mark-all"><CheckCheck size={14} className="mr-1" /> Mark all read</Button>
      </div>
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 divide-y divide-slate-50 dark:divide-slate-800/60 overflow-hidden">
        {items.length === 0 ? (
          <p className="px-4 py-12 text-center text-sm text-slate-400" data-testid="notifications-empty">No notifications yet.</p>
        ) : items.map((n) => {
          const meta = ICONS[n.type] || { icon: Bell, cls: "text-slate-400" };
          const I = meta.icon;
          return (
            <button key={n.id} onClick={() => click(n)} data-testid={`notification-row-${n.id}`}
              className={`w-full text-left px-5 py-3.5 flex gap-3 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors ${n.read ? "" : "bg-indigo-50/40 dark:bg-indigo-500/5"}`}>
              <I size={18} className={`mt-0.5 shrink-0 ${meta.cls}`} />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium text-slate-800 dark:text-slate-200">{n.title}</span>
                <span className="block text-sm text-slate-500 dark:text-slate-400">{n.body}</span>
                <span className="block text-xs text-slate-400 mt-0.5">{relTime(n.created_at)}</span>
              </span>
              {!n.read && <span className="mt-1.5 h-2 w-2 rounded-full bg-indigo-500 shrink-0" />}
            </button>
          );
        })}
      </div>
      {items.length < total && (
        <div className="text-center">
          <Button variant="outline" onClick={more} data-testid="notifications-load-more">Load more</Button>
        </div>
      )}
    </div>
  );
}
