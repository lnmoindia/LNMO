import { useCallback, useEffect, useState } from "react";
import { KeyRound, LockOpen, Mail } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../../components/ui/dialog";
import { LockedBadge } from "../../../components/common/AccountLock";
import { Card, Empty, SkeletonGrid, StatusPill, fmtDate } from "./ui";

function ResetDialog({ admin, iid, onClose, onDone }) {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { setRes(null); setErr(""); }, [admin]);
  const send = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/platform/institutions/${iid}/admins/${admin.id}/password-reset`);
      setRes(data); toast.success(`Reset email sent to ${data.sent_to}`); onDone();
    } catch (e) { setErr(errText(e)); toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={!!admin} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="reset-dialog">
        <DialogHeader><DialogTitle>Send password reset</DialogTitle>
          <DialogDescription>Emails {admin?.name} ({admin?.email}) a single-use link, valid for 24 hours, to set a new password. Any earlier link stops working. You never see the password.</DialogDescription></DialogHeader>
        {res && <div className="rounded-lg bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-800 p-3 text-sm text-emerald-800 dark:text-emerald-200" data-testid="reset-result">
          Sent via Resend to <b>{res.sent_to}</b>. Provider message id: <code className="text-xs break-all" data-testid="reset-message-id">{res.message_id}</code>. Link expires {fmtDate(res.expires_at)}.</div>}
        {err && <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700" data-testid="reset-error">{err}</div>}
        <DialogFooter><Button variant="outline" onClick={onClose}>{res ? "Done" : "Cancel"}</Button>
          {!res && <Button onClick={send} disabled={busy} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="reset-send-btn">{busy ? "Sending…" : "Send reset email"}</Button>}</DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EmailDialog({ admin, iid, onClose, onDone }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { setEmail(""); setRes(null); setErr(""); }, [admin]);
  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/platform/institutions/${iid}/admins/${admin.id}/email`, { email });
      setRes(data); toast.success("Login email changed"); onDone();
    } catch (x) { setErr(errText(x)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={!!admin} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="email-dialog">
        <DialogHeader><DialogTitle>Change login email</DialogTitle>
          <DialogDescription>Current: {admin?.email}. Both the old and the new address get an email about the change.</DialogDescription></DialogHeader>
        {!res ? (
          <form onSubmit={save} className="space-y-3">
            <div className="space-y-1.5"><Label htmlFor="new-email">New email</Label>
              <Input id="new-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoCapitalize="none" data-testid="new-email-input" /></div>
            {err && <p className="text-sm text-red-600" data-testid="email-error">{err}</p>}
            <DialogFooter><Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
              <Button type="submit" disabled={busy} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="email-save-btn">{busy ? "Saving…" : "Change email"}</Button></DialogFooter>
          </form>
        ) : (
          <div className="space-y-2 text-sm" data-testid="email-result">
            <p>Login email is now <b>{res.email}</b>.</p>
            {Object.entries(res.notifications).map(([a, r]) => (
              <p key={a} className={r.message_id ? "text-emerald-700" : "text-red-600"}>{a}: {r.message_id ? <>sent · id <code className="text-xs break-all">{r.message_id}</code></> : `not sent (${r.error})`}</p>
            ))}
            <DialogFooter><Button onClick={onClose}>Done</Button></DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function AdminsTab({ iid }) {
  const [list, setList] = useState(null);
  const [reset, setReset] = useState(null);
  const [change, setChange] = useState(null);
  const load = useCallback(() => api.get(`/platform/institutions/${iid}/admins`).then((r) => setList(r.data.admins)).catch((e) => toast.error(errText(e))), [iid]);
  useEffect(() => { load(); }, [load]);
  const unlock = async (a) => {
    try { await api.post(`/account-locks/${a.id}/unlock`); toast.success(`${a.name} unlocked`); load(); } catch (e) { toast.error(errText(e)); }
  };
  if (!list) return <SkeletonGrid n={2} />;
  return (
    <Card title="School admins" testid="inst-admins-tab">
      {!list.length ? <Empty testid="admins-empty">No school admin accounts yet.</Empty> : (
        <div className="divide-y divide-slate-100 dark:divide-slate-800">
          {list.map((a) => (
            <div key={a.id} className="py-4 flex flex-wrap items-center gap-4 justify-between" data-testid={`admin-row-${a.id}`}>
              <div className="min-w-0">
                <p className="font-medium text-slate-900 dark:text-slate-50 flex items-center gap-2 flex-wrap">{a.name} <StatusPill status={a.status} />{a.lock && <LockedBadge lock={a.lock} testId={`admin-locked-${a.id}`} />}</p>
                <p className="text-sm text-slate-500" data-testid={`admin-email-${a.id}`}>{a.email}</p>
                <p className="text-xs text-slate-400 mt-0.5">Last sign-in {fmtDate(a.last_login)}{a.pending_reset && ` · reset link active until ${fmtDate(a.pending_reset.expires_at)}`}</p>
              </div>
              <div className="flex gap-2 flex-wrap">
                {a.lock && <Button size="sm" variant="outline" onClick={() => unlock(a)} data-testid={`admin-unlock-${a.id}`}><LockOpen size={14} className="mr-1.5" /> Unlock account</Button>}
                <Button size="sm" variant="outline" onClick={() => setReset(a)} data-testid={`admin-reset-${a.id}`}><KeyRound size={14} className="mr-1.5" /> Send password reset</Button>
                <Button size="sm" variant="outline" onClick={() => setChange(a)} data-testid={`admin-email-btn-${a.id}`}><Mail size={14} className="mr-1.5" /> Change email</Button>
              </div>
            </div>
          ))}
        </div>
      )}
      <ResetDialog admin={reset} iid={iid} onClose={() => setReset(null)} onDone={load} />
      <EmailDialog admin={change} iid={iid} onClose={() => setChange(null)} onDone={load} />
    </Card>
  );
}
