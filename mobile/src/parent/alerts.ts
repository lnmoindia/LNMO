// "Today" alerts — same rules as the web parent portal's TodayStrip.
import { addDaysISO, fmtDate, inr, todayISO } from "@/src/lib/format";
import { pendingItems } from "@/src/lib/queries";

export type Alert = { k: string; tone: "rose" | "amber" | "indigo" | "sky" | "emerald"; text: string; action?: string; to: string; icon: string };

export function buildAlerts({ fees, hw, asg, tt, notices, exams }: any): Alert[] {
  const today = todayISO();
  const tmrw = addDaysISO(1);
  const week = addDaysISO(7);
  const open = (fees?.invoices || []).filter((i: any) => (i.balance || 0) > 0);
  const overdue = open.filter((i: any) => i.due_date && i.due_date < today);
  const dueSoon = open.filter((i: any) => i.due_date && i.due_date >= today && i.due_date <= week);
  const sum = (xs: any[]) => inr(xs.reduce((a, i) => a + (i.balance || 0), 0));
  const hwSoon = [...pendingItems(hw || []), ...pendingItems(asg || [])].filter((x) => {
    const d = String(x.due_date || "").slice(0, 10);
    return d === today || d === tmrw;
  });
  const subs = tt?.today_changes?.items?.length || 0;
  const since = addDaysISO(-3);
  const fresh = (notices || []).filter((n: any) => String(n.created_at || "").slice(0, 10) >= since);
  const nextExam = (exams || []).filter((x: any) => x.date >= today).find((x: any) => x.date <= week);
  const items: Alert[] = [];
  if (overdue.length) items.push({ k: "fee-overdue", tone: "rose", icon: "alert-octagon", text: `${sum(overdue)} fee overdue`, action: "Pay", to: `/invoice/${overdue[0].id}` });
  else if (dueSoon.length) items.push({ k: "fee-due", tone: "amber", icon: "credit-card", text: `${sum(dueSoon)} fee due by ${fmtDate(dueSoon[0].due_date, { year: false })}`, action: "Pay", to: `/invoice/${dueSoon[0].id}` });
  if (hwSoon.length) items.push({ k: "homework", tone: "indigo", icon: "book-open", text: `${hwSoon.length} homework/assignment due today or tomorrow`, to: "/more/homework" });
  if (subs) items.push({ k: "substitute", tone: "amber", icon: "user-check", text: `${subs} period${subs > 1 ? "s" : ""} with a substitute or absent teacher today`, to: "/timetable" });
  if (nextExam) items.push({ k: "exam", tone: "sky", icon: "edit-3", text: `Exam: ${nextExam.subject} on ${fmtDate(nextExam.date, { weekday: true, year: false })}`, to: "/more/results" });
  if (fresh.length) items.push({ k: "notices", tone: "emerald", icon: "bell", text: `${fresh.length} new notice${fresh.length > 1 ? "s" : ""}`, to: "/more/notices" });
  return items;
}

export const TONE: Record<Alert["tone"], [string, string]> = {
  rose: ["#FDECEF", "#9F1239"],
  amber: ["#FDF3E1", "#8A4B08"],
  indigo: ["#EEF0FD", "#3730A3"],
  sky: ["#E6F4FB", "#075985"],
  emerald: ["#E7F6EF", "#065F46"],
};
