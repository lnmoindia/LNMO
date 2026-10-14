import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api, { errText } from "../../lib/api";
import { BulkResultView, summaryText } from "../../components/bulk/BulkResultDialog";

export default function BulkRunPage() {
  const { id } = useParams();
  const [run, setRun] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { api.get(`/bulk-runs/${id}`).then((r) => setRun(r.data)).catch((e) => setErr(errText(e))); }, [id]);
  if (err) return <p className="py-16 text-center text-slate-400" data-testid="bulk-run-error">{err}</p>;
  if (!run) return <p className="py-16 text-center text-sm text-slate-400">Loading…</p>;
  return (
    <div className="space-y-4" data-testid="bulk-run-page">
      <div>
        <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50">{run.title}</h1>
        <p className="text-sm text-slate-500 mt-1">{summaryText(run.summary)} · by {run.actor_name} · {new Date(run.created_at).toLocaleString("en-IN")}</p>
      </div>
      <BulkResultView run={run} />
    </div>
  );
}
