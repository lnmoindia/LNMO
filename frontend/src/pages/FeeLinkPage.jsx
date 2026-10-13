import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import api, { errText } from "../lib/api";

// Reminder link → remembers which child to open, then the parent portal (sign-in required) opens its fee card.
export default function FeeLinkPage() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get(`/public/fee-link/${token}`).then(({ data }) => {
      sessionStorage.setItem("fee_link_child", data.student_id);
      navigate(`/parents?child=${data.student_id}&fees=1`, { replace: true });
    }).catch((e) => setErr(errText(e)));
  }, [token, navigate]);
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4" data-testid="fee-link-page">
      {err ? <p className="text-sm text-rose-600" data-testid="fee-link-error">{err}</p> : <Loader2 className="animate-spin text-slate-400" />}
    </div>
  );
}
