import { useEffect, useRef, useState } from "react";
import { ImageUp, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import DangerZoneCard from "./DangerZoneCard";

const API = process.env.REACT_APP_BACKEND_URL;
const MAX = 10 * 1024 * 1024;
const PREVIEWS = [
  ["lnmo-logo@2x.png", "Full logo", "h-20"],
  ["lnmo-mark@2x.png", "Mark only", "h-12"],
  ["icon-192.png", "App icon", "h-12"],
  ["icon-maskable-512.png", "Maskable icon", "h-12"],
  ["apple-touch-icon.png", "Apple touch", "h-12"],
];

const Tile = ({ src, label, h, dark }) => (
  <div className={`rounded-xl border p-4 flex flex-col items-center gap-2 ${dark ? "bg-slate-950 border-slate-800" : "bg-[repeating-conic-gradient(#f1f5f9_0_25%,#fff_0_50%)] [background-size:16px_16px] border-slate-200"}`}>
    <img src={src} alt={label} className={`${h} w-auto object-contain`} />
    <span className={`text-[11px] ${dark ? "text-slate-400" : "text-slate-500"}`}>{label}</span>
  </div>
);

function BrandingCard() {
  const [b, setB] = useState(null);
  const [busy, setBusy] = useState(false);
  const input = useRef(null);
  useEffect(() => { api.get("/platform/branding").then((r) => setB(r.data)).catch((e) => toast.error(errText(e))); }, []);

  const upload = async (file) => {
    if (!file) return;
    if (file.size > MAX) return toast.error("Logo must be 10 MB or smaller");
    const fd = new FormData();
    fd.append("file", file);
    setBusy(true);
    try {
      const { data } = await api.post("/platform/branding/logo", fd);
      setB(data);
      toast.success("LNMO logo updated — background removed and icons regenerated");
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); if (input.current) input.current.value = ""; }
  };
  const reset = async () => {
    if (!window.confirm("Go back to the bundled default LNMO logo?")) return;
    try { const { data } = await api.delete("/platform/branding/logo"); setB(data); toast.success("Default logo restored"); }
    catch (e) { toast.error(errText(e)); }
  };
  const src = (n) => `${API}${b?.assets?.[n] || `/api/public/platform-brand/${n}`}`;

  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-5" data-testid="platform-branding-card">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="font-heading text-lg font-semibold text-slate-900 dark:text-slate-50">Platform branding</h2>
          <p className="text-sm text-slate-500 mt-1 max-w-xl">Upload the LNMO logo (PNG, JPG, WebP or SVG, up to 10 MB). Raster images are cleaned automatically: the white tile and shadow are removed, padding is trimmed, and the favicon, app icons and mark are regenerated.</p>
          {b && <p className="text-xs text-slate-400 mt-2" data-testid="platform-branding-meta">{b.uploaded ? `Version ${b.version} · ${b.original_name || "uploaded"} · ${b.updated_by || ""}` : "Using the bundled default logo"}</p>}
        </div>
        <div className="flex gap-2">
          <input ref={input} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" className="hidden" onChange={(e) => upload(e.target.files?.[0])} data-testid="platform-logo-input" />
          <Button onClick={() => input.current?.click()} disabled={busy} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="platform-logo-upload-btn">
            <ImageUp size={15} className="mr-1.5" /> {busy ? "Processing…" : "Upload logo"}
          </Button>
          {b?.uploaded && <Button variant="outline" onClick={reset} data-testid="platform-logo-reset-btn"><RotateCcw size={15} className="mr-1.5" /> Default</Button>}
        </div>
      </div>
      {b && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="platform-logo-preview">
          {PREVIEWS.map(([n, label, h]) => <Tile key={n} src={src(n)} label={label} h={h} />)}
          <Tile src={src("lnmo-logo@2x.png")} label="Full logo on dark" h="h-20" dark />
          <Tile src={src("lnmo-mark@2x.png")} label="Mark on dark" h="h-12" dark />
          <Tile src={src("lnmo-mark.svg")} label="Mark (SVG)" h="h-12" dark />
          <Tile src={src("favicon.ico")} label="Favicon" h="h-8" />
        </div>
      )}
    </div>
  );
}

export default function PlatformSettings() {
  return (
    <div className="space-y-6" data-testid="platform-settings-page">
      <div>
        <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">Settings</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Platform-wide settings for LNMO.</p>
      </div>
      <BrandingCard />
      <DangerZoneCard />
    </div>
  );
}
