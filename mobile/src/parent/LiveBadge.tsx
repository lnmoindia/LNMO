import { StyleSheet, Text, View } from "react-native";
import type { ChatStatus } from "@/src/lib/chat";
import { fonts } from "@/src/theme";

export function LiveBadge({ status, testID = "chat-live-status" }: { status: ChatStatus; testID?: string }) {
  const live = status === "live";
  const color = live ? "#047857" : "#B45309";
  return (
    <View style={s.wrap} testID={testID}>
      <View style={[s.dot, { backgroundColor: color }]} />
      <Text style={[s.text, { color }]}>{live ? "Live" : status === "polling" ? "Auto-refresh" : "Connecting…"}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flexDirection: "row", alignItems: "center", gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  text: { fontFamily: fonts.bodyBold, fontSize: 12, letterSpacing: 0.6, textTransform: "uppercase" },
});
