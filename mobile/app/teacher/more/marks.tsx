// Read-only marks registers (marks entry stays on the web for now).
import { Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/lib/api";
import { StackScreen } from "@/src/ui/Screen";
import { Card, Empty, SkeletonList, StatusChip, k } from "@/src/ui/kit";

export default function Marks() {
  const q = useQuery({ queryKey: ["t-assess"], queryFn: async () => (await api.get("/teacher/assessments")).assessments || [] });
  return (
    <StackScreen title="Marks registers" testID="teacher-marks-screen">
      <Text style={k.small}>Marks entry and submission are on the web for now. Here you can see your registers.</Text>
      {q.isLoading ? <SkeletonList n={3} /> : !q.data?.length ? <Card><Empty icon="edit-3" text="No assessments yet." /></Card> : q.data.map((a: any) => (
        <Card key={a.id} style={{ gap: 4 }} testID={`marks-${a.id}`}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}><Text style={[k.label, { flex: 1 }]}>{a.name}</Text><StatusChip status={a.status || "pending"} /></View>
          <Text style={k.small}>{a.class_name} {a.section || "(all sections)"} · {a.subject} · max {a.max_marks}</Text>
        </Card>
      ))}
    </StackScreen>
  );
}
