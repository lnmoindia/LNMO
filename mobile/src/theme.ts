// Design tokens for this app. Light theme only.Always modify the colors and theme to Dark, Light or Dark and Light according to the design guidelines.
//
// The keys match the "color" block of /app/design_guidelines.json. Fill the
// values from that file (or from the user's brand colors). Keep every key; do
// not add a second theme or colors file; do not write color literals in
// components.
//
// How the names work: a plain key is a background, and its `on` partner is the
// text or icon color that sits on top of it. Always use them as a pair.
//   <View style={{ backgroundColor: colors.brandPrimary }}>
//     <Text style={{ color: colors.onBrandPrimary }}>Continue</Text>
//   </View>
//
// Styling a screen or component: build the sheet with makeStyles so colors
// and layout live together and follow the active scheme:
//   const useStyles = makeStyles((colors) => ({
//     card: { backgroundColor: colors.surfaceSecondary, padding: 16 },
//     title: { color: colors.onSurfaceSecondary, fontSize: 16 },
//   }));
//   function Screen() {
//     const styles = useStyles();
//     return <View style={styles.card}><Text style={styles.title}>Hi</Text></View>;
//   }
// For color props that are not styles (icon color, placeholderTextColor,
// ActivityIndicator) read useTheme().colors inside the component.
// Never call StyleSheet.create with color values at module level; it cannot
// follow the scheme.
//
// To support dark mode later: add `dark` to `themes` with every key filled.
// Nothing else changes; the device setting takes over automatically.
// Feel free to add as many new colors as you need to support the design guidelines.

import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  // Calm, clean canvas; the school brand colour is layered on top at runtime (src/state/brand.tsx).
  surface: "#F5F6F8", // primary canvas, most of every screen
  onSurface: "#0F172A", // text and icons on the canvas
  surfaceSecondary: "#FFFFFF", // cards, sheets, list rows
  onSurfaceSecondary: "#1E293B", // text and icons on cards, sheets, rows
  surfaceTertiary: "#EEF1F5", // input backgrounds, chips, deepest nesting
  onSurfaceTertiary: "#475569", // text on inputs and chips; also muted text
  surfaceInverse: "#0F172A", // tooltips, snackbars, anything popping against the theme
  onSurfaceInverse: "#FFFFFF", // text and icons on the inverse surface
  muted: "#64748B", // subdued text on surface: captions, timestamps, placeholders

  // Fallback brand (calm blue-grey) — replaced per school by useBrand()
  brand: "#3F6B8A",
  onBrand: "#FFFFFF",
  brandPrimary: "#3F6B8A",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#E3ECF2",
  onBrandSecondary: "#24425A",
  brandTertiary: "#EEF3F7",
  onBrandTertiary: "#24425A",

  success: "#047857",
  onSuccess: "#FFFFFF",
  successSoft: "#E7F6EF",
  warning: "#B45309",
  onWarning: "#FFFFFF",
  warningSoft: "#FDF3E1",
  error: "#BE123C",
  onError: "#FFFFFF",
  errorSoft: "#FDECEF",
  info: "#1D4ED8",
  onInfo: "#FFFFFF",
  infoSoft: "#E8EEFC",

  border: "#E2E8F0", // hairline outline, 0.5pt or 1pt max: inputs, cards
  borderStrong: "#CBD5E1", // focus rings, selected outlines, 1.5pt max
  divider: "#EDF0F4", // subtle list separators
};

export const fonts = {
  heading: "Outfit_700Bold",
  headingSemi: "Outfit_600SemiBold",
  body: "Figtree_400Regular",
  bodyMedium: "Figtree_500Medium",
  bodySemi: "Figtree_600SemiBold",
  bodyBold: "Figtree_700Bold",
};

export type ThemeColors = typeof light;

export const defaultScheme = "light" satisfies ColorScheme;

export const themes: { light: ThemeColors; dark?: ThemeColors } = { light };

// In-app theme toggle, only after `dark` exists in `themes`. Call
// setColorScheme("dark"), setColorScheme("light"), or setColorScheme(null) to
// follow the device. Every useTheme() consumer re-renders. Persisting the
// choice and re-applying it on launch is the toggle's job.
export function setColorScheme(scheme: ColorScheme | null) {
  // RN 0.86 re-reads the device scheme only for the literal "unspecified";
  // null would pin useColorScheme() to null and the app to light.
  Appearance.setColorScheme?.(scheme ?? "unspecified");
}

// Keep native surfaces (alerts, pickers, navigation chrome) on the schemes this
// app ships: light only forces light; once `dark` exists the device decides.
// Optional call because react-native-web does not implement it.
setColorScheme?.(themes.dark ? null : defaultScheme);

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  const scheme: ColorScheme = system && themes[system] ? system : defaultScheme;
  return { scheme, colors: themes[scheme] ?? themes.light };
}

// Themed StyleSheet: returns a hook that builds the sheet from the active
// scheme's colors and memoizes it until the scheme changes.
export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}


