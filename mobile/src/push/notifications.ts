// The ONLY place that touches expo-notifications / expo-device. Both are loaded lazily with require() so that
// nothing evaluates their native modules at import time (Expo Go on Android has no ExpoTopicSubscriptionModule etc.).
//  • web                → stub (null)
//  • Expo Go on Android → stub, require() is never called
//  • Expo Go on iOS     → try the real module, stub on any error
//  • dev / preview / production builds → the real module
import { Platform } from "react-native";
import Constants, { ExecutionEnvironment } from "expo-constants";

export const isWeb = Platform.OS === "web";
export const isExpoGo = Constants.executionEnvironment === ExecutionEnvironment.StoreClient || (Constants as any).appOwnership === "expo";
export const isExpoGoAndroid = isExpoGo && Platform.OS === "android";

let notifications: any;   // undefined = not tried yet, null = unavailable
let device: any;

export function getNotifications(): any | null {
  if (notifications !== undefined) return notifications;
  notifications = null;
  if (isWeb || isExpoGoAndroid) return null;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const m = require("expo-notifications");
    if (m && typeof m.getPermissionsAsync === "function") notifications = m;
  } catch (e: any) {
    console.log(`[push] expo-notifications unavailable here: ${e?.message || e}`);
  }
  return notifications;
}

export function getDevice(): any | null {
  if (device !== undefined) return device;
  device = null;
  if (isWeb) return null;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    device = require("expo-device");
  } catch (e: any) {
    console.log(`[push] expo-device unavailable: ${e?.message || e}`);
  }
  return device;
}

/** True when this runtime can show / receive notifications at all. */
export const notificationsSupported = () => Boolean(getNotifications());
