// Splash + entry router: school → login → (change password) → parent app.
import { useEffect, useRef, useState } from "react";
import { Animated, StyleSheet, View } from "react-native";
import { Redirect } from "expo-router";
import { Image } from "expo-image";
import { useAuth } from "@/src/state/auth";
import { loadView, viewHome, type AppView } from "@/src/state/view";

let shownOnce = false;

export default function Index() {
  const { ready, school, user } = useAuth();
  const [waited, setWaited] = useState(shownOnce);
  const op = useRef(new Animated.Value(0)).current;
  const principal = user?.role === "teacher" && Boolean(user?.is_principal);
  const [view, setView] = useState<{ uid: string; v: AppView } | null>(null);
  useEffect(() => { if (principal && user?.id) loadView(user.id).then((v) => setView({ uid: user.id, v })); }, [principal, user?.id]);
  useEffect(() => {
    Animated.timing(op, { toValue: 1, duration: 450, useNativeDriver: true }).start();
    if (shownOnce) return undefined;
    const t = setTimeout(() => { shownOnce = true; setWaited(true); }, 1100);
    return () => clearTimeout(t);
  }, [op]);

  if (ready && waited && !(principal && view?.uid !== user?.id)) {
    if (!school && !user) return <Redirect href="/school" />;
    if (!user) return <Redirect href="/login" />;
    if (user.must_change_password) return <Redirect href="/change-password" />;
    if (user.role === "parent") return <Redirect href="/home" />;
    if (user.role === "student") return <Redirect href="/student/today" />;
    if (principal && view && view.uid === user.id) return <Redirect href={viewHome(view.v)} />; // last chosen view (default Principal)
    if (user.role === "teacher") return <Redirect href="/teacher/today" />;
    return <Redirect href="/unsupported" />;
  }
  return (
    <View style={s.wrap} testID="splash-screen">
      <Animated.View style={{ opacity: op, transform: [{ scale: op.interpolate({ inputRange: [0, 1], outputRange: [0.94, 1] }) }] }}>
        <Image source={require("../assets/images/lnmo-logo.png")} style={s.logo} contentFit="contain" testID="splash-logo" />
      </Animated.View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" },
  logo: { width: 180, height: 126 },
});
