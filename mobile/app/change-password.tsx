// Forced password change (backend 403 PASSWORD_CHANGE_REQUIRED or must_change_password on the user).
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useAuth, useBrand } from "@/src/state/auth";
import { api, saveTokens } from "@/src/lib/api";
import { Button, C, k } from "@/src/ui/kit";
import { PasswordField } from "@/src/ui/inputs";
import { fonts } from "@/src/theme";
import { useToast } from "@/src/state/toast";

export default function ChangePassword() {
  const { user, refreshMe, logout } = useAuth();
  const b = useBrand();
  const toast = useToast();
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const strict = Boolean(user?.pw_set_by_staff);

  const submit = async () => {
    setErr("");
    if (strict && !(pw.length >= 8 && /[A-Z]/.test(pw) && /[a-z]/.test(pw) && /\d/.test(pw))) return setErr("Use at least 8 characters with an uppercase letter, a lowercase letter and a number.");
    if (pw.length < 6) return setErr("Password must be at least 6 characters");
    if (pw !== pw2) return setErr("Passwords do not match");
    setBusy(true);
    try {
      const d = await api.post("/auth/change-password", { new_password: pw });
      await saveTokens(d?.access_token, d?.refresh_token);
      await refreshMe();
      toast("Password updated");
      router.replace("/");
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const signOut = async () => { await logout(); router.replace("/login"); };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: "#fff" }} testID="change-password-screen">
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
          <View style={[s.icon, { backgroundColor: b.soft }]}><Feather name="key" size={26} color={b.ink} /></View>
          <Text style={k.h1}>Set a new password</Text>
          <Text style={k.body} testID="change-password-intro">
            {strict ? "Your school reset your password. Choose your own new password before continuing." : "For security, please choose your own password before continuing."}
          </Text>
          {strict && <Text style={k.small}>At least 8 characters with an uppercase letter, a lowercase letter and a number.</Text>}
          <PasswordField label="New password" value={pw} onChangeText={setPw} testID="new-password-input" />
          <PasswordField label="Confirm password" value={pw2} onChangeText={setPw2} testID="confirm-password-input" onSubmitEditing={submit} />
          {err ? <Text style={s.err} testID="change-password-error">{err}</Text> : null}
          <Button label={busy ? "Saving…" : "Update password"} onPress={submit} loading={busy} testID="change-password-submit-btn" />
          <Button label="Sign out" variant="ghost" onPress={signOut} testID="change-password-signout-btn" />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  content: { padding: 24, paddingTop: 40, gap: 16, maxWidth: 520, width: "100%", alignSelf: "center" },
  icon: { width: 56, height: 56, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  err: { fontFamily: fonts.bodySemi, fontSize: 14, color: C.error },
});
