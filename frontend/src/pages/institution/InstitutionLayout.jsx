import { useCallback, useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import api from "../../lib/api";
import AppShell from "../../components/layout/AppShell";
import { institutionNav, buildPrincipalNav } from "../../navigation";
import { useAuth } from "../../context/AuthContext";
import { Button } from "../../components/ui/button";

const Loader = () => (
  <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-[#0B0F17]">
    <div className="h-8 w-8 rounded-lg bg-indigo-600 animate-pulse" />
  </div>
);

/** Gates the institution console: admins must finish setup first; principals (elevated teachers)
 *  get the merged principal console with no setup gate. */
export default function InstitutionLayout() {
  const location = useLocation();
  const { user } = useAuth();
  const isAdmin = user?.role === "institution_admin";
  const isPrincipal = Boolean(user?.is_principal);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(false);

  const fetchStatus = useCallback(() => {
    setError(false);
    setStatus(null);
    return api.get("/institution/setup-status")
      .then((r) => setStatus(r.data))
      .catch(() => setError(true));
  }, []);

  useEffect(() => { if (isAdmin) fetchStatus(); }, [fetchStatus, location.pathname, isAdmin]);

  // Principals share the /app/* pages but with the merged nav and no setup wizard gate.
  if (isPrincipal) {
    return <AppShell nav={buildPrincipalNav(user)} consoleLabel="Principal Console" />;
  }
  if (!isAdmin) return <Navigate to="/access-denied" replace />;

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-slate-50 dark:bg-[#0B0F17] text-center px-6" data-testid="setup-status-error">
        <AlertTriangle size={28} className="text-amber-500" />
        <div>
          <p className="font-medium text-slate-900 dark:text-slate-100">Couldn't load your console</p>
          <p className="text-sm text-slate-500 mt-1">There was a problem reaching the server.</p>
        </div>
        <Button onClick={fetchStatus} data-testid="setup-status-retry" className="bg-indigo-700 hover:bg-indigo-800 text-white">Retry</Button>
      </div>
    );
  }

  if (status === null) return <Loader />;

  const allowed = location.pathname.startsWith("/app/settings");
  if (!status.setup_complete && !allowed) return <Navigate to="/app/setup" replace />;

  return <AppShell nav={institutionNav} consoleLabel="Institution Console" />;
}
