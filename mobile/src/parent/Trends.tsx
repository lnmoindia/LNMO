// Simple per-subject score trend (shared by parent + student results).
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Feather } from "@expo/vector-icons";
import { C, Card, k } from "@/src/ui/kit";
import { fonts } from "@/src/theme";

const PALETTE = ["#4F46E5", "#DB2777", "#0284C7", "#059669", "#D97706", "#7C3AED", "#DC2626", "#0D9488"];

// Simple trend: one row per subject with a bar per assessment (oldest → newest).
export function Trends({ results, onSubject }: { results: any[]; onSubject?: (s: string) => void }) {
  const by: Record<string, any[]> = {};
  results.forEach((r) => { if (r.score != null && r.max_marks) (by[r.subject || "—"] = by[r.subject || "—"] || []).push(r); });
  const subs = Object.keys(by).sort();
  if (!subs.length) return null;
  return (
    <Card style={{ gap: 14 }} testID="results-trends">
      {subs.map((sub, idx) => {
        const items = [...by[sub]].sort((a, b) => String(a.created_at || a.date || "").localeCompare(String(b.created_at || b.date || "")));
        const pcts = items.map((r) => Math.round((r.score / r.max_marks) * 100));
        const last = pcts[pcts.length - 1];
        const delta = last - pcts[0];
        const color = PALETTE[idx % PALETTE.length];
        return (
          <Pressable key={sub} style={s.tRow} testID={`results-trend-${sub}`} onPress={onSubject ? () => onSubject(sub) : undefined} disabled={!onSubject}>
            <View style={{ flex: 1 }}>
              <Text style={s.tSub} numberOfLines={1}>{sub}</Text>
              <Text style={k.small}>{items.length} assessment{items.length > 1 ? "s" : ""}</Text>
            </View>
            <View style={s.bars}>
              {pcts.slice(-6).map((p, i) => <View key={i} style={[s.bar, { height: Math.max(4, (p / 100) * 36), backgroundColor: color, opacity: 0.45 + (0.55 * (i + 1)) / Math.min(6, pcts.length) }]} />)}
            </View>
            <View style={{ width: 54, alignItems: "flex-end" }}>
              <Text style={[s.tPct, { color }]}>{last}%</Text>
              {pcts.length > 1 && <Text style={[s.delta, { color: delta >= 0 ? C.success : C.error }]}>{delta >= 0 ? "▲" : "▼"}{Math.abs(delta)}</Text>}
            </View>
            {onSubject ? <Feather name="chevron-right" size={18} color={C.muted} /> : null}
          </Pressable>
        );
      })}
    </Card>
  );
}

const s = StyleSheet.create({
  tRow: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 44 },
  tSub: { fontFamily: fonts.bodyBold, fontSize: 15, color: C.onSurface },
  bars: { flexDirection: "row", alignItems: "flex-end", gap: 4, height: 38 },
  bar: { width: 9, borderRadius: 3 },
  tPct: { fontFamily: fonts.heading, fontSize: 17 },
  delta: { fontFamily: fonts.bodyBold, fontSize: 11 },
});
