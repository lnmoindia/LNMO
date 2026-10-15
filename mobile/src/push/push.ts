// Push notifications (Phase M3): permission, Expo push token registration, Android channels, badge, tap routing.
// No static import of expo-notifications here — everything goes through the lazy wrapper in ./notifications.
import { Platform } from "react-native";
import Constants from "expo-constants";
import { api } from "@/src/lib/api";
import { storage } from "@/src/utils/storage";
import { getDevice, getNotifications, isExpoGo, isExpoGoAndroid, isWeb, notificationsSupported } from "./notifications";

export { isExpoGo, isExpoGoAndroid, isWeb, notificationsSupported };

const TOKEN_KEY = "lnmo.push.token";
export const ASKED_KEY = "lnmo.push.asked";
export const projectId: string | undefined = (Constants.expoConfig?.extra as any)?.eas?.projectId || (Constants as any).easConfig?.projectId || undefined;
export const UNSUPPORTED_TEXT = isWeb
  ? "Push alerts work in the phone app, not in the web preview."
  : "Push needs the LNMO app build — not available in Expo Go on Android.";

export type PushStatus = { ok: boolean; reason?: "unsupported" | "simulator" | "denied" | "no_project" | "error"; message?: string };
let status: PushStatus = { ok: false };
export const pushStatus = () => status;

// Foreground: no system alert for the chat thread that is open right now (PushManager shows a toast instead).
let activeThread: string | null = null;
export const setActiveThread = (id: string | null) => { activeThread = id; };
export const isActiveThread = (data: any) => Boolean(data?.thread_id && data.thread_id === activeThread);

let handlerSet = false;
export function setupHandler() {
  const N = getNotifications();
  if (!N || handlerSet) return;
  handlerSet = true;
  try {
    N.setNotificationHandler({
      handleNotification: async (n: any) => {
        const here = isActiveThread(n?.request?.content?.data);
        return { shouldShowBanner: !here, shouldShowList: !here, shouldPlaySound: !here, shouldSetBadge: true };
      },
    });
  } catch (e: any) { console.log(`[push] handler not set: ${e?.message}`); }
}

export async function ensureChannels() {
  const N = getNotifications();
  if (!N || Platform.OS !== "android") return;
  const hi = N.AndroidImportance?.HIGH ?? 4;
  await Promise.all([
    N.setNotificationChannelAsync("messages", { name: "Messages", importance: hi, lightColor: "#3F6B8A" }),
    N.setNotificationChannelAsync("fees", { name: "Fees", importance: hi, lightColor: "#3F6B8A" }),
    N.setNotificationChannelAsync("school", { name: "School (notices, homework, timetable)", importance: N.AndroidImportance?.DEFAULT ?? 3 }),
    N.setNotificationChannelAsync("teacher", { name: "Teacher covers", importance: hi, lightColor: "#3F6B8A" }),
  ]).catch(() => {});
}

export type Perm = "granted" | "denied" | "undetermined" | "unavailable";
export async function permission(): Promise<Perm> {
  const N = getNotifications();
  if (!N) return "unavailable";
  try { return (await N.getPermissionsAsync()).status; } catch { return "unavailable"; }
}

export async function askPermission(): Promise<Perm> {
  const N = getNotifications();
  if (!N) return "unavailable";
  try {
    await ensureChannels();
    return (await N.requestPermissionsAsync({ ios: { allowAlert: true, allowBadge: true, allowSound: true } })).status;
  } catch { return "unavailable"; }
}

/** Get the Expo push token and register it with the backend. Never throws. */
export async function registerForPush(): Promise<PushStatus> {
  const done = (s: PushStatus) => { status = s; if (!s.ok) console.log(`[push] registration skipped: ${s.reason}${s.message ? ` — ${s.message}` : ""}`); return s; };
  const N = getNotifications();
  if (!N || isExpoGoAndroid) return done({ ok: false, reason: "unsupported" });
  const D = getDevice();
  if (D && D.isDevice === false) return done({ ok: false, reason: "simulator" });
  if ((await permission()) !== "granted") return done({ ok: false, reason: "denied" });
  if (!projectId) return done({ ok: false, reason: "no_project", message: "set expo.extra.eas.projectId (run `eas init`)" });
  try {
    await ensureChannels();
    const token = (await N.getExpoPushTokenAsync({ projectId })).data;
    await api.post("/push/register", {
      token, platform: Platform.OS, device_name: D?.deviceName || D?.modelName || "", app_version: Constants.expoConfig?.version || "",
    });
    await storage.setItem(TOKEN_KEY, token);
    return done({ ok: true });
  } catch (e: any) {
    return done({ ok: false, reason: "error", message: e?.message });
  }
}

/** Called on sign out, while the session is still valid. Safe everywhere (no native calls when unsupported). */
export async function unregisterPush() {
  const token = (await storage.getItem(TOKEN_KEY, "")) as string;
  if (token) {
    try { await api.post("/push/unregister", { token }); } catch { /* best effort */ }
    await storage.removeItem(TOKEN_KEY);
  }
  status = { ok: false };
  getNotifications()?.setBadgeCountAsync?.(0)?.catch?.(() => {});
}

export async function syncBadge() {
  const N = getNotifications();
  if (!N) return;
  try { const { badge } = await api.get("/push/badge"); await N.setBadgeCountAsync(Number(badge) || 0); } catch { /* ignore */ }
}

/** Deep-link target for a tapped notification, limited to the signed-in role's screens. */
export function routeFor(role: string, data: any): string | null {
  const r = typeof data?.route === "string" ? data.route : "";
  if (!r.startsWith("/")) return null;
  if (role === "student") return r.startsWith("/student") || r.startsWith("/more/") ? r : "/student/today";
  if (role === "teacher") return r.startsWith("/teacher") || r.startsWith("/thread/") || r.startsWith("/more/") ? r : "/teacher/today";
  if (role === "parent") return r.startsWith("/student") || r.startsWith("/teacher") ? "/home" : r;
  return null;
}

/** Local notification — used by Settings to test tap → deep link (only where notifications are supported). */
export async function localTest(route: string) {
  const N = getNotifications();
  if (!N) throw new Error(UNSUPPORTED_TEXT);
  await ensureChannels();
  const type = N.SchedulableTriggerInputTypes?.TIME_INTERVAL ?? "timeInterval";
  await N.scheduleNotificationAsync({
    content: { title: "Test notification", body: "Tap to open the screen this alert links to.", data: { route, type: "local_test" } },
    trigger: Platform.OS === "android" ? { type, seconds: 2, channelId: "school" } : { type, seconds: 2 },
  });
}
