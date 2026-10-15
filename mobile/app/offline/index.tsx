// More → Offline sync: what's waiting, what needs attention, and the last 20 sync results.
import { useEffect, useState } from "react";
import { Switch, Text, View } from "react-native";
import { router } from "expo-router";
import { useAuth } from "@/src/state/auth";
import { StackScreen } from "@/src/ui/Screen";
import { Button, C, Card, Divider, Empty, ListRow, SectionTitle, k } from "@/src/ui/kit";
import { fmtDate, fmtDateTime } from "@/src/lib/format";
import { useOnline, useSimOffline, setSimOffline } from "@/src/offline/net";
import { isWaiting, needsAttention, useOutbox, type HistStatus, type Item } from "@/src/offline/outbox";
import { retryItem, syncNow } from "@/src/offline/sync";
import { onPrefetched, prefetchOffline, readPrefetchMeta } from "@/src/offline/prefetch";

const HIST: Record<HistStatus, [string, string]> = {
  synced: ["Synced", C.success], conflict_resolved: ["Conflict resolved", C.success], rejected_locked: ["Rejected — locked", C.error], rejected: ["Rejected", C.error], failed: ["Failed", C.warning],
};
const itemSub = (it: Item) => it.status === "conflict" ? "Sync conflict — tap to resolve" : it.status === "rejected" ? (it.rejected?.locked ? "Finalised on the server — not applied" : "Not accepted by the server") : it.status === "failed" ? `Failed: ${it.error || "server error"} — will retry` : "Saved offline — will sync";

export default function OfflineSyncScreen() {
  const { user } = useAuth();
  const { items, history } = useOutbox();
  const online = useOnline();
  const sim = useSimOffline();
  const [meta, setMeta] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { readPrefetchMeta().then(setMeta); return onPrefetched(() => { readPrefetchMeta().then(setMeta); }); }, []);
  const waiting = items.filter(isWaiting);
  const attention = items.filter(needsAttention);
  const refresh = async () => { setBusy(true); await prefetchOffline(user, true); setMeta(await readPrefetchMeta()); setBusy(false); };
  const row = (it: Item) => (
    <ListRow key={it.id} icon={it.status === "conflict" ? "git-merge" : it.status === "rejected" ? "lock" : "upload-cloud"} title={`${it.class_name} ${it.section} · ${fmtDate(it.date, { weekday: true })}`}
      sub={itemSub(it)} danger={needsAttention(it)} onPress={() => router.push(`/offline/${it.id}`)} testID={`offline-item-${it.id}`} />
  );
  return (
    <StackScreen title="Offline sync" testID="offline-sync-screen">
      <Card style={{ gap: 6 }} testID="offline-status-card">
        <Text style={k.h2} testID="offline-connection">{online ? "Online" : "Offline"}</Text>
        <Text style={k.small} testID="offline-cache-meta">{meta?.at ? `Saved for offline: ${fmtDateTime(meta.at)} · ${(meta.classes || []).join(", ") || "no classes"} (today + yesterday)` : "Nothing saved for offline yet."}</Text>
        <View style={{ flexDirection: "row", gap: 8, marginTop: 6 }}>
          <Button small label="Sync now" icon="refresh-cw" onPress={() => syncNow(true)} style={{ flex: 1 }} testID="offline-sync-now" />
          <Button small variant="outline" label="Refresh offline data" icon="download" onPress={refresh} loading={busy} disabled={!online} style={{ flex: 1 }} testID="offline-refresh-cache" />
        </View>
      </Card>
      {attention.length > 0 && (<><SectionTitle title={`Needs attention · ${attention.length}`} /><Card style={{ padding: 0 }}>{attention.map((it, i) => <View key={it.id}>{i > 0 && <Divider />}{row(it)}</View>)}</Card></>)}
      <SectionTitle title={`Waiting to sync · ${waiting.length}`} />
      {waiting.length ? <Card style={{ padding: 0 }}>{waiting.map((it, i) => <View key={it.id}>{i > 0 && <Divider />}{row(it)}</View>)}</Card>
        : <Card><Empty icon="check-circle" text="Every register is synced." testID="offline-nothing-waiting" /></Card>}
      <SectionTitle title="Sync history" />
      {history.length ? (
        <Card style={{ padding: 0 }} testID="offline-history">
          {history.map((h, i) => (
            <View key={h.id}>{i > 0 && <Divider />}
              <View style={{ paddingHorizontal: 16, paddingVertical: 12, gap: 2 }} testID={`offline-history-${h.id}`}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Text style={[k.body, { flex: 1, fontWeight: "600" }]}>{h.label} · {fmtDate(h.date)}</Text>
                  <Text style={[k.label, { color: HIST[h.status][1] }]} testID={`offline-history-status-${h.id}`}>{HIST[h.status][0]}</Text>
                </View>
                <Text style={k.small}>{fmtDateTime(h.at)}{h.detail ? ` · ${h.detail}` : ""}</Text>
                {h.status === "failed" && items.some((x) => x.id === h.id) && <Button small variant="outline" label="Retry" icon="rotate-cw" onPress={() => retryItem(h.id)} style={{ alignSelf: "flex-start", marginTop: 6 }} testID={`offline-retry-${h.id}`} />}
              </View>
            </View>
          ))}
        </Card>
      ) : <Card><Empty icon="clock" text="No syncs yet." /></Card>}
      {__DEV__ && (
        <Card style={{ flexDirection: "row", alignItems: "center", gap: 12 }} testID="offline-dev-card">
          <View style={{ flex: 1 }}><Text style={k.body}>Simulate offline (testing)</Text><Text style={k.small}>Dev builds only. Every request fails like a lost connection.</Text></View>
          <Switch value={sim} onValueChange={setSimOffline} testID="offline-sim-toggle" />
        </Card>
      )}
    </StackScreen>
  );
}
