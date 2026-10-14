import { useCallback, useEffect, useState } from "react";
import { BellRing, ChevronDown, Printer, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { printSlipsFor } from "./ParentInvites";
import { ChannelPicker } from "../../components/comm/ChannelPicker";
import { bulkToast } from "../../components/bulk/BulkResultDialog";

const Seg = ({ value, total, className }) => (
  <div className={`h-full ${className}`} style={{ width: `${total ? (value / total) * 100 : 0}%` }} />
);

const Funnel = ({ row }) => (
  <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden flex" title="completed · pending · not invited · no phone">
    <Seg value={row.setup_completed} total={row.enrolled} className="bg-emerald-500" />
    <Seg value={row.pending} total={row.enrolled} className="bg-amber-400" />
    <Seg value={row.not_invited} total={row.enrolled} className="bg-indigo-300" />
    <Seg value={row.no_phone} total={row.enrolled} className="bg-rose-300" />
  </div>
);

const Stat = ({ label, value, tone, testid }) => (
  <span className="text-xs text-slate-500 whitespace-nowrap"><b className={tone} data-testid={testid}>{value}</b> {label}</span>
);

const ClassRow = ({ row, busy, onRemind }) => (
  <li className="py-3 grid grid-cols-1 md:grid-cols-[140px_1fr_auto] gap-2 md:gap-4 items-center" data-testid={`progress-row-${row.class_name}`}>
    <p className="font-medium text-sm text-slate-800 dark:text-slate-100">{row.class_name} <span className="text-xs text-slate-400">· {row.enrolled}</span></p>
    <div className="space-y-1.5">
      <Funnel row={row} />
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        <Stat label="invited" value={row.invited} tone="text-slate-700 dark:text-slate-200" testid={`progress-invited-${row.class_name}`} />
        <Stat label="set up" value={row.setup_completed} tone="text-emerald-600" testid={`progress-completed-${row.class_name}`} />
        <Stat label="pending" value={row.pending} tone="text-amber-600" testid={`progress-pending-${row.class_name}`} />
        <Stat label="not invited" value={row.not_invited} tone="text-indigo-500" testid={`progress-notinvited-${row.class_name}`} />
        <Stat label="no phone" value={row.no_phone} tone="text-rose-500" testid={`progress-nophone-${row.class_name}`} />
        {row.linked_other > 0 && <Stat label="linked manually" value={row.linked_other} tone="text-slate-500" testid={`progress-other-${row.class_name}`} />}
      </div>
    </div>
    <div className="flex gap-2 md:justify-end">
      <Button size="sm" variant="outline" disabled={!row.pending || row.reminder_sent_today || busy === row.class_id}
        onClick={() => onRemind(row)} data-testid={`progress-remind-${row.class_name}`}>
        <BellRing size={13} className="mr-1" /> {row.reminder_sent_today ? "Reminded today" : "Send reminder"}
      </Button>
      <Button size="sm" variant="ghost" disabled={!row.no_phone} onClick={() => printSlipsFor({ class_ids: [row.class_id] })} data-testid={`progress-slips-${row.class_name}`}>
        <Printer size={13} className="mr-1" /> Slips
      </Button>
    </div>
  </li>
);

export function OnboardingProgress({ refreshKey }) {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const [channels, setChannels] = useState(["whatsapp"]);
  const load = useCallback(async () => {
    try { const { data } = await api.get("/students/invite-progress"); setRows(data.classes); } catch { /* advisory */ }
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);
  const remind = async (row) => {
    setBusy(row.class_id);
    try {
      if (!channels.length) { toast.error("Pick at least one channel"); return; }
      const { data } = await api.post("/students/invite-reminder", { class_id: row.class_id, channels });
      const skipped = (data.results || []).filter((r) => Object.values(r.channels).some((v) => String(v).startsWith("skipped"))).length;
      if (data.ok) bulkToast(toast, { title: `Invite reminders · ${row.class_name}`, ...data }, null, `Reminder sent to ${data.sent} parent${data.sent === 1 ? "" : "s"}${skipped ? ` (${skipped} skipped on some channels)` : ""} — `);
      else toast.info(data.message);
      load();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(""); }
  };
  const t = rows.reduce((a, r) => ({ enrolled: a.enrolled + r.enrolled, done: a.done + r.setup_completed, pending: a.pending + r.pending }), { enrolled: 0, done: 0, pending: 0 });
  if (!rows.length) return null;
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm" data-testid="onboarding-progress-panel">
      <button className="w-full flex items-center justify-between gap-3 p-4 text-left" onClick={() => setOpen((o) => !o)} data-testid="onboarding-progress-toggle">
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
          <TrendingUp size={15} className="text-emerald-600" /> Parent onboarding
          <span className="font-normal text-xs text-slate-500" data-testid="onboarding-progress-summary">{t.done} set up · {t.pending} pending · {t.enrolled} enrolled</span>
        </span>
        <ChevronDown size={16} className={`text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="px-4 pt-3 border-t border-slate-100 dark:border-slate-800"><ChannelPicker value={channels} onChange={setChannels} prefix="reminder" note="Reminders go to parents who were invited but haven't set up yet, on each channel you pick." /></div>
      )}
      {open && (
        <ul className="px-4 pb-2 divide-y divide-slate-100 dark:divide-slate-800 border-t border-slate-100 dark:border-slate-800" data-testid="onboarding-progress-list">
          {rows.map((r) => <ClassRow key={r.class_id} row={r} busy={busy} onRemind={remind} />)}
        </ul>
      )}
    </div>
  );
}
