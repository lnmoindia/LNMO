import { useEffect, useRef, useState } from "react";
import { Wallet } from "lucide-react";
import StudentFees from "../portal/StudentFees";
import {
  LogOut, Moon, Sun, GraduationCap, CalendarCheck, Award, User, Crown, Medal, Trophy,
  Megaphone, CalendarClock, FlaskConical, DoorOpen, BookOpen, History, LayoutDashboard,
  Table2, Flame, Camera, Paperclip, Sparkles,
} from "lucide-react";
import { BookMarked } from "lucide-react";
import { ClipboardCheck } from "lucide-react";
import { Menu } from "lucide-react";
import { Reveal, AttendanceRing, QuickCard, PortalSkeleton, BottomNav, ResultTrends, pendingItems, nearestDue } from "../portal/PortalKit";
import { TrendingUp } from "lucide-react";
import HomeworkList from "../../components/homework/HomeworkList";
import AssignmentsList from "../../components/homework/AssignmentsList";
import { AITutorStudent, AILibraryStudent } from "./AITutorStudent";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../context/ThemeContext";
import { useReportIssue } from "../../context/ReportIssue";
import { MessageSquareWarning } from "lucide-react";
import { Button } from "../../components/ui/button";
import { useNavigate } from "react-router-dom";

const DAY_SHORT = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };
const API_BASE = process.env.REACT_APP_BACKEND_URL;

const NAV = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { key: "profile", label: "My Profile", icon: User },
  { key: "timetable", label: "Timetable", icon: Table2 },
  { key: "homework", label: "Homework", icon: BookMarked },
  { key: "assignments", label: "Assignments", icon: ClipboardCheck },
  { key: "ai-tutor", label: "AI Tutor", icon: Sparkles },
  { key: "library", label: "Library", icon: BookOpen },
  { key: "results", label: "Results", icon: Award },
  { key: "fees", label: "Fees", icon: Wallet },
  { key: "achievements", label: "Achievements", icon: Trophy },
];

