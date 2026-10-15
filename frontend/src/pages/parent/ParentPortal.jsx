import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Home, CalendarClock, BookMarked, CalendarCheck, Award, Wallet, Megaphone, Trophy, User, Users, LifeBuoy, Crown, Medal,
  ChevronDown, Link2Off, Plus, AlertTriangle, ClipboardCheck, ArrowRight, Check, MessageSquare,
} from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { useReportIssue } from "../../context/ReportIssue";
import { Button } from "../../components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../../components/ui/dropdown-menu";
import StudentFees from "../portal/StudentFees";
import HomeworkList from "../../components/homework/HomeworkList";
import AssignmentsList from "../../components/homework/AssignmentsList";
import AttendanceCalendar from "../portal/AttendanceCalendar";
import PortalShell, { PCard, PEmpty } from "../portal/PortalShell";
import { useSchoolBrand } from "../portal/useSchoolBrand";
import { TodayList, WeekGrid, NoticesList, ExamsList, ResultsBlock, Field, Chips, filterWork } from "../portal/PortalBlocks";
import { pendingItems } from "../portal/PortalKit";
import { LinkChildDialog } from "./LinkChildDialog";
import ParentMessages from "./ParentMessages";
import { Avatar as Photo } from "../../components/common/Avatar";

const API_BASE = process.env.REACT_APP_BACKEND_URL;
const NAV = [
  { key: "home", label: "Home", icon: Home },
  { key: "timetable", label: "Timetable", short: "Timetable", icon: CalendarClock },
  { key: "homework", label: "Homework", icon: BookMarked },
  { key: "attendance", label: "Attendance", icon: CalendarCheck },
  { key: "results", label: "Results", icon: Award },
  { key: "fees", label: "Fees", icon: Wallet },
  { key: "messages", label: "Messages", icon: MessageSquare },
  { key: "notices", label: "Notices", icon: Megaphone },
  { key: "achievements", label: "Achievements", icon: Trophy },
  { key: "profile", label: "Child profile", icon: User },
  { key: "account", label: "My account", icon: Users },
  { key: "support", label: "Support", icon: LifeBuoy },
];
const BOTTOM = ["home", "timetable", "attendance", "fees"];
const iso = (d) => d.toISOString().slice(0, 10);
const fullName = (c) => `${c?.first_name || ""} ${c?.last_name || ""}`.trim();

export default function ParentPortal() {
  const { "*": rest = "" } = useParams();
  const page = rest.split("/")[0];
  const { search } = useLocation();
  const navigate = useNavigate();
  const qs = new URLSearchParams(search);
  const brand = useSchoolBrand("Parent Portal");
  const [children, setChildren] = useState(null);
  const [showLink, setShowLink] = useState(false);
  const childParam = qs.get("child");

  const loadChildren = useCallback(() => {
    api.get("/parent/children").then((r) => setChildren(r.data.children)).catch(() => setChildren([]));
  }, []);
  useEffect(() => { loadChildren(); }, [loadChildren]);

  // ensure ?child= is always a linked child (fee links store it in sessionStorage)
  useEffect(() => {
    if (!children?.length || !page) return;
    if (children.some((c) => c.id === childParam)) return;
    const want = sessionStorage.getItem("fee_link_child");
    sessionStorage.removeItem("fee_link_child");
    const pick = children.find((c) => c.id === want) || children[0];
    const keep = new URLSearchParams(search);
    keep.set("child", pick.id);
    navigate(`/parents/${page}?${keep.toString()}`, { replace: true });
  }, [children, childParam, page, navigate, search]);

  if (!page || !NAV.some((n) => n.key === page)) {
    const target = qs.get("fees") === "1" ? "fees" : "home";
    return <Navigate to={`/parents/${target}${childParam ? `?child=${childParam}` : ""}`} replace />;
  }
  const selected = children?.find((c) => c.id === childParam)?.id || "";
  const query = selected ? `?child=${selected}` : "";
  const switcher = children?.length ? (
    <ChildSwitcher kids={children} selected={selected} onPick={(id) => navigate(`/parents/${page}?child=${id}`)} />
  ) : null;
  return (
    <PortalShell brand={brand} label="Parent Portal" nav={NAV} bottom={BOTTOM} base="/parents" query={query} extra={switcher} testid="parent-portal">
      {children === null && <div className="h-40 rounded-2xl bg-slate-200/60 dark:bg-slate-800 animate-pulse" />}
      {children?.length === 0 && !["account", "support", "messages"].includes(page) && (
        <PCard testid="parent-no-children"><PEmpty icon={Users} text="No children are linked to your account yet. Link a child from My account, or contact the school office." /></PCard>
      )}
      {page === "messages" ? (children && <ParentMessages kids={children} childId={selected} />) : (page === "account" || page === "support") ? (
        page === "account"
          ? <Account kids={children || []} onLink={() => setShowLink(true)} onChanged={loadChildren} />
          : <Support />
      ) : selected && <ChildPages key={selected} page={page} childId={selected} go={(k) => navigate(`/parents/${k}?child=${selected}`)} />}
      {showLink && <LinkChildDialog onClose={() => setShowLink(false)} onLinked={() => { setShowLink(false); loadChildren(); }} />}
    </PortalShell>
  );
}

