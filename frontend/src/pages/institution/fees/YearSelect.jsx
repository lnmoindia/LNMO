import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "../../../lib/api";

const sel = "h-9 w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-2 text-sm";
const CLOSED = ["closed", "archived"];

export function YearSelect({ value, onChange, keepId, setDefault }) {
  const [years, setYears] = useState(null);
  useEffect(() => {
    api.get("/res/academic_years", { params: { page_size: 200 } })
      .then((r) => setYears(r.data.items || r.data || []))
      .catch(() => setYears([]));
  }, []);
  const opts = useMemo(() => (years || [])
    .filter((y) => !CLOSED.includes(y.status) || y.id === keepId)
    .sort((a, b) => String(b.name).localeCompare(String(a.name))), [years, keepId]);
  useEffect(() => {
    if (!value && setDefault && opts.length) setDefault((opts.find((y) => y.status === "active") || opts[0]).id);
  }, [value, opts, setDefault]);
  if (years === null) return <div className={`${sel} animate-pulse bg-slate-100 dark:bg-slate-800`} />;
  if (!opts.length) {
    return (
      <p className="text-xs rounded-md bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300 px-3 py-2" data-testid="fee-structure-no-years">
        No academic years yet. <Link to="/app/academic-years" className="font-semibold underline">Create one</Link> first.
      </p>
    );
  }
  const label = (y) => `${y.name}${y.status === "active" ? " (Current)" : y.status === "upcoming" ? " (Upcoming)" : CLOSED.includes(y.status) ? ` (${y.status[0].toUpperCase()}${y.status.slice(1)})` : ""}`;
  return (
    <select className={sel} value={value || ""} onChange={(e) => onChange(e.target.value)} data-testid="fee-structure-year">
      {!value && <option value="">Select…</option>}
      {opts.map((y) => <option key={y.id} value={y.id}>{label(y)}</option>)}
    </select>
  );
}
