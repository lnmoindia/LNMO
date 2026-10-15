// One QueryClient for the whole app; the provider in app/_layout.tsx uses this instance.
// Refetch when the app returns to the foreground and when the network comes back.
import { AppState, Platform } from "react-native";
import NetInfo from "@react-native-community/netinfo";
import { QueryClient, focusManager, onlineManager } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30000 } },
});

if (Platform.OS !== "web") {
  AppState.addEventListener("change", (s) => focusManager.setFocused(s === "active"));
  onlineManager.setEventListener((setOnline) => NetInfo.addEventListener((st) => setOnline(st.isConnected !== false)));
}
