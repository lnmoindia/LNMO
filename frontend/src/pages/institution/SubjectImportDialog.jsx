import { useState } from "react";
import { Upload, Download, FileText, Check, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import { parseCSV } from "./BulkImportDialog";

const TEMPLATE_COLS = ["name", "code", "type", "default_max_marks"];
const TYPES = ["core", "elective", "language", "practical"];

export default function SubjectImportButton({ onDone }) {
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState("upload"); // upload | preview | result
  const [rows, setRows] = useState([]);
  const [fileName, setFileName] = useState("");
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);

  const close = () => { setOpen(false); setPhase("upload"); setRows([]); setFileName(""); setResult(null); };

  const downloadTemplate = () => {
    const csv = TEMPLATE_COLS.join(",") + "\nMathematics,MATH,core,100\nPhysics,,practical,100\n";
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url; a.download = "subjects_template.csv"; a.click();
    URL.revokeObjectURL(url);
  };

  const onFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = () => {
      const parsed = parseCSV(String(reader.result));
      if (parsed.length < 2) { toast.error("CSV has no data rows"); return; }
      const header = parsed[0].map((h) => h.trim().toLowerCase());
      const mapped = parsed.slice(1).map((r, idx) => {
        const obj = { _row: idx + 2 };
        header.forEach((h, i) => { if (TEMPLATE_COLS.includes(h)) obj[h] = (r[i] || "").trim(); });
        return obj;
      });
      setRows(mapped);
      setPhase("preview");
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  const seen = new Set();
  const validated = rows.map((r) => {
    let error = "";
    const key = (r.name || "").toLowerCase();
    if (!r.name) error = "Missing subject name";
    else if (seen.has(key)) error = "Duplicate name in file";
    if (key) seen.add(key);
    return { ...r, _error: error };
  });
  const validRows = validated.filter((r) => !r._error);

  const doImport = async () => {
    setImporting(true);
    try {
      const { data } = await api.post("/subjects/bulk-import", {
        subjects: validRows.map(({ _error, _row, ...s }) => s),
      });
      const backendSkips = (data.skipped || []).map((s) => ({ row: validRows[s.row - 1]?._row ?? s.row, reason: s.reason }));
      const clientSkips = validated.filter((r) => r._error).map((r) => ({ row: r._row, reason: r._error }));
      setResult({ created: data.created, skipped: [...clientSkips, ...backendSkips].sort((a, b) => a.row - b.row) });
      setPhase("result");
      onDone && onDone();
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setImporting(false);
    }
  };

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)} data-testid="subject-import-btn">
        <Upload size={15} className="mr-1" /> Import CSV
      </Button>
      <Dialog open={open} onOpenChange={(o) => !o && close()}>
        <DialogContent className="sm:max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="subject-import-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading">Bulk Import Subjects</DialogTitle>
            <DialogDescription>Upload a CSV to add many subjects to your catalog at once. Codes are auto-generated when blank.</DialogDescription>
          </DialogHeader>

          {phase === "upload" && (
            <div className="space-y-4 py-2" data-testid="subject-import-upload">
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-4 space-y-2 text-sm">
                <p className="font-medium text-slate-800 dark:text-slate-200">Expected columns</p>
                <p className="text-slate-500 dark:text-slate-400"><code className="text-xs">{TEMPLATE_COLS.join(", ")}</code></p>
                <p className="text-xs text-slate-400">Only <span className="font-medium">name</span> is required. Type must be one of: {TYPES.join(", ")} (defaults to core). Blank codes are auto-generated from the name.</p>
                <Button variant="outline" size="sm" onClick={downloadTemplate} data-testid="subject-import-template">
                  <Download size={14} className="mr-1" /> Download template
                </Button>
              </div>
              <label className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-slate-300 dark:border-slate-700 p-8 cursor-pointer hover:border-indigo-400 transition-colors">
                <FileText size={22} className="text-slate-400" />
                <span className="text-sm text-slate-600 dark:text-slate-300 font-medium">Click to choose a .csv file</span>
                <input type="file" accept=".csv,text/csv" className="hidden" onChange={onFile} data-testid="subject-csv-input" />
              </label>
            </div>
          )}

          {phase === "preview" && (
            <div className="space-y-3 py-1" data-testid="subject-import-preview">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                <span className="font-medium text-slate-800 dark:text-slate-200">{fileName}</span> — {validRows.length} valid {validRows.length === 1 ? "row" : "rows"}
                {validated.length - validRows.length > 0 && <span className="text-amber-600"> · {validated.length - validRows.length} with errors (will be skipped)</span>}
              </p>
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 overflow-auto max-h-72">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 dark:bg-slate-900/60 text-left sticky top-0">
                    <tr>
                      {["Row", "Name", "Code", "Type", "Default max", ""].map((h) => (
                        <th key={h} className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-500">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                    {validated.map((r) => (
                      <tr key={r._row} data-testid={`subject-import-row-${r._row}`} className={r._error ? "bg-amber-50/60 dark:bg-amber-500/5" : ""}>
                        <td className="px-3 py-2 text-slate-400">{r._row}</td>
                        <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{r.name || "—"}</td>
                        <td className="px-3 py-2 text-slate-500">{r.code || <span className="text-slate-400 italic">auto</span>}</td>
                        <td className="px-3 py-2 text-slate-500 capitalize">{r.type || "core"}</td>
                        <td className="px-3 py-2 text-slate-500">{r.default_max_marks || 100}</td>
                        <td className="px-3 py-2 text-xs text-amber-600">{r._error && <span className="inline-flex items-center gap-1"><AlertTriangle size={12} /> {r._error}</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex justify-between">
                <Button variant="outline" onClick={() => { setPhase("upload"); setRows([]); }} data-testid="subject-import-back">Back</Button>
                <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" disabled={validRows.length === 0 || importing} onClick={doImport} data-testid="subject-import-confirm">
                  {importing ? "Importing…" : `Import ${validRows.length} ${validRows.length === 1 ? "subject" : "subjects"}`}
                </Button>
              </div>
            </div>
          )}

          {phase === "result" && result && (
            <div className="space-y-3 py-2" data-testid="subject-import-result">
              <div className="flex items-center gap-2 text-emerald-600">
                <Check size={20} />
                <p className="font-semibold text-slate-900 dark:text-slate-50">
                  {result.created} {result.created === 1 ? "subject" : "subjects"} imported.
                </p>
              </div>
              {result.skipped.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-500/10 dark:border-amber-500/20 p-3 text-sm">
                  <p className="font-medium text-amber-700 dark:text-amber-400 mb-1">Skipped {result.skipped.length}:</p>
                  <ul className="text-amber-700 dark:text-amber-300 list-disc pl-5 space-y-0.5">
                    {result.skipped.map((s, i) => <li key={i}>Row {s.row} — {s.reason}</li>)}
                  </ul>
                </div>
              )}
              <div className="flex justify-end">
                <Button onClick={close} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="subject-import-close">Done</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
