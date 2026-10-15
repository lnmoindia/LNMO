import { useMyAttendance } from "@/src/lib/queries";
import { AttendanceView } from "@/src/ui/AttendanceView";

export default function StudentAttendance() {
  return <AttendanceView useData={useMyAttendance} testID="student-attendance-screen" />;
}
