import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft, ChevronRight, Users2, GraduationCap, BookOpen, CalendarRange,
  Pencil, Save, Check, X, Crown, Medal, LayoutDashboard, FileBarChart,
} from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Switch } from "../../components/ui/switch";
import MonthlyReportDialog from "../../components/MonthlyReportDialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";
import SubjectStaff from "./SubjectStaff";
import GradeTimetable from "./timetable/GradeTimetable";

const NONE = "__none__";
const TABS = [
  { key: "subjects", label: "Subjects & Teachers", icon: BookOpen },
  { key: "students", label: "Students", icon: GraduationCap },
  { key: "timetable", label: "Timetable", icon: CalendarRange },
];

export default function SectionDetailPage() {
  const { classId, sectionId } = useParams();
  const [sp, setSp] = useSearchParams();
  const navigate = useNavigate();
  const tab = TABS.some((t) => t.key === sp.get("tab")) ? sp.get("tab") : "subjects";
  const fromTab = sp.get("from") || "overview";
  const [data, setData] = useState(null);
  const [teachers, setTeachers] = useState([]);
  const [year, setYear] = useState("");
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState({});
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState("");
  const [showReport, setShowReport] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/classes/${classId}/detail`);
      setData(data);
    } catch (e) { toast.error(errText(e)); }
  }, [classId]);

  useEffect(() => {
    load();
    api.get("/lookup/teachers_by_id").then((r) => setTeachers(r.data)).catch(() => {});
    api.get("/res/academic_years?limit=100").then((r) => {
      const items = r.data.items || [];
      const a = items.find((y) => y.status === "active") || items[0];
      if (a) setYear(a.name);
    }).catch(() => {});
  }, [load]);

  const sec = data?.sections?.find((s) => s.id === sectionId);
  useEffect(() => {
    if (sec) {
      setForm({ class_teacher_id: sec.class_teacher_id || "", class_leader_id: sec.class_leader_id || "",
        second_leader_id: sec.second_leader_id || "", capacity: sec.capacity || "", room: sec.room || "",
        class_teacher_first_period: !!sec.class_teacher_first_period });
      setName(sec.name);
    }
  }, [sec?.id]); // eslint-disable-line

  if (!data) return <div className="py-16 text-center text-slate-400" data-testid="section-detail-loading">Loading…</div>;
  if (!sec) return <div className="py-16 text-center text-slate-400" data-testid="section-not-found">Section not found.</div>;

  const cls = data.class;
  const students = data.students.filter((s) => s.section === sec.name);
  const offerings = data.offerings.filter((o) => !o.section || o.section === sec.name);
  const studentOpts = students.map((s) => ({ value: s.id, label: `${s.first_name || ""} ${s.last_name || ""}`.trim() + (s.admission_no ? ` · ${s.admission_no}` : "") }));
  const setTab = (k) => { const n = new URLSearchParams(sp); n.set("tab", k); setSp(n); };

  const saveStaff = async () => {
    try { await api.put(`/res/sections/${sec.id}`, form); toast.success("Section updated"); setEdit(false); load(); }
    catch (e) { toast.error(errText(e)); }
  };
  const doRename = async () => {
    try { await api.put(`/res/sections/${sec.id}`, { name }); toast.success(`Renamed to ${name}`); setRenaming(false); load(); }
    catch (e) { toast.error(errText(e)); }
  };

  return (
    <div className="space-y-6" data-testid="section-detail-page">
      <nav className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400" data-testid="section-breadcrumb">
        <Link to="/app/class-hub" className="text-indigo-600 dark:text-indigo-400 hover:underline inline-flex items-center gap-1"><ArrowLeft size={13} /> Class Hub</Link>
        <ChevronRight size={13} className="opacity-50" />
        <Link to={`/app/class-hub/${classId}?tab=${fromTab}`} className="text-indigo-600 dark:text-indigo-400 hover:underline">{cls.name}</Link>
        <ChevronRight size={13} className="opacity-50" />
        <span className="font-medium text-slate-700 dark:text-slate-200">Section {sec.name}</span>
      </nav>

      {/* Header + inline staff editor */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid="section-header">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {renaming ? (
              <span className="flex items-center gap-2">
                <Input value={name} onChange={(e) => setName(e.target.value)} className="w-28 h-9" data-testid="section-rename-input" />
                <Button size="sm" className="bg-indigo-700 hover:bg-indigo-800 text-white" onClick={doRename} data-testid="section-rename-save"><Check size={14} /></Button>
                <Button size="sm" variant="ghost" onClick={() => { setRenaming(false); setName(sec.name); }}><X size={14} /></Button>
              </span>
            ) : (
              <>
                <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50">{cls.name} · Section {sec.name}</h1>
                <button onClick={() => setRenaming(true)} title="Rename section" data-testid="section-rename-btn" className="text-slate-400 hover:text-indigo-600 transition-colors"><Pencil size={16} /></button>
              </>
            )}
          </div>
          <div className="flex items-center gap-4 text-sm text-slate-500">
            <span className="inline-flex items-center gap-1.5"><GraduationCap size={14} /> {students.length} students</span>
            <span className="inline-flex items-center gap-1.5"><BookOpen size={14} /> {offerings.length} subjects</span>
            <Button size="sm" variant="outline" onClick={() => setShowReport(true)} data-testid="section-monthly-report-btn"><FileBarChart size={13} className="mr-1" /> Monthly Report</Button>
            {!edit && <Button size="sm" variant="outline" onClick={() => setEdit(true)} data-testid="section-edit-btn"><Pencil size={13} className="mr-1" /> Edit staff</Button>}
          </div>
        </div>

        {edit ? (
          <div className="mt-4 space-y-4">
            <div className="grid gap-4 sm:grid-cols-3">
              <LeadSelect label="Class teacher" icon={Users2} testid="section-class-teacher" value={form.class_teacher_id} options={teachers} onChange={(v) => setForm((f) => ({ ...f, class_teacher_id: v }))} placeholder="Pick a teacher" />
              <LeadSelect label="Class leader" icon={Crown} testid="section-class-leader" value={form.class_leader_id} options={studentOpts} onChange={(v) => setForm((f) => ({ ...f, class_leader_id: v }))} placeholder="Pick a student" />
              <LeadSelect label="Second leader" icon={Medal} testid="section-second-leader" value={form.second_leader_id} options={studentOpts} onChange={(v) => setForm((f) => ({ ...f, second_leader_id: v }))} placeholder="Pick a student" />
              <div className="space-y-1"><label className="text-xs font-medium text-slate-600 dark:text-slate-400">Capacity</label><Input type="number" value={form.capacity} onChange={(e) => setForm((f) => ({ ...f, capacity: e.target.value }))} data-testid="section-capacity" /></div>
              <div className="space-y-1"><label className="text-xs font-medium text-slate-600 dark:text-slate-400">Room</label><Input value={form.room} onChange={(e) => setForm((f) => ({ ...f, room: e.target.value }))} data-testid="section-room" /></div>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={!!form.class_teacher_first_period} onCheckedChange={(v) => setForm((f) => ({ ...f, class_teacher_first_period: v }))} data-testid="section-first-period" />
              <span className="text-sm text-slate-600 dark:text-slate-300">Class teacher takes Period 1</span>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setEdit(false)}>Cancel</Button>
              <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" onClick={saveStaff} data-testid="section-save-staff"><Save size={14} className="mr-1" /> Save</Button>
            </div>
          </div>
        ) : (
          <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-1 text-sm text-slate-600 dark:text-slate-300">
            <span className="inline-flex items-center gap-1.5"><Users2 size={14} className="text-indigo-500" /> {sec.class_teacher || <span className="text-slate-400">No class teacher</span>}</span>
            {sec.room && <span>Room {sec.room}</span>}
            {sec.capacity ? <span>Capacity {sec.capacity}</span> : null}
            {sec.class_teacher_first_period && <span className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 bg-blue-50 dark:bg-blue-500/10 rounded-full px-2 py-0.5">Period 1 reserved for class teacher</span>}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-slate-200 dark:border-slate-800" data-testid="section-tabs">
        {TABS.map((t) => {
          const Icon = t.icon; const active = tab === t.key;
          return (
            <button key={t.key} onClick={() => setTab(t.key)} data-testid={`section-tab-${t.key}`}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${active ? "border-indigo-600 text-indigo-700 dark:text-indigo-300" : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"}`}>
              <Icon size={15} /> {t.label}
            </button>
          );
        })}
      </div>

      <div data-testid={`section-panel-${tab}`}>
        {tab === "subjects" && (year
          ? <SubjectStaff className={cls.name} year={year} initialSection={sec.name} lockSection />
          : <p className="text-sm text-slate-400">Create an academic year first.</p>)}
        {tab === "students" && (
          students.length === 0 ? <p className="text-sm text-slate-400" data-testid="section-no-students">No students enrolled in this section yet.</p> : (
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-900/60 text-left"><tr>{["Student", "Adm. No."].map((h) => <th key={h} className="px-4 py-2 text-xs font-semibold uppercase tracking-wider text-slate-500">{h}</th>)}</tr></thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                  {students.map((s) => (
                    <tr key={s.id} data-testid={`section-student-${s.id}`}>
                      <td className="px-4 py-2.5 font-medium text-slate-700 dark:text-slate-200">{`${s.first_name || ""} ${s.last_name || ""}`.trim()}</td>
                      <td className="px-4 py-2.5 text-slate-500">{s.admission_no || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
        {tab === "timetable" && (year
          ? <GradeTimetable year={year} initialClass={cls.name} initialSection={sec.name} />
          : <p className="text-sm text-slate-400">Create an academic year first.</p>)}
      </div>
      {showReport && <MonthlyReportDialog classId={classId} className={cls.name} onClose={() => setShowReport(false)} />}
    </div>
  );
}

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
