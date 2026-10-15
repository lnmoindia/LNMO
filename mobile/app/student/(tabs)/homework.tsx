import { useEffect, useMemo, useState } from "react";
import { ScrollView } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { filterWork, useMyAssignments, useMyHomework } from "@/src/lib/queries";
import { TabScreen } from "@/src/ui/Screen";
import { Card, Chip, Empty, ErrorState, SectionTitle, SkeletonList } from "@/src/ui/kit";
import { WorkCard } from "@/src/student/work";
import { todayISO } from "@/src/lib/format";

const FILTERS: [string, string][] = [["due", "Due"], ["submitted", "Submitted"], ["overdue", "Overdue"], ["all", "All"]];

export default function StudentHomework() {
  const params = useLocalSearchParams<{ f?: string }>();
  const hw = useMyHomework();
  const asg = useMyAssignments();
  const [f, setF] = useState(params.f || "due");
  useEffect(() => { if (params.f) setF(params.f); }, [params.f]);
  const today = todayISO();
  const h = useMemo(() => filterWork(hw.data, f, today), [hw.data, f, today]);
  const a = useMemo(() => filterWork(asg.data, f, today), [asg.data, f, today]);
  const count = (k: string) => (filterWork(hw.data, k, today)?.length || 0) + (filterWork(asg.data, k, today)?.length || 0);
  return (
    <TabScreen testID="student-homework-screen" title="Homework" showSwitcher={false}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} testID="student-homework-filter">
        {FILTERS.map(([key, l]) => <Chip key={key} label={l} count={hw.data && asg.data ? count(key) : undefined} active={f === key} onPress={() => setF(key)} testID={`student-homework-filter-${key}`} />)}
      </ScrollView>
      {hw.isLoading || asg.isLoading ? <SkeletonList n={3} /> : hw.isError ? <ErrorState error={hw.error} onRetry={hw.refetch} /> : (
        <>
          <SectionTitle title="Homework" />
          {!h?.length ? <Card><Empty icon="check-circle" title="All caught up" text="No homework in this list." testID="student-homework-empty" /></Card>
            : h.map((x: any) => <WorkCard key={x.id} x={x} kind="homework" />)}
          <SectionTitle title="Assignments" />
          {!a?.length ? <Card><Empty icon="clipboard" text="No assignments in this list." testID="student-assignments-empty" /></Card>
            : a.map((x: any) => <WorkCard key={x.id} x={x} kind="assignment" />)}
        </>
      )}
    </TabScreen>
  );
}