export default function StudentPortal() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const { openReport } = useReportIssue();
  const navigate = useNavigate();
  const [page, setPage] = useState("dashboard");
  const [moreOpen, setMoreOpen] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [tt, setTt] = useState(null);
  const [notices, setNotices] = useState([]);
  const [exams, setExams] = useState([]);
  const [hw, setHw] = useState(null);
  const [asg, setAsg] = useState(null);
  const [photoV, setPhotoV] = useState(Date.now());
  const fileRef = useRef(null);

  useEffect(() => {
    api.get("/portal/me").then((r) => setData(r.data)).catch(() => setError(true));
    api.get("/portal/timetable").then((r) => setTt(r.data)).catch(() => setTt(null));
    api.get("/portal/exams").then((r) => setExams(r.data.exams || [])).catch(() => setExams([]));
    api.get("/notices/feed").then((r) => setNotices(r.data.notices || [])).catch(() => setNotices([]));
  }, []);

  const loadHw = () => api.get("/homework").then((r) => setHw(r.data.homework)).catch(() => setHw([]));
  useEffect(() => { loadHw(); }, []);

  const loadAsg = () => api.get("/assignments").then((r) => setAsg(r.data.assignments)).catch(() => setAsg([]));
  useEffect(() => { loadAsg(); }, []);

  const handleLogout = async () => { await logout(); navigate("/login"); };
  const s = data?.student;
  const todayKey = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"][new Date().getDay()];

  let streak = 0;
  for (const h of data?.attendance_history || []) {
    if (String(h.status || "").toLowerCase().startsWith("p")) streak += 1;
    else break;
  }
  const streakLabel = streak >= 30 ? "30+" : streak;

  const todayClasses = (tt?.entries || []).filter((e) => e.day === todayKey)
    .map((e) => ({ ...e, period: tt.config.periods[e.period_no - 1] || {} }))
    .sort((a, b) => a.period_no - b.period_no);

  const uploadPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !s) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.post(`/students/${s.id}/photo`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Photo updated!");
      setPhotoV(Date.now());
    } catch (err) {
      toast.error(errText(err));
    }
    e.target.value = "";
  };

  const photoUrl = s ? `${API_BASE}/api/students/${s.id}/photo?v=${photoV}` : null;

  const Avatar = ({ size = "h-16 w-16", icon = 28 }) => (
    <div className={`${size} rounded-2xl bg-white/20 backdrop-blur flex items-center justify-center shrink-0 overflow-hidden relative group`}>
      {s?.photo_path ? <img src={photoUrl} alt="me" className="h-full w-full object-cover" /> : <User size={icon} />}
      <button onClick={() => fileRef.current?.click()} data-testid="portal-photo-btn"
        className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white">
        <Camera size={16} />
      </button>
    </div>
  );

  const Card = ({ children, className = "", testid }) => (
    <div className={`rounded-3xl border-2 border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-md hover:shadow-xl transition-all duration-300 overflow-hidden ${className}`} data-testid={testid}>
      {children}
    </div>
  );
  const CardHead = ({ icon: Icon, color = "text-indigo-600", title, right }) => (
    <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
      <Icon size={17} className={color} />
      <h2 className="font-heading text-lg font-bold text-slate-900 dark:text-slate-50">{title}</h2>
      {right && <span className="text-xs text-slate-400 ml-auto">{right}</span>}
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#0B0F17] flex">
      <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={uploadPhoto} data-testid="portal-photo-input" />
      {/* Sidebar */}
      <aside className="hidden md:flex w-56 flex-col bg-slate-900 text-white shrink-0 sticky top-0 h-screen" data-testid="portal-sidebar">
        <div className="h-16 flex items-center gap-2.5 px-5 border-b border-white/10">
          {data?.branding?.logo_url || data?.branding?.has_logo
            ? <img src={data.branding.has_logo ? `${process.env.REACT_APP_BACKEND_URL}/api/public/institution-logo?domain=${encodeURIComponent(data.branding.domain || "")}` : data.branding.logo_url} alt="logo" className="h-8 w-8 rounded-lg object-cover" />
            : <div className="h-8 w-8 rounded-lg flex items-center justify-center font-heading font-bold text-sm" style={{ background: data?.branding?.primary_color || "#4f46e5" }}>{(data?.branding?.portal_name || "L")[0]}</div>}
          <div>
            <p className="font-heading font-bold text-sm leading-none">{data?.branding?.portal_name || "Student Portal"}</p>
            <p className="text-[10px] text-white/50 mt-0.5">Student Portal</p>
          </div>
        </div>
        <nav className="flex-1 py-4 px-3 space-y-1">
          {NAV.map((n) => {
            const Icon = n.icon;
            const active = page === n.key;
            return (
              <button key={n.key} onClick={() => setPage(n.key)} data-testid={`portal-nav-${n.key}`}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium transition-colors ${active ? "bg-indigo-600 text-white" : "text-white/60 hover:text-white hover:bg-white/10"}`}>
                <Icon size={16} /> {n.label}
              </button>
            );
          })}
        </nav>
        <div className="p-4 border-t border-white/10 text-xs text-white/40">{user?.institution_name}</div>
      </aside>

      <div className="flex-1 min-w-0">
        <header className="h-16 flex items-center gap-3 px-4 md:px-8 border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl sticky top-0 z-20">
          <div className="md:hidden flex gap-1 overflow-x-auto flex-1">
            {NAV.map((n) => (
              <button key={n.key} onClick={() => setPage(n.key)} data-testid={`portal-mnav-${n.key}`}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap ${page === n.key ? "bg-indigo-600 text-white" : "text-slate-500"}`}>{n.label}</button>
            ))}
          </div>
          <p className="hidden md:block flex-1 font-heading font-bold text-slate-900 dark:text-white capitalize">{NAV.find((n) => n.key === page)?.label}</p>
          <button onClick={toggle} className="h-9 w-9 rounded-lg flex items-center justify-center text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors" data-testid="portal-theme-toggle">
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <Button variant="outline" size="sm" onClick={openReport} data-testid="portal-report-btn"><MessageSquareWarning size={14} className="mr-1.5" /> Report</Button>
          <Button variant="outline" size="sm" onClick={handleLogout} data-testid="portal-logout-btn"><LogOut size={14} className="mr-1.5" /> Sign out</Button>
        </header>

        <main className="max-w-4xl mx-auto px-4 md:px-8 py-8 pb-24 md:pb-10 space-y-6" data-testid="student-portal">
          {error && <div className="rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10 p-6 text-sm text-amber-800 dark:text-amber-200">No student profile is linked to your account yet. Please contact your school administrator.</div>}
          {!error && !data && <PortalSkeleton />}
          {s && (
            <>
              {page === "dashboard" && (
                <>
                  <div className="relative overflow-hidden rounded-3xl p-6 md:p-7 text-white shadow-lg shadow-indigo-500/20 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 dark:from-indigo-900 dark:via-purple-950 dark:to-slate-900 dark:border dark:border-indigo-500/30" data-testid="portal-profile">
                    <div className="absolute -top-8 -right-8 h-32 w-32 rounded-full bg-white/10" />
                    <div className="absolute top-10 right-24 h-14 w-14 rounded-full bg-white/10" />
                    <div className="relative flex items-center gap-5">
                      <Avatar />
                      <div>
                        <h1 className="font-heading text-2xl md:text-3xl font-bold flex items-center gap-2 flex-wrap">
                          {`${s.first_name || ""} ${s.last_name || ""}`.trim()}
                          {data.leader_role === "class_leader" && <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-400 text-amber-950 border border-amber-300 shadow-md" data-testid="portal-leader-badge"><Crown size={12} /> Class Leader</span>}
                          {data.leader_role === "second_leader" && <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-white/90 text-slate-800 shadow-sm" data-testid="portal-leader-badge"><Medal size={12} /> Second Leader</span>}
                        </h1>
                        <p className="text-sm text-white/80 mt-1">{s.admission_no ? `Adm. ${s.admission_no} · ` : ""}{s.class_name || "—"}{s.section ? ` · Section ${s.section}` : ""}{s.academic_year ? ` · ${s.academic_year}` : ""}</p>
                      </div>
                    </div>
                  </div>

                  <Reveal className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4" data-testid="portal-quickgrid">
                    <QuickCard tone="emerald" icon={CalendarCheck} label="Attendance" value={data.attendance.pct !== null ? `${data.attendance.pct}%` : "—"} sub={data.attendance.total ? `${data.attendance.present}/${data.attendance.total} days` : "No records yet"} onClick={() => setPage("achievements")} testid="quick-attendance">
                      <AttendanceRing pct={data.attendance.pct} />
                    </QuickCard>
                    <QuickCard tone="indigo" icon={BookMarked} label="Homework due" value={hw ? pendingItems(hw).length : "—"} sub={hw && pendingItems(hw).length ? `Next: ${nearestDue(pendingItems(hw)) || "—"}` : "All caught up 🎉"} onClick={() => setPage("homework")} testid="quick-homework" />
                    <QuickCard tone="fuchsia" icon={ClipboardCheck} label="Assignments" value={asg ? pendingItems(asg).length : "—"} sub={asg && pendingItems(asg).length ? "pending to submit" : "nothing pending"} onClick={() => setPage("assignments")} testid="quick-assignments" />
                    <QuickCard tone="sky" icon={Award} label="Latest result" value={data.results[0] ? `${data.results[0].score ?? "—"}${data.results[0].max_marks ? `/${data.results[0].max_marks}` : ""}` : "—"} sub={data.results[0]?.subject || data.results[0]?.assessment || "No results yet"} onClick={() => setPage("results")} testid="quick-results" />
                    <QuickCard tone="purple" icon={Sparkles} label="AI Tutor" value="Ask" sub="Get help instantly" onClick={() => setPage("ai-tutor")} testid="quick-ai-tutor" />
                  </Reveal>

                  <Card testid="portal-today">
                    <CardHead icon={CalendarClock} title={`Today — ${DAY_SHORT[todayKey]}`} right={tt?.academic_year} />
                    {!tt?.config || !tt.config.working_days.includes(todayKey) ? (
                      <p className="px-6 py-6 text-sm text-slate-400">No school today — enjoy your day!</p>
                    ) : todayClasses.length === 0 ? (
                      <p className="px-6 py-6 text-sm text-slate-400">No classes scheduled today yet.</p>
                    ) : (
                      <div className="px-6 py-4 flex gap-3 overflow-x-auto">
                        {todayClasses.map((e) => (
                          <div key={e.id} className="min-w-[150px] rounded-2xl border-2 border-indigo-100 dark:border-indigo-500/20 bg-indigo-50/60 dark:bg-indigo-500/10 px-3 py-2.5" data-testid={`portal-today-${e.id}`}>
                            <p className="text-[11px] font-bold text-indigo-600 dark:text-indigo-400">{e.period.label}{e.period.start ? ` · ${e.period.start}` : ""}</p>
                            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{e.subject}{e.type === "lab" && <FlaskConical size={10} className="inline ml-1 text-amber-500" />}</p>
                            <p className="text-xs text-slate-500">{e.teacher_name}{e.room ? ` · ${e.room}` : ""}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>

                  {exams.length > 0 && (
                    <Card testid="portal-exams">
                      <CardHead icon={CalendarClock} color="text-rose-500" title="Upcoming Exams" right={`${exams.length} paper${exams.length === 1 ? "" : "s"}`} />
                      <div className="px-6 py-4 space-y-2">
                        {exams.map((x, i) => (
                          <div key={i} className={`flex items-center justify-between gap-3 rounded-xl border px-3 py-2.5 ${x.status === "postponed" ? "border-amber-200 bg-amber-50/60 dark:border-amber-500/30 dark:bg-amber-500/10" : "border-slate-200 dark:border-slate-700"}`} data-testid={`portal-exam-${i}`}>
                            <div>
                              <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{x.subject}</p>
                              <p className="text-xs text-slate-500">{x.exam_name}{x.room ? ` · ${x.room}` : ""}{x.status === "postponed" ? " · postponed" : ""}</p>
                            </div>
                            <div className="text-right shrink-0">
                              <p className="text-sm font-bold text-rose-600 dark:text-rose-400">{x.date}</p>
                              <p className="text-xs text-slate-500">{x.start}–{x.end}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </Card>
                  )}

                  {notices.length > 0 && (
                    <Card testid="portal-notices">
                      <CardHead icon={Megaphone} title="Notices" />
                      <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
                        {notices.map((n) => (
                          <li key={n.id} className="px-6 py-3.5" data-testid={`portal-notice-${n.id}`}>
                            <div className="flex items-start justify-between gap-4">
                              <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{n.title}</p>
                              <span className="text-xs text-slate-400 whitespace-nowrap">{(n.created_at || "").slice(0, 10)}</span>
                            </div>
                            {n.body && <p className="text-xs text-slate-500 mt-0.5 whitespace-pre-line">{n.body}</p>}
                            {n.attachments?.length > 0 && (
                              <div className="flex flex-wrap gap-2 mt-1.5">
                                {n.attachments.map((a, i) => (
                                  <a key={i} href={`${process.env.REACT_APP_BACKEND_URL}/api/notices/attachment/${n.id}/${i}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:underline" data-testid={`portal-notice-file-${n.id}-${i}`}><Paperclip size={11} /> {a.name}</a>
                                ))}
                              </div>
                            )}
                          </li>
                        ))}
                      </ul>
                    </Card>
                  )}
                </>
              )}

              {page === "profile" && (
                <Card testid="portal-profile-card">
                  <div className="px-6 py-6 flex items-center gap-5 border-b border-slate-100 dark:border-slate-800 bg-gradient-to-r from-indigo-500/10 to-pink-500/10">
                    <div className="relative">
                      <div className="h-20 w-20 rounded-3xl bg-indigo-600 text-white flex items-center justify-center overflow-hidden">
                        {s.photo_path ? <img src={photoUrl} alt="me" className="h-full w-full object-cover" /> : <User size={32} />}
                      </div>
                      <button onClick={() => fileRef.current?.click()} data-testid="profile-photo-btn"
                        className="absolute -bottom-1.5 -right-1.5 h-8 w-8 rounded-full bg-indigo-600 text-white flex items-center justify-center shadow-md hover:bg-indigo-700 transition-colors">
                        <Camera size={14} />
                      </button>
                    </div>
                    <div>
                      <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-slate-50">{`${s.first_name || ""} ${s.last_name || ""}`.trim()}</h2>
                      <p className="text-xs text-slate-500 mt-0.5">Tap the camera to upload your photo (JPG/PNG/WebP, max 4 MB)</p>
                    </div>
                  </div>
                  <div className="px-6 py-5 grid sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-4">
                    <Field label="Full name" value={`${s.first_name || ""} ${s.last_name || ""}`.trim()} testid="student-name-field" />
                    <Field label="Admission no." value={s.admission_no} testid="student-admno-field" />
                    <Field label="Class & section" value={`${s.class_name || "—"}${s.section ? " · " + s.section : ""}`} testid="student-class-field" />
                    <Field label="Academic year" value={s.academic_year} testid="student-year-field" />
                    <Field label="Date of birth" value={s.dob} testid="student-dob-field" />
                    <Field label="Gender" value={s.gender && s.gender.charAt(0).toUpperCase() + s.gender.slice(1)} testid="student-gender-field" />
                    <Field label="Guardian" value={s.guardian_name} testid="student-guardian-field" />
                    <Field label="Guardian phone" value={s.guardian_phone} testid="student-guardian-phone-field" />
                    <Field label="Leadership" value={data.leader_role === "class_leader" ? "Class Leader" : data.leader_role === "second_leader" ? "Second Leader" : null} testid="student-leadership-field" />
                  </div>
                </Card>
              )}

              {page === "timetable" && (
                <Card testid="portal-timetable">
                  <CardHead icon={CalendarClock} title="My Timetable" right={tt ? `${tt.class_name} ${tt.section} · ${tt.academic_year}` : ""} />
                  {!tt?.config || tt.entries.length === 0 ? (
                    <p className="px-6 py-8 text-center text-sm text-slate-400">Your timetable hasn't been published yet.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm border-collapse">
                        <thead>
                          <tr className="bg-slate-50 dark:bg-slate-900/60">
                            <th className="px-4 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-500 w-28">Period</th>
                            {tt.config.working_days.map((d) => (
                              <th key={d} className={`px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider border-l border-slate-100 dark:border-slate-800 ${d === todayKey ? "text-indigo-600 dark:text-indigo-400" : "text-slate-500"}`}>
                                {DAY_SHORT[d]}{d === todayKey ? " · today" : ""}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {tt.config.periods.map((p, idx) => {
                            const pno = idx + 1;
                            if (p.is_break) return (
                              <tr key={pno} className="bg-slate-50 dark:bg-slate-800/40">
                                <td className="px-4 py-1 text-[10px] text-slate-400">{p.label}</td>
                                <td colSpan={tt.config.working_days.length} className="px-3 py-1 text-center text-[10px] uppercase tracking-widest text-slate-400 border-l border-slate-100 dark:border-slate-800">{p.label}</td>
                              </tr>
                            );
                            return (
                              <tr key={pno} className="border-t border-slate-100 dark:border-slate-800/60">
                                <td className="px-4 py-2 text-xs text-slate-500 align-top">{p.label}<span className="block text-[10px] text-slate-400">{p.start}–{p.end}</span></td>
                                {tt.config.working_days.map((d) => {
                                  const e = tt.entries.find((x) => x.day === d && x.period_no === pno);
                                  return (
                                    <td key={d} className={`px-3 py-2 align-top border-l border-slate-100 dark:border-slate-800 ${d === todayKey ? "bg-indigo-50/50 dark:bg-indigo-500/5" : ""}`}>
                                      {e && (<><span className="block text-[13px] font-semibold text-slate-800 dark:text-slate-200 leading-tight">{e.subject}{e.type === "lab" && <FlaskConical size={10} className="inline ml-1 text-amber-500" />}</span><span className="block text-[11px] text-slate-500">{e.teacher_name}</span>{e.room && <span className="text-[10px] text-slate-400 inline-flex items-center gap-0.5"><DoorOpen size={9} /> {e.room}</span>}</>)}
                                    </td>
                                  );
                                })}
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>
              )}

              {page === "homework" && (
                <Card testid="portal-homework">
                  <CardHead icon={BookMarked} color="text-indigo-600" title="Homework" right={hw ? `${hw.length} assigned` : ""} />
                  <HomeworkList items={hw} canSubmit onChanged={loadHw} />
                </Card>
              )}

              {page === "assignments" && (
                <Card testid="portal-assignments">
                  <CardHead icon={ClipboardCheck} color="text-fuchsia-600" title="Assignments" right={asg ? `${asg.length} assigned` : ""} />
                  <AssignmentsList items={asg} canSubmit onChanged={loadAsg} />
                </Card>
              )}

              {page === "ai-tutor" && <AITutorStudent />}
              {page === "fees" && <StudentFees endpoint="/portal/fees" testid="student-fees" />}
              {page === "library" && <AILibraryStudent />}
              {page === "results" && (
                <>
                  {data.results.length > 0 && (
                    <Card testid="portal-trends">
                      <CardHead icon={TrendingUp} color="text-indigo-500" title="Score trends" />
                      <div className="px-4 pb-4"><ResultTrends results={data.results} testid="student-trends" /></div>
                    </Card>
                  )}
                  <Card testid="portal-results">
                    <CardHead icon={Award} color="text-sky-500" title="Results" />
                    {data.results.length === 0 ? <p className="px-6 py-8 text-center text-sm text-slate-400">No published results yet.</p> : (
                      <table className="w-full text-sm">
                        <thead className="bg-slate-50 dark:bg-slate-900/60 text-left">
                          <tr>
                            <th className="px-6 py-2.5 text-xs font-semibold uppercase text-slate-500">Assessment</th>
                            <th className="px-6 py-2.5 text-xs font-semibold uppercase text-slate-500">Subject</th>
                            <th className="px-6 py-2.5 text-xs font-semibold uppercase text-slate-500">Score</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                          {data.results.map((r, i) => (
                            <tr key={i}>
                              <td className="px-6 py-3 text-slate-700 dark:text-slate-300">{r.assessment}</td>
                              <td className="px-6 py-3 text-slate-500">{r.subject || "—"}</td>
                              <td className="px-6 py-3 font-medium text-slate-800 dark:text-slate-200">{r.score ?? "—"}{r.max_marks ? ` / ${r.max_marks}` : ""}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </Card>
                  {(data.subjects || []).length > 0 && (
                    <Card testid="portal-subjects">
                      <CardHead icon={BookOpen} title="My Subjects" />
                      <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
                        {data.subjects.map((sub, i) => (
                          <li key={i} className="px-6 py-3 flex items-center justify-between gap-4" data-testid={`portal-subject-${i}`}>
                            <div>
                              <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{sub.subject}{sub.has_practical && <FlaskConical size={11} className="inline ml-1.5 text-amber-500" />}</p>
                              <p className="text-xs text-slate-500">{sub.teacher_name || "Teacher to be assigned"}</p>
                            </div>
                            <span className="text-xs text-slate-400 whitespace-nowrap">Max {sub.max_marks}</span>
                          </li>
                        ))}
                      </ul>
                    </Card>
                  )}
                </>
              )}

              {page === "achievements" && (
                <>
                  <div className="rounded-3xl border-2 border-amber-200 dark:border-amber-800/50 bg-gradient-to-br from-amber-50/80 to-orange-50/50 dark:from-amber-950/20 dark:to-orange-950/10 shadow-md overflow-hidden" data-testid="portal-achievements">
                    <div className="px-6 py-4 border-b border-amber-200/60 dark:border-amber-800/40 flex items-center gap-2">
                      <div className="h-9 w-9 rounded-2xl bg-amber-400/20 text-amber-600 dark:text-amber-400 flex items-center justify-center"><Trophy size={17} /></div>
                      <h2 className="font-heading text-lg font-bold text-slate-900 dark:text-slate-50">My Achievements</h2>
                      {(data.achievements || []).length > 0 && <span className="ml-auto text-xs font-bold text-amber-600 dark:text-amber-400">{data.achievements.length} earned</span>}
                    </div>
                    {(data.achievements || []).length === 0 ? (
                      <p className="px-6 py-8 text-center text-sm text-slate-400">No achievements yet — keep going, your first badge is waiting!</p>
                    ) : (
                      <ul className="divide-y divide-amber-100 dark:divide-amber-900/30">
                        {data.achievements.map((a) => (
                          <li key={a.id} className="px-6 py-3.5 flex items-start gap-3" data-testid={`portal-ach-${a.id}`}>
                            <div className="h-9 w-9 rounded-2xl bg-amber-400/20 text-amber-600 dark:text-amber-400 flex items-center justify-center shrink-0 mt-0.5"><Medal size={15} /></div>
                            <div className="flex-1">
                              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{a.title}</p>
                              {a.description && <p className="text-xs text-slate-500 mt-0.5">{a.description}</p>}
                              {a.awarded_by && <p className="text-[11px] text-amber-600/80 dark:text-amber-400/80 mt-0.5">Awarded by {a.awarded_by}</p>}
                            </div>
                            <span className="text-xs text-slate-400 whitespace-nowrap">{a.date || ""}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  {(data.attendance_history || []).length > 0 && (
                    <Card testid="portal-attendance-history">
                      <CardHead icon={History} title="Attendance History" right={`streak: ${streakLabel} · last ${data.attendance_history.length} days`} />
                      <div className="px-6 py-4 flex flex-wrap gap-2">
                        {data.attendance_history.map((h, i) => {
                          const st = String(h.status || "").toLowerCase();
                          const cls = st.startsWith("p") ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300"
                            : st.startsWith("l") ? "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300"
                            : "bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-300";
                          return <span key={i} className={`px-3 py-1 rounded-xl text-xs font-semibold ${cls}`} data-testid={`portal-att-${h.date}`}>{h.date} · {st.charAt(0).toUpperCase() + st.slice(1)}</span>;
                        })}
                      </div>
                    </Card>
                  )}
                </>
              )}
            </>
          )}
        </main>
      </div>

      <BottomNav
        items={[
          { key: "dashboard", label: "Home", icon: LayoutDashboard },
          { key: "homework", label: "Homework", icon: BookMarked },
          { key: "timetable", label: "Timetable", icon: Table2 },
          { key: "ai-tutor", label: "Tutor", icon: Sparkles },
          { key: "__more", label: "More", icon: Menu },
        ]}
        active={page}
        onSelect={(k) => (k === "__more" ? setMoreOpen(true) : setPage(k))}
      />

      {moreOpen && (
        <div className="md:hidden fixed inset-0 z-40 flex items-end" data-testid="portal-more-sheet">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMoreOpen(false)} />
          <div className="relative w-full rounded-t-3xl bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 p-4 pb-8 animate-in slide-in-from-bottom duration-200">
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-slate-300 dark:bg-slate-700" />
            <div className="grid grid-cols-3 gap-3">
              {NAV.map((n) => (
                <button key={n.key} onClick={() => { setPage(n.key); setMoreOpen(false); }} data-testid={`portal-more-${n.key}`}
                  className={`flex flex-col items-center gap-1.5 rounded-2xl border p-3 text-xs font-semibold min-h-[72px] justify-center ${page === n.key ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400" : "border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300"}`}>
                  <n.icon size={20} /> {n.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const TONES = {
  emerald: "bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800/60 text-emerald-950 dark:text-emerald-100",
  sky: "bg-sky-50 dark:bg-sky-950/40 border-sky-200 dark:border-sky-800/60 text-sky-950 dark:text-sky-100",
  purple: "bg-purple-50 dark:bg-purple-950/40 border-purple-200 dark:border-purple-800/60 text-purple-950 dark:text-purple-100",
  orange: "bg-orange-50 dark:bg-orange-950/40 border-orange-200 dark:border-orange-800/60 text-orange-950 dark:text-orange-100",
};

const Stat = ({ icon: Icon, label, value, sub, tone, testid }) => (
  <div className={`rounded-2xl border-2 p-4 shadow-sm hover:scale-[1.02] transition-transform duration-300 ${TONES[tone]}`} data-testid={testid}>
    <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide opacity-70"><Icon size={14} /> {label}</div>
    <p className="mt-1.5 font-heading text-2xl md:text-3xl font-bold">{value}</p>
    {sub && <p className="text-xs opacity-60 mt-0.5 font-medium">{sub}</p>}
  </div>
);

const Field = ({ label, value, testid }) => (
  <div data-testid={testid}>
    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</p>
    <p className="text-sm font-medium text-slate-800 dark:text-slate-200 mt-0.5">{value || "—"}</p>
  </div>
);
