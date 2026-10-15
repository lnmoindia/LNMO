import { Tabs } from "expo-router";
import { Platform, StyleSheet } from "react-native";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useBrand } from "@/src/state/auth";
import { useUnread } from "@/src/lib/queries";
import { C } from "@/src/ui/kit";
import { fonts } from "@/src/theme";

const TABS: [string, string, keyof typeof Feather.glyphMap][] = [
  ["today", "Today", "sun"],
  ["attendance", "Attendance", "check-square"],
  ["homework", "Homework", "book-open"],
  ["messages", "Messages", "message-circle"],
  ["more", "More", "grid"],
];

export default function TeacherTabs() {
  const b = useBrand();
  const insets = useSafeAreaInsets();
  const unread = useUnread(true);
  return (
    <Tabs screenOptions={{
      headerShown: false,
      tabBarActiveTintColor: b.ink,
      tabBarInactiveTintColor: C.muted,
      tabBarLabelStyle: s.label,
      tabBarStyle: [s.bar, { height: 64 + Math.max(insets.bottom, Platform.OS === "web" ? 6 : 8), paddingBottom: Math.max(insets.bottom, 8) }],
      tabBarItemStyle: { paddingTop: 6 },
    }}>
      {TABS.map(([name, title, icon]) => (
        <Tabs.Screen key={name} name={name} options={{
          title,
          tabBarButtonTestID: `ttab-${name}`,
          tabBarIcon: ({ color, focused }) => <Feather name={icon} size={focused ? 24 : 22} color={color} />,
          tabBarBadge: name === "messages" && unread.data ? unread.data : undefined,
          tabBarBadgeStyle: { backgroundColor: C.error, color: "#fff", fontFamily: fonts.bodyBold, fontSize: 11 },
        }} />
      ))}
    </Tabs>
  );
}

const s = StyleSheet.create({
  bar: { backgroundColor: "#FFFFFF", borderTopColor: C.border, borderTopWidth: 1, elevation: 0 },
  label: { fontFamily: fonts.bodySemi, fontSize: 12, marginTop: 2 },
});
