// Background sync driver (renders nothing): loads the signed-in user's outbox, prefetches offline data,
// and syncs when the connection returns, on foreground, and every 30s while registers are waiting.
import { useEffect } from "react";
import { AppState } from "react-native";
import { useAuth } from "@/src/state/auth";
import { useToast } from "@/src/state/toast";
import { useOnline } from "./net";
import { loadOutbox, useOutboxCounts } from "./outbox";
import { setSyncNotifier, syncNow } from "./sync";
import { prefetchOffline } from "./prefetch";

export function OfflineSync() {
  const { user } = useAuth();
  const toast = useToast();
  const online = useOnline();
  const { waiting } = useOutboxCounts();
  const active = user && !user.must_change_password ? user : null;
  const owner = active ? `${active.institution_id}.${active.id}` : null;

  useEffect(() => { setSyncNotifier(toast); }, [toast]);
  useEffect(() => {
    loadOutbox(owner, active?.email || null).then(() => { if (owner) { syncNow(); prefetchOffline(active, true); } });
  }, [owner]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (online && owner) { syncNow(); prefetchOffline(active); } }, [online]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const sub = AppState.addEventListener("change", (s) => { if (s === "active" && owner) { syncNow(); prefetchOffline(active); } });
    return () => sub.remove();
  }, [owner]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!waiting || !online) return undefined;
    const t = setInterval(() => syncNow(), 30000);
    return () => clearInterval(t);
  }, [waiting, online]);
  return null;
}
