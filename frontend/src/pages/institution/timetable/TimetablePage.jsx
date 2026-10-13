import { useEffect, useState } from "react";
import { CalendarRange, Table2, Users2, Settings2, SlidersHorizontal, LayoutGrid, BookOpen, CalendarDays } from "lucide-react";
import api from "../../../lib/api";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../../components/ui/select";
import TimetableBuilder from "./TimetableBuilder";
import TimetableTeacherView from "./TimetableTeacherView";
import TimetableSetup from "./TimetableSetup";
import TimetableRequirements from "./TimetableRequirements";
import GradeTimetable from "./GradeTimetable";
import SubjectTimetableView from "./SubjectTimetableView";
import DailyTimetableView from "./DailyTimetableView";

const TABS = [
  { key: "grade", label: "Grade grid", icon: LayoutGrid },
  { key: "builder", label: "Builder", icon: Table2 },
  { key: "teacher", label: "By teacher", icon: Users2 },
  { key: "subject", label: "By subject", icon: BookOpen },
  { key: "day", label: "By day", icon: CalendarDays },
  { key: "requirements", label: "Requirements", icon: SlidersHorizontal },
  { key: "setup", label: "Setup", icon: Settings2 },
];

export default function TimetablePage() {
  const [tab, setTab] = useState("grade");
  const [years, setYears] = useState([]);
  const [year, setYear] = useState("");

  useEffect(() => {
    api.get("/res/academic_years?limit=100").then((r) => {
      const items = r.data.items || [];
      setYears(items);
      const active = items.find((y) => y.status === "active") || items[0];
      if (active) setYear(active.name);
    }).catch(() => setYears([]));
  }, []);

  return (
    <div className="space-y-6" data-testid="timetable-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">Operations</p>
          <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50">Timetable</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Build section schedules, keep teachers conflict-free, and configure periods per academic unit.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <CalendarRange size={15} className="text-slate-400" />
          <Select value={year} onValueChange={setYear}>
            <SelectTrigger className="w-40" data-testid="tt-year-select"><SelectValue placeholder="Academic year" /></SelectTrigger>
            <SelectContent>
              {years.map((y) => <SelectItem key={y.id} value={y.name}>{y.name}{y.status === "active" ? " · active" : ""}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
        <div className="flex items-center gap-1 border-b border-slate-200 dark:border-slate-800 -mx-5 px-5 pb-0 overflow-x-auto">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.key;
            return (
              <button key={t.key} onClick={() => setTab(t.key)} data-testid={`tt-tab-${t.key}`}
                className={`flex items-center gap-1.5 px-3.5 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap ${
                  active ? "border-indigo-600 text-indigo-700 dark:text-indigo-300" : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                }`}>
                <Icon size={15} /> {t.label}
              </button>
            );
          })}
        </div>
        <div className="pt-5" data-testid={`tt-panel-${tab}`}>
          {!year ? <p className="text-sm text-slate-400">Create an academic year first (Academics → Academic Years).</p> : (
            <>
              {tab === "grade" && <GradeTimetable year={year} />}
              {tab === "builder" && <TimetableBuilder year={year} />}
              {tab === "teacher" && <TimetableTeacherView year={year} />}
              {tab === "subject" && <SubjectTimetableView year={year} />}
              {tab === "day" && <DailyTimetableView year={year} />}
              {tab === "requirements" && <TimetableRequirements year={year} />}
              {tab === "setup" && <TimetableSetup year={year} />}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
