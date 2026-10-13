import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, CheckCircle2, XCircle, AlertTriangle, FileText, Loader2, BookOpen, ChevronRight, Eye, MessageSquare, Lock } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Switch } from "../../components/ui/switch";
import { StatusChip } from "./AITutorTeacher";
import CurriculumDetail from "./CurriculumDetail";

const API = process.env.REACT_APP_BACKEND_URL;
const TABS = [{ k: "curricula", l: "Pending curricula" }, { k: "items", l: "Pending contributions" }, { k: "browse", l: "Curricula browser" }];

export default function AITutorAdmin() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("curricula");
  const [detailCid, setDetailCid] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [layerOff, setLayerOff] = useState(false);
  useEffect(() => { api.get("/ai/layer-status").then((r) => setLayerOff(r.data.ai_layer_enabled === false)).catch(() => {}); }, []);
  const openDetail = (cid) => navigate(`/app/ai-tutor/curriculum/${cid}`);
  return (
    <div className="space-y-6" data-testid="ai-tutor-admin">
      <div>
        <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Sparkles className="text-violet-600" size={24} /> AI Tutor</h1>
        <p className="text-sm text-slate-500 mt-1">Approve curricula & contributions, then enable the AI Tutor per published curriculum.</p>
      </div>
      {layerOff && (
        <div className="rounded-xl border-2 border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 p-4 flex items-center gap-3" data-testid="ai-layer-disabled-banner">
          <Lock className="text-amber-600 shrink-0" size={18} />
          <p className="text-sm text-amber-800 dark:text-amber-200">The AI Tutor is <b>Disabled by LNMO Platform</b> for your school. Curricula can be managed, but students can't use the tutor until the platform enables the AI Layer.</p>
        </div>
      )}
      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-800">
        {TABS.map((t) => (
          <button key={t.k} onClick={() => setTab(t.k)} data-testid={`ai-tab-${t.k}`}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${tab === t.k ? "border-violet-600 text-violet-700 dark:text-violet-300" : "border-transparent text-slate-500 hover:text-slate-700"}`}>{t.l}</button>
        ))}
      </div>
      {tab === "curricula" && <PendingCurricula key={`c${reloadKey}`} openDetail={openDetail} />}
      {tab === "items" && <PendingItems key={`i${reloadKey}`} openDetail={openDetail} />}
      {tab === "browse" && <Browser key={`b${reloadKey}`} openDetail={openDetail} />}
      {detailCid && <CurriculumDetail cid={detailCid} onClose={() => setDetailCid(null)} onChanged={() => setReloadKey((k) => k + 1)} />}
    </div>
  );
}

function ReviewButtons({ onReview, testid }) {
  return (
    <div className="flex gap-2">
      <Button size="sm" onClick={() => onReview("approve")} data-testid={`${testid}-approve`} className="bg-emerald-600 hover:bg-emerald-700 text-white"><CheckCircle2 size={14} className="mr-1" /> Approve</Button>
      <Button size="sm" variant="outline" onClick={() => { const n = window.prompt("What changes are needed?"); if (n !== null) onReview("changes", n); }} data-testid={`${testid}-changes`}><AlertTriangle size={14} className="mr-1" /> Changes</Button>
      <Button size="sm" variant="outline" onClick={() => onReview("reject")} data-testid={`${testid}-reject`} className="text-rose-600"><XCircle size={14} className="mr-1" /> Reject</Button>
    </div>
  );
}

function PendingCurricula({ openDetail }) {
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(null);
  const load = useCallback(() => api.get("/ai/approvals/curricula").then((r) => setRows(r.data.curricula)).catch((e) => toast.error(errText(e))), []);
  useEffect(() => { load(); }, [load]);

  const review = async (cid, action, note = "") => {
    try { await api.post(`/ai/curriculum/${cid}/review`, { action, note }); toast.success(`Curriculum ${action === "approve" ? "published" : action}`); setOpen(null); load(); }
    catch (e) { toast.error(errText(e)); }
  };

  if (rows === null) return <p className="text-sm text-slate-400">Loading…</p>;
  if (!rows.length) return <Empty text="No curricula awaiting approval." />;
  return (
    <div className="space-y-3">
      {rows.map((c) => (
        <div key={c.id} className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid={`ai-pending-cur-${c.id}`}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="font-heading font-semibold text-slate-900 dark:text-slate-50">{c.name}</h3>
              <p className="text-xs text-slate-400">{c.class_name} · {c.subject} · {c.academic_year} · by {c.created_by_name}</p>
            </div>
            <div className="flex items-center gap-2">
              {c.open_comment_count > 0 && <span className="text-[10px] font-bold rounded-full px-2 py-0.5 bg-amber-100 text-amber-700 inline-flex items-center gap-1" data-testid={`ai-pending-cur-comments-${c.id}`}><MessageSquare size={10} /> {c.open_comment_count}</span>}
              <StatusChip s={c.status} />
            </div>
          </div>
          {c.syllabus_text && <p className="text-sm text-slate-500 mt-2 whitespace-pre-line line-clamp-3">{c.syllabus_text}</p>}
          <div className="flex items-center justify-between mt-4">
            <div className="flex items-center gap-3">
              <button className="text-sm text-violet-600 inline-flex items-center gap-1" onClick={() => setOpen(open === c.id ? null : c.id)} data-testid={`ai-pending-cur-view-${c.id}`}>Quick view <ChevronRight size={14} className={open === c.id ? "rotate-90 transition-transform" : "transition-transform"} /></button>
              <button className="text-sm text-indigo-600 inline-flex items-center gap-1" onClick={() => openDetail(c.id)} data-testid={`ai-pending-cur-detail-${c.id}`}><Eye size={14} /> Full detail</button>
            </div>
            <ReviewButtons onReview={(a, n) => review(c.id, a, n)} testid={`ai-cur-${c.id}`} />
          </div>
          {open === c.id && <CurriculumItems cid={c.id} />}
        </div>
      ))}
    </div>
  );
}

function CurriculumItems({ cid }) {
  const [items, setItems] = useState(null);
  useEffect(() => { api.get(`/ai/curriculum/${cid}`).then((r) => setItems(r.data.items)).catch(() => setItems([])); }, [cid]);
  if (!items) return <p className="text-xs text-slate-400 mt-3">Loading…</p>;
  return (
    <ul className="mt-3 border-t border-slate-100 dark:border-slate-800 pt-3 space-y-1.5" data-testid={`ai-cur-items-${cid}`}>
      {items.map((i) => (
        <li key={i.id} className="flex items-center gap-2 text-sm">
          <span className="text-[10px] uppercase font-bold text-slate-400 w-24">{i.item_type.replace("_", " ")}</span>
          <span className="text-slate-700 dark:text-slate-200">{i.title || i.topic || i.chapter}</span>
          {i.has_file && <a href={`${API}/api/ai/items/${i.id}/file`} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline inline-flex items-center gap-0.5"><FileText size={12} /> file</a>}
          <span className="ml-auto text-xs text-slate-400">{i.contributor_name}</span>
          <StatusChip s={i.status} />
        </li>
      ))}
    </ul>
  );
}

function PendingItems({ openDetail }) {
  const [groups, setGroups] = useState(null);
  const load = useCallback(() => api.get("/ai/approvals/items").then((r) => setGroups(r.data.groups)).catch((e) => toast.error(errText(e))), []);
  useEffect(() => { load(); }, [load]);
  const review = async (id, action) => {
    try { await api.post(`/ai/items/${id}/review`, { action }); toast.success(`Material ${action}d`); load(); }
    catch (e) { toast.error(errText(e)); }
  };
  if (groups === null) return <p className="text-sm text-slate-400">Loading…</p>;
  if (!groups.length) return <Empty text="No contributions awaiting approval." />;
  return (
    <div className="space-y-4">
      {groups.map((g) => (
        <div key={g.curriculum.id} className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid={`ai-item-group-${g.curriculum.id}`}>
          <p className="font-heading font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2">{g.curriculum.name} <span className="text-xs text-slate-400">· {g.curriculum.class_name} {g.curriculum.subject}</span>
            <button className="ml-auto text-sm text-indigo-600 inline-flex items-center gap-1" onClick={() => openDetail(g.curriculum.id)} data-testid={`ai-item-group-detail-${g.curriculum.id}`}><Eye size={14} /> Full detail</button>
          </p>
          <ul className="mt-3 space-y-2">
            {g.items.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-2 text-sm border-t border-slate-100 dark:border-slate-800 pt-2" data-testid={`ai-pending-item-${i.id}`}>
                <span className="text-[10px] uppercase font-bold text-slate-400">{i.item_type.replace("_", " ")}</span>
                <span className="text-slate-700 dark:text-slate-200">{i.title || i.topic}</span>
                {i.chapter && <span className="text-xs text-slate-400">· {i.chapter}</span>}
                {i.has_file && <a href={`${API}/api/ai/items/${i.id}/file`} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline inline-flex items-center gap-0.5"><FileText size={12} /> file</a>}
                {i.version > 1 && <span className="text-[10px] text-slate-400">replaces v{i.version - 1}</span>}
                <span className="text-xs text-slate-400">by {i.contributor_name}</span>
                <div className="ml-auto flex gap-1.5">
                  <Button size="sm" onClick={() => review(i.id, "approve")} data-testid={`ai-item-approve-${i.id}`} className="bg-emerald-600 hover:bg-emerald-700 text-white">Approve</Button>
                  <Button size="sm" variant="outline" className="text-rose-600" onClick={() => review(i.id, "reject")} data-testid={`ai-item-reject-${i.id}`}>Reject</Button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function Browser({ openDetail }) {
  const [curs, setCurs] = useState(null);
  const [openId, setOpenId] = useState(null);
  const load = useCallback(() => api.get("/ai/curricula").then((r) => setCurs(r.data.curricula)).catch((e) => toast.error(errText(e))), []);
  useEffect(() => { load(); }, [load]);
  const toggle = async (c, enabled) => {
    try { await api.put(`/ai/curriculum/${c.id}/ai-enabled`, { enabled }); toast.success(`AI Tutor ${enabled ? "enabled" : "disabled"} for ${c.class_name} ${c.subject}`); load(); }
    catch (e) { toast.error(errText(e)); }
  };
  if (curs === null) return <p className="text-sm text-slate-400">Loading…</p>;
  if (!curs.length) return <Empty text="No curricula yet." />;
  return (
    <div className="space-y-3">
      {curs.map((c) => (
        <div key={c.id} className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid={`ai-browse-${c.id}`}>
          <div className="flex items-center justify-between gap-3">
            <button className="flex items-center gap-2 text-left" onClick={() => setOpenId(openId === c.id ? null : c.id)}>
              <BookOpen size={18} className="text-violet-500" />
              <div>
                <p className="font-heading font-semibold text-slate-900 dark:text-slate-50">{c.class_name} · {c.subject}</p>
                <p className="text-xs text-slate-400">{c.name} · {c.academic_year}</p>
              </div>
            </button>
            <div className="flex items-center gap-3">
              <StatusChip s={c.status} />
              <button className="text-sm text-indigo-600 inline-flex items-center gap-1" onClick={() => openDetail(c.id)} data-testid={`ai-browse-detail-${c.id}`}><Eye size={14} /> Detail</button>
              {c.status === "published" && (
                <label className="flex items-center gap-2 text-xs text-slate-500">AI Tutor
                  <Switch checked={!!c.ai_enabled} onCheckedChange={(v) => toggle(c, v)} data-testid={`ai-enable-${c.id}`} />
                </label>
              )}
            </div>
          </div>
          {openId === c.id && <CurriculumItems cid={c.id} />}
        </div>
      ))}
    </div>
  );
}

const Empty = ({ text }) => <div className="rounded-2xl border border-dashed border-slate-300 dark:border-slate-700 p-10 text-center text-slate-400">{text}</div>;