function ChildSwitcher({ kids, selected, onPick }) {
  const cur = kids.find((c) => c.id === selected) || kids[0];
  const Avatar = ({ c }) => (
    <span className="h-7 w-7 rounded-full bg-[var(--brand-soft)] text-[var(--brand-ink)] flex items-center justify-center overflow-hidden shrink-0 text-xs font-bold">
      {c.thumb_url ? <img src={c.thumb_url} alt="" className="h-full w-full object-cover" /> : c.photo_path ? <img src={`${API_BASE}/api/students/${c.id}/photo`} alt="" className="h-full w-full object-cover" /> : (c.first_name || "?")[0]}
    </span>
  );
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex items-center gap-2 rounded-full border border-slate-200 dark:border-slate-700 pl-1 pr-2.5 py-1 max-w-[46vw] hover:border-[var(--brand-line)]" data-testid="parent-child-switcher">
          <Avatar c={cur} />
          <span className="text-left min-w-0 hidden sm:block">
            <span className="block text-xs font-semibold text-slate-800 dark:text-slate-100 truncate">{fullName(cur)}</span>
            <span className="block text-[10px] text-slate-500">{cur.class_name}{cur.section ? ` ${cur.section}` : ""}</span>
          </span>
          <span className="sm:hidden text-xs font-semibold text-slate-800 dark:text-slate-100 truncate">{cur.first_name}</span>
          <ChevronDown size={14} className="text-slate-400 shrink-0" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        {kids.map((c) => (
          <DropdownMenuItem key={c.id} onSelect={() => onPick(c.id)} data-testid={`parent-child-${c.id}`} className="gap-2">
            <Avatar c={c} />
            <span className="flex-1 min-w-0"><span className="block text-sm font-medium truncate">{fullName(c)}</span><span className="block text-[11px] text-slate-500">{c.class_name}{c.section ? ` ${c.section}` : ""}</span></span>
            {c.id === selected && <Check size={14} />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ChildPages({ page, childId, go }) {
  const [snap, setSnap] = useState(null);
  const [tt, setTt] = useState(null);
  const [hw, setHw] = useState(null);
  const [asg, setAsg] = useState(null);
  const [fees, setFees] = useState(null);
  const [exams, setExams] = useState(null);
  const [notices, setNotices] = useState(null);
  const [filter, setFilter] = useState("due");
  const base = `/parent/child/${childId}`;
  useEffect(() => {
    api.get(base).then((r) => setSnap(r.data)).catch(() => setSnap({ error: true }));
    api.get(`${base}/timetable`).then((r) => setTt(r.data)).catch(() => setTt(null));
    api.get(`${base}/homework`).then((r) => setHw(r.data.homework)).catch(() => setHw([]));
    api.get(`${base}/assignments`).then((r) => setAsg(r.data.assignments)).catch(() => setAsg([]));
    api.get(`${base}/fees`).then((r) => setFees(r.data)).catch(() => setFees(null));
    api.get(`${base}/exams`).then((r) => setExams(r.data.exams || [])).catch(() => setExams([]));
    api.get("/notices/feed").then((r) => setNotices(r.data.notices || [])).catch(() => setNotices([]));
  }, [base]);
  const today = iso(new Date());
  const upcoming = useMemo(() => (exams || []).filter((x) => x.date >= today), [exams, today]);
  if (!snap) return <div className="space-y-4">{[0, 1, 2].map((i) => <div key={i} className="h-28 rounded-2xl bg-slate-200/60 dark:bg-slate-800 animate-pulse" />)}</div>;
  if (snap.error) return <PCard><PEmpty icon={AlertTriangle} text="Couldn't load this child's details. Please try again." /></PCard>;
  const s = snap.student;

  if (page === "home") return (
    <>
      <Hero s={s} leader={snap.leader_role} />
      <ClassTeacher ct={snap.class_teacher} childId={childId} />
      <TodayStrip fees={fees} hw={hw} asg={asg} tt={tt} notices={notices} exams={upcoming} go={go} />
      <div className="grid grid-cols-3 gap-3" data-testid="parent-stats">
        <MiniStat label="Attendance" value={snap.attendance.pct != null ? `${snap.attendance.pct}%` : "—"} sub={snap.attendance.total ? `${snap.attendance.present}/${snap.attendance.total} days` : "No records"} onClick={() => go("attendance")} testid="parent-quick-attendance" />
        <MiniStat label="Homework due" value={hw ? pendingItems(hw).length : "—"} sub={asg ? `${pendingItems(asg).length} assignment(s)` : ""} onClick={() => go("homework")} testid="parent-quick-homework" />
        <MiniStat label="Latest result" value={snap.results[0] ? `${snap.results[0].score ?? "—"}${snap.results[0].max_marks ? `/${snap.results[0].max_marks}` : ""}` : "—"} sub={snap.results[0]?.subject || "No results yet"} onClick={() => go("results")} testid="parent-quick-results" />
      </div>
      <TodayList tt={tt} prefix="parent" testid="parent-today-tt" />
      <NoticesList notices={notices} limit={3} testid="parent-home-notices" prefix="parent" />
    </>
  );
  if (page === "timetable") return (<><TodayList tt={tt} prefix="parent" testid="parent-today-tt" /><WeekGrid tt={tt} prefix="parent" testid="parent-week" /></>);
  if (page === "homework") return (
    <>
      <Chips value={filter} onChange={setFilter} testid="parent-hw-filter" options={[["due", "Due"], ["submitted", "Submitted"], ["overdue", "Overdue"], ["all", "All"]]} />
      <PCard title="Homework" icon={BookMarked} testid="parent-homework"><HomeworkList items={filterWork(hw, filter)} /></PCard>
      <PCard title="Assignments" icon={ClipboardCheck} testid="parent-assignments"><AssignmentsList items={filterWork(asg, filter)} /></PCard>
    </>
  );
  if (page === "attendance") return <AttendanceCalendar endpoint={`${base}/attendance-calendar`} testid="parent-attendance" />;
  if (page === "results") return (<><ExamsList exams={upcoming} testid="parent-exams" prefix="parent" /><ResultsBlock results={snap.results} prefix="parent" /></>);
  if (page === "fees") return <StudentFees endpoint={`${base}/fees`} testid="parent-fees" parentChildId={childId} defaultOpen />;
  if (page === "notices") return <NoticesList notices={notices} testid="parent-notices" prefix="parent" />;
  if (page === "achievements") return (
    <PCard title="Achievements" icon={Trophy} testid="parent-achievements">
      {snap.achievements.length === 0 ? <PEmpty icon={Trophy} text="No achievements recorded yet — the class teacher adds them here." /> : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
          {snap.achievements.map((a) => <li key={a.id} className="px-5 py-3 flex items-start justify-between gap-4"><div><p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{a.title}</p>{a.description && <p className="text-xs text-slate-500 mt-0.5">{a.description}</p>}</div><span className="text-xs text-slate-400 whitespace-nowrap">{a.date || ""}</span></li>)}
        </ul>
      )}
    </PCard>
  );
  if (page === "profile") return (
    <PCard title="Child profile" icon={User} testid="parent-child-profile">
      <div className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
        <Field label="Full name" value={fullName(s)} /><Field label="Admission no." value={s.admission_no} />
        <Field label="Class & section" value={`${s.class_name || "—"}${s.section ? ` · ${s.section}` : ""}`} /><Field label="Academic year" value={s.academic_year} />
        <Field label="Date of birth" value={s.date_of_birth || s.dob} /><Field label="Gender" value={s.gender && s.gender[0].toUpperCase() + s.gender.slice(1)} />
        <Field label="Leadership" value={snap.leader_role === "class_leader" ? "Class Leader" : snap.leader_role === "second_leader" ? "Second Leader" : ""} />
      </div>
      <div className="px-5 pb-5"><ClassTeacher ct={snap.class_teacher} childId={childId} /></div>
    </PCard>
  );
  return null;
}

function ClassTeacher({ ct, childId }) {
  const navigate = useNavigate();
  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 flex items-center gap-3" data-testid="parent-class-teacher">
      <Photo src={ct?.thumb_url} name={ct?.name || "?"} size="md" testid="parent-class-teacher-photo" />
      <div className="flex-1 min-w-0">
        <p className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">Class teacher</p>
        <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate" data-testid="parent-class-teacher-name">{ct?.name || "Not assigned yet"}</p>
      </div>
      {ct && <Button size="sm" variant="outline" onClick={() => navigate(`/parents/messages?child=${childId}&compose=class_teacher`)} data-testid="parent-class-teacher-message-btn"><MessageSquare size={14} className="mr-1.5" /> Message</Button>}
    </div>
  );
}

const Hero = ({ s, leader }) => (
  <div className="rounded-2xl p-5 sm:p-6 text-white relative overflow-hidden flex items-center gap-4" style={{ background: "linear-gradient(120deg, var(--brand-ink), var(--brand))" }} data-testid="parent-child-hero">
    <div className="absolute -top-10 -right-10 h-36 w-36 rounded-full bg-white/10" />
    <Photo src={s.photo_url} name={fullName(s)} size="xl" className="!ring-white/40" testid="parent-child-photo" />
    <div className="min-w-0 relative">
    <p className="text-xs uppercase tracking-wider text-white/75">Your child</p>
    <h2 className="font-heading text-2xl font-bold flex items-center gap-2 flex-wrap mt-0.5">
      {fullName(s)}
      {leader === "class_leader" && <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-300 text-amber-950" data-testid="parent-leader-badge"><Crown size={11} /> Class Leader</span>}
      {leader === "second_leader" && <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-white/90 text-slate-800" data-testid="parent-leader-badge"><Medal size={11} /> Second Leader</span>}
    </h2>
    <p className="text-sm text-white/85 mt-1">{s.admission_no ? `Adm. ${s.admission_no} · ` : ""}{s.class_name}{s.section ? ` · Section ${s.section}` : ""}</p>
    </div>
  </div>
);

const MiniStat = ({ label, value, sub, onClick, testid }) => (
  <button onClick={onClick} className="text-left rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-3.5 sm:p-4 hover:border-[var(--brand-line)] transition-colors" data-testid={testid}>
    <p className="text-[10px] sm:text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</p>
    <p className="font-heading text-xl sm:text-2xl font-bold text-slate-900 dark:text-white mt-1">{value}</p>
    <p className="text-[11px] text-slate-500 mt-0.5 truncate">{sub}</p>
  </button>
);

function TodayStrip({ fees, hw, asg, tt, notices, exams, go }) {
  const today = iso(new Date());
  const tmrw = iso(new Date(Date.now() + 86400000));
  const week = iso(new Date(Date.now() + 7 * 86400000));
  const open = (fees?.invoices || []).filter((i) => (i.balance || 0) > 0);
  const overdue = open.filter((i) => i.due_date && i.due_date < today);
  const dueSoon = open.filter((i) => i.due_date && i.due_date >= today && i.due_date <= week);
  const sum = (xs) => xs.reduce((a, i) => a + (i.balance || 0), 0).toLocaleString("en-IN");
  const hwSoon = [...pendingItems(hw || []), ...pendingItems(asg || [])].filter((x) => x.due_date === today || x.due_date === tmrw);
  const subs = tt?.today_changes?.items?.length || 0;
  const fresh = (notices || []).filter((n) => (n.created_at || "") >= iso(new Date(Date.now() - 3 * 86400000)));
  const nextExam = (exams || []).find((x) => x.date <= week);
  const items = [];
  if (overdue.length) items.push({ k: "fee-overdue", tone: "rose", text: `₹${sum(overdue)} fee overdue`, action: "Pay", to: "fees" });
  else if (dueSoon.length) items.push({ k: "fee-due", tone: "amber", text: `₹${sum(dueSoon)} fee due by ${dueSoon[0].due_date}`, action: "Pay", to: "fees" });
  if (hwSoon.length) items.push({ k: "homework", tone: "indigo", text: `${hwSoon.length} homework/assignment due today or tomorrow`, to: "homework" });
  if (subs) items.push({ k: "substitute", tone: "amber", text: `${subs} period${subs > 1 ? "s" : ""} with a substitute or absent teacher today`, to: "timetable" });
  if (nextExam) items.push({ k: "exam", tone: "sky", text: `Exam: ${nextExam.subject} on ${nextExam.date}`, to: "results" });
  if (fresh.length) items.push({ k: "notices", tone: "emerald", text: `${fresh.length} new notice${fresh.length > 1 ? "s" : ""}`, to: "notices" });
  if (!items.length) return null;
  const TONE = { rose: "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300", amber: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300", indigo: "border-indigo-200 bg-indigo-50 text-indigo-800 dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-300", sky: "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300", emerald: "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300" };
  return (
    <div className="space-y-2" data-testid="parent-today-strip">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Today</p>
      {items.map((i) => (
        <button key={i.k} onClick={() => go(i.to)} className={`w-full flex items-center gap-3 rounded-xl border px-3.5 py-2.5 text-left text-sm font-medium ${TONE[i.tone]}`} data-testid={`parent-alert-${i.k}`}>
          <span className="flex-1">{i.text}</span>
          {i.action ? <span className="rounded-lg bg-[var(--brand)] text-white px-3 py-1 text-xs font-semibold" data-testid={`parent-alert-${i.k}-pay`}>{i.action}</span> : <ArrowRight size={15} />}
        </button>
      ))}
    </div>
  );
}

function Account({ kids, onLink, onChanged }) {
  const unlink = async (c) => {
    if (!window.confirm(`Remove ${c.first_name} from your account? You can link again later.`)) return;
    try { await api.post(`/parent/unlink/${c.id}`); toast.success("Child unlinked"); onChanged(); } catch (e) { toast.error(errText(e)); }
  };
  return (
    <PCard title="Linked children" icon={Users} right={<Button size="sm" onClick={onLink} className="bg-[var(--brand)] hover:opacity-90 text-white" data-testid="parent-link-child-btn"><Plus size={14} className="mr-1" /> Link a child</Button>} testid="parent-account">
      {kids.length === 0 ? <PEmpty icon={Users} text="No children linked yet. Use Link a child with the admission number and your registered mobile." /> : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
          {kids.map((c) => (
            <li key={c.id} className="px-5 py-3 flex items-center gap-3">
              <div className="flex-1 min-w-0"><p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{fullName(c)}</p><p className="text-xs text-slate-500">{c.class_name}{c.section ? ` ${c.section}` : ""}{c.admission_no ? ` · Adm. ${c.admission_no}` : ""}</p></div>
              <Button size="sm" variant="ghost" className="text-slate-500" onClick={() => unlink(c)} data-testid={`parent-unlink-${c.id}`}><Link2Off size={14} className="mr-1" /> Unlink</Button>
            </li>
          ))}
        </ul>
      )}
    </PCard>
  );
}

function Support() {
  const { openReport } = useReportIssue();
  return (
    <PCard title="Support" icon={LifeBuoy} testid="parent-support">
      <div className="p-5 space-y-3">
        <p className="text-sm text-slate-600 dark:text-slate-300">Something not working, or a question about fees, attendance or results? Send it to the school and they'll get back to you.</p>
        <Button onClick={openReport} className="bg-[var(--brand)] hover:opacity-90 text-white" data-testid="parent-report-btn">Report an issue</Button>
      </div>
    </PCard>
  );
}
