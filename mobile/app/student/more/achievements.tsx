import { StyleSheet, Text, View } from "react-native";
import { Feather } from "@expo/vector-icons";
import { useMe } from "@/src/lib/queries";
import { StackScreen } from "@/src/ui/Screen";
import { C, Card, Empty, ErrorState, SkeletonList, k } from "@/src/ui/kit";
import { fmtDate } from "@/src/lib/format";
import { fonts } from "@/src/theme";

export default function StudentAchievements() {
  const q = useMe();
  const list = q.data?.achievements || [];
  return (
    <StackScreen title="Achievements" testID="student-achievements-screen">
      {q.isLoading ? <SkeletonList n={3} height={70} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !list.length
        ? <Card><Empty icon="star" title="Nothing yet" text="No achievements recorded yet — keep going!" testID="student-achievements-empty" /></Card>
        : list.map((a: any) => (
          <Card key={a.id} style={s.row} testID={`student-achievement-${a.id}`}>
            <View style={s.icon}><Feather name="star" size={20} color="#B45309" /></View>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={s.title}>{a.title}</Text>
              {a.description ? <Text style={k.body}>{a.description}</Text> : null}
              {a.date ? <Text style={k.small}>{fmtDate(a.date)}</Text> : null}
            </View>
          </Card>
        ))}
    </StackScreen>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: "row", gap: 14, alignItems: "flex-start" },
  icon: { width: 42, height: 42, borderRadius: 14, backgroundColor: "#FEF3C7", alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.bodyBold, fontSize: 16, color: C.onSurface },
});
