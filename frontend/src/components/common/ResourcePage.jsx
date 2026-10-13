import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { DataTable, Pagination } from "./DataTable";
import { FormDialog } from "./FormDialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "../ui/alert-dialog";

export default function ResourcePage({ title, singular, description, endpoint, columns, fields, updateEndpoint, rowActions, headerExtra }) {
  const [searchParams] = useSearchParams();
  const urlQ = searchParams.get("q") || "";
  const [data, setData] = useState({ items: [], total: 0, page: 1, pages: 1 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState(urlQ);
  const [page, setPage] = useState(1);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/${endpoint}`, { params: { search, page, limit: 15 } });
      setData(data);
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setLoading(false);
    }
  }, [endpoint, search, page]);

  useEffect(() => {
    if (urlQ) { setSearch(urlQ); setPage(1); }
  }, [urlQ]);

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, search]);

  const itemBase = updateEndpoint || endpoint;

  const handleSubmit = async (values) => {
    setSubmitting(true);
    setFormError("");
    try {
      if (editing) {
        await api.put(`/${itemBase}/${editing.id}`, values);
        toast.success(`${singular} updated`);
      } else {
        await api.post(`/${endpoint}`, values);
        toast.success(`${singular} created`);
      }
      setDialogOpen(false);
      setEditing(null);
      load();
    } catch (e) {
      setFormError(errText(e));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    try {
      await api.delete(`/${itemBase}/${deleting.id}`);
      toast.success(`${singular} deleted`);
      setDeleting(null);
      load();
    } catch (e) {
      toast.error(errText(e));
      setDeleting(null);
    }
  };

  return (
    <div className="space-y-6" data-testid={`${endpoint.replace(/\//g, "-")}-page`}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">{title}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{description}</p>
        </div>
        <div className="flex items-center gap-2">
          {headerExtra && headerExtra({ reload: load })}
          <Button onClick={() => { setEditing(null); setFormError(""); setDialogOpen(true); }} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="add-record-btn">
            <Plus size={15} className="mr-1" /> New {singular}
          </Button>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800">
          <div className="relative max-w-sm">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              placeholder={`Search ${title.toLowerCase()}…`}
              className="pl-9"
              data-testid="search-input"
            />
          </div>
        </div>
        <DataTable
          columns={columns}
          rows={data.items}
          loading={loading}
          rowActions={rowActions}
          onEdit={(row) => { setEditing(row); setFormError(""); setDialogOpen(true); }}
          onDelete={(row) => setDeleting(row)}
        />
        {data.items.length > 0 && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </div>

      <FormDialog
        open={dialogOpen}
        onClose={() => { setDialogOpen(false); setEditing(null); }}
        title={singular}
        fields={fields}
        initial={editing}
        onSubmit={handleSubmit}
        submitting={submitting}
        error={formError}
      />

      <AlertDialog open={Boolean(deleting)} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent data-testid="delete-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this {singular.toLowerCase()}?</AlertDialogTitle>
            <AlertDialogDescription>This action cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="delete-cancel-btn">Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-red-600 hover:bg-red-700" data-testid="delete-confirm-btn">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
