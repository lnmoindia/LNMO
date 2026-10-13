import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileSpreadsheet, PenSquare, Eye, CheckCircle2 } from "lucide-react";
import api from "../../lib/api";

export default function TeacherMarksList() {
  const navigate = useNavigate();
  const [rows, setRows] = useState(null);

  useEffect(() => {
    api.get("/teacher/assessments").then((r) => setRows(r.data.assessments)).catch(() => setRows([]));
  }, []);

  return (
    <div className="space-y-6" data-testid="teacher-marks-page">
      <div>
        <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">Teaching</p>
        <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50">Marks Entry</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Assessments for your assigned classes and subjects. Publishing results stays with the admin.</p>
      </div>

      {rows === null ? <p className="text-sm text-slate-400">Loading…</p> : rows.length === 0 ? (
        <div className="py-14 text-center space-y-2 rounded-xl border border-dashed border-slate-200 dark:border-slate-800" data-testid="teacher-marks-empty">
          <FileSpreadsheet size={26} className="mx-auto text-slate-300" />
          <p className="text-sm text-slate-400">No assessments for your classes yet. Your admin creates them under Operations → Assessments.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900/60 text-left">
              <tr>
                {["Assessment", "Class", "Subject", "Max", "Status", ""].map((h) => (
                  <th key={h} className="px-4 py-2 text-xs font-semibold uppercase tracking-wider text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {rows.map((a) => (
                <tr key={a.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40" data-testid={`teacher-assessment-${a.id}`}>
                  <td className="px-4 py-2.5 font-medium text-slate-700 dark:text-slate-200">{a.name}</td>
                  <td className="px-4 py-2.5 text-slate-500">{a.class_name}{a.section ? ` · ${a.section}` : ""}</td>
                  <td className="px-4 py-2.5 text-slate-500">{a.subject || "—"}</td>
                  <td className="px-4 py-2.5 text-slate-500">{a.max_marks}</td>
                  <td className="px-4 py-2.5">
                    {a.status === "published" ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600"><CheckCircle2 size={13} /> Published</span>
                    ) : (
                      <span className="text-xs font-medium text-slate-400">Draft</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => navigate(`/teacher/marks/${a.id}`)}
                      data-testid={`teacher-marks-open-${a.id}`}
                      className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:underline"
                    >
                      {a.status === "published" ? <><Eye size={14} /> View</> : <><PenSquare size={14} /> Enter marks</>}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
