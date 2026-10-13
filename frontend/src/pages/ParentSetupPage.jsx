import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ShieldCheck, Loader2, GraduationCap } from "lucide-react";
import api, { errText } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { PasswordInput } from "../components/common/PasswordInput";

const Shell = ({ title, subtitle, children }) => (
  <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4 py-10">
    <div className="w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-7 space-y-5" data-testid="parent-setup-card">
      <div className="space-y-1">
        <ShieldCheck className="text-indigo-600" size={26} />
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-50">{title}</h1>
        {subtitle && <p className="text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>}
      </div>
      {children}
    </div>
  </div>
);

const Field = ({ id, label, ...p }) => (
  <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{p.type === "password" ? <PasswordInput id={id} {...p} /> : <Input id={id} {...p} />}</div>
);

const enterPortal = () => window.location.assign("/parents");

function LinkSetup({ token }) {
  const [info, setInfo] = useState(null);
  const [err, setErr] = useState("");
  const [pw, setPw] = useState({ a: "", b: "" });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get(`/public/parent-setup/${token}`).then((r) => setInfo(r.data)).catch((e) => setErr(errText(e)));
  }, [token]);
  const submit = async (e) => {
    e.preventDefault();
    if (pw.a !== pw.b) { setErr("Passwords do not match"); return; }
    setBusy(true); setErr("");
    try { await api.post(`/public/parent-setup/${token}`, { password: pw.a }); enterPortal(); }
    catch (e2) { setErr(errText(e2)); } finally { setBusy(false); }
  };
  if (!info) return <Shell title="Parent account setup">{err ? <p className="text-sm text-rose-600" data-testid="parent-setup-error">{err}</p> : <Loader2 className="animate-spin text-slate-400" />}</Shell>;
  return (
    <Shell title={`Welcome, ${info.parent_name}`} subtitle={`${info.school_name} has invited you to the parent app.`}>
      <ul className="space-y-1.5" data-testid="parent-setup-children">
        {info.children.map((c) => (
          <li key={c.name} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"><GraduationCap size={15} className="text-indigo-500" /> {c.name} <span className="text-slate-400">· {c.class}</span></li>
        ))}
      </ul>
      <form onSubmit={submit} className="space-y-3">
        <Field id="pw1" label="Choose a password" type="password" value={pw.a} onChange={(e) => setPw({ ...pw, a: e.target.value })} data-testid="parent-setup-password" />
        <Field id="pw2" label="Confirm password" type="password" value={pw.b} onChange={(e) => setPw({ ...pw, b: e.target.value })} data-testid="parent-setup-password-confirm" />
        {info.phone && (
          <p className="text-xs rounded-md bg-emerald-50 dark:bg-emerald-500/10 text-emerald-800 dark:text-emerald-300 px-3 py-2" data-testid="parent-setup-phone-login">
            You can now sign in with your mobile number <span className="font-mono font-semibold">{info.phone}</span> and this password.
          </p>
        )}
        <p className="text-xs text-slate-500">Or use your login ID: <span className="font-mono" data-testid="parent-setup-login-id">{info.login_email}</span></p>
        {err && <p className="text-sm text-rose-600" data-testid="parent-setup-error">{err}</p>}
        <Button type="submit" disabled={busy || pw.a.length < 6} className="w-full bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="parent-setup-submit">
          {busy ? "Setting up…" : "Set password & open portal"}
        </Button>
      </form>
    </Shell>
  );
}

function CodeRegister() {
  const [f, setF] = useState({ admission_no: "", code: "", name: "", phone: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try { await api.post("/public/parent-register", f); enterPortal(); }
    catch (e2) { setErr(errText(e2)); } finally { setBusy(false); }
  };
  return (
    <Shell title="Register with your invitation slip" subtitle="Enter the details printed on the slip your school sent home.">
      <form onSubmit={submit} className="space-y-3">
        <Field id="adm" label="Admission number (optional)" value={f.admission_no} onChange={set("admission_no")} data-testid="register-admission-no" />
        <Field id="code" label="Setup code" value={f.code} onChange={set("code")} autoCapitalize="characters" placeholder="e.g. ABCD-2345" data-testid="register-code" />
        <Field id="name" label="Your name" value={f.name} onChange={set("name")} data-testid="register-name" />
        <Field id="phone" label="Your mobile number" value={f.phone} onChange={set("phone")} inputMode="tel" data-testid="register-phone" />
        <Field id="rpw" label="Choose a password" type="password" value={f.password} onChange={set("password")} data-testid="register-password" />
        <p className="text-xs text-slate-500" data-testid="register-phone-login-note">After registering you can sign in with this mobile number and password.</p>
        {err && <p className="text-sm text-rose-600" data-testid="register-error">{err}</p>}
        <Button type="submit" disabled={busy || !f.code || !f.phone || f.password.length < 6} className="w-full bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="register-submit">
          {busy ? "Creating account…" : "Create account & open portal"}
        </Button>
      </form>
    </Shell>
  );
}

export default function ParentSetupPage() {
  const { token } = useParams();
  return token ? <LinkSetup token={token} /> : <CodeRegister />;
}
