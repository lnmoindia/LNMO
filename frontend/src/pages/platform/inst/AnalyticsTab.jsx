import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { Card, Metric, SkeletonGrid, TrendChart, inr } from "./ui";

const Quota = ({ label, used, limit, total, testid }) => {
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  return (
    <div className="space-y-1.5" data-testid={testid}>
      <div className="flex justify-between text-sm"><span className="text-slate-600 dark:text-slate-300 font-medium">{label}</span>
        <span className="tabular-nums text-slate-500">{used ?? 0} / {limit ?? "no limit"} this cycle · {total ?? 0} logged this month</span></div>
      <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden"><div className={`h-full ${pct > 85 ? "bg-red-500" : "bg-indigo-600"}`} style={{ width: `${pct}%` }} /></div>
    </div>
  );
};

export default function AnalyticsTab({ iid }) {
  const [d, setD] = useState(null);
  useEffect(() => { api.get(`/platform/institutions/${iid}/analytics`).then((r) => setD(r.data)).catch((e) => toast.error(errText(e))); }, [iid]);
  if (!d) return <SkeletonGrid n={8} />;
  const m = d.modules, p = d.people, msg = d.messages;
  return (
    <div className="space-y-6" data-testid="inst-analytics-tab">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Metric label="Students" value={p.students} hint={`${p.student_logins} with a login account`} testid="an-students" />
        <Metric label="Teachers" value={p.teachers} testid="an-teachers" />
        <Metric label="Parents linked" value={p.parents} hint="Parent accounts" testid="an-parents" />
        <Metric label="Active users" value={`${d.active_users.d7} · ${d.active_users.d30}`} hint="Signed in, last 7 · 30 days" tone="indigo" testid="an-active" />
      </div>
      <Card title="Sign-ins, last 30 days" testid="an-trend"><TrendChart data={d.logins_trend} /></Card>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">Module usage · this month</p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Metric label="Attendance days marked" value={m.attendance_days_month} hint={`${m.attendance_registers_month} registers`} testid="an-attendance" />
          <Metric label="Homework posted" value={m.homework_month} hint={`${m.homework_total} all time`} testid="an-homework" />
          <Metric label="Exams published" value={m.exams_published} hint={`of ${m.exams_total} exams`} testid="an-exams" />
          <Metric label="Fee collections" value={inr(m.fee_collections_month.amount)} hint={`${m.fee_collections_month.count} payments`} tone="emerald" testid="an-fees" />
          <Metric label="AI Tutor questions" value={m.ai_tutor_questions_month} hint={`${m.ai_tutor_students_month} students`} testid="an-ai" />
          <Metric label="AI tokens / cost" value={m.ai_tokens} testid="an-ai-tokens" />
          <Metric label="Storage used" value={m.storage_bytes} testid="an-storage" />
        </div>
      </div>
      <Card title="Messages vs quota" action={<span className="text-[11px] font-bold uppercase px-2 py-0.5 rounded bg-amber-100 text-amber-800" data-testid="an-provider">{msg.provider === "stub" ? "STUB — not really sent" : msg.provider}</span>} testid="an-messages">
        <div className="space-y-4">
          <Quota label="WhatsApp" used={msg.quota_used.whatsapp} limit={msg.quota_limits.whatsapp} total={msg.month.whatsapp?.total} testid="an-quota-whatsapp" />
          <Quota label="SMS" used={msg.quota_used.sms} limit={msg.quota_limits.sms} total={msg.month.sms?.total} testid="an-quota-sms" />
          <p className="text-xs text-slate-400">Quota cycle started {msg.cycle_start || "—"}. Status breakdown: {Object.entries(msg.month).map(([ch, v]) => `${ch}: ${Object.entries(v.by_status).map(([s, n]) => `${n} ${s}`).join(", ")}`).join(" · ") || "no messages this month"}.</p>
        </div>
      </Card>
    </div>
  );
}
