import { useCallback, useEffect, useState } from "react";
import { UserPlus, Upload, Search, AlertTriangle, KeyRound, X, ShieldCheck, Eye, Download, GraduationCap, UserMinus, Send } from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import api, { errText } from "../../lib/api";
import { DataTable, Pagination } from "../../components/common/DataTable";
import { FormDialog } from "../../components/common/FormDialog";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
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
import StudentEnrollWizard from "./StudentEnrollWizard";
import BulkImportDialog from "./BulkImportDialog";
import EnrollmentPicker from "./EnrollmentPicker";
import { InviteParentsDialog, ReadyToInvitePanel } from "./ParentInvites";
import { OnboardingProgress } from "./OnboardingProgress";

const enrollBadge = (row) => {
  const s = row.enrollment_status;
  if (s === "enrolled") return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400">Enrolled</span>;
  if (s === "alumni") return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400" data-testid="status-alumni"><GraduationCap size={11} /> Alumni</span>;
  if (s === "transferred") return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400" data-testid="status-transferred"><UserMinus size={11} /> Transferred</span>;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400">
      <AlertTriangle size={11} /> Not enrolled
    </span>
  );
};

const fullName = (row) => `${row.first_name || ""} ${row.last_name || ""}`.trim() || "—";

const columns = [
  { key: "name", label: "Name", render: fullName },
  { key: "admission_no", label: "Admission No." },
  { key: "enrollment_status", label: "Enrollment", render: enrollBadge },
  { key: "class_name", label: "Class" },
  { key: "section", label: "Section" },
  { key: "guardian_name", label: "Guardian" },
  { key: "has_portal_access", label: "Portal", render: (r) => r.has_portal_access
    ? <span className="inline-flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400"><ShieldCheck size={12} /> Yes</span>
    : <span className="text-xs text-slate-400">—</span> },
];

