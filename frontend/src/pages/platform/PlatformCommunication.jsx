import { useCallback, useEffect, useState } from "react";
import { MessageSquare, Send, Save, Check, X, Inbox, Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Switch } from "../../components/ui/switch";

export default function PlatformCommunication() {
  const [cfg, setCfg] = useState(null);
  const [schools, setSchools] = useState([]);
  const [reqs, setReqs] = useState([]);

  const load = useCallback(() => {
    api.get("/platform/comm-config").then((r) => setCfg(r.data)).catch(() => {});
    api.get("/platform/comm/schools").then((r) => setSchools(r.data.schools)).catch(() => {});
    api.get("/platform/comm/requests").then((r) => setReqs(r.data.requests)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6" data-testid="platform-comm-page">
      <div>
        <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2"><MessageSquare className="text-emerald-600" size={24} /> Communication</h1>
        <p className="text-sm text-slate-500 mt-1">Twilio provider config, channel toggles, per-school quotas and credit requests.</p>
      </div>
      {cfg && <TwilioCard cfg={cfg} onSaved={load} />}
      <TemplatesCard />
      <SchoolsTable schools={schools} onSaved={load} />
      <RequestsInbox reqs={reqs} onDecided={load} />
    </div>
  );
}

function TwilioCard({ cfg, onSaved }) {
  const [f, setF] = useState({ account_sid: "", auth_token: "", whatsapp_sender: cfg.twilio.whatsapp_sender, sms_sender: cfg.twilio.sms_sender });
  const [provider, setProvider] = useState(cfg.active_provider);
  const [ch, setCh] = useState(cfg.channels);
  const [busy, setBusy] = useState(false);
  const [testPhone, setTestPhone] = useState("");

  const save = async () => {
    setBusy(true);
    try {
      const payload = { ...f, active_provider: provider, sms_enabled: ch.sms_enabled, whatsapp_enabled: ch.whatsapp_enabled };
      await api.put("/platform/comm-config", payload);
      toast.success("Communication config saved"); onSaved();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const test = async () => {
    if (!testPhone.trim()) { toast.error("Enter a test number"); return; }
    try { const r = await api.post("/platform/comm-test", { channel: "whatsapp", phone: testPhone }); toast.success(`Test via ${r.data.provider}: ${r.data.status}${r.data.test_mode ? " (test mode)" : ""}`); }
    catch (e) { toast.error(errText(e)); }
  };

  return (
    <Card title="Twilio provider" icon={ShieldCheck} testid="comm-twilio-card">
      <div className="p-5 space-y-4">
        <div className="grid sm:grid-cols-2 gap-3">
          <Field label="Account SID" placeholder={cfg.twilio.account_sid || "AC…"} value={f.account_sid} onChange={(v) => setF({ ...f, account_sid: v })} testid="twilio-sid" />
          <Field label="Auth Token" placeholder={cfg.twilio.auth_token || "••••"} value={f.auth_token} onChange={(v) => setF({ ...f, auth_token: v })} testid="twilio-token" />
          <Field label="WhatsApp sender" placeholder="+1…" value={f.whatsapp_sender} onChange={(v) => setF({ ...f, whatsapp_sender: v })} testid="twilio-wa" />
          <Field label="SMS sender" placeholder="+1…" value={f.sms_sender} onChange={(v) => setF({ ...f, sms_sender: v })} testid="twilio-sms" />
        </div>
        <p className="text-xs text-slate-400">Secrets are masked after saving. Leave a field blank to keep the current value.</p>
        <div className="flex flex-wrap items-center gap-6">
          <label className="flex items-center gap-2 text-sm"><Switch checked={ch.whatsapp_enabled} onCheckedChange={(v) => setCh({ ...ch, whatsapp_enabled: v })} data-testid="toggle-wa" /> WhatsApp enabled</label>
          <label className="flex items-center gap-2 text-sm"><Switch checked={ch.sms_enabled} onCheckedChange={(v) => setCh({ ...ch, sms_enabled: v })} data-testid="toggle-sms" /> SMS enabled</label>
          <label className="flex items-center gap-2 text-sm">Active provider:
            <select className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm" value={provider} onChange={(e) => setProvider(e.target.value)} data-testid="active-provider">
              <option value="stub">Stub (Test Mode)</option>
              <option value="twilio">Twilio (Live)</option>
            </select>
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={save} disabled={busy} data-testid="comm-config-save">{busy ? <Loader2 className="animate-spin" size={16} /> : <><Save size={15} className="mr-1.5" /> Save config</>}</Button>
          <div className="flex items-center gap-2 ml-auto">
            <Input placeholder="Test phone +1…" value={testPhone} onChange={(e) => setTestPhone(e.target.value)} className="w-44" data-testid="comm-test-phone" />
            <Button variant="outline" onClick={test} data-testid="comm-test-send"><Send size={14} className="mr-1.5" /> Send test</Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

function SchoolsTable({ schools, onSaved }) {
  return (
    <Card title="Schools — usage & quotas" icon={MessageSquare} testid="comm-schools-card">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-400"><tr>
            <th className="px-5 py-2">School</th><th className="px-3 py-2">Mode</th><th className="px-3 py-2">WhatsApp</th><th className="px-3 py-2">SMS</th><th className="px-3 py-2"></th>
          </tr></thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {schools.map((s) => <SchoolRow key={s.id} s={s} onSaved={onSaved} />)}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function SchoolRow({ s, onSaved }) {
  const [wa, setWa] = useState(s.quota.whatsapp.limit);
  const [sms, setSms] = useState(s.quota.sms.limit);
  const [mode, setMode] = useState(s.sender_mode);
  const save = async () => {
    try { await api.put(`/platform/comm/schools/${s.id}`, { whatsapp_limit: Number(wa), sms_limit: Number(sms), sender_mode: mode }); toast.success("Updated"); onSaved(); }
    catch (e) { toast.error(errText(e)); }
  };
  const bar = (q) => `${q.used}/${q.limit}`;
  return (
    <tr data-testid={`comm-school-${s.id}`}>
      <td className="px-5 py-2.5 font-medium text-slate-800 dark:text-slate-200">{s.name}</td>
      <td className="px-3 py-2.5">
        <select className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1.5 py-1 text-xs" value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="lnmo">LNMO</option><option value="own">Own</option>
        </select>
      </td>
      <td className="px-3 py-2.5"><span className="text-xs text-slate-400 mr-2">{bar(s.quota.whatsapp)}</span><Input type="number" value={wa} onChange={(e) => setWa(e.target.value)} className="w-20 h-8 inline-block" data-testid={`wa-limit-${s.id}`} /></td>
      <td className="px-3 py-2.5"><span className="text-xs text-slate-400 mr-2">{bar(s.quota.sms)}</span><Input type="number" value={sms} onChange={(e) => setSms(e.target.value)} className="w-20 h-8 inline-block" data-testid={`sms-limit-${s.id}`} /></td>
      <td className="px-3 py-2.5"><Button size="sm" variant="outline" onClick={save} data-testid={`save-school-${s.id}`}><Save size={13} /></Button></td>
    </tr>
  );
}

function RequestsInbox({ reqs, onDecided }) {
  const decide = async (id, action) => {
    try { await api.post(`/platform/comm/requests/${id}/${action}`); toast.success(action === "approve" ? "Approved — quota increased" : "Rejected"); onDecided(); }
    catch (e) { toast.error(errText(e)); }
  };
  return (
    <Card title="Credit requests" icon={Inbox} testid="comm-requests-card">
      {reqs.length === 0 ? <p className="px-5 py-6 text-sm text-slate-400">No pending requests.</p> : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
          {reqs.map((r) => (
            <li key={r.id} className="px-5 py-3 flex items-center justify-between gap-3" data-testid={`comm-request-${r.id}`}>
              <div>
                <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{r.institution_name} · +{r.requested_additional} {r.channel}</p>
                <p className="text-xs text-slate-500">current {r.current_used}/{r.current_limit}{r.note ? ` · "${r.note}"` : ""}</p>
              </div>
              <div className="flex gap-1.5">
                <Button size="sm" onClick={() => decide(r.id, "approve")} data-testid={`approve-${r.id}`}><Check size={14} className="mr-1" /> Approve</Button>
                <Button size="sm" variant="outline" onClick={() => decide(r.id, "reject")} data-testid={`reject-${r.id}`}><X size={14} /></Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function TemplatesCard() {
  const [rows, setRows] = useState([]);
  const [draft, setDraft] = useState({ name: "", category: "announcement", channel: "both", body: "" });
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => { api.get("/platform/comm/templates").then((r) => setRows(r.data.templates)).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  const create = async () => {
    if (!draft.name.trim() || !draft.body.trim()) { toast.error("Name and body required"); return; }
    setBusy(true);
    try { await api.post("/platform/comm/templates", draft); toast.success("Template added"); setDraft({ name: "", category: "announcement", channel: "both", body: "" }); load(); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const setStatus = async (id, status) => {
    try { await api.put(`/platform/comm/templates/${id}`, { status }); toast.success("Updated"); load(); }
    catch (e) { toast.error(errText(e)); }
  };
  const chip = { approved: "bg-emerald-100 text-emerald-700", pending: "bg-amber-100 text-amber-700", disabled: "bg-slate-200 text-slate-500" };
  return (
    <Card title="Global message templates" icon={MessageSquare} testid="comm-templates-card">
      <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
        {rows.map((t) => (
          <li key={t.id} className="px-5 py-3 flex items-start justify-between gap-3" data-testid={`template-${t.id}`}>
            <div className="min-w-0">
              <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{t.name} <span className="text-xs text-slate-400">· {t.category} · {t.channel}</span></p>
              <p className="text-xs text-slate-500 truncate">{t.body}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={`text-[10px] font-bold uppercase rounded-full px-2 py-0.5 ${chip[t.status] || chip.pending}`}>{t.status}</span>
              <select className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1.5 py-1 text-xs" value={t.status} onChange={(e) => setStatus(t.id, e.target.value)} data-testid={`template-status-${t.id}`}>
                <option value="approved">approved</option><option value="pending">pending</option><option value="disabled">disabled</option>
              </select>
            </div>
          </li>
        ))}
      </ul>
      <div className="px-5 py-4 border-t border-slate-100 dark:border-slate-800 space-y-2">
        <div className="grid sm:grid-cols-3 gap-2">
          <Input placeholder="Template name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} data-testid="new-template-name" />
          <select className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 text-sm" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })} data-testid="new-template-category">
            {["announcement", "exam", "homework", "fee", "attendance", "general"].map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 text-sm" value={draft.channel} onChange={(e) => setDraft({ ...draft, channel: e.target.value })} data-testid="new-template-channel">
            {["both", "whatsapp", "sms"].map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <Input placeholder="Body — use {{parent_name}}, {{student_name}}, {{class}}, {{exam_name}}…" value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} data-testid="new-template-body" />
        <Button size="sm" onClick={create} disabled={busy} data-testid="new-template-create">{busy ? <Loader2 className="animate-spin" size={14} /> : "Add template"}</Button>
      </div>
    </Card>
  );
}

function Field({ label, value, onChange, placeholder, testid }) {
  return (
    <div>
      <label className="text-xs font-medium text-slate-400 block mb-1">{label}</label>
      {placeholder && placeholder.includes("•") && (
        <span className="inline-block mb-1 text-[10px] font-mono rounded bg-slate-100 dark:bg-slate-800 text-slate-500 px-1.5 py-0.5" data-testid={`${testid}-current`}>saved: {placeholder}</span>
      )}
      <Input value={value} placeholder={placeholder ? `Keep current (${placeholder})` : ""} onChange={(e) => onChange(e.target.value)} data-testid={testid} />
    </div>
  );
}
function Card({ title, icon: Icon, children, testid }) {
  return (
    <div className="rounded-3xl border-2 border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-md overflow-hidden" data-testid={testid}>
      <div className="px-5 py-3.5 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
        <Icon size={16} className="text-emerald-600" />
        <h2 className="font-heading text-base font-bold text-slate-900 dark:text-slate-50">{title}</h2>
      </div>
      {children}
    </div>
  );
}
