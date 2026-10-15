// Classes in my divisions with today's register status → drill into the shared register.
import { Text, View } from "react-native";
import { router } from "expo-router";
import { usePSections, useTodayAttendance } from "@/src/principal/hooks";
import { TabScreen } from "@/src/ui/Screen";
import { Card, Empty, ErrorState, SkeletonList, StatusChip, k } from "@/src/ui/kit";

export default function PrincipalAttendance() {
  const sec = usePSections();
  const att = useTodayAttendance(sec.data || []);
  return (
    <TabScreen testID="principal-attendance-screen" title="Attendance" showSwitcher={false}>
      <Text style={k.small}>Today · {att.marked} of {att.rows.length} classes marked{att.pct !== null ? ` · ${att.pct}% present` : ""}</Text>
      {sec.isLoading ? <SkeletonList n={3} /> : sec.isError ? <ErrorState error={sec.error} onRetry={sec.refetch} /> : !att.rows.length ? <Card><Empty icon="users" text="No classes in your divisions." /></Card>
        : att.rows.map((r) => (
          <Card key={`${r.class_name}${r.section}`} onPress={() => router.push({ pathname: "/principal/att", params: { c: r.class_name, s: r.section } })}
            style={{ gap: 8 }} testID={`patt-class-${r.class_name}-${r.section}`.replace(/\s/g, "")}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <Text style={[k.h2, { flex: 1 }]}>{r.class_name} {r.section}</Text>
              <StatusChip status={r.marked ? (r.final ? "approved" : "open") : "pending"} />
            </View>
            <Text style={k.small}>{r.marked ? `P ${r.present} · A ${r.absent} · L ${r.late} of ${r.total}${r.final ? " · final" : " · draft"}` : `Not marked yet · ${r.total} students`}</Text>
          </Card>
        ))}
    </TabScreen>
  );
}
