import { useCallback, useEffect, useState } from "react";
import api, { errText } from "../../../lib/api";
import { toast } from "sonner";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../../components/ui/select";
import TeacherGrid from "./TeacherGrid";

export default function TimetableTeacherView({ year }) {
  const [teachers, setTeachers] = useState([]);
  const [teacherId, setTeacherId] = useState("");
  const [grid, setGrid] = useState(null);

  useEffect(() => {
    api.get("/lookup/teachers_by_id").then((r) => setTeachers(r.data)).catch(() => setTeachers([]));
  }, []);

  const load = useCallback(() => {
    if (!teacherId || !year) { setGrid(null); return; }
    api.get("/timetable/teacher-grid", { params: { teacher_id: teacherId, academic_year: year } })
      .then((r) => setGrid(r.data))
      .catch((e) => toast.error(errText(e)));
  }, [teacherId, year]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4" data-testid="tt-teacher-view">
      <Select value={teacherId} onValueChange={setTeacherId}>
        <SelectTrigger className="w-72" data-testid="tt-teacher-select"><SelectValue placeholder="Pick a teacher" /></SelectTrigger>
        <SelectContent>{teachers.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
      </Select>

      {!grid ? (
        <p className="text-sm text-slate-400 py-8 text-center">Pick a teacher to see their weekly teaching load.</p>
      ) : (
        <>
          <p className="text-xs text-slate-400" data-testid="tt-teacher-load">{grid.entries.length} scheduled {grid.entries.length === 1 ? "period" : "periods"} this week</p>
          <TeacherGrid config={grid.config} entries={grid.entries} />
        </>
      )}
    </div>
  );
}
