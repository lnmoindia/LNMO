// One class register for a principal (edit allowed by the server unless finalized — same rule as the web).
import { useLocalSearchParams } from "expo-router";
import { usePSections } from "@/src/principal/hooks";
import { StackScreen } from "@/src/ui/Screen";
import { AttendanceRegister } from "@/src/ui/AttendanceRegister";

export default function PrincipalRegister() {
  const { c, s } = useLocalSearchParams<{ c: string; s: string }>();
  const sec = usePSections();
  return (
    <StackScreen title="Class register" testID="principal-register-screen">
      <AttendanceRegister classes={sec.data || []} initial={c && s ? [c, s] : undefined} />
    </StackScreen>
  );
}
