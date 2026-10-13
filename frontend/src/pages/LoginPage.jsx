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
  const [school, setSchool] = useState(null);
  const params = useParams();

  useEffect(() => {
    setSchool(null);
    const qs = new URLSearchParams(window.location.search);
    const code = params.slug || qs.get("slug");
    const domain = qs.get("domain");
    if ((!code && !domain) || platform) return;
    (code ? api.get(`/public/institutions/${encodeURIComponent(code)}/branding`)
      : api.get("/public/institutions/branding", { params: { domain } }))
      .then((r) => setSchool(r.data)).catch(() => setSchool(false));
  }, [params.slug, platform]);

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
  const legacyDomain = !params.slug && new URLSearchParams(window.location.search).get("domain");
  if (legacyDomain) return <Navigate to={`/login/${encodeURIComponent(legacyDomain)}`} replace />;

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
      else if (code === 401) setError(`${errText(err)}. Check for typos or extra spaces; after 5 failed tries the account is paused for 15 minutes.`);
      else setError(errText(err));
    } finally {
      setLoading(false);
    }
  };

  const formEl = (
            <form onSubmit={submit} className="space-y-4" data-testid="login-form">
              <div className="space-y-1.5">
                <Label htmlFor="email">{platform ? "Email" : "Email or mobile number"}</Label>
                <Input id="email" type={platform ? "email" : "text"} autoComplete="username" autoCapitalize="none" autoCorrect="off" spellCheck={false} required value={email} onChange={(e) => setEmail(e.target.value)} placeholder={platform ? "you@institution.edu" : "you@institution.edu or 98470 12345"} data-testid="login-email-input" />
                {!platform && <p className="text-[11px] text-slate-400" data-testid="login-phone-hint">Students & staff: use your school email. Parents: email or registered mobile number.</p>}
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
  );
  if (school) return <BrandedLogin school={school} form={formEl} theme={theme} toggle={toggle} />;

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
            {formEl}
          </div>
        </div>
      </div>
    </div>
  );
}

const abs = (u) => (u && u.startsWith("/api") ? `${process.env.REACT_APP_BACKEND_URL}${u}` : u);

function BrandedLogin({ school, form, theme, toggle }) {
  const bg = abs(school.background_url);
  const logo = abs(school.logo_url);
  const Logo = ({ cls }) => (logo
    ? <img src={logo} alt="" className={`${cls} rounded-2xl object-cover bg-white shadow-lg`} data-testid="login-school-logo" />
    : <div className={`${cls} rounded-2xl flex items-center justify-center font-heading font-bold text-white bg-white/20 backdrop-blur`}>{(school.name || "S")[0]}</div>);
  return (
    <div className="min-h-screen relative flex flex-col bg-slate-950" data-testid="branded-login">
      <div className="hidden md:block absolute inset-0">
        <img src={bg} alt="" className="h-full w-full object-cover" data-testid="login-school-bg" />
        <div className="absolute inset-0 bg-gradient-to-r from-slate-950/85 via-slate-950/55 to-slate-950/30" />
      </div>
      <div className="md:hidden relative h-60 overflow-hidden">
        <img src={bg} alt="" className="h-full w-full object-cover" data-testid="login-school-bg-mobile" />
        <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/50 to-slate-950/10" />
        <div className="absolute bottom-4 left-5 right-5 flex items-center gap-3 text-white">
          <Logo cls="h-12 w-12" />
          <div>
            <p className="font-heading text-xl font-bold leading-tight">{school.name}</p>
            {school.tagline && <p className="text-xs text-white/80 mt-0.5">{school.tagline}</p>}
          </div>
        </div>
      </div>
      <button onClick={toggle} data-testid="auth-theme-toggle" className="absolute top-4 right-4 z-10 h-9 w-9 rounded-lg flex items-center justify-center text-white/80 hover:bg-white/10 transition-colors">
        {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
      </button>
      <div className="relative flex-1 flex flex-col md:flex-row md:items-center md:justify-between gap-10 px-5 md:px-14 lg:px-24 py-8 md:py-16 bg-slate-50 dark:bg-[#0B0F17] md:bg-transparent md:dark:bg-transparent">
        <div className="hidden md:block max-w-xl text-white">
          <Logo cls="h-16 w-16 text-2xl" />
          <h1 className="font-heading text-4xl lg:text-5xl font-bold tracking-tight mt-6 leading-tight" data-testid="login-school-name">{school.name}</h1>
          {school.tagline && <p className="text-lg text-white/85 mt-3 max-w-md" data-testid="login-school-tagline">{school.tagline}</p>}
        </div>
        <div className="w-full md:max-w-sm rounded-2xl md:bg-white/95 md:dark:bg-slate-900/90 md:backdrop-blur-xl md:shadow-2xl md:border md:border-white/40 md:dark:border-slate-700 md:p-8">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 mb-2">Sign in</p>
          <h2 className="font-heading text-2xl font-bold text-slate-900 dark:text-slate-50 tracking-tight">Welcome back</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 mb-6">Students, parents and staff of {school.name}.</p>
          {form}
        </div>
      </div>
      <p className="relative pb-4 pt-2 text-center text-[11px] text-slate-400 md:text-white/60 bg-slate-50 dark:bg-[#0B0F17] md:bg-transparent md:dark:bg-transparent" data-testid="login-powered-by">Powered by LNMO</p>
    </div>
  );
}
