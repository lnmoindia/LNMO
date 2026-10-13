import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Upload, Trash2, ImageOff } from "lucide-react";
import api, { errText } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Skeleton } from "../components/ui/skeleton";

const FIELDS = [
  { name: "name", label: "Institution name" },
  { name: "code", label: "Code" },
  { name: "city", label: "City" },
  { name: "address", label: "Address" },
  { name: "contact_email", label: "Contact email", type: "email" },
  { name: "phone", label: "Phone" },
  { name: "website", label: "Website" },
  { name: "academic_year", label: "Current academic year" },
  { name: "portal_name", label: "Portal display name" },
];

const API = process.env.REACT_APP_BACKEND_URL;

function LogoCard() {
  const fileRef = useRef(null);
  const [hasLogo, setHasLogo] = useState(false);
  const [bust, setBust] = useState(Date.now());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/institution/logo-status").then((r) => setHasLogo(Boolean(r.data?.has_logo))).catch(() => {});
  }, []);

  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setBusy(true);
    try {
      await api.post("/institution/logo", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setHasLogo(true);
      setBust(Date.now());
      toast.success("Logo updated");
    } catch (err) {
      toast.error(errText(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.delete("/institution/logo");
      setHasLogo(false);
      toast.success("Logo removed");
    } catch (err) {
      toast.error(errText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6" data-testid="institution-logo-card">
      <h2 className="font-heading font-semibold text-slate-900 dark:text-slate-100">School logo</h2>
      <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Shown on your branded login page and student/parent portals. JPG, PNG or WebP, up to 4&nbsp;MB.</p>
      <div className="flex items-center gap-5 mt-5">
        <div className="h-20 w-20 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex items-center justify-center overflow-hidden shrink-0">
          {hasLogo
            ? <img src={`${API}/api/institution/logo?t=${bust}`} alt="logo" className="h-full w-full object-cover" data-testid="institution-logo-preview" />
            : <ImageOff size={24} className="text-slate-300 dark:text-slate-600" />}
        </div>
        <div className="flex flex-wrap gap-2">
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={upload} data-testid="institution-logo-input" />
          <Button type="button" variant="outline" disabled={busy} onClick={() => fileRef.current?.click()} data-testid="institution-logo-upload-btn">
            <Upload size={15} className="mr-1.5" /> {hasLogo ? "Replace logo" : "Upload logo"}
          </Button>
          {hasLogo && (
            <Button type="button" variant="outline" disabled={busy} onClick={remove} className="text-red-600 hover:text-red-700" data-testid="institution-logo-remove-btn">
              <Trash2 size={15} className="mr-1.5" /> Remove
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function SealCard() {
  const fileRef = useRef(null);
  const [hasSeal, setHasSeal] = useState(false);
  const [bust, setBust] = useState(Date.now());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/institution/seal-status").then((r) => setHasSeal(Boolean(r.data?.has_seal))).catch(() => {});
  }, []);

  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setBusy(true);
    try {
      await api.post("/institution/seal", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setHasSeal(true); setBust(Date.now()); toast.success("Seal saved");
    } catch (err) { toast.error(errText(err)); } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true);
    try { await api.delete("/institution/seal"); setHasSeal(false); toast.success("Seal removed"); }
    catch (err) { toast.error(errText(err)); } finally { setBusy(false); }
  };

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6" data-testid="institution-seal-card">
      <h2 className="font-heading font-semibold text-slate-900 dark:text-slate-100">Official seal</h2>
      <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Stamped on report cards & certificates. Stored privately — never shown publicly. PNG with transparency works best.</p>
      <div className="flex items-center gap-5 mt-5">
        <div className="h-20 w-20 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex items-center justify-center overflow-hidden shrink-0">
          {hasSeal
            ? <img src={`${API}/api/institution/seal?t=${bust}`} alt="seal" className="h-full w-full object-contain" data-testid="institution-seal-preview" />
            : <ImageOff size={24} className="text-slate-300 dark:text-slate-600" />}
        </div>
        <div className="flex flex-wrap gap-2">
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={upload} data-testid="institution-seal-input" />
          <Button type="button" variant="outline" disabled={busy} onClick={() => fileRef.current?.click()} data-testid="institution-seal-upload-btn">
            <Upload size={15} className="mr-1.5" /> {hasSeal ? "Replace seal" : "Upload seal"}
          </Button>
          {hasSeal && (
            <Button type="button" variant="outline" disabled={busy} onClick={remove} className="text-red-600 hover:text-red-700" data-testid="institution-seal-remove-btn">
              <Trash2 size={15} className="mr-1.5" /> Remove
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function InstitutionSettingsPage() {
  const [values, setValues] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let ignore = false;
    api.get("/institution/profile")
      .then((r) => { if (!ignore) setValues((v) => v || r.data); })
      .catch((e) => { if (!ignore) { toast.error(errText(e)); setValues((v) => v || {}); } });
    return () => { ignore = true; };
  }, []);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {};
      FIELDS.forEach((f) => { payload[f.name] = values[f.name] ?? ""; });
      payload.primary_color = values.primary_color ?? "";
      const { data } = await api.put("/institution/profile", payload);
      setValues(data);
      toast.success("Institution profile saved");
    } catch (err) {
      toast.error(errText(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl" data-testid="institution-settings-page">
      <div>
        <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">Institution settings</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Profile, branding and identity of your institution.</p>
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6">
        {!values ? (
          <div className="space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
        ) : (
          <form onSubmit={save} className="space-y-4">
            {FIELDS.map((f) => (
              <div key={f.name} className="space-y-1.5">
                <Label htmlFor={f.name}>{f.label}</Label>
                <Input
                  id={f.name}
                  type={f.type || "text"}
                  value={values[f.name] || ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                  data-testid={`settings-field-${f.name}`}
                />
              </div>
            ))}
            <div className="space-y-1.5">
              <Label htmlFor="primary_color">Primary colour</Label>
              <div className="flex gap-2">
                <Input type="color" value={values.primary_color || "#4f46e5"} onChange={(e) => setValues((v) => ({ ...v, primary_color: e.target.value }))} className="w-14 p-1 h-9" data-testid="settings-field-primary_color" />
                <Input value={values.primary_color || ""} onChange={(e) => setValues((v) => ({ ...v, primary_color: e.target.value }))} placeholder="#4f46e5" />
              </div>
            </div>
            <div className="flex justify-end pt-2">
              <Button type="submit" disabled={saving} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="settings-save-btn">
                {saving ? "Saving…" : "Save changes"}
              </Button>
            </div>
          </form>
        )}
      </div>

      <LogoCard />
      <SealCard />
    </div>
  );
}
