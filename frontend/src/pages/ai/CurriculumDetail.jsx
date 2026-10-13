import { useCallback, useEffect, useState } from "react";
import { X, FileText, Loader2, MessageSquare, CheckCircle2, XCircle, AlertTriangle, Send, BookOpen, Trash2, Library, ChevronUp, ChevronDown, Eye } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Textarea } from "../../components/ui/textarea";
import { StatusChip } from "./AITutorTeacher";
import { LibraryPreview } from "./LibraryPreview";

const API = process.env.REACT_APP_BACKEND_URL;
const fmtDate = (s) => (s ? new Date(s).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—");

function ReviewBtns({ onReview, testid, size = "sm" }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <Button size={size} onClick={() => onReview("approve")} data-testid={`${testid}-approve`} className="bg-emerald-600 hover:bg-emerald-700 text-white"><CheckCircle2 size={13} className="mr-1" /> Approve</Button>
      <Button size={size} variant="outline" onClick={() => { const n = window.prompt("What changes are needed?"); if (n) onReview("changes", n); }} data-testid={`${testid}-changes`}><AlertTriangle size={13} className="mr-1" /> Changes</Button>
      <Button size={size} variant="outline" className="text-rose-600" onClick={() => onReview("reject")} data-testid={`${testid}-reject`}><XCircle size={13} className="mr-1" /> Reject</Button>
    </div>
  );
}

