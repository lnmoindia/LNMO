import { Link, useNavigate } from "react-router-dom";
import { ShieldAlert, Compass, Hourglass, LogOut } from "lucide-react";
import { Button } from "../components/ui/button";
import { useAuth } from "../context/AuthContext";

const Shell = ({ icon: Icon, title, message, children, testId }) => (
  <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 dark:bg-[#0B0F17] px-6 text-center" data-testid={testId}>
    <div className="h-14 w-14 rounded-2xl bg-indigo-50 dark:bg-indigo-500/10 flex items-center justify-center mb-5">
      <Icon size={26} className="text-indigo-600 dark:text-indigo-400" strokeWidth={1.6} />
    </div>
    <h1 className="font-heading text-2xl font-bold text-slate-900 dark:text-slate-50 tracking-tight">{title}</h1>
    <p className="text-sm text-slate-500 dark:text-slate-400 mt-2 max-w-sm">{message}</p>
    <div className="mt-6 flex gap-3">{children}</div>
  </div>
);

export const AccessDeniedPage = () => (
  <Shell icon={ShieldAlert} title="Access denied" message="You don't have permission to view this area. Contact your administrator if you believe this is a mistake." testId="access-denied-page">
    <Button asChild variant="outline" data-testid="access-denied-login-link"><Link to="/login">Back to sign in</Link></Button>
  </Shell>
);

// In-shell (not full screen) — shown when a principal hits an admin-only page directly.
export const NotPermitted = () => (
  <div className="flex flex-col items-center justify-center py-24 text-center" data-testid="not-permitted">
    <div className="h-14 w-14 rounded-2xl bg-amber-50 dark:bg-amber-500/10 flex items-center justify-center mb-5">
      <ShieldAlert size={26} className="text-amber-600 dark:text-amber-400" strokeWidth={1.6} />
    </div>
    <h1 className="font-heading text-2xl font-bold text-slate-900 dark:text-slate-50 tracking-tight">Not permitted</h1>
    <p className="text-sm text-slate-500 dark:text-slate-400 mt-2 max-w-sm">
      This area is restricted to institution administrators. Your principal access does not include it.
    </p>
    <div className="mt-6">
      <Button asChild variant="outline" data-testid="not-permitted-back-link"><Link to="/teacher/dashboard">Back to my dashboard</Link></Button>
    </div>
  </div>
);

export const NotFoundPage = () => (
  <Shell icon={Compass} title="Page not found" message="The page you're looking for doesn't exist or has been moved." testId="not-found-page">
    <Button asChild variant="outline" data-testid="not-found-home-link"><Link to="/">Go home</Link></Button>
  </Shell>
);

export const ComingSoonPage = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <Shell icon={Hourglass} title="Portal coming soon" message={`Hi ${user?.name || "there"} — the ${user?.role || ""} portal is being built. Your administrator console will notify you when it's ready.`} testId="coming-soon-page">
      <Button variant="outline" onClick={async () => { await logout(); navigate("/login"); }} data-testid="coming-soon-logout-btn">
        <LogOut size={14} className="mr-2" /> Sign out
      </Button>
    </Shell>
  );
};
