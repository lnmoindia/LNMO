import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft, Layers, Users2, Rows3, BookOpen, Trophy, Plus, Trash2,
  GraduationCap, Crown, Medal, Save, ChevronRight, LayoutDashboard,
  CalendarRange, ExternalLink, UserCog, Printer,
} from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { printReportCard } from "../../lib/printDoc";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";
import { Switch } from "../../components/ui/switch";
import InlineList from "./InlineList";
import SubjectStaff from "./SubjectStaff";
import GradeTimetable from "./timetable/GradeTimetable";

const NONE = "__none__";

const TABS = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "staff", label: "Sections & Staff", icon: UserCog },
  { key: "subjects", label: "Subjects & Teachers", icon: BookOpen },
  { key: "students", label: "Students", icon: GraduationCap },
  { key: "timetable", label: "Timetable", icon: CalendarRange },
];

export default function ClassDetailPage() {
  const { classId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = TABS.some((t) => t.key === searchParams.get("tab")) ? searchParams.get("tab") : "overview";
  const [data, setData] = useState(null);
  const [teachers, setTeachers] = useState([]);
  const [year, setYear] = useState("");
  const [subjectsDirty, setSubjectsDirty] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/classes/${classId}/detail`);
      setData(data);
    } catch (e) {
      toast.error(errText(e));
    }
  }, [classId]);

  useEffect(() => {
    load();
    api.get("/lookup/teachers_by_id").then((r) => setTeachers(r.data)).catch(() => setTeachers([]));
    api.get("/res/academic_years?limit=100").then((r) => {
      const items = r.data.items || [];
      const active = items.find((y) => y.status === "active") || items[0];
      if (active) setYear(active.name);
    }).catch(() => {});
  }, [load]);

  const setTab = (key) => {
    if (subjectsDirty && tab === "subjects" && key !== "subjects") {
      if (!window.confirm("You have unsaved teacher changes. Leave without saving?")) return;
      setSubjectsDirty(false);
    }
    const next = new URLSearchParams(searchParams);
    if (key === "overview") next.delete("tab"); else next.set("tab", key);
    setSearchParams(next);
  };

  if (!data) return <div className="py-16 text-center text-slate-400" data-testid="class-detail-loading">Loading class…</div>;

  const cls = data.class;
  const sections = data.sections;
  const studentsInSec = (name) => data.students.filter((s) => s.section === name);
  const offeringsInSec = (name) => data.offerings.filter((o) => !o.section || o.section === name);
  const activeTab = TABS.find((t) => t.key === tab);

  return (
    <div className="space-y-6" data-testid="class-detail-page">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400" data-testid="class-breadcrumb">
        <Link to="/app/class-hub" className="inline-flex items-center gap-1 text-indigo-600 dark:text-indigo-400 hover:underline" data-testid="back-to-class-hub">
          <ArrowLeft size={13} /> Class Hub
        </Link>
        <ChevronRight size={13} className="opacity-50" />
        <span className="font-medium text-slate-700 dark:text-slate-200">{cls.name}</span>
        <ChevronRight size={13} className="opacity-50" />
        <span>{activeTab?.label}</span>
      </nav>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50" data-testid="class-detail-name">{cls.name}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 flex items-center gap-2">
            <span className="inline-flex items-center gap-1"><Layers size={13} /> {data.unit?.name || cls.academic_unit_name || "—"}</span>
            {cls.grade_level && <span>· Grade level {cls.grade_level}</span>}
          </p>
        </div>
        <div className="flex items-center gap-4 text-sm text-slate-500 dark:text-slate-400" data-testid="class-detail-stats">
          <span className="inline-flex items-center gap-1.5"><Rows3 size={14} /> {sections.length} sec</span>
          <span className="inline-flex items-center gap-1.5"><BookOpen size={14} /> {new Set(data.offerings.map((o) => o.subject)).size} subj</span>
          <span className="inline-flex items-center gap-1.5"><GraduationCap size={14} /> {data.students.length} std</span>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex items-center gap-1 border-b border-slate-200 dark:border-slate-800 overflow-x-auto" data-testid="class-detail-tabs">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.key;
          return (
            <button key={t.key} onClick={() => setTab(t.key)} data-testid={`class-tab-${t.key}`}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors ${
                active ? "border-indigo-600 text-indigo-700 dark:text-indigo-300" : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
              }`}>
              <Icon size={15} /> {t.label}
            </button>
          );
        })}
      </div>

      <div data-testid={`class-panel-${tab}`}>
        {tab === "overview" && (
          <OverviewTab cls={cls} classId={classId} navigate={navigate} sections={sections} studentsInSec={studentsInSec} offeringsInSec={offeringsInSec} setTab={setTab} />
        )}
        {tab === "staff" && (
          <StaffTab classId={classId} cls={cls} sections={sections} teachers={teachers} students={data.students} reload={load} />
        )}
        {tab === "subjects" && (
          year ? <SubjectStaff className={cls.name} year={year} onDirtyChange={setSubjectsDirty} />
            : <p className="text-sm text-slate-400">Create an academic year first.</p>
        )}
        {tab === "students" && (
          <StudentsTab data={data} reload={load} navigate={navigate} />
        )}
        {tab === "timetable" && (
          <div className="space-y-4" data-testid="class-timetable-tab">
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-500 dark:text-slate-400">The schedule grid for {cls.name}. Pick a section below to view or edit.</p>
              <Link to="/app/timetable" className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-600 px-3 py-1.5 text-sm font-medium text-indigo-700 dark:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition-colors" data-testid="open-full-timetable">
                <ExternalLink size={14} /> Open full editor
              </Link>
            </div>
            {year ? <GradeTimetable year={year} initialClass={cls.name} /> : <p className="text-sm text-slate-400">Create an academic year first.</p>}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- Overview ---------------- */
const OverviewTab = ({ cls, classId, navigate, sections, studentsInSec, offeringsInSec, setTab }) => (
  <div className="space-y-5" data-testid="overview-tab">
    {sections.length === 0 ? (
      <div className="rounded-xl border border-dashed border-slate-300 dark:border-slate-700 p-8 text-center">
        <p className="text-sm text-slate-500">No sections yet. Add sections in the <button onClick={() => setTab("staff")} className="font-medium text-indigo-600 hover:underline">Sections &amp; Staff</button> tab.</p>
      </div>
    ) : (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {sections.map((s) => (
          <div key={s.id} onClick={() => navigate(`/app/class-hub/${classId}/section/${s.id}?from=overview`)} role="button" tabIndex={0}
            className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 cursor-pointer hover:border-indigo-400 hover:shadow-md transition-all" data-testid={`overview-section-${s.name}`}>
            <div className="flex items-center justify-between">
              <h3 className="font-heading text-lg font-bold text-slate-900 dark:text-slate-50">Section {s.name}</h3>
              {s.room && <span className="text-xs text-slate-400">Room {s.room}</span>}
            </div>
            <div className="mt-3 flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300">
              <Users2 size={14} className="text-indigo-500" />
              <span className={s.class_teacher ? "font-medium" : "text-slate-400"}>{s.class_teacher || "No class teacher"}</span>
            </div>
            <div className="mt-2 flex items-center gap-4 text-sm text-slate-500">
              <span className="inline-flex items-center gap-1.5"><GraduationCap size={14} /> {studentsInSec(s.name).length} students</span>
              <span className="inline-flex items-center gap-1.5"><BookOpen size={14} /> {offeringsInSec(s.name).length} subjects</span>
            </div>
          </div>
        ))}
      </div>
    )}
    <div className="flex flex-wrap gap-2">
      <QuickLink onClick={() => setTab("staff")} icon={UserCog} label="Manage sections & class teachers" />
      <QuickLink onClick={() => setTab("subjects")} icon={BookOpen} label="Assign subject teachers" />
      <QuickLink onClick={() => setTab("students")} icon={GraduationCap} label="View students" />
      <QuickLink onClick={() => setTab("timetable")} icon={CalendarRange} label="Open timetable" />
    </div>
  </div>
);

const QuickLink = ({ onClick, icon: Icon, label }) => (
  <button onClick={onClick} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 dark:border-slate-700 px-3.5 py-2 text-sm font-medium text-slate-700 dark:text-slate-200 hover:border-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors" data-testid={`quicklink-${label.split(" ")[0].toLowerCase()}`}>
    <Icon size={15} className="text-indigo-500" /> {label}
  </button>
);

/* ---------------- Sections & Staff ---------------- */
const StaffTab = ({ classId, cls, sections, teachers, students, reload }) => {
  const [leaders, setLeaders] = useState({});
  const [savingId, setSavingId] = useState("");

  useEffect(() => {
    const m = {};
    sections.forEach((s) => { m[s.id] = { class_teacher_id: s.class_teacher_id || "", class_leader_id: s.class_leader_id || "", second_leader_id: s.second_leader_id || "", class_teacher_first_period: !!s.class_teacher_first_period }; });
    setLeaders(m);
  }, [sections]);

  const teacherSectionCount = useMemo(() => {
    const c = {};
    sections.forEach((s) => { if (s.class_teacher_id) c[s.class_teacher_id] = (c[s.class_teacher_id] || 0) + 1; });
    return c;
  }, [sections]);

  const studentOpts = (secName) => students.filter((s) => s.section === secName).map((s) => ({
    value: s.id, label: `${s.first_name || ""} ${s.last_name || ""}`.trim() + (s.admission_no ? ` · ${s.admission_no}` : ""),
  }));

  const pickClassTeacher = (sec, tid) => {
    const prev = sec.class_teacher_id;
    if (tid && tid !== prev && (teacherSectionCount[tid] || 0) >= 2) {
      const t = teachers.find((x) => x.value === tid);
      toast.warning(`${t?.label?.split(" (")[0] || "This teacher"} already leads 2 sections — assigning anyway.`);
    }
    setLeaders((l) => ({ ...l, [sec.id]: { ...l[sec.id], class_teacher_id: tid } }));
  };

  const saveSection = async (sec) => {
    setSavingId(sec.id);
    try {
      await api.put(`/res/sections/${sec.id}`, leaders[sec.id]);
      toast.success(`Section ${sec.name} staff updated`);
      reload();
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setSavingId("");
    }
  };

  return (
    <div className="space-y-6" data-testid="staff-tab">
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
        <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2 mb-1"><Rows3 size={16} className="text-indigo-600" /> Sections</h2>
        <p className="text-xs text-slate-400 mb-4">Add, rename or remove sections for {cls.name}.</p>
        <InlineList
          testid="class-sections"
          endpoint="res/sections"
          onChange={reload}
          extra={{ class_name: cls.name }}
          hideFields={["class_name"]}
          filter={(i) => i.class_name === cls.name}
          fields={[
            { name: "name", label: "Section", required: true, placeholder: "A" },
            { name: "class_name", label: "Class", optionsUrl: "lookup/classes", required: true },
            { name: "capacity", label: "Capacity", type: "number" },
            { name: "room", label: "Room" },
          ]}
          columns={[
            { key: "name", label: "Section" },
            { key: "class_teacher", label: "Class teacher", render: (r) => r.class_teacher || "—" },
            { key: "capacity", label: "Capacity" },
            { key: "room", label: "Room" },
          ]}
        />
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4" data-testid="class-leadership">
        <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Users2 size={16} className="text-indigo-600" /> Class teacher &amp; leaders per section</h2>
        {sections.length === 0 ? <p className="text-sm text-slate-400">Add a section first.</p> : sections.map((sec) => (
          <div key={sec.id} className="rounded-lg border border-slate-100 dark:border-slate-800 p-4" data-testid={`staff-section-${sec.name}`}>
            <div className="flex items-center justify-between mb-3">
              <span className="font-medium text-slate-800 dark:text-slate-200">Section {sec.name}</span>
              <Button size="sm" onClick={() => saveSection(sec)} disabled={savingId === sec.id} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid={`save-staff-${sec.name}`}>
                <Save size={13} className="mr-1" /> {savingId === sec.id ? "Saving…" : "Save"}
              </Button>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <LeadSelect label="Class teacher" icon={Users2} testid={`class-teacher-${sec.name}`} placeholder="Pick a teacher"
                value={leaders[sec.id]?.class_teacher_id} onChange={(v) => pickClassTeacher(sec, v)} options={teachers} />
              <LeadSelect label="Class leader" icon={Crown} testid={`class-leader-${sec.name}`} placeholder="Pick a student"
                value={leaders[sec.id]?.class_leader_id} onChange={(v) => setLeaders((l) => ({ ...l, [sec.id]: { ...l[sec.id], class_leader_id: v } }))} options={studentOpts(sec.name)} />
              <LeadSelect label="Second leader" icon={Medal} testid={`second-leader-${sec.name}`} placeholder="Pick a student"
                value={leaders[sec.id]?.second_leader_id} onChange={(v) => setLeaders((l) => ({ ...l, [sec.id]: { ...l[sec.id], second_leader_id: v } }))} options={studentOpts(sec.name)} />
            </div>
            <div className="mt-3 flex items-center gap-2 pt-3 border-t border-slate-100 dark:border-slate-800">
              <Switch checked={!!leaders[sec.id]?.class_teacher_first_period}
                onCheckedChange={(v) => setLeaders((l) => ({ ...l, [sec.id]: { ...l[sec.id], class_teacher_first_period: v } }))}
                data-testid={`first-period-${sec.name}`} />
              <span className="text-sm text-slate-600 dark:text-slate-300">Class teacher takes Period 1</span>
              <span className="text-xs text-slate-400">— timetable generation reserves P1 each day for the class teacher's subject</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const LeadSelect = ({ label, icon: Icon, value, onChange, options, testid, placeholder }) => (
  <div className="space-y-1">
    <label className="text-xs font-medium text-slate-600 dark:text-slate-400 flex items-center gap-1.5"><Icon size={13} /> {label}</label>
    <Select value={value || NONE} onValueChange={(v) => onChange(v === NONE ? "" : v)}>
      <SelectTrigger data-testid={testid}><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}><span className="text-slate-400">Not set</span></SelectItem>
        {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
      </SelectContent>
    </Select>
  </div>
);

/* ---------------- Students ---------------- */
const StudentsTab = ({ data, reload, navigate }) => {
  const [achOpen, setAchOpen] = useState(false);
  const [ach, setAch] = useState({ student_id: "", title: "", description: "", date: "" });
  const [savingAch, setSavingAch] = useState(false);

  const students = data.students;
  const achievements = data.achievements;
  const studentOpts = students.map((s) => ({ value: s.id, label: `${s.first_name || ""} ${s.last_name || ""}`.trim() + (s.admission_no ? ` · ${s.admission_no}` : "") }));
  const achCountByStudent = {};
  achievements.forEach((a) => { achCountByStudent[a.student_id] = (achCountByStudent[a.student_id] || 0) + 1; });
  const leadersBySection = {};
  data.sections.forEach((s) => { leadersBySection[s.name] = { leader: s.class_leader_id, second: s.second_leader_id }; });

  const openAchFor = (sid) => { setAch({ student_id: sid || "", title: "", description: "", date: "" }); setAchOpen(true); };

  const addAchievement = async () => {
    setSavingAch(true);
    try {
      await api.post("/res/achievements", ach);
      toast.success("Achievement added");
      setAchOpen(false);
      reload();
    } catch (e) { toast.error(errText(e)); } finally { setSavingAch(false); }
  };
  const removeAchievement = async (id) => {
    try { await api.delete(`/res/achievements/${id}`); reload(); } catch (e) { toast.error(errText(e)); }
  };
  const openReportCard = async (sid) => {
    try { const { data } = await api.get(`/students/${sid}/report-card`); printReportCard(data); } catch (e) { toast.error(errText(e)); }
  };

  return (
    <div className="space-y-6" data-testid="students-tab">
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 dark:border-slate-800">
          <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><GraduationCap size={16} className="text-indigo-600" /> Students</h2>
          <Button size="sm" variant="outline" onClick={() => openAchFor("")} data-testid="add-achievement-btn"><Trophy size={14} className="mr-1" /> Add achievement</Button>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-900/60 text-left">
            <tr>{["Student", "Adm. No.", "Section", "Achievements", ""].map((h) => (
              <th key={h} className="px-4 py-2 text-xs font-semibold uppercase tracking-wider text-slate-500">{h}</th>))}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {students.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-400">No students enrolled yet.</td></tr>
            ) : students.map((s) => {
              const secLead = leadersBySection[s.section] || {};
              return (
                <tr key={s.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40" data-testid={`class-student-${s.id}`}>
                  <td className="px-4 py-2.5 text-slate-700 dark:text-slate-200 font-medium">
                    <button onClick={() => navigate(`/app/students/${s.id}`)} className="hover:text-indigo-600 hover:underline text-left" data-testid={`open-student-profile-${s.id}`}>
                      {`${s.first_name || ""} ${s.last_name || ""}`.trim()}
                    </button>
                    {secLead.leader === s.id && <span className="ml-2 inline-flex items-center gap-1 text-[11px] font-medium text-amber-600"><Crown size={11} /> Leader</span>}
                    {secLead.second === s.id && <span className="ml-2 inline-flex items-center gap-1 text-[11px] font-medium text-slate-500"><Medal size={11} /> 2nd</span>}
                  </td>
                  <td className="px-4 py-2.5 text-slate-500">{s.admission_no || "—"}</td>
                  <td className="px-4 py-2.5 text-slate-500">{s.section || "—"}</td>
                  <td className="px-4 py-2.5 text-slate-500">{achCountByStudent[s.id] ? <span className="inline-flex items-center gap-1 text-amber-600 font-medium"><Trophy size={12} /> {achCountByStudent[s.id]}</span> : <span className="text-slate-300 dark:text-slate-600">—</span>}</td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    <button onClick={() => openReportCard(s.id)} title="Print report card" data-testid={`report-card-${s.id}`} className="text-slate-400 hover:text-indigo-600 transition-colors mr-2"><Printer size={15} /></button>
                    <button onClick={() => openAchFor(s.id)} title="Add achievement" data-testid={`add-ach-${s.id}`} className="text-slate-400 hover:text-amber-600 transition-colors"><Plus size={15} /></button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden" data-testid="class-achievements-card">
        <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
          <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Trophy size={16} className="text-amber-500" /> Achievements</h2>
        </div>
        {achievements.length === 0 ? (
          <p className="px-5 py-6 text-sm text-slate-400">No achievements recorded yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900/60 text-left">
              <tr>{["Student", "Achievement", "Details", "Date", ""].map((h) => (
                <th key={h} className="px-4 py-2 text-xs font-semibold uppercase tracking-wider text-slate-500">{h}</th>))}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {achievements.map((a) => (
                <tr key={a.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40" data-testid={`achievement-row-${a.id}`}>
                  <td className="px-4 py-2.5 text-slate-700 dark:text-slate-200 font-medium">{a.student_name}</td>
                  <td className="px-4 py-2.5 text-slate-700 dark:text-slate-300">{a.title}</td>
                  <td className="px-4 py-2.5 text-slate-500">{a.description || "—"}</td>
                  <td className="px-4 py-2.5 text-slate-500">{a.date || "—"}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button onClick={() => removeAchievement(a.id)} data-testid={`delete-ach-${a.id}`} className="text-slate-400 hover:text-red-600 transition-colors"><Trash2 size={15} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Dialog open={achOpen} onOpenChange={setAchOpen}>
        <DialogContent className="sm:max-w-md" data-testid="achievement-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Trophy size={17} className="text-amber-500" /> Add achievement</DialogTitle>
            <DialogDescription>Record an award or recognition for a student in {data.class.name}.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-1">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Student <span className="text-red-500">*</span></label>
              <Select value={ach.student_id} onValueChange={(v) => setAch((a) => ({ ...a, student_id: v }))}>
                <SelectTrigger data-testid="ach-student-select"><SelectValue placeholder="Pick a student" /></SelectTrigger>
                <SelectContent>{studentOpts.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Title <span className="text-red-500">*</span></label>
              <Input value={ach.title} onChange={(e) => setAch((a) => ({ ...a, title: e.target.value }))} placeholder="e.g. 1st place — Science Fair" data-testid="ach-title-input" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Details</label>
              <Input value={ach.description} onChange={(e) => setAch((a) => ({ ...a, description: e.target.value }))} placeholder="Optional description" data-testid="ach-desc-input" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Date</label>
              <Input type="date" value={ach.date} onChange={(e) => setAch((a) => ({ ...a, date: e.target.value }))} data-testid="ach-date-input" />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={() => setAchOpen(false)} data-testid="ach-cancel-btn">Cancel</Button>
              <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" disabled={!ach.student_id || !ach.title.trim() || savingAch} onClick={addAchievement} data-testid="ach-save-btn">{savingAch ? "Saving…" : "Save achievement"}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
