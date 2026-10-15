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

// Dev-only "simulate offline" switch (More → Offline sync): every request fails like a dropped connection.
export const netSim = { offline: false };
const SIM_KEY = "lnmo.dev.simOffline";
export const simReady: Promise<void> = __DEV__ ? storage.getItem(SIM_KEY, false).then((v) => { netSim.offline = Boolean(v); }) : Promise.resolve();
export async function setNetSim(v: boolean) { netSim.offline = v; await storage.setItem(SIM_KEY, v); }

// Last NetInfo verdict (set by src/offline/net.ts) — "offline" wording only when the device really is offline.
export const netState = { online: true };
const unreachable = () => (netState.online
  ? "Couldn't reach the school server — please try again in a moment."
  : "You're offline or the school server can't be reached. Check your connection and try again.");

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

type Opts = { body?: any; form?: FormData; params?: Record<string, any>; raw?: boolean; headers?: Record<string, string> };

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
  const headers: Record<string, string> = { "X-Client": "mobile", Accept: "application/json", ...authHeaders(), ...(o.headers || {}) };
  let body: any;
  if (o.form) body = o.form;
  else if (o.body !== undefined) { body = JSON.stringify(o.body); headers["Content-Type"] = "application/json"; }
  return fetch(`${API}${path}${qs}`, { method, headers, body });
}

export async function request(method: string, path: string, o: Opts = {}) {
  let res: Response;
  await simReady;
  try {
    if (netSim.offline) throw new Error("simulated offline");
    res = await send(method, path, o);
    if (res.status === 401 && !path.startsWith("/auth/") && (await tryRefresh())) res = await send(method, path, o);
  } catch (e: any) {
    console.warn(`[api] ${method} ${path} failed: ${e?.message || e} (online=${netState.online})`);
    throw new ApiError(0, { code: "NETWORK" }, unreachable());
  }
  if (!res.ok) {
    let body: any = null;
    try { body = await res.json(); } catch { /* not json */ }
    throw failure(res.status, body, method, path);
  }
  if (o.raw) return res;
  if (res.status === 204) return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

// Error → friendly message. 413/503/5xx have fixed wording; other errors keep the server's detail.
function failure(status: number, body: any, method: string, path: string) {
  const detail = body?.detail;
  if (status === 403 && detail?.code === "PASSWORD_CHANGE_REQUIRED") authEvents.onPasswordChange?.();
  if (status === 401 && !path.startsWith("/auth/login") && access) authEvents.onUnauthorized?.();
  let msg = detailText(detail) || `Request failed (${status})`;
  if (status === 413) {
    const mb = body?.max_mb || Number((detailText(detail).match(/(\d+)\s*MB/i) || [])[1]) || 25;
    msg = `File too large (max ${mb} MB)`;
  } else if (status === 503) msg = path.startsWith("/scan") ? "Scanner temporarily unavailable — try again shortly" : "Service temporarily unavailable — try again shortly";
  else if (status >= 500) msg = "Server error, try again";
  if (status >= 500 || status === 413) console.warn(`[api] ${method} ${path} → ${status}`, body);
  return new ApiError(status, body?.code ? { ...(typeof detail === "object" ? detail : {}), code: body.code, max_mb: body.max_mb } : detail, msg);
}

// ---- Uploads: XHR (progress + timeout) with the Bearer header; never set multipart Content-Type by hand.
type UploadState = { pct: number; label: string } | null;
let upload: UploadState = null;
const upSubs = new Set<() => void>();
const setUpload = (u: UploadState) => { upload = u; upSubs.forEach((f) => f()); };
export const uploadStore = { get: () => upload, subscribe: (f: () => void) => { upSubs.add(f); return () => { upSubs.delete(f); }; } };
export const UPLOAD_TIMEOUT_MS = 90000;

function xhrPost(path: string, form: FormData, onProgress: (p: number) => void) {
  return new Promise<{ status: number; text: string }>((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", `${API}${path}`);
    const h: Record<string, string> = { "X-Client": "mobile", Accept: "application/json", ...authHeaders() };
    Object.entries(h).forEach(([k, v]) => x.setRequestHeader(k, v));
    x.timeout = UPLOAD_TIMEOUT_MS;
    x.onload = () => resolve({ status: x.status, text: x.responseText || "" });
    x.onerror = () => reject(Object.assign(new Error("network error"), { kind: "network" }));
    x.ontimeout = () => reject(Object.assign(new Error("timeout"), { kind: "timeout" }));
    if (x.upload) x.upload.onprogress = (e: any) => { if (e.lengthComputable && e.total) onProgress(e.loaded / e.total); };
    x.send(form as any);
  });
}

export async function uploadForm(path: string, form: FormData, label = "Uploading") {
  await simReady;
  if (netSim.offline) throw new ApiError(0, { code: "NETWORK" }, unreachable());
  const t0 = Date.now();
  setUpload({ pct: 0, label });
  try {
    let res: { status: number; text: string } | null = null;
    for (let attempt = 0; attempt < 2 && !res; attempt++) {
      try {
        res = await xhrPost(path, form, (p) => setUpload({ pct: p, label }));
        if (res.status === 401 && (await tryRefresh())) res = await xhrPost(path, form, (p) => setUpload({ pct: p, label }));
      } catch (e: any) {
        console.warn(`[upload] POST ${path} attempt ${attempt + 1}: ${e?.kind || e?.message} after ${Date.now() - t0} ms (online=${netState.online})`);
        if (e?.kind === "timeout") throw new ApiError(0, { code: "TIMEOUT" }, "Upload is taking too long — check your connection");
        if (attempt === 1 || !netState.online) throw new ApiError(0, { code: "NETWORK" }, unreachable());
        await new Promise((r) => setTimeout(r, 1500)); // one retry on a dropped connection
      }
    }
    let body: any = null;
    try { body = res!.text ? JSON.parse(res!.text) : null; } catch { /* not json */ }
    if (res!.status < 200 || res!.status >= 300) throw failure(res!.status, body, "POST", path);
    return body;
  } finally { setUpload(null); }
}

export const api = {
  get: (p: string, params?: Record<string, any>) => request("GET", p, { params }),
  post: (p: string, body?: any, headers?: Record<string, string>) => request("POST", p, { body: body ?? {}, headers }),
  put: (p: string, body?: any) => request("PUT", p, { body: body ?? {} }),
  postForm: (p: string, form: FormData, label?: string) => uploadForm(p, form, label),
  del: (p: string) => request("DELETE", p),
};
