// Mounted once inside the providers: registers the device after login, re-registers on token change / app start,
// routes notification taps (foreground, background and cold start), shows the pre-prompt once, keeps the badge fresh.
// Renders nothing and does nothing where notifications aren't supported (web, Expo Go on Android).
import { useCallback, useEffect, useRef } from "react";
import { AppState } from "react-native";
import { router, useSegments } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/src/state/auth";
import { useChild } from "@/src/state/child";
import { useToast } from "@/src/state/toast";
import { storage } from "@/src/utils/storage";
import { getNotifications } from "./notifications";
import { ASKED_KEY, isActiveThread, permission, registerForPush, routeFor, setupHandler, syncBadge } from "./push";

const PRE_LOGIN = new Set(["", "school", "login", "setup", "change-password", "notify-permission"]);

export function PushManager() {
  return getNotifications() ? <NativePushManager /> : null;
}

function NativePushManager() {
  const N = getNotifications();
  const { ready, user } = useAuth();
  const { setChild } = useChild();
  const toast = useToast();
  const qc = useQueryClient();
  const segs = useSegments() as string[];
  const inApp = ready && Boolean(user) && !user?.must_change_password && !PRE_LOGIN.has(segs[0] || "");
  const handled = useRef<string>("");

  useEffect(() => { setupHandler(); }, []);

  // Register (or show the friendly pre-prompt once) after login; repeat on app start.
  useEffect(() => {
    if (!inApp) return;
    (async () => {
      const p = await permission();
      if (p === "granted") registerForPush();
      else if (p === "undetermined" && !(await storage.getItem(ASKED_KEY, ""))) router.push("/notify-permission");
      syncBadge();
    })();
  }, [inApp, user?.id]);

  const openResponse = useCallback((resp: any) => {
    if (!resp || !user || resp.actionIdentifier !== N.DEFAULT_ACTION_IDENTIFIER) return;
    const id = resp.notification?.request?.identifier;
    if (!id || handled.current === id) return;
    handled.current = id;
    const d: any = resp.notification.request.content?.data || {};
    if (user.role === "parent" && d.student_id) setChild(d.student_id);
    const to = routeFor(user.role, d);
    if (to) setTimeout(() => router.push(to as any), 50);
    N.clearLastNotificationResponseAsync?.()?.catch?.(() => {});
  }, [N, user, setChild]);

  // Listeners: token rotation, foreground receipt, taps (background) + the tap that opened the app (killed state).
  useEffect(() => {
    if (!inApp) return undefined;
    const subs: { remove: () => void }[] = [];
    try {
      subs.push(N.addPushTokenListener(() => { registerForPush(); }));
      subs.push(N.addNotificationReceivedListener((n: any) => {
        const d: any = n?.request?.content?.data || {};
        if (d.category === "messages") { qc.invalidateQueries({ queryKey: ["threads"] }); qc.invalidateQueries({ queryKey: ["unread"] }); }
        if (isActiveThread(d)) toast(n.request.content.title || "New message");
        syncBadge();
      }));
      subs.push(N.addNotificationResponseReceivedListener(openResponse));
      N.getLastNotificationResponseAsync?.().then(openResponse).catch(() => {});
    } catch (e: any) { console.log(`[push] listeners not attached: ${e?.message}`); }
    subs.push(AppState.addEventListener("change", (s) => { if (s === "active") syncBadge(); }));
    return () => subs.forEach((s) => s?.remove?.());
  }, [N, inApp, qc, toast, openResponse]);

  return null;
}
