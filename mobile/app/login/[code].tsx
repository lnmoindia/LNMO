// Deep link: https://<host>/login/<code> or lnmo://login/<code> → remember the school, open its login.
import { useEffect } from "react";
import { ActivityIndicator, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useAuth } from "@/src/state/auth";

export default function LoginDeepLink() {
  const { code } = useLocalSearchParams<{ code: string }>();
  const { ready, resolveSchool, setSchool, user, logout, school } = useAuth();
  useEffect(() => {
    if (!ready || !code) return;
    (async () => {
      try {
        const s = await resolveSchool(String(code));
        if (user && school?.code !== s.code) await logout();
        await setSchool(s);
        router.replace(user && school?.code === s.code ? "/" : "/login");
      } catch (e: any) {
        router.replace({ pathname: "/school", params: { code: String(code), error: e?.message || "School not found" } });
      }
    })();
  }, [ready, code]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#fff" }} testID="login-deeplink-loading">
      <ActivityIndicator size="large" />
    </View>
  );
}
