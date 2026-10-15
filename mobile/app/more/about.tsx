import { StyleSheet, Text, View } from "react-native";
import { Image } from "expo-image";
import Constants from "expo-constants";
import { useBrand } from "@/src/state/auth";
import { StackScreen } from "@/src/ui/Screen";
import { Card, k } from "@/src/ui/kit";
import { SchoolLogo } from "@/src/ui/brandbits";

export default function About() {
  const b = useBrand();
  return (
    <StackScreen title="About" testID="about-screen">
      <Card style={s.card}>
        <SchoolLogo size={64} />
        <Text style={k.h2}>{b.name}</Text>
        {b.tagline ? <Text style={[k.small, { textAlign: "center" }]}>{b.tagline}</Text> : null}
      </Card>
      <Card style={s.card} testID="about-powered-by">
        <Image source={require("../../assets/images/lnmo-logo.png")} style={{ width: 110, height: 77 }} contentFit="contain" />
        <Text style={k.label}>Powered by LNMO</Text>
        <Text style={k.small} testID="about-version">Version {Constants.expoConfig?.version || "1.0.0"}</Text>
      </Card>
      <View />
    </StackScreen>
  );
}

const s = StyleSheet.create({ card: { alignItems: "center", gap: 8, paddingVertical: 24 } });
