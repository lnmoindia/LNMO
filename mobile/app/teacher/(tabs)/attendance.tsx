// Teacher Attendance tab: my homerooms + teaching sections → the shared register.
import { useMemo } from "react";
import { useMyClass, useTeachingOptions } from "@/src/lib/queries";
import { TabScreen } from "@/src/ui/Screen";
import { AttendanceRegister } from "@/src/ui/AttendanceRegister";
import { teacherClasses } from "@/src/offline/prefetch";

export default function TeacherAttendance() {
  const homes = useMyClass();
  const opts = useTeachingOptions();
  const classes = useMemo(() => teacherClasses(homes.data, opts.data), [homes.data, opts.data]);
  return (
    <TabScreen testID="teacher-attendance-screen" title="Attendance" showSwitcher={false}>
      <AttendanceRegister classes={classes} />
    </TabScreen>
  );
}
