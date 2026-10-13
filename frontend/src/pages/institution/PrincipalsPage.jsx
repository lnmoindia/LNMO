import { useCallback, useEffect, useState } from "react";
import { UserPlus, Pencil, UserX, Crown } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { DataTable } from "../../components/common/DataTable";
import { Button } from "../../components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "../../components/ui/alert-dialog";
import AssignPrincipalDialog from "./AssignPrincipalDialog";
import { designationLabel } from "../../components/layout/ScopeChip";

const designationBadge = (row) => {
  const isP = row.designation === "principal";
  const cls = isP
    ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300"
    : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>{isP && <Crown size={11} />}{designationLabel(row.designation)}</span>;
};

const scopeText = (row) =>
  row.scope_type === "whole_school"
    ? <span className="text-slate-700 dark:text-slate-300">Whole School</span>
    : <span className="text-slate-700 dark:text-slate-300">{(row.units || []).map((u) => u.name).join(", ") || "—"}</span>;

const columns = [
  { key: "teacher_name", label: "Teacher", render: (r) => r.teacher_name || "—" },
  { key: "teacher_email", label: "Email" },
  { key: "designation", label: "Designation", render: designationBadge },
  { key: "scope", label: "Scope", render: scopeText },
  { key: "created_at", label: "Assigned", render: (r) => (r.created_at || "").slice(0, 10) },
];

export default function PrincipalsPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [assignOpen, setAssignOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [revoking, setRevoking] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/principals");
      setItems(data.items || []);
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const revoke = async () => {
    try {
      await api.delete(`/principals/${revoking.id}`);
      toast.success("Principal access revoked — reverted to plain teacher");
      setRevoking(null);
      load();
    } catch (e) {
      toast.error(errText(e));
      setRevoking(null);
    }
  };

  const rowActions = [
    { title: "Edit", icon: Pencil, testId: "principal-edit", onClick: (row) => { setEditing(row); setAssignOpen(true); } },
    { title: "Revoke", icon: UserX, testId: "principal-revoke", onClick: (row) => setRevoking(row) },
  ];

  return (
    <div className="space-y-6" data-testid="principals-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">Principals</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Elevate teachers to principal with whole-school or division scope. Revoking reverts them to a plain teacher — nothing is deleted.</p>
        </div>
        <Button onClick={() => { setEditing(null); setAssignOpen(true); }} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="assign-principal-open-btn">
          <UserPlus size={15} className="mr-1.5" /> Assign Principal
        </Button>
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
        {!loading && items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center" data-testid="principals-empty">
            <div className="h-14 w-14 rounded-2xl bg-indigo-50 dark:bg-indigo-500/10 flex items-center justify-center mb-4">
              <Crown size={26} className="text-indigo-600 dark:text-indigo-400" strokeWidth={1.6} />
            </div>
            <p className="font-medium text-slate-700 dark:text-slate-200">No principals yet</p>
            <p className="text-sm text-slate-400 mt-1 max-w-xs">Give a teacher principal powers over the whole school or specific divisions.</p>
            <Button onClick={() => { setEditing(null); setAssignOpen(true); }} className="mt-5 bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="assign-principal-empty-btn">
              <UserPlus size={15} className="mr-1.5" /> Assign your first principal
            </Button>
          </div>
        ) : (
          <DataTable columns={columns} rows={items} loading={loading} rowActions={rowActions} testId="principals-table" />
        )}
      </div>

      <AssignPrincipalDialog
        open={assignOpen}
        editing={editing}
        onClose={() => { setAssignOpen(false); setEditing(null); }}
        onSaved={load}
      />

      <AlertDialog open={Boolean(revoking)} onOpenChange={(o) => !o && setRevoking(null)}>
        <AlertDialogContent data-testid="principal-revoke-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke principal access?</AlertDialogTitle>
            <AlertDialogDescription>
              {revoking?.teacher_name} will revert to a plain teacher and immediately lose principal management access. Their teaching assignments, classes and all data remain untouched.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="principal-revoke-cancel">Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={revoke} className="bg-red-600 hover:bg-red-700" data-testid="principal-revoke-confirm">Revoke</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
