import { useCallback, useEffect, useState } from "react";
import { UserPlus, Search, ShieldCheck, UserCheck, Eye } from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import api, { errText } from "../../lib/api";
import { DataTable, Pagination } from "../../components/common/DataTable";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import AssignPrincipalDialog from "./AssignPrincipalDialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../../components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "../../components/ui/alert-dialog";
import PhoneField from "./PhoneField";
import { Avatar } from "../../components/common/Avatar";

const STATUS = {
  active: { label: "Active", cls: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400" },
  invited: { label: "Invitation pending", cls: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400" },
  inactive: { label: "Inactive", cls: "bg-slate-100 text-slate-500 dark:bg-slate-800" },
  archived: { label: "Archived", cls: "bg-slate-100 text-slate-500 dark:bg-slate-800" },
};

const columns = [
  { key: "name", label: "Name", render: (r) => (
    <span className="flex items-center gap-1.5"><Avatar src={r.thumb_url} name={r.name} size="xs" testid={`teacher-avatar-${r.id}`} />{r.name}{r.is_class_teacher && <ShieldCheck size={13} className="text-indigo-500" title="Class teacher" />}</span>
  ) },
  { key: "email", label: "Login email" },
  { key: "employee_id", label: "Emp. ID" },
  { key: "classes_count", label: "Classes" },
  { key: "subjects_count", label: "Subjects" },
  { key: "status", label: "Status", render: (r) => {
    const s = STATUS[r.status] || STATUS.active;
    return <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${s.cls}`}>{s.label}</span>;
  } },
];

const emptyForm = { name: "", email: "", password: "", employee_id: "", gender: "", phone: "", specialization: "", status: "invited" };

export default function TeachersPage() {
  const navigate = useNavigate();
  const [data, setData] = useState({ items: [], total: 0, page: 1, pages: 1 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [dialog, setDialog] = useState(null); // "add" | teacher-object (edit)
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [assignFor, setAssignFor] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/teachers", { params: { search, page, limit: 15 } });
      setData(data);
    } catch (e) { toast.error(errText(e)); } finally { setLoading(false); }
  }, [search, page]);

  useEffect(() => { const t = setTimeout(load, search ? 300 : 0); return () => clearTimeout(t); }, [load, search]);

  const openAdd = () => { setForm(emptyForm); setDialog("add"); };
  const openEdit = (row) => { setForm({ ...emptyForm, ...row, password: "" }); setDialog(row); };
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const genEmail = async () => {
    try { const { data } = await api.get("/institution/generate-login", { params: { name: form.name } }); set("email", data.email); }
    catch (e) { toast.error(errText(e)); }
  };
  const isAdd = dialog === "add";

  const save = async () => {
    setSaving(true);
    try {
      if (isAdd) {
        await api.post("/teachers", form);
        toast.success("Teacher added — share the temporary password; they'll set their own on first login");
      } else {
        const { email, password, ...rest } = form;
        await api.put(`/teachers/${dialog.id}`, { ...rest, ...(password ? { password } : {}) });
        toast.success("Teacher updated");
      }
      setDialog(null); load();
    } catch (e) { toast.error(errText(e)); } finally { setSaving(false); }
  };

  const handleDelete = async () => {
    try { await api.delete(`/teachers/${deleting.id}`); toast.success("Teacher removed"); setDeleting(null); load(); }
    catch (e) { toast.error(errText(e)); setDeleting(null); }
  };

  return (
    <div className="space-y-6" data-testid="teachers-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">Teachers</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Staff accounts that can sign in and be assigned to classes.</p>
        </div>
        <Button onClick={openAdd} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="add-teacher-open-btn"><UserPlus size={15} className="mr-1.5" /> Add Teacher</Button>
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800">
          <div className="relative max-w-sm">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="Search teachers…" className="pl-9" data-testid="teacher-search-input" />
          </div>
        </div>
        <DataTable columns={columns} rows={data.items} loading={loading} onEdit={openEdit} onDelete={(row) => setDeleting(row)} rowActions={[
          { title: "View profile", icon: Eye, testId: "view-teacher-profile", onClick: (row) => navigate(`/app/teachers/${row.id}`) },
          { title: "Make principal", icon: UserCheck, testId: "teacher-make-principal", onClick: (row) => setAssignFor(row) },
        ]} />
        {data.items.length > 0 && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </div>

      <AssignPrincipalDialog
        open={Boolean(assignFor)}
        preselectTeacher={assignFor}
        onClose={() => setAssignFor(null)}
        onSaved={() => { setAssignFor(null); load(); }}
      />

      <Dialog open={Boolean(dialog)} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent className="sm:max-w-lg max-h-[88vh] overflow-y-auto" data-testid="teacher-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading">{isAdd ? "Add Teacher" : "Edit Teacher"}</DialogTitle>
            <DialogDescription>{isAdd ? "Creates a login-capable teacher account with a temporary password." : "Update this teacher's details."}</DialogDescription>
          </DialogHeader>
          <div className="grid sm:grid-cols-2 gap-4 py-2">
            <div className="space-y-1.5"><Label>Full name <span className="text-red-500">*</span></Label><Input value={form.name} onChange={(e) => set("name", e.target.value)} data-testid="teacher-name" /></div>
            <div className="space-y-1.5"><Label>Login email <span className="text-red-500">*</span></Label>
              <div className="flex gap-2">
                <Input type="email" value={form.email} disabled={!isAdd} onChange={(e) => set("email", e.target.value)} data-testid="teacher-email" />
                {isAdd && <Button type="button" variant="outline" onClick={genEmail} disabled={!form.name} data-testid="teacher-generate-email">Generate</Button>}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>{isAdd ? "Temporary password" : "Reset password (optional)"} {isAdd && <span className="text-red-500">*</span>}</Label>
              <Input type="text" value={form.password} onChange={(e) => set("password", e.target.value)} data-testid="teacher-password" placeholder={isAdd ? "" : "Leave blank to keep"} />
            </div>
            <div className="space-y-1.5"><Label>Employee ID</Label><Input value={form.employee_id || ""} onChange={(e) => set("employee_id", e.target.value)} data-testid="teacher-empid" /></div>
            <div className="space-y-1.5">
              <Label>Gender</Label>
              <Select value={form.gender || ""} onValueChange={(v) => set("gender", v)}>
                <SelectTrigger data-testid="teacher-gender"><SelectValue placeholder="Select gender" /></SelectTrigger>
                <SelectContent><SelectItem value="female">Female</SelectItem><SelectItem value="male">Male</SelectItem><SelectItem value="others">Others</SelectItem></SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Mobile number</Label><PhoneField value={form.phone} onChange={(v) => set("phone", v)} testid="teacher-phone" /></div>
            <div className="space-y-1.5"><Label>Specialization</Label><Input value={form.specialization || ""} onChange={(e) => set("specialization", e.target.value)} data-testid="teacher-spec" /></div>
            <div className="space-y-1.5">
              <Label>Status</Label>
              <Select value={form.status || "invited"} onValueChange={(v) => set("status", v)}>
                <SelectTrigger data-testid="teacher-status"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="active">Active</SelectItem><SelectItem value="invited">Invitation pending</SelectItem><SelectItem value="inactive">Inactive</SelectItem><SelectItem value="archived">Archived</SelectItem></SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDialog(null)}>Cancel</Button>
            <Button disabled={saving || !form.name || (isAdd && (!form.email || !form.password))} onClick={save} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="teacher-save-btn">{saving ? "Saving…" : isAdd ? "Add teacher" : "Save"}</Button>
          </div>
        </DialogContent>
      </Dialog>

      <AlertDialog open={Boolean(deleting)} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent data-testid="teacher-delete-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this teacher?</AlertDialogTitle>
            <AlertDialogDescription>Their account and class assignments will be deleted. This cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-red-600 hover:bg-red-700" data-testid="teacher-delete-confirm">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
