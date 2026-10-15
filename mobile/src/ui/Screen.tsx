// Screen shells: tab screens (school header + child switcher) and stacked detail screens (back header).
import { useCallback, useState, type ReactNode } from "react";
import { KeyboardAvoidingView, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useNetInfo } from "@react-native-community/netinfo";
import { useQueryClient } from "@tanstack/react-query";
import { fonts } from "@/src/theme";
import { C } from "./kit";
import { SchoolLogo } from "./brandbits";
import { ChildSwitcher } from "./ChildSwitcher";
import { useAuth, useBrand } from "@/src/state/auth";

export function usePullRefresh(extra?: () => Promise<any> | void) {
  const qc = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    try { await Promise.all([qc.refetchQueries({ type: "active" }), extra?.()]); } finally { setRefreshing(false); }
  }, [qc, extra]);
  return { refreshing, onRefresh };
}

export function OfflineBanner() {
  const net = useNetInfo();
  const qc = useQueryClient();
  if (net.isConnected !== false) return null;
  return (
    <View style={s.offline} testID="offline-banner">
      <Feather name="wifi-off" size={16} color="#7C2D12" />
      <Text style={s.offlineText}>You're offline. Showing the last loaded data.</Text>
      <Pressable onPress={() => qc.refetchQueries({ type: "active" })} hitSlop={10} testID="offline-retry">
        <Text style={s.offlineRetry}>Retry</Text>
      </Pressable>
    </View>
  );
}

export function TabScreen({ children, testID, title, scroll = true, showSwitcher = true }: { children: ReactNode; testID: string; title?: string; scroll?: boolean; showSwitcher?: boolean }) {
  const b = useBrand();
  const { refreshing, onRefresh } = usePullRefresh();
  return (
    <SafeAreaView edges={["top"]} style={s.safe} testID={testID}>
      <View style={s.header}>
        <SchoolLogo size={38} />
        <View style={{ flex: 1 }}>
          <Text style={s.school} numberOfLines={1} testID="header-school-name">{b.name || "Your school"}</Text>
          {title ? <Text style={s.title} numberOfLines={1}>{title}</Text> : null}
        </View>
        {showSwitcher && <ChildSwitcher />}
      </View>
      <OfflineBanner />
      {scroll ? (
        <ScrollView contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={b.color} colors={[b.color]} />}>
          {children}
        </ScrollView>
      ) : children}
    </SafeAreaView>
  );
}

export function StackScreen({ children, title, testID, scroll = true, right, keyboard = false, footer }: { children: ReactNode; title: string; testID: string; scroll?: boolean; right?: ReactNode; keyboard?: boolean; footer?: ReactNode }) {
  const b = useBrand();
  const { user } = useAuth();
  const { refreshing, onRefresh } = usePullRefresh();
  const back = () => (router.canGoBack() ? router.back() : router.replace(user?.role === "student" ? "/student/today" : user?.role === "teacher" ? "/teacher/today" : "/home"));
  const body = scroll ? (
    <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled"
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={b.color} colors={[b.color]} />}>
      {children}
    </ScrollView>
  ) : children;
  return (
    <SafeAreaView edges={["top", "bottom"]} style={s.safe} testID={testID}>
      <View style={s.stackHeader}>
        <Pressable onPress={back} style={s.backBtn} hitSlop={8} testID="header-back-btn" accessibilityLabel="Go back">
          <Feather name="arrow-left" size={22} color={C.onSurface} />
        </Pressable>
        <Text style={s.stackTitle} numberOfLines={1}>{title}</Text>
        <View style={{ minWidth: 44, alignItems: "flex-end" }}>{right}</View>
      </View>
      <OfflineBanner />
      {keyboard ? (
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>{body}{footer}</KeyboardAvoidingView>
      ) : (<>{body}{footer}</>)}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 20, paddingTop: 8, paddingBottom: 12 },
  school: { fontFamily: fonts.bodySemi, fontSize: 13, color: C.muted },
  title: { fontFamily: fonts.heading, fontSize: 22, color: C.onSurface, marginTop: -1 },
  content: { padding: 20, paddingTop: 4, gap: 16, paddingBottom: 40 },
  stackHeader: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 8, paddingVertical: 6, minHeight: 56 },
  backBtn: { width: 44, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  stackTitle: { flex: 1, fontFamily: fonts.heading, fontSize: 20, color: C.onSurface },
  offline: { flexDirection: "row", alignItems: "center", gap: 8, marginHorizontal: 20, marginBottom: 8, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, backgroundColor: "#FFEDD5" },
  offlineText: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: 13, color: "#7C2D12" },
  offlineRetry: { fontFamily: fonts.bodyBold, fontSize: 14, color: "#7C2D12" },
});
