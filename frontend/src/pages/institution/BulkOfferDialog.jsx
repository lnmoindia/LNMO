import { useEffect, useMemo, useState } from "react";
import { Layers, BookOpen, CheckCircle2, ArrowRight, ArrowLeft, FlaskConical } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Checkbox } from "../../components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";

const STEPS = ["Classes", "Subject & marks", "Review"];

export default function BulkOfferDialog({ open, onOpenChange, units, classes, onDone }) {
  const [step, setStep] = useState(0);
  const [unitId, setUnitId] = useState("");
  const [picked, setPicked] = useState({});
  const [subjects, setSubjects] = useState([]);
  const [subject, setSubject] = useState("");
  const [section, setSection] = useState("");
  const [hasPractical, setHasPractical] = useState(false);
  const [maxMarks, setMaxMarks] = useState("100");
  const [theory, setTheory] = useState("70");
  const [practical, setPractical] = useState("30");
  const [applying, setApplying] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!open) return;
    setStep(0); setUnitId(""); setPicked({}); setSubject(""); setSection("");
    setHasPractical(false); setMaxMarks("100"); setTheory("70"); setPractical("30"); setResult(null);
    api.get("/res/subjects", { params: { limit: 500 } })
      .then((r) => setSubjects((r.data.items || []).map((s) => ({
        value: s.name, label: s.name + (s.code ? ` (${s.code})` : ""), default_max_marks: s.default_max_marks,
      }))))
      .catch(() => setSubjects([]));
  }, [open]);

  const unitClasses = useMemo(
    () => classes.filter((c) => c.academic_unit_id === unitId),
    [classes, unitId]
  );

  const selectUnit = (id) => {
    setUnitId(id);
    const all = {};
    classes.filter((c) => c.academic_unit_id === id).forEach((c) => { all[c.name] = true; });
    setPicked(all);
  };

  const chosen = Object.keys(picked).filter((k) => picked[k]);
  const totalMax = hasPractical ? (Number(theory) || 0) + (Number(practical) || 0) : maxMarks;

  const apply = async () => {
    setApplying(true);
    try {
      const body = {
        subject, class_names: chosen, section,
        has_practical: hasPractical,
        ...(hasPractical
          ? { theory_max_marks: Number(theory), practical_max_marks: Number(practical) }
          : { max_marks: Number(maxMarks) }),
      };
      const { data } = await api.post("/subject-offerings/bulk", body);
      setResult(data);
      onDone && onDone();
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setApplying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl" data-testid="bulk-offer-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BookOpen size={18} className="text-indigo-600" /> Bulk-offer a subject
          </DialogTitle>
          <DialogDescription>
            Offer one subject to many classes in a unit at once, with shared marks config.
          </DialogDescription>
        </DialogHeader>

        {!result && (
          <div className="flex items-center gap-2 text-xs font-medium">
            {STEPS.map((s, i) => (
              <span key={s} className={`px-2 py-1 rounded-full ${i === step ? "bg-indigo-600 text-white" : i < step ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/10" : "text-slate-400"}`}>
                {i + 1}. {s}
              </span>
            ))}
          </div>
        )}

        {result ? (
          <div className="space-y-3 py-2" data-testid="bulk-offer-result">
            <div className="flex items-center gap-2 text-emerald-600">
              <CheckCircle2 size={20} />
              <p className="font-semibold text-slate-900 dark:text-slate-50">
                {result.created} {result.created === 1 ? "class" : "classes"} offered “{subject}”.
              </p>
            </div>
            {result.skipped?.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-500/10 dark:border-amber-500/20 p-3 text-sm">
                <p className="font-medium text-amber-700 dark:text-amber-400 mb-1">Skipped {result.skipped.length}:</p>
                <ul className="text-amber-700 dark:text-amber-300 list-disc pl-5 space-y-0.5">
                  {result.skipped.map((s, i) => <li key={i}>{s.class} — {s.reason}</li>)}
                </ul>
              </div>
            )}
            <div className="flex justify-end">
              <Button onClick={() => onOpenChange(false)} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="bulk-offer-close">Done</Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4 py-1">
            {step === 0 && (
              <div className="space-y-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Academic unit</label>
                  <Select value={unitId} onValueChange={selectUnit}>
                    <SelectTrigger data-testid="bulk-offer-unit"><SelectValue placeholder="Select a unit" /></SelectTrigger>
                    <SelectContent>
                      {units.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                {unitId && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium text-slate-600 dark:text-slate-400 flex items-center gap-1.5"><Layers size={12} /> Target classes ({chosen.length}/{unitClasses.length})</p>
                      <button className="text-xs text-indigo-600 hover:underline" onClick={() => {
                        const all = {}; unitClasses.forEach((c) => { all[c.name] = chosen.length !== unitClasses.length; }); setPicked(all);
                      }}>{chosen.length === unitClasses.length ? "Clear all" : "Select all"}</button>
                    </div>
                    {unitClasses.length === 0 ? (
                      <p className="text-sm text-slate-400">No classes in this unit yet.</p>
                    ) : (
                      <div className="grid grid-cols-2 gap-2 max-h-52 overflow-y-auto">
                        {unitClasses.map((c) => (
                          <label key={c.id} data-testid={`bulk-offer-class-${c.name}`} className="flex items-center gap-2 rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 cursor-pointer hover:border-indigo-400">
                            <Checkbox checked={!!picked[c.name]} onCheckedChange={(v) => setPicked((p) => ({ ...p, [c.name]: !!v }))} />
                            <span className="text-sm text-slate-700 dark:text-slate-200">{c.name}</span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {step === 1 && (
              <div className="space-y-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Subject</label>
                  <Select value={subject} onValueChange={(v) => {
                    setSubject(v);
                    const s = subjects.find((x) => x.value === v);
                    if (s?.default_max_marks) setMaxMarks(String(s.default_max_marks));
                  }}>
                    <SelectTrigger data-testid="bulk-offer-subject"><SelectValue placeholder="Pick from catalog" /></SelectTrigger>
                    <SelectContent>
                      {subjects.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Section (blank = whole class)</label>
                  <Input value={section} onChange={(e) => setSection(e.target.value)} placeholder="e.g. A (optional)" data-testid="bulk-offer-section" />
                </div>
                <label className="flex items-center gap-2 rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 cursor-pointer">
                  <Checkbox checked={hasPractical} onCheckedChange={(v) => setHasPractical(!!v)} data-testid="bulk-offer-practical" />
                  <span className="text-sm text-slate-700 dark:text-slate-200 flex items-center gap-1.5"><FlaskConical size={14} /> Has practical / lab</span>
                </label>
                {hasPractical ? (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Theory max</label>
                      <Input type="number" value={theory} onChange={(e) => setTheory(e.target.value)} data-testid="bulk-offer-theory" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Practical max</label>
                      <Input type="number" value={practical} onChange={(e) => setPractical(e.target.value)} data-testid="bulk-offer-practical-marks" />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Max marks</label>
                    <Input type="number" value={maxMarks} onChange={(e) => setMaxMarks(e.target.value)} data-testid="bulk-offer-max" />
                  </div>
                )}
              </div>
            )}

            {step === 2 && (
              <div className="space-y-3 text-sm">
                <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3 space-y-1">
                  <p><span className="text-slate-400">Subject:</span> <span className="font-medium">{subject}</span></p>
                  <p><span className="text-slate-400">Section:</span> {section || "All sections"}</p>
                  <p><span className="text-slate-400">Marks:</span> {hasPractical ? `${theory} theory + ${practical} practical = ${totalMax}` : `${maxMarks} total`}</p>
                  <p><span className="text-slate-400">Classes ({chosen.length}):</span> {chosen.join(", ") || "—"}</p>
                </div>
                <p className="text-xs text-slate-400">Existing offerings for the same class/section are skipped automatically.</p>
              </div>
            )}

            <div className="flex justify-between pt-1">
              <Button variant="outline" disabled={step === 0} onClick={() => setStep((s) => s - 1)} data-testid="bulk-offer-back">
                <ArrowLeft size={15} className="mr-1" /> Back
              </Button>
              {step < 2 ? (
                <Button
                  className="bg-indigo-700 hover:bg-indigo-800 text-white"
                  disabled={(step === 0 && chosen.length === 0) || (step === 1 && !subject)}
                  onClick={() => setStep((s) => s + 1)}
                  data-testid="bulk-offer-next"
                >
                  Next <ArrowRight size={15} className="ml-1" />
                </Button>
              ) : (
                <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" disabled={applying} onClick={apply} data-testid="bulk-offer-apply">
                  {applying ? "Applying…" : `Offer to ${chosen.length} ${chosen.length === 1 ? "class" : "classes"}`}
                </Button>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
