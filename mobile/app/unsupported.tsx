// Roles other than parent arrive in later phases (student M2, teacher M4).
import { StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { useAuth } from "@/src/state/auth";
import { Button, Empty, k } from "@/src/ui/kit";
import { SchoolLogo } from "@/src/ui/brandbits";

const ROLE: Record<string, string> = { institution_admin: "school admin", platform_admin: "platform manager" };

export default function Unsupported() {
  const { user, logout } = useAuth();
  return (
    <SafeAreaView style={s.safe} testID="unsupported-role-screen">
      <View style={s.content}>
        <SchoolLogo size={56} />
        <Text style={k.h1}>Hi {user?.name?.split(" ")[0] || "there"}</Text>
        <Empty icon="smartphone" title={`The ${ROLE[user?.role] || user?.role || ""} app is coming soon`}
          text="The mobile app is currently for parents and students. Please use your school's web portal for now." />
        <Button label="Sign out" variant="outline" icon="log-out" onPress={async () => { await logout(); router.replace("/login"); }} testID="unsupported-signout-btn" />
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#fff" },
  content: { padding: 24, paddingTop: 48, gap: 16, maxWidth: 520, width: "100%", alignSelf: "center" },
});
