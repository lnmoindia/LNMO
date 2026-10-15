// Friendly pre-prompt shown once after login, before the system permission dialog.
import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { useBrand } from "@/src/state/auth";
import { storage } from "@/src/utils/storage";
import { ASKED_KEY, askPermission, notificationsSupported, registerForPush } from "@/src/push/push";
import { Button, C, k } from "@/src/ui/kit";
import { fonts } from "@/src/theme";

const POINTS: [keyof typeof Feather.glyphMap, string][] = [
  ["message-circle", "New messages from the school or parents"],
  ["credit-card", "Fee reminders and payment confirmations"],
  ["calendar", "Homework, notices and timetable changes"],
];

export default function NotifyPermission() {
  const b = useBrand();
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    storage.setItem(ASKED_KEY, "1");
    if (!notificationsSupported()) leave(); // nothing to ask for here (web / Expo Go on Android)
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const leave = () => (router.canGoBack() ? router.back() : router.replace("/"));
  const allow = async () => {
    setBusy(true);
    try { if ((await askPermission()) === "granted") await registerForPush(); } finally { setBusy(false); leave(); }
  };
  return (
    <SafeAreaView style={s.safe} testID="notify-permission-screen">
      <View style={s.body}>
        <View style={[s.icon, { backgroundColor: b.soft }]}><Feather name="bell" size={40} color={b.ink} /></View>
        <Text style={s.title}>Get alerts for messages, fees and timetable changes</Text>
        <Text style={[k.small, { fontSize: 15, lineHeight: 22 }]}>We only send what matters to you. You can choose the types any time in More → Notifications.</Text>
        <View style={{ gap: 14, marginTop: 8 }}>
          {POINTS.map(([icon, text]) => (
            <View key={icon} style={s.row}><Feather name={icon} size={20} color={b.ink} /><Text style={s.rowText}>{text}</Text></View>
          ))}
        </View>
      </View>
      <View style={s.foot}>
        <Button label="Allow notifications" icon="bell" onPress={allow} loading={busy} testID="notify-allow-btn" />
        <Button label="Not now" variant="ghost" onPress={leave} testID="notify-later-btn" />
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#FFFFFF" },
  body: { flex: 1, padding: 28, paddingTop: 56, gap: 16 },
  icon: { width: 84, height: 84, borderRadius: 28, alignItems: "center", justifyContent: "center", marginBottom: 8 },
  title: { fontFamily: fonts.heading, fontSize: 26, lineHeight: 32, color: C.onSurface },
  row: { flexDirection: "row", alignItems: "center", gap: 14 },
  rowText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 16, color: C.onSurface },
  foot: { padding: 24, gap: 8 },
});
