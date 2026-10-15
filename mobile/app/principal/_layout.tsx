import { Redirect, Stack } from "expo-router";
import { useAuth } from "@/src/state/auth";

// Principal = a teacher with an active principal assignment (user.is_principal from /auth/me).
export default function PrincipalLayout() {
  const { ready, user } = useAuth();
  if (!ready) return null;
  if (!user || user.role !== "teacher" || !user.is_principal) return <Redirect href="/" />;
  return <Stack screenOptions={{ headerShown: false, animation: "slide_from_right", contentStyle: { backgroundColor: "#F5F6F8" } }} />;
}
