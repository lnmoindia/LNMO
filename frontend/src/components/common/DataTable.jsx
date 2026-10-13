import { Pencil, Trash2, ChevronLeft, ChevronRight, Inbox } from "lucide-react";
import { Button } from "../ui/button";
import { Skeleton } from "../ui/skeleton";

export const DataTable = ({ columns, rows, loading, onEdit, onDelete, rowActions, testId = "data-table" }) => {
  if (loading) {
    return (
      <div className="space-y-2 p-4">
        {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
      </div>
    );
  }
  if (!rows.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center" data-testid={`${testId}-empty`}>
        <Inbox className="text-slate-300 dark:text-slate-600 mb-3" size={36} strokeWidth={1.2} />
        <p className="text-sm font-medium text-slate-600 dark:text-slate-300">No records yet</p>
        <p className="text-xs text-slate-400 mt-1">Create your first record to get started.</p>
      </div>
    );
  }
  return (
    <div className="overflow-x-auto" data-testid={testId}>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800">
            {columns.map((c) => (
              <th key={c.key} className="text-left px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 whitespace-nowrap">
                {c.label}
              </th>
            ))}
            {(onEdit || onDelete || rowActions) && <th className="px-4 py-3 w-20" />}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-slate-100 dark:border-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors" data-testid={`row-${row.id}`}>
              {columns.map((c) => (
                <td key={c.key} className="px-4 py-3 text-slate-700 dark:text-slate-300 whitespace-nowrap">
                  {c.render ? c.render(row) : (row[c.key] ?? <span className="text-slate-300 dark:text-slate-600">—</span>)}
                </td>
              ))}
              {(onEdit || onDelete || rowActions) && (
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1 justify-end">
                    {rowActions?.filter((a) => !a.show || a.show(row)).map((a) => (
                      <button key={a.title} title={a.title} onClick={() => a.onClick(row)} data-testid={`${a.testId}-${row.id}`} className="h-7 w-7 rounded flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-slate-800 transition-colors">
                        <a.icon size={14} />
                      </button>
                    ))}
                    {onEdit && (
                      <button onClick={() => onEdit(row)} data-testid={`edit-btn-${row.id}`} className="h-7 w-7 rounded flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-slate-800 transition-colors">
                        <Pencil size={14} />
                      </button>
                    )}
                    {onDelete && (
                      <button onClick={() => onDelete(row)} data-testid={`delete-btn-${row.id}`} className="h-7 w-7 rounded flex items-center justify-center text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-slate-800 transition-colors">
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export const Pagination = ({ page, pages, total, onPage }) => (
  <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 dark:border-slate-800">
    <p className="text-xs text-slate-500" data-testid="pagination-summary">{total} record{total === 1 ? "" : "s"} · page {page} of {pages}</p>
    <div className="flex items-center gap-1">
      <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)} data-testid="pagination-prev-btn">
        <ChevronLeft size={14} />
      </Button>
      <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)} data-testid="pagination-next-btn">
        <ChevronRight size={14} />
      </Button>
    </div>
  </div>
);
