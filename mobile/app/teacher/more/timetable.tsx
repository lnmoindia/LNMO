import { useAuth } from "@/src/state/auth";
import { useTeacherTT } from "@/src/lib/queries";
import { TimetableView } from "@/src/ui/TimetableView";

// Teacher week view: reuse the shared timetable, showing the class/section where the student view shows the teacher.
export default function TeacherTimetable() {
  const { user } = useAuth();
  const q = useTeacherTT(user?.id);
  const data = q.data && { ...q.data, today_changes: null, entries: (q.data.entries || []).map((e: any) => ({ ...e, teacher_name: `${e.class_name} ${e.section || ""}`.trim() })) };
  return <TimetableView tt={{ ...q, data }} testID="teacher-timetable-screen" stack />;
}
