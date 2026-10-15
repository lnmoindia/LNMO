// Shared UI kit: cards, buttons, chips, empty/error/skeleton states. Big, calm, thumb-friendly.
import { useEffect, useRef, type ReactNode } from "react";
import { ActivityIndicator, Animated, Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from "react-native";
import { Feather } from "@expo/vector-icons";
import { fonts, themes } from "@/src/theme";
import { useBrand } from "@/src/state/auth";

export const C = themes.light;
export type IconName = keyof typeof Feather.glyphMap;

export function Card({ children, style, testID, onPress }: { children: ReactNode; style?: StyleProp<ViewStyle>; testID?: string; onPress?: () => void }) {
  if (onPress) {
    return (
      <Pressable testID={testID} onPress={onPress} style={({ pressed }) => [k.card, style, pressed && k.pressed]}>
        {children}
      </Pressable>
    );
  }
  return <View testID={testID} style={[k.card, style]}>{children}</View>;
}

export function SectionTitle({ title, action, onAction, testID }: { title: string; action?: string; onAction?: () => void; testID?: string }) {
  const b = useBrand();
  return (
    <View style={k.secRow}>
      <Text style={k.secTitle}>{title}</Text>
      {action && (
        <Pressable onPress={onAction} hitSlop={12} testID={testID}>
          <Text style={[k.secAction, { color: b.ink }]}>{action}</Text>
        </Pressable>
      )}
    </View>
  );
}

type BtnProps = { label: string; onPress?: () => void; icon?: IconName; variant?: "primary" | "outline" | "ghost" | "success" | "danger"; loading?: boolean; disabled?: boolean; testID?: string; style?: StyleProp<ViewStyle>; small?: boolean };
export function Button({ label, onPress, icon, variant = "primary", loading, disabled, testID, style, small }: BtnProps) {
  const b = useBrand();
  const bg = variant === "primary" ? b.color : variant === "success" ? C.success : variant === "danger" ? C.error : "transparent";
  const fg = variant === "primary" ? b.onColor : variant === "success" || variant === "danger" ? "#fff" : b.ink;
  const border = variant === "outline" ? C.borderStrong : "transparent";
  return (
    <Pressable testID={testID} onPress={onPress} disabled={disabled || loading} accessibilityRole="button"
      style={({ pressed }) => [k.btn, small && k.btnSmall, { backgroundColor: bg, borderColor: border }, (disabled || loading) && { opacity: 0.5 }, pressed && k.pressed, style]}>
      {loading ? <ActivityIndicator color={fg} /> : icon ? <Feather name={icon} size={small ? 15 : 18} color={fg} /> : null}
      <Text style={[k.btnText, small && { fontSize: 14 }, { color: fg }]}>{label}</Text>
    </Pressable>
  );
}

export function Chip({ label, active, onPress, testID, count }: { label: string; active?: boolean; onPress?: () => void; testID?: string; count?: number }) {
  const b = useBrand();
  return (
    <Pressable testID={testID} onPress={onPress} hitSlop={4}
      style={({ pressed }) => [k.chip, active ? { backgroundColor: b.color, borderColor: b.color } : null, pressed && k.pressed]}>
      <Text style={[k.chipText, active && { color: b.onColor }]}>{label}{count != null ? ` · ${count}` : ""}</Text>
    </Pressable>
  );
}

const TONES: Record<string, [string, string]> = {
  paid: [C.successSoft, C.success], approved: [C.successSoft, C.success], resolved: [C.successSoft, C.success],
  partial: [C.infoSoft, C.info], pending: [C.surfaceTertiary, C.onSurfaceTertiary],
  overdue: [C.errorSoft, C.error], rejected: [C.errorSoft, C.error],
  reversed: [C.warningSoft, C.warning], open: [C.warningSoft, C.warning], verification_pending: [C.warningSoft, C.warning],
  carried_forward: ["#F1EDFB", "#5B3FA6"], closed: [C.surfaceTertiary, C.onSurfaceTertiary],
  requested: [C.infoSoft, C.info], cancelled: [C.surfaceTertiary, C.onSurfaceTertiary],
};
export function StatusChip({ status, testID }: { status: string; testID?: string }) {
  const [bg, fg] = TONES[status] || TONES.pending;
  const label = String(status).replace(/_/g, " ");
  return (
    <View style={[k.status, { backgroundColor: bg }]} testID={testID}>
      <Text style={[k.statusText, { color: fg }]}>{label.charAt(0).toUpperCase() + label.slice(1)}</Text>
    </View>
  );
}

export function Empty({ icon = "inbox", title, text, testID, action }: { icon?: IconName; title?: string; text: string; testID?: string; action?: ReactNode }) {
  const b = useBrand();
  return (
    <View style={k.empty} testID={testID}>
      <View style={[k.emptyIcon, { backgroundColor: b.soft }]}><Feather name={icon} size={24} color={b.ink} /></View>
      {title && <Text style={k.emptyTitle}>{title}</Text>}
      <Text style={k.emptyText}>{text}</Text>
      {action}
    </View>
  );
}

export function ErrorState({ error, onRetry, testID = "error-state" }: { error: any; onRetry?: () => void; testID?: string }) {
  return (
    <Card style={{ padding: 0 }} testID={testID}>
      <Empty icon="cloud-off" title="Couldn't load this" text={error?.message || "Please try again."}
        action={onRetry ? <Button small variant="outline" label="Try again" icon="refresh-cw" onPress={onRetry} testID={`${testID}-retry`} style={{ marginTop: 12 }} /> : null} />
    </Card>
  );
}

export function Skeleton({ height = 96, style }: { height?: number; style?: StyleProp<ViewStyle> }) {
  const op = useRef(new Animated.Value(0.5)).current;
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(op, { toValue: 1, duration: 700, useNativeDriver: true }),
      Animated.timing(op, { toValue: 0.5, duration: 700, useNativeDriver: true }),
    ]));
    loop.start();
    return () => loop.stop();
  }, [op]);
  return <Animated.View style={[k.skel, { height, opacity: op }, style]} />;
}
export const SkeletonList = ({ n = 3, height = 88 }: { n?: number; height?: number }) => (
  <View style={{ gap: 12 }} testID="skeleton-loader">{Array.from({ length: n }).map((_, i) => <Skeleton key={i} height={height} />)}</View>
);

