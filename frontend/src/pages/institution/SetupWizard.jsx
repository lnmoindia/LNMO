import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Circle, LogOut, Moon, Sun, ArrowRight, ArrowLeft, Sparkles, Info } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../context/ThemeContext";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";
import InlineList from "./InlineList";
import ApplyPresetCards from "../../components/common/ApplyPresetCards";

const STEPS = [
  { key: "profile", label: "Institution Profile" },
  { key: "academic_config", label: "Academic Configuration" },
  { key: "academic_year", label: "Academic Year" },
  { key: "academic_units", label: "Academic Units" },
  { key: "classes_sections", label: "Classes & Sections" },
  { key: "subjects", label: "Subjects" },
  { key: "teachers", label: "Teachers", optional: true },
  { key: "ready", label: "Ready" },
];

const MODEL_NOTE = (
  <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
    <Info size={13} className="inline align-text-bottom mr-1.5" />
    These models are <span className="font-medium text-slate-600 dark:text-slate-300">configured &amp; partially enforced</span> today (used for readiness &amp; visibility). Deep grading/assessment behaviour differences arrive in a later phase.
  </p>
);

const stepDone = (key, s) => {
  if (!s) return false;
  if (key === "classes_sections") return s.steps.classes && s.steps.sections;
  if (key === "ready") return s.setup_complete;
  return Boolean(s.steps[key]);
};

export default function SetupWizard() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [active, setActive] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/institution/setup-status");
      setStatus(data);
      return data;
    } catch (e) { toast.error(errText(e)); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleLogout = async () => { await logout(); navigate("/login"); };
  const stepKey = STEPS[active].key;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#0B0F17]">
      <header className="h-16 flex items-center gap-3 px-4 md:px-8 border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl sticky top-0 z-20">
        <div className="h-8 w-8 rounded-lg bg-indigo-600 flex items-center justify-center font-heading font-bold text-white text-sm">L</div>
        <div className="flex-1">
          <p className="font-heading font-bold text-slate-900 dark:text-white leading-none">Institution Setup</p>
          <p className="text-[11px] text-slate-500 mt-0.5">{user?.institution_name}</p>
        </div>
        <button onClick={toggle} data-testid="setup-theme-toggle" className="h-9 w-9 rounded-lg flex items-center justify-center text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
          {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
        </button>
        <Button variant="outline" size="sm" onClick={handleLogout} data-testid="setup-logout-btn">
          <LogOut size={14} className="mr-1.5" /> Sign out
        </Button>
      </header>

      <div className="max-w-6xl mx-auto px-4 md:px-8 py-8 grid lg:grid-cols-[260px_1fr] gap-8 items-start">
        {/* Progress rail */}
        <aside className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3" data-testid="setup-progress-rail">
          {STEPS.map((st, i) => {
            const done = stepDone(st.key, status);
            const current = i === active;
            return (
              <button
                key={st.key}
                onClick={() => setActive(i)}
                data-testid={`setup-step-${st.key}`}
                className={`w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-left transition-colors ${
                  current ? "bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 font-medium" : "text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50"
                }`}
              >
                <span className={`h-5 w-5 rounded-full flex items-center justify-center shrink-0 ${done ? "bg-emerald-500 text-white" : current ? "bg-indigo-600 text-white" : "border border-slate-300 dark:border-slate-600 text-slate-400"}`}>
                  {done ? <Check size={12} /> : <Circle size={7} fill="currentColor" />}
                </span>
                <span className="flex-1">{st.label}</span>
                {st.optional && <span className="text-[9px] uppercase tracking-wide text-slate-400">Optional</span>}
              </button>
            );
          })}
        </aside>

        {/* Step content */}
        <main className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 md:p-8 min-h-[440px] flex flex-col" data-testid={`setup-panel-${stepKey}`}>
          <div className="flex-1">
            {stepKey === "profile" && <ProfileStep onSaved={refresh} />}
            {stepKey === "academic_config" && <ConfigStep onSaved={refresh} />}
            {stepKey === "academic_year" && <YearStep onChange={refresh} />}
            {stepKey === "academic_units" && <UnitsStep onChange={refresh} />}
            {stepKey === "classes_sections" && <ClassesStep onChange={refresh} />}
            {stepKey === "subjects" && <SubjectsStep onChange={refresh} />}
            {stepKey === "teachers" && <TeachersStep onChange={refresh} />}
            {stepKey === "ready" && <ReadyStep status={status} onGo={() => navigate("/app/dashboard")} />}
          </div>
          <div className="flex items-center justify-between pt-6 mt-6 border-t border-slate-200 dark:border-slate-800">
            <Button variant="ghost" disabled={active === 0} onClick={() => setActive((a) => a - 1)} data-testid="setup-back-btn">
              <ArrowLeft size={15} className="mr-1.5" /> Back
            </Button>
            {active < STEPS.length - 1 && (
              <Button onClick={() => setActive((a) => a + 1)} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="setup-next-btn">
                Continue <ArrowRight size={15} className="ml-1.5" />
              </Button>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

const Heading = ({ title, desc }) => (
  <div className="mb-6">
    <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-slate-50">{title}</h2>
    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{desc}</p>
  </div>
);

const PROFILE_FIELDS = [
  { name: "name", label: "Institution name", required: true },
  { name: "contact_email", label: "Contact email", type: "email", required: true },
  { name: "phone", label: "Phone", required: true },
  { name: "city", label: "City" },
  { name: "address", label: "Address" },
  { name: "website", label: "Website" },
];

function ProfileStep({ onSaved }) {
  const [values, setValues] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { api.get("/institution/profile").then((r) => setValues(r.data)).catch(() => setValues({})); }, []);
  const save = async () => {
    setSaving(true);
    try {
      const payload = {}; PROFILE_FIELDS.forEach((f) => { payload[f.name] = values[f.name] ?? ""; });
      await api.put("/institution/profile", payload);
      toast.success("Profile saved");
      onSaved();
    } catch (e) { toast.error(errText(e)); } finally { setSaving(false); }
  };
  if (!values) return <p className="text-slate-400">Loading…</p>;
  return (
    <>
      <Heading title="Institution Profile" desc="Basic identity of your school. Contact email and phone are required to continue." />
      <div className="grid sm:grid-cols-2 gap-4">
        {PROFILE_FIELDS.map((f) => (
          <div key={f.name} className="space-y-1.5">
            <Label>{f.label}{f.required && <span className="text-red-500 ml-0.5">*</span>}</Label>
            <Input type={f.type || "text"} value={values[f.name] || ""} onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))} data-testid={`profile-${f.name}`} />
          </div>
        ))}
      </div>
      <div className="flex justify-end mt-6">
        <Button onClick={save} disabled={saving} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="profile-save-btn">
          {saving ? "Saving…" : "Save profile"}
        </Button>
      </div>
    </>
  );
}

