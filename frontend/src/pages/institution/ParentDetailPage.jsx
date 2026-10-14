import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ChevronRight, Phone, Mail, Pencil, Users2, Wallet, Send, History, MessageSquare, Link2Off, Plus, UserCircle2 } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { AccountLock } from "../../components/common/AccountLock";
import { ResetPasswordButton } from "../../components/common/ResetPasswordDialog";
import ChatThread from "../../components/chat/ChatThread";
import { staffBase, StatusPill } from "./ParentsPage";

const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN")}`;
const day = (iso, tz) => (iso ? new Intl.DateTimeFormat("en-IN", { timeZone: tz, day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(iso)) : "—");

const Panel = ({ icon: Icon, title, right, children, testid }) => (
  <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden" data-testid={testid}>
    <div className="px-5 py-3.5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between gap-3">
      <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Icon size={15} className="text-indigo-600" /> {title}</h2>{right}
    </div>
    {children}
  </div>
);

function EditDialog({ p, open, onClose, onSaved }) {
  const [f, setF] = useState({});
  useEffect(() => { if (open) setF({ name: p.name || "", phone: p.phone || "", email: p.email || "", relation: p.relation || "", preferred_channel: p.preferred_channel || "" }); }, [open, p]);
  const save = async () => {
    const body = {};
    ["name", "relation", "preferred_channel"].forEach((k) => { if ((f[k] || "") !== (p[k] || "")) body[k] = f[k]; });
    if (f.phone !== (p.phone || "")) body.phone = f.phone;
    if (f.email && f.email !== (p.email || "")) body.email = f.email;
    if (body.email && !window.confirm(`Change the login email to ${body.email}? Both the old and new address will be emailed.`)) return;
    try {
      const { data } = await api.patch(`/parents/${p.id}`, body);
      const n = Object.entries(data.notifications || {});
      toast.success(data.changed.length ? `Saved${n.length ? ` · notified ${n.map(([a, r]) => `${a} (${r.message_id ? "sent" : r.error})`).join(", ")}` : ""}` : "Nothing changed");
      onSaved(); onClose();
    } catch (e) { toast.error(errText(e)); }
  };
  const set = (k) => (e) => setF({ ...f, [k]: e.target ? e.target.value : e });
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="parent-edit-dialog">
        <DialogHeader><DialogTitle>Edit parent</DialogTitle><DialogDescription>Changes are audited. Phone and email must be unique.</DialogDescription></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1"><Label>Name</Label><Input value={f.name || ""} onChange={set("name")} data-testid="parent-edit-name" /></div>
          <div className="space-y-1"><Label>Mobile</Label><Input value={f.phone || ""} onChange={set("phone")} data-testid="parent-edit-phone" /></div>
          <div className="space-y-1"><Label>Email (login)</Label><Input type="email" value={f.email || ""} onChange={set("email")} data-testid="parent-edit-email" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1"><Label>Relation</Label>
              <Select value={f.relation || "none"} onValueChange={(v) => setF({ ...f, relation: v === "none" ? "" : v })}>
                <SelectTrigger data-testid="parent-edit-relation"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="none">—</SelectItem>{["father", "mother", "guardian", "grandparent", "other"].map((r) => <SelectItem key={r} value={r} className="capitalize">{r}</SelectItem>)}</SelectContent>
              </Select></div>
            <div className="space-y-1"><Label>Preferred channel</Label>
              <Select value={f.preferred_channel || "auto"} onValueChange={(v) => setF({ ...f, preferred_channel: v === "auto" ? "" : v })}>
                <SelectTrigger data-testid="parent-edit-channel"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="auto">Automatic</SelectItem><SelectItem value="whatsapp">WhatsApp</SelectItem><SelectItem value="sms">SMS</SelectItem><SelectItem value="email">Email</SelectItem></SelectContent>
              </Select></div>
          </div>
          <div className="flex justify-end gap-2 pt-1"><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={save} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="parent-edit-save">Save</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function LinkChild({ pid, onDone }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [rows, setRows] = useState(null);
  useEffect(() => {
    if (!open) return undefined;
    const t = setTimeout(() => {
      if (!q.trim()) return setRows(null);
      api.get(`/parents/${pid}/link-candidates`, { params: { q } }).then((r) => setRows(r.data.results)).catch((e) => toast.error(errText(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [q, open, pid]);
  const link = async (s) => {
    if (!window.confirm(`Link ${s.name} (${s.admission_no || "no adm. no"}, ${s.class_name || "not enrolled"}) to this parent?`)) return;
    try { await api.post(`/parents/${pid}/children`, { student_id: s.id }); toast.success("Child linked"); setOpen(false); setQ(""); onDone(); }
    catch (e) { toast.error(errText(e)); }
  };
  return (
    <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800">
      <Button size="sm" variant="outline" onClick={() => setOpen(true)} data-testid="parent-link-child-btn"><Plus size={13} className="mr-1" /> Link child</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg" data-testid="link-child-dialog">
          <DialogHeader><DialogTitle>Link a child</DialogTitle><DialogDescription>Search by admission number (full or part, e.g. "SPS-001", "sps 001", "001") or by name.</DialogDescription></DialogHeader>
          <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Admission no. or student name" data-testid="link-child-search" />
          <ul className="max-h-80 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800 -mx-1" data-testid="link-child-results">
            {rows?.length === 0 && <li className="py-6 text-center text-sm text-slate-400" data-testid="link-child-empty">No students match.</li>}
            {rows?.map((s) => (
              <li key={s.id} className="px-1 py-2.5 flex items-center justify-between gap-3 text-sm" data-testid={`link-child-row-${s.id}`}>
                <div className="min-w-0">
                  <p className="font-medium text-slate-800 dark:text-slate-100">{s.name} <span className="font-mono text-xs text-indigo-700 dark:text-indigo-300">{s.admission_no || "—"}</span></p>
                  <p className="text-xs text-slate-500">{s.class_name ? `${s.class_name}${s.section ? ` · ${s.section}` : ""}` : "Not enrolled"}
                    {" · "}{s.parents.length ? `Parents: ${s.parents.map((x) => x.name).join(", ")}` : "No parent linked"}</p>
                </div>
                {s.already_linked ? <span className="text-xs font-semibold text-emerald-700 shrink-0" data-testid={`link-child-linked-${s.id}`}>Already linked</span>
                  : <Button size="sm" onClick={() => link(s)} className="bg-indigo-700 hover:bg-indigo-800 text-white shrink-0" data-testid={`link-child-pick-${s.id}`}>Link</Button>}
              </li>
            ))}
          </ul>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Conversations({ d, reload }) {
  const [sel, setSel] = useState(d.threads[0]?.id || null);
  const start = async (c) => {
    try {
      const fd = new FormData(); fd.append("student_id", c.id); fd.append("parent_id", d.parent.id);
      const { data } = await api.post("/chat/threads", fd);
      setSel(data.thread.id); reload();
    } catch (e) { toast.error(errText(e)); }
  };
  return (
    <Panel icon={MessageSquare} title="Messages" testid="parent-chat-panel"
      right={<div className="flex gap-1.5 flex-wrap">{d.children.map((c) => <Button key={c.id} size="sm" variant="outline" onClick={() => start(c)} data-testid={`parent-message-${c.id}`}><Send size={12} className="mr-1" /> Message about {c.name.split(" ")[0]}</Button>)}</div>}>
      <div className="p-4 grid md:grid-cols-[220px_1fr] gap-4">
        <ul className="space-y-1" data-testid="parent-thread-list">
          {d.threads.length === 0 && <li className="text-sm text-slate-400">No conversations yet.</li>}
          {d.threads.map((t) => (
            <li key={t.id}><button onClick={() => setSel(t.id)} className={`w-full text-left rounded-lg px-3 py-2 text-sm ${sel === t.id ? "bg-indigo-50 dark:bg-indigo-500/10" : "hover:bg-slate-50 dark:hover:bg-slate-800"}`} data-testid={`parent-thread-${t.id}`}>
              <span className="font-medium text-slate-800 dark:text-slate-100">{t.student_name}</span> <span className="text-[11px] text-slate-400">{t.status}</span>
              {t.unread > 0 && <span className="ml-1 rounded-full bg-rose-500 text-white text-[10px] px-1.5">{t.unread}</span>}
              <p className="text-xs text-slate-500 truncate">{t.last_message_preview || "—"}</p>
            </button></li>
          ))}
        </ul>
        {sel ? <ChatThread threadId={sel} onChanged={reload} height="h-[360px]" /> : <p className="text-sm text-slate-400 py-10 text-center">Pick a child above to start a conversation.</p>}
      </div>
    </Panel>
  );
}

export default function ParentDetailPage() {
  const { id } = useParams();
  const { pathname } = useLocation();
  const base = staffBase(pathname);
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const [edit, setEdit] = useState(false);
  const load = useCallback(() => api.get(`/parents/${id}`).then((r) => setD(r.data)).catch((e) => setErr(errText(e))), [id]);
  useEffect(() => { load(); }, [load]);
  const unlink = async (c) => {
    if (!window.confirm(`Unlink ${c.name} from ${d.parent.name}? The parent will no longer see this child.`)) return;
    try { await api.post(`/parents/${id}/children/${c.id}/unlink`); toast.success("Child unlinked"); load(); } catch (e) { toast.error(errText(e)); }
  };
  if (err) return <p className="py-16 text-center text-slate-400" data-testid="parent-detail-error">{err}</p>;
  if (!d) return <p className="py-16 text-center text-sm text-slate-400">Loading…</p>;
  const p = d.parent;
  const tz = d.timezone;
  return (
    <div className="space-y-6" data-testid="parent-detail-page">
      <nav className="flex items-center gap-1.5 text-sm text-slate-500">
        <Link to={`${base}/parents`} className="text-indigo-600 dark:text-indigo-400 hover:underline" data-testid="back-to-parents">Parents</Link><ChevronRight size={14} />
        <span className="text-slate-700 dark:text-slate-200 font-medium">{p.name}</span>
      </nav>
      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 flex items-start justify-between gap-5 flex-wrap" data-testid="parent-hero">
        <div className="flex items-center gap-4 min-w-0">
          <div className="h-16 w-16 rounded-full bg-indigo-600 text-white flex items-center justify-center shrink-0"><UserCircle2 size={30} /></div>
          <div className="min-w-0">
            <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2 flex-wrap" data-testid="parent-name">{p.name} <StatusPill s={d.onboarding.status} /></h1>
            <p className="text-sm text-slate-500 mt-1"><span className="capitalize">{p.relation || "Parent / guardian"}</span> · last sign-in {d.last_login ? day(d.last_login, tz) : "never"}{p.account_status !== "active" ? ` · ${p.account_status}` : ""}</p>
            <div className="flex flex-wrap gap-2 mt-3">
              {p.phone && <a href={`tel:+91${p.phone}`} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-sm" data-testid="parent-call"><Phone size={14} /> {p.phone}</a>}
              {p.email && <a href={`mailto:${p.email}`} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-sm" data-testid="parent-email"><Mail size={14} /> {p.email}</a>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <AccountLock userId={p.id} />
          <ResetPasswordButton userId={p.id} name={p.name} hasEmail={Boolean(p.email)} />
          {d.can_edit && <Button variant="outline" onClick={() => setEdit(true)} data-testid="parent-edit-btn"><Pencil size={14} className="mr-1.5" /> Edit</Button>}
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <Panel icon={Users2} title="Children" testid="parent-children">
          <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {d.children.map((c) => (
              <li key={c.id} className="px-5 py-3 flex items-start justify-between gap-3" data-testid={`parent-child-${c.id}`}>
                <div className="min-w-0">
                  <Link to={base === "/app" ? `/app/students/${c.id}` : `${base}/students`} className="font-medium text-indigo-700 dark:text-indigo-400 hover:underline" data-testid={`parent-child-open-${c.id}`}>{c.name}</Link>
                  <p className="text-xs text-slate-500">{c.class_name}{c.section ? ` · ${c.section}` : ""}{c.admission_no ? ` · Adm. ${c.admission_no}` : ""}</p>
                  <p className="text-xs mt-1 flex items-center gap-1.5 flex-wrap" data-testid={`parent-child-fees-${c.id}`}>
                    <Wallet size={12} className="text-slate-400" /> Outstanding <b>{inr(c.fees.outstanding)}</b>
                    {c.fees.overdue_amount > 0 && <span className="text-rose-600 font-semibold">· {inr(c.fees.overdue_amount)} overdue</span>}
                    <span className="text-slate-400">· last payment {c.fees.last_payment ? `${inr(c.fees.last_payment.amount)} on ${c.fees.last_payment.at?.slice(0, 10)}` : "none"}</span>
                  </p>
                </div>
                {d.can_edit && <button onClick={() => unlink(c)} className="text-xs text-red-600 inline-flex items-center gap-1 shrink-0" data-testid={`parent-unlink-${c.id}`}><Link2Off size={12} /> Unlink</button>}
              </li>
            ))}
            {d.children.length === 0 && <li className="px-5 py-6 text-sm text-slate-400">No linked children.</li>}
          </ul>
          {d.can_edit && <LinkChild pid={p.id} onDone={load} />}
        </Panel>
        <Panel icon={Send} title="Onboarding" testid="parent-onboarding">
          <dl className="px-5 py-3 text-sm divide-y divide-slate-100 dark:divide-slate-800/60">
            <div className="py-2 flex justify-between"><dt className="text-slate-400">Method</dt><dd className="font-medium first-letter:uppercase" data-testid="parent-onboarding-method">{d.onboarding.method}</dd></div>
            <div className="py-2 flex justify-between"><dt className="text-slate-400">First invited</dt><dd className="font-medium">{day(d.onboarding.invited_at, tz)}</dd></div>
            <div className="py-2 flex justify-between"><dt className="text-slate-400">Account created</dt><dd className="font-medium">{day(p.created_at, tz)}</dd></div>
            <div className="py-2 flex justify-between"><dt className="text-slate-400">Login</dt><dd className="font-medium text-xs">{p.login_email}</dd></div>
          </dl>
          {d.onboarding.events.length > 0 && (
            <ul className="px-5 pb-3 text-xs text-slate-500 space-y-0.5">{d.onboarding.events.map((e, i) => <li key={i}>{day(e.at, tz)} · {e.channel} · {e.status}</li>)}</ul>
          )}
        </Panel>
      </div>

      <Conversations key={d.threads.length} d={d} reload={load} />

      <Panel icon={History} title="Communication history" testid="parent-comms">
        {d.communications.length === 0 ? <p className="px-5 py-6 text-sm text-slate-400">Nothing sent to this parent yet.</p> : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {d.communications.map((m) => (
              <li key={m.id} className="px-5 py-2.5 text-sm flex items-start justify-between gap-3" data-testid={`parent-comm-${m.id}`}>
                <div className="min-w-0"><p className="text-slate-700 dark:text-slate-200 truncate">{m.body}</p><p className="text-xs text-slate-400">{day(m.created_at, tz)} · {(m.module || "").replace(/_/g, " ")}{m.provider_message_id ? ` · id ${m.provider_message_id.slice(0, 8)}…` : ""}</p></div>
                <span className="text-xs shrink-0"><span className="uppercase font-semibold text-slate-500">{m.channel}</span> · <span className={m.status === "failed" ? "text-rose-600" : "text-emerald-700"}>{m.status}</span></span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <EditDialog p={p} open={edit} onClose={() => setEdit(false)} onSaved={load} />
    </div>
  );
}
