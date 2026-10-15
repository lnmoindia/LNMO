// One offline register: resolve a sync conflict (pick per student), or see why it wasn't applied.
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import * as Clipboard from "expo-clipboard";
import { useToast } from "@/src/state/toast";
import { useBrand } from "@/src/state/auth";
import { StackScreen } from "@/src/ui/Screen";
import { Button, C, Card, Empty, k } from "@/src/ui/kit";
import { confirm } from "@/src/ui/brandbits";
import { fmtDate, fmtDateTime } from "@/src/lib/format";
import { fonts } from "@/src/theme";
import { useOutbox, type Diff, type Item } from "@/src/offline/outbox";
import { dismissItem, resolveConflict, retryItem, syncNow } from "@/src/offline/sync";

const word = (v?: string) => (v ? v[0].toUpperCase() + v.slice(1) : "Not marked");
const title = (it: Item) => `${it.class_name} ${it.section} · ${fmtDate(it.date, { weekday: true })}`;

export default function OfflineItem() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const it = useOutbox().items.find((x) => x.id === id);
  if (!it) return <StackScreen title="Offline register" testID="offline-item-screen"><Card><Empty icon="check-circle" text="This register is no longer waiting — it was synced or dismissed." testID="offline-item-gone" /></Card></StackScreen>;
  if (it.status === "conflict") return <Conflict it={it} />;
  if (it.status === "rejected") return <Rejected it={it} />;
  return <Waiting it={it} />;
}

function Conflict({ it }: { it: Item }) {
  const toast = useToast();
  const [pick, setPick] = useState<Record<string, "mine" | "server">>({});
  const [busy, setBusy] = useState(false);
  const c = it.conflict!;
  const all = (v: "mine" | "server") => setPick(Object.fromEntries(c.list.map((d) => [d.id, v])));
  const done = c.list.every((d) => pick[d.id]);
  const save = async () => { setBusy(true); await resolveConflict(it.id, pick); setBusy(false); toast("Saved your choices"); router.back(); };
  const by = `changed by ${c.server.marked_by || "someone"}${c.server.updated_at ? ` at ${fmtDateTime(c.server.updated_at)}` : ""}`;
  return (
    <StackScreen title="Resolve sync conflict" testID="conflict-screen">
      <Card style={{ gap: 4 }}><Text style={k.h2}>{title(it)}</Text><Text style={k.body}>{c.list.length} student{c.list.length > 1 ? "s were" : " was"} changed on the server while you were offline. Pick the mark to keep for each. Other changes were merged automatically.</Text></Card>
      <View style={{ flexDirection: "row", gap: 8 }}>
        <Button small variant="outline" label="Use all mine" onPress={() => all("mine")} style={{ flex: 1 }} testID="conflict-all-mine" />
        <Button small variant="outline" label="Use all server" onPress={() => all("server")} style={{ flex: 1 }} testID="conflict-all-server" />
      </View>
      {c.list.map((d) => (
        <Card key={d.id} style={{ gap: 10 }} testID={`conflict-row-${d.id}`}>
          <Text style={s.name}>{d.name}</Text>
          <Option on={pick[d.id] === "mine"} label={`Yours (offline): ${word(d.mine)}`} onPress={() => setPick((p) => ({ ...p, [d.id]: "mine" }))} testID={`conflict-mine-${d.id}`} />
          <Option on={pick[d.id] === "server"} label={`Server (${by}): ${word(d.server)}`} onPress={() => setPick((p) => ({ ...p, [d.id]: "server" }))} testID={`conflict-server-${d.id}`} />
        </Card>
      ))}
      <Button label={done ? "Save" : "Pick one for each student"} icon="check" onPress={save} loading={busy} disabled={!done} testID="conflict-save" />
    </StackScreen>
  );
}

function Option({ on, label, onPress, testID }: { on: boolean; label: string; onPress: () => void; testID: string }) {
  const b = useBrand();
  return (
    <Pressable onPress={onPress} style={[s.opt, on && { borderColor: b.color, backgroundColor: b.soft }]} accessibilityRole="radio" accessibilityState={{ checked: on }} testID={testID}>
      <View style={[s.dot, on && { borderColor: b.color }]}>{on && <View style={[s.dotIn, { backgroundColor: b.color }]} />}</View>
      <Text style={s.optText}>{label}</Text>
    </Pressable>
  );
}

