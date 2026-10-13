import { useState } from "react";
import { Sparkles, Layers } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../ui/button";

const PRESETS = [
  { key: "lp_up_hs_hss", title: "LP / UP / HS / HSS (Kerala)",
    rows: [["LP", "Grades 1–4"], ["UP", "Grades 5–7"], ["HS", "Grades 8–10"], ["HSS", "Grades 11–12"]] },
  { key: "k12", title: "K-12 (single unit)",
    rows: [["K-12", "Grades 1–12"]] },
];

const summaryMsg = (s) => {
  const made = [];
  if (s.units_created) made.push(`${s.units_created} unit${s.units_created > 1 ? "s" : ""}`);
  if (s.classes_created) made.push(`${s.classes_created} grade${s.classes_created > 1 ? "s" : ""}`);
  if (s.sections_created) made.push(`${s.sections_created} section${s.sections_created > 1 ? "s" : ""}`);
  const added = made.length ? `Added ${made.join(", ")}` : "Everything already exists — nothing added";
  const skipped = (s.units_skipped || s.classes_skipped)
    ? ` — ${s.units_skipped} unit(s), ${s.classes_skipped} grade(s) already existed` : "";
  return added + skipped;
};

export default function ApplyPresetCards({ onApplied, compact = false }) {
  const [busy, setBusy] = useState(null);
  const apply = async (key) => {
    setBusy(key);
    try {
      const { data } = await api.post("/institution/apply-preset", { preset: key });
      toast.success(summaryMsg(data.summary));
      onApplied?.();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(null); }
  };

  if (compact) {
    return (
      <div className="flex flex-wrap gap-2" data-testid="apply-preset-compact">
        {PRESETS.map((p) => (
          <Button key={p.key} variant="outline" size="sm" disabled={busy} onClick={() => apply(p.key)} data-testid={`apply-preset-${p.key}`}>
            <Sparkles size={14} className="mr-1.5" /> {busy === p.key ? "Applying…" : p.title}
          </Button>
        ))}
      </div>
    );
  }

  return (
    <div className="mt-8" data-testid="apply-preset-cards">
      <p className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1">Start from a preset</p>
      <p className="text-xs text-slate-500 mb-3">One click creates the units, grades and a default “A” section. Safe to apply over an existing setup — only missing items are added, nothing is duplicated or deleted.</p>
      <div className="grid sm:grid-cols-2 gap-3 max-w-2xl">
        {PRESETS.map((p) => (
          <div key={p.key} className="rounded-lg border border-slate-200 dark:border-slate-700 p-4 flex flex-col" data-testid={`preset-card-${p.key}`}>
            <div className="flex items-center gap-2 mb-2"><Layers size={16} className="text-indigo-600" /><p className="text-sm font-medium text-slate-900 dark:text-slate-100">{p.title}</p></div>
            <ul className="text-xs text-slate-500 space-y-1 flex-1 mb-3">
              {p.rows.map(([u, g]) => <li key={u}><span className="font-medium text-slate-600 dark:text-slate-300">{u}</span> → {g}</li>)}
            </ul>
            <Button variant="outline" size="sm" disabled={busy} onClick={() => apply(p.key)} data-testid={`apply-preset-${p.key}`}>
              {busy === p.key ? "Applying…" : "Apply preset"}
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
