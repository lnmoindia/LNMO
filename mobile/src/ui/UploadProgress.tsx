// Floating "Uploading… 42%" pill for every multipart upload (api.postForm → uploadForm).
import { useSyncExternalStore } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { uploadStore } from "@/src/lib/api";
import { useBrand } from "@/src/state/auth";
import { fonts } from "@/src/theme";

export function UploadProgress() {
  const u = useSyncExternalStore(uploadStore.subscribe, uploadStore.get, uploadStore.get);
  const insets = useSafeAreaInsets();
  const b = useBrand();
  if (!u) return null;
  const pct = Math.round(u.pct * 100);
  return (
    <View pointerEvents="none" style={[s.wrap, { top: insets.top + 8 }]} testID="upload-progress">
      <View style={s.pill}>
        <Text style={s.text} testID="upload-progress-text">{u.label}… {pct}%</Text>
        <View style={s.track}><View style={[s.bar, { width: `${Math.max(4, pct)}%`, backgroundColor: b.color }]} /></View>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { position: "absolute", left: 0, right: 0, alignItems: "center", zIndex: 1000 },
  pill: { backgroundColor: "rgba(15,23,42,0.9)", borderRadius: 16, paddingHorizontal: 16, paddingVertical: 10, gap: 6, minWidth: 200 },
  text: { color: "#fff", fontFamily: fonts.bodySemi, fontSize: 13 },
  track: { height: 4, borderRadius: 2, backgroundColor: "rgba(255,255,255,0.25)", overflow: "hidden" },
  bar: { height: 4, borderRadius: 2 },
});
