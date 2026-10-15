// A teacher's week timetable (principal → Teachers → teacher).
import { useLocalSearchParams } from "expo-router";
import { useTeacherTT } from "@/src/lib/queries";
import { TimetableView } from "@/src/ui/TimetableView";

export default function PTeacherTimetable() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const q = useTeacherTT(id);
  const data = q.data && { ...q.data, today_changes: null, entries: (q.data.entries || []).map((e: any) => ({ ...e, teacher_name: `${e.class_name} ${e.section || ""}`.trim() })) };
  return <TimetableView tt={{ ...q, data }} testID="principal-teacher-timetable" stack />;
}
