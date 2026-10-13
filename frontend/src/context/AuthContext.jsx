import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "../lib/api";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null); // null=checking, false=guest, object=authed

  const refresh = useCallback(
    () => api.get("/auth/me").then((r) => setUser(r.data)).catch(() => setUser(false)),
    []
  );

  useEffect(() => { refresh(); }, [refresh]);

  // Re-validate identity when the server rejects a request. On 401 the session is gone; on 403
  // (e.g. a principal was revoked mid-session) we silently refresh /auth/me so the UI (nav,
  // excluded pages) downgrades to plain-teacher without a crash.
  useEffect(() => {
    const id = api.interceptors.response.use(
      (r) => r,
      (err) => {
        const code = err?.response?.status;
        const url = err?.config?.url || "";
        if (code === 401 && !url.includes("/auth/")) setUser(false);
        else if (code === 403) { api.get("/auth/me").then((r) => setUser(r.data)).catch(() => {}); }
        return Promise.reject(err);
      }
    );
    return () => api.interceptors.response.eject(id);
  }, []);

  const login = useCallback(async (email, password, context = {}) => {
    const { data } = await api.post("/auth/login", { email, password, ...context });
    setUser(data);
    return data;
  }, []);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout"); } catch (e) { /* noop */ }
    setUser(false);
  }, []);

  return <AuthContext.Provider value={{ user, login, logout, refresh }}>{children}</AuthContext.Provider>;
};

export const useAuth = () => useContext(AuthContext);
