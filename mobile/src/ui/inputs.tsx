// Text inputs: labelled field + password field with show/hide eye.
import { useState } from "react";
import { Platform, Pressable, StyleSheet, Text, TextInput, View, type TextInputProps } from "react-native";
import { Feather } from "@expo/vector-icons";
import { fonts } from "@/src/theme";
import { C } from "./kit";
import { useBrand } from "@/src/state/auth";

type Props = TextInputProps & { label?: string; hint?: string; error?: string; testID?: string };

export function TextField({ label, hint, error, style, multiline, ...rest }: Props) {
  const [focus, setFocus] = useState(false);
  const b = useBrand();
  return (
    <View style={{ gap: 6 }}>
      {label && <Text style={f.label}>{label}</Text>}
      <TextInput placeholderTextColor={C.muted} multiline={multiline}
        onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
        style={[f.input, multiline && f.multi, focus && { borderColor: b.color, backgroundColor: "#fff" }, error ? { borderColor: C.error } : null, style]} {...rest} />
      {hint && !error ? <Text style={f.hint}>{hint}</Text> : null}
      {error ? <Text style={f.error}>{error}</Text> : null}
    </View>
  );
}

export function PasswordField({ label, testID, ...rest }: Props) {
  const [show, setShow] = useState(false);
  const [focus, setFocus] = useState(false);
  const b = useBrand();
  return (
    <View style={{ gap: 6 }}>
      {label && <Text style={f.label}>{label}</Text>}
      <View style={[f.input, f.pwWrap, focus && { borderColor: b.color, backgroundColor: "#fff" }]}>
        <TextInput {...rest} testID={testID} secureTextEntry={!show} autoCapitalize="none" autoCorrect={false} spellCheck={false}
          keyboardType={show && Platform.OS === "android" ? "visible-password" : "default"}
          onFocus={() => setFocus(true)} onBlur={() => setFocus(false)} placeholderTextColor={C.muted} style={f.pwInput} />
        <Pressable onPress={() => setShow((v) => !v)} hitSlop={10} style={f.eye} testID={`${testID || "password"}-toggle`}
          accessibilityLabel={show ? "Hide password" : "Show password"}>
          <Feather name={show ? "eye-off" : "eye"} size={20} color={C.muted} />
        </Pressable>
      </View>
    </View>
  );
}

const f = StyleSheet.create({
  label: { fontFamily: fonts.bodySemi, fontSize: 14, color: C.onSurfaceSecondary },
  input: { minHeight: 54, borderRadius: 14, borderWidth: 1.5, borderColor: C.border, backgroundColor: C.surfaceTertiary, paddingHorizontal: 16, fontFamily: fonts.bodyMedium, fontSize: 16, color: C.onSurface },
  multi: { minHeight: 110, paddingTop: 14, textAlignVertical: "top" },
  pwWrap: { flexDirection: "row", alignItems: "center", paddingHorizontal: 0 },
  pwInput: { flex: 1, minHeight: 50, paddingHorizontal: 16, fontFamily: fonts.bodyMedium, fontSize: 16, color: C.onSurface },
  eye: { width: 52, height: 50, alignItems: "center", justifyContent: "center" },
  hint: { fontFamily: fonts.body, fontSize: 13, color: C.muted, lineHeight: 18 },
  error: { fontFamily: fonts.bodyMedium, fontSize: 13, color: C.error },
});
