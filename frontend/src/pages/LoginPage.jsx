import { useState, useEffect } from "react";
import { useNavigate, Navigate, useParams } from "react-router-dom";
import { Moon, Sun, GraduationCap, ShieldCheck, Building2 } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import api, { errText } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

export const roleHome = (role) =>
  role === "platform_admin" ? "/platform/dashboard"
    : role === "institution_admin" ? "/app/dashboard"
    : role === "teacher" ? "/teacher/dashboard"
    : role === "parent" ? "/parents"
    : "/portal";

export default function LoginPage({ platform = false }) {
  const { user, login } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [brand, setBrand] = useState(null);
  const params = useParams();

  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    const domain = qs.get("domain");
    const slug = params.slug || qs.get("slug");
    if (slug || domain) {
      api.get("/public/branding", { params: slug ? { slug } : { domain } })
        .then((r) => { if (r.data?.name) setBrand(r.data); }).catch(() => {});
    }
  }, [params.slug]);

  const logoSrc = brand?.has_logo
    ? `${process.env.REACT_APP_BACKEND_URL}/api/public/institution-logo?slug=${encodeURIComponent(brand.slug || "")}&domain=${encodeURIComponent(brand.domain || "")}`
    : brand?.logo_url;

  if (user && user !== false) return <Navigate to={roleHome(user.role)} replace />;

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const qs = new URLSearchParams(window.location.search);
      const slug = params.slug || qs.get("slug");
      const domain = qs.get("domain");
      const u = await login(email, password, { ...(slug ? { slug } : {}), ...(domain ? { domain } : {}) });
      navigate(roleHome(u.role));
    } catch (err) {
      const code = err?.response?.status;
      if (code === 429) setError(errText(err) || "Too many failed attempts — please try again in 15 minutes.");
      else if (code === 403 || code === 423) setError(errText(err) || "This account is locked or inactive. Contact your administrator.");
      else setError(errText(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-slate-50 dark:bg-[#0B0F17]">
      <div className="hidden lg:flex w-[45%] flex-col justify-between bg-slate-950 p-12 relative overflow-hidden">
        <div className="absolute inset-0 opacity-20 bg-[radial-gradient(ellipse_at_top_left,#4338CA_0%,transparent_55%)]" />
        <div className="relative flex items-center gap-3">
          {logoSrc
            ? <img src={logoSrc} alt="logo" className="h-10 w-10 rounded-xl object-cover" data-testid="login-brand-logo" />
            : <div className="h-10 w-10 rounded-xl flex items-center justify-center font-heading font-bold text-white text-lg" style={{ background: brand?.primary_color || "#4f46e5" }}>{(brand?.name || "L")[0]}</div>}
          <span className="font-heading font-bold text-white text-xl tracking-tight">{brand?.name || "LNMO"}</span>
        </div>
        <div className="relative space-y-6">
          <h1 className="font-heading text-4xl font-bold text-white leading-tight tracking-tight">
            One platform to run<br />your entire institution.
          </h1>
          <p className="text-slate-400 text-sm leading-relaxed max-w-md">
            Multi-tenant school ERP — admissions, academics, attendance, assessments and finance, unified under one console.
          </p>
          <div className="flex gap-8 pt-2">
            {[
              { icon: Building2, label: "Multi-tenant" },
              { icon: GraduationCap, label: "Academics-first" },
              { icon: ShieldCheck, label: "Role-secured" },
            ].map((f) => (
              <div key={f.label} className="flex items-center gap-2 text-slate-300 text-sm">
                <f.icon size={16} className="text-indigo-400" /> {f.label}
              </div>
            ))}
          </div>
        </div>
        <p className="relative text-xs text-slate-600">© 2026 LNMO Pvt. Ltd.</p>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="flex justify-end p-4">
          <button onClick={toggle} data-testid="auth-theme-toggle" className="h-9 w-9 rounded-lg flex items-center justify-center text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </div>
        <div className="flex-1 flex items-center justify-center px-6 pb-16">
          <div className="w-full max-w-sm">
            <div className="lg:hidden flex items-center gap-3 mb-8">
              {logoSrc
                ? <img src={logoSrc} alt="logo" className="h-9 w-9 rounded-lg object-cover" />
                : <div className="h-9 w-9 rounded-lg flex items-center justify-center font-heading font-bold text-white" style={{ background: brand?.primary_color || "#4f46e5" }}>{(brand?.name || "L")[0]}</div>}
              <span className="font-heading font-bold text-slate-900 dark:text-white text-lg">{brand?.name || "LNMO"}</span>
            </div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 mb-2">
              {platform ? "Platform Console" : "Sign in"}
            </p>
            <h2 className="font-heading text-2xl font-bold text-slate-900 dark:text-slate-50 tracking-tight">
              {platform ? "Platform administrator access" : "Welcome back"}
            </h2>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 mb-8">
              {platform ? "Restricted area for LNMO platform operators." : "Enter your credentials to access your console."}
            </p>
            <form onSubmit={submit} className="space-y-4" data-testid="login-form">
              <div className="space-y-1.5">
                <Label htmlFor="email">{platform ? "Email" : "Email or mobile number"}</Label>
                <Input id="email" type={platform ? "email" : "text"} autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder={platform ? "you@institution.edu" : "you@institution.edu or 98470 12345"} data-testid="login-email-input" />
                {!platform && <p className="text-[11px] text-slate-400" data-testid="login-phone-hint">Parents can sign in with their registered mobile number.</p>}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <Input id="password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" data-testid="login-password-input" />
              </div>
              {error && <p className="text-sm text-red-600" data-testid="login-error">{error}</p>}
              <Button type="submit" disabled={loading} style={brand?.primary_color ? { backgroundColor: brand.primary_color } : undefined} className="w-full bg-indigo-700 hover:bg-indigo-800 text-white h-10" data-testid="login-submit-btn">
                {loading ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
