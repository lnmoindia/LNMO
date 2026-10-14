import { useEffect, useState } from "react";
import { Check, ArrowRight, ArrowLeft, User, Users, GraduationCap, ClipboardCheck, AlertTriangle, Wand2 } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import EnrollmentPicker from "./EnrollmentPicker";
import PhoneField from "./PhoneField";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";

const STEPS = [
  { key: "profile", label: "Personal", icon: User },
  { key: "guardian", label: "Guardian", icon: Users },
  { key: "enroll", label: "Enrollment", icon: GraduationCap },
  { key: "review", label: "Review", icon: ClipboardCheck },
];

const emptyForm = {
  first_name: "", last_name: "", admission_no: "", email: "", date_of_birth: "", gender: "", phone: "",
  guardian_name: "", guardian_relation: "", guardian_phone: "", guardian_email: "", address: "",
};

export default function StudentEnrollWizard({ open, onClose, onDone }) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(emptyForm);
  const [enroll, setEnroll] = useState(true);
  const [placement, setPlacement] = useState({ academic_year: "", academic_unit_id: "", class_name: "", section: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) { setStep(0); setForm(emptyForm); setAdmTouched(false); setEnroll(true); setPlacement({ academic_year: "", academic_unit_id: "", class_name: "", section: "" }); }
  }, [open]);

  const set = (name, val) => setForm((f) => ({ ...f, [name]: val }));
  const [genning, setGenning] = useState(false);
  const generateAdmission = async () => {
    setGenning(true);
    try { const { data } = await api.get("/students/next-admission-no", { params: { class_name: placement.class_name || "" } }); set("admission_no", data.admission_no); }
    catch (e) { toast.error(errText(e)); } finally { setGenning(false); }
  };
  const [admTouched, setAdmTouched] = useState(false);
  // Last step: class is known now, so pre-fill the next number unless the admin typed one.
  useEffect(() => {
    if (step === STEPS.length - 1 && !admTouched && enroll && placement.class_name) generateAdmission();
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps
  const genEmail = async () => {
    try {
      const nm = `${form.first_name || ""} ${form.last_name || ""}`.trim();
      const { data } = await api.get("/institution/generate-login", { params: { name: nm } });
      set("email", data.email);
    } catch (e) { toast.error(errText(e)); }
  };
  const canNext = step === 0 ? form.first_name.trim() : step === 2 ? (!enroll || placement.class_name) : true;

  const submit = async () => {
    setSaving(true);
    try {
      const payload = { ...form, enroll };
      if (enroll) Object.assign(payload, { academic_year: placement.academic_year, class_name: placement.class_name, section: placement.section });
      const { data } = await api.post("/students/enroll", payload);
      toast.success(enroll ? "Student created and enrolled" : "Student profile created (not enrolled)");
      if (data?.warning) toast.warning(data.warning);
      onDone && onDone();
      onClose();
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="student-wizard">
        <DialogHeader>
          <DialogTitle className="font-heading">Enroll a Student</DialogTitle>
          <DialogDescription>Create the student and place them into a class in one flow.</DialogDescription>
        </DialogHeader>

        {/* Stepper */}
        <div className="flex items-center gap-1.5 mb-2">
          {STEPS.map((s, i) => {
            const Icon = s.icon;
            const done = i < step;
            const cur = i === step;
            return (
              <div key={s.key} className="flex items-center gap-1.5 flex-1">
                <div className={`h-7 w-7 rounded-full flex items-center justify-center shrink-0 ${done ? "bg-emerald-500 text-white" : cur ? "bg-indigo-600 text-white" : "bg-slate-100 dark:bg-slate-800 text-slate-400"}`}>
                  {done ? <Check size={14} /> : <Icon size={14} />}
                </div>
                <span className={`text-xs font-medium hidden sm:block ${cur ? "text-slate-900 dark:text-slate-100" : "text-slate-400"}`}>{s.label}</span>
                {i < STEPS.length - 1 && <div className={`h-px flex-1 ${done ? "bg-emerald-400" : "bg-slate-200 dark:bg-slate-700"}`} />}
              </div>
            );
          })}
        </div>

        <div className="py-2 min-h-[240px]">
          {step === 0 && (
            <div className="grid sm:grid-cols-2 gap-4" data-testid="wizard-profile">
              <FieldRow form={form} set={set} name="first_name" label="First name" required />
              <FieldRow form={form} set={set} name="last_name" label="Last name" />
              <FieldRow form={form} set={set} name="date_of_birth" label="Date of birth" type="date" />
              <div className="space-y-1.5">
                <Label>Gender</Label>
                <Select value={form.gender || ""} onValueChange={(v) => set("gender", v)}>
                  <SelectTrigger data-testid="student-gender"><SelectValue placeholder="Select gender" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="female">Female</SelectItem>
                    <SelectItem value="male">Male</SelectItem>
                    <SelectItem value="others">Others</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Email</Label>
                <div className="flex gap-2">
                  <Input type="email" value={form.email || ""} onChange={(e) => set("email", e.target.value)} data-testid="student-email" />
                  <Button type="button" variant="outline" onClick={genEmail} disabled={!form.first_name} data-testid="student-generate-email">Generate</Button>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Mobile number</Label>
                <PhoneField value={form.phone} onChange={(v) => set("phone", v)} testid="student-phone" />
              </div>
            </div>
          )}
          {step === 1 && (
            <div className="grid sm:grid-cols-2 gap-4" data-testid="wizard-guardian">
              <FieldRow form={form} set={set} name="guardian_name" label="Guardian name" />
              <FieldRow form={form} set={set} name="guardian_relation" label="Relationship" />
              <div className="space-y-1.5">
                <Label>Guardian phone</Label>
                <PhoneField value={form.guardian_phone} onChange={(v) => set("guardian_phone", v)} testid="guardian-phone" />
              </div>
              <FieldRow form={form} set={set} name="guardian_email" label="Guardian email" type="email" />
              <div className="sm:col-span-2"><FieldRow form={form} set={set} name="address" label="Address" /></div>
            </div>
          )}
          {step === 2 && (
            <div className="space-y-4" data-testid="wizard-enroll">
              <div className="flex rounded-lg border border-slate-200 dark:border-slate-700 p-1">
                <button onClick={() => setEnroll(true)} data-testid="enroll-mode-now" className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors ${enroll ? "bg-indigo-600 text-white" : "text-slate-500"}`}>Enroll now</button>
                <button onClick={() => setEnroll(false)} data-testid="enroll-mode-later" className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors ${!enroll ? "bg-amber-500 text-white" : "text-slate-500"}`}>Profile only (pre-admission)</button>
              </div>
              {enroll ? (
                <EnrollmentPicker value={placement} onChange={setPlacement} />
              ) : (
                <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10 p-4 text-sm" data-testid="profile-only-note">
                  <AlertTriangle size={16} className="text-amber-600 mt-0.5 shrink-0" />
                  <p className="text-amber-800 dark:text-amber-200">This student will be saved as <span className="font-semibold">Not Enrolled</span> and excluded from attendance, marks and results until you enroll them into a class.</p>
                </div>
              )}
            </div>
          )}
          {step === 3 && (
            <div className="space-y-3 text-sm" data-testid="wizard-review">
              <div className="rounded-lg border border-indigo-200 dark:border-indigo-500/30 bg-indigo-50/60 dark:bg-indigo-500/10 p-3 space-y-1.5" data-testid="wizard-admission">
                <Label>Admission number</Label>
                <div className="flex gap-2">
                  <Input value={form.admission_no || ""} onChange={(e) => { setAdmTouched(true); set("admission_no", e.target.value); }} placeholder={genning ? "Generating…" : "e.g. SPS-G8-001"} data-testid="student-admission_no" />
                  <Button type="button" variant="outline" onClick={() => { setAdmTouched(false); generateAdmission(); }} disabled={genning} data-testid="generate-admission-btn"><Wand2 size={15} className="mr-1" /> {genning ? "…" : "Generate"}</Button>
                </div>
                <p className="text-xs text-slate-500" data-testid="admission-hint">
                  {enroll && placement.class_name ? `Next free number for ${placement.class_name} — edit it if you use your own.` : "Profile only: Generate gives a provisional number (no grade yet), or type your own. Leave blank to auto-assign."}
                </p>
              </div>
              <Row label="Name" value={`${form.first_name} ${form.last_name}`.trim() || "—"} />
              <Row label="Guardian" value={form.guardian_name ? `${form.guardian_name}${form.guardian_relation ? ` (${form.guardian_relation})` : ""}` : "—"} />
              <Row label="Status" value={enroll ? <span className="text-emerald-600 font-medium">Enrolled</span> : <span className="text-amber-600 font-medium">Not enrolled</span>} />
              {enroll && <Row label="Placement" value={`${placement.class_name || "—"}${placement.section ? ` · ${placement.section}` : ""}${placement.academic_year ? ` · ${placement.academic_year}` : ""}`} />}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between pt-3 border-t border-slate-200 dark:border-slate-800">
          <Button variant="ghost" disabled={step === 0} onClick={() => setStep((s) => s - 1)} data-testid="wizard-back-btn"><ArrowLeft size={15} className="mr-1.5" /> Back</Button>
          {step < STEPS.length - 1 ? (
            <Button disabled={!canNext} onClick={() => setStep((s) => s + 1)} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="wizard-next-btn">Continue <ArrowRight size={15} className="ml-1.5" /></Button>
          ) : (
            <Button disabled={saving} onClick={submit} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="wizard-submit-btn">{saving ? "Saving…" : enroll ? "Create & Enroll" : "Create profile"}</Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

const FieldRow = ({ name, label, type = "text", required, form, set }) => (
  <div className="space-y-1.5">
    <Label>{label}{required && <span className="text-red-500 ml-0.5">*</span>}</Label>
    <Input type={type} value={form[name] || ""} onChange={(e) => set(name, e.target.value)} data-testid={`student-${name}`} />
  </div>
);

const Row = ({ label, value }) => (
  <div className="flex justify-between border-b border-slate-100 dark:border-slate-800 pb-2">
    <span className="text-slate-500">{label}</span>
    <span className="text-slate-800 dark:text-slate-200 font-medium">{value}</span>
  </div>
);
