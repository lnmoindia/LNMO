import { useCallback, useEffect, useState } from "react";
import { Send, Printer, UserCheck, PhoneOff, AlertTriangle, Link2, Loader2, Users } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { printParentSlip, printParentSlips } from "../../lib/printDoc";
import { ChannelPicker, ChannelResults } from "../../components/comm/ChannelPicker";
import { bulkToast, showBulkResult } from "../../components/bulk/BulkResultDialog";
import { Button } from "../../components/ui/button";
import { Checkbox } from "../../components/ui/checkbox";
import { Label } from "../../components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../components/ui/dialog";

export const printSlipFor = async (studentId) => {
  try {
    const { data } = await api.post(`/students/${studentId}/setup-code`);
    printParentSlip({ ...data, setupUrl: `${window.location.origin}/setup/parent` });
  } catch (e) { toast.error(errText(e)); }
};

export const printSlipsFor = async (scope) => {
  try {
    const { data } = await api.post("/students/setup-codes/bulk", scope);
    if (!data.count) { toast.info("No students without a phone (and without a parent account) here"); return; }
    printParentSlips(data.slips, `${window.location.origin}/setup/parent`, data.logo_src);
    toast.success(`${data.count} slip${data.count === 1 ? "" : "s"} ready to print`);
  } catch (e) { toast.error(errText(e)); }
};

const BUCKETS = [
  { key: "invited", label: "Invited", icon: Send, tone: "text-emerald-700 bg-emerald-50 dark:bg-emerald-500/10 dark:text-emerald-400" },
  { key: "already_linked", label: "Already linked", icon: UserCheck, tone: "text-sky-700 bg-sky-50 dark:bg-sky-500/10 dark:text-sky-400" },
  { key: "skipped_no_phone", label: "No phone", icon: PhoneOff, tone: "text-amber-700 bg-amber-50 dark:bg-amber-500/10 dark:text-amber-400" },
  { key: "collisions_for_review", label: "Needs review", icon: AlertTriangle, tone: "text-rose-700 bg-rose-50 dark:bg-rose-500/10 dark:text-rose-400" },
];

const BucketRow = ({ bucket, row }) => (
  <li className="flex items-center justify-between gap-3 py-2 text-sm" data-testid={`invite-row-${bucket}-${row.student_id}`}>
    <div className="min-w-0">
      <p className="font-medium text-slate-800 dark:text-slate-100 truncate">{row.student_name}</p>
      <p className="text-xs text-slate-500">{row.class}{row.phone ? ` · ${row.phone}` : ""}{row.guardian_name ? ` · ${row.guardian_name}` : ""}
        {row.action === "linked_sibling" ? " · linked to sibling's account" : ""}{row.delivery === "failed" ? " · delivery failed" : ""}
        <ChannelResults channels={row.channels} testid={`invite-channels-${row.student_id}`} /></p>
    </div>
    {bucket === "skipped_no_phone" && (
      <Button size="sm" variant="outline" onClick={() => printSlipFor(row.student_id)} data-testid={`print-slip-${row.student_id}`}>
        <Printer size={13} className="mr-1" /> Paper slip
      </Button>
    )}
  </li>
);

