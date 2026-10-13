import { useCallback, useEffect, useState } from "react";
import { Library, Upload, Loader2, Check, Trash2, FileText, Search, BookOpen, Layers } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";

const GRADES = Array.from({ length: 12 }, (_, i) => `Grade ${i + 1}`);
const TYPES = ["textbook", "notes", "question_paper", "worksheet", "reference", "other"];

export default function PlatformLibrary() {
  const [tab, setTab] = useState("library");
  return (
    <div className="space-y-6" data-testid="platform-library">
      <div>
        <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Library className="text-indigo-600" size={24} /> LNMO Central Library</h1>
        <p className="text-sm text-slate-500 mt-1">Kerala SCERT content shared with every school. Upload textbooks & materials and approve school submissions.</p>
      </div>
      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-800">
        {[["library", "Library"], ["templates", "Chapter templates"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`lib-tab-${k}`}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab === k ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500"}`}>{l}</button>
        ))}
      </div>
      {tab === "library" ? <LibraryTab /> : <TemplatesTab />}
    </div>
  );
}

function BulkUpload({ onDone }) {
  const [rows, setRows] = useState([]); // [{file, grade, subject, material_type, title}]
  const [quick, setQuick] = useState({ grade: "Grade 8", subject: "Mathematics", material_type: "textbook", academic_year: "" });
  const [busy, setBusy] = useState(false);
  const [pct, setPct] = useState(0);

  const onPick = (files) => setRows(Array.from(files).map((f) => ({
    file: f, grade: quick.grade, subject: quick.subject, material_type: quick.material_type, academic_year: quick.academic_year,
    title: (f.name || "Untitled").replace(/\.[^.]+$/, ""),
  })));
  const applyAll = () => setRows(rows.map((r) => ({ ...r, grade: quick.grade, subject: quick.subject, material_type: quick.material_type, academic_year: quick.academic_year })));
  const setRow = (i, k, v) => { const n = [...rows]; n[i][k] = v; setRows(n); };
  const removeRow = (i) => setRows(rows.filter((_, k) => k !== i));

  const upload = async () => {
    if (!rows.length) return;
    setBusy(true); setPct(0);
    try {
      const fd = new FormData();
      fd.append("board", "kerala_scert");
      fd.append("meta", JSON.stringify(rows.map((r) => ({ grade: r.grade, subject: r.subject, material_type: r.material_type, title: r.title, academic_year: r.academic_year || "" }))));
      rows.forEach((r) => fd.append("files", r.file));
      await api.post("/platform/library/bulk", fd, { onUploadProgress: (e) => setPct(Math.round((e.loaded / (e.total || 1)) * 100)) });
      toast.success(`Uploaded ${rows.length} file(s) — extracting text in the background`);
      setRows([]); onDone();
    } catch (e) { toast.error(typeof errText(e) === "string" ? errText(e) : "Bulk upload failed"); } finally { setBusy(false); }
  };

  return (
    <div className="mt-5 pt-5 border-t border-slate-200 dark:border-slate-800" data-testid="lib-bulk">
      <p className="font-heading font-semibold text-slate-800 dark:text-slate-100 mb-2 flex items-center gap-2"><Layers size={16} /> Bulk upload</p>
      <label className="flex items-center justify-center gap-2 text-sm text-indigo-600 cursor-pointer rounded-lg border-2 border-dashed border-indigo-300 dark:border-indigo-800 py-3">
        <Upload size={15} /> Select multiple files (PDF/DOCX/TXT)
        <input type="file" hidden multiple accept=".pdf,.docx,.txt" onChange={(e) => onPick(e.target.files)} data-testid="lib-bulk-files" />
      </label>
      {rows.length > 0 && (
        <>
          <div className="mt-3 rounded-lg bg-slate-50 dark:bg-slate-800/40 p-2" data-testid="lib-bulk-quicktag">
            <p className="text-[10px] uppercase font-bold text-slate-400 mb-1">Quick-tag all rows</p>
            <div className="grid grid-cols-3 gap-1.5">
              <select className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1 py-1 text-xs" value={quick.grade} onChange={(e) => setQuick({ ...quick, grade: e.target.value })} data-testid="lib-bulk-all-grade">{GRADES.map((g) => <option key={g}>{g}</option>)}</select>
              <input className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1 py-1 text-xs" value={quick.subject} onChange={(e) => setQuick({ ...quick, subject: e.target.value })} data-testid="lib-bulk-all-subject" />
              <select className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1 py-1 text-xs" value={quick.material_type} onChange={(e) => setQuick({ ...quick, material_type: e.target.value })} data-testid="lib-bulk-all-type">{TYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</select>
            </div>
            <button className="mt-1.5 text-xs text-indigo-600 font-semibold" onClick={applyAll} data-testid="lib-bulk-apply-all">Apply to all {rows.length} rows</button>
            <input className="mt-1.5 w-full rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1.5 py-1 text-xs" value={quick.academic_year} onChange={(e) => setQuick({ ...quick, academic_year: e.target.value })} data-testid="lib-bulk-all-year" placeholder="Academic year (optional, e.g. 2025-2026) — applies on 'Apply to all'" />
          </div>
          <div className="mt-2 space-y-2 max-h-72 overflow-y-auto">
            {rows.map((r, i) => (
              <div key={i} className="rounded-lg border border-slate-200 dark:border-slate-700 p-2 space-y-1.5" data-testid={`lib-bulk-row-${i}`}>
                <div className="flex items-center gap-1.5 text-xs"><FileText size={12} className="text-slate-400" /><span className="truncate flex-1">{r.file.name}</span><button className="text-rose-400" onClick={() => removeRow(i)} data-testid={`lib-bulk-remove-${i}`}><Trash2 size={12} /></button></div>
                <input className="w-full rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1.5 py-1 text-xs" value={r.title} onChange={(e) => setRow(i, "title", e.target.value)} data-testid={`lib-bulk-title-${i}`} placeholder="Title" />
                <div className="grid grid-cols-3 gap-1.5">
                  <select className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1 py-1 text-xs" value={r.grade} onChange={(e) => setRow(i, "grade", e.target.value)} data-testid={`lib-bulk-grade-${i}`}>{GRADES.map((g) => <option key={g}>{g}</option>)}</select>
                  <input className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1 py-1 text-xs" value={r.subject} onChange={(e) => setRow(i, "subject", e.target.value)} data-testid={`lib-bulk-subject-${i}`} />
                  <select className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1 py-1 text-xs" value={r.material_type} onChange={(e) => setRow(i, "material_type", e.target.value)} data-testid={`lib-bulk-type-${i}`}>{TYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</select>
                </div>
              </div>
            ))}
          </div>
          {busy && <div className="mt-2 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden"><div className="h-full bg-indigo-600 transition-all" style={{ width: `${pct}%` }} /></div>}
          <Button className="mt-3 w-full" disabled={busy} onClick={upload} data-testid="lib-bulk-submit">{busy ? <><Loader2 className="animate-spin mr-1" size={15} /> Uploading {pct}%</> : `Upload ${rows.length} file(s)`}</Button>
        </>
      )}
    </div>
  );
}

