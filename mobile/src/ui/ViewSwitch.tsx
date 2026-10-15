// View switcher UI — rendered only for principals (user.is_principal). Normal teachers never see it.
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Feather } from "@expo/vector-icons";
import { useAuth, useBrand } from "@/src/state/auth";
import { switchView, type AppView } from "@/src/state/view";
import { C } from "@/src/ui/kit";
import { fonts } from "@/src/theme";

const isPrincipal = (u: any) => u?.role === "teacher" && Boolean(u?.is_principal);

// Segmented pill: "Principal view | Teacher view".
export function ViewSwitch({ current }: { current: AppView }) {
  const { user } = useAuth();
  const b = useBrand();
  if (!isPrincipal(user)) return null;
  const seg = (v: AppView, text: string, icon: keyof typeof Feather.glyphMap) => {
    const on = v === current;
    return (
      <Pressable key={v} onPress={() => !on && switchView(user.id, v)} style={[s.seg, on && { backgroundColor: b.color }]}
        accessibilityRole="button" accessibilityState={{ selected: on }} testID={`view-switch-${v}`}>
        <Feather name={icon} size={15} color={on ? b.onColor : C.onSurface} />
        <Text style={[s.segText, { color: on ? b.onColor : C.onSurface }]}>{text}</Text>
      </Pressable>
    );
  };
  return (
    <View style={s.wrap} testID="view-switch">
      {seg("principal", "Principal view", "briefcase")}
      {seg("teacher", "Teacher view", "book-open")}
    </View>
  );
}

// Compact header pill: jumps to the other view.
export function ViewPill({ to }: { to: AppView }) {
  const { user } = useAuth();
  const b = useBrand();
  if (!isPrincipal(user)) return null;
  return (
    <Pressable onPress={() => switchView(user.id, to)} style={[s.pill, { borderColor: b.color, backgroundColor: b.soft }]} hitSlop={6} testID={`view-pill-${to}`}
      accessibilityLabel={to === "principal" ? "Switch to Principal view" : "Switch to Teacher view"}>
      <Feather name="repeat" size={14} color={b.ink} />
      <Text style={[s.pillText, { color: b.ink }]}>{to === "principal" ? "Principal view" : "Teacher view"}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  wrap: { flexDirection: "row", padding: 4, borderRadius: 999, backgroundColor: "#fff", borderWidth: 1, borderColor: C.border, gap: 4 },
  seg: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, minHeight: 44, borderRadius: 999 },
  segText: { fontFamily: fonts.bodyBold, fontSize: 14 },
  pill: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, minHeight: 36, borderRadius: 999, borderWidth: 1 },
  pillText: { fontFamily: fonts.bodyBold, fontSize: 13 },
});
