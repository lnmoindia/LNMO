import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  User, Mail, Phone, ShieldCheck, BookOpen, GraduationCap, Crown, ClipboardList, PenLine,
  ChevronRight, Building2, BadgeCheck, CalendarRange,
} from "lucide-react";
import api, { errText } from "../../lib/api";
import { toast } from "sonner";
import { Button } from "../../components/ui/button";
import { AccountLock } from "../../components/common/AccountLock";

const API = process.env.REACT_APP_BACKEND_URL;

export default function TeacherProfileView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [p, setP] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    api.get(`/teachers/${id}/profile`)
      .then((r) => setP(r.data.profile))
      .catch((e) => { setErr(errText(e)); toast.error(errText(e)); });
  }, [id]);

  if (err) return <div className="py-16 text-center text-slate-400" data-testid="teacher-profile-error">{err}</div>;
  if (!p) return <p className="py-16 text-center text-sm text-slate-400">Loading…</p>;

  return (
    <div className="space-y-6" data-testid="teacher-profile-view">
      <nav className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400" data-testid="teacher-profile-breadcrumb">
        <Link to="/app/teachers" className="text-indigo-600 dark:text-indigo-400 hover:underline" data-testid="back-to-teachers">Teachers</Link>
        <ChevronRight size={14} />
        <span className="text-slate-700 dark:text-slate-200 font-medium">{p.name}</span>
      </nav>

      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 flex items-center gap-5" data-testid="teacher-profile-hero">
        <div className="h-20 w-20 rounded-full bg-indigo-600 flex items-center justify-center text-white shrink-0 overflow-hidden">
          {p.has_photo ? <img src={`${API}/api/users/${p.id}/photo`} alt="" className="h-full w-full object-cover" data-testid="teacher-profile-photo" /> : <User size={34} />}
        </div>
        <div className="min-w-0">
          <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2 flex-wrap" data-testid="teacher-profile-name">
            {p.name}
            {p.principal && <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300" data-testid="teacher-principal-badge"><Crown size={12} /> {(p.principal.designation || "principal").replace(/^\w/, (c) => c.toUpperCase())}</span>}
          </h1>
          <div className="text-sm text-slate-500 mt-1 flex items-center gap-4 flex-wrap">
            <span className="inline-flex items-center gap-1.5"><Mail size={14} /> {p.email || "—"}</span>
            <span className="inline-flex items-center gap-1.5">
              <Phone size={14} /> {p.phone || "—"}
              {p.phone && (p.phone_verified
                ? <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 text-xs font-semibold" data-testid="teacher-phone-verified"><BadgeCheck size={13} /> Verified</span>
                : <span className="text-amber-600 text-xs font-medium" data-testid="teacher-phone-unverified">Unverified</span>)}
            </span>
            {p.employee_id && <span className="inline-flex items-center gap-1.5"><ClipboardList size={14} /> {p.employee_id}</span>}
          </div>
          <div className="mt-2"><AccountLock userId={p.id} /></div>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        <InfoCard icon={BookOpen} title="Subjects taught" testid="teacher-subjects">
          {p.subjects?.length ? (
            <div className="flex flex-wrap gap-1.5">{p.subjects.map((s) => <span key={s} className="px-2.5 py-1 rounded-lg text-xs font-medium bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300">{s}</span>)}</div>
          ) : <p className="text-sm text-slate-400">No subjects assigned.</p>}
        </InfoCard>

        <InfoCard icon={PenLine} title="Digital signature" testid="teacher-signature">
          {p.has_signature
            ? <div className="h-16 flex items-center"><img src={`${API}/api/users/${p.id}/signature`} alt="signature" className="max-h-16 object-contain" data-testid="teacher-signature-img" /></div>
            : <p className="text-sm text-slate-400">No signature uploaded.</p>}
        </InfoCard>

        <InfoCard icon={Building2} title="Principal scope" testid="teacher-scope">
          {p.principal
            ? <div className="space-y-1.5" data-testid="teacher-principal-scope">
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 capitalize">{p.principal.designation || "principal"}</p>
                {p.principal.scope_type === "whole_school"
                  ? <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">Whole school</span>
                  : <div className="flex flex-wrap gap-1.5">{(p.principal.unit_names || []).length
                      ? p.principal.unit_names.map((u) => <span key={u} className="px-2.5 py-1 rounded-lg text-xs font-medium bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">{u}</span>)
                      : <span className="text-sm text-slate-400">No divisions</span>}</div>}
              </div>
            : <p className="text-sm text-slate-400">Not a principal.</p>}
        </InfoCard>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <Panel icon={BookOpen} title="Teaching load" testid="teacher-assignments">
          {p.assignments?.length ? (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {p.assignments.map((a, i) => (
                <li key={i} className="px-5 py-3 flex items-center justify-between text-sm">
                  <span className="font-medium text-slate-700 dark:text-slate-200">{a.subject || "General"}</span>
                  <span className="text-slate-500">{a.class_name}{a.section ? ` · ${a.section}` : " · all sections"}</span>
                </li>
              ))}
            </ul>
          ) : <p className="px-5 py-6 text-sm text-slate-400">No teaching assignments.</p>}
        </Panel>

        <Panel icon={Crown} title="Class teacher of" iconClass="text-amber-500" testid="teacher-homerooms">
          {p.homerooms?.length ? (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {p.homerooms.map((h, i) => (
                <li key={i} className="px-5 py-3 text-sm font-medium text-slate-700 dark:text-slate-200">{h.class_name} · Section {h.section}</li>
              ))}
            </ul>
          ) : <p className="px-5 py-6 text-sm text-slate-400">Not a class teacher of any section.</p>}
        </Panel>
      </div>

      <Button variant="outline" onClick={() => navigate("/app/timetable")} data-testid="teacher-view-timetable"><CalendarRange size={15} className="mr-1.5" /> Open timetable</Button>
    </div>
  );
}

const InfoCard = ({ icon: Icon, title, children, testid }) => (
  <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid={testid}>
    <h2 className="font-heading text-sm font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2 mb-3"><Icon size={15} className="text-indigo-600" /> {title}</h2>
    {children}
  </div>
);

const Panel = ({ icon: Icon, title, children, iconClass = "text-indigo-600", testid }) => (
  <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden" data-testid={testid}>
    <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
      <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Icon size={15} className={iconClass} /> {title}</h2>
    </div>
    {children}
  </div>
);
