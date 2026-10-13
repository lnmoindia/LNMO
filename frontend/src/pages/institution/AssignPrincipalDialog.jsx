import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { Checkbox } from "../../components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../components/ui/dialog";

/**
 * Assign or edit a principal. Reused by the Principals page and the Teachers page.
 * - preselectTeacher: {id, name, email} to lock the teacher (from Teachers page).
 * - editing: an existing assignment to edit (teacher is fixed; scope/designation editable).
 */
export default function AssignPrincipalDialog({ open, onClose, onSaved, preselectTeacher, editing }) {
  const isEdit = Boolean(editing);
  const [teacherId, setTeacherId] = useState("");
  const [scopeType, setScopeType] = useState("whole_school");
  const [unitIds, setUnitIds] = useState([]);
  const [designation, setDesignation] = useState("principal");
  const [units, setUnits] = useState([]);
  const [available, setAvailable] = useState([]);
  const [saving, setSaving] = useState(false);

  const reset = useCallback(() => {
    if (isEdit) {
      setTeacherId(editing.user_id);
      setScopeType(editing.scope_type || "whole_school");
      setUnitIds(editing.unit_ids || []);
      setDesignation(editing.designation || "principal");
    } else {
      setTeacherId(preselectTeacher?.id || "");
      setScopeType("whole_school");
      setUnitIds([]);
      setDesignation("principal");
    }
  }, [isEdit, editing, preselectTeacher]);

  useEffect(() => {
    if (!open) return;
    reset();
    api.get("/lookup/academic_units").then((r) => setUnits(r.data || [])).catch(() => setUnits([]));
    if (!isEdit && !preselectTeacher) {
      // only active teachers who are not already principals
      Promise.all([
        api.get("/teachers", { params: { limit: 200 } }),
        api.get("/principals"),
      ]).then(([t, p]) => {
        const assigned = new Set((p.data?.items || []).map((x) => x.user_id));
        const list = (t.data?.items || []).filter((x) => x.status === "active" && !assigned.has(x.id));
        setAvailable(list);
      }).catch(() => setAvailable([]));
    }
  }, [open, isEdit, preselectTeacher, reset]);

  const teacherLabel = useMemo(() => {
    if (preselectTeacher) return `${preselectTeacher.name} (${preselectTeacher.email})`;
    if (isEdit) return `${editing.teacher_name} (${editing.teacher_email})`;
    return null;
  }, [preselectTeacher, isEdit, editing]);

  const toggleUnit = (id) =>
    setUnitIds((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));

  const valid = teacherId && (scopeType === "whole_school" || unitIds.length > 0);

  const save = async () => {
    setSaving(true);
    try {
      const body = {
        scope_type: scopeType,
        unit_ids: scopeType === "units" ? unitIds : [],
        designation,
      };
      if (isEdit) {
        await api.put(`/principals/${editing.id}`, body);
        toast.success("Principal assignment updated");
      } else {
        await api.post("/principals", { teacher_id: teacherId, ...body });
        toast.success("Principal assigned");
      }
      onSaved?.();
      onClose();
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg max-h-[88vh] overflow-y-auto" data-testid="assign-principal-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading">{isEdit ? "Edit principal assignment" : "Assign principal"}</DialogTitle>
          <DialogDescription>
            {isEdit ? "Update the scope and title for this principal." : "Elevate a teacher to principal. They keep their teaching duties."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>Teacher</Label>
            {teacherLabel ? (
              <div className="h-10 flex items-center rounded-md border border-slate-200 dark:border-slate-700 px-3 text-sm text-slate-600 dark:text-slate-300" data-testid="assign-teacher-fixed">
                {teacherLabel}
              </div>
            ) : (
              <Select value={teacherId} onValueChange={setTeacherId}>
                <SelectTrigger data-testid="assign-teacher-select"><SelectValue placeholder="Select an active teacher" /></SelectTrigger>
                <SelectContent>
                  {available.length === 0
                    ? <div className="px-3 py-2 text-xs text-slate-400">No eligible teachers (all active teachers are already principals).</div>
                    : available.map((t) => <SelectItem key={t.id} value={t.id}>{t.name} ({t.email})</SelectItem>)}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>Scope</Label>
            <div className="flex gap-2">
              {[["whole_school", "Whole School"], ["units", "Specific divisions"]].map(([v, l]) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setScopeType(v)}
                  data-testid={`assign-scope-${v}`}
                  className={`flex-1 h-10 rounded-lg border text-sm font-medium transition-colors ${
                    scopeType === v
                      ? "border-indigo-600 bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300"
                      : "border-slate-200 dark:border-slate-700 text-slate-500 hover:border-slate-300"
                  }`}
                >{l}</button>
              ))}
            </div>
          </div>

          {scopeType === "units" && (
            <div className="space-y-2">
              <Label>Divisions</Label>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 divide-y divide-slate-100 dark:divide-slate-800 max-h-48 overflow-y-auto" data-testid="assign-units-list">
                {units.length === 0 && <p className="px-3 py-3 text-xs text-slate-400">No academic units (divisions) exist yet.</p>}
                {units.map((u) => (
                  <label key={u.value} className="flex items-center gap-2.5 px-3 py-2.5 cursor-pointer text-sm">
                    <Checkbox checked={unitIds.includes(u.value)} onCheckedChange={() => toggleUnit(u.value)} data-testid={`assign-unit-${u.value}`} />
                    <span className="text-slate-700 dark:text-slate-300">{u.label}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            <Label>Designation</Label>
            <Select value={designation} onValueChange={setDesignation}>
              <SelectTrigger data-testid="assign-designation-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="principal">Principal</SelectItem>
                <SelectItem value="assistant_principal">Assistant Principal</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-slate-400">Only one Principal title per scope — additional assignees become Assistant Principals.</p>
          </div>
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} data-testid="assign-cancel-btn">Cancel</Button>
          <Button disabled={!valid || saving} onClick={save} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="assign-save-btn">
            {saving ? "Saving…" : isEdit ? "Save changes" : "Assign principal"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
