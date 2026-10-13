import { UserCheck, UserX } from "lucide-react";

export const coverFor = (changes, day, pno) =>
  changes && changes.day === day ? changes.items.find((i) => i.period_no === pno) : null;

export const CoverBadge = ({ item, testid }) => {
  if (!item) return null;
  return item.kind === "substitute" ? (
    <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-amber-100 dark:bg-amber-500/15 text-amber-800 dark:text-amber-300 px-2 py-0.5 text-[10px] font-semibold" data-testid={testid}>
      <UserCheck size={10} /> Substitute: {item.substitute_name}
    </span>
  ) : (
    <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-rose-100 dark:bg-rose-500/15 text-rose-700 dark:text-rose-300 px-2 py-0.5 text-[10px] font-semibold" data-testid={testid}>
      <UserX size={10} /> Teacher absent — cover being arranged
    </span>
  );
};

export const TodayChanges = ({ changes, testid = "today-changes" }) => {
  const items = changes?.items || [];
  if (!items.length) return null;
  const subs = items.filter((i) => i.kind === "substitute").length;
  const open = items.length - subs;
  const parts = [];
  if (subs) parts.push(`${subs} period${subs > 1 ? "s have" : " has"} a substitute teacher today`);
  if (open) parts.push(`${open} period${open > 1 ? "s" : ""} awaiting cover`);
  return (
    <p className="mx-6 mt-3 rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 px-3 py-2 text-xs font-medium text-amber-800 dark:text-amber-300" data-testid={testid}>
      Today's changes: {parts.join(" · ")}
    </p>
  );
};
