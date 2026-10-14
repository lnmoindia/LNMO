import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Activity, ArrowLeft, BarChart3, Building2, CreditCard, Globe, Palette, Sparkles, Users } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Skeleton } from "../../components/ui/skeleton";
import OverviewTab, { LoginLink } from "./inst/OverviewTab";
import AnalyticsTab from "./inst/AnalyticsTab";
import PlanTab from "./inst/PlanTab";
import AdminsTab from "./inst/AdminsTab";
import ActivityTab from "./inst/ActivityTab";
import { PlanBadge, StatusPill } from "./inst/ui";

const API = process.env.REACT_APP_BACKEND_URL;
const TABS = [
  { key: "overview", label: "Overview", icon: Building2 },
  { key: "analytics", label: "Analytics & Usage", icon: BarChart3 },
  { key: "plan", label: "Plan", icon: CreditCard },
  { key: "admins", label: "Admins", icon: Users },
  { key: "domain", label: "Domain & Access", icon: Globe },
  { key: "branding", label: "Branding", icon: Palette },
  { key: "features", label: "AI & Features", icon: Sparkles },
  { key: "activity", label: "Activity", icon: Activity },
];

function EditForm({ form, set, children, onSave, saving }) {
  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 max-w-3xl space-y-4">
      {children}
      <div className="flex justify-end"><Button onClick={onSave} disabled={saving} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="inst-save-btn">{saving ? "Saving…" : "Save changes"}</Button></div>
    </div>
  );
}

function FeaturesTab({ id }) {
  const [ai, setAi] = useState(null);
  useEffect(() => { api.get(`/platform/institutions/${id}/ai`).then((r) => setAi(r.data)).catch(() => {}); }, [id]);
  const toggle = async (on) => {
    try { const { data } = await api.put(`/platform/institutions/${id}/features`, { ai_layer_enabled: on }); setAi((a) => ({ ...a, features: data.features })); toast.success(`AI Layer ${on ? "enabled" : "disabled"}`); }
    catch (e) { toast.error(errText(e)); }
  };
  const on = !!ai?.features?.ai_layer_enabled;
  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 max-w-3xl space-y-6" data-testid="inst-features-tab">
      <div className="flex items-start justify-between gap-4 rounded-xl border-2 border-violet-200 dark:border-violet-900 bg-violet-50/50 dark:bg-violet-950/20 p-4">
        <div><p className="font-heading font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Sparkles size={16} className="text-violet-600" /> AI Layer</p>
          <p className="text-sm text-slate-500 mt-1 max-w-md">Master switch for all AI Tutor surfaces at this school. When OFF, students can't chat or browse the AI library regardless of per-curriculum settings.</p></div>
        <button role="switch" aria-checked={on} onClick={() => toggle(!on)} data-testid="inst-ai-layer-toggle" className={`relative w-14 h-7 rounded-full transition-colors shrink-0 ${on ? "bg-violet-600" : "bg-slate-300 dark:bg-slate-700"}`}>
          <span className={`absolute top-0.5 left-0.5 w-6 h-6 rounded-full bg-white transition-transform ${on ? "translate-x-7" : ""}`} /></button>
      </div>
      <div className="grid grid-cols-3 gap-3" data-testid="inst-ai-summary">
        {[["Curricula", ai?.summary?.curricula], ["AI-enabled", ai?.summary?.ai_enabled_curricula], ["Tutor msgs / month", ai?.summary?.tutor_messages_month]].map(([l, v]) => (
          <div key={l} className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 text-center"><p className="font-heading text-2xl font-bold text-slate-900 dark:text-slate-50">{v ?? "—"}</p><p className="text-xs text-slate-400 mt-1">{l}</p></div>
        ))}
      </div>
    </div>
  );
}

