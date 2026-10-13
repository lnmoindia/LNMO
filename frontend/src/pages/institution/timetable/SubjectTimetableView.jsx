import { useCallback, useEffect, useState } from "react";
import { BookOpen } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../../components/ui/select";
import { DAY_LABELS } from "./days";

export default function SubjectTimetableView({ year }) {
  const [subjects, setSubjects] = useState([]);
  const [subject, setSubject] = useState("");
  const [entries, setEntries] = useState([]);

  useEffect(() => {
    api.get("/lookup/subjects").then((r) => {
      setSubjects(r.data);
      if (r.data.length) setSubject((s) => s || r.data[0].value);
    }).catch(() => setSubjects([]));
  }, []);

  const load = useCallback(() => {
    if (!subject || !year) { setEntries([]); return; }
    api.get("/timetable/subject", { params: { subject, academic_year: year } })
      .then((r) => setEntries(r.data.entries || [])).catch((e) => toast.error(errText(e)));
  }, [subject, year]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4" data-testid="tt-subject-view">
      <div className="flex items-center gap-2">
        <BookOpen size={15} className="text-slate-400" />
        <Select value={subject} onValueChange={setSubject}>
          <SelectTrigger className="w-64" data-testid="subject-select"><SelectValue placeholder="Pick a subject" /></SelectTrigger>
          <SelectContent>{subjects.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent>
        </Select>
        <span className="text-xs text-slate-400">{entries.length} scheduled {entries.length === 1 ? "period" : "periods"}</span>
      </div>

      {entries.length === 0 ? (
        <p className="text-sm text-slate-400 py-8 text-center" data-testid="subject-empty">No periods scheduled for {subject || "this subject"} yet.</p>
      ) : (
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900/60 text-left">
              <tr>{["Class", "Section", "Day", "Period", "Teacher", "Room"].map((h) => (
                <th key={h} className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500">{h}</th>))}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {entries.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40" data-testid={`subject-row-${e.id}`}>
                  <td className="px-4 py-2.5 font-medium text-slate-800 dark:text-slate-200">{e.class_name}</td>
                  <td className="px-4 py-2.5 text-slate-500">{e.section}</td>
                  <td className="px-4 py-2.5 text-slate-500">{DAY_LABELS[e.day] || e.day}</td>
                  <td className="px-4 py-2.5 text-slate-500">P{e.period_no}</td>
                  <td className="px-4 py-2.5 text-slate-500">{e.teacher_name || "—"}</td>
                  <td className="px-4 py-2.5 text-slate-500">{e.room || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
