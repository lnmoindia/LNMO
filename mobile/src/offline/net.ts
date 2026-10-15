// Connection state = NetInfo (works in Expo Go + web) AND the dev "simulate offline" switch.
import { useSyncExternalStore } from "react";
import NetInfo, { type NetInfoState } from "@react-native-community/netinfo";
import { netSim, netState, setNetSim, simReady } from "@/src/lib/api";

let real = true;
const subs = new Set<() => void>();
const emit = () => subs.forEach((f) => f());
const fromState = (s: NetInfoState) => !(s.isConnected === false || s.isInternetReachable === false);

NetInfo.addEventListener((s) => { const on = fromState(s); netState.online = on; if (on !== real) { real = on; emit(); } });
NetInfo.fetch().then((s) => { real = fromState(s); netState.online = real; emit(); }).catch(() => {});
simReady.then(emit); // the dev switch is restored from storage by api.ts

export const isOnlineNow = () => real && !netSim.offline;
const subscribe = (f: () => void) => { subs.add(f); return () => { subs.delete(f); }; };
export const useOnline = () => useSyncExternalStore(subscribe, isOnlineNow, isOnlineNow);
export const useSimOffline = () => useSyncExternalStore(subscribe, () => netSim.offline, () => netSim.offline);
export async function setSimOffline(v: boolean) { await setNetSim(v); emit(); }
