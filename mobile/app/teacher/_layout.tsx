import { Redirect, Stack } from "expo-router";
import { useAuth } from "@/src/state/auth";

export default function TeacherLayout() {
  const { ready, user } = useAuth();
  if (!ready) return null;
  if (!user) return <Redirect href="/" />;
  if (user.role !== "teacher") return <Redirect href="/" />;
  return <Stack screenOptions={{ headerShown: false, animation: "slide_from_right", contentStyle: { backgroundColor: "#F5F6F8" } }} />;
}
