// API client for the LNMO backend. Same endpoints as the web app (/api/...),
// but auth is a Bearer token (the web uses an httpOnly cookie). The backend
// returns tokens in the JSON when the request carries `X-Client: mobile`.
import Constants from "expo-constants";
import { storage } from "@/src/utils/storage";

// Backend origin:
//  • dev (Expo Go / Metro, __DEV__ true) → EXPO_PUBLIC_BACKEND_URL from mobile/.env (the preview server)
//  • release build (installed APK)       → app.json extra.productionBackendUrl (the live site);
//    EXPO_PUBLIC_BACKEND_URL only if that's missing.
// A trailing "/" or "/api" is stripped. Every REST, asset/PDF (absUrl) and WebSocket URL builds on BACKEND.
const clean = (u?: string | null) => (u || "").trim().replace(/\/+$/, "").replace(/\/api$/, "");
const APP_JSON_EXTRA = (require("../../app.json")?.expo?.extra || {}) as { productionBackendUrl?: string };
const PROD = clean((Constants.expoConfig?.extra as any)?.productionBackendUrl || APP_JSON_EXTRA.productionBackendUrl);
const DEV_ENV = clean(process.env.EXPO_PUBLIC_BACKEND_URL);
export const resolveBackend = (dev: boolean) => (dev ? DEV_ENV || PROD : PROD || DEV_ENV);
export const BACKEND = resolveBackend(__DEV__);
if (!BACKEND) console.warn("[api] no backend URL configured — API calls will fail");
export const BACKEND_HOST = BACKEND.replace(/^https?:\/\//, "");
export const API = `${BACKEND}/api`;
const ACCESS_KEY = "lnmo.access";
const REFRESH_KEY = "lnmo.refresh";

let access: string | null = null;
let refresh: string | null = null;

export const authEvents: { onUnauthorized?: () => void; onPasswordChange?: () => void } = {};
export const getToken = () => access;
export const absUrl = (u?: string | null) => (u && u.startsWith("/api") ? `${BACKEND}${u}` : u || "");
export const authHeaders = (): Record<string, string> => (access ? { Authorization: `Bearer ${access}` } : {});

export async function loadTokens() {
  access = (await storage.secureGet(ACCESS_KEY, null)) as string | null;
  refresh = (await storage.secureGet(REFRESH_KEY, null)) as string | null;
  return access;
}
export async function saveTokens(a?: string, r?: string) {
  if (a) { access = a; await storage.secureSet(ACCESS_KEY, a); }
  if (r) { refresh = r; await storage.secureSet(REFRESH_KEY, r); }
}
export async function clearTokens() {
  access = null; refresh = null;
  await storage.secureRemove(ACCESS_KEY);
  await storage.secureRemove(REFRESH_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: any;
  constructor(status: number, detail: any, message: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

const detailText = (d: any): string => {
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => (x && typeof x.msg === "string" ? x.msg : JSON.stringify(x))).join(" ");
  if (d && typeof d.msg === "string") return d.msg;
  return "";
};
export const errText = (e: any) => (e instanceof ApiError ? e.message : e?.message || "Something went wrong");

type Opts = { body?: any; form?: FormData; params?: Record<string, any>; raw?: boolean };

async function tryRefresh() {
  if (!refresh) return false;
  try {
    const r = await fetch(`${API}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Client": "mobile" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!r.ok) return false;
    const d = await r.json();
    await saveTokens(d.access_token, d.refresh_token);
    return Boolean(d.access_token);
  } catch {
    return false;
  }
}

async function send(method: string, path: string, o: Opts) {
  const qs = o.params
    ? "?" + Object.entries(o.params).filter(([, v]) => v !== undefined && v !== null)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&")
    : "";
  const headers: Record<string, string> = { "X-Client": "mobile", Accept: "application/json", ...authHeaders() };
  let body: any;
  if (o.form) body = o.form;
  else if (o.body !== undefined) { body = JSON.stringify(o.body); headers["Content-Type"] = "application/json"; }
  return fetch(`${API}${path}${qs}`, { method, headers, body });
}

export async function request(method: string, path: string, o: Opts = {}) {
  let res: Response;
  try {
    res = await send(method, path, o);
    if (res.status === 401 && !path.startsWith("/auth/") && (await tryRefresh())) res = await send(method, path, o);
  } catch {
    throw new ApiError(0, null, "You're offline or the school server can't be reached. Check your connection and try again.");
  }
  if (!res.ok) {
    let detail: any = null;
    try { detail = (await res.json())?.detail; } catch { /* not json */ }
    if (res.status === 403 && detail?.code === "PASSWORD_CHANGE_REQUIRED") authEvents.onPasswordChange?.();
    if (res.status === 401 && !path.startsWith("/auth/login") && access) authEvents.onUnauthorized?.();
    throw new ApiError(res.status, detail, detailText(detail) || `Request failed (${res.status})`);
  }
  if (o.raw) return res;
  if (res.status === 204) return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

export const api = {
  get: (p: string, params?: Record<string, any>) => request("GET", p, { params }),
  post: (p: string, body?: any) => request("POST", p, { body: body ?? {} }),
  put: (p: string, body?: any) => request("PUT", p, { body: body ?? {} }),
  postForm: (p: string, form: FormData) => request("POST", p, { form }),
  del: (p: string) => request("DELETE", p),
};
