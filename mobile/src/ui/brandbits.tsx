// Brand bits: school logo (or initials), child avatar, bottom sheet, confirm dialog, "Powered by LNMO".
import { type ReactNode } from "react";
import { Alert, Modal, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { fonts } from "@/src/theme";
import { C } from "./kit";
import { useBrand } from "@/src/state/auth";
import { initials } from "@/src/lib/format";

export function SchoolLogo({ size = 40, uri, name, testID = "school-logo" }: { size?: number; uri?: string; name?: string; testID?: string }) {
  const b = useBrand();
  const src = uri ?? b.logo;
  const r = size * 0.3;
  if (src) return <Image source={{ uri: src }} style={{ width: size, height: size, borderRadius: r, backgroundColor: "#fff" }} contentFit="cover" testID={testID} />;
  return (
    <View style={{ width: size, height: size, borderRadius: r, backgroundColor: b.color, alignItems: "center", justifyContent: "center" }} testID={`${testID}-initials`}>
      <Text style={{ color: b.onColor, fontFamily: fonts.heading, fontSize: size * 0.38 }}>{initials(name ?? b.name)}</Text>
    </View>
  );
}

export function Avatar({ name, size = 36, light }: { name: string; size?: number; light?: boolean }) {
  const b = useBrand();
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: light ? "rgba(255,255,255,0.25)" : b.soft, alignItems: "center", justifyContent: "center" }}>
      <Text style={{ fontFamily: fonts.heading, fontSize: size * 0.42, color: light ? "#fff" : b.ink }}>{(name || "?")[0]?.toUpperCase()}</Text>
    </View>
  );
}

export function Sheet({ open, onClose, title, children, testID }: { open: boolean; onClose: () => void; title?: string; children: ReactNode; testID?: string }) {
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={open} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={sh.backdrop} onPress={onClose} testID={`${testID}-backdrop`} />
      <View style={[sh.sheet, { paddingBottom: insets.bottom + 16 }]} testID={testID}>
        <View style={sh.grab} />
        {title && <Text style={sh.title}>{title}</Text>}
        {children}
      </View>
    </Modal>
  );
}

export function confirm(title: string, message: string, okLabel = "OK"): Promise<boolean> {
  if (Platform.OS === "web") return Promise.resolve(window.confirm(`${title}\n\n${message}`));
  return new Promise((resolve) => {
    Alert.alert(title, message, [
      { text: "Cancel", style: "cancel", onPress: () => resolve(false) },
      { text: okLabel, style: "destructive", onPress: () => resolve(true) },
    ], { cancelable: true, onDismiss: () => resolve(false) });
  });
}

export function PoweredBy({ testID = "powered-by" }: { testID?: string }) {
  return (
    <View style={sh.powered} testID={testID}>
      <Image source={require("../../assets/images/lnmo-mark.png")} style={{ width: 26, height: 13 }} contentFit="contain" />
      <Text style={sh.poweredText}>Powered by LNMO</Text>
    </View>
  );
}

const sh = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(15,23,42,0.45)" },
  sheet: { backgroundColor: C.surfaceSecondary, borderTopLeftRadius: 28, borderTopRightRadius: 28, paddingHorizontal: 20, paddingTop: 10, maxHeight: "80%" },
  grab: { alignSelf: "center", width: 42, height: 5, borderRadius: 3, backgroundColor: C.borderStrong, marginBottom: 14 },
  title: { fontFamily: fonts.heading, fontSize: 20, color: C.onSurface, marginBottom: 12 },
  powered: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 8 },
  poweredText: { fontFamily: fonts.bodySemi, fontSize: 12, color: C.muted },
});
