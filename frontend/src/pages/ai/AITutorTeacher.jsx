import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, Plus, FileText, Loader2, X, BookOpen, CheckCircle2, Clock, AlertTriangle, XCircle, Send, Eye, Lock, Library, Sparkle, Pencil, Trash2, ChevronUp, ChevronDown, UploadCloud } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import CurriculumDetail from "./CurriculumDetail";
import { LibraryPreview } from "./LibraryPreview";

const API = process.env.REACT_APP_BACKEND_URL;
const ITEM_TYPES = ["chapter", "topic", "textbook", "notes", "syllabus", "worksheet", "question_paper", "examples", "practice_questions", "reference", "previous_year", "other"];

const STATUS = {
  draft: { c: "bg-slate-200 text-slate-600", i: FileText },
  pending: { c: "bg-amber-100 text-amber-700", i: Clock },
  published: { c: "bg-emerald-100 text-emerald-700", i: CheckCircle2 },
  approved: { c: "bg-emerald-100 text-emerald-700", i: CheckCircle2 },
  rejected: { c: "bg-rose-100 text-rose-700", i: XCircle },
  changes_requested: { c: "bg-orange-100 text-orange-700", i: AlertTriangle },
};
export const StatusChip = ({ s }) => {
  const m = STATUS[s] || STATUS.draft; const I = m.i;
  return <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase rounded-full px-2 py-0.5 ${m.c}`}><I size={10} /> {String(s || "").replace("_", " ")}</span>;
};

export default function AITutorTeacher() {
  const navigate = useNavigate();
  const [subjects, setSubjects] = useState([]);
  const [year, setYear] = useState("");
  const [layerOff, setLayerOff] = useState(false);
  const [sel, setSel] = useState("");
  const [cur, setCur] = useState(null);     // {exists, curriculum, items, can_contribute}
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [showContribute, setShowContribute] = useState(false);
  const [showDetail, setShowDetail] = useState(false);

  useEffect(() => {
    api.get("/ai/teaching-subjects").then((r) => { setSubjects(r.data.subjects || []); setYear(r.data.academic_year || ""); setLayerOff(r.data.ai_layer_enabled === false); }).catch((e) => toast.error(errText(e)));
  }, []);

  const picked = sel !== "" ? subjects[Number(sel)] : null;
  const loadCur = useCallback(() => {
    if (!picked || !year) return;
    setLoading(true);
    api.get(`/ai/curriculum?academic_year=${encodeURIComponent(year)}&class_name=${encodeURIComponent(picked.class_name)}&subject=${encodeURIComponent(picked.subject)}`)
      .then((r) => setCur(r.data)).catch((e) => toast.error(errText(e))).finally(() => setLoading(false));
  }, [picked, year]);
  useEffect(() => { setCur(null); if (picked) loadCur(); }, [sel]); // eslint-disable-line

  const submitCur = async () => {
    try { await api.post(`/ai/curriculum/${cur.curriculum.id}/submit`); toast.success("Submitted for approval"); loadCur(); }
    catch (e) { toast.error(errText(e)); }
  };
  const deleteDraft = async () => {
    if (!window.confirm("Delete this draft? This cannot be undone.")) return;
    try { await api.delete(`/ai/curriculum/${cur.curriculum.id}`); toast.success("Draft deleted"); setCur(null); loadCur(); }
    catch (e) { toast.error(errText(e)); }
  };

  const approvedItems = (cur?.items || []).filter((i) => i.status === "approved" && i.active);
  const chapters = [...new Set((cur?.items || []).filter((i) => i.chapter).map((i) => i.chapter))];

  return (
    <div className="space-y-6" data-testid="ai-tutor-teacher">
      <div>
        <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Sparkles className="text-violet-600" size={24} /> AI Tutor · Curriculum</h1>
        <p className="text-sm text-slate-500 mt-1">Build the shared curriculum knowledge base. Your contributions go to a principal for approval. <span className="text-slate-400">Academic year: {year || "—"}</span></p>
      </div>

      {layerOff && (
        <div className="rounded-xl border-2 border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 p-4 flex items-center gap-3" data-testid="ai-layer-disabled-banner">
          <Lock className="text-amber-600 shrink-0" size={18} />
          <p className="text-sm text-amber-800 dark:text-amber-200">The AI Tutor is currently <b>Disabled by LNMO Platform</b> for your school. You can still build the curriculum, but students can't chat until the platform enables the AI Layer.</p>
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="text-xs font-medium text-slate-400">Grade & subject you teach</label>
          <select className="mt-1 block rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-3 py-2 text-sm min-w-[260px]" value={sel} onChange={(e) => setSel(e.target.value)} data-testid="ai-subject-select">
            <option value="">Select…</option>
            {subjects.map((s, i) => <option key={i} value={i}>{s.class_name} · {s.subject}</option>)}
          </select>
        </div>
      </div>

      {loading && <p className="text-sm text-slate-400">Loading…</p>}

      {picked && cur && !cur.exists && (
        <div className="rounded-2xl border border-dashed border-violet-300 dark:border-violet-700 p-8 text-center" data-testid="ai-no-curriculum">
          <BookOpen className="mx-auto text-violet-400" size={32} />
          <p className="mt-2 text-slate-600 dark:text-slate-300">No curriculum yet for <b>{picked.class_name} · {picked.subject}</b>.</p>
          {cur.can_create && <Button className="mt-4" onClick={() => setShowCreate(true)} data-testid="ai-create-curriculum-btn"><Plus size={16} className="mr-1.5" /> Create curriculum</Button>}
        </div>
      )}

      {picked && cur && cur.exists && (
        <div className="space-y-4" data-testid="ai-curriculum-view">
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-heading text-lg font-bold text-slate-900 dark:text-slate-50">{cur.curriculum.name}</h2>
                <p className="text-xs text-slate-400 mt-0.5">{cur.curriculum.class_name} · {cur.curriculum.subject} · {cur.curriculum.academic_year}</p>
              </div>
              <div className="flex items-center gap-2">
                <StatusChip s={cur.curriculum.status} />
                {cur.curriculum.ai_enabled && <span className="text-[10px] font-bold uppercase rounded-full px-2 py-0.5 bg-violet-100 text-violet-700">AI ON</span>}
              </div>
            </div>
            {cur.curriculum.syllabus_text && <p className="text-sm text-slate-500 mt-2 whitespace-pre-line">{cur.curriculum.syllabus_text}</p>}
            {cur.curriculum.review_note && <p className="text-xs text-orange-600 mt-2">Reviewer note: {cur.curriculum.review_note}</p>}
            <div className="flex flex-wrap gap-2 mt-4">
              {["draft", "changes_requested"].includes(cur.curriculum.status) && cur.can_contribute && <Button size="sm" variant="outline" onClick={() => setShowEdit(true)} data-testid="ai-edit-draft-btn"><Pencil size={14} className="mr-1.5" /> Edit / resume</Button>}
              {["draft", "changes_requested"].includes(cur.curriculum.status) && <Button size="sm" onClick={submitCur} data-testid="ai-submit-curriculum-btn"><Send size={14} className="mr-1.5" /> Submit for approval</Button>}
              {["draft", "changes_requested"].includes(cur.curriculum.status) && cur.can_contribute && <Button size="sm" variant="outline" className="text-rose-600 border-rose-200 hover:bg-rose-50" onClick={deleteDraft} data-testid="ai-delete-draft-btn"><Trash2 size={14} className="mr-1.5" /> Delete draft</Button>}
              {cur.can_contribute && cur.curriculum.status === "published" && <Button size="sm" variant="outline" onClick={() => setShowContribute(true)} data-testid="ai-contribute-btn"><Plus size={14} className="mr-1.5" /> Add chapter, topic or material</Button>}
              <Button size="sm" variant="outline" onClick={() => navigate(`/teacher/ai-tutor/curriculum/${cur.curriculum.id}`)} data-testid="ai-view-detail-btn"><Eye size={14} className="mr-1.5" /> View full curriculum</Button>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
            <h3 className="font-heading font-semibold text-slate-800 dark:text-slate-100 mb-3">Approved materials</h3>
            {approvedItems.length === 0 && <p className="text-sm text-slate-400">No approved materials yet.</p>}
            {chapters.map((ch) => (
              <div key={ch} className="mb-4">
                <p className="text-sm font-semibold text-violet-700 dark:text-violet-300">{ch}</p>
                <ul className="mt-1 space-y-1">
                  {approvedItems.filter((i) => i.chapter === ch && i.item_type !== "chapter").map((i) => <ItemRow key={i.id} i={i} />)}
                </ul>
              </div>
            ))}
            {approvedItems.filter((i) => !i.chapter && i.item_type !== "chapter").map((i) => <ItemRow key={i.id} i={i} />)}
          </div>

          <MyContributions items={(cur.items || []).filter((i) => i.status !== "approved" || !i.active)} />
        </div>
      )}

      {showCreate && <CreateDialog picked={picked} year={year} onClose={() => setShowCreate(false)} onDone={() => { setShowCreate(false); loadCur(); }} />}
      {showEdit && <CreateDialog picked={picked} year={year} editCur={cur} onClose={() => setShowEdit(false)} onDone={() => { setShowEdit(false); loadCur(); }} />}
      {showContribute && <ContributeDialog cid={cur.curriculum.id} chapters={chapters} grade={cur.curriculum.class_name} subject={cur.curriculum.subject} onClose={() => setShowContribute(false)} onDone={() => { setShowContribute(false); loadCur(); }} />}
      {showDetail && <CurriculumDetail cid={cur.curriculum.id} onClose={() => setShowDetail(false)} onChanged={loadCur} />}
    </div>
  );
}

function ItemRow({ i }) {
  return (
    <li className="flex items-center gap-2 text-sm" data-testid={`ai-item-${i.id}`}>
      <span className="text-[10px] uppercase font-bold text-slate-400">{i.item_type.replace("_", " ")}</span>
      <span className="text-slate-700 dark:text-slate-200">{i.title || i.topic}</span>
      {i.has_file && <a href={`${API}/api/ai/items/${i.id}/file`} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline inline-flex items-center gap-0.5"><FileText size={12} /> {i.file_name}</a>}
      {i.version > 1 && <span className="text-[10px] text-slate-400">v{i.version}</span>}
      <span className="ml-auto text-xs text-slate-400">by {i.contributor_name}</span>
    </li>
  );
}

function MyContributions({ items }) {
  if (!items.length) return null;
  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid="ai-my-pending">
      <h3 className="font-heading font-semibold text-slate-800 dark:text-slate-100 mb-3">Pending / in-review contributions</h3>
      <ul className="space-y-2">
        {items.map((i) => (
          <li key={i.id} className="flex items-center gap-2 text-sm">
            <span className="text-[10px] uppercase font-bold text-slate-400">{i.item_type.replace("_", " ")}</span>
            <span className="text-slate-700 dark:text-slate-200">{i.title || i.topic}</span>
            {i.chapter && <span className="text-xs text-slate-400">· {i.chapter}</span>}
            <span className="ml-auto"><StatusChip s={i.status} /></span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CreateDialog({ picked, year, editCur, onClose, onDone }) {
  const isEdit = !!editCur;
  const cid0 = editCur?.curriculum?.id;
  const its = editCur?.items || [];
  const tbItem = its.find((i) => i.item_type === "textbook");
  const chItems = its.filter((i) => i.item_type === "chapter").sort((a, b) => (a.order || 0) - (b.order || 0));
  const matItems = its.filter((i) => !["textbook", "chapter", "topic"].includes(i.item_type));
  const topicsFor = (ch) => its.filter((i) => i.item_type === "topic" && i.chapter === ch).map((t) => t.title || t.topic);

  const [step, setStep] = useState(1);
  const [name, setName] = useState(isEdit ? (editCur.curriculum.name || "") : `${picked.class_name} ${picked.subject}`);
  const [syllabus, setSyllabus] = useState(isEdit ? (editCur.curriculum.syllabus_text || "") : "");
  const [textbook, setTextbook] = useState(null);        // File
  const [existingTextbook] = useState(tbItem || null);
  const [textbookTitle, setTextbookTitle] = useState(tbItem?.title || "Class textbook");
  const [chapters, setChapters] = useState(
    isEdit && chItems.length
      ? chItems.map((c) => ({ chapter: c.chapter || c.title, topics: topicsFor(c.chapter || c.title).join(", "), id: c.id, locked: true }))
      : [{ chapter: "", topics: "" }]);
  const [materials, setMaterials] = useState([]);        // new [{type, chapter, title, text, file}]
  const [existingMats, setExistingMats] = useState(isEdit ? matItems.map((m) => ({ id: m.id, type: m.item_type, title: m.title || m.topic, chapter: m.chapter || "", origChapter: m.chapter || "" })) : []);
  const [removedIds, setRemovedIds] = useState([]);
  const [libTextbook, setLibTextbook] = useState(null);  // {library_id, title, material_type}
  const [libPicks, setLibPicks] = useState([]);          // [{library_id, title, chapter, material_type}]
  const [tplLoading, setTplLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadTemplate = async () => {
    setTplLoading(true);
    try {
      const r = await api.get("/ai/curriculum-template", { params: { grade: picked.class_name, subject: picked.subject } });
      const t = r.data.template;
      if (!t) { toast.message(`No Kerala SCERT template for ${picked.class_name} ${picked.subject} yet`); return; }
      if (isEdit) {
        const have = new Set(chapters.map((c) => c.chapter.trim().toLowerCase()));
        const add = t.chapters.filter((c) => !have.has(c.title.trim().toLowerCase())).map((c) => ({ chapter: c.title, topics: (c.topics || []).join(", ") }));
        setChapters([...chapters, ...add]);
        toast.success(`Added ${add.length} new chapter(s) from Kerala SCERT`);
      } else {
        setChapters(t.chapters.map((c) => ({ chapter: c.title, topics: (c.topics || []).join(", ") })));
        toast.success(`Loaded ${t.chapters.length} chapters from Kerala SCERT`);
      }
    } catch (e) { toast.error("Could not load template"); } finally { setTplLoading(false); }
  };

  const validChapters = chapters.filter((c) => c.chapter.trim());
  const hasTextbook = !!textbook || !!libTextbook || (isEdit && !!existingTextbook);
  const step1ok = !!name.trim() && hasTextbook;
  const step2ok = validChapters.length > 0;

  const moveChapter = (i, dir) => { const j = i + dir; if (j < 0 || j >= chapters.length) return; const n = [...chapters]; [n[i], n[j]] = [n[j], n[i]]; setChapters(n); };
  const removeChapter = (i) => { const c = chapters[i]; if (c.id) setRemovedIds((r) => [...r, c.id]); setChapters(chapters.filter((_, k) => k !== i)); };
  const removeExistingMat = (id) => { setRemovedIds((r) => [...r, id]); setExistingMats(existingMats.filter((m) => m.id !== id)); };
  const setExMatChapter = (id, ch) => setExistingMats(existingMats.map((m) => (m.id === id ? { ...m, chapter: ch } : m)));
  const addMaterial = () => setMaterials([...materials, { type: "notes", chapter: validChapters[0]?.chapter?.trim() || "", title: "", text: "", file: null }]);
  const setMat = (i, k, v) => { const n = [...materials]; n[i][k] = v; setMaterials(n); };

  const run = async (submitNow) => {
    if (!name.trim()) { toast.error("Enter a name"); setStep(1); return; }
    if (!step1ok) { toast.error("Upload a textbook/reference first"); setStep(1); return; }
    if (!step2ok) { toast.error("Add at least one chapter"); setStep(2); return; }
    for (const m of materials) {
      if (!m.chapter.trim()) { toast.error("Every material must be attached to a chapter"); setStep(3); return; }
      if (!m.title.trim()) { toast.error("Give each material a title"); setStep(3); return; }
    }
    setBusy(true);
    try {
      let cid = cid0;
      if (!isEdit) {
        // 1) create the draft with chapters + topics
        const chs = validChapters.map((c) => ({ chapter: c.chapter.trim(), topics: c.topics.split(",").map((t) => t.trim()).filter(Boolean) }));
        const res = await api.post("/ai/curriculum", { academic_year: year, class_name: picked.class_name, subject: picked.subject, name, syllabus_text: syllabus, chapters: chs, items: [], submit: false });
        cid = res.data.curriculum.id;
        // 2) add the textbook: uploaded file OR LNMO Library reference (no upload)
        if (textbook) {
          const tb = new FormData();
          tb.append("item_type", "textbook"); tb.append("title", textbookTitle.trim()); tb.append("chapter", ""); tb.append("file", textbook);
          await api.post(`/ai/curriculum/${cid}/items`, tb);
        } else if (libTextbook) {
          await api.post(`/ai/curriculum/${cid}/import-library`, { library_id: libTextbook.library_id, chapter: "" });
        }
      } else {
        // 1) save name/syllabus
        await api.put(`/ai/curriculum/${cid}`, { name: name.trim(), syllabus_text: syllabus });
        // 2) replace textbook if a new file OR a library reference was chosen
        if (textbook || libTextbook) {
          if (existingTextbook) { try { await api.delete(`/ai/items/${existingTextbook.id}`); } catch (e) { /* ignore */ } }
          if (textbook) {
            const tb = new FormData();
            tb.append("item_type", "textbook"); tb.append("title", textbookTitle.trim()); tb.append("chapter", ""); tb.append("file", textbook);
            await api.post(`/ai/curriculum/${cid}/items`, tb);
          } else {
            await api.post(`/ai/curriculum/${cid}/import-library`, { library_id: libTextbook.library_id, chapter: "" });
          }
        }
        // 3) delete removed chapters/materials
        for (const id of removedIds) { try { await api.delete(`/ai/items/${id}`); } catch (e) { /* ignore */ } }
        // 4) add brand-new chapters (+ their topics)
        for (const c of validChapters.filter((x) => !x.id)) {
          const cf = new FormData();
          cf.append("item_type", "chapter"); cf.append("chapter", c.chapter.trim()); cf.append("title", c.chapter.trim());
          await api.post(`/ai/curriculum/${cid}/items`, cf);
          for (const tp of c.topics.split(",").map((t) => t.trim()).filter(Boolean)) {
            const tf = new FormData();
            tf.append("item_type", "topic"); tf.append("chapter", c.chapter.trim()); tf.append("topic", tp); tf.append("title", tp);
            await api.post(`/ai/curriculum/${cid}/items`, tf);
          }
        }
        // 5) move existing materials whose chapter changed
        for (const m of existingMats) {
          if (m.chapter.trim() && m.chapter.trim() !== (m.origChapter || "").trim()) {
            await api.post(`/ai/items/${m.id}/move`, { chapter: m.chapter.trim() });
          }
        }
      }
      // new material uploads (both modes)
      for (const m of materials) {
        const fd = new FormData();
        fd.append("item_type", m.type); fd.append("chapter", m.chapter); fd.append("title", m.title.trim());
        fd.append("text_content", m.text || "");
        if (m.file) fd.append("file", m.file);
        await api.post(`/ai/curriculum/${cid}/items`, fd);
      }
      // attach any LNMO Library items (both modes)
      for (const p of libPicks) {
        await api.post(`/ai/curriculum/${cid}/import-library`, { library_id: p.library_id, chapter: p.chapter });
      }
      // persist chapter display order
      await api.post(`/ai/curriculum/${cid}/chapters/reorder`, { chapters: validChapters.map((c) => c.chapter.trim()) });
      // submit or leave as draft
      if (submitNow) await api.post(`/ai/curriculum/${cid}/submit`);
      toast.success(submitNow ? (isEdit ? "Updated & submitted for approval" : "Created & submitted for approval") : "Draft saved — finish later");
      onDone();
    } catch (e) { toast.error(typeof errText(e) === "string" ? errText(e) : "Could not save curriculum"); } finally { setBusy(false); }
  };

  const StepDot = ({ n, label, ok }) => (
    <div className="flex items-center gap-1.5" data-testid={`ai-wiz-step-${n}`}>
      <span className={`w-6 h-6 rounded-full grid place-items-center text-xs font-bold ${step === n ? "bg-violet-600 text-white" : ok ? "bg-emerald-500 text-white" : "bg-slate-200 text-slate-500"}`}>{ok && step !== n ? "✓" : n}</span>
      <span className={`text-xs ${step === n ? "text-violet-700 font-semibold" : "text-slate-400"}`}>{label}</span>
    </div>
  );

  return (
    <Modal title={isEdit ? "Edit curriculum" : "Create curriculum"} onClose={onClose} testid="ai-create-dialog">
      <div className="flex items-center justify-between mb-4">
        <StepDot n={1} label="Textbook" ok={step1ok} />
        <div className="h-px flex-1 bg-slate-200 mx-2" />
        <StepDot n={2} label="Chapters" ok={step2ok} />
        <div className="h-px flex-1 bg-slate-200 mx-2" />
        <StepDot n={3} label="Materials" ok={step1ok && step2ok} />
      </div>

      {step === 1 && (
        <div data-testid="ai-wiz-1">
          <Input placeholder="Curriculum name" value={name} onChange={(e) => setName(e.target.value)} data-testid="ai-name-input" />
          <Textarea className="mt-3" placeholder="Syllabus overview (optional)" value={syllabus} onChange={(e) => setSyllabus(e.target.value)} data-testid="ai-syllabus-input" />
          <p className="text-xs font-medium text-slate-400 mt-4">Step 1 · {isEdit ? "Textbook / main reference" : "Upload the textbook / main reference (required)"}</p>
          {isEdit && existingTextbook && !textbook && (
            <div className="mt-2 flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/30 rounded-lg px-3 py-2" data-testid="ai-wiz-existing-textbook">
              <CheckCircle2 size={14} /> {existingTextbook.file_name || existingTextbook.title || "Textbook uploaded"}
            </div>
          )}
          {isEdit && !existingTextbook && !textbook && !libTextbook && (
            <div className="mt-2 flex items-center gap-2 text-sm text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/30 rounded-lg px-3 py-2" data-testid="ai-wiz-no-textbook-hint">
              <AlertTriangle size={14} /> No textbook saved on this draft — upload one or attach from the LNMO Library below.
            </div>
          )}
          <Input className="mt-2" placeholder="Textbook title" value={textbookTitle} onChange={(e) => setTextbookTitle(e.target.value)} data-testid="ai-wiz-textbook-title" />
          {textbook ? (
            <div className="mt-2 flex items-center gap-3 rounded-xl border border-indigo-200 dark:border-indigo-800 bg-indigo-50/50 dark:bg-indigo-950/20 px-3 py-2.5" data-testid="ai-wiz-textbook-picked">
              <FileText size={18} className="text-indigo-600 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-800 dark:text-slate-100 truncate">{textbook.name}</p>
                <p className="text-xs text-slate-400">{(textbook.size / 1024 / 1024).toFixed(2)} MB</p>
              </div>
              <label className="text-xs font-semibold text-indigo-600 cursor-pointer">Change<input type="file" hidden accept=".pdf,.docx,.txt" onChange={(e) => e.target.files[0] && setTextbook(e.target.files[0])} data-testid="ai-wiz-textbook-change" /></label>
              <button className="text-xs font-semibold text-rose-500" onClick={() => setTextbook(null)} data-testid="ai-wiz-textbook-remove">Remove</button>
            </div>
          ) : libTextbook ? (
            <div className="mt-2 flex items-center gap-3 rounded-xl border border-indigo-300 dark:border-indigo-700 bg-indigo-50/60 dark:bg-indigo-950/30 px-3 py-2.5" data-testid="ai-wiz-textbook-lib">
              <Library size={18} className="text-indigo-600 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-800 dark:text-slate-100 truncate">{libTextbook.title}</p>
                <p className="text-[10px] uppercase font-bold text-indigo-500">LNMO Library · reference (no upload)</p>
              </div>
              <button className="text-xs font-semibold text-rose-500" onClick={() => setLibTextbook(null)} data-testid="ai-wiz-textbook-lib-remove">Remove</button>
            </div>
          ) : (
            <>
              <label className="mt-2 flex flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed border-indigo-300 dark:border-indigo-700 bg-indigo-50/40 dark:bg-indigo-950/10 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 transition-colors px-4 py-6 cursor-pointer text-center" data-testid="ai-wiz-textbook-dropzone">
                <UploadCloud size={26} className="text-indigo-500" />
                <span className="text-sm font-semibold text-indigo-700 dark:text-indigo-300">{isEdit && existingTextbook ? "Replace textbook — click to upload" : "Click to upload textbook"}</span>
                <span className="text-xs text-slate-400">PDF, DOCX or TXT · up to 60MB</span>
                <input type="file" hidden accept=".pdf,.docx,.txt" onChange={(e) => e.target.files[0] && setTextbook(e.target.files[0])} data-testid="ai-wiz-textbook-file" />
              </label>
              <p className="text-center text-xs font-semibold text-slate-400 my-2">— OR —</p>
              <LibraryBrowser grade={picked.class_name} subject={picked.subject} only={["textbook", "reference"]}
                picks={libTextbook ? [{ library_id: libTextbook.library_id }] : []}
                onAttach={(it) => { setLibTextbook({ library_id: it.id, title: it.title, material_type: it.material_type }); setTextbook(null); setTextbookTitle(it.title || textbookTitle); }} />
            </>
          )}
          <div className="flex justify-end mt-5">
            <Button disabled={!step1ok || !name.trim()} onClick={() => setStep(2)} data-testid="ai-wiz-next-1">Next: Chapters</Button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div data-testid="ai-wiz-2">
          <p className="text-xs font-medium text-slate-400">Step 2 · Add chapters (reorder with arrows; topics optional, comma-separated)</p>
          {chapters.map((c, i) => (
            <div key={c.id || i} className="mt-2 flex items-start gap-2" data-testid={`ai-chapter-row-${i}`}>
              <div className="flex flex-col pt-1">
                <button className="text-slate-400 hover:text-slate-700 disabled:opacity-30" disabled={i === 0} onClick={() => moveChapter(i, -1)} data-testid={`ai-chapter-up-${i}`}><ChevronUp size={14} /></button>
                <button className="text-slate-400 hover:text-slate-700 disabled:opacity-30" disabled={i === chapters.length - 1} onClick={() => moveChapter(i, 1)} data-testid={`ai-chapter-down-${i}`}><ChevronDown size={14} /></button>
              </div>
              <div className="grid grid-cols-2 gap-2 flex-1">
                {c.locked ? (
                  <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/40 px-2 py-2 text-sm text-slate-700 dark:text-slate-200 truncate" data-testid={`ai-chapter-${i}`}>{c.chapter}</div>
                ) : (
                  <Input placeholder={`Chapter ${i + 1}`} value={c.chapter} onChange={(e) => { const n = [...chapters]; n[i].chapter = e.target.value; setChapters(n); }} data-testid={`ai-chapter-${i}`} />
                )}
                {c.locked ? (
                  <div className="px-2 py-2 text-xs text-slate-400 truncate">{c.topics || "—"}</div>
                ) : (
                  <Input placeholder="Topics (optional, comma-separated)" value={c.topics} onChange={(e) => { const n = [...chapters]; n[i].topics = e.target.value; setChapters(n); }} data-testid={`ai-chapter-topics-${i}`} />
                )}
              </div>
              <button className="text-rose-400 hover:text-rose-600 pt-2" onClick={() => removeChapter(i)} data-testid={`ai-chapter-remove-${i}`}><Trash2 size={14} /></button>
            </div>
          ))}
          <button className="text-xs text-violet-600 mt-2" onClick={() => setChapters([...chapters, { chapter: "", topics: "" }])} data-testid="ai-add-chapter">+ Add chapter</button>
          <button className="text-xs text-indigo-600 mt-2 ml-4 inline-flex items-center gap-1" onClick={loadTemplate} data-testid="ai-wiz-load-template"><Sparkle size={12} /> {tplLoading ? "Loading…" : "Start from Kerala SCERT template"}</button>
          <div className="flex justify-between mt-5">
            <Button variant="outline" onClick={() => setStep(1)}>Back</Button>
            <Button disabled={!step2ok} onClick={() => setStep(3)} data-testid="ai-wiz-next-2">Next: Materials</Button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div data-testid="ai-wiz-3">
          <p className="text-xs font-medium text-slate-400">Step 3 · Upload learning materials (each must attach to a chapter)</p>
          {isEdit && existingMats.length > 0 && (
            <div className="mt-2 space-y-1.5" data-testid="ai-wiz-existing-mats">
              <p className="text-xs font-medium text-slate-400">Existing materials — move between chapters or remove</p>
              {existingMats.map((m) => (
                <div key={m.id} className="flex items-center gap-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 px-2 py-1.5" data-testid={`ai-wiz-exmat-${m.id}`}>
                  <span className="uppercase text-[9px] font-bold text-slate-400">{m.type.replace("_", " ")}</span>
                  <span className="truncate">{m.title}</span>
                  <select className="ml-auto rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1 py-0.5" value={m.chapter} onChange={(e) => setExMatChapter(m.id, e.target.value)} data-testid={`ai-wiz-exmat-chapter-${m.id}`}>
                    {validChapters.map((c) => <option key={c.chapter} value={c.chapter.trim()}>{c.chapter.trim()}</option>)}
                  </select>
                  <button className="text-rose-400 hover:text-rose-600" onClick={() => removeExistingMat(m.id)} data-testid={`ai-wiz-exmat-remove-${m.id}`}><Trash2 size={13} /></button>
                </div>
              ))}
            </div>
          )}
          {materials.length === 0 && !existingMats.length && <p className="text-sm text-slate-400 mt-2">No materials yet — add some, or submit with just the textbook & chapters.</p>}
          {materials.map((m, i) => (
            <div key={i} className="mt-3 rounded-xl border border-slate-200 dark:border-slate-700 p-3 space-y-2" data-testid={`ai-wiz-material-${i}`}>
              <div className="grid grid-cols-2 gap-2">
                <select className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-2 text-sm" value={m.type} onChange={(e) => setMat(i, "type", e.target.value)} data-testid={`ai-wiz-mat-type-${i}`}>
                  {["notes", "worksheet", "question_paper", "examples", "practice_questions", "reference", "previous_year", "other"].map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
                </select>
                <select className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-2 text-sm" value={m.chapter} onChange={(e) => setMat(i, "chapter", e.target.value)} data-testid={`ai-wiz-mat-chapter-${i}`}>
                  <option value="">Select chapter…</option>
                  {validChapters.map((c) => <option key={c.chapter} value={c.chapter.trim()}>{c.chapter.trim()}</option>)}
                </select>
              </div>
              <Input placeholder="Material title" value={m.title} onChange={(e) => setMat(i, "title", e.target.value)} data-testid={`ai-wiz-mat-title-${i}`} />
              <Textarea placeholder="Typed content (optional)" value={m.text} onChange={(e) => setMat(i, "text", e.target.value)} />
              <label className="flex items-center gap-2 text-sm text-indigo-600 cursor-pointer">
                <FileText size={14} /> {m.file ? m.file.name : "Attach file (optional)"}
                <input type="file" hidden accept=".pdf,.docx,.txt,.jpg,.jpeg,.png" onChange={(e) => setMat(i, "file", e.target.files[0])} data-testid={`ai-wiz-mat-file-${i}`} />
              </label>
            </div>
          ))}
          <button className="text-xs text-violet-600 mt-2" onClick={addMaterial} data-testid="ai-wiz-add-material">+ Add material</button>
          {libPicks.length > 0 && (
            <div className="mt-3" data-testid="ai-wiz-lib-picks">
              <p className="text-xs font-medium text-slate-400">From LNMO Library</p>
              {libPicks.map((p, i) => (
                <div key={p.library_id} className="mt-1 flex items-center gap-2 text-xs rounded-lg bg-indigo-50 dark:bg-indigo-950/30 px-2 py-1.5">
                  <Library size={12} className="text-indigo-500" />
                  <span className="truncate">{p.title}</span>
                  {!["textbook", "reference", "other"].includes(p.material_type) && (
                    <select className="ml-auto rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1" value={p.chapter} onChange={(e) => { const n = [...libPicks]; n[i].chapter = e.target.value; setLibPicks(n); }} data-testid={`ai-wiz-libpick-chapter-${i}`}>
                      {validChapters.map((c) => <option key={c.chapter} value={c.chapter.trim()}>{c.chapter.trim()}</option>)}
                    </select>
                  )}
                  <button className={`${["textbook", "reference", "other"].includes(p.material_type) ? "ml-auto" : ""} text-rose-400`} onClick={() => setLibPicks(libPicks.filter((x) => x.library_id !== p.library_id))}>remove</button>
                </div>
              ))}
            </div>
          )}
          <div className="mt-3">
            <LibraryBrowser grade={picked.class_name} subject={picked.subject} picks={libPicks} chapters={validChapters.map((c) => c.chapter.trim())}
              onAttach={(it, ch) => setLibPicks([...libPicks, { library_id: it.id, title: it.title, chapter: ch, material_type: it.material_type }])} />
          </div>
          <div className="flex justify-between gap-2 mt-5">
            <Button variant="outline" onClick={() => setStep(2)}>Back</Button>
            <div className="flex gap-2">
              <Button variant="outline" disabled={busy} onClick={() => run(false)} data-testid="ai-wiz-save-draft">Finish later</Button>
              <Button disabled={busy} onClick={() => run(true)} data-testid="ai-create-submit">{busy ? <Loader2 className="animate-spin" size={16} /> : "Submit for approval"}</Button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}

function LibraryBrowser({ grade, subject, picks = [], onAttach, chapters = [], only = null }) {
  const [items, setItems] = useState(null);
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [preview, setPreview] = useState(null);
  useEffect(() => {
    const t = setTimeout(() => {
      api.get("/ai/central-library", { params: { grade, subject, material_type: only ? undefined : (type || undefined), q: q || undefined } })
        .then((r) => setItems(r.data.items || [])).catch(() => setItems([]));
    }, 250);
    return () => clearTimeout(t);
  }, [grade, subject, type, q, only ? only.join(",") : ""]);
  const filtered = only ? (items || []).filter((it) => only.includes(it.material_type)) : (items || []);
  const needsChapter = (mt) => !["textbook", "reference", "other"].includes(mt);
  return (
    <div className="rounded-xl border-2 border-indigo-200 dark:border-indigo-900 bg-indigo-50/40 dark:bg-indigo-950/20 p-3" data-testid="ai-library-browser">
      <div className="flex items-center gap-2 mb-2">
        <Library size={15} className="text-indigo-600" />
        <p className="text-sm font-semibold text-indigo-800 dark:text-indigo-200">{only ? "Attach a textbook from the LNMO Library" : "Browse LNMO Library"}</p>
        <span className="text-[10px] text-indigo-400 ml-auto">{grade} · {subject}</span>
      </div>
      <div className="flex gap-2 mb-2">
        <Input className="h-8 text-xs" placeholder="Search title or description…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="ai-library-search" />
        {!only && (
          <select className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 text-xs" value={type} onChange={(e) => setType(e.target.value)} data-testid="ai-library-type">
            <option value="">All types</option>
            {["textbook", "notes", "question_paper", "worksheet", "reference", "other"].map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
          </select>
        )}
      </div>
      <p className="text-[10px] text-indigo-400 mb-2">Attaching references the shared file — no re-upload, no extra storage for your school.</p>
      {items === null && <p className="text-xs text-slate-400">Loading…</p>}
      {items !== null && filtered.length === 0 && <p className="text-xs text-slate-400">No published library items match.</p>}
      <ul className="space-y-1.5 max-h-56 overflow-y-auto">
        {filtered.map((it) => {
          const chosen = picks.some((p) => p.library_id === it.id);
          return (
            <li key={it.id} className="flex items-center gap-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 px-2.5 py-1.5" data-testid={`ai-library-item-${it.id}`}>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-slate-800 dark:text-slate-100 truncate">{it.title} <span className="text-[9px] uppercase text-slate-400">· {it.material_type.replace("_", " ")}</span></p>
                <p className="text-[10px] text-slate-400 truncate">{it.file_name || "typed content"}</p>
              </div>
              {(it.has_file || it.has_text) && (
                <button onClick={() => setPreview(it)} className="text-[11px] font-semibold text-indigo-600 inline-flex items-center gap-0.5" data-testid={`ai-library-view-${it.id}`}><Eye size={13} /> View</button>
              )}
              <button
                disabled={chosen}
                onClick={() => onAttach(it, needsChapter(it.material_type) ? (chapters[0] || "") : "")}
                className={`text-[11px] font-semibold rounded-full px-2.5 py-1 ${chosen ? "bg-emerald-100 text-emerald-600" : "bg-indigo-600 text-white hover:bg-indigo-700"}`}
                data-testid={`ai-library-attach-${it.id}`}>
                {chosen ? "Added ✓" : "Attach"}
              </button>
            </li>
          );
        })}
      </ul>
      {preview && <LibraryPreview libraryId={preview.id} fallbackTitle={preview.title} onClose={() => setPreview(null)} />}
    </div>
  );
}

function ContributeDialog({ cid, chapters, grade, subject, onClose, onDone }) {
  const [type, setType] = useState("worksheet");
  const [chapter, setChapter] = useState(chapters[0] || "");
  const [topic, setTopic] = useState("");
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);

  const isChapter = type === "chapter";
  const isTopic = type === "topic";

  const submit = async () => {
    if (isChapter && !chapter.trim()) { toast.error("Enter a chapter name"); return; }
    if (isTopic && !topic.trim()) { toast.error("Enter a topic name"); return; }
    if (!isChapter && !isTopic && !title.trim()) { toast.error("Enter a title"); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      const finalTitle = isChapter ? chapter.trim() : isTopic ? topic.trim() : title.trim();
      fd.append("item_type", type); fd.append("chapter", chapter); fd.append("topic", topic);
      fd.append("title", finalTitle); fd.append("description", desc); fd.append("text_content", text);
      if (file) fd.append("file", file);
      await api.post(`/ai/curriculum/${cid}/items`, fd);
      toast.success(isChapter || isTopic ? `${isChapter ? "Chapter" : "Topic"} submitted for approval` : "Contribution submitted for approval");
      onDone();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <Modal title="Contribute learning material" onClose={onClose} testid="ai-contribute-dialog">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs font-medium text-slate-400">Material type</label>
          <select className="w-full mt-1 rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-2 text-sm" value={type} onChange={(e) => setType(e.target.value)} data-testid="ai-contrib-type">
            {ITEM_TYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-medium text-slate-400">Chapter</label>
          <input list="ai-chapters" className="w-full mt-1 rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-2 text-sm" value={chapter} onChange={(e) => setChapter(e.target.value)} data-testid="ai-contrib-chapter" />
          <datalist id="ai-chapters">{chapters.map((c) => <option key={c} value={c} />)}</datalist>
        </div>
      </div>
      {isChapter && <p className="text-xs text-slate-400 mt-2">Adding a new <b>chapter</b> — enter the chapter name above. It goes to a principal for approval.</p>}
      {isTopic && <Input className="mt-3" placeholder="Topic name" value={topic} onChange={(e) => setTopic(e.target.value)} data-testid="ai-contrib-topic-name" />}
      {!isChapter && !isTopic && <>
        <Input className="mt-3" placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} data-testid="ai-contrib-title" />
        <Input className="mt-3" placeholder="Topic (optional)" value={topic} onChange={(e) => setTopic(e.target.value)} />
      </>}
      {!isChapter && <>
        <Textarea className="mt-3" placeholder="Description (optional)" value={desc} onChange={(e) => setDesc(e.target.value)} />
        <Textarea className="mt-3" placeholder="Typed content / explanation (optional)" value={text} onChange={(e) => setText(e.target.value)} data-testid="ai-contrib-text" />
        <label className="mt-3 flex items-center gap-2 text-sm text-indigo-600 cursor-pointer">
          <FileText size={15} /> Attach file (PDF/DOCX/TXT/JPG/PNG ≤10MB)
          <input type="file" hidden accept=".pdf,.docx,.txt,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files[0])} data-testid="ai-contrib-file" />
        </label>
        {file && <p className="text-xs text-slate-500">{file.name}</p>}
      </>}
      <Button className="w-full mt-4" disabled={busy} onClick={submit} data-testid="ai-contrib-submit">{busy ? <Loader2 className="animate-spin" size={16} /> : "Submit contribution"}</Button>
      <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800">
        <LibraryBrowser grade={grade} subject={subject} chapters={chapters}
          onAttach={async (it, ch) => {
            try {
              await api.post(`/ai/curriculum/${cid}/import-library`, { library_id: it.id, chapter: ch });
              toast.success(`"${it.title}" attached — pending principal approval`);
              onDone();
            } catch (e) { toast.error(errText(e)); }
          }} />
      </div>
    </Modal>
  );
}

function Modal({ title, children, onClose, testid }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" data-testid={testid}>
      <div className="w-full max-w-lg rounded-3xl bg-white dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-800 shadow-2xl p-6 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-white">{title}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}
