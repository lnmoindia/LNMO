// First launch: type your school code (sunrise, lpgs, …) → resolved via the public branding endpoint.
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useLocalSearchParams } from "expo-router";
import { Image } from "expo-image";
import { Feather } from "@expo/vector-icons";
import { useAuth } from "@/src/state/auth";
import { Button, C, k } from "@/src/ui/kit";
import { TextField } from "@/src/ui/inputs";
import { fonts } from "@/src/theme";

export default function SchoolScreen() {
  const { resolveSchool, setSchool } = useAuth();
  const params = useLocalSearchParams<{ code?: string; error?: string }>();
  const [code, setCode] = useState(params.code || "");
  const [err, setErr] = useState(params.error || "");
  const [busy, setBusy] = useState(false);

  const go = async () => {
    if (!code.trim()) return;
    setBusy(true); setErr("");
    try {
      const s = await resolveSchool(code);
      await setSchool(s);
      router.replace("/login");
    } catch (e: any) { setErr(e?.message || "Couldn't find that school"); } finally { setBusy(false); }
  };

  return (
    <SafeAreaView style={s.safe} testID="school-select-screen">
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
          <Image source={require("../assets/images/lnmo-logo.png")} style={s.logo} contentFit="contain" testID="school-select-logo" />
          <View style={{ gap: 8 }}>
            <Text style={k.h1}>Find your school</Text>
            <Text style={k.body}>{"Enter the school code your school shared with you. It's usually the last part of your school's login link."}</Text>
          </View>
          <TextField label="School code" value={code} onChangeText={(v) => { setCode(v); setErr(""); }}
            placeholder="e.g. sunrise" autoCapitalize="none" autoCorrect={false} returnKeyType="go" onSubmitEditing={go}
            testID="school-code-input" />
          {err ? (
            <View style={s.errBox} testID="school-code-error">
              <Feather name="alert-circle" size={18} color={C.error} />
              <Text style={s.errText}>{err}</Text>
            </View>
          ) : null}
          <Button label="Continue" icon="arrow-right" onPress={go} loading={busy} disabled={!code.trim()} testID="school-continue-btn" />
          <View style={s.tip}>
            <Feather name="link" size={16} color={C.muted} />
            <Text style={s.tipText}>Opened a school link like …/login/sunrise? The app fills the code in for you.</Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#FFFFFF" },
  content: { padding: 24, paddingTop: 48, gap: 22, maxWidth: 520, width: "100%", alignSelf: "center" },
  logo: { width: 110, height: 77, marginBottom: 12 },
  errBox: { flexDirection: "row", gap: 10, alignItems: "center", padding: 14, borderRadius: 14, backgroundColor: C.errorSoft },
  errText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 14, color: C.error },
  tip: { flexDirection: "row", gap: 10, alignItems: "flex-start", paddingTop: 8 },
  tipText: { flex: 1, fontFamily: fonts.body, fontSize: 13, color: C.muted, lineHeight: 19 },
});
