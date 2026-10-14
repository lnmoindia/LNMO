import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CheckCircle2, ShieldAlert } from "lucide-react";
import api, { errText } from "../lib/api";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import { PasswordInput } from "../components/common/PasswordInput";
import { PoweredBy } from "../components/common/LnmoLogo";

const API = process.env.REACT_APP_BACKEND_URL;
const rules = [["8+ characters", (p) => p.length >= 8], ["Uppercase letter", (p) => /[A-Z]/.test(p)], ["Lowercase letter", (p) => /[a-z]/.test(p)], ["Number", (p) => /\d/.test(p)]];

export default function ResetPasswordPage() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [bad, setBad] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  useEffect(() => { api.get(`/public/password-reset/${token}`).then((r) => setInfo(r.data)).catch((e) => setBad(errText(e))); }, [token]);
  useEffect(() => { if (info?.school?.name) document.title = `${info.school.name} · Reset password`; }, [info]);
  const ok = rules.every(([, f]) => f(pw)) && pw === pw2;
  const submit = async (e) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try { const { data } = await api.post(`/public/password-reset/${token}`, { password: pw }); setDone(data); }
    catch (x) { const m = errText(x); if (x.response?.status === 410) setBad(m); else setErr(m); } finally { setBusy(false); }
  };
  const color = info?.school?.primary_color || "#4338ca";
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#0B0F17] flex flex-col items-center justify-center p-4" data-testid="reset-password-page">
      <div className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm p-8">
        {info?.school && (
          <div className="flex items-center gap-3 mb-6" data-testid="reset-school">
            {info.school.logo_url ? <img src={`${API}${info.school.logo_url}`} alt="" className="h-11 w-11 rounded-xl object-contain" />
              : <div className="h-11 w-11 rounded-xl text-white font-bold flex items-center justify-center" style={{ background: color }}>{info.school.name?.[0]}</div>}
            <p className="font-heading font-bold text-slate-900 dark:text-white">{info.school.name}</p>
          </div>
        )}
        {bad ? (
          <div className="text-center space-y-3" data-testid="reset-invalid">
            <ShieldAlert size={36} className="mx-auto text-amber-500" />
            <h1 className="font-heading text-xl font-bold text-slate-900 dark:text-white">Link can't be used</h1>
            <p className="text-sm text-slate-500">{bad}</p>
          </div>
        ) : done ? (
          <div className="text-center space-y-3" data-testid="reset-success">
            <CheckCircle2 size={36} className="mx-auto text-emerald-600" />
            <h1 className="font-heading text-xl font-bold text-slate-900 dark:text-white">Password updated</h1>
            <p className="text-sm text-slate-500">You've been signed out on all devices. Sign in with your new password.</p>
            <Button asChild className="w-full text-white" style={{ background: color }}><Link to={done.login_key ? `/login/${done.login_key}` : "/login"} data-testid="reset-goto-login">Go to sign in</Link></Button>
          </div>
        ) : !info ? <p className="text-sm text-slate-400">Checking your link…</p> : (
          <form onSubmit={submit} className="space-y-4">
            <div><h1 className="font-heading text-xl font-bold text-slate-900 dark:text-white">Set a new password</h1>
              <p className="text-sm text-slate-500 mt-1">Hi {info.name}, choose a new password for {info.email_masked}.</p></div>
            <div className="space-y-1.5"><Label htmlFor="pw">New password</Label><PasswordInput id="pw" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} data-testid="reset-password-input" required /></div>
            <div className="space-y-1.5"><Label htmlFor="pw2">Confirm password</Label><PasswordInput id="pw2" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} data-testid="reset-confirm-input" required /></div>
            <ul className="grid grid-cols-2 gap-1 text-xs" data-testid="reset-rules">
              {rules.map(([l, f]) => <li key={l} className={f(pw) ? "text-emerald-600" : "text-slate-400"}>{f(pw) ? "✓" : "•"} {l}</li>)}
              <li className={pw && pw === pw2 ? "text-emerald-600" : "text-slate-400"}>{pw && pw === pw2 ? "✓" : "•"} Passwords match</li>
            </ul>
            {err && <p className="text-sm text-red-600" data-testid="reset-form-error">{err}</p>}
            <Button type="submit" disabled={!ok || busy} className="w-full text-white" style={{ background: color }} data-testid="reset-submit-btn">{busy ? "Saving…" : "Set new password"}</Button>
          </form>
        )}
      </div>
      <PoweredBy className="justify-center mt-6 text-[11px] text-slate-400" testid="reset-powered-by" />
    </div>
  );
}
