import { StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { useMe } from "@/src/lib/queries";
import { StackScreen } from "@/src/ui/Screen";
import { C, Card, Empty, ErrorState, SectionTitle, SkeletonList, k } from "@/src/ui/kit";
import { Trends } from "@/src/parent/Trends";
import { fonts } from "@/src/theme";

export default function StudentResults() {
  const q = useMe();
  const results = [...(q.data?.results || [])].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  const go = (subject: string) => router.push({ pathname: "/student/more/subject/[name]", params: { name: subject } });
  return (
    <StackScreen title="Results" testID="student-results-screen">
      {q.isLoading ? <SkeletonList n={3} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !results.length ? (
        <Card><Empty icon="award" text="No published results yet — they appear here once your school publishes them." testID="student-results-empty" /></Card>
      ) : (
        <>
          <SectionTitle title="By subject" />
          <Trends results={results} onSubject={go} />
          <SectionTitle title="All results" />
          <Card style={{ padding: 0 }} testID="student-results-list">
            {results.map((r: any, i: number) => (
              <View key={i} style={[s.row, i < results.length - 1 && s.line]}>
                <View style={{ flex: 1 }}><Text style={s.sub}>{r.subject || "—"}</Text><Text style={k.small} numberOfLines={2}>{r.assessment}</Text></View>
                <Text style={s.score}>{r.score ?? "—"}{r.max_marks ? <Text style={k.small}> / {r.max_marks}</Text> : null}</Text>
              </View>
            ))}
          </Card>
        </>
      )}
    </StackScreen>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: 12, padding: 16, minHeight: 64 },
  line: { borderBottomWidth: 1, borderBottomColor: C.divider },
  sub: { fontFamily: fonts.bodyBold, fontSize: 15, color: C.onSurface },
  score: { fontFamily: fonts.heading, fontSize: 18, color: C.onSurface },
});
