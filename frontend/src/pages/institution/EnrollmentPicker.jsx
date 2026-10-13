import { useEffect, useState } from "react";
import { Label } from "../../components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";
import api from "../../lib/api";

/** Cascading Academic Year → Unit → Class → Section picker. value = {academic_year, academic_unit_id, class_name, section}. */
export default function EnrollmentPicker({ value, onChange, disabled }) {
  const [years, setYears] = useState([]);
  const [units, setUnits] = useState([]);
  const [classes, setClasses] = useState([]);
  const [sections, setSections] = useState([]);

  useEffect(() => {
    api.get("/lookup/academic_years").then((r) => setYears(r.data)).catch(() => {});
    api.get("/res/academic_units", { params: { limit: 200 } }).then((r) => setUnits((r.data.items || []).sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)))).catch(() => {});
    api.get("/res/classes", { params: { limit: 500 } }).then((r) => setClasses(r.data.items || [])).catch(() => {});
    api.get("/res/sections", { params: { limit: 500 } }).then((r) => setSections(r.data.items || [])).catch(() => {});
  }, []);

  const set = (patch) => onChange({ ...value, ...patch });
  const unitClasses = classes.filter((c) => c.academic_unit_id === value.academic_unit_id);
  const classSections = sections.filter((s) => s.class_name === value.class_name);

  return (
    <div className="grid sm:grid-cols-2 gap-4" data-testid="enrollment-picker">
      <div className="space-y-1.5">
        <Label>Academic year</Label>
        <Select value={value.academic_year || ""} onValueChange={(v) => set({ academic_year: v })} disabled={disabled}>
          <SelectTrigger data-testid="enroll-year"><SelectValue placeholder="Select year" /></SelectTrigger>
          <SelectContent>{years.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label>Academic unit</Label>
        <Select value={value.academic_unit_id || ""} onValueChange={(v) => set({ academic_unit_id: v, class_name: "", section: "" })} disabled={disabled}>
          <SelectTrigger data-testid="enroll-unit"><SelectValue placeholder="Select unit" /></SelectTrigger>
          <SelectContent>{units.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}{u.code ? ` (${u.code})` : ""}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label>Class <span className="text-red-500">*</span></Label>
        <Select value={value.class_name || ""} onValueChange={(v) => set({ class_name: v, section: "" })} disabled={disabled || !value.academic_unit_id}>
          <SelectTrigger data-testid="enroll-class"><SelectValue placeholder={value.academic_unit_id ? "Select class" : "Pick a unit first"} /></SelectTrigger>
          <SelectContent>{unitClasses.map((c) => <SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label>Section</Label>
        <Select value={value.section || ""} onValueChange={(v) => set({ section: v })} disabled={disabled || !value.class_name}>
          <SelectTrigger data-testid="enroll-section"><SelectValue placeholder={value.class_name ? "Select section" : "Pick a class first"} /></SelectTrigger>
          <SelectContent>{classSections.map((s) => <SelectItem key={s.id} value={s.name}>{s.name}</SelectItem>)}</SelectContent>
        </Select>
      </div>
    </div>
  );
}
