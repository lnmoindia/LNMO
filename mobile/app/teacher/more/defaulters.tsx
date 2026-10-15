// Fee defaulters — teacher scope (view only), GET /fees/defaulters (same as web DefaultersTab).
import { Linking, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/lib/api";
import { StackScreen } from "@/src/ui/Screen";
import { Button, Card, Empty, ErrorState, SkeletonList, k } from "@/src/ui/kit";
import { fmtDate, inr } from "@/src/lib/format";

function Row({ r }: { r: any }) {
  return (
    <Card style={{ gap: 8 }} testID={`defaulter-${r.student_id}`}>
      <View style={{ flexDirection: "row", alignItems: "flex-start", gap: 12 }}>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={k.label}>{r.student_name}</Text>
          <Text style={k.small}>{r.admission_no} · {r.class_name} {r.section}</Text>
          <Text style={k.small}>{r.days_late ? `${r.days_late} days late` : "Overdue"}{r.oldest_due_date ? ` · due ${fmtDate(r.oldest_due_date)}` : ""}</Text>
        </View>
        <View style={{ alignItems: "flex-end" }}>
          <Text style={[k.h2, { color: "#B42318" }]}>{inr(r.overdue_amount)}</Text>
          {r.total_outstanding > r.overdue_amount ? <Text style={k.small}>{inr(r.total_outstanding)} total</Text> : null}
        </View>
      </View>
      {r.parent_phone ? (
        <Button small variant="outline" icon="phone" label={`Call ${r.parent_name || "parent"}`} onPress={() => Linking.openURL(`tel:${r.parent_phone}`)} testID={`defaulter-call-${r.student_id}`} />
      ) : null}
    </Card>
  );
}

export default function Defaulters() {
  const q = useQuery({ queryKey: ["t-defaulters"], queryFn: () => api.get("/fees/defaulters") });
  const rows = q.data?.rows || [];
  const total = rows.reduce((n: number, r: any) => n + (Number(r.overdue_amount) || 0), 0);
  return (
    <StackScreen title="Fee defaulters" testID="teacher-defaulters-screen">
      <Text style={k.small}>Students of your class with overdue fees. View only — reminders are sent by the office.</Text>
      {q.isLoading ? <SkeletonList n={3} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : (
        <>
          <Card style={{ flexDirection: "row", gap: 12 }} testID="defaulters-summary">
            <View style={{ flex: 1 }}><Text style={k.small}>Students</Text><Text style={k.h2}>{q.data.total ?? rows.length}</Text></View>
            <View style={{ flex: 1 }}><Text style={k.small}>Overdue</Text><Text style={k.h2}>{inr(total)}</Text></View>
            <View style={{ flex: 1 }}><Text style={k.small}>As of</Text><Text style={k.label}>{fmtDate(q.data.as_of)}</Text></View>
          </Card>
          {!rows.length ? <Card><Empty icon="check-circle" text="No overdue fees in your class." /></Card> : rows.map((r: any) => <Row key={r.student_id} r={r} />)}
        </>
      )}
    </StackScreen>
  );
}