export default function InstitutionDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [sp, setSp] = useSearchParams();
  const tab = TABS.some((t) => t.key === sp.get("tab")) ? sp.get("tab") : "overview";
  const [form, setForm] = useState(null);
  const [head, setHead] = useState(null);
  const [saving, setSaving] = useState(false);
  const loadHead = () => api.get(`/platform/institutions/${id}/overview`).then((r) => setHead(r.data)).catch(() => {});
  useEffect(() => { api.get(`/res/institutions/${id}`).then((r) => setForm(r.data)).catch((e) => toast.error(errText(e))); loadHead(); }, [id]); // eslint-disable-line
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const save = async () => {
    setSaving(true);
    try { await api.put(`/res/institutions/${id}`, form); toast.success("Saved"); loadHead(); } catch (e) { toast.error(errText(e)); } finally { setSaving(false); }
  };
  const F = (k, label, type = "text", placeholder) => (
    <div className="space-y-1.5"><Label>{label}</Label><Input type={type} value={form?.[k] || ""} onChange={(e) => set(k, e.target.value)} placeholder={placeholder} data-testid={`inst-${k}`} /></div>
  );
  const logo = head?.branding?.logo_url;
  return (
    <div className="space-y-6" data-testid="institution-detail">
      <button onClick={() => navigate("/platform/institutions")} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 dark:hover:text-slate-200" data-testid="back-to-institutions"><ArrowLeft size={15} /> Institutions</button>
      {!head ? <Skeleton className="h-16 w-96 rounded-xl" /> : (
        <div className="flex flex-wrap items-center gap-4 justify-between">
          <div className="flex items-center gap-4 min-w-0">
            {logo ? <img src={`${API}${logo}`} alt="" className="h-14 w-14 rounded-xl object-contain bg-white border border-slate-200 p-1" data-testid="inst-logo" />
              : <div className="h-14 w-14 rounded-xl flex items-center justify-center text-white font-heading font-bold text-xl bg-indigo-600">{(head.institution.name || "?")[0]}</div>}
            <div className="min-w-0">
              <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50 truncate" data-testid="inst-name">{head.institution.name}</h1>
              <div className="flex flex-wrap items-center gap-2 mt-1 text-sm text-slate-500">
                <span className="font-mono" data-testid="inst-code">{head.institution.code || "—"}</span><StatusPill status={head.status} /><PlanBadge name={head.plan?.name} />
                {head.institution.is_demo && <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">Demo</span>}
              </div>
            </div>
          </div>
          <div className="flex gap-2 flex-wrap">
            <Button variant="outline" size="sm" onClick={() => setSp({ tab: "admins" })} data-testid="qa-admins">Manage admins</Button>
            <Button variant="outline" size="sm" onClick={() => setSp({ tab: "plan" })} data-testid="qa-plan">Edit plan</Button>
            {head.login_key && <Button variant="outline" size="sm" onClick={() => window.open(`/login/${encodeURIComponent(head.login_key)}`, "_blank")} data-testid="qa-open-login">Open login page</Button>}
          </div>
        </div>
      )}
      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-800 overflow-x-auto" role="tablist">
        {TABS.map((t) => { const I = t.icon; return (
          <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setSp({ tab: t.key })} data-testid={`inst-tab-${t.key}`}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors ${tab === t.key ? "border-indigo-600 text-indigo-700 dark:text-indigo-300" : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"}`}><I size={15} /> {t.label}</button>
        ); })}
      </div>
      {tab === "overview" && <OverviewTab iid={id} />}
      {tab === "analytics" && <AnalyticsTab iid={id} />}
      {tab === "plan" && <PlanTab iid={id} onChanged={loadHead} />}
      {tab === "admins" && <AdminsTab iid={id} />}
      {tab === "activity" && <ActivityTab iid={id} />}
      {tab === "features" && <FeaturesTab id={id} />}
      {tab === "domain" && form && (
        <EditForm onSave={save} saving={saving}>
          <div className="grid sm:grid-cols-2 gap-4">{F("name", "Institution name")}{F("code", "Code")}{F("city", "City")}{F("contact_email", "Contact email", "email")}{F("phone", "Phone")}{F("domain", "Domain", "text", "greenwood.edu")}{F("slug", "URL slug", "text", "greenwood")}</div>
          <p className="text-xs text-slate-500">Domain auto-generates teacher & student login IDs (e.g. ravi.kumar@{form.domain || "greenwood.edu"}). Slug powers the branded login URL; lowercase letters, numbers and hyphens only.</p>
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 p-4 space-y-2"><Label>Branded login link</Label><LoginLink loginKey={form.slug || (form.code || "").toLowerCase() || form.domain} /></div>
        </EditForm>
      )}
      {tab === "branding" && form && (
        <EditForm onSave={save} saving={saving}>
          <div className="grid sm:grid-cols-2 gap-4">
            {F("portal_name", "Portal display name", "text", form.name)}
            <div className="space-y-1.5"><Label>Primary color</Label><div className="flex gap-2"><Input type="color" value={form.primary_color || "#4f46e5"} onChange={(e) => set("primary_color", e.target.value)} className="w-14 p-1 h-9" data-testid="inst-primary_color" /><Input value={form.primary_color || ""} onChange={(e) => set("primary_color", e.target.value)} placeholder="#4f46e5" /></div></div>
            <div className="sm:col-span-2">{F("logo_url", "Logo URL (if no uploaded logo)", "text", "https://…/logo.png")}</div>
          </div>
        </EditForm>
      )}
    </div>
  );
}
