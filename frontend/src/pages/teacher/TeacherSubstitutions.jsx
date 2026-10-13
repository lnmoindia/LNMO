import { useCallback, useEffect, useState } from "react";
import { UserX, CalendarRange, Check, X, Plus, CheckCircle2, Clock } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { CancelAbsenceDialog } from "../../components/substitutions/CancelAbsenceDialog";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../components/ui/dialog";

const today = () => new Date().toISOString().slice(0, 10);

export default function TeacherSubstitutions() {
  const { user } = useAuth();
  const [data, setData] = useState({ assigned: [], requests: [] });
  const [mine, setMine] = useState([]);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [cancelFor, setCancelFor] = useState(null);
  const [leave, setLeave] = useState({ date: today(), reason: "" });

  const refresh = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([
        api.get("/me/substitutions"),
        api.get("/absences"),
      ]);
      setData(s.data);
      setMine(a.data.absences);
    } catch (e) { toast.error(errText(e)); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const respond = async (id, accept) => {
    try { await api.post(`/substitutions/${id}/respond`, { accept }); toast.success(accept ? "Accepted" : "Declined"); refresh(); }
    catch (e) { toast.error(errText(e)); }
  };
  const requestLeave = async () => {
    try {
      await api.post("/absences", { teacher_id: user.id, date: leave.date, reason: leave.reason });
      toast.success("Leave requested — awaiting approval");
      setLeaveOpen(false); setLeave({ date: today(), reason: "" });
      refresh();
    } catch (e) { toast.error(errText(e)); }
  };

  return (
    <div className="space-y-6" data-testid="teacher-substitutions">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">Workspace</p>
          <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50">My Substitutions</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Cover requests, your assigned periods, and your leave.</p>
        </div>
        <Button onClick={() => setLeaveOpen(true)} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="request-leave-btn"><Plus size={14} className="mr-1" /> Request leave</Button>
      </div>

      <section className="space-y-3" data-testid="cover-requests">
        <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Clock size={16} className="text-blue-600" /> Cover requests</h2>
        {data.requests.length === 0 ? <p className="text-sm text-slate-400">No pending cover requests.</p> : data.requests.map((s) => (
          <div key={s.id} className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-5 py-3.5 flex items-center justify-between" data-testid={`request-${s.id}`}>
            <div className="text-sm">
              <span className="font-medium text-slate-800 dark:text-slate-200">{s.class_name} {s.section} · {s.subject}</span>
              <span className="text-slate-400"> · {s.date} · P{s.period_no}</span>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white" onClick={() => respond(s.id, true)} data-testid={`accept-${s.id}`}><Check size={13} className="mr-1" /> Accept</Button>
              <Button size="sm" variant="ghost" className="text-red-600" onClick={() => respond(s.id, false)} data-testid={`decline-${s.id}`}><X size={13} className="mr-1" /> Decline</Button>
            </div>
          </div>
        ))}
      </section>

      <section className="space-y-3" data-testid="assigned-subs">
        <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><CheckCircle2 size={16} className="text-emerald-600" /> My assigned cover</h2>
        {data.assigned.length === 0 ? <p className="text-sm text-slate-400">You have no assigned substitutions.</p> : (
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-900/60 text-left"><tr>{["Date", "Period", "Class", "Subject"].map((h) => <th key={h} className="px-4 py-2 text-xs font-semibold uppercase tracking-wider text-slate-500">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {data.assigned.map((s) => (
                  <tr key={s.id} data-testid={`assigned-${s.id}`}>
                    <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300">{s.date}</td>
                    <td className="px-4 py-2.5">P{s.period_no}</td>
                    <td className="px-4 py-2.5 text-slate-700 dark:text-slate-200">{s.class_name} {s.section}</td>
                    <td className="px-4 py-2.5 text-slate-700 dark:text-slate-200">{s.subject}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="space-y-3" data-testid="my-absences">
        <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><UserX size={16} className="text-slate-500" /> My leave</h2>
        {mine.length === 0 ? <p className="text-sm text-slate-400">No leave on record.</p> : (
          <ul className="space-y-1.5 text-sm">
            {mine.map((a) => (
              <li key={a.id} className="flex items-center gap-3" data-testid={`myabs-${a.id}`}>
                <CalendarRange size={13} className="text-slate-400" />
                <span className="text-slate-700 dark:text-slate-200">{a.date}</span>
                {a.reason && <span className="text-slate-400">· {a.reason}</span>}
                <span className={`text-xs px-2 py-0.5 rounded-full ${a.status === "approved" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400" : a.status === "requested" ? "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400" : "bg-slate-100 text-slate-500 dark:bg-slate-800"}`}>{a.status}</span>
                {(a.status === "requested" || a.status === "approved") && a.date > today() && (
                  <Button size="sm" variant="ghost" className="h-7 text-red-600" onClick={() => setCancelFor(a)} data-testid={`cancel-my-leave-${a.id}`}>Cancel leave</Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {cancelFor && <CancelAbsenceDialog absence={{ ...cancelFor, teacher_name: user?.name }} onClose={() => setCancelFor(null)} onDone={() => { setCancelFor(null); refresh(); }} />}
      <Dialog open={leaveOpen} onOpenChange={setLeaveOpen}>
        <DialogContent className="sm:max-w-md" data-testid="leave-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><UserX size={17} className="text-indigo-600" /> Request leave</DialogTitle>
            <DialogDescription>Your principal or admin will approve it and arrange cover.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-1">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Date <span className="text-red-500">*</span></label>
              <Input type="date" value={leave.date} onChange={(e) => setLeave((l) => ({ ...l, date: e.target.value }))} data-testid="leave-date-input" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Reason</label>
              <Input value={leave.reason} onChange={(e) => setLeave((l) => ({ ...l, reason: e.target.value }))} placeholder="Optional" data-testid="leave-reason-input" />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={() => setLeaveOpen(false)}>Cancel</Button>
              <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" disabled={!leave.date} onClick={requestLeave} data-testid="leave-confirm-btn">Request</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
