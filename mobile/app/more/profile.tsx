import { View } from "react-native";
import { useChild } from "@/src/state/child";
import { useSnap } from "@/src/lib/queries";
import { StackScreen } from "@/src/ui/Screen";
import { Card, ErrorState, Field, SkeletonList } from "@/src/ui/kit";
import { Avatar } from "@/src/ui/brandbits";
import { fmtDate, fullName } from "@/src/lib/format";

export default function ChildProfile() {
  const { childId } = useChild();
  const q = useSnap(childId);
  const s = q.data?.student;
  const leader = q.data?.leader_role === "class_leader" ? "Class Leader" : q.data?.leader_role === "second_leader" ? "Second Leader" : "";
  return (
    <StackScreen title="Child profile" testID="child-profile-screen">
      {q.isLoading ? <SkeletonList n={2} height={160} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : (
        <Card testID="child-profile-card">
          <View style={{ alignItems: "flex-start", marginBottom: 8 }}><Avatar name={s.first_name} size={64} /></View>
          <Field label="Full name" value={fullName(s)} testID="profile-name" />
          <Field label="Admission no." value={s.admission_no} testID="profile-admission" />
          <Field label="Class & section" value={`${s.class_name || "—"}${s.section ? ` · ${s.section}` : ""}`} testID="profile-class" />
          <Field label="Academic year" value={s.academic_year} />
          <Field label="Date of birth" value={s.date_of_birth || s.dob ? fmtDate(s.date_of_birth || s.dob) : ""} />
          <Field label="Gender" value={s.gender && s.gender[0].toUpperCase() + s.gender.slice(1)} />
          {leader ? <Field label="Leadership" value={leader} /> : null}
        </Card>
      )}
    </StackScreen>
  );
}
