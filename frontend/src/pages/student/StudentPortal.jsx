import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import {
  LayoutDashboard, User, Table2, BookMarked, ClipboardCheck, Sparkles, BookOpen, Award, Wallet, Trophy, Megaphone,
  CalendarCheck, CalendarClock, Camera, Crown, Medal, ArrowRight,
} from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import StudentFees from "../portal/StudentFees";
import HomeworkList from "../../components/homework/HomeworkList";
import AssignmentsList from "../../components/homework/AssignmentsList";
import AttendanceCalendar from "../portal/AttendanceCalendar";
import PortalShell, { PCard, PEmpty } from "../portal/PortalShell";
import { useSchoolBrand } from "../portal/useSchoolBrand";
import { TodayList, WeekGrid, NoticesList, ExamsList, ResultsBlock, Field } from "../portal/PortalBlocks";
import { pendingItems, nearestDue } from "../portal/PortalKit";
import { AITutorStudent, AILibraryStudent } from "./AITutorStudent";

const API_BASE = process.env.REACT_APP_BACKEND_URL;
const NAV = [
  { key: "dashboard", label: "Dashboard", short: "Home", icon: LayoutDashboard },
  { key: "timetable", label: "Timetable", icon: Table2 },
  { key: "homework", label: "Homework", icon: BookMarked },
  { key: "assignments", label: "Assignments", icon: ClipboardCheck },
  { key: "exams", label: "Exams", icon: CalendarClock },
  { key: "results", label: "Results", icon: Award },
  { key: "attendance", label: "Attendance", icon: CalendarCheck },
  { key: "notices", label: "Notices", icon: Megaphone },
  { key: "ai-tutor", label: "AI Tutor", icon: Sparkles },
  { key: "library", label: "Library", icon: BookOpen },
  { key: "fees", label: "Fees", icon: Wallet },
  { key: "achievements", label: "Achievements", icon: Trophy },
  { key: "profile", label: "My Profile", icon: User },
];
const BOTTOM = ["dashboard", "timetable", "homework", "ai-tutor"];

