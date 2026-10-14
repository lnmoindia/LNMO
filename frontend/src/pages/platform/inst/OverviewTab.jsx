import { useEffect, useState } from "react";
import { CheckCircle2, Circle, Copy, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Card, Metric, SkeletonGrid, fmtDay } from "./ui";

export const LoginLink = ({ loginKey }) => {
  if (!loginKey) return <p className="text-sm text-slate-400">Set a slug, code or domain to get a login link.</p>;
  const link = `${window.location.origin}/login/${encodeURIComponent(loginKey)}`;
  return (
    <div className="flex gap-2" data-testid="branded-login-link">
      <Input readOnly value={link} data-testid="login-link-input" onFocus={(e) => e.target.select()} />
      <Button type="button" variant="outline" onClick={() => { navigator.clipboard?.writeText(link); toast.success("Login link copied"); }} data-testid="copy-login-link"><Copy size={15} className="mr-1" /> Copy</Button>
      <Button type="button" variant="outline" onClick={() => window.open(link, "_blank")} data-testid="open-login-link" aria-label="Open login page"><ExternalLink size={15} /></Button>
    </div>
  );
};

const Fact = ({ k, v }) => (
  <div className="py-2.5 flex justify-between gap-4 border-b border-slate-100 dark:border-slate-800 last:border-0 text-sm">
    <span className="text-slate-500">{k}</span><span className="text-right text-slate-900 dark:text-slate-100 font-medium">{v || "—"}</span>
  </div>
);

export default function OverviewTab({ iid }) {
  const [d, setD] = useState(null);
  useEffect(() => { api.get(`/platform/institutions/${iid}/overview`).then((r) => setD(r.data)).catch((e) => toast.error(errText(e))); }, [iid]);
  if (!d) return <SkeletonGrid />;
  const i = d.institution, c = d.counts;
  const pct = Math.round((d.setup.done / d.setup.total) * 100);
  return (
    <div className="space-y-6" data-testid="inst-overview-tab">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Metric label="Students" value={c.students} testid="ov-students" />
        <Metric label="Teachers" value={c.teachers} testid="ov-teachers" />
        <Metric label="Parent accounts" value={c.parents} testid="ov-parents" />
        <Metric label="Classes · sections" value={`${c.classes} · ${c.sections}`} testid="ov-classes" />
      </div>
      <div className="grid lg:grid-cols-2 gap-6 items-start">
        <Card title="Key facts" testid="ov-facts">
          <Fact k="Created" v={fmtDay(i.created_at)} />
          <Fact k="Academic year" v={d.academic_year ? `${d.academic_year.name} (${d.academic_year.start_date || "?"} → ${d.academic_year.end_date || "?"})` : null} />
          <Fact k="Divisions" v={d.divisions.map((u) => u.name).join(", ")} />
          <Fact k="Contact email" v={i.contact_email} />
          <Fact k="Phone" v={i.phone} />
          <Fact k="Address" v={[i.address, i.city].filter(Boolean).join(", ")} />
          <div className="pt-4"><p className="text-xs font-semibold text-slate-500 mb-2">School login link</p><LoginLink loginKey={d.login_key} /></div>
        </Card>
        <Card title="Setup progress" action={<span className="text-xs font-semibold text-slate-500" data-testid="ov-setup-count">{d.setup.done}/{d.setup.total} · {pct}%</span>} testid="ov-setup">
          <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden mb-4"><div className="h-full bg-indigo-600 transition-[width] duration-700" style={{ width: `${pct}%` }} /></div>
          <ul className="grid sm:grid-cols-2 gap-x-4 gap-y-2">
            {d.setup.steps.map((s) => (
              <li key={s.label} className="flex items-center gap-2 text-sm">
                {s.done ? <CheckCircle2 size={16} className="text-emerald-600 shrink-0" /> : <Circle size={16} className="text-slate-300 shrink-0" />}
                <span className={s.done ? "text-slate-700 dark:text-slate-200" : "text-slate-400"}>{s.label}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