function ItemRow({ i, canReview, canComment, canSubmitLib, canMove, chapterOptions = [], onReviewItem, onCommentItem, onDeleteItem, onSubmitLib, onMove }) {
  const [showC, setShowC] = useState(false);
  const [txt, setTxt] = useState("");
  const [preview, setPreview] = useState(false);
  const approved = i.status === "approved" || i.status === "published";
  const canPreview = i.has_file || (i.source === "lnmo_library" && i.library_id);
  return (
    <li className="border-t border-slate-100 dark:border-slate-800 py-2" data-testid={`ai-detail-item-${i.id}`}>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-[10px] uppercase font-bold text-slate-400 min-w-[90px]">{i.item_type.replace("_", " ")}</span>
        <span className="text-slate-700 dark:text-slate-200 font-medium">{i.title || i.topic || i.chapter}</span>
        {i.source === "lnmo_library" && <span className="text-[9px] font-bold uppercase rounded-full px-1.5 py-0.5 bg-indigo-100 text-indigo-700 inline-flex items-center gap-0.5" data-testid={`ai-item-lib-badge-${i.id}`}><Library size={10} /> LNMO Library</span>}
        {i.version > 1 && <span className="text-[10px] text-slate-400">v{i.version}</span>}
        {!i.active && <span className="text-[10px] text-slate-400 italic">retired</span>}
        {i.has_file && <a href={`${API}/api/ai/items/${i.id}/file`} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline inline-flex items-center gap-0.5"><FileText size={12} /> {i.file_name}</a>}
        <span className="ml-auto flex items-center gap-2">
          <span className="text-xs text-slate-400">{i.contributor_name} · {fmtDate(i.contributed_at)}</span>
          <StatusChip s={i.status} />
          {canReview && <button onClick={() => onDeleteItem(i)} className="text-rose-400 hover:text-rose-600" data-testid={`ai-item-delete-${i.id}`} title="Delete"><Trash2 size={14} /></button>}
        </span>
      </div>
      {i.description && <p className="text-xs text-slate-500 mt-1">{i.description}</p>}
      <div className="flex flex-wrap items-center gap-2 mt-1.5">
        {canReview && i.status === "pending" && <ReviewBtns onReview={(a, n) => onReviewItem(i.id, a, n)} testid={`ai-detail-item-${i.id}`} />}
        {canComment && <button className="text-xs text-violet-600 inline-flex items-center gap-1" onClick={() => setShowC(!showC)} data-testid={`ai-item-comment-toggle-${i.id}`}><MessageSquare size={12} /> Comment</button>}
        {canPreview && <button className="text-xs text-indigo-600 inline-flex items-center gap-1" onClick={() => setPreview(true)} data-testid={`ai-item-preview-${i.id}`}><Eye size={12} /> View</button>}
        {canSubmitLib && approved && i.source !== "lnmo_library" && !["chapter", "topic"].includes(i.item_type) && (
          <button className="text-xs text-indigo-600 inline-flex items-center gap-1" onClick={() => onSubmitLib(i)} data-testid={`ai-item-submit-lib-${i.id}`}><Library size={12} /> Submit to LNMO Library</button>
        )}
        {canMove && !["chapter", "topic"].includes(i.item_type) && chapterOptions.length > 1 && (
          <select className="text-xs rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1 py-0.5" value={i.chapter || ""} onChange={(e) => onMove(i.id, e.target.value)} data-testid={`ai-item-move-${i.id}`} title="Move to chapter">
            {chapterOptions.map((ch) => <option key={ch} value={ch}>{`→ ${ch}`}</option>)}
          </select>
        )}
      </div>
      {showC && (
        <div className="mt-2 flex gap-2">
          <Textarea className="text-sm" rows={2} placeholder="Leave a review comment on this item…" value={txt} onChange={(e) => setTxt(e.target.value)} data-testid={`ai-item-comment-input-${i.id}`} />
          <Button size="sm" onClick={async () => { if (!txt.trim()) return; await onCommentItem(i.id, txt.trim()); setTxt(""); setShowC(false); }} data-testid={`ai-item-comment-send-${i.id}`}><Send size={14} /></Button>
        </div>
      )}
      {preview && <LibraryPreview libraryId={i.library_id || undefined} itemId={i.library_id ? undefined : i.id} fallbackTitle={i.title || i.topic || i.item_type} onClose={() => setPreview(false)} />}
    </li>
  );
}

export default function CurriculumDetail({ cid, onClose, onChanged, asPage = false }) {
  const [data, setData] = useState(null);
  const [newComment, setNewComment] = useState("");
  const [candidates, setCandidates] = useState([]);
  const [mentions, setMentions] = useState([]);   // selected teacher ids

  const load = useCallback(() => {
    api.get(`/ai/curriculum/${cid}`).then((r) => setData(r.data)).catch((e) => toast.error(errText(e)));
  }, [cid]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get(`/ai/curriculum/${cid}/mention-candidates`).then((r) => setCandidates(r.data.candidates || [])).catch(() => {}); }, [cid]);

  const refresh = () => { load(); onChanged && onChanged(); };

  const reviewCurriculum = async (action, note = "") => {
    try { await api.post(`/ai/curriculum/${cid}/review`, { action, note }); toast.success(`Curriculum ${action === "approve" ? "published" : action}`); refresh(); }
    catch (e) { toast.error(errText(e)); }
  };
  const reviewItem = async (id, action, note = "") => {
    try { await api.post(`/ai/items/${id}/review`, { action, note }); toast.success(`Material ${action}d`); refresh(); }
    catch (e) { toast.error(errText(e)); }
  };
  const addComment = async (text, itemId = null, mentionIds = []) => {
    try { await api.post(`/ai/curriculum/${cid}/comments`, { text, item_id: itemId, mentions: mentionIds }); toast.success(mentionIds.length ? "Comment added — contributor & mentions notified" : "Comment added — the contributor was notified"); refresh(); }
    catch (e) { toast.error(errText(e)); }
  };
  const resolveComment = async (id) => {
    const reply = window.prompt("Add an optional reply, then resolve:") || "";
    try { await api.post(`/ai/comments/${id}/resolve`, { reply }); toast.success("Comment resolved"); refresh(); }
    catch (e) { toast.error(errText(e)); }
  };
  const toggleAI = async (enabled) => {
    try { await api.put(`/ai/curriculum/${cid}/ai-enabled`, { enabled }); toast.success(`AI Tutor ${enabled ? "enabled" : "disabled"}`); refresh(); }
    catch (e) { toast.error(errText(e)); }
  };
  const deleteItem = async (it) => {
    const kids = it.item_type === "chapter"
      ? items.filter((x) => x.chapter === it.chapter && x.id !== it.id && x.status !== "deleted").length : 0;
    const label = it.title || it.topic || it.chapter || it.item_type;
    const msg = `Delete "${label}"?${kids ? ` This also removes ${kids} item(s) under this chapter.` : ""}\n\nThis removes it from the student knowledge base.`;
    if (!window.confirm(msg)) return;
    try { await api.delete(`/ai/items/${it.id}`); toast.success("Removed from the knowledge base"); refresh(); }
    catch (e) { toast.error(errText(e)); }
  };
  const deleteCurriculum = async () => {
    const hard = !!data?.is_admin;
    const warn = hard
      ? `Permanently deletes the curriculum and all its materials — this cannot be undone.`
      : `Removes the curriculum from the knowledge base (retained internally for records).`;
    if (!window.confirm(`Delete "${c.name}"?\n\n${warn}`)) return;
    const typed = window.prompt(`${hard ? "FINAL STEP — " : ""}Type the curriculum name to confirm:\n\n${c.name}`);
    if (typed === null) return;
    try { await api.delete(`/ai/curriculum/${cid}`, { data: { confirm_name: typed } }); toast.success(hard ? "Curriculum permanently deleted" : "Curriculum deleted"); onClose(); onChanged && onChanged(); }
    catch (e) { toast.error(errText(e)); }
  };

  const c = data?.curriculum;
  const items = data?.items || [];
  const comments = data?.comments || [];
  const canReview = !!data?.can_review;
  const canComment = !!data?.can_comment;
  const canSubmitLib = !!data?.can_contribute;

  const submitLib = async (it) => {
    if (!window.confirm(`Submit "${it.title || it.topic || it.item_type}" to the LNMO Central Library?\n\nA platform admin will review it before it's published for all schools.`)) return;
    try { await api.post(`/ai/curriculum/${cid}/submit-to-library`, { item_id: it.id }); toast.success("Submitted to LNMO Library — awaiting platform approval"); }
    catch (e) { toast.error(errText(e)); }
  };
  const canEdit = canReview || canSubmitLib;
  const reorderChapters = async (newOrder) => {
    try { await api.post(`/ai/curriculum/${cid}/chapters/reorder`, { chapters: newOrder }); refresh(); }
    catch (e) { toast.error(errText(e)); }
  };
  const moveMaterial = async (id, chapter) => {
    try { await api.post(`/ai/items/${id}/move`, { chapter }); toast.success(`Moved to ${chapter}`); refresh(); }
    catch (e) { toast.error(errText(e)); }
  };
  const canDeleteDraft = canSubmitLib && !canReview && ["draft", "changes_requested"].includes(c?.status);
  const deleteDraft = async () => {
    if (!window.confirm("Delete this draft? This cannot be undone.")) return;
    try { await api.delete(`/ai/curriculum/${cid}`); toast.success("Draft deleted"); onClose(); onChanged && onChanged(); }
    catch (e) { toast.error(errText(e)); }
  };

  const chapterNames = [...new Set([
    ...items.filter((i) => i.item_type === "chapter").map((i) => i.chapter),
    ...items.filter((i) => i.chapter).map((i) => i.chapter),
  ].filter(Boolean))];
  const ungrouped = items.filter((i) => !i.chapter && i.item_type !== "chapter");

  return (
    <div className={asPage ? "" : "fixed inset-0 z-50 flex items-stretch justify-end bg-black/50 backdrop-blur-sm"} data-testid={asPage ? "ai-curriculum-detail-page" : "ai-curriculum-detail"}>
      <div className={asPage ? "w-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800" : "w-full max-w-3xl bg-white dark:bg-slate-900 border-l-2 border-slate-200 dark:border-slate-800 shadow-2xl overflow-y-auto"}>
        {!data ? (
          <div className="p-10 text-center text-slate-400"><Loader2 className="animate-spin mx-auto" /></div>
        ) : (
          <div className="p-6 space-y-5">
            <div className="flex items-start justify-between gap-3 sticky top-0 bg-white dark:bg-slate-900 pb-3 z-10">
              <div>
                <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2"><BookOpen size={20} className="text-violet-500" /> {c.name}</h2>
                <p className="text-xs text-slate-400 mt-0.5">{c.class_name} · {c.subject} · {c.academic_year} · by {c.created_by_name}</p>
              </div>
              <div className="flex items-center gap-2">
                <StatusChip s={c.status} />
                {c.ai_enabled && <span className="text-[10px] font-bold uppercase rounded-full px-2 py-0.5 bg-violet-100 text-violet-700">AI ON</span>}
                <button onClick={onClose} className="text-slate-400 hover:text-slate-600" data-testid="ai-detail-close"><X size={18} /></button>
              </div>
            </div>

            {c.syllabus_text && (
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
                <p className="text-xs font-semibold uppercase text-slate-400 mb-1">Syllabus</p>
                <p className="text-sm text-slate-600 dark:text-slate-300 whitespace-pre-line">{c.syllabus_text}</p>
              </div>
            )}
            {c.review_note && <p className="text-xs text-orange-600">Reviewer note: {c.review_note}</p>}

            {canReview && (
              <div className="flex flex-wrap items-center gap-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 p-3">
                {c.status === "pending" && <ReviewBtns onReview={reviewCurriculum} testid="ai-detail-cur" />}
                {c.status === "published" && (
                  <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">AI Tutor
                    <input type="checkbox" checked={!!c.ai_enabled} onChange={(e) => toggleAI(e.target.checked)} data-testid="ai-detail-enable" />
                  </label>
                )}
                <Button size="sm" variant="outline" className="ml-auto text-rose-600 border-rose-200" onClick={deleteCurriculum} data-testid="ai-detail-delete-curriculum"><Trash2 size={14} className="mr-1" /> Delete curriculum</Button>
              </div>
            )}

            {canDeleteDraft && (
              <div className="flex" data-testid="ai-detail-draft-actions">
                <Button size="sm" variant="outline" className="text-rose-600 border-rose-200" onClick={deleteDraft} data-testid="ai-detail-delete-draft"><Trash2 size={14} className="mr-1" /> Delete draft</Button>
              </div>
            )}

            <div>
              <h3 className="font-heading font-semibold text-slate-800 dark:text-slate-100 mb-2">Curriculum structure</h3>
              {items.length === 0 && <p className="text-sm text-slate-400">No materials yet.</p>}
              {chapterNames.map((ch, ci) => {
                const chItem = items.find((i) => i.item_type === "chapter" && i.chapter === ch);
                const topics = items.filter((i) => i.item_type === "topic" && i.chapter === ch);
                const mats = items.filter((i) => i.chapter === ch && !["chapter", "topic"].includes(i.item_type));
                return (
                  <div key={ch} className="mb-4 rounded-xl border border-slate-200 dark:border-slate-800 p-3" data-testid={`ai-detail-chapter-${ch}`}>
                    <div className="flex items-center gap-2">
                      {canEdit && chapterNames.length > 1 && (
                        <span className="flex flex-col -my-1" data-testid={`ai-chapter-reorder-${ci}`}>
                          <button disabled={ci === 0} onClick={() => { const n = [...chapterNames]; [n[ci], n[ci - 1]] = [n[ci - 1], n[ci]]; reorderChapters(n); }} className="text-slate-400 hover:text-slate-700 disabled:opacity-30" data-testid={`ai-detail-chapter-up-${ci}`}><ChevronUp size={13} /></button>
                          <button disabled={ci === chapterNames.length - 1} onClick={() => { const n = [...chapterNames]; [n[ci], n[ci + 1]] = [n[ci + 1], n[ci]]; reorderChapters(n); }} className="text-slate-400 hover:text-slate-700 disabled:opacity-30" data-testid={`ai-detail-chapter-down-${ci}`}><ChevronDown size={13} /></button>
                        </span>
                      )}
                      <p className="text-sm font-semibold text-violet-700 dark:text-violet-300">{ch}</p>
                      {chItem && <StatusChip s={chItem.status} />}
                      {chItem && canReview && chItem.status === "pending" && <span className="ml-auto"><ReviewBtns onReview={(a, n) => reviewItem(chItem.id, a, n)} testid={`ai-detail-chapter-${chItem.id}`} /></span>}
                      {chItem && canReview && <button onClick={() => deleteItem(chItem)} className={`${chItem.status === "pending" ? "" : "ml-auto"} text-rose-400 hover:text-rose-600`} data-testid={`ai-chapter-delete-${chItem.id}`} title="Delete chapter"><Trash2 size={14} /></button>}
                    </div>
                    <ul className="mt-1">
                      {topics.map((t) => <ItemRow key={t.id} i={t} canReview={canReview} canComment={canComment} canSubmitLib={canSubmitLib} onReviewItem={reviewItem} onCommentItem={(id, txt) => addComment(txt, id)} onDeleteItem={deleteItem} onSubmitLib={submitLib} />)}
                      {mats.map((m) => <ItemRow key={m.id} i={m} canReview={canReview} canComment={canComment} canSubmitLib={canSubmitLib} canMove={canEdit} chapterOptions={chapterNames} onReviewItem={reviewItem} onCommentItem={(id, txt) => addComment(txt, id)} onDeleteItem={deleteItem} onSubmitLib={submitLib} onMove={moveMaterial} />)}
                    </ul>
                  </div>
                );
              })}
              {ungrouped.length > 0 && (
                <ul className="rounded-xl border border-slate-200 dark:border-slate-800 p-3">
                  {ungrouped.map((m) => <ItemRow key={m.id} i={m} canReview={canReview} canComment={canComment} canSubmitLib={canSubmitLib} onReviewItem={reviewItem} onCommentItem={(id, txt) => addComment(txt, id)} onDeleteItem={deleteItem} onSubmitLib={submitLib} />)}
                </ul>
              )}
            </div>

            <div data-testid="ai-detail-comments">
              <h3 className="font-heading font-semibold text-slate-800 dark:text-slate-100 mb-2 flex items-center gap-2"><MessageSquare size={16} /> Review comments {data.open_comment_count > 0 && <span className="text-[10px] font-bold rounded-full px-2 py-0.5 bg-amber-100 text-amber-700">{data.open_comment_count} open</span>}</h3>
              {comments.length === 0 && <p className="text-sm text-slate-400">No comments yet.</p>}
              <ul className="space-y-2">
                {comments.map((cm) => {
                  const canResolve = cm.status === "open";
                  return (
                    <li key={cm.id} className={`rounded-xl border p-3 ${cm.status === "open" ? "border-amber-200 bg-amber-50/50 dark:border-amber-900 dark:bg-amber-950/20" : "border-slate-200 dark:border-slate-800"}`} data-testid={`ai-comment-${cm.id}`}>
                      <div className="flex items-center gap-2 text-xs">
                        <span className="font-semibold text-slate-700 dark:text-slate-200">{cm.author_name}</span>
                        <span className="text-slate-400">({cm.author_role})</span>
                        {cm.item_id && <span className="text-slate-400">· on a material</span>}
                        <span className="ml-auto"><StatusChip s={cm.status === "open" ? "pending" : "approved"} /></span>
                      </div>
                      <p className="text-sm text-slate-700 dark:text-slate-200 mt-1">{cm.text}</p>
                      {cm.mention_names?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1" data-testid={`ai-comment-mentions-${cm.id}`}>
                          {cm.mention_names.map((n, i) => <span key={i} className="text-[10px] font-semibold rounded-full px-2 py-0.5 bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300">@{n}</span>)}
                        </div>
                      )}
                      {cm.reply && <p className="text-xs text-emerald-700 dark:text-emerald-300 mt-1">↳ Reply: {cm.reply}</p>}
                      {cm.status === "resolved" && <p className="text-[11px] text-slate-400 mt-1">Resolved by {cm.resolved_by_name} · {fmtDate(cm.resolved_at)}</p>}
                      {cm.status === "open" && canResolve && (
                        <Button size="sm" variant="outline" className="mt-2" onClick={() => resolveComment(cm.id)} data-testid={`ai-comment-resolve-${cm.id}`}><CheckCircle2 size={13} className="mr-1" /> Resolve</Button>
                      )}
                    </li>
                  );
                })}
              </ul>
              {canComment && (
                <div className="mt-3 space-y-2">
                  {candidates.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5" data-testid="ai-mention-picker">
                      <span className="text-xs text-slate-400">Mention:</span>
                      {candidates.map((p) => {
                        const on = mentions.includes(p.id);
                        return (
                          <button key={p.id} onClick={() => setMentions((m) => on ? m.filter((x) => x !== p.id) : [...m, p.id])} data-testid={`ai-mention-${p.id}`}
                            className={`text-[11px] rounded-full px-2 py-0.5 border transition-colors ${on ? "bg-violet-600 text-white border-violet-600" : "border-slate-300 dark:border-slate-700 text-slate-500 hover:border-violet-400"}`}>@{p.name}</button>
                        );
                      })}
                    </div>
                  )}
                  <div className="flex gap-2">
                    <Textarea rows={2} placeholder="Leave a review comment for the contributing teacher…" value={newComment} onChange={(e) => setNewComment(e.target.value)} data-testid="ai-comment-input" />
                    <Button onClick={async () => { if (!newComment.trim()) return; await addComment(newComment.trim(), null, mentions); setNewComment(""); setMentions([]); }} data-testid="ai-comment-send"><Send size={16} /></Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
