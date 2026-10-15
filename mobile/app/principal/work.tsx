// Principal → More → Homework & assignments in their divisions → the Submissions board (same screen as teachers).
import { Text, View } from "react-native";
import { router } from "expo-router";
import { useTeacherWork } from "@/src/lib/queries";
import { StackScreen } from "@/src/ui/Screen";
import { Card, Empty, ErrorState, SkeletonList, StatusChip, k } from "@/src/ui/kit";
import { fmtDate } from "@/src/lib/format";

export default function PrincipalWork() {
  const q = useTeacherWork();
  const items = [...(q.data || [])].sort((a: any, b: any) => String(b.due_date).localeCompare(String(a.due_date)));
  return (
    <StackScreen title="Homework & assignments" testID="principal-work-screen">
      {q.isLoading ? <SkeletonList n={3} height={80} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !items.length
        ? <Card><Empty icon="book-open" text="No homework or assignments in your divisions yet." /></Card>
        : items.map((x: any) => (
          <Card key={x.id} onPress={() => router.push(`/teacher/hw/${x.kind}/${x.id}`)} style={{ gap: 4 }} testID={`pwork-${x.id}`}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
              <Text style={k.small}>{x.kind === "assignment" ? "Assignment · " : ""}{x.class_name} {x.section} · {x.subject}</Text>
              <StatusChip status={x.status} />
            </View>
            <Text style={k.label}>{x.title}</Text>
            <Text style={k.small}>Due {fmtDate(x.due_date)}{x.teacher_name ? ` · ${x.teacher_name}` : ""}</Text>
          </Card>
        ))}
    </StackScreen>
  );
}