function ConfigStep({ onSaved }) {
  const [cfg, setCfg] = useState({ institution_type: "school", school_model: "k12" });
  const [presets, setPresets] = useState(true);
  const [saving, setSaving] = useState(false);
  useEffect(() => { api.get("/institution/academic-config").then((r) => { if (r.data && r.data.school_model) setCfg(r.data); }).catch(() => {}); }, []);
  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put("/institution/academic-config", {
        institution_type: cfg.institution_type, school_model: cfg.school_model, apply_presets: presets,
      });
      toast.success(data.units_created ? `Configuration saved · ${data.units_created} units created` : "Configuration saved");
      onSaved();
    } catch (e) { toast.error(errText(e)); } finally { setSaving(false); }
  };
  return (
    <>
      <Heading title="Academic Configuration" desc="Define your institution's structure. You can start from a recommended template or build from scratch." />
      <div className="grid sm:grid-cols-2 gap-4 max-w-xl">
        <div className="space-y-1.5">
          <Label>Institution type</Label>
          <Select value={cfg.institution_type} onValueChange={(v) => setCfg((c) => ({ ...c, institution_type: v }))}>
            <SelectTrigger data-testid="config-institution-type"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="school">School</SelectItem>
              <SelectItem value="college">College</SelectItem>
              <SelectItem value="coaching">Coaching / Institute</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>School model</Label>
          <Select value={cfg.school_model} onValueChange={(v) => setCfg((c) => ({ ...c, school_model: v }))}>
            <SelectTrigger data-testid="config-school-model"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="k12">K-12 (LP · UP · HS · HSS)</SelectItem>
              <SelectItem value="custom">Custom</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="mt-6 space-y-2 max-w-xl">
        <button
          type="button"
          onClick={() => setPresets(true)}
          data-testid="config-preset-recommended"
          className={`w-full flex items-start gap-3 rounded-lg border p-4 text-left transition-colors ${presets ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10" : "border-slate-200 dark:border-slate-700"}`}
        >
          <Sparkles size={18} className="text-indigo-600 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Start with recommended presets</p>
            <p className="text-xs text-slate-500 mt-0.5">Creates editable academic units (LP, UP, HS, HSS). Rename, reorder, disable or delete anytime.</p>
          </div>
        </button>
        <button
          type="button"
          onClick={() => setPresets(false)}
          data-testid="config-preset-blank"
          className={`w-full flex items-start gap-3 rounded-lg border p-4 text-left transition-colors ${!presets ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10" : "border-slate-200 dark:border-slate-700"}`}
        >
          <Circle size={18} className="text-slate-400 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Start blank</p>
            <p className="text-xs text-slate-500 mt-0.5">Define academic units yourself in the next step.</p>
          </div>
        </button>
      </div>
      <div className="flex justify-end mt-6">
        <Button onClick={save} disabled={saving} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="config-save-btn">
          {saving ? "Saving…" : "Save configuration"}
        </Button>
      </div>
      <ApplyPresetCards onApplied={onSaved} />
    </>
  );
}

