import { useState } from "react";
import { toast } from "sonner";
import { KeyRound } from "lucide-react";
import api, { errText } from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { roleHome } from "../LoginPage";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { PasswordInput } from "../../components/common/PasswordInput";
import { Label } from "../../components/ui/label";

export default function ChangePasswordPage() {
  const { user } = useAuth();
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (pw.length < 6) return toast.error("Password must be at least 6 characters");
    if (pw !== pw2) return toast.error("Passwords do not match");
    setSaving(true);
    try {
      await api.post("/auth/change-password", { new_password: pw });
      toast.success("Password updated");
      window.location.href = roleHome(user?.role || "");
    } catch (e) { toast.error(errText(e)); setSaving(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-[#0B0F17] px-4" data-testid="change-password-page">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8">
        <div className="h-12 w-12 rounded-xl bg-indigo-600 flex items-center justify-center mb-5"><KeyRound className="text-white" size={22} /></div>
        <h1 className="font-heading text-2xl font-bold text-slate-900 dark:text-slate-50">Set a new password</h1>
        <p className="text-sm text-slate-500 mt-1 mb-6">For security, please choose your own password before continuing.</p>
        <div className="space-y-4">
          <div className="space-y-1.5"><Label>New password</Label><PasswordInput resetKey={saving} value={pw} onChange={(e) => setPw(e.target.value)} data-testid="new-password" /></div>
          <div className="space-y-1.5"><Label>Confirm password</Label><PasswordInput resetKey={saving} value={pw2} onChange={(e) => setPw2(e.target.value)} data-testid="confirm-password" /></div>
          <Button onClick={submit} disabled={saving} className="w-full bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="change-password-btn">{saving ? "Saving…" : "Update password"}</Button>
        </div>
      </div>
    </div>
  );
}
