import { useMe } from "@/src/lib/queries";
import { MyPhotoCard } from "@/src/ui/MyPhoto";
import { StackScreen } from "@/src/ui/Screen";
import { Card, ErrorState, Field, SkeletonList } from "@/src/ui/kit";
import { fmtDate, fullName } from "@/src/lib/format";

export default function StudentProfile() {
  const q = useMe();
  const s = q.data?.student;
  const leader = q.data?.leader_role === "class_leader" ? "Class Leader" : q.data?.leader_role === "second_leader" ? "Second Leader" : "";
  return (
    <StackScreen title="Profile" testID="student-profile-screen">
      <MyPhotoCard />
      {q.isLoading ? <SkeletonList n={2} height={160} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : (
        <Card testID="student-profile-card">
          <Field label="Full name" value={fullName(s)} testID="student-profile-name" />
          <Field label="Admission no." value={s.admission_no} testID="student-profile-admission" />
          <Field label="Class & section" value={`${s.class_name || "—"}${s.section ? ` · ${s.section}` : ""}`} />
          <Field label="Academic year" value={s.academic_year} />
          <Field label="Date of birth" value={s.date_of_birth || s.dob ? fmtDate(s.date_of_birth || s.dob) : ""} />
          <Field label="Gender" value={s.gender && s.gender[0].toUpperCase() + s.gender.slice(1)} />
          <Field label="Guardian" value={s.guardian_name} />
          <Field label="Guardian phone" value={s.guardian_phone} />
          {leader ? <Field label="Leadership" value={leader} /> : null}
        </Card>
      )}
    </StackScreen>
  );
}
