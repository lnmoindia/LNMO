// More → Notifications: per-category toggles (saved on the server), device status, test buttons.
import { useEffect, useState } from "react";
import { Linking, Switch, Text, View } from "react-native";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth, useBrand } from "@/src/state/auth";
import { useToast } from "@/src/state/toast";
import { api } from "@/src/lib/api";
import { askPermission, isExpoGo, localTest, notificationsSupported, permission, pushStatus, registerForPush, UNSUPPORTED_TEXT, type Perm } from "@/src/push/push";
import { StackScreen } from "@/src/ui/Screen";
import { Button, C, Card, Divider, ErrorState, SectionTitle, SkeletonList, k } from "@/src/ui/kit";

const HINT: Record<string, string> = {
  messages: "New chat messages", fees: "Reminders, payment verified / not accepted", homework: "New homework and assignments",
  notices: "New school notices", timetable: "Substitute teacher or cover changes today", teacher_covers: "Cover requests, assignments and cancellations",
};

function deviceText(perm: string) {
  const st = pushStatus();
  if (perm === "unavailable") return [`${UNSUPPORTED_TEXT} You can still choose your alert types here — they're saved to your account.`, "info"];
  if (perm === "denied") return ["Notifications are turned off for this app in your phone settings.", "warn"];
  if (perm !== "granted") return ["Notifications are not turned on yet on this phone.", "warn"];
  if (st.ok) return ["This phone receives notifications.", "ok"];
  if (st.reason === "no_project") return ["This app build isn't linked to an Expo project yet, so push is off. The local test still works.", "info"];
  if (st.reason === "unsupported") return [`${UNSUPPORTED_TEXT} The local test below still works.`, "info"];
  return ["Couldn't register this phone yet — open this screen again to retry.", "warn"];
}

function DeviceCard() {
  const toast = useToast();
  const { user } = useAuth();
  const [perm, setPerm] = useState<Perm>(notificationsSupported() ? "undetermined" : "unavailable");
  const [busy, setBusy] = useState("");
  const refresh = async () => { const p = await permission(); setPerm(p); if (p === "granted" && !pushStatus().ok) { await registerForPush(); setPerm(await permission()); } };
  useEffect(() => { refresh(); }, []);
  const [text, tone] = deviceText(perm);
  const turnOn = async () => { setBusy("on"); try { if ((await askPermission()) !== "granted") Linking.openSettings(); await refresh(); } finally { setBusy(""); } };
  const test = async () => {
    if (perm === "unavailable" || pushStatus().reason === "unsupported") { toast(UNSUPPORTED_TEXT, "info"); return; }
    setBusy("test");
    try { const r = await api.post("/push/test"); toast(r.ok ? "Test sent — it should arrive in a few seconds" : r.message || (r.results?.[0]?.error ?? "Couldn't send"), r.ok ? "success" : "error"); }
    catch (e: any) { toast(e.message, "error"); } finally { setBusy(""); }
  };
  const home = user?.role === "student" ? "/student/timetable" : user?.role === "teacher" ? "/teacher/more/substitutions" : "/fees";
  const local = async () => { setBusy("local"); try { await localTest(home); toast("A local alert will appear in 2 seconds — tap it"); } catch (e: any) { toast(e.message, "error"); } finally { setBusy(""); } };
  return (
    <Card style={{ gap: 12 }} testID="push-device-card">
      <Text style={[k.label, { color: tone === "ok" ? C.success : tone === "warn" ? C.warning : C.onSurface }]} testID="push-device-status">{text}</Text>
      {(perm === "undetermined" || perm === "denied") && <Button label="Turn on notifications" icon="bell" onPress={turnOn} loading={busy === "on"} testID="push-turn-on-btn" />}
      <Button label="Send test notification" icon="send" variant="outline" onPress={test} loading={busy === "test"} testID="push-send-test-btn" />
      {perm === "granted" && <Button label="Local test (tap to open a screen)" icon="smartphone" variant="ghost" onPress={local} loading={busy === "local"} testID="push-local-test-btn" />}
    </Card>
  );
}

export default function NotificationSettings() {
  const b = useBrand();
  const toast = useToast();
  const qc = useQueryClient();
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["push-prefs"], queryFn: () => api.get("/push/preferences"), enabled: Boolean(user) });
  const toggle = async (key: string, v: boolean) => {
    qc.setQueryData(["push-prefs"], (d: any) => d && { ...d, categories: d.categories.map((c: any) => (c.key === key ? { ...c, enabled: v } : c)) });
    try { qc.setQueryData(["push-prefs"], await api.put("/push/preferences", { preferences: { [key]: v } })); }
    catch (e: any) { toast(e.message, "error"); q.refetch(); }
  };
  return (
    <StackScreen title="Notifications" testID="notification-settings-screen">
      <DeviceCard />
      <SectionTitle title="Alert me about" />
      {q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !q.data ? <SkeletonList n={1} height={220} /> : (
        <Card style={{ padding: 0 }} testID="push-categories">
          {q.data.categories.map((c: any, i: number) => (
            <View key={c.key}>
              {i > 0 && <Divider />}
              <View style={{ flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, minHeight: 64, paddingVertical: 10 }}>
                <View style={{ flex: 1, gap: 2 }}><Text style={k.label}>{c.label}</Text><Text style={k.small}>{HINT[c.key]}</Text></View>
                <Switch value={c.enabled} onValueChange={(v) => toggle(c.key, v)} trackColor={{ true: b.color, false: C.borderStrong }}
                  thumbColor="#FFFFFF" {...({ activeThumbColor: "#FFFFFF" } as any)} testID={`push-toggle-${c.key}`} accessibilityLabel={c.label} />
              </View>
            </View>
          ))}
        </Card>
      )}
      <Text style={k.small}>Your choices are saved to your account and apply on every phone you sign in on.{isExpoGo ? " (Running in Expo Go.)" : ""}</Text>
    </StackScreen>
  );
}