export function Field({ label, value, testID }: { label: string; value?: string | null; testID?: string }) {
  return (
    <View style={k.field} testID={testID}>
      <Text style={k.fieldLabel}>{label}</Text>
      <Text style={k.fieldValue}>{value || "—"}</Text>
    </View>
  );
}

export function ListRow({ icon, title, sub, onPress, testID, right, danger }: { icon: IconName; title: string; sub?: string; onPress?: () => void; testID?: string; right?: ReactNode; danger?: boolean }) {
  const b = useBrand();
  return (
    <Pressable testID={testID} onPress={onPress} style={({ pressed }) => [k.row, pressed && { backgroundColor: C.surfaceTertiary }]}>
      <View style={[k.rowIcon, { backgroundColor: danger ? C.errorSoft : b.soft }]}><Feather name={icon} size={19} color={danger ? C.error : b.ink} /></View>
      <View style={{ flex: 1 }}>
        <Text style={[k.rowTitle, danger && { color: C.error }]}>{title}</Text>
        {sub ? <Text style={k.rowSub} numberOfLines={2}>{sub}</Text> : null}
      </View>
      {right ?? (onPress ? <Feather name="chevron-right" size={20} color={C.muted} /> : null)}
    </Pressable>
  );
}

export const Divider = () => <View style={{ height: 1, backgroundColor: C.divider, marginLeft: 68 }} />;

export const k = StyleSheet.create({
  card: { backgroundColor: C.surfaceSecondary, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: C.border },
  pressed: { opacity: 0.85, transform: [{ scale: 0.985 }] },
  secRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 8, marginBottom: 2 },
  secTitle: { fontFamily: fonts.headingSemi, fontSize: 17, color: C.onSurface },
  secAction: { fontFamily: fonts.bodySemi, fontSize: 14 },
  btn: { minHeight: 52, borderRadius: 16, paddingHorizontal: 18, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, borderWidth: 1.5 },
  btnSmall: { minHeight: 44, borderRadius: 12, paddingHorizontal: 14 },
  btnText: { fontFamily: fonts.bodyBold, fontSize: 16 },
  chip: { minHeight: 40, paddingHorizontal: 16, borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceSecondary, justifyContent: "center" },
  chipText: { fontFamily: fonts.bodySemi, fontSize: 14, color: C.onSurfaceTertiary },
  status: { alignSelf: "flex-start", paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  statusText: { fontFamily: fonts.bodyBold, fontSize: 12 },
  empty: { alignItems: "center", paddingVertical: 28, paddingHorizontal: 20, gap: 6 },
  emptyIcon: { width: 56, height: 56, borderRadius: 18, alignItems: "center", justifyContent: "center", marginBottom: 6 },
  emptyTitle: { fontFamily: fonts.headingSemi, fontSize: 17, color: C.onSurface, textAlign: "center" },
  emptyText: { fontFamily: fonts.body, fontSize: 15, color: C.muted, textAlign: "center", lineHeight: 21 },
  skel: { backgroundColor: "#E4E8EE", borderRadius: 20 },
  field: { paddingVertical: 10 },
  fieldLabel: { fontFamily: fonts.bodySemi, fontSize: 12, letterSpacing: 0.6, textTransform: "uppercase", color: C.muted },
  fieldValue: { fontFamily: fonts.bodyMedium, fontSize: 16, color: C.onSurface, marginTop: 2 },
  row: { flexDirection: "row", alignItems: "center", gap: 14, paddingHorizontal: 16, paddingVertical: 14, minHeight: 64 },
  rowIcon: { width: 40, height: 40, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  rowTitle: { fontFamily: fonts.bodySemi, fontSize: 16, color: C.onSurface },
  rowSub: { fontFamily: fonts.body, fontSize: 13, color: C.muted, marginTop: 1 },
  h1: { fontFamily: fonts.heading, fontSize: 26, color: C.onSurface, letterSpacing: -0.3 },
  h2: { fontFamily: fonts.heading, fontSize: 20, color: C.onSurface },
  body: { fontFamily: fonts.body, fontSize: 15, color: C.onSurfaceSecondary, lineHeight: 21 },
  small: { fontFamily: fonts.body, fontSize: 13, color: C.muted },
  label: { fontFamily: fonts.bodySemi, fontSize: 14, color: C.onSurfaceSecondary },
});
