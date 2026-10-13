import { useCallback, useEffect, useState } from "react";
import { CalendarRange, Download, X, FileBarChart } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { printMonthlyReport } from "../lib/printDoc";

const currentMonth = () => new Date().toISOString().slice(0, 7);

export default function MonthlyReportDialog({ classId, className, onClose }) {
  const [month, setMonth] = useState(currentMonth());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api.get(`/classes/${classId}/monthly-report`, { params: { month } })
      .then((r) => setData(r.data))
      .catch((e) => toast.error(errText(e)))
      .finally(() => setLoading(false));
  }, [classId, month]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" data-testid="monthly-report-dialog">
      <div className="w-full max-w-4xl max-h-[88vh] overflow-y-auto rounded-3xl bg-white dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-800 shadow-2xl p-6">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <FileBarChart className="text-indigo-600" size={20} /> Monthly Report — {className}
          </h2>
          <div className="flex items-center gap-2">
            <div className="relative">
              <CalendarRange size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="pl-8 w-[160px]" data-testid="monthly-report-month" />
            </div>
            <Button size="sm" disabled={!data || loading} onClick={() => printMonthlyReport(data)} data-testid="monthly-report-download">
              <Download size={14} className="mr-1.5" /> Download PDF
            </Button>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600" data-testid="monthly-report-close"><X size={18} /></button>
          </div>
        </div>

        {loading && <p className="text-sm text-slate-400 py-6">Loading…</p>}
        {!loading && data && data.sections.length === 0 && <p className="text-sm text-slate-400 py-6">No sections in this class.</p>}

        {!loading && data && data.sections.map((sec) => (
          <div key={sec.section} className="mb-6" data-testid={`monthly-section-${sec.section}`}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-heading font-semibold text-slate-800 dark:text-slate-200">Section {sec.section}
                <span className="ml-2 text-xs font-normal text-slate-400">Class teacher: {sec.class_teacher || "—"} · {sec.homework_count} HW · {sec.assignment_count} ASG</span>
              </h3>
            </div>
            {sec.students.length === 0 ? (
              <p className="text-sm text-slate-400">No enrolled students.</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 dark:bg-slate-800/50 text-left text-xs uppercase text-slate-400">
                    <tr>
                      <th className="px-4 py-2">Student</th>
                      <th className="px-2 py-2" colSpan={4}>Homework</th>
                      <th className="px-2 py-2" colSpan={2}>Assignments</th>
                    </tr>
                    <tr className="text-[10px]">
                      <th className="px-4 py-1"></th>
                      <th className="px-2 py-1">Sub/Asgn</th><th className="px-2 py-1">Late</th><th className="px-2 py-1">Verified</th><th className="px-2 py-1">Redo</th>
                      <th className="px-2 py-1">Sub/Asgn</th><th className="px-2 py-1">Avg score</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                    {sec.students.map((st) => (
                      <tr key={st.student_id} data-testid={`monthly-student-${st.student_id}`}>
                        <td className="px-4 py-2.5">
                          <span className="font-medium text-slate-800 dark:text-slate-200">{st.name}</span>
                          {st.admission_no && <span className="block text-xs text-slate-400">{st.admission_no}</span>}
                        </td>
                        <td className="px-2 py-2.5 text-center">{st.homework.submitted}/{st.homework.assigned}</td>
                        <td className="px-2 py-2.5 text-center text-rose-600">{st.homework.late}</td>
                        <td className="px-2 py-2.5 text-center text-emerald-600">{st.homework.verified}</td>
                        <td className="px-2 py-2.5 text-center text-amber-600">{st.homework.redo}</td>
                        <td className="px-2 py-2.5 text-center">{st.assignments.submitted}/{st.assignments.assigned}</td>
                        <td className="px-2 py-2.5 text-center font-semibold">{st.assignments.avg_score == null ? "—" : st.assignments.avg_score}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
