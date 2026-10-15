import { Tabs } from "expo-router";
import { Platform, StyleSheet } from "react-native";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useBrand } from "@/src/state/auth";
import { C } from "@/src/ui/kit";
import { fonts } from "@/src/theme";

const TABS: [string, string, keyof typeof Feather.glyphMap][] = [
  ["today", "Today", "sun"], ["cover", "Cover", "shuffle"], ["attendance", "Attendance", "check-square"], ["fees", "Fees", "credit-card"], ["more", "More", "grid"],
];

export default function PrincipalTabs() {
  const b = useBrand();
  const insets = useSafeAreaInsets();
  return (
    <Tabs screenOptions={{
      headerShown: false, tabBarActiveTintColor: b.ink, tabBarInactiveTintColor: C.muted, tabBarLabelStyle: s.label,
      tabBarStyle: [s.bar, { height: 64 + Math.max(insets.bottom, Platform.OS === "web" ? 6 : 8), paddingBottom: Math.max(insets.bottom, 8) }],
      tabBarItemStyle: { paddingTop: 6 },
    }}>
      {TABS.map(([name, title, icon]) => (
        <Tabs.Screen key={name} name={name} options={{ title, tabBarButtonTestID: `ptab-${name}`,
          tabBarIcon: ({ color, focused }) => <Feather name={icon} size={focused ? 24 : 22} color={color} /> }} />
      ))}
    </Tabs>
  );
}

const s = StyleSheet.create({
  bar: { backgroundColor: "#FFFFFF", borderTopColor: C.border, borderTopWidth: 1, elevation: 0 },
  label: { fontFamily: fonts.bodySemi, fontSize: 12, marginTop: 2 },
});
