// "Offline · N registers waiting to sync" + "N need attention" — shown under the header on every screen.
import { Pressable, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { fonts } from "@/src/theme";
import { useOnline } from "./net";
import { useOutboxCounts } from "./outbox";
import { syncNow } from "./sync";

export function SyncBanner() {
  const online = useOnline();
  const { waiting, attention } = useOutboxCounts();
  if (!waiting && !attention) return null;
  const n = (x: number) => `${x} register${x > 1 ? "s" : ""}`;
  return (
    <View style={{ gap: 6, marginHorizontal: 20, marginBottom: 8 }}>
      {waiting > 0 && (
        <Pressable onPress={() => router.push("/offline")} style={[s.bar, s.wait]} testID="sync-banner">
          <Feather name={online ? "upload-cloud" : "cloud-off"} size={16} color="#1E3A8A" />
          <Text style={[s.text, { color: "#1E3A8A" }]} testID="sync-banner-text">{online ? `${n(waiting)} waiting to sync` : `Offline · ${n(waiting)} waiting to sync`}</Text>
          {online && <Pressable onPress={() => syncNow(true)} hitSlop={10} testID="sync-banner-sync-now"><Text style={[s.act, { color: "#1E3A8A" }]}>Sync now</Text></Pressable>}
        </Pressable>
      )}
      {attention > 0 && (
        <Pressable onPress={() => router.push("/offline")} style={[s.bar, s.att]} testID="sync-attention-banner">
          <Feather name="alert-triangle" size={16} color="#9F1239" />
          <Text style={[s.text, { color: "#9F1239" }]}>{n(attention)} need{attention > 1 ? "" : "s"} attention</Text>
          <Text style={[s.act, { color: "#9F1239" }]}>Open</Text>
        </Pressable>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  bar: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 14, minHeight: 44, borderRadius: 12 },
  wait: { backgroundColor: "#E0EAFF" },
  att: { backgroundColor: "#FDECEF" },
  text: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 13 },
  act: { fontFamily: fonts.bodyBold, fontSize: 14 },
});
