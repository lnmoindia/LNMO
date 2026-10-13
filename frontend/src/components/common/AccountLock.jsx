import { useCallback, useEffect, useState } from "react";
import { Lock, LockOpen } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../ui/button";

const hhmm = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export const LockedBadge = ({ lock, testId = "account-locked-badge" }) => (
  <span title={`Last failed attempt: ${new Date(lock.last_failed_at).toLocaleString()} · ${lock.count} failed tries`}
    className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300 whitespace-nowrap"
    data-testid={testId}>
    <Lock size={12} /> Locked — unlocks at {hhmm(lock.locked_until)}
  </span>
);

// Shows the lock badge + Unlock button for a paused account; renders nothing otherwise.
export const AccountLock = ({ userId }) => {
  const [lock, setLock] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    if (!userId) return;
    api.get(`/account-locks/${userId}`).then((r) => setLock(r.data)).catch(() => setLock(null));
  }, [userId]);
  useEffect(() => { load(); }, [load]);
  if (!lock?.locked) return null;
  const unlock = async () => {
    setBusy(true);
    try {
      await api.post(`/account-locks/${userId}/unlock`);
      toast.success("Account unlocked — they can sign in again now");
      setLock({ locked: false });
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="flex items-center gap-2 flex-wrap" data-testid="account-lock">
      <LockedBadge lock={lock} />
      <Button size="sm" variant="outline" onClick={unlock} disabled={busy} data-testid="unlock-account-btn">
        <LockOpen size={14} className="mr-1.5" /> {busy ? "Unlocking…" : "Unlock account"}
      </Button>
    </div>
  );
};
