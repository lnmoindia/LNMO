// Tiny toast: one message at a time, slides in above the tab bar.
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { Animated, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { fonts } from "@/src/theme";

type Tone = "success" | "error" | "info";
const ToastCtx = createContext<(msg: string, tone?: Tone) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [t, setT] = useState<{ msg: string; tone: Tone } | null>(null);
  const op = useRef(new Animated.Value(0)).current;
  const timer = useRef<any>(null);
  const insets = useSafeAreaInsets();
  const show = useCallback((msg: string, tone: Tone = "success") => {
    clearTimeout(timer.current);
    setT({ msg, tone });
    Animated.timing(op, { toValue: 1, duration: 180, useNativeDriver: true }).start();
    timer.current = setTimeout(() => {
      Animated.timing(op, { toValue: 0, duration: 220, useNativeDriver: true }).start(() => setT(null));
    }, 3200);
  }, [op]);
  const icon = t?.tone === "error" ? "alert-circle" : t?.tone === "info" ? "info" : "check-circle";
  const bg = t?.tone === "error" ? "#9F1239" : t?.tone === "info" ? "#1E293B" : "#065F46";
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {t && (
        <Animated.View pointerEvents="none" style={[s.wrap, { bottom: insets.bottom + 84, opacity: op, transform: [{ translateY: op.interpolate({ inputRange: [0, 1], outputRange: [16, 0] }) }] }]}>
          <View style={[s.toast, { backgroundColor: bg }]} testID="app-toast">
            <Feather name={icon as any} size={18} color="#fff" />
            <Text style={s.text}>{t.msg}</Text>
          </View>
        </Animated.View>
      )}
    </ToastCtx.Provider>
  );
}

const s = StyleSheet.create({
  wrap: { position: "absolute", left: 16, right: 16, alignItems: "center" },
  toast: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 12, borderRadius: 14, maxWidth: 520, shadowColor: "#000", shadowOpacity: 0.18, shadowRadius: 12, shadowOffset: { width: 0, height: 4 }, elevation: 6 },
  text: { color: "#fff", fontFamily: fonts.bodySemi, fontSize: 14, flexShrink: 1 },
});