export default function StudentPortal() {
  const { "*": rest = "" } = useParams();
  const page = rest.split("/")[0];
  const navigate = useNavigate();
  const brand = useSchoolBrand("Student Portal");
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [tt, setTt] = useState(null);
  const [notices, setNotices] = useState(null);
  const [exams, setExams] = useState(null);
  const [hw, setHw] = useState(null);
  const [asg, setAsg] = useState(null);
  const [photoV, setPhotoV] = useState(Date.now());
  const fileRef = useRef(null);
  const loadHw = () => api.get("/homework").then((r) => setHw(r.data.homework)).catch(() => setHw([]));
  const loadAsg = () => api.get("/assignments").then((r) => setAsg(r.data.assignments)).catch(() => setAsg([]));
  useEffect(() => {
    api.get("/portal/me").then((r) => setData(r.data)).catch(() => setError(true));
    api.get("/portal/timetable").then((r) => setTt(r.data)).catch(() => setTt(null));
    api.get("/portal/exams").then((r) => setExams(r.data.exams || [])).catch(() => setExams([]));
    api.get("/notices/feed").then((r) => setNotices(r.data.notices || [])).catch(() => setNotices([]));
    loadHw(); loadAsg();
  }, []);
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = useMemo(() => (exams || []).filter((x) => x.date >= today), [exams, today]);
  if (!NAV.some((n) => n.key === page)) return <Navigate to="/portal/dashboard" replace />;
  const s = data?.student;
  const go = (k) => navigate(`/portal/${k}`);

  const uploadPhoto = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !s) return;
    const fd = new FormData();
    fd.append("file", file);
    try { await api.post(`/students/${s.id}/photo`, fd, { headers: { "Content-Type": "multipart/form-data" } }); toast.success("Photo updated!"); setPhotoV(Date.now()); }
    catch (err) { toast.error(errText(err)); }
  };
  const Avatar = () => (
    <div className="h-16 w-16 rounded-2xl bg-white/20 flex items-center justify-center shrink-0 overflow-hidden relative group">
      {s?.photo_path ? <img src={`${API_BASE}/api/students/${s.id}/photo?v=${photoV}`} alt="" className="h-full w-full object-cover" /> : <User size={26} />}
      <button onClick={() => fileRef.current?.click()} data-testid="portal-photo-btn" className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white"><Camera size={16} /></button>
    </div>
  );

  let body;
  if (error) body = <PCard><PEmpty icon={User} text="Your student profile couldn't be loaded. Please contact the school office." testid="portal-error" /></PCard>;
  else if (!data) body = <div className="space-y-4">{[0, 1, 2].map((i) => <div key={i} className="h-28 rounded-2xl bg-slate-200/60 dark:bg-slate-800 animate-pulse" />)}</div>;
  else if (page === "dashboard") {
    const due = pendingItems(hw || []);
    const dueA = pendingItems(asg || []);
    body = (
      <>
        <div className="rounded-2xl p-5 sm:p-6 text-white relative overflow-hidden flex items-center gap-4" style={{ background: "linear-gradient(120deg, var(--brand-ink), var(--brand))" }} data-testid="portal-hero">
          <Avatar />
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wider text-white/75">Welcome back</p>
            <h2 className="font-heading text-2xl font-bold flex items-center gap-2 flex-wrap">{`${s.first_name || ""} ${s.last_name || ""}`.trim()}
              {data.leader_role === "class_leader" && <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-300 text-amber-950"><Crown size={11} /> Class Leader</span>}
              {data.leader_role === "second_leader" && <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-white/90 text-slate-800"><Medal size={11} /> Second Leader</span>}
            </h2>
            <p className="text-sm text-white/85">{s.class_name}{s.section ? ` · Section ${s.section}` : ""}{s.admission_no ? ` · Adm. ${s.admission_no}` : ""}</p>
          </div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="portal-stats">
          <Mini label="Attendance" value={data.attendance.pct != null ? `${data.attendance.pct}%` : "—"} sub={data.attendance.total ? `${data.attendance.present}/${data.attendance.total} days` : "No records"} onClick={() => go("attendance")} testid="quick-attendance" />
          <Mini label="Due next" value={due.length + dueA.length} sub={due.length || dueA.length ? `Next: ${nearestDue([...due, ...dueA]) || "—"}` : "All caught up"} onClick={() => go("homework")} testid="quick-homework" />
          <Mini label="Latest result" value={data.results[0] ? `${data.results[0].score ?? "—"}${data.results[0].max_marks ? `/${data.results[0].max_marks}` : ""}` : "—"} sub={data.results[0]?.subject || "No results yet"} onClick={() => go("results")} testid="quick-results" />
          <button onClick={() => go("ai-tutor")} className="text-left rounded-2xl p-4 text-white" style={{ background: "var(--brand)" }} data-testid="quick-ai-tutor">
            <Sparkles size={18} /><p className="font-heading font-bold mt-1.5">AI Tutor</p><p className="text-[11px] text-white/85 flex items-center gap-1">Ask a question <ArrowRight size={11} /></p>
          </button>
        </div>
        <TodayList tt={tt} prefix="portal" testid="portal-today" />
        <div className="grid lg:grid-cols-2 gap-5">
          <ExamsList exams={upcoming.slice(0, 4)} testid="portal-dash-exams" />
          <NoticesList notices={notices} limit={3} testid="portal-dash-notices" />
        </div>
      </>
    );
  } else if (page === "timetable") body = (<><TodayList tt={tt} prefix="portal" testid="portal-today" /><WeekGrid tt={tt} prefix="portal" testid="portal-timetable" /></>);
  else if (page === "homework") body = <PCard title="Homework" icon={BookMarked} testid="portal-homework"><HomeworkList items={hw} canSubmit onChanged={loadHw} /></PCard>;
  else if (page === "assignments") body = <PCard title="Assignments" icon={ClipboardCheck} testid="portal-assignments"><AssignmentsList items={asg} canSubmit onChanged={loadAsg} /></PCard>;
  else if (page === "exams") body = (
    <>
      <ExamsList exams={upcoming} testid="portal-exams" />
      <PCard testid="portal-exams-results-link"><button onClick={() => go("results")} className="w-full px-5 py-4 flex items-center justify-between text-sm font-semibold text-[var(--brand-ink)] dark:text-[var(--brand)]">See published results <ArrowRight size={15} /></button></PCard>
    </>
  );
  else if (page === "results") body = <ResultsBlock results={data.results} subjects={data.subjects} prefix="portal" />;
  else if (page === "attendance") body = <AttendanceCalendar endpoint="/portal/attendance-calendar" testid="portal-attendance" />;
  else if (page === "notices") body = <NoticesList notices={notices} testid="portal-notices" />;
  else if (page === "ai-tutor") body = <AITutorStudent />;
  else if (page === "library") body = <AILibraryStudent />;
  else if (page === "fees") body = <StudentFees endpoint="/portal/fees" testid="student-fees" />;
  else if (page === "achievements") body = (
    <PCard title="Achievements" icon={Trophy} testid="portal-achievements">
      {data.achievements.length === 0 ? <PEmpty icon={Trophy} text="No achievements recorded yet — keep going!" /> : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
          {data.achievements.map((a) => <li key={a.id} className="px-5 py-3 flex items-start justify-between gap-4"><div><p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{a.title}</p>{a.description && <p className="text-xs text-slate-500 mt-0.5">{a.description}</p>}</div><span className="text-xs text-slate-400 whitespace-nowrap">{a.date || ""}</span></li>)}
        </ul>
      )}
    </PCard>
  );
  else if (page === "profile") body = (
    <PCard title="My Profile" icon={User} testid="portal-profile">
      <div className="p-5 flex items-center gap-4 border-b border-slate-100 dark:border-slate-800 text-white" style={{ background: "linear-gradient(120deg, var(--brand-ink), var(--brand))" }}><Avatar /><p className="text-sm">Tap the photo to change it.</p></div>
      <div className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
        <Field label="Full name" value={`${s.first_name || ""} ${s.last_name || ""}`.trim()} testid="student-name-field" />
        <Field label="Admission no." value={s.admission_no} testid="student-admno-field" />
        <Field label="Class & section" value={`${s.class_name || "—"}${s.section ? ` · ${s.section}` : ""}`} testid="student-class-field" />
        <Field label="Academic year" value={s.academic_year} testid="student-year-field" />
        <Field label="Date of birth" value={s.date_of_birth || s.dob} testid="student-dob-field" />
        <Field label="Gender" value={s.gender && s.gender[0].toUpperCase() + s.gender.slice(1)} testid="student-gender-field" />
        <Field label="Guardian" value={s.guardian_name} testid="student-guardian-field" />
        <Field label="Guardian phone" value={s.guardian_phone} testid="student-guardian-phone-field" />
      </div>
    </PCard>
  );

  return (
    <PortalShell brand={brand} label="Student Portal" nav={NAV} bottom={BOTTOM} base="/portal" testid="student-portal">
      <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={uploadPhoto} data-testid="portal-photo-input" />
      {body}
    </PortalShell>
  );
}

const Mini = ({ label, value, sub, onClick, testid }) => (
  <button onClick={onClick} className="text-left rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 hover:border-[var(--brand-line)] transition-colors" data-testid={testid}>
    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</p>
    <p className="font-heading text-2xl font-bold text-slate-900 dark:text-white mt-1">{value}</p>
    <p className="text-[11px] text-slate-500 mt-0.5 truncate">{sub}</p>
  </button>
);
