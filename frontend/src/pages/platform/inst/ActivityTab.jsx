import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { Card, Empty, SkeletonGrid, fmtDate } from "./ui";

export default function ActivityTab({ iid }) {
  const [items, setItems] = useState(null);
  const [platformOnly, setPlatformOnly] = useState(true);
  useEffect(() => {
    setItems(null);
    api.get(`/platform/institutions/${iid}/activity`, { params: { platform_only: platformOnly, limit: 60 } })
      .then((r) => setItems(r.data.items)).catch((e) => toast.error(errText(e)));
  }, [iid, platformOnly]);
  return (
    <Card title="Recent activity" testid="inst-activity-tab"
      action={<label className="flex items-center gap-2 text-xs text-slate-500 cursor-pointer"><input type="checkbox" checked={platformOnly} onChange={(e) => setPlatformOnly(e.target.checked)} data-testid="activity-platform-only" /> Platform actions only</label>}>
      {!items ? <SkeletonGrid n={2} /> : !items.length ? <Empty testid="activity-empty">No activity recorded yet.</Empty> : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800" data-testid="activity-list">
          {items.map((a) => (
            <li key={a.id} className="py-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
              <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">{a.action}</span>
              <span className="text-slate-700 dark:text-slate-200 flex-1 min-w-[12rem] break-words">{a.entity_name || a.resource}</span>
              <span className="text-slate-500">{a.actor_email}</span>
              <span className="text-slate-400 tabular-nums">{fmtDate(a.timestamp)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
