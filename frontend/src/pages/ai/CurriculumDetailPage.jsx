import { useParams, useNavigate, useLocation } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import CurriculumDetail from "./CurriculumDetail";

export default function CurriculumDetailPage() {
  const { cid } = useParams();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const listPath = pathname.startsWith("/app") ? "/app/ai-tutor" : "/teacher/ai-tutor";
  const back = () => (window.history.length > 1 ? navigate(-1) : navigate(listPath));
  return (
    <div className="space-y-4" data-testid="ai-curriculum-detail-page-wrap">
      <button onClick={back} className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 dark:hover:text-slate-200" data-testid="ai-detail-back">
        <ArrowLeft size={15} /> Back
      </button>
      <CurriculumDetail cid={cid} asPage onClose={back} onChanged={() => {}} />
    </div>
  );
}
