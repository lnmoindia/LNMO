import { useState } from "react";
import { View, Text } from "react-native";
import { router } from "expo-router";
import { useTeacherWork } from "@/src/lib/queries";
import { TabScreen } from "@/src/ui/Screen";
import { Button, Card, Chip, Empty, ErrorState, SkeletonList, StatusChip, k } from "@/src/ui/kit";
import { fmtDate, todayISO } from "@/src/lib/format";

const due = (x: any) => String(x.due_date || "").slice(0, 10);

export default function TeacherHomework() {
  const q = useTeacherWork();
  const [f, setF] = useState("active");
  const t = todayISO();
  const list = (q.data || []).filter((x: any) => f === "today" ? due(x) === t : f === "past" ? due(x) < t || x.status === "closed" : due(x) >= t && x.status !== "closed")
    .sort((a: any, b: any) => due(a).localeCompare(due(b)));
  return (
    <TabScreen testID="teacher-homework-screen" title="Homework" showSwitcher={false}>
      <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
        {[["active", "Active"], ["today", "Due today"], ["past", "Past"]].map(([key, l]) => <Chip key={key} label={l} active={f === key} onPress={() => setF(key)} testID={`thw-filter-${key}`} />)}
      </View>
      <Button label="New homework / assignment" icon="plus" onPress={() => router.push("/teacher/hw-new")} testID="thw-new-btn" />
      {q.isLoading ? <SkeletonList n={3} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !list.length ? <Card><Empty icon="book-open" text="Nothing in this list." testID="thw-empty" /></Card>
        : list.map((x: any) => (
          <Card key={x.id} onPress={() => router.push(`/teacher/hw/${x.kind}/${x.id}`)} style={{ gap: 4 }} testID={`thw-item-${x.id}`}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
              <Text style={k.small}>{x.kind === "assignment" ? "Assignment · " : ""}{x.class_name} {x.section} · {x.subject}</Text>
              <StatusChip status={x.status} />
            </View>
            <Text style={k.h2}>{x.title}</Text>
            <Text style={k.small}>Due {fmtDate(x.due_date, { weekday: true, year: false })}{x.counts ? ` · Submitted ${x.counts.submitted || 0}/${x.counts.total_students ?? "—"}` : ""}</Text>
          </Card>
        ))}
    </TabScreen>
  );
}
