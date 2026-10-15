// Branded login: school background + logo + name + tagline, identifier + password (eye), clear errors.
import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { Redirect, router } from "expo-router";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Feather } from "@expo/vector-icons";
import { useAuth } from "@/src/state/auth";
import { ApiError, absUrl } from "@/src/lib/api";
import { Button, C, k } from "@/src/ui/kit";
import { PasswordField, TextField } from "@/src/ui/inputs";
import { PoweredBy, SchoolLogo } from "@/src/ui/brandbits";
import { fonts } from "@/src/theme";

const loginError = (e: any, pw: string) => {
  const code = e instanceof ApiError ? e.status : -1;
  if (code === 0) return "Can't reach the school server. Check your internet connection and try again.";
  if (code === 429) return "Too many attempts — try again in 15 min.";
  if (code >= 500) return `The school server had a problem (${code}). Please try again in a minute.`;
  if (code === 403 || code === 423) return e.message || "This account is locked or inactive. Contact your school office.";
  if (code === 401) {
    const edge = pw !== pw.trim() ? " Your password starts or ends with a space — remove it if that's not intended." : "";
    return `${e.message}. Check for typos — after 5 failed tries the account is paused for 15 minutes.${edge}`;
  }
  return e?.message || "Something went wrong";
};

export default function LoginScreen() {
  const { ready, school, login, setSchool } = useAuth();
  const insets = useSafeAreaInsets();
  const [id, setId] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  if (!ready) return <View style={s.root} testID="login-loading" />;
  if (!school) return <Redirect href="/school" />;

  const submit = async () => {
    if (!id.trim() || !pw) { setErr("Enter your email, mobile or admission number and your password."); return; }
    setBusy(true); setErr("");
    try { await login(id, pw); router.replace("/"); }
    catch (e) { setErr(loginError(e, pw)); } finally { setBusy(false); }
  };
  const changeSchool = async () => { await setSchool(null); router.replace("/school"); };
  const bg = absUrl(school.background_url);

  return (
    <View style={s.root} testID="login-screen">
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={{ flexGrow: 1 }} keyboardShouldPersistTaps="handled" bounces={false}>
          <View style={[s.hero, { paddingTop: insets.top + 16 }]}>
            {bg ? <Image source={{ uri: bg }} style={StyleSheet.absoluteFill} contentFit="cover" testID="login-school-bg" /> : null}
            <LinearGradient colors={["rgba(15,23,42,0.15)", "rgba(15,23,42,0.55)", "rgba(15,23,42,0.92)"]} style={StyleSheet.absoluteFill} />
            <Pressable onPress={changeSchool} style={s.changeBtn} testID="login-change-school-btn" hitSlop={6}>
              <Feather name="repeat" size={14} color="#fff" />
              <Text style={s.changeText}>Change school</Text>
            </Pressable>
            <View style={s.brandRow}>
              <SchoolLogo size={60} uri={absUrl(school.logo_url)} name={school.name} testID="login-school-logo" />
              <View style={{ flex: 1 }}>
                <Text style={s.schoolName} testID="login-school-name">{school.name}</Text>
                {school.tagline ? <Text style={s.tagline} testID="login-school-tagline">{school.tagline}</Text> : null}
              </View>
            </View>
          </View>
          <View style={s.form}>
            <View style={{ gap: 4 }}>
              <Text style={k.h1}>Welcome back</Text>
              <Text style={k.small}>Students, parents and staff of {school.name}.</Text>
            </View>
            <TextField label="Email, mobile or admission no." value={id} onChangeText={(v) => { setId(v); setErr(""); }}
              placeholder="you@school.edu, 98470 12345 or SPS-001" autoCapitalize="none" autoCorrect={false} spellCheck={false}
              keyboardType="email-address" autoComplete="username" textContentType="username" importantForAutofill="yes"
              hint="Students: school email or admission number. Parents: email or registered mobile. Staff: school email."
              testID="login-identifier-input" />
            <PasswordField label="Password" value={pw} onChangeText={(v) => { setPw(v); setErr(""); }} placeholder="••••••••"
              autoComplete="current-password" textContentType="password" returnKeyType="go" onSubmitEditing={submit} testID="login-password-input" />
            {err ? (
              <View style={s.errBox} testID="login-error">
                <Feather name="alert-circle" size={18} color={C.error} />
                <Text style={s.errText}>{err}</Text>
              </View>
            ) : null}
            <Button label={busy ? "Signing in…" : "Sign in"} onPress={submit} loading={busy} testID="login-submit-btn" />
            <View style={{ flex: 1 }} />
            <SafeAreaView edges={["bottom"]}><PoweredBy testID="login-powered-by" /></SafeAreaView>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#FFFFFF" },
  hero: { minHeight: 300, justifyContent: "flex-end", padding: 20, paddingBottom: 40, overflow: "hidden", backgroundColor: "#0F172A" },
  changeBtn: { position: "absolute", top: 52, right: 16, flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, minHeight: 36, borderRadius: 999, backgroundColor: "rgba(255,255,255,0.18)" },
  changeText: { fontFamily: fonts.bodySemi, fontSize: 13, color: "#fff" },
  brandRow: { flexDirection: "row", alignItems: "center", gap: 14 },
  schoolName: { fontFamily: fonts.heading, fontSize: 24, color: "#fff", lineHeight: 28 },
  tagline: { fontFamily: fonts.bodyMedium, fontSize: 14, color: "rgba(255,255,255,0.85)", marginTop: 4 },
  form: { flex: 1, marginTop: -20, borderTopLeftRadius: 28, borderTopRightRadius: 28, backgroundColor: "#FFFFFF", padding: 24, gap: 18, maxWidth: 560, width: "100%", alignSelf: "center" },
  errBox: { flexDirection: "row", gap: 10, alignItems: "flex-start", padding: 14, borderRadius: 14, backgroundColor: C.errorSoft },
  errText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 14, color: C.error, lineHeight: 20 },
});
