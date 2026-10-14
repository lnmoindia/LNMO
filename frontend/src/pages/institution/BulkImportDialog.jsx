import { useState } from "react";
import { Upload, Download, FileText, ArrowRight, ArrowLeft, Check, AlertTriangle, X } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import EnrollmentPicker from "./EnrollmentPicker";
import { showBulkResult } from "../../components/bulk/BulkResultDialog";

const TEMPLATE_COLS = [
  "first_name", "last_name", "admission_no", "email", "date_of_birth",
  "gender", "guardian_name", "guardian_phone", "guardian_email", "address",
];

// Minimal CSV parser (handles quoted fields, commas, CRLF).
export function parseCSV(text) {
  const rows = [];
  let field = "", row = [], inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else inQuotes = false; }
      else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  return rows.filter((r) => r.some((v) => String(v).trim() !== ""));
}

export default function BulkImportDialog({ open, onClose, onDone }) {
  const [phase, setPhase] = useState("context"); // context | upload | preview | result
  const [placement, setPlacement] = useState({ academic_year: "", academic_unit_id: "", class_name: "", section: "" });
  const [rows, setRows] = useState([]);
  const [fileName, setFileName] = useState("");
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);

  const reset = () => { setPhase("context"); setPlacement({ academic_year: "", academic_unit_id: "", class_name: "", section: "" }); setRows([]); setFileName(""); setResult(null); };
  const close = () => { reset(); onClose(); };

  const downloadTemplate = () => {
    const csv = TEMPLATE_COLS.join(",") + "\n";
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url; a.download = "students_template.csv"; a.click();
    URL.revokeObjectURL(url);
  };

  const onFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = () => {
      setRows([]);
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
  };

  const seen = new Set();
  const validated = rows.map((r) => {
    let error = "";
    if (!r.first_name) error = "Missing first name";
    else if (r.admission_no && seen.has(r.admission_no)) error = `Duplicate admission no in file`;
    if (r.admission_no) seen.add(r.admission_no);
    return { ...r, _error: error };
  });
  const validCount = validated.filter((r) => !r._error).length;
  const errorCount = validated.length - validCount;

  const doImport = async () => {
    setImporting(true);
    try {
      const validRows = validated.filter((r) => !r._error);
      const payload = {
        academic_year: placement.academic_year, class_name: placement.class_name, section: placement.section,
        students: validRows.map(({ _error, _row, ...s }) => s),
      };
      const { data } = await api.post("/students/bulk-enroll", payload);
      const backendSkips = (data.skipped || []).map((s) => ({ row: validRows[s.row - 1]?._row ?? s.row, reason: s.reason }));
      const clientSkips = validated.filter((r) => r._error).map((r) => ({ row: r._row, reason: r._error }));
      const skipped = [...clientSkips, ...backendSkips].sort((a, b) => a.row - b.row);
      setResult({ created: data.created, skipped, run: data.items ? { title: `Student import · ${placement.class_name}`, items: [...data.items, ...clientSkips.map((c) => ({ id: `client-${c.row}`, label: `Row ${c.row}`, status: "skipped", reason: c.reason }))], summary: { ...data.summary, skipped: (data.summary?.skipped || 0) + clientSkips.length } } : null });
      if (data.warning) toast.warning(data.warning);
      setPhase("result");
      onDone && onDone();
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setImporting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent className="sm:max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="bulk-import-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading">Bulk Import Students</DialogTitle>
          <DialogDescription>Pick a destination class, then upload a CSV to create and enroll many students at once.</DialogDescription>
        </DialogHeader>

        {phase === "context" && (
          <div className="space-y-4 py-2" data-testid="import-context">
            <p className="text-sm text-slate-500 dark:text-slate-400">All students in the file will be enrolled into the class you choose here.</p>
            <EnrollmentPicker value={placement} onChange={setPlacement} />
            <div className="flex justify-end pt-2">
              <Button disabled={!placement.class_name} onClick={() => setPhase("upload")} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="import-context-next">
                Continue <ArrowRight size={15} className="ml-1.5" />
              </Button>
            </div>
          </div>
        )}

        {phase === "upload" && (
          <div className="space-y-4 py-2" data-testid="import-upload">
            <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 p-4 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
                <FileText size={16} /> Not sure about the format?
              </div>
              <Button variant="outline" size="sm" onClick={downloadTemplate} data-testid="import-download-template">
                <Download size={14} className="mr-1.5" /> Download template
              </Button>
            </div>
            <label className="block rounded-xl border-2 border-dashed border-slate-300 dark:border-slate-700 p-8 text-center cursor-pointer hover:border-indigo-400 transition-colors" data-testid="import-dropzone">
              <Upload size={26} className="mx-auto text-slate-400 mb-2" />
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200">Click to upload a CSV file</p>
              <p className="text-xs text-slate-400 mt-1">{fileName || "No file selected yet · .csv only"}</p>
              <input type="file" accept=".csv,text/csv" className="hidden" onChange={onFile} data-testid="import-file-input" />
            </label>
            <div className="flex justify-between pt-2">
              <Button variant="ghost" onClick={() => setPhase("context")}><ArrowLeft size={15} className="mr-1.5" /> Back</Button>
            </div>
          </div>
        )}

        {phase === "preview" && (
          <div className="space-y-4 py-2" data-testid="import-preview">
            <div className="flex items-center gap-3 text-sm">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 font-medium"><Check size={13} /> {validCount} ready</span>
              {errorCount > 0 && <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400 font-medium"><X size={13} /> {errorCount} will be skipped</span>}
              <span className="text-slate-400">into <span className="font-medium text-slate-600 dark:text-slate-300">{placement.class_name}{placement.section ? ` · ${placement.section}` : ""}</span></span>
            </div>
            <div className="rounded-lg border border-slate-200 dark:border-slate-800 overflow-hidden max-h-64 overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-900/60 sticky top-0"><tr>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-slate-500">Row</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-slate-500">Name</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-slate-500">Adm. No.</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-slate-500">Guardian</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-slate-500">Status</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                  {validated.map((r, i) => (
                    <tr key={i} data-testid={`import-row-${i}`} className={r._error ? "bg-red-50/50 dark:bg-red-500/5" : ""}>
                      <td className="px-3 py-2 text-slate-400">{r._row}</td>
                      <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{`${r.first_name || ""} ${r.last_name || ""}`.trim() || "—"}</td>
                      <td className="px-3 py-2 text-slate-500">{r.admission_no || "—"}</td>
                      <td className="px-3 py-2 text-slate-500">{r.guardian_name || "—"}</td>
                      <td className="px-3 py-2">
                        {r._error
                          ? <span className="inline-flex items-center gap-1 text-xs text-red-600"><AlertTriangle size={11} /> {r._error}</span>
                          : <span className="text-xs text-emerald-600">Ready</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex justify-between pt-2">
              <Button variant="ghost" onClick={() => setPhase("upload")}><ArrowLeft size={15} className="mr-1.5" /> Back</Button>
              <Button disabled={validCount === 0 || importing} onClick={doImport} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="import-confirm-btn">
                {importing ? "Importing…" : `Import ${validCount} student${validCount === 1 ? "" : "s"}`}
              </Button>
            </div>
          </div>
        )}

        {phase === "result" && result && (
          <div className="flex flex-col items-center text-center py-6" data-testid="import-result">
            <div className="h-14 w-14 rounded-2xl bg-emerald-500 flex items-center justify-center mb-4"><Check size={28} className="text-white" /></div>
            <h3 className="font-heading text-xl font-bold text-slate-900 dark:text-slate-50">Import complete</h3>
            <p className="text-sm text-slate-500 mt-1">
              <span className="font-semibold text-emerald-600">{result.created}</span> student{result.created === 1 ? "" : "s"} enrolled into {placement.class_name}
              {result.skipped?.length ? <> · <span className="font-semibold text-amber-600">{result.skipped.length}</span> skipped</> : null}
            </p>
            {result.skipped?.length > 0 && (
              <div className="mt-4 w-full text-left rounded-lg border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 p-3 max-h-32 overflow-y-auto text-xs text-amber-800 dark:text-amber-200">
                {result.skipped.map((s, i) => <div key={i}>Row {s.row}: {s.reason}</div>)}
              </div>
            )}
            <div className="mt-6 flex gap-2">
              {result.run && <Button variant="outline" onClick={() => showBulkResult(result.run)} data-testid="import-view-details">View details</Button>}
              <Button onClick={close} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="import-done-btn">Done</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
