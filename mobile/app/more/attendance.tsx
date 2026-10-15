import { useChild } from "@/src/state/child";
import { useAttendance } from "@/src/lib/queries";
import { AttendanceView } from "@/src/ui/AttendanceView";

export default function Attendance() {
  const { childId } = useChild();
  return <AttendanceView useData={(month) => useAttendance(childId, month)} testID="attendance-screen" />;
}