const DiffList = ({ diffs }: { diffs: Diff[] }) => (
  <Card style={{ gap: 8 }} testID="rejected-diffs">
    {diffs.length ? diffs.map((d) => <Text key={d.id} style={k.body}>{d.name}: yours {word(d.mine)} · server {word(d.server)}</Text>) : <Text style={k.small}>No differences — the server already matches.</Text>}
  </Card>
);

function Rejected({ it }: { it: Item }) {
  const toast = useToast();
  const [show, setShow] = useState(false);
  const r = it.rejected!;
  const head = r.locked ? `Register was finalised by ${r.by || "the school"}${r.at ? ` (${fmtDateTime(r.at)})` : ""} — your offline changes weren't applied.` : `The server didn't accept this register: ${r.reason}`;
  const details = `${head}\n\nClass ${it.class_name} ${it.section}, ${it.date}.\nMy offline marks that were not applied:\n${r.diffs.map((d) => `- ${d.name}: ${word(d.mine)} (server: ${word(d.server)})`).join("\n") || "- none"}`;
  const report = () => router.push({ pathname: "/more/support", params: { title: `Attendance correction: ${it.class_name} ${it.section} ${it.date}`, desc: details } });
  const dismiss = async () => { if (await confirm("Dismiss?", "Your offline marks for this register will be removed from this phone.", "Dismiss")) { await dismissItem(it.id); router.back(); } };
  return (
    <StackScreen title="Not applied" testID="rejected-screen">
      <Card style={{ gap: 6, borderColor: "#FBCFE8" }}><Text style={k.h2}>{title(it)}</Text><Text style={[k.body, { color: "#9F1239" }]} testID="rejected-reason">{head}</Text></Card>
      <Button variant="outline" label={show ? "Hide differences" : `View differences (${r.diffs.length})`} icon="list" onPress={() => setShow(!show)} testID="rejected-toggle-diffs" />
      {show && <DiffList diffs={r.diffs} />}
      <Button label="Report to the office" icon="send" onPress={report} testID="rejected-report-office" />
      <Button variant="outline" label="Copy details" icon="copy" onPress={async () => { await Clipboard.setStringAsync(details); toast("Copied"); }} testID="rejected-copy" />
      {!r.locked && <Button variant="outline" label="Try again" icon="rotate-cw" onPress={() => retryItem(it.id)} testID="rejected-retry" />}
      <Button variant="ghost" label="Dismiss" icon="x" onPress={dismiss} testID="rejected-dismiss" />
    </StackScreen>
  );
}

function Waiting({ it }: { it: Item }) {
  const n = Object.keys(it.entries).length;
  const discard = async () => { if (await confirm("Discard offline changes?", "These marks were never sent to the school.", "Discard")) { await dismissItem(it.id); router.back(); } };
  return (
    <StackScreen title="Offline register" testID="waiting-screen">
      <Card style={{ gap: 6 }}><Text style={k.h2}>{title(it)}</Text><Text style={k.body} testID="waiting-state">{it.status === "failed" ? `Sync failed: ${it.error} — will retry.` : "Saved offline — will sync."}</Text>
        <Text style={k.small}>{n} students marked{it.finalized ? " · submit as final" : " · draft"} · saved {fmtDateTime(it.updated_at)}</Text></Card>
      <Button label="Sync now" icon="refresh-cw" onPress={() => syncNow(true)} testID="waiting-sync-now" />
      <Button variant="ghost" label="Discard offline changes" icon="trash-2" onPress={discard} testID="waiting-discard" />
    </StackScreen>
  );
}

const s = StyleSheet.create({
  name: { fontFamily: fonts.bodyBold, fontSize: 16, color: C.onSurface },
  opt: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 52, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: "#fff" },
  optText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 15, color: C.onSurface },
  dot: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: C.borderStrong, alignItems: "center", justifyContent: "center" },
  dotIn: { width: 10, height: 10, borderRadius: 5 },
});
