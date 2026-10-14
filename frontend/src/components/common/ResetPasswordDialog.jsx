import { useState } from "react";
import { KeyRound, Mail, Wand2, Copy, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../ui/button";
import { Label } from "../ui/label";
import { PasswordInput } from "./PasswordInput";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../ui/dialog";

const RULE = "At least 8 characters with an uppercase letter, a lowercase letter and a number.";
const strong = (p) => p.length >= 8 && /[A-Z]/.test(p) && /[a-z]/.test(p) && /\d/.test(p);

export function ResetPasswordDialog({ userId, name, hasEmail, open, onClose }) {
  const [tab, setTab] = useState("set");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [shown, setShown] = useState(null);
  const [sent, setSent] = useState(null);
  const close = () => { setPw(""); setShown(null); setSent(null); setTab("set"); onClose(); };

  const setPassword = async (generate) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/users/${userId}/set-password`, generate ? { generate: true } : { password: pw });
      setPw("");
      if (generate) setShown(data.generated_password);
      else { toast.success(`Password set — ${name || "they"} must change it at next sign-in`); close(); }
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const emailLink = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/users/${userId}/reset-link`); setSent(data); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent className="max-w-md" data-testid="reset-password-dialog">
        <DialogHeader>
          <DialogTitle>Reset password · {name}</DialogTitle>
          <DialogDescription>Either way they're signed out everywhere, any lockout is cleared and they must choose a new password at next sign-in.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-1 rounded-lg bg-slate-100 dark:bg-slate-800 p-1 text-sm">
          {[["set", "Set password", KeyRound], ["email", "Email reset link", Mail]].map(([k, l, I]) => (
            <button key={k} onClick={() => setTab(k)} className={`flex items-center justify-center gap-1.5 rounded-md py-1.5 font-medium transition-colors ${tab === k ? "bg-white dark:bg-slate-900 shadow-sm text-slate-900 dark:text-white" : "text-slate-500"}`} data-testid={`reset-tab-${k}`}><I size={14} /> {l}</button>
          ))}
        </div>
        {tab === "set" && (shown ? (
          <div className="space-y-3" data-testid="reset-generated">
            <p className="text-sm text-slate-600 dark:text-slate-300">Share this temporary password with {name}. It's shown only once.</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded-lg bg-slate-100 dark:bg-slate-800 px-3 py-2 font-mono text-lg tracking-wider" data-testid="reset-generated-value">{shown}</code>
              <Button variant="outline" onClick={() => { navigator.clipboard?.writeText(shown); toast.success("Copied"); }} data-testid="reset-copy-btn"><Copy size={14} /></Button>
            </div>
            <Button className="w-full" onClick={close} data-testid="reset-done-btn">Done</Button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>New temporary password</Label>
              <PasswordInput value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" data-testid="reset-new-password" />
              <p className={`text-xs ${pw && !strong(pw) ? "text-rose-600" : "text-slate-500"}`}>{RULE}</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" disabled={busy} onClick={() => setPassword(true)} data-testid="reset-generate-btn"><Wand2 size={14} className="mr-1.5" /> Generate</Button>
              <Button className="flex-1 bg-indigo-700 hover:bg-indigo-800 text-white" disabled={busy || !strong(pw)} onClick={() => setPassword(false)} data-testid="reset-set-btn">
                {busy && <Loader2 size={14} className="mr-1.5 animate-spin" />} Set password
              </Button>
            </div>
          </div>
        ))}
        {tab === "email" && (sent ? (
          <p className="text-sm text-emerald-700 dark:text-emerald-400" data-testid="reset-link-sent">Reset link sent to {sent.sent_to}. It works once and expires in 24 hours.</p>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-600 dark:text-slate-300">{hasEmail === false ? "This account has no email address — use Set password instead." : "We'll email a secure single-use link (valid 24 hours) from LNMO Support."}</p>
            <Button className="w-full bg-indigo-700 hover:bg-indigo-800 text-white" disabled={busy || hasEmail === false} onClick={emailLink} data-testid="reset-email-btn">
              {busy && <Loader2 size={14} className="mr-1.5 animate-spin" />} Email reset link
            </Button>
          </div>
        ))}
      </DialogContent>
    </Dialog>
  );
}

export function ResetPasswordButton({ userId, name, hasEmail, size = "default" }) {
  const [open, setOpen] = useState(false);
  if (!userId) return null;
  return (
    <>
      <Button variant="outline" size={size} onClick={() => setOpen(true)} data-testid="reset-password-btn"><KeyRound size={14} className="mr-1.5" /> Reset password</Button>
      <ResetPasswordDialog open={open} onClose={() => setOpen(false)} userId={userId} name={name} hasEmail={hasEmail} />
    </>
  );
}
