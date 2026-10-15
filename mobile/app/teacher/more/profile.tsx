// Teacher profile — mirrors web TeacherProfile (GET /teacher/profile → {user, institution_name, assignments, subjects, total_students, homerooms}).
// Phone OTP verification, personal email and digital signature stay on the web.
import { Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/lib/api";
import { MyPhotoCard } from "@/src/ui/MyPhoto";
import { StackScreen } from "@/src/ui/Screen";
import { Card, Divider, Empty, ErrorState, SectionTitle, SkeletonList, k } from "@/src/ui/kit";
import { fmtDate } from "@/src/lib/format";

const Stat = ({ label, value, testID }: { label: string; value: any; testID: string }) => (
  <Card style={{ flex: 1, gap: 4 }} testID={testID}><Text style={k.small}>{label}</Text><Text style={k.h2}>{value}</Text></Card>
);
const Row = ({ left, right }: { left: string; right: string }) => (
  <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8, paddingHorizontal: 16, paddingVertical: 14 }}>
    <Text style={[k.label, { flex: 1 }]}>{left}</Text><Text style={k.small}>{right}</Text>
  </View>
);

export default function TeacherProfile() {
  const q = useQuery({ queryKey: ["t-profile"], queryFn: () => api.get("/teacher/profile") });
  const d = q.data;
  const u = d?.user || {};
  return (
    <StackScreen title="Profile" testID="teacher-profile-screen">
      {q.isLoading ? <SkeletonList n={3} height={120} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : (
        <>
          <MyPhotoCard />
          <Card style={{ flexDirection: "row", alignItems: "center", gap: 16 }} testID="teacher-profile-card">
            <View style={{ flex: 1, gap: 3 }}>
              <Text style={k.h2} testID="teacher-profile-name">{u.name}</Text>
              <Text style={k.small}>{u.email}</Text>
              <Text style={k.small}>{d.institution_name}{u.created_at ? ` · Joined ${fmtDate(u.created_at, { year: true })}` : ""}</Text>
              {u.phone ? <Text style={k.small}>{u.phone}</Text> : null}
            </View>
          </Card>
          <View style={{ flexDirection: "row", gap: 12 }}>
            <Stat label="Assignments" value={d.assignments?.length ?? 0} testID="teacher-stat-assignments" />
            <Stat label="Students" value={d.total_students ?? 0} testID="teacher-stat-students" />
          </View>
          <Card style={{ gap: 4 }} testID="teacher-stat-subjects"><Text style={k.small}>Subjects</Text><Text style={k.label}>{d.subjects?.length ? d.subjects.join(", ") : "—"}</Text></Card>
          <SectionTitle title="Teaching load" />
          <Card style={{ padding: 0 }} testID="teacher-profile-assignments">
            {!d.assignments?.length ? <Empty icon="book-open" text="No teaching assignments yet." /> : d.assignments.map((a: any, i: number) => (
              <View key={a.id}>{i > 0 && <Divider />}<Row left={a.subject || "General"} right={`${a.class_name}${a.section ? ` · ${a.section}` : " · all sections"}`} /></View>
            ))}
          </Card>
          <SectionTitle title="Class teacher of" />
          <Card style={{ padding: 0 }} testID="teacher-profile-homerooms">
            {!d.homerooms?.length ? <Empty icon="award" text="You are not a class teacher of any section." /> : d.homerooms.map((h: any, i: number) => (
              <View key={h.id}>{i > 0 && <Divider />}<Row left={`${h.class_name} · Section ${h.name}`} right={h.class_leader ? `Leader: ${h.class_leader}` : "No leader set"} /></View>
            ))}
          </Card>
          <Text style={k.small}>Phone verification, personal email and your digital signature are managed on the web.</Text>
        </>
      )}
    </StackScreen>
  );
}
