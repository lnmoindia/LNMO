// Email invite link (/setup/parent/:token) — opened via deep link; sets the password and signs in.
import { useEffect, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useLocalSearchParams } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { api, absUrl } from "@/src/lib/api";
import { useAuth } from "@/src/state/auth";
import { Button, C, Card, k } from "@/src/ui/kit";
import { PasswordField, TextField } from "@/src/ui/inputs";
import { SchoolLogo } from "@/src/ui/brandbits";
import { fonts } from "@/src/theme";

export default function ParentSetup() {
  const { token } = useLocalSearchParams<{ token: string }>();
  const { acceptSession, setSchool, resolveSchool } = useAuth();
  const [info, setInfo] = useState<any>(null);
  const [err, setErr] = useState("");
  const [a, setA] = useState("");
  const [b2, setB2] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const strong = a.length >= 8 && /[A-Z]/.test(a) && /[a-z]/.test(a) && /\d/.test(a);

  useEffect(() => {
    api.get(`/public/parent-setup/${token}`).then((d) => { setInfo(d); setName(d.parent_name || ""); }).catch((e) => setErr(e.message));
  }, [token]);

  const submit = async () => {
    if (a !== b2) return setErr("Passwords do not match");
    setBusy(true); setErr("");
    try {
      const d = await api.post(`/public/parent-setup/${token}`, info.single_use ? { password: a, name, phone } : { password: a });
      if (info.login_key) { try { await setSchool(await resolveSchool(info.login_key)); } catch { /* keep current */ } }
      await acceptSession(d);
      router.replace("/");
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  if (!info) return (
    <SafeAreaView style={s.center} testID="parent-setup-screen">
      {err ? <Card style={{ margin: 24 }}><Text style={s.err} testID="parent-setup-error">{err}</Text>
        <Button label="Go to sign in" variant="outline" onPress={() => router.replace("/")} style={{ marginTop: 12 }} testID="parent-setup-signin-btn" /></Card>
        : <ActivityIndicator size="large" />}
    </SafeAreaView>
  );
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: "#fff" }} testID="parent-setup-screen">
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
          <SchoolLogo size={56} uri={absUrl(info.branding?.logo_url)} name={info.school_name} />
          <Text style={k.h1}>Welcome, {info.parent_name}</Text>
          <Text style={k.body}>{info.school_name} has invited you to the parent app.</Text>
          <Card style={{ gap: 8 }} testID="parent-setup-children">
            {info.children.map((c: any) => (
              <View key={c.name} style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
                <Feather name="user" size={16} color={C.muted} /><Text style={k.label}>{c.name}</Text><Text style={k.small}>· {c.class}</Text>
              </View>
            ))}
          </Card>
          {info.single_use && <TextField label="Your name" value={name} onChangeText={setName} testID="parent-setup-name-input" />}
          <PasswordField label="Choose a password" value={a} onChangeText={setA} testID="parent-setup-password-input" />
          <PasswordField label="Confirm password" value={b2} onChangeText={setB2} testID="parent-setup-confirm-input" />
          {info.single_use && <Text style={[k.small, a && !strong ? { color: C.error } : null]}>At least 8 characters with an uppercase letter, a lowercase letter and a number.</Text>}
          {info.single_use && !info.phone && <TextField label="Mobile number (optional)" keyboardType="number-pad" value={phone} onChangeText={setPhone} placeholder="10-digit mobile" testID="parent-setup-phone-input" />}
          {info.phone ? <Text style={k.small}>You can sign in with your mobile number {info.phone} and this password.</Text> : null}
          <Text style={k.small}>Or use your login ID: {info.login_email}</Text>
          {err ? <Text style={s.err} testID="parent-setup-error">{err}</Text> : null}
          <Button label={busy ? "Setting up…" : "Set password & open app"} onPress={submit} loading={busy}
            disabled={info.single_use ? !strong : a.length < 6} testID="parent-setup-submit-btn" />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#fff" },
  content: { padding: 24, gap: 16, maxWidth: 520, width: "100%", alignSelf: "center" },
  err: { fontFamily: fonts.bodySemi, fontSize: 14, color: C.error },
});
