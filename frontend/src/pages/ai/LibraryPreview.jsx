import { useEffect, useState } from "react";
import { X, Loader2, FileText, ExternalLink } from "lucide-react";
import api from "../../lib/api";

const API = process.env.REACT_APP_BACKEND_URL;

/**
 * In-app preview for an LNMO Library item.
 * Pass EITHER libraryId (browse-before-attach) OR itemId (an imported curriculum item).
 * PDFs embed via <iframe>; everything else shows the extracted text (readable for big files).
 */
export function LibraryPreview({ libraryId, itemId, fallbackTitle = "Preview", onClose }) {
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Always fetch library detail (for title + mime + extracted text). When only itemId is known,
    // the caller still passes the library_id, so libraryId is required for text/metadata.
    if (!libraryId) { setLoading(false); return; }
    setLoading(true);
    api.get(`/ai/central-library/${libraryId}`)
      .then((r) => setMeta(r.data))
      .catch(() => setMeta(null))
      .finally(() => setLoading(false));
  }, [libraryId]);

  const mime = meta?.mime || "";
  const isPdf = mime.includes("pdf") || (meta?.file_name || "").toLowerCase().endsWith(".pdf");
  const fileUrl = itemId
    ? `${API}/api/ai/items/${itemId}/file`
    : (libraryId ? `${API}/api/ai/central-library/${libraryId}/file` : null);
  const title = meta?.title || fallbackTitle;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" data-testid="ai-library-preview" onClick={onClose}>
      <div className="w-full max-w-4xl h-[85vh] bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100 dark:border-slate-800">
          <FileText size={16} className="text-indigo-600 shrink-0" />
          <p className="font-heading font-semibold text-slate-800 dark:text-slate-100 truncate flex-1" data-testid="ai-preview-title">{title}</p>
          {fileUrl && <a href={fileUrl} target="_blank" rel="noreferrer" className="text-xs text-indigo-600 inline-flex items-center gap-1" data-testid="ai-preview-open-tab"><ExternalLink size={13} /> Open</a>}
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" data-testid="ai-preview-close"><X size={18} /></button>
        </div>
        <div className="flex-1 overflow-hidden p-0">
          {loading ? (
            <div className="h-full flex items-center justify-center text-slate-400"><Loader2 className="animate-spin" /></div>
          ) : isPdf && fileUrl ? (
            <iframe title="preview" src={fileUrl} className="w-full h-full" data-testid="ai-preview-iframe" />
          ) : meta?.extracted_text ? (
            <pre className="w-full h-full overflow-auto whitespace-pre-wrap p-5 text-sm text-slate-700 dark:text-slate-200 font-sans" data-testid="ai-preview-text">{meta.extracted_text}</pre>
          ) : (
            <div className="h-full flex flex-col items-center justify-center gap-2 text-slate-400 p-6 text-center" data-testid="ai-preview-empty">
              <FileText size={28} />
              <p className="text-sm">No readable preview for this file type yet.</p>
              {fileUrl && <a href={fileUrl} target="_blank" rel="noreferrer" className="text-indigo-600 text-sm inline-flex items-center gap-1"><ExternalLink size={14} /> Open the file in a new tab</a>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
