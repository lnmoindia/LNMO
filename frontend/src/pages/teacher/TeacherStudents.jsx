import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { DataTable } from "../../components/common/DataTable";

const columns = [
  { key: "name", label: "Name", render: (r) => `${r.first_name || ""} ${r.last_name || ""}`.trim() },
  { key: "admission_no", label: "Admission No." },
  { key: "class_name", label: "Class" },
  { key: "section", label: "Section" },
  { key: "guardian_name", label: "Guardian" },
  { key: "guardian_phone", label: "Guardian Phone" },
];

export default function TeacherStudents() {
  const [assignments, setAssignments] = useState([]);
  const [pair, setPair] = useState("");
  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/teacher/overview").then((r) => {
      setAssignments(r.data.assignments);
      const first = r.data.assignments[0];
      if (first) setPair(`${first.class_name}|${first.section || ""}`);
    }).catch((e) => toast.error(errText(e)));
  }, []);

  useEffect(() => {
    if (!pair) return;
    const [cls, section] = pair.split("|");
    setLoading(true);
    api.get("/teacher/students", { params: { class_name: cls, section } })
      .then((r) => setStudents(r.data.students))
      .catch((e) => toast.error(errText(e)))
      .finally(() => setLoading(false));
  }, [pair]);

  const uniquePairs = [...new Map(assignments.map((a) => [`${a.class_name}|${a.section || ""}`, a])).values()];

  return (
    <div className="space-y-6" data-testid="teacher-students-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">My students</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Students in the classes assigned to you.</p>
        </div>
        <Select value={pair} onValueChange={setPair}>
          <SelectTrigger className="w-56" data-testid="teacher-students-class-select"><SelectValue placeholder="Select class" /></SelectTrigger>
          <SelectContent>
            {uniquePairs.map((a) => (
              <SelectItem key={`${a.class_name}|${a.section || ""}`} value={`${a.class_name}|${a.section || ""}`}>
                {a.class_name}{a.section ? ` · ${a.section}` : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
        <DataTable columns={columns} rows={students} loading={loading} testId="teacher-students-table" />
      </div>
    </div>
  );
}
