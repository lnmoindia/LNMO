// School + session state: remembered school (code + public branding), the signed-in user,
// and the school brand (/me/branding) used to theme the whole app.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, authEvents, clearTokens, loadTokens, saveTokens, ApiError } from "@/src/lib/api";
import { closeChat } from "@/src/lib/chat";
import { queryClient } from "@/src/query-client";
import { storage } from "@/src/utils/storage";
import { makeBrand, type Brand } from "./brand";
import { unregisterPush } from "@/src/push/push";

export type School = { code: string; name: string; logo_url?: string; tagline?: string; background_url?: string };
type Ctx = {
  ready: boolean;
  school: School | null;
  user: any | null;
  brand: Brand;
  resolveSchool: (code: string) => Promise<School>;
  setSchool: (s: School | null) => Promise<void>;
  login: (identifier: string, password: string) => Promise<any>;
  acceptSession: (data: any) => Promise<any>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<any>;
};
const SCHOOL_KEY = "lnmo.school";
const BRAND_KEY = "lnmo.brand";
const AuthCtx = createContext<Ctx | null>(null);

// Phone keyboards can add zero-width chars, trailing spaces, or a space after "." in emails.
export const cleanIdentifier = (v: string) => {
  const s = v.replace(/[\u200B-\u200D\u2060\uFEFF]/g, "").trim();
  return s.includes("@") ? s.replace(/\s+/g, "") : s;
};
// Passwords are sent as typed — only trailing newlines (from paste/autofill) are removed.
export const cleanPassword = (v: string) => v.replace(/[\r\n]+$/, "");

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [school, setSchoolState] = useState<School | null>(null);
  const [user, setUser] = useState<any | null>(null);
  const [brandRaw, setBrandRaw] = useState<any>(null);
  const schoolRef = useRef<School | null>(null);

  const loadBrand = useCallback(() => {
    api.get("/me/branding").then((b) => { setBrandRaw(b); storage.setItem(BRAND_KEY, JSON.stringify(b || {})); })
      .catch(() => setBrandRaw((cur: any) => cur || {}));
  }, []);

  const refreshMe = useCallback(async () => {
    const me = await api.get("/auth/me");
    setUser(me);
    return me;
  }, []);

  useEffect(() => {
    (async () => {
      const raw = (await storage.getItem(SCHOOL_KEY, null)) as string | null;
      if (raw) { try { schoolRef.current = JSON.parse(raw); setSchoolState(schoolRef.current); } catch { /* ignore */ } }
      const rawBrand = (await storage.getItem(BRAND_KEY, null)) as string | null;
      if (rawBrand) { try { setBrandRaw(JSON.parse(rawBrand)); } catch { /* ignore */ } }
      const tok = await loadTokens();
      if (tok) {
        try { await refreshMe(); loadBrand(); } catch (e) {
          if (e instanceof ApiError && (e.status === 401 || e.status === 403)) await clearTokens();
        }
      }
      setReady(true);
    })();
  }, [refreshMe, loadBrand]);

  const resolveSchool = useCallback(async (code: string) => {
    const c = code.trim().toLowerCase();
    try {
      const b = await api.get(`/public/institutions/${encodeURIComponent(c)}/branding`);
      return { code: c, ...b } as School;
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) throw new ApiError(404, null, "School not found — check the school code and try again.");
      throw e;
    }
  }, []);

  const setSchool = useCallback(async (s: School | null) => {
    if (schoolRef.current?.code !== s?.code) { setBrandRaw(null); await storage.removeItem(BRAND_KEY); }
    schoolRef.current = s;
    setSchoolState(s);
    if (s) await storage.setItem(SCHOOL_KEY, JSON.stringify(s));
    else await storage.removeItem(SCHOOL_KEY);
  }, []);

  const acceptSession = useCallback(async (data: any) => {
    await saveTokens(data?.access_token, data?.refresh_token);
    const { access_token, refresh_token, token_type, ...u } = data || {};
    setUser(u);
    loadBrand();
    return u;
  }, [loadBrand]);

  const login = useCallback(async (identifier: string, password: string) => {
    const data = await api.post("/auth/login", { email: cleanIdentifier(identifier), password: cleanPassword(password), ...(school?.code ? { slug: school.code } : {}) });
    if (!data?.access_token) throw new ApiError(500, null, "The server didn't return a session — please update the app.");
    return acceptSession(data);
  }, [school, acceptSession]);

  const logout = useCallback(async () => {
    await unregisterPush(); // while the session is still valid
    try { await api.post("/auth/logout"); } catch { /* ignore */ }
    closeChat();
    await clearTokens();
    queryClient.clear();
    setUser(null);
  }, []);

  useEffect(() => {
    authEvents.onUnauthorized = () => { clearTokens(); queryClient.clear(); setUser(null); };
    authEvents.onPasswordChange = () => setUser((u: any) => (u ? { ...u, must_change_password: true } : u));
  }, []);

  const brand = useMemo(() => makeBrand(brandRaw, school), [brandRaw, school]);
  const value = { ready, school, user, brand, resolveSchool, setSchool, login, acceptSession, logout, refreshMe };
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const c = useContext(AuthCtx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
export const useBrand = () => useAuth().brand;
