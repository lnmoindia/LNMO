import { StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useBrand } from "@/src/state/auth";
import { useTutorSubjects } from "@/src/lib/queries";
import { TabScreen } from "@/src/ui/Screen";
import { C, Card, Empty, ErrorState, SkeletonList, k } from "@/src/ui/kit";
import { fonts } from "@/src/theme";

export default function TutorHome() {
  const q = useTutorSubjects();
  const b = useBrand();
  const off = q.data?.ai_layer_enabled === false || (q.error as any)?.status === 403;
  const subjects = q.data?.subjects || [];
  return (
    <TabScreen testID="tutor-subjects-screen" title="AI Tutor" showSwitcher={false}>
      <Text style={k.body}>Pick a subject to start. Enabled subjects use your teachers' approved materials first.</Text>
      {off && (
        <View style={s.off} testID="tutor-disabled-banner">
          <Feather name="lock" size={18} color={C.warning} />
          <Text style={s.offText}>The AI Tutor isn't available for your school right now. Please check back later.</Text>
        </View>
      )}
      {q.isLoading ? <SkeletonList n={4} height={76} /> : q.isError && !off ? <ErrorState error={q.error} onRetry={q.refetch} /> : !subjects.length ? (
        <Card><Empty icon="zap" text="No subjects are set up for the AI Tutor yet." /></Card>
      ) : (
        <View style={s.grid}>
          {subjects.map((x: any) => (
            <Card key={x.subject} onPress={x.enabled && !off ? () => router.push({ pathname: "/student/tutor/[subject]", params: { subject: x.subject } }) : undefined}
              style={[s.tile, !(x.enabled && !off) && s.locked]} testID={`tutor-subject-${x.subject}`}>
              <View style={[s.icon, { backgroundColor: x.enabled ? b.soft : C.surfaceTertiary }]}>
                <Feather name={x.enabled ? "zap" : "lock"} size={20} color={x.enabled ? b.ink : C.muted} />
              </View>
              <Text style={s.name}>{x.subject}</Text>
              <Text style={k.small}>{x.enabled ? "Tap to start" : "Not enabled yet"}</Text>
            </Card>
          ))}
        </View>
      )}
      <Text style={[k.small, { textAlign: "center" }]}>AI answers can be wrong. Check important facts with your teacher.</Text>
    </TabScreen>
  );
}

const s = StyleSheet.create({
  off: { flexDirection: "row", gap: 10, alignItems: "center", padding: 14, borderRadius: 16, backgroundColor: C.warningSoft },
  offText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 14, color: "#7C3E06" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  tile: { width: "47%", flexGrow: 1, gap: 4, minHeight: 120 },
  locked: { opacity: 0.6, backgroundColor: C.surfaceTertiary },
  icon: { width: 42, height: 42, borderRadius: 14, alignItems: "center", justifyContent: "center", marginBottom: 6 },
  name: { fontFamily: fonts.heading, fontSize: 17, color: C.onSurface },
});