const Results = ({ result, scope }) => {
  const [tab, setTab] = useState("invited");
  return (
    <div data-testid="invite-results">
      {result.items && <div className="flex justify-end mb-2"><Button size="sm" variant="outline" onClick={() => showBulkResult({ title: "Parent invites", ...result })} data-testid="invite-view-details">View details</Button></div>}
      {result.skipped_no_phone.length > 0 && (
        <div className="flex justify-end mb-2">
          <Button size="sm" variant="outline" onClick={() => printSlipsFor(scope)} data-testid="print-all-slips-btn">
            <Printer size={13} className="mr-1" /> Print all slips ({result.skipped_no_phone.length})
          </Button>
        </div>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {BUCKETS.map(({ key, label, icon: Icon, tone }) => (
          <button key={key} onClick={() => setTab(key)} data-testid={`invite-bucket-${key}`}
            className={`rounded-lg p-3 text-left border transition-colors ${tab === key ? "border-indigo-500" : "border-transparent"} ${tone}`}>
            <Icon size={15} />
            <p className="text-xl font-bold mt-1" data-testid={`invite-count-${key}`}>{result[key].length}</p>
            <p className="text-xs">{label}</p>
          </button>
        ))}
      </div>
      <ul className="mt-3 max-h-64 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
        {result[tab].length === 0 && <li className="py-6 text-center text-sm text-slate-400">Nothing here.</li>}
        {result[tab].map((r) => <BucketRow key={r.student_id} bucket={tab} row={r} />)}
      </ul>
    </div>
  );
};

export function InviteParentsDialog({ open, onClose, classes, onDone }) {
  const [all, setAll] = useState(true);
  const [picked, setPicked] = useState([]);
  const [channels, setChannels] = useState(["whatsapp"]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  useEffect(() => { if (open) { setResult(null); setPicked([]); setAll(true); } }, [open]);
  const toggle = (v) => setPicked((p) => (p.includes(v) ? p.filter((x) => x !== v) : [...p, v]));
  const run = async () => {
    setBusy(true);
    try {
      const body = all ? { all: true, channels } : { class_names: picked, channels };
      const { data } = await api.post("/students/invite-parents", body);
      setResult(data);
      bulkToast(toast, { title: "Parent invites", ...data }, null, "Invites: ");
      onDone?.();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl" data-testid="invite-parents-dialog">
        <DialogHeader>
          <DialogTitle>Invite parents</DialogTitle>
          <DialogDescription>One account per guardian phone — siblings are linked automatically. Invites count toward your message quota.</DialogDescription>
        </DialogHeader>
        {!result ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Checkbox id="inv-all" checked={all} onCheckedChange={(v) => setAll(Boolean(v))} data-testid="invite-scope-all" />
              <Label htmlFor="inv-all">All classes in my scope</Label>
            </div>
            {!all && (
              <div className="grid grid-cols-3 gap-2 max-h-48 overflow-y-auto" data-testid="invite-class-picker">
                {classes.map((c) => (
                  <label key={c.value} className="flex items-center gap-2 text-sm rounded-md border border-slate-200 dark:border-slate-700 px-2 py-1.5 cursor-pointer">
                    <Checkbox checked={picked.includes(c.value)} onCheckedChange={() => toggle(c.value)} data-testid={`invite-class-${c.value}`} /> {c.label}
                  </label>
                ))}
              </div>
            )}
            <ChannelPicker value={channels} onChange={setChannels} prefix="invite" />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={onClose} data-testid="invite-cancel-btn">Cancel</Button>
              <Button disabled={busy || channels.length === 0 || (!all && picked.length === 0)} onClick={run} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="invite-run-btn">
                {busy ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <Send size={14} className="mr-1.5" />} Send invites
              </Button>
            </div>
          </div>
        ) : (
          <>
            <Results result={result} scope={all ? { all: true } : { class_names: picked }} />
            <div className="flex justify-end"><Button onClick={onClose} data-testid="invite-done-btn">Done</Button></div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

const ReviewGroups = ({ groups, onChanged }) => {
  const act = async (g, action) => {
    try {
      await api.post("/students/invite-review/resolve", { phone: g.phone, action, student_ids: g.students.map((s) => s.student_id) });
      toast.success(action === "dismiss" ? "Dismissed" : "Linked to one parent account");
      onChanged();
    } catch (e) { toast.error(errText(e)); }
  };
  return groups.map((g) => (
    <div key={g.phone} className="rounded-lg border border-rose-200 dark:border-rose-500/30 p-3" data-testid={`review-group-${g.phone}`}>
      <p className="text-sm font-medium text-rose-700 dark:text-rose-300">Phone {g.phone} shared by different guardian names</p>
      <ul className="text-xs text-slate-600 dark:text-slate-300 mt-1 space-y-0.5">
        {g.students.map((s) => <li key={s.student_id}>{s.student_name} ({s.class}) — guardian: {s.guardian_name || "—"}</li>)}
      </ul>
      <div className="flex gap-2 mt-2">
        <Button size="sm" variant="outline" onClick={() => act(g, "force_link")} data-testid={`review-force-${g.phone}`}><Link2 size={13} className="mr-1" /> Same family — link</Button>
        <Button size="sm" variant="ghost" onClick={() => act(g, "dismiss")} data-testid={`review-dismiss-${g.phone}`}>Dismiss</Button>
      </div>
    </div>
  ));
};

export function ReadyToInvitePanel({ refreshKey }) {
  const [ready, setReady] = useState([]);
  const [review, setReview] = useState([]);
  const [busy, setBusy] = useState("");
  const [channels, setChannels] = useState(["whatsapp"]);
  const load = useCallback(async () => {
    try {
      const [r, v] = await Promise.all([api.get("/students/ready-to-invite"), api.get("/students/invite-review")]);
      setReady(r.data.ready); setReview(v.data.review);
    } catch { /* panel is advisory */ }
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);
  const inviteOne = async (sid) => {
    setBusy(sid);
    try {
      const { data } = await api.post(`/students/${sid}/invite-parent`, { channels });
      const per = data.invited[0]?.channels;
      toast.success(data.invited.length ? `Invite ${data.invited[0].delivery}${per ? ` · ${Object.entries(per).filter(([k]) => !k.startsWith("email_")).map(([k, v]) => `${k}: ${v.replace("skipped_", "")}`).join(", ")}` : ""}` : "No invite needed");
      load();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(""); }
  };
  const inviteAll = async () => {
    setBusy("all");
    for (const r of ready) {
      try { await api.post(`/students/${r.student_id}/invite-parent`, { channels }); } catch { /* reported below */ }
    }
    setBusy(""); toast.success("Invites sent"); load();
  };
  if (!ready.length && !review.length) return null;
  return (
    <div className="rounded-xl border border-indigo-200 dark:border-indigo-500/30 bg-indigo-50/50 dark:bg-indigo-500/5 p-4 space-y-3" data-testid="ready-to-invite-panel">
      {ready.length > 0 && (
        <>
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-indigo-900 dark:text-indigo-200 flex items-center gap-2">
              <Users size={15} /> Ready to invite <span data-testid="ready-to-invite-count">({ready.length})</span>
              <span className="font-normal text-xs text-slate-500">enrolled · guardian phone on file · no parent account yet</span>
            </p>
            <Button size="sm" disabled={busy === "all" || !channels.length} onClick={inviteAll} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="invite-all-ready-btn">Invite all</Button>
          </div>
          <ChannelPicker value={channels} onChange={setChannels} prefix="ready" />
          <ul className="divide-y divide-indigo-100 dark:divide-indigo-500/20 max-h-48 overflow-y-auto">
            {ready.map((r) => (
              <li key={r.student_id} className="flex items-center justify-between py-1.5 text-sm" data-testid={`ready-row-${r.student_id}`}>
                <span className="text-slate-800 dark:text-slate-100">{r.student_name} <span className="text-xs text-slate-500">· {r.class} · {r.phone}</span>
                  {!r.has_email && channels.includes("email") && <span className="ml-1.5 rounded bg-slate-100 dark:bg-slate-800 px-1.5 text-[10px] text-slate-500" data-testid={`ready-no-email-${r.student_id}`}>no email</span>}</span>
                <Button size="sm" variant="outline" disabled={busy === r.student_id || !channels.length} onClick={() => inviteOne(r.student_id)} data-testid={`ready-invite-${r.student_id}`}>
                  <Send size={12} className="mr-1" /> Invite
                </Button>
              </li>
            ))}
          </ul>
        </>
      )}
      {review.length > 0 && (
        <div className="space-y-2" data-testid="invite-review-panel">
          <p className="text-sm font-semibold text-rose-800 dark:text-rose-300 flex items-center gap-2"><AlertTriangle size={15} /> Needs review ({review.length})</p>
          <ReviewGroups groups={review} onChanged={load} />
        </div>
      )}
    </div>
  );
}
