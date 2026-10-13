import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Lock } from "lucide-react";
import api, { errText } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { DataTable, Pagination } from "../components/common/DataTable";

const STATUSES = [
  { value: "present", label: "P", full: "Present", cls: "bg-emerald-600 text-white", idle: "text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/30 hover:bg-emerald-50 dark:hover:bg-emerald-500/10" },
  { value: "absent", label: "A", full: "Absent", cls: "bg-red-600 text-white", idle: "text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/30 hover:bg-red-50 dark:hover:bg-red-500/10" },
  { value: "late", label: "L", full: "Late", cls: "bg-amber-500 text-white", idle: "text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/30 hover:bg-amber-50 dark:hover:bg-amber-500/10" },
];

const HistoryTab = () => {
  const [data, setData] = useState({ items: [], total: 0, page: 1, pages: 1 });
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setLoading(true);
    api.get("/attendance/records", { params: { page, limit: 20 } })
      .then((r) => setData(r.data))
      .catch((e) => toast.error(errText(e)))
      .finally(() => setLoading(false));
  }, [page]);

  const columns = [
    { key: "date", label: "Date" },
    { key: "class_name", label: "Class" },
    { key: "section", label: "Section" },
    { key: "present", label: "Present" },
    { key: "absent", label: "Absent" },
    { key: "late", label: "Late" },
    { key: "marked_by", label: "Marked By" },
    {
      key: "finalized", label: "Status",
      render: (r) => (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
          r.finalized ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400" : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400"
        }`}>{r.finalized ? "final" : "draft"}</span>
      ),
    },
  ];

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
      <DataTable columns={columns} rows={data.items} loading={loading} testId="attendance-history-table" />
      {data.items.length > 0 && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
    </div>
  );
};

export default function AttendancePage({ teacherMode = false }) {
  const [classOpts, setClassOpts] = useState([]);
  const [sectionOpts, setSectionOpts] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [pair, setPair] = useState("");
  const [cls, setCls] = useState("");
  const [section, setSection] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [sheet, setSheet] = useState(null);
  const [statuses, setStatuses] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (teacherMode) {
      api.get("/teacher/overview").then((r) => setAssignments(r.data.assignments)).catch((e) => toast.error(errText(e)));
    } else {
      api.get("/lookup/classes").then((r) => setClassOpts(r.data));
      api.get("/lookup/sections").then((r) => setSectionOpts(r.data));
    }
  }, [teacherMode]);

  const uniquePairs = [...new Map(assignments.map((a) => [`${a.class_name}|${a.section || ""}`, a])).values()];

  const effectiveCls = teacherMode ? pair.split("|")[0] : cls;
  const effectiveSection = teacherMode ? pair.split("|")[1] || "" : section;

  const load = useCallback(async () => {
    if (!effectiveCls) { toast.error("Select a class first"); return; }
    setLoading(true);
    try {
      const { data } = await api.get("/attendance/sheet", { params: { class_name: effectiveCls, section: effectiveSection, date } });
      setSheet(data);
      const st = {};
      data.students.forEach((s) => { st[s.id] = data.record?.entries?.[s.id] || "present"; });
      setStatuses(st);
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setLoading(false);
    }
  }, [effectiveCls, effectiveSection, date]);

  const save = async (finalized) => {
    setSaving(true);
    try {
      const { data } = await api.post("/attendance/sheet", { class_name: effectiveCls, section: effectiveSection, date, entries: statuses, finalized });
      setSheet((s) => ({ ...s, record: data }));
      toast.success(finalized ? "Attendance submitted as final" : "Draft saved");
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setSaving(false);
    }
  };

  const locked = teacherMode && sheet?.record?.finalized;
  const counts = Object.values(statuses).reduce((acc, v) => ({ ...acc, [v]: (acc[v] || 0) + 1 }), {});

  return (
    <div className="space-y-6" data-testid="attendance-page">
      <div>
        <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">Attendance</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Daily attendance marking with draft and final submission.</p>
      </div>

      <Tabs defaultValue="entry">
        <TabsList data-testid="attendance-tabs">
          <TabsTrigger value="entry" data-testid="attendance-entry-tab">Mark attendance</TabsTrigger>
          <TabsTrigger value="history" data-testid="attendance-history-tab">History</TabsTrigger>
        </TabsList>

        <TabsContent value="entry" className="space-y-4 mt-4">
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-3 md:p-4 flex flex-wrap items-end gap-3">
            {teacherMode ? (
              <div className="space-y-1 min-w-[220px]">
                <p className="text-xs font-medium text-slate-500">My class</p>
                <Select value={pair} onValueChange={setPair}>
                  <SelectTrigger data-testid="attendance-class-select"><SelectValue placeholder="Select class" /></SelectTrigger>
                  <SelectContent>
                    {uniquePairs.map((a) => (
                      <SelectItem key={`${a.class_name}|${a.section || ""}`} value={`${a.class_name}|${a.section || ""}`}>
                        {a.class_name}{a.section ? ` · ${a.section}` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <>
                <div className="space-y-1 min-w-[180px]">
                  <p className="text-xs font-medium text-slate-500">Class</p>
                  <Select value={cls} onValueChange={setCls}>
                    <SelectTrigger data-testid="attendance-class-select"><SelectValue placeholder="Select class" /></SelectTrigger>
                    <SelectContent>{classOpts.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1 min-w-[160px]">
                  <p className="text-xs font-medium text-slate-500">Section (optional)</p>
                  <Select value={section} onValueChange={setSection}>
                    <SelectTrigger data-testid="attendance-section-select"><SelectValue placeholder="All sections" /></SelectTrigger>
                    <SelectContent>{sectionOpts.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </>
            )}
            <div className="space-y-1">
              <p className="text-xs font-medium text-slate-500">Date</p>
              <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-40" data-testid="attendance-date-input" />
            </div>
            <Button onClick={load} disabled={loading} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="attendance-load-btn">
              {loading ? "Loading…" : "Load sheet"}
            </Button>
          </div>

          {sheet && (
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
              <div className="flex flex-wrap items-center gap-3 px-4 py-3 border-b border-slate-200 dark:border-slate-800">
                <div className="flex items-center gap-2 text-xs">
                  {STATUSES.map((s) => (
                    <span key={s.value} className="flex items-center gap-1 text-slate-500">
                      <span className={`h-4 w-4 rounded text-[10px] font-bold flex items-center justify-center ${s.cls}`}>{s.label}</span>
                      {s.full} ({counts[s.value] || 0})
                    </span>
                  ))}
                </div>
                <div className="flex-1" />
                {sheet.record?.finalized && (
                  <span className="flex items-center gap-1 text-xs font-medium text-emerald-600" data-testid="attendance-finalized-badge">
                    <CheckCircle2 size={13} /> Finalized
                  </span>
                )}
                <Button variant="outline" size="sm" disabled={locked} onClick={() => setStatuses(Object.fromEntries(sheet.students.map((s) => [s.id, "present"])))} data-testid="mark-all-present-btn">
                  Mark all present
                </Button>
              </div>
              {sheet.students.length === 0 ? (
                <p className="px-4 py-10 text-sm text-slate-400 text-center" data-testid="attendance-empty">No students in this class/section yet. Enroll students first.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs md:text-sm">
                    <tbody>
                      {sheet.students.map((s, i) => (
                        <tr key={s.id} className="border-b border-slate-100 dark:border-slate-800/60" data-testid={`attendance-row-${s.id}`}>
                          <td className="px-3 py-1.5 text-slate-400 w-8 font-mono">{i + 1}</td>
                          <td className="px-2 py-1.5 text-slate-700 dark:text-slate-300 whitespace-nowrap">
                            {`${s.first_name || ""} ${s.last_name || ""}`.trim()}
                            {s.admission_no && <span className="ml-2 text-slate-400 font-mono text-xs">{s.admission_no}</span>}
                          </td>
                          <td className="px-3 py-1.5">
                            <div className="flex gap-1 justify-end">
                              {STATUSES.map((st) => (
                                <button
                                  key={st.value}
                                  disabled={locked}
                                  onClick={() => setStatuses((prev) => ({ ...prev, [s.id]: st.value }))}
                                  data-testid={`status-${st.value}-${s.id}`}
                                  className={`h-7 w-9 rounded text-xs font-bold border transition-colors disabled:opacity-50 ${
                                    statuses[s.id] === st.value ? `${st.cls} border-transparent` : `bg-transparent ${st.idle}`
                                  }`}
                                >
                                  {st.label}
                                </button>
                              ))}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {sheet.students.length > 0 && (
                <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-slate-200 dark:border-slate-800">
                  {locked && <span className="flex items-center gap-1 text-xs text-slate-400 mr-auto"><Lock size={12} /> Finalized — contact an administrator for corrections</span>}
                  <Button variant="outline" disabled={saving || locked} onClick={() => save(false)} data-testid="attendance-save-draft-btn">Save draft</Button>
                  <Button disabled={saving || locked} onClick={() => save(true)} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="attendance-submit-final-btn">
                    {saving ? "Saving…" : "Submit final"}
                  </Button>
                </div>
              )}
            </div>
          )}
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          <HistoryTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
