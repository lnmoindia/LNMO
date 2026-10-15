// Principal ⇄ Teacher view for principals who also teach. Remembered per user; default = Principal view.
import { router } from "expo-router";
import { storage } from "@/src/utils/storage";

export type AppView = "principal" | "teacher";
const key = (uid: string) => `lnmo.view.${uid}`;
const mem: Record<string, AppView> = {};

export async function loadView(uid: string): Promise<AppView> {
  const v = await storage.getItem(key(uid), null);
  mem[uid] = v === "teacher" ? "teacher" : "principal";
  return mem[uid];
}
export const currentView = (u: any): AppView | null => (u?.role === "teacher" && u?.is_principal ? mem[u.id] || "principal" : null);
export const viewHome = (v: AppView) => (v === "principal" ? "/principal/today" : "/teacher/today");

// Resets navigation to the target app's first tab (no sign-out); nothing of the other view stays underneath,
// so the Android back button can't lead back into it.
export async function switchView(uid: string, v: AppView) {
  mem[uid] = v;
  await storage.setItem(key(uid), v);
  if (router.canDismiss()) router.dismissAll();
  router.replace(viewHome(v));
}

// Home route for the signed-in user (used by back buttons when there's no history).
export function homeFor(u: any) {
  if (u?.role === "student") return "/student/today";
  if (u?.role === "teacher") return viewHome(currentView(u) || "teacher");
  return "/home";
}
