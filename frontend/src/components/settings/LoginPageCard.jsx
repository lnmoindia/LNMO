import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Upload, RotateCcw, ExternalLink, Loader2 } from "lucide-react";
import api, { errText } from "../../lib/api";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";

const API = process.env.REACT_APP_BACKEND_URL;

export function LoginPageCard() {
  const fileRef = useRef(null);
  const [lp, setLp] = useState(null);
  const [tagline, setTagline] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get("/institution/login-page").then((r) => { setLp(r.data); setTagline(r.data.tagline || ""); }).catch(() => {});
  }, []);
  const call = async (fn, msg) => {
    setBusy(true);
    try { const r = await fn(); setLp(r.data); setTagline(r.data.tagline || ""); toast.success(msg); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const upload = (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { toast.error("Background photo must be 5 MB or smaller"); return; }
    const fd = new FormData();
    fd.append("file", file);
    call(() => api.post("/institution/login-page/background", fd, { headers: { "Content-Type": "multipart/form-data" } }), "Background updated");
  };
  if (!lp) return null;
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6" data-testid="login-page-card">
      <h2 className="font-heading font-semibold text-slate-900 dark:text-slate-100">Login page</h2>
      <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Background photo and tagline for <span className="font-mono text-xs">/login/{lp.slug}</span>. JPG, PNG or WebP up to 5&nbsp;MB — resized to 1920px automatically.</p>
      <div className="grid md:grid-cols-[1fr_280px] gap-5 mt-5">
        <div className="relative aspect-[16/9] rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700" data-testid="login-page-preview">
          <img src={`${API}${lp.background_url}`} alt="" className="absolute inset-0 h-full w-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-r from-slate-950/80 via-slate-950/45 to-slate-950/20" />
          <div className="relative h-full flex items-center justify-between gap-4 p-5">
            <div className="text-white max-w-[55%]">
              {lp.logo_url && <img src={lp.logo_url.startsWith("/api") ? `${API}${lp.logo_url}` : lp.logo_url} alt="" className="h-9 w-9 rounded-lg object-cover mb-2" />}
              <p className="font-heading font-bold text-lg leading-tight">{lp.name}</p>
              {tagline && <p className="text-xs text-white/80 mt-1" data-testid="login-page-preview-tagline">{tagline}</p>}
            </div>
            <div className="w-32 rounded-lg bg-white/90 dark:bg-slate-900/90 p-2.5 space-y-1.5">
              <div className="h-2 w-12 rounded bg-slate-300" /><div className="h-5 rounded bg-slate-200" /><div className="h-5 rounded bg-slate-200" /><div className="h-5 rounded bg-indigo-600" />
            </div>
          </div>
        </div>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="lp-tagline">Tagline</Label>
            <Input id="lp-tagline" value={tagline} maxLength={80} onChange={(e) => setTagline(e.target.value)} placeholder="e.g. Learning that lights the way" data-testid="login-page-tagline-input" />
            <p className="text-[11px] text-slate-400">{tagline.length}/80</p>
          </div>
          <Button size="sm" disabled={busy || tagline === (lp.tagline || "")} onClick={() => call(() => api.put("/institution/login-page", { tagline }), "Tagline saved")} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="login-page-tagline-save">Save tagline</Button>
          <div className="flex flex-wrap gap-2 pt-1">
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={upload} data-testid="login-page-bg-input" />
            <Button size="sm" variant="outline" disabled={busy} onClick={() => fileRef.current?.click()} data-testid="login-page-bg-upload">
              {busy ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <Upload size={14} className="mr-1.5" />} {lp.has_background ? "Replace photo" : "Upload photo"}
            </Button>
            {lp.has_background && (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => call(() => api.delete("/institution/login-page/background"), "Reset to the default background")} data-testid="login-page-bg-reset">
                <RotateCcw size={14} className="mr-1.5" /> Use default
              </Button>
            )}
          </div>
          <a href={`/login/${lp.slug}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:underline" data-testid="login-page-open-link"><ExternalLink size={12} /> Open login page</a>
        </div>
      </div>
    </div>
  );
}
