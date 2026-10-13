import { useCallback, useEffect, useState } from "react";
import api from "../lib/api";
import { DataTable, Pagination } from "../components/common/DataTable";

const actionPill = (row) => {
  const map = {
    create: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
    update: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
    delete: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400",
    login: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-400",
  };
  return <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${map[row.action] || map.login}`}>{row.action}</span>;
};

const columns = [
  { key: "timestamp", label: "When", render: (r) => new Date(r.timestamp).toLocaleString() },
  { key: "actor_email", label: "Actor" },
  { key: "action", label: "Action", render: actionPill },
  { key: "resource", label: "Resource" },
  { key: "entity_name", label: "Entity" },
];

export default function AuditPage() {
  const [data, setData] = useState({ items: [], total: 0, page: 1, pages: 1 });
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/audit", { params: { page, limit: 25 } });
      setData(data);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6" data-testid="audit-page">
      <div>
        <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">Audit log</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Chronological record of actions performed in this scope.</p>
      </div>
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
        <DataTable columns={columns} rows={data.items} loading={loading} testId="audit-table" />
        {data.items.length > 0 && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </div>
    </div>
  );
}
