import { useEffect, useState } from "react";
import { Crown } from "lucide-react";
import api from "../../lib/api";

export const designationLabel = (d) => (d === "assistant_principal" ? "Assistant Principal" : "Principal");

// Visible badge of a principal's designation + scope, e.g. "Principal · Whole School"
// or "Assistant Principal · Primary, Secondary". Unit names are resolved from the lookup.
export function ScopeChip({ user, variant = "light" }) {
  const p = user?.principal;
  const [units, setUnits] = useState([]);

  useEffect(() => {
    if (p?.scope_type === "units") {
      api.get("/lookup/academic_units").then((r) => setUnits(r.data || [])).catch(() => setUnits([]));
    }
  }, [p?.scope_type]);

  if (!p) return null;

  const scope = p.scope_type === "whole_school"
    ? "Whole School"
    : (p.unit_ids || []).map((id) => (units.find((u) => u.value === id) || {}).label || "…").join(", ") || "—";

  const cls = variant === "dark"
    ? "bg-amber-500/15 text-amber-300 border-amber-500/25"
    : "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20";

  return (
    <span
      data-testid="principal-scope-chip"
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${cls}`}
    >
      <Crown size={12} strokeWidth={2} />
      {designationLabel(p.designation)} · {scope}
    </span>
  );
}
