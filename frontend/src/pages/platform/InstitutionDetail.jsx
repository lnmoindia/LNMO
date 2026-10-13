import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Building2, Globe, Palette, Copy, ExternalLink, Sparkles } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";

const TABS = [
  { key: "overview", label: "Overview", icon: Building2 },
  { key: "domain", label: "Domain & Access", icon: Globe },
  { key: "branding", label: "Branding", icon: Palette },
  { key: "features", label: "Features / AI", icon: Sparkles },
];

export default function InstitutionDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState(null);
  const [tab, setTab] = useState("overview");
  const [saving, setSaving] = useState(false);
  const [ai, setAi] = useState(null);        // {features, summary}
  const [stats, setStats] = useState(null);   // usage counts

  useEffect(() => { api.get(`/res/institutions/${id}`).then((r) => setForm(r.data)).catch((e) => toast.error(errText(e))); }, [id]);
  useEffect(() => { api.get(`/platform/institutions/${id}/ai`).then((r) => setAi(r.data)).catch(() => {}); }, [id]);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const toggleLayer = async (on) => {
    try { const { data } = await api.put(`/platform/institutions/${id}/features`, { ai_layer_enabled: on });
      setAi((a) => ({ ...a, features: data.features })); toast.success(`AI Layer ${on ? "enabled" : "disabled"}`); }
    catch (e) { toast.error(errText(e)); }
  };

  const save = async () => {
    setSaving(true);
    try { await api.put(`/res/institutions/${id}`, form); toast.success("Saved"); }
    catch (e) { toast.error(errText(e)); } finally { setSaving(false); }
  };

  if (!form) return <div className="text-slate-400">Loading…</div>;
  const F = ({ k, label, type = "text", placeholder }) => (
    <div className="space-y-1.5"><Label>{label}</Label><Input type={type} value={form[k] || ""} onChange={(e) => set(k, e.target.value)} placeholder={placeholder} data-testid={`inst-${k}`} /></div>
  );

  return (
    <div className="space-y-6" data-testid="institution-detail">
      <button onClick={() => navigate("/platform/institutions")} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 dark:hover:text-slate-200" data-testid="back-to-institutions"><ArrowLeft size={15} /> Institutions</button>
      <div className="flex items-center gap-3">
        <div className="h-12 w-12 rounded-xl flex items-center justify-center text-white font-heading font-bold" style={{ background: form.primary_color || "#4f46e5" }}>{(form.name || "?")[0]}</div>
        <div>
          <h1 className="font-heading text-2xl font-bold text-slate-900 dark:text-slate-50">{form.name}</h1>
          <p className="text-sm text-slate-500">{form.domain || "No domain set"}</p>
        </div>
      </div>

      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-800">
        {TABS.map((t) => { const I = t.icon; return (
          <button key={t.key} onClick={() => setTab(t.key)} data-testid={`inst-tab-${t.key}`} className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px ${tab === t.key ? "border-indigo-600 text-indigo-700 dark:text-indigo-300" : "border-transparent text-slate-500"}`}><I size={15} /> {t.label}</button>
        ); })}
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 max-w-2xl">
        {tab === "overview" && <div className="grid sm:grid-cols-2 gap-4"><F k="name" label="Institution name" /><F k="code" label="Code" /><F k="city" label="City" /><F k="contact_email" label="Contact email" type="email" /><F k="phone" label="Phone" /></div>}
        {tab === "domain" && <div className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <F k="domain" label="Domain" placeholder="greenwood.edu" />
            <F k="slug" label="URL slug" placeholder="greenwood" />
          </div>
          <div className="text-xs text-slate-500">Domain auto-generates teacher & student login IDs (e.g. ravi.kumar@{form.domain || "greenwood.edu"}) — not DNS hosting. Slug powers a friendly branded login URL; lowercase letters, numbers and hyphens only.</div>
          {(form.slug || form.code || form.domain) && (() => {
            const key = form.slug || (form.code || "").toLowerCase() || form.domain;
            const link = `${window.location.origin}/login/${encodeURIComponent(key)}`;
            return (
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 p-4 space-y-2" data-testid="branded-login-link">
                <Label>Branded login link</Label>
                <div className="flex gap-2">
                  <Input readOnly value={link} data-testid="login-link-input" onFocus={(e) => e.target.select()} />
                  <Button type="button" variant="outline" onClick={() => { navigator.clipboard?.writeText(link); toast.success("Login link copied"); }} data-testid="copy-login-link"><Copy size={15} className="mr-1" /> Copy</Button>
                  <Button type="button" variant="outline" onClick={() => window.open(link, "_blank")} data-testid="open-login-link"><ExternalLink size={15} /></Button>
                </div>
                <p className="text-xs text-slate-500">Share this so staff & students land on a login page branded with this school's logo and colours.</p>
              </div>
            );
          })()}
        </div>}
        {tab === "branding" && <div className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <F k="portal_name" label="Portal display name" placeholder={form.name} />
            <div className="space-y-1.5"><Label>Primary color</Label><div className="flex gap-2"><Input type="color" value={form.primary_color || "#4f46e5"} onChange={(e) => set("primary_color", e.target.value)} className="w-14 p-1 h-9" data-testid="inst-primary_color" /><Input value={form.primary_color || ""} onChange={(e) => set("primary_color", e.target.value)} placeholder="#4f46e5" /></div></div>
            <div className="sm:col-span-2"><F k="logo_url" label="Logo URL" placeholder="https://…/logo.png" /></div>
          </div>
          {form.logo_url && <img src={form.logo_url} alt="logo" className="h-12 rounded border border-slate-200 dark:border-slate-700 p-1" />}
        </div>}
        {tab === "features" && (
          <div className="space-y-6" data-testid="inst-features-tab">
            <div className="flex items-start justify-between gap-4 rounded-xl border-2 border-violet-200 dark:border-violet-900 bg-violet-50/50 dark:bg-violet-950/20 p-4">
              <div>
                <p className="font-heading font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Sparkles size={16} className="text-violet-600" /> AI Layer</p>
                <p className="text-sm text-slate-500 mt-1 max-w-md">Master switch for all AI Tutor surfaces at this school. When OFF, students can't chat or browse the AI library regardless of per-curriculum settings. When ON, each school's per-curriculum AI toggles govern.</p>
              </div>
              <button role="switch" aria-checked={!!ai?.features?.ai_layer_enabled} onClick={() => toggleLayer(!ai?.features?.ai_layer_enabled)} data-testid="inst-ai-layer-toggle"
                className={`relative w-14 h-7 rounded-full transition-colors shrink-0 ${ai?.features?.ai_layer_enabled ? "bg-violet-600" : "bg-slate-300 dark:bg-slate-700"}`}>
                <span className={`absolute top-0.5 left-0.5 w-6 h-6 rounded-full bg-white transition-transform ${ai?.features?.ai_layer_enabled ? "translate-x-7" : ""}`} />
              </button>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase text-slate-400 mb-2">AI usage (read-only)</p>
              <div className="grid grid-cols-3 gap-3" data-testid="inst-ai-summary">
                {[["Curricula", ai?.summary?.curricula], ["AI-enabled", ai?.summary?.ai_enabled_curricula], ["Tutor msgs / month", ai?.summary?.tutor_messages_month]].map(([l, v]) => (
                  <div key={l} className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 text-center">
                    <p className="font-heading text-2xl font-bold text-slate-900 dark:text-slate-50">{v ?? "—"}</p>
                    <p className="text-xs text-slate-400 mt-1">{l}</p>
                  </div>
                ))}
              </div>
            </div>
            <p className="text-xs text-slate-400">More AI capabilities (ELSA, Risk Detection, Teacher Assistant…) will appear here as additional platform-governed toggles.</p>
          </div>
        )}
        {tab !== "features" && <div className="flex justify-end mt-6"><Button onClick={save} disabled={saving} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="inst-save-btn">{saving ? "Saving…" : "Save changes"}</Button></div>}
      </div>
    </div>
  );
}