function YearStep({ onChange }) {
  return (
    <>
      <Heading title="Academic Year" desc="Create the academic session(s) your school operates in." />
      <InlineList
        testid="setup-years"
        endpoint="res/academic_years"
        onChange={onChange}
        fields={[
          { name: "name", label: "Name (e.g. 2026–27)", required: true },
          { name: "start_date", label: "Start date", type: "date" },
          { name: "end_date", label: "End date", type: "date" },
        ]}
        columns={[
          { key: "name", label: "Year" },
          { key: "start_date", label: "Start" },
          { key: "end_date", label: "End" },
        ]}
      />
    </>
  );
}

const MODEL_OPTS = {
  attendance_model: [{ value: "daily", label: "Daily" }, { value: "period", label: "Period-wise" }, { value: "none", label: "None" }],
  subject_model: [{ value: "fixed", label: "Fixed" }, { value: "elective", label: "Elective" }, { value: "stream", label: "Stream" }],
  assessment_model: [{ value: "marks", label: "Marks" }, { value: "grades", label: "Grades" }, { value: "none", label: "None" }],
  grading_model: [{ value: "percentage", label: "Percentage" }, { value: "letter", label: "Letter" }, { value: "gpa", label: "GPA" }],
};

function UnitsStep({ onChange }) {
  return (
    <>
      <Heading title="Academic Units" desc="The structural bands of your school. Classes live inside units, and units drive attendance/assessment behaviour." />
      {MODEL_NOTE}
      <div className="mt-4">
        <InlineList
          testid="setup-units"
          endpoint="res/academic_units"
          onChange={onChange}
          fields={[
            { name: "name", label: "Unit name", required: true },
            { name: "code", label: "Code" },
            { name: "attendance_model", label: "Attendance", type: "select", default: "daily", options: MODEL_OPTS.attendance_model },
            { name: "subject_model", label: "Subjects", type: "select", default: "fixed", options: MODEL_OPTS.subject_model },
            { name: "assessment_model", label: "Assessment", type: "select", default: "marks", options: MODEL_OPTS.assessment_model },
            { name: "grading_model", label: "Grading", type: "select", default: "percentage", options: MODEL_OPTS.grading_model },
            { name: "timetable_required", label: "Timetable required", type: "checkbox" },
            { name: "has_lab", label: "Has lab / practical", type: "checkbox" },
          ]}
          columns={[
            { key: "name", label: "Unit" },
            { key: "code", label: "Code" },
            { key: "attendance_model", label: "Attendance" },
            { key: "assessment_model", label: "Assessment" },
            { key: "grading_model", label: "Grading" },
          ]}
        />
      </div>
    </>
  );
}