const FilterSelect = ({ testid, placeholder, value, options, onChange }) => (
  <Select value={value || "__all__"} onValueChange={(v) => onChange(v === "__all__" ? "" : v)}>
    <SelectTrigger className="w-[150px]" data-testid={testid}><SelectValue placeholder={placeholder} /></SelectTrigger>
    <SelectContent>
      <SelectItem value="__all__">{placeholder}</SelectItem>
      {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
    </SelectContent>
  </Select>
);

const editFields = [
  { name: "first_name", label: "First name", required: true },
  { name: "last_name", label: "Last name" },
  { name: "admission_no", label: "Admission number" },
  { name: "email", label: "Email", type: "email" },
  { name: "gender", label: "Gender", type: "select", options: [{ value: "female", label: "Female" }, { value: "male", label: "Male" }, { value: "others", label: "Others" }] },
  { name: "guardian_name", label: "Guardian name" },
  { name: "guardian_phone", label: "Guardian phone" },
  { name: "date_of_birth", label: "Date of birth", type: "date" },
];

export default function StudentsPage() {
  const navigate = useNavigate();
  const [data, setData] = useState({ items: [], total: 0, page: 1, pages: 1 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteTick, setInviteTick] = useState(0);
  const [editing, setEditing] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [deleting, setDeleting] = useState(null);
  const [enrolling, setEnrolling] = useState(null);
  const [placement, setPlacement] = useState({ academic_year: "", academic_unit_id: "", class_name: "", section: "" });
  const [enrollSaving, setEnrollSaving] = useState(false);
  const [classFilter, setClassFilter] = useState("");
  const [sectionFilter, setSectionFilter] = useState("");
  const [subjectFilter, setSubjectFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [opts, setOpts] = useState({ classes: [], sections: [], subjects: [] });
  const [portalFor, setPortalFor] = useState(null);
  const [portalForm, setPortalForm] = useState({ email: "", password: "" });
  const [portalSaving, setPortalSaving] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);

  const createAllLogins = async () => {
    if (!window.confirm("Create portal logins for every enrolled student who doesn't have one yet? Password will be 'student123'.")) return;
    setBulkBusy(true);
    try {
      const { data } = await api.post("/students/bulk-portal-users", { password: "student123" });
      toast.success(`${data.created_count} logins created (${data.existing_count} already existed)`);
      if (data.created.length) {
        const header = "Name,Admission No,Class,Section,Login Email,Password";
        const lines = [...data.created, ...data.existing].map((r) =>
          [r.name, r.admission_no || "", r.class || "", r.section || "", r.email || "", r.password || "student123"]
            .map((x) => `"${String(x).replace(/"/g, '""')}"`).join(","));
        downloadCsv("student-logins-new.csv", [header, ...lines].join("\n"));
      }
      load();
    } catch (e) { toast.error(errText(e)); } finally { setBulkBusy(false); }
  };

  const downloadLoginsCsv = async () => {
    try {
      const { data } = await api.get("/students/portal-credentials");
      const header = "Name,Admission No,Class,Section,Login Email,Has Portal";
      const lines = data.students.map((r) =>
        [r.name, r.admission_no || "", r.class || "", r.section || "", r.email || "", r.has_portal ? "Yes" : "No"]
          .map((x) => `"${String(x).replace(/"/g, '""')}"`).join(","));
      downloadCsv("student-logins.csv", [header, ...lines].join("\n"));
      toast.success(`${data.with_portal}/${data.total} students have portal logins`);
    } catch (e) { toast.error(errText(e)); }
  };

  const downloadCsv = (filename, text) => {
    const blob = new Blob([text], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/students/filter", { params: { search, page, limit: 15, class_name: classFilter, section: sectionFilter, subject: subjectFilter, status: statusFilter } });
      setData(data);
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setLoading(false);
    }
  }, [search, page, classFilter, sectionFilter, subjectFilter, statusFilter]);

  useEffect(() => {
    Promise.all([api.get("/lookup/classes"), api.get("/res/sections", { params: { limit: 500 } }), api.get("/lookup/subjects")])
      .then(([c, s, sub]) => setOpts({
        classes: c.data,
        sections: (s.data.items || []).map((x) => ({ value: x.name, label: x.name, class_name: x.class_name })),
        subjects: sub.data,
      }))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, search]);

  const notEnrolled = data.items.filter((s) => s.enrollment_status !== "enrolled").length;

  const handleEditSubmit = async (values) => {
    setSubmitting(true); setFormError("");
    try {
      await api.put(`/res/students/${editing.id}`, values);
      toast.success("Student updated");
      setEditing(null); load();
    } catch (e) { setFormError(errText(e)); } finally { setSubmitting(false); }
  };

  const handleDelete = async () => {
    try {
      await api.delete(`/res/students/${deleting.id}`);
      toast.success("Student deleted"); setDeleting(null); load();
    } catch (e) { toast.error(errText(e)); setDeleting(null); }
  };

  const openEnroll = (row) => {
    setEnrolling(row);
    setPlacement({ academic_year: row.academic_year || "", academic_unit_id: "", class_name: row.class_name || "", section: row.section || "" });
  };

  const submitEnroll = async () => {
    setEnrollSaving(true);
    try {
      await api.post("/res/enrollments", {
        student_id: enrolling.id, academic_year: placement.academic_year,
        class_name: placement.class_name, section: placement.section,
      });
      toast.success("Student enrolled"); setEnrolling(null); load();
    } catch (e) { toast.error(errText(e)); } finally { setEnrollSaving(false); }
  };

  const rowActions = [
    { title: "View profile", icon: Eye, testId: "view-student-profile", onClick: (row) => navigate(`/app/students/${row.id}`) },
    { title: "Enroll / update placement", icon: UserPlus, testId: "enroll-student-btn", onClick: openEnroll },
    { title: "Create portal login", icon: KeyRound, testId: "portal-login-btn", onClick: openPortal },
    { title: "Parent login", icon: ShieldCheck, testId: "parent-login-btn", onClick: (row) => { setParentFor(row); setParentForm({ email: "", password: "", name: row.guardian_name || "" }); } },
  ];
  const [parentFor, setParentFor] = useState(null);
  const [parentForm, setParentForm] = useState({ email: "", password: "", name: "" });
  const [parentSaving, setParentSaving] = useState(false);
  const [linkedParents, setLinkedParents] = useState([]);
  const loadLinkedParents = async (sid) => {
    try { const { data } = await api.get(`/students/${sid}/parents`); setLinkedParents(data.parents || []); }
    catch { setLinkedParents([]); }
  };
  useEffect(() => { if (parentFor) loadLinkedParents(parentFor.id); else setLinkedParents([]); }, [parentFor]);
  const submitParent = async () => {
    setParentSaving(true);
    try {
      const { data } = await api.post(`/students/${parentFor.id}/parent-user`, parentForm);
      toast.success(data.message);
      setParentForm((f) => ({ ...f, email: "", password: "" }));
      loadLinkedParents(parentFor.id);
    } catch (e) { toast.error(errText(e)); } finally { setParentSaving(false); }
  };
  const unlinkParent = async (email) => {
    try { await api.post(`/students/${parentFor.id}/unlink-parent`, { email }); toast.success("Parent unlinked"); loadLinkedParents(parentFor.id); }
    catch (e) { toast.error(errText(e)); }
  };

  function openPortal(row) {
    setPortalFor(row);
    setPortalForm({ email: row.portal_email || row.email || "", password: "" });
  }
  const submitPortal = async () => {
    setPortalSaving(true);
    try {
      await api.post(`/students/${portalFor.id}/portal-user`, portalForm);
      toast.success("Portal login created"); setPortalFor(null); load();
    } catch (e) { toast.error(errText(e)); } finally { setPortalSaving(false); }
  };
  const revokePortal = async () => {
    setPortalSaving(true);
    try {
      await api.delete(`/students/${portalFor.id}/portal-user`);
      toast.success("Portal login revoked"); setPortalFor(null); load();
    } catch (e) { toast.error(errText(e)); } finally { setPortalSaving(false); }
  };

  return (
    <div className="space-y-6" data-testid="students-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">Students</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Create students and enroll them into classes and sections.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={() => setInviteOpen(true)} data-testid="invite-parents-open-btn">
            <Send size={15} className="mr-1.5" /> Invite Parents
          </Button>
          <Button variant="outline" onClick={createAllLogins} disabled={bulkBusy} data-testid="bulk-portal-logins-btn">
            <KeyRound size={15} className="mr-1.5" /> {bulkBusy ? "Creating…" : "Create portal logins"}
          </Button>
          <Button variant="outline" onClick={downloadLoginsCsv} data-testid="download-logins-csv-btn">
            <Download size={15} className="mr-1.5" /> Download logins CSV
          </Button>
          <Button variant="outline" onClick={() => setBulkOpen(true)} data-testid="bulk-import-open-btn">
            <Upload size={15} className="mr-1.5" /> Import CSV
          </Button>
          <Button onClick={() => setWizardOpen(true)} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="enroll-student-open-btn">
            <UserPlus size={15} className="mr-1.5" /> Enroll Student
          </Button>
        </div>
      </div>

      <ReadyToInvitePanel refreshKey={inviteTick} />
      <OnboardingProgress refreshKey={inviteTick} />

      {notEnrolled > 0 && (
        <div className="flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10 p-3 text-sm" data-testid="not-enrolled-banner">
          <AlertTriangle size={16} className="text-amber-600 shrink-0" />
          <p className="text-amber-800 dark:text-amber-200">
            <span className="font-semibold">{notEnrolled}</span> student{notEnrolled === 1 ? " is" : "s are"} not enrolled on this page — they are excluded from attendance, marks and results until placed in a class.
          </p>
        </div>
      )}

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="Search students…" className="pl-9" data-testid="search-input" />
          </div>
          <FilterSelect testid="filter-class" placeholder="All classes" value={classFilter} options={opts.classes} onChange={(v) => { setClassFilter(v); setPage(1); }} />
          <FilterSelect testid="filter-section" placeholder="All sections" value={sectionFilter} options={classFilter ? opts.sections.filter((s) => s.class_name === classFilter) : opts.sections.filter((s, i, a) => a.findIndex((x) => x.value === s.value) === i)} onChange={(v) => { setSectionFilter(v); setPage(1); }} />
          <FilterSelect testid="filter-subject" placeholder="All subjects" value={subjectFilter} options={opts.subjects} onChange={(v) => { setSubjectFilter(v); setPage(1); }} />
          <FilterSelect testid="filter-status" placeholder="All statuses" value={statusFilter} options={[{ value: "enrolled", label: "Enrolled" }, { value: "alumni", label: "Alumni" }, { value: "transferred", label: "Transferred" }, { value: "not_enrolled", label: "Not enrolled" }]} onChange={(v) => { setStatusFilter(v); setPage(1); }} />
          {(classFilter || sectionFilter || subjectFilter || statusFilter) && (
            <Button variant="ghost" size="sm" onClick={() => { setClassFilter(""); setSectionFilter(""); setSubjectFilter(""); setStatusFilter(""); setPage(1); }} data-testid="clear-filters-btn"><X size={14} className="mr-1" /> Clear</Button>
          )}
        </div>
        <DataTable
          columns={columns}
          rows={data.items}
          loading={loading}
          rowActions={rowActions}
          onEdit={(row) => { setEditing(row); setFormError(""); }}
          onDelete={(row) => setDeleting(row)}
        />
        {data.items.length > 0 && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </div>

      <StudentEnrollWizard open={wizardOpen} onClose={() => setWizardOpen(false)} onDone={load} />
      <BulkImportDialog open={bulkOpen} onClose={() => setBulkOpen(false)} onDone={load} />
      <InviteParentsDialog open={inviteOpen} onClose={() => setInviteOpen(false)} classes={opts.classes} onDone={() => setInviteTick((t) => t + 1)} />

      <FormDialog
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title="Student"
        fields={editFields}
        initial={editing}
        onSubmit={handleEditSubmit}
        submitting={submitting}
        error={formError}
      />

      <Dialog open={Boolean(enrolling)} onOpenChange={(o) => !o && setEnrolling(null)}>
        <DialogContent className="sm:max-w-lg" data-testid="enroll-existing-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading">Enroll {enrolling ? fullName(enrolling) : ""}</DialogTitle>
            <DialogDescription>Place this student into a class and section for an academic year.</DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <EnrollmentPicker value={placement} onChange={setPlacement} />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setEnrolling(null)} data-testid="enroll-cancel-btn">Cancel</Button>
            <Button disabled={!placement.class_name || enrollSaving} onClick={submitEnroll} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="enroll-confirm-btn">
              {enrollSaving ? "Enrolling…" : "Enroll"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(parentFor)} onOpenChange={(o) => !o && setParentFor(null)}>
        <DialogContent className="sm:max-w-md" data-testid="parent-login-dialog">
          <DialogHeader>
            <DialogTitle>Parent login — {parentFor && `${parentFor.first_name || ""} ${parentFor.last_name || ""}`.trim()}</DialogTitle>
            <DialogDescription>Create a parent account, or enter an existing parent's email to link this child to it.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-1">
            <Input placeholder="Parent email" value={parentForm.email} onChange={(e) => setParentForm((f) => ({ ...f, email: e.target.value }))} data-testid="parent-email-input" />
            <Input placeholder="Parent name (for new accounts)" value={parentForm.name} onChange={(e) => setParentForm((f) => ({ ...f, name: e.target.value }))} data-testid="parent-name-input" />
            <Input type="password" placeholder="Password (only for new accounts)" value={parentForm.password} onChange={(e) => setParentForm((f) => ({ ...f, password: e.target.value }))} data-testid="parent-password-input" />
            {linkedParents.length > 0 && (
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 divide-y divide-slate-100 dark:divide-slate-800" data-testid="linked-parents-list">
                {linkedParents.map((p) => (
                  <div key={p.id} className="flex items-center justify-between px-3 py-2 text-sm">
                    <span className="text-slate-700 dark:text-slate-200 truncate">{p.name || p.email} <span className="text-slate-400">· {p.email}</span></span>
                    <button onClick={() => unlinkParent(p.email)} className="text-red-600 hover:text-red-700 text-xs font-medium" data-testid={`unlink-parent-${p.email}`}>Unlink</button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setParentFor(null)} data-testid="parent-cancel-btn">Close</Button>
              <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" disabled={!parentForm.email || parentSaving} onClick={submitParent} data-testid="parent-save-btn">
                {parentSaving ? "Saving…" : "Create / link parent"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(portalFor)} onOpenChange={(o) => !o && setPortalFor(null)}>
        <DialogContent className="sm:max-w-md" data-testid="portal-login-dialog">
          {portalFor?.has_portal_access ? (
            <>
              <DialogHeader>
                <DialogTitle className="font-heading">Portal login</DialogTitle>
                <DialogDescription>{portalFor ? fullName(portalFor) : ""} can sign in with <span className="font-medium">{portalFor?.portal_email}</span>.</DialogDescription>
              </DialogHeader>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setPortalFor(null)}>Close</Button>
                <Button disabled={portalSaving} onClick={revokePortal} className="bg-red-600 hover:bg-red-700 text-white" data-testid="portal-revoke-btn">{portalSaving ? "Revoking…" : "Revoke access"}</Button>
              </div>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle className="font-heading">Create portal login</DialogTitle>
                <DialogDescription>Give {portalFor ? fullName(portalFor) : ""} access to the Student Portal.</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-1.5"><Label>Login email</Label><Input type="email" value={portalForm.email} onChange={(e) => setPortalForm((f) => ({ ...f, email: e.target.value }))} data-testid="portal-email" /></div>
                <div className="space-y-1.5"><Label>Password</Label><Input type="password" value={portalForm.password} onChange={(e) => setPortalForm((f) => ({ ...f, password: e.target.value }))} data-testid="portal-password" /></div>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setPortalFor(null)}>Cancel</Button>
                <Button disabled={!portalForm.email || !portalForm.password || portalSaving} onClick={submitPortal} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="portal-create-btn">{portalSaving ? "Creating…" : "Create login"}</Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog open={Boolean(deleting)} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent data-testid="delete-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this student?</AlertDialogTitle>
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
