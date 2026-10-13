import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  LogOut, Moon, Sun, User, CalendarCheck, Award, Trophy, Megaphone, Crown, Medal, Flame, History, Plus, Link2Off, X, Loader2, BookMarked, ClipboardCheck, Paperclip, Home, Users,
} from "lucide-react";
import { Reveal, AttendanceRing, QuickCard, PortalSkeleton, BottomNav, ResultTrends, pendingItems, nearestDue } from "../portal/PortalKit";import { toast } from "sonner";
import StudentFees from "../portal/StudentFees";
import api, { errText } from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../context/ThemeContext";
import { useReportIssue } from "../../context/ReportIssue";
import { MessageSquareWarning } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import HomeworkList from "../../components/homework/HomeworkList";
import AssignmentsList from "../../components/homework/AssignmentsList";

const API_BASE = process.env.REACT_APP_BACKEND_URL;

function LinkChildDialog({ onClose, onLinked }) {
  const [stage, setStage] = useState("details"); // details | code
  const [phone, setPhone] = useState("");
  const [adm, setAdm] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [err, setErr] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [cooldown, setCooldown] = useState(0);
  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const t = setInterval(() => setCooldown((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [cooldown]);
  const request = async () => {
    if (busy) return;
    setBusy(true); setErr("");
    try {
      const r = await api.post("/verify/request", { purpose: "parent_link", phone, admission_no: adm });
      if (r.data.sent === false) { setErr(r.data.message || "Couldn't send the code — check the details."); return; }
      setStage("code"); setCode(""); setSentTo(r.data.sent_to || ""); setCooldown(60); toast.success(r.data.message);
    } catch (e) { setErr("Something went wrong — try again."); } finally { setBusy(false); }
  };
  const confirm = useCallback(async (val) => {
    setConfirming(true); setErr("");
    try {
      await api.post("/verify/confirm", { purpose: "parent_link", phone, admission_no: adm, code: (val ?? "").toString() });
      toast.success("Child linked"); onLinked();
    } catch (e) { setErr(errText(e)); } finally { setConfirming(false); }
  }, [phone, adm, onLinked]);
  useEffect(() => {
    if (stage === "code" && code.length === 6 && !confirming) confirm(code);
  }, [code, stage, confirming, confirm]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" data-testid="link-child-dialog">
      <div className="w-full max-w-md rounded-3xl bg-white dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-800 shadow-2xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-white">Link a child</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" data-testid="link-child-close"><X size={18} /></button>
        </div>
        {stage === "details" ? (
          <>
            <p className="text-sm text-slate-500">Enter the phone number on your child's school record and their admission number. We'll email you a verification code.</p>
            <div className="space-y-2">
              <Input value={phone} onChange={(e) => { setPhone(e.target.value); setErr(""); }} placeholder="Guardian phone on record" data-testid="link-child-phone" />
              <Input value={adm} onChange={(e) => { setAdm(e.target.value); setErr(""); }} placeholder="Student admission number" data-testid="link-child-admission" />
            </div>
            {err && <p className="text-sm text-red-600 dark:text-red-400" data-testid="link-child-error">{err}</p>}
            <Button className="w-full" disabled={busy || !phone.trim() || !adm.trim()} onClick={request} data-testid="link-child-request-btn">
              {busy ? <span className="inline-flex items-center gap-2"><Loader2 className="animate-spin" size={15} /> Sending…</span> : "Send code"}
            </Button>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-500">Enter the 6-digit code sent to <span className="font-medium">{sentTo}</span>.</p>
            <Input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="Verification code" maxLength={6} inputMode="numeric" data-testid="link-child-code" />
            {err && <p className="text-sm text-red-600 dark:text-red-400" data-testid="link-child-error">{err}</p>}
            <div className="flex items-center justify-between">
              <button type="button" className="text-xs text-indigo-600 underline disabled:text-slate-400 disabled:no-underline" disabled={cooldown > 0 || busy} onClick={request} data-testid="link-child-resend">
                {cooldown > 0 ? `Resend in ${cooldown}s` : (busy ? "Sending…" : "Resend code")}
              </button>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" disabled={confirming} onClick={() => { setStage("details"); setErr(""); }} data-testid="link-child-back">Back</Button>
              <Button className="flex-1" disabled={confirming || code.length < 4} onClick={() => confirm(code)} data-testid="link-child-confirm-btn">
                {confirming ? <span className="inline-flex items-center gap-2"><Loader2 className="animate-spin" size={15} /> Linking…</span> : "Link child"}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function ParentPortal() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const { openReport } = useReportIssue();
  const navigate = useNavigate();
  const [children, setChildren] = useState(null);
  const [branding, setBranding] = useState({});
  const [selected, setSelected] = useState("");
  const [snap, setSnap] = useState(null);
  const [notices, setNotices] = useState([]);
  const [showLink, setShowLink] = useState(false);
  const [hw, setHw] = useState(null);
  const [asg, setAsg] = useState(null);

  const loadChildren = useCallback((selectFirst) => {
    api.get("/parent/children").then((r) => {
      setChildren(r.data.children);
      setBranding(r.data.branding || {});
      const want = new URLSearchParams(window.location.search).get("child") || sessionStorage.getItem("fee_link_child");
      sessionStorage.removeItem("fee_link_child");
      const hit = r.data.children.find((c) => c.id === want);
      if (hit) setSelected(hit.id);
      else if (selectFirst && r.data.children.length) setSelected(r.data.children[0].id);
    }).catch(() => setChildren([]));
  }, []);

  useEffect(() => {
    loadChildren(true);
    api.get("/notices/feed").then((r) => setNotices(r.data.notices || [])).catch(() => setNotices([]));
  }, [loadChildren]);

  const unlinkChild = async (id, name) => {
    if (!window.confirm(`Remove ${name} from your account? You can link again later.`)) return;
    try {
      await api.post(`/parent/unlink/${id}`);
      toast.success("Child unlinked");
      if (selected === id) setSelected("");
      loadChildren(true);
    } catch (err) { toast.error(errText(err)); }
  };

  const load = useCallback(() => {
    if (!selected) { setSnap(null); setHw(null); setAsg(null); return; }
    api.get(`/parent/child/${selected}`).then((r) => setSnap(r.data)).catch(() => setSnap(null));
    api.get(`/parent/child/${selected}/homework`).then((r) => setHw(r.data.homework)).catch(() => setHw([]));
    api.get(`/parent/child/${selected}/assignments`).then((r) => setAsg(r.data.assignments)).catch(() => setAsg([]));
  }, [selected]);
  useEffect(() => { load(); }, [load]);

  const handleLogout = async () => { await logout(); navigate("/login"); };
  const s = snap?.student;
  let streak = 0;
  for (const h of snap?.attendance_history || []) {
    if (String(h.status || "").toLowerCase().startsWith("p")) streak += 1; else break;
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#0B0F17]">
      <header className="h-16 flex items-center gap-3 px-4 md:px-8 border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl sticky top-0 z-20">
        {branding.logo_url || branding.has_logo
          ? <img src={branding.has_logo ? `${process.env.REACT_APP_BACKEND_URL}/api/public/institution-logo?domain=${encodeURIComponent(branding.domain || "")}` : branding.logo_url} alt="logo" className="h-8 w-8 rounded-lg object-cover" />
          : <div className="h-8 w-8 rounded-lg flex items-center justify-center font-heading font-bold text-white text-sm" style={{ background: branding.primary_color || "#4f46e5" }}>{(branding.portal_name || "L")[0]}</div>}
        <div className="flex-1">
          <p className="font-heading font-bold text-slate-900 dark:text-white leading-none">{branding.portal_name || "Parent Portal"}</p>
          <p className="text-[11px] text-slate-500 mt-0.5">Parent Portal · {user?.name}</p>
        </div>
        <button onClick={toggle} className="h-9 w-9 rounded-lg flex items-center justify-center text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" data-testid="parent-theme-toggle">
          {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
        </button>
        <Button variant="outline" size="sm" onClick={openReport} data-testid="parent-report-btn"><MessageSquareWarning size={14} className="mr-1.5" /> Report</Button>
        <Button variant="outline" size="sm" onClick={handleLogout} data-testid="parent-logout-btn"><LogOut size={14} className="mr-1.5" /> Sign out</Button>
      </header>

      <main className="max-w-4xl mx-auto px-4 md:px-8 py-8 pb-24 md:pb-10 space-y-6" data-testid="parent-portal">
        {children === null && <PortalSkeleton />}
        {children?.length === 0 && <div className="rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10 p-6 text-sm text-amber-800 dark:text-amber-200">No children are linked to your account yet. Use <span className="font-semibold">Link a child</span> below, or contact the school office.</div>}

        {children !== null && (
          <div id="parent-children" className="flex items-center justify-between gap-2 flex-wrap">
            {children?.length > 0 ? (
              <div className="flex gap-2 flex-wrap" data-testid="parent-child-switcher">
                {children.map((c) => (
                  <div key={c.id} className={`flex items-center gap-2 pl-3.5 pr-2 py-2 rounded-2xl border-2 text-sm font-semibold transition-colors ${selected === c.id ? "bg-indigo-600 text-white border-indigo-600" : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-indigo-400"}`}>
                    <button onClick={() => setSelected(c.id)} data-testid={`parent-child-${c.id}`} className="flex items-center gap-2">
                      <span className="h-7 w-7 rounded-xl bg-white/20 dark:bg-slate-800 flex items-center justify-center overflow-hidden">
                        {c.photo_path ? <img src={`${API_BASE}/api/students/${c.id}/photo`} alt="" className="h-full w-full object-cover" /> : <User size={13} className={selected === c.id ? "text-white" : "text-slate-400"} />}
                      </span>
                      {`${c.first_name || ""} ${c.last_name || ""}`.trim()}
                      <span className="text-[11px] opacity-70">{c.class_name}{c.section ? ` ${c.section}` : ""}</span>
                    </button>
                    <button onClick={() => unlinkChild(c.id, `${c.first_name || ""}`.trim())} title="Unlink" data-testid={`parent-unlink-${c.id}`}
                      className={`h-6 w-6 rounded-lg flex items-center justify-center ${selected === c.id ? "hover:bg-white/20" : "hover:bg-slate-100 dark:hover:bg-slate-800"}`}>
                      <Link2Off size={13} />
                    </button>
                  </div>
                ))}
              </div>
            ) : <span />}
            <Button size="sm" variant="outline" onClick={() => setShowLink(true)} data-testid="parent-link-child-btn"><Plus size={14} className="mr-1.5" /> Link a child</Button>
          </div>
        )}

        {s && (
          <>
            <div className="rounded-3xl p-6 text-white bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 dark:from-indigo-900 dark:via-purple-950 dark:to-slate-900 relative overflow-hidden" data-testid="parent-child-hero">
              <div className="absolute -top-8 -right-8 h-28 w-28 rounded-full bg-white/10" />
              <h1 className="font-heading text-2xl font-bold flex items-center gap-2 flex-wrap">
                {`${s.first_name || ""} ${s.last_name || ""}`.trim()}
                {snap.leader_role === "class_leader" && <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-400 text-amber-950"><Crown size={12} /> Class Leader</span>}
                {snap.leader_role === "second_leader" && <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-white/90 text-slate-800"><Medal size={12} /> Second Leader</span>}
              </h1>
              <p className="text-sm text-white/80 mt-1">{s.admission_no ? `Adm. ${s.admission_no} · ` : ""}{s.class_name}{s.section ? ` · Section ${s.section}` : ""}</p>
            </div>

            <Reveal className="grid grid-cols-2 sm:grid-cols-4 gap-4" data-testid="parent-stats">
              <QuickCard tone="emerald" icon={CalendarCheck} label="Attendance" value={snap.attendance.pct !== null ? `${snap.attendance.pct}%` : "—"} sub={snap.attendance.total ? `${snap.attendance.present}/${snap.attendance.total} days` : "No records yet"}><AttendanceRing pct={snap.attendance.pct} /></QuickCard>
              <QuickCard tone="indigo" icon={BookMarked} label="Homework due" value={hw ? pendingItems(hw).length : "—"} sub={hw && pendingItems(hw).length ? `Next: ${nearestDue(pendingItems(hw)) || "—"}` : "All caught up"} onClick={() => document.querySelector('[data-testid=parent-homework]')?.scrollIntoView({ behavior: "smooth" })} testid="parent-quick-homework" />
              <QuickCard tone="fuchsia" icon={ClipboardCheck} label="Assignments" value={asg ? pendingItems(asg).length : "—"} sub={asg && pendingItems(asg).length ? "pending to submit" : "nothing pending"} onClick={() => document.querySelector('[data-testid=parent-assignments]')?.scrollIntoView({ behavior: "smooth" })} testid="parent-quick-assignments" />
              <QuickCard tone="sky" icon={Award} label="Latest result" value={snap.results[0] ? `${snap.results[0].score ?? "—"}${snap.results[0].max_marks ? `/${snap.results[0].max_marks}` : ""}` : "—"} sub={snap.results[0]?.subject || snap.results[0]?.assessment || "No results yet"} onClick={() => document.querySelector('[data-testid=parent-results]')?.scrollIntoView({ behavior: "smooth" })} testid="parent-quick-results" />
            </Reveal>

            <Card title="Homework" icon={BookMarked} testid="parent-homework">
              <HomeworkList items={hw} />
            </Card>

            <Card title="Assignments" icon={ClipboardCheck} testid="parent-assignments">
              <AssignmentsList items={asg} />
            </Card>

            <StudentFees key={selected} endpoint={`/parent/child/${selected}/fees`} testid="parent-fees" parentChildId={selected} defaultOpen={new URLSearchParams(window.location.search).get("fees") === "1"} />

            <Card title="Results" icon={Award} testid="parent-results">
              {snap.results.length === 0 ? <Empty text="No published results yet." /> : (
                <>
                  <div className="px-4 pt-1 pb-3"><ResultTrends results={snap.results} testid="parent-trends" /></div>
                  <table className="w-full text-sm">
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                      {snap.results.map((r, i) => (
                        <tr key={i}>
                          <td className="px-6 py-3 text-slate-700 dark:text-slate-300">{r.assessment}</td>
                          <td className="px-6 py-3 text-slate-500">{r.subject || "—"}</td>
                          <td className="px-6 py-3 font-medium text-right text-slate-800 dark:text-slate-200">{r.score ?? "—"}{r.max_marks ? ` / ${r.max_marks}` : ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </Card>

            <Card title="Recent Attendance" icon={History} testid="parent-attendance">
              {snap.attendance_history.length === 0 ? <Empty text="No attendance records yet." /> : (
                <div className="px-6 py-4 flex flex-wrap gap-2">
                  {snap.attendance_history.map((h, i) => {
                    const st = String(h.status || "").toLowerCase();
                    const cls = st.startsWith("p") ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300"
                      : st.startsWith("l") ? "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300"
                      : "bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-300";
                    return <span key={i} className={`px-3 py-1 rounded-xl text-xs font-semibold ${cls}`}>{h.date} · {st.charAt(0).toUpperCase() + st.slice(1)}</span>;
                  })}
                </div>
              )}
            </Card>

            <Card title="Achievements" icon={Trophy} testid="parent-achievements">
              {snap.achievements.length === 0 ? <Empty text="No achievements yet." /> : (
                <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
                  {snap.achievements.map((a) => (
                    <li key={a.id} className="px-6 py-3 flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{a.title}</p>
                        {a.description && <p className="text-xs text-slate-500 mt-0.5">{a.description}</p>}
                      </div>
                      <span className="text-xs text-slate-400 whitespace-nowrap">{a.date || ""}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </>
        )}

        {notices.length > 0 && (
          <div id="parent-notices">
          <Card title="School Notices" icon={Megaphone} testid="parent-notices">
            <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {notices.map((n) => (
                <li key={n.id} className="px-6 py-3.5">
                  <div className="flex items-start justify-between gap-4">
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{n.title}</p>
                    <span className="text-xs text-slate-400 whitespace-nowrap">{(n.created_at || "").slice(0, 10)}</span>
                  </div>
                  {n.body && <p className="text-xs text-slate-500 mt-0.5 whitespace-pre-line">{n.body}</p>}
                  {n.attachments?.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-1.5">
                      {n.attachments.map((a, i) => (
                        <a key={i} href={`${process.env.REACT_APP_BACKEND_URL}/api/notices/attachment/${n.id}/${i}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:underline"><Paperclip size={11} /> {a.name}</a>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </Card>
          </div>
        )}
      </main>
      <BottomNav
        items={[
          { key: "top", label: "Home", icon: Home },
          { key: "children", label: "Children", icon: Users },
          { key: "notices", label: "Notices", icon: Megaphone },
        ]}
        active=""
        onSelect={(k) => {
          if (k === "top") window.scrollTo({ top: 0, behavior: "smooth" });
          else document.getElementById(`parent-${k}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}
      />
      {showLink && <LinkChildDialog onClose={() => setShowLink(false)} onLinked={() => { setShowLink(false); loadChildren(true); }} />}
    </div>
  );
}

const Card = ({ title, icon: Icon, children, testid }) => (
  <div className="rounded-3xl border-2 border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-md overflow-hidden" data-testid={testid}>
    <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
      <Icon size={17} className="text-indigo-600" />
      <h2 className="font-heading text-lg font-bold text-slate-900 dark:text-slate-50">{title}</h2>
    </div>
    {children}
  </div>
);
const Empty = ({ text }) => <p className="px-6 py-6 text-sm text-slate-400">{text}</p>;
const Stat = ({ icon: Icon, label, value, sub }) => (
  <div className="rounded-2xl border-2 border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm">
    <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-400"><Icon size={14} /> {label}</div>
    <p className="mt-1.5 font-heading text-2xl font-bold text-slate-900 dark:text-slate-50">{value}</p>
    {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
  </div>
);