function ClassesStep({ onChange }) {
  const [tick, setTick] = useState(0);
  const bump = () => { setTick((t) => t + 1); onChange(); };
  return (
    <>
      <Heading title="Classes & Sections" desc="Create classes under their academic unit, then add sections within each class." />
      <div className="space-y-6">
        <div>
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">Classes</p>
          <InlineList
            testid="setup-classes"
            endpoint="res/classes"
            onChange={bump}
            fields={[
              { name: "name", label: "Class name", required: true, placeholder: "Grade 6" },
              { name: "academic_unit_id", label: "Academic unit", optionsUrl: "lookup/academic_units", required: true },
              { name: "grade_level", label: "Grade level" },
            ]}
            columns={[
              { key: "name", label: "Class" },
              { key: "academic_unit_name", label: "Unit" },
              { key: "grade_level", label: "Grade" },
            ]}
          />
        </div>
        <div key={tick}>
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">Sections</p>
          <InlineList
            testid="setup-sections"
            endpoint="res/sections"
            onChange={onChange}
            fields={[
              { name: "name", label: "Section", required: true, placeholder: "A" },
              { name: "class_name", label: "Class", optionsUrl: "lookup/classes", required: true },
              { name: "capacity", label: "Capacity", type: "number" },
              { name: "room", label: "Room" },
            ]}
            columns={[
              { key: "name", label: "Section" },
              { key: "class_name", label: "Class" },
              { key: "capacity", label: "Capacity" },
              { key: "room", label: "Room" },
            ]}
          />
        </div>
      </div>
    </>
  );
}

function SubjectsStep({ onChange }) {
  return (
    <>
      <Heading title="Subjects" desc="The master list of subjects taught across your institution." />
      <InlineList
        testid="setup-subjects"
        endpoint="res/subjects"
        onChange={onChange}
        fields={[
          { name: "name", label: "Subject name", required: true },
          { name: "code", label: "Code (auto if blank)" },
          { name: "type", label: "Type", type: "select", default: "core", options: [{ value: "core", label: "Core" }, { value: "elective", label: "Elective" }] },
        ]}
        columns={[
          { key: "name", label: "Subject" },
          { key: "code", label: "Code" },
          { key: "type", label: "Type" },
        ]}
      />
    </>
  );
}

function TeachersStep({ onChange }) {
  return (
    <>
      <Heading title="Teachers (optional)" desc="Add teaching staff logins now, or skip and staff your school later. Not required to finish setup." />
      <InlineList
        testid="setup-teachers"
        endpoint="users"
        extra={{ role: "teacher" }}
        params={{ role: "teacher" }}
        onChange={onChange}
        fields={[
          { name: "name", label: "Full name", required: true },
          { name: "email", label: "Login email", type: "email", required: true },
          { name: "password", label: "Password", type: "password", required: true },
          { name: "phone", label: "Phone" },
        ]}
        columns={[
          { key: "name", label: "Name" },
          { key: "email", label: "Email" },
          { key: "phone", label: "Phone" },
        ]}
        emptyText="No teachers added yet (optional)."
      />
    </>
  );
}

function ReadyStep({ status, onGo }) {
  const complete = status?.setup_complete;
  const ready = status?.operationally_ready;
  return (
    <div className="flex flex-col items-center justify-center text-center h-full py-8" data-testid="setup-ready">
      <div className={`h-16 w-16 rounded-2xl flex items-center justify-center mb-5 ${complete ? "bg-emerald-500" : "bg-amber-500"}`}>
        {complete ? <Check size={30} className="text-white" /> : <Info size={28} className="text-white" />}
      </div>
      <h2 className="font-heading text-2xl font-bold text-slate-900 dark:text-slate-50">
        {complete ? "Setup complete!" : "Almost there"}
      </h2>
      <p className="text-sm text-slate-500 dark:text-slate-400 mt-2 max-w-md">
        {complete
          ? "Your institution's academic structure is ready. You can now run operations."
          : "Finish the required steps (profile, configuration, academic year, unit, class, section, subject) to unlock your console."}
      </p>
      <div className="flex gap-3 mt-6 text-sm">
        <span className={`px-3 py-1 rounded-full font-medium ${complete ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300" : "bg-slate-100 text-slate-500 dark:bg-slate-800"}`}>
          {complete ? "✓ Setup Complete" : "Setup Incomplete"}
        </span>
        <span className={`px-3 py-1 rounded-full font-medium ${ready ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300" : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"}`}>
          {ready ? "✓ Operationally Ready" : "Needs teacher + assignment"}
        </span>
      </div>
      <Button onClick={onGo} disabled={!complete} className="mt-8 bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="setup-go-dashboard-btn">
        Go to Dashboard <ArrowRight size={15} className="ml-1.5" />
      </Button>
    </div>
  );
}
