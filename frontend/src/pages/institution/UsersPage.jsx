import { useCallback, useEffect, useState } from "react";
import { LockOpen, KeyRound } from "lucide-react";
import { ResetPasswordDialog } from "../../components/common/ResetPasswordDialog";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import ResourcePage from "../../components/common/ResourcePage";
import { LockedBadge } from "../../components/common/AccountLock";
import { usersConfig } from "./config";

export default function UsersPage() {
  const [locks, setLocks] = useState({});
  const [resetFor, setResetFor] = useState(null);
  const load = useCallback(() => {
    api.get("/account-locks").then((r) => setLocks(Object.fromEntries(r.data.locks.map((l) => [l.user_id, l])))).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const unlock = async (row) => {
    try {
      await api.post(`/account-locks/${row.id}/unlock`);
      toast.success(`${row.name || "Account"} unlocked`);
      load();
    } catch (e) { toast.error(errText(e)); }
  };

  const columns = [...usersConfig.columns, {
    key: "lock", label: "Sign-in",
    render: (row) => (locks[row.id]
      ? <LockedBadge lock={locks[row.id]} testId={`locked-badge-${row.id}`} />
      : <span className="text-xs text-slate-400">OK</span>),
  }];
  const rowActions = [
    { title: "Unlock account", icon: LockOpen, testId: "unlock-row", show: (row) => Boolean(locks[row.id]), onClick: unlock },
    { title: "Reset password", icon: KeyRound, testId: "reset-password-row", show: (row) => row.role !== "platform_admin", onClick: setResetFor },
  ];
  return (
    <>
      <ResourcePage {...usersConfig} columns={columns} rowActions={rowActions} />
      <ResetPasswordDialog open={Boolean(resetFor)} onClose={() => setResetFor(null)} userId={resetFor?.id} name={resetFor?.name}
        hasEmail={Boolean(resetFor?.email && !resetFor.email.endsWith(".parent.invite"))} />
    </>
  );
}
