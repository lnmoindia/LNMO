import { useChild } from "@/src/state/child";
import { useTimetable } from "@/src/lib/queries";
import { TimetableView } from "@/src/ui/TimetableView";

export default function Timetable() {
  const { childId } = useChild();
  const tt = useTimetable(childId);
  return <TimetableView tt={tt} ready={Boolean(childId)} testID="timetable-screen" />;
}
