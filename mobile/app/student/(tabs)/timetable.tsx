import { useMyTimetable } from "@/src/lib/queries";
import { TimetableView } from "@/src/ui/TimetableView";

export default function StudentTimetable() {
  const tt = useMyTimetable();
  return <TimetableView tt={tt} testID="student-timetable-screen" />;
}
