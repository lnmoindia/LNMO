import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Layers, Users2, Rows3, GraduationCap, ClipboardList, BookOpen, CalendarCheck, LayoutList, School, FlaskConical, ExternalLink } from "lucide-react";
import api from "../../lib/api";
import InlineList from "./InlineList";
import BulkOfferDialog from "./BulkOfferDialog";

const TABS = [
  { key: "classes", label: "Classes", icon: School },
  { key: "sections", label: "Sections", icon: Rows3 },
  { key: "enrollments", label: "Enrollments", icon: GraduationCap },
  { key: "teachers", label: "Teacher Assignments", icon: ClipboardList },
  { key: "offerings", label: "Subject Offerings", icon: BookOpen },
];

export default function ClassHub() {
  const [units, setUnits] = useState([]);
  const [classes, setClasses] = useState([]);
  const [sections, setSections] = useState([]);
  const [enrollments, setEnrollments] = useState([]);
  const [offerings, setOfferings] = useState([]);
  const [selectedId, setSelectedId] = useState("all");
  const [tab, setTab] = useState("classes");
  const [bulkOpen, setBulkOpen] = useState(false);

  const refresh = useCallback(async () => {
    const safe = (p) => p.then((r) => r.data.items || []).catch(() => []);
    const [u, c, s, e, o] = await Promise.all([
      safe(api.get("/res/academic_units", { params: { limit: 200 } })),
      safe(api.get("/res/classes", { params: { limit: 500 } })),
      safe(api.get("/res/sections", { params: { limit: 500 } })),
      safe(api.get("/res/enrollments", { params: { limit: 500 } })),
      safe(api.get("/res/subject_offerings", { params: { limit: 500 } })),
    ]);
    setUnits((u || []).sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)));
    setClasses(c || []);
    setSections(s || []);
    setEnrollments(e || []);
    setOfferings(o || []);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const selected = selectedId === "all" ? null : classes.find((c) => c.id === selectedId);
  const selectedUnit = selected ? units.find((u) => u.id === selected.academic_unit_id) : null;

  const counts = useMemo(() => {
    const by = {};
    classes.forEach((c) => {
      by[c.name] = {
        sections: sections.filter((s) => s.class_name === c.name).length,
        students: new Set(enrollments.filter((e) => e.class_name === c.name).map((e) => e.student_id)).size,
        offerings: offerings.filter((o) => o.class_name === c.name).length,
      };
    });
    return by;
  }, [classes, sections, enrollments, offerings]);

  const grouped = useMemo(() => {
    const groups = units.map((u) => ({ unit: u, classes: classes.filter((c) => c.academic_unit_id === u.id) }));
    const orphan = classes.filter((c) => !units.some((u) => u.id === c.academic_unit_id));
    if (orphan.length) groups.push({ unit: { id: "none", name: "Unassigned" }, classes: orphan });
    return groups.filter((g) => g.classes.length > 0);
  }, [units, classes]);

  const scoped = selected
    ? { extra: { class_name: selected.name }, hideFields: ["class_name"], filter: (i) => i.class_name === selected.name }
    : {};

  return (
    <div className="space-y-6" data-testid="class-hub">
      <div>
        <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">Academics</p>
        <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50">Class Hub</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Pick a class to manage its sections, subject offerings, teachers and enrolled students — all in one place.
        </p>
      </div>

      {/* Class selector rail */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-4" data-testid="class-selector">
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setSelectedId("all")}
            data-testid="class-chip-all"
            className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
              selectedId === "all" ? "bg-indigo-700 text-white border-indigo-700" : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-indigo-400"
            }`}
          >
            <LayoutList size={14} className="inline mr-1.5 align-text-bottom" /> All classes
          </button>
        </div>
        {grouped.length === 0 && (
          <p className="text-sm text-slate-400">No classes yet. Add your first class in the <span className="font-medium">Classes</span> tab below.</p>
        )}
        {grouped.map((g) => (
          <div key={g.unit.id} className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Layers size={12} /> {g.unit.name}
            </p>
            <div className="flex items-center gap-2 flex-wrap">
              {g.classes.map((c) => {
                const active = selectedId === c.id;
                const ct = counts[c.name] || {};
                return (
                  <button
                    key={c.id}
                    onClick={() => setSelectedId(c.id)}
                    data-testid={`class-chip-${c.name}`}
                    className={`text-left px-3.5 py-2 rounded-lg border transition-colors ${
                      active ? "bg-indigo-50 dark:bg-indigo-500/10 border-indigo-500" : "border-slate-200 dark:border-slate-700 hover:border-indigo-400"
                    }`}
                  >
                    <span className={`block text-sm font-semibold ${active ? "text-indigo-700 dark:text-indigo-300" : "text-slate-800 dark:text-slate-200"}`}>{c.name}</span>
                    <span className="block text-[11px] text-slate-400 mt-0.5">{ct.sections || 0} sec · {ct.students || 0} std · {ct.offerings || 0} subj</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Selected class summary */}
      {selected && (
        <div className="space-y-3">
          <div className="flex justify-end">
            <Link
              to={`/app/class-hub/${selected.id}`}
              data-testid="open-class-detail"
              className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-600 px-3 py-1.5 text-sm font-medium text-indigo-700 dark:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition-colors"
            >
              <ExternalLink size={14} /> Open class page — leadership & achievements
            </Link>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="class-summary">
          <SummaryCard icon={Layers} label="Academic Unit" value={selectedUnit?.name || "—"} />
          <SummaryCard icon={Users2} label="Section Teachers" value={(() => { const t = sections.filter((s) => s.class_name === selected.name && s.class_teacher).map((s) => `${s.name}: ${s.class_teacher}`); return t.length ? t.join(" · ") : "Not set"; })()} muted={!sections.some((s) => s.class_name === selected.name && s.class_teacher)} />
          <SummaryCard icon={Rows3} label="Sections" value={counts[selected.name]?.sections || 0} />
          <SummaryCard icon={BookOpen} label="Subjects Offered" value={counts[selected.name]?.offerings || 0} />
          <SummaryCard icon={CalendarCheck} label="Attendance (inherited)" value={selectedUnit?.attendance_model || "—"} sub={selectedUnit?.timetable_required ? "Timetable required" : "No timetable"} />
          </div>
        </div>
      )}

      {/* Tabs */}
      <div>
        <div className="flex items-center gap-1 border-b border-slate-200 dark:border-slate-800 overflow-x-auto" data-testid="class-hub-tabs">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.key;
            return (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                data-testid={`hub-tab-${t.key}`}
                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors ${
                  active ? "border-indigo-600 text-indigo-700 dark:text-indigo-300" : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                }`}
              >
                <Icon size={15} /> {t.label}
              </button>
            );
          })}
        </div>

        <div className="pt-5" data-testid={`hub-panel-${tab}`}>
          {selected && tab !== "classes" && (
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-3">
              Showing <span className="font-medium text-slate-700 dark:text-slate-200">{selected.name}</span> only. New entries are added to this class automatically.
            </p>
          )}

          {tab === "classes" && (
            <InlineList
              testid="hub-classes"
              endpoint="res/classes"
              onChange={refresh}
              fields={[
                { name: "name", label: "Class name", required: true, placeholder: "Grade 6" },
                { name: "academic_unit_id", label: "Academic unit", optionsUrl: "lookup/academic_units", required: true },
                { name: "grade_level", label: "Grade level" },
              ]}
              columns={[
                { key: "name", label: "Class" },
                { key: "academic_unit_name", label: "Unit", render: (r) => r.academic_unit_name || units.find((u) => u.id === r.academic_unit_id)?.name || "—" },
                { key: "grade_level", label: "Grade" },
              ]}
            />
          )}

          {tab === "sections" && (
            <InlineList
              testid="hub-sections"
              endpoint="res/sections"
              onChange={refresh}
              {...scoped}
              fields={[
                { name: "name", label: "Section", required: true, placeholder: "A" },
                { name: "class_name", label: "Class", optionsUrl: "lookup/classes", required: true },
                { name: "capacity", label: "Capacity", type: "number" },
                { name: "room", label: "Room" },
              ]}
              columns={[
                { key: "name", label: "Section" },
                { key: "class_name", label: "Class" },
                { key: "class_teacher", label: "Teacher", render: (r) => r.class_teacher || "—" },
                { key: "capacity", label: "Capacity" },
                { key: "room", label: "Room" },
              ]}
            />
          )}

          {tab === "enrollments" && (
            <InlineList
              testid="hub-enrollments"
              endpoint="res/enrollments"
              onChange={refresh}
              {...scoped}
              fields={[
                { name: "student_id", label: "Student", optionsUrl: "lookup/students", required: true },
                { name: "academic_year", label: "Academic year", optionsUrl: "lookup/academic_years" },
                { name: "class_name", label: "Class", optionsUrl: "lookup/classes", required: true },
                { name: "section", label: "Section", optionsUrl: "lookup/sections", dependsOn: "class_name" },
              ]}
              columns={[
                { key: "student_name", label: "Student" },
                { key: "admission_no", label: "Adm. No." },
                { key: "academic_year", label: "Year" },
                { key: "class_name", label: "Class" },
                { key: "section", label: "Section" },
              ]}
            />
          )}

          {tab === "teachers" && (
            <InlineList
              testid="hub-teachers"
              endpoint="res/teacher_assignments"
              onChange={refresh}
              {...scoped}
              fields={[
                { name: "teacher_email", label: "Teacher (login account)", optionsUrl: "lookup/teacher_users", required: true },
                { name: "class_name", label: "Class", optionsUrl: "lookup/classes", required: true },
                { name: "section", label: "Section", optionsUrl: "lookup/sections", dependsOn: "class_name" },
                { name: "subject", label: "Subject", optionsUrl: "lookup/offered_subjects", dependsOn: "class_name" },
              ]}
              columns={[
                { key: "teacher_name", label: "Teacher" },
                { key: "teacher_email", label: "Email" },
                { key: "class_name", label: "Class" },
                { key: "section", label: "Section" },
                { key: "subject", label: "Subject" },
              ]}
            />
          )}

          {tab === "offerings" && (
            <div className="space-y-4">
              <div className="flex justify-end">
                <button
                  onClick={() => setBulkOpen(true)}
                  data-testid="open-bulk-offer"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-600 px-3 py-1.5 text-sm font-medium text-indigo-700 dark:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition-colors"
                >
                  <BookOpen size={15} /> Bulk-offer a subject
                </button>
              </div>
              <InlineList
                testid="hub-offerings"
                endpoint="res/subject_offerings"
                onChange={refresh}
                {...scoped}
                emptyText="No subjects offered for this class yet."
                fields={[
                  { name: "subject", label: "Subject", optionsUrl: "lookup/subjects", required: true },
                  { name: "class_name", label: "Class", optionsUrl: "lookup/classes", required: true },
                  { name: "section", label: "Section (blank = whole class)", optionsUrl: "lookup/sections", dependsOn: "class_name" },
                  { name: "max_marks", label: "Max marks", type: "number", default: 100, showIf: (f) => !f.has_practical },
                  { name: "has_practical", label: "Has practical / lab", type: "checkbox" },
                  { name: "theory_max_marks", label: "Theory max", type: "number", default: 70, showIf: (f) => f.has_practical },
                  { name: "practical_max_marks", label: "Practical max", type: "number", default: 30, showIf: (f) => f.has_practical },
                ]}
                columns={[
                  { key: "subject", label: "Subject" },
                  { key: "class_name", label: "Class" },
                  { key: "section", label: "Section", render: (r) => r.section || "All sections" },
                  { key: "max_marks", label: "Max marks", render: (r) => r.has_practical
                    ? `${r.theory_max_marks} + ${r.practical_max_marks} = ${r.max_marks}`
                    : (r.max_marks ?? 100) },
                  { key: "has_practical", label: "Type", render: (r) => r.has_practical
                    ? <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700 dark:text-amber-400"><FlaskConical size={12} /> Practical</span>
                    : <span className="text-xs text-slate-400">Theory</span> },
                ]}
              />
            </div>
          )}
        </div>
      </div>
      <BulkOfferDialog open={bulkOpen} onOpenChange={setBulkOpen} units={units} classes={classes} onDone={refresh} />
    </div>
  );
}

const SummaryCard = ({ icon: Icon, label, value, sub, muted }) => (
  <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
    <div className="flex items-center gap-2 text-slate-400 text-xs font-medium uppercase tracking-wide">
      <Icon size={13} /> {label}
    </div>
    <p className={`mt-1.5 font-heading text-lg font-bold capitalize ${muted ? "text-slate-400" : "text-slate-900 dark:text-slate-50"}`}>{value}</p>
    {sub && <p className="text-[11px] text-slate-400 mt-0.5">{sub}</p>}
  </div>
);
