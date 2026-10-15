import { useEffect } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { Stack, router, useSegments } from "expo-router";
import { LogBox } from "react-native";
import { StatusBar } from "expo-status-bar";
import * as SplashScreen from "expo-splash-screen";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { useFonts, Outfit_600SemiBold, Outfit_700Bold } from "@expo-google-fonts/outfit";
import { Figtree_400Regular, Figtree_500Medium, Figtree_600SemiBold, Figtree_700Bold } from "@expo-google-fonts/figtree";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { AuthProvider, useAuth } from "@/src/state/auth";
import { ChildProvider } from "@/src/state/child";
import { ToastProvider } from "@/src/state/toast";
import { PushManager } from "@/src/push/PushManager";
import { OfflineSync } from "@/src/offline/OfflineSync";
import { UploadProgress } from "@/src/ui/UploadProgress";

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync().catch(() => {});

const PUBLIC = new Set(["", "school", "login", "setup"]);

// Keeps routing consistent with the session: signed out → login; forced password change → change-password.
function SessionGuard() {
  const { ready, user, school } = useAuth();
  const segs = useSegments() as string[];
  useEffect(() => {
    if (!ready) return;
    const first = segs[0] || "";
    if (!user && !PUBLIC.has(first)) router.replace(school ? "/login" : "/school");
    else if (user?.must_change_password && first !== "change-password") router.replace("/change-password");
  }, [ready, user, school, segs]);
  return null;
}

export default function RootLayout() {
  const [loaded] = useFonts({ Outfit_600SemiBold, Outfit_700Bold, Figtree_400Regular, Figtree_500Medium, Figtree_600SemiBold, Figtree_700Bold });
  useEffect(() => { if (loaded) SplashScreen.hideAsync().catch(() => {}); }, [loaded]);
  if (!loaded) return null;
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <KeyboardProvider>
          <AuthProvider>
            <ChildProvider>
              <ToastProvider>
                <StatusBar style="dark" />
                <SessionGuard />
                <PushManager />
                <OfflineSync />
                <Stack screenOptions={{ headerShown: false, animation: "slide_from_right", contentStyle: { backgroundColor: "#F5F6F8" } }}>
                  <Stack.Screen name="index" options={{ animation: "fade" }} />
                  <Stack.Screen name="(parent)" options={{ animation: "fade" }} />
                </Stack>
                <UploadProgress />
              </ToastProvider>
            </ChildProvider>
          </AuthProvider>
        </KeyboardProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