function LibraryTab() {
  const [items, setItems] = useState([]);
  const [filters, setFilters] = useState({ grade: "", subject: "", material_type: "", status: "", q: "" });
  const [form, setForm] = useState({ grade: "Grade 8", subject: "Mathematics", material_type: "textbook", title: "", description: "" });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/platform/library", { params: filters }).then((r) => setItems(r.data.items)).catch((e) => toast.error(errText(e)));
  }, [filters]);
  useEffect(() => { load(); }, [load]);

  const upload = async () => {
    if (!form.title.trim()) { toast.error("Enter a title"); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("board", "kerala_scert");
      Object.entries(form).forEach(([k, v]) => fd.append(k, v));
      if (file) fd.append("file", file);
      await api.post("/platform/library", fd);
      toast.success(file ? "Uploaded — extracting text in background" : "Added to library");
      setForm({ ...form, title: "", description: "" }); setFile(null); load();
    } catch (e) { toast.error(typeof errText(e) === "string" ? errText(e) : "Upload failed"); } finally { setBusy(false); }
  };

  const approve = async (id) => { try { await api.post(`/platform/library/${id}/approve`); toast.success("Published"); load(); } catch (e) { toast.error(errText(e)); } };
  const del = async (id) => { if (!window.confirm("Delete this library item permanently?")) return; try { await api.delete(`/platform/library/${id}`); toast.success("Deleted"); load(); } catch (e) { toast.error(errText(e)); } };

  return (
    <div className="grid lg:grid-cols-3 gap-6">
      <div className="lg:col-span-1 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 h-fit" data-testid="lib-upload-form">
        <p className="font-heading font-semibold text-slate-800 dark:text-slate-100 mb-3 flex items-center gap-2"><Upload size={16} /> Upload material</p>
        <div className="grid grid-cols-2 gap-2">
          <select className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-2 text-sm" value={form.grade} onChange={(e) => setForm({ ...form, grade: e.target.value })} data-testid="lib-up-grade">{GRADES.map((g) => <option key={g}>{g}</option>)}</select>
          <select className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-2 text-sm" value={form.material_type} onChange={(e) => setForm({ ...form, material_type: e.target.value })} data-testid="lib-up-type">{TYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</select>
        </div>
        <Input className="mt-2" placeholder="Subject" value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} data-testid="lib-up-subject" />
        <Input className="mt-2" placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="lib-up-title" />
        <Textarea className="mt-2" placeholder="Description (optional)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <label className="mt-2 flex items-center gap-2 text-sm text-indigo-600 cursor-pointer">
          <FileText size={15} /> {file ? file.name : "Attach file (PDF/DOCX/TXT, up to 60MB)"}
          <input type="file" hidden accept=".pdf,.docx,.txt" onChange={(e) => setFile(e.target.files[0])} data-testid="lib-up-file" />
        </label>
        <Button className="mt-4 w-full" disabled={busy} onClick={upload} data-testid="lib-up-submit">{busy ? <Loader2 className="animate-spin" size={16} /> : "Upload to Library"}</Button>
        <BulkUpload onDone={load} />
      </div>

      <div className="lg:col-span-2 space-y-3">
        <div className="flex flex-wrap gap-2">
          <div className="relative flex-1 min-w-[160px]"><Search className="absolute left-2.5 top-2.5 text-slate-400" size={15} /><Input className="pl-8" placeholder="Search title…" value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} data-testid="lib-search" /></div>
          <select className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 text-sm" value={filters.grade} onChange={(e) => setFilters({ ...filters, grade: e.target.value })} data-testid="lib-filter-grade"><option value="">All grades</option>{GRADES.map((g) => <option key={g}>{g}</option>)}</select>
          <select className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 text-sm" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} data-testid="lib-filter-status"><option value="">All status</option><option value="published">Published</option><option value="pending">Pending</option></select>
        </div>
        {items.length === 0 && <p className="text-sm text-slate-400 p-6 text-center">No items.</p>}
        {items.map((it) => (
          <div key={it.id} className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 flex items-start gap-3" data-testid={`lib-item-${it.id}`}>
            <BookOpen className="text-indigo-500 shrink-0 mt-0.5" size={18} />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-slate-800 dark:text-slate-100 truncate">{it.title} <span className="text-[10px] uppercase text-slate-400">· {it.material_type}</span></p>
              <p className="text-xs text-slate-400">{it.grade} · {it.subject} · {it.source === "school" ? `submitted by ${it.submitted_by_school_name || "a school"}` : "platform"}{it.file_name ? ` · ${it.file_name}` : ""}</p>
              {it.processing && <span className="text-[11px] text-amber-600">● processing text…</span>}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={`text-[10px] font-bold uppercase rounded-full px-2 py-0.5 ${it.status === "published" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{it.status}</span>
              {it.status === "pending" && <Button size="sm" onClick={() => approve(it.id)} data-testid={`lib-approve-${it.id}`}><Check size={13} className="mr-1" />Approve</Button>}
              <button className="text-rose-400 hover:text-rose-600" onClick={() => del(it.id)} data-testid={`lib-delete-${it.id}`}><Trash2 size={15} /></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TemplatesTab() {
  const [list, setList] = useState([]);
  const [edit, setEdit] = useState(null);  // {grade, subject, chaptersText}
  const load = useCallback(() => { api.get("/platform/curriculum-templates").then((r) => setList(r.data.templates)).catch((e) => toast.error(errText(e))); }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    const chapters = edit.chaptersText.split("\n").map((l) => l.trim()).filter(Boolean).map((title) => ({ title, topics: [] }));
    try { await api.post("/platform/curriculum-templates", { board: "kerala_scert", grade: edit.grade, subject: edit.subject, chapters }); toast.success("Template saved"); setEdit(null); load(); } catch (e) { toast.error(errText(e)); }
  };

  return (
    <div className="space-y-4" data-testid="lib-templates">
      <Button variant="outline" onClick={() => setEdit({ grade: "Grade 8", subject: "", chaptersText: "" })} data-testid="lib-template-new">+ New template</Button>
      {edit && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <select className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-2 text-sm" value={edit.grade} onChange={(e) => setEdit({ ...edit, grade: e.target.value })}>{GRADES.map((g) => <option key={g}>{g}</option>)}</select>
            <Input placeholder="Subject" value={edit.subject} onChange={(e) => setEdit({ ...edit, subject: e.target.value })} data-testid="lib-template-subject" />
          </div>
          <Textarea rows={8} placeholder="One chapter per line" value={edit.chaptersText} onChange={(e) => setEdit({ ...edit, chaptersText: e.target.value })} data-testid="lib-template-chapters" />
          <div className="flex gap-2"><Button onClick={save} data-testid="lib-template-save">Save</Button><Button variant="outline" onClick={() => setEdit(null)}>Cancel</Button></div>
        </div>
      )}
      {list.map((t) => (
        <div key={t.id} className="rounded-xl border border-slate-200 dark:border-slate-800 p-4" data-testid={`lib-template-${t.grade}-${t.subject}`}>
          <div className="flex items-center justify-between">
            <p className="font-medium text-slate-800 dark:text-slate-100">{t.grade} · {t.subject} <span className="text-xs text-slate-400">({t.chapters.length} chapters)</span></p>
            <Button size="sm" variant="outline" onClick={() => setEdit({ grade: t.grade, subject: t.subject, chaptersText: t.chapters.map((c) => c.title).join("\n") })}>Edit</Button>
          </div>
          <p className="text-xs text-slate-400 mt-1 line-clamp-2">{t.chapters.map((c) => c.title).join(" · ")}</p>
        </div>
      ))}
    </div>
  );
}
