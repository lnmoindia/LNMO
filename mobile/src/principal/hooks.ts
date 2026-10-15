// Principal (elevated teacher) data hooks. Every endpoint is scoped server-side to the principal's divisions.
import { useQueries, useQuery } from "@tanstack/react-query";
import { api } from "@/src/lib/api";
import { todayISO } from "@/src/lib/format";

export const usePSections = () => useQuery({
  queryKey: ["p-sections"],
  queryFn: async () => {
    const d = await api.get("/res/sections");
    const rows: any[] = Array.isArray(d) ? d : d.items || [];
    return rows.map((x) => [x.class_name, x.name] as [string, string]).sort((a, b) => `${a[0]}${a[1]}`.localeCompare(`${b[0]}${b[1]}`, undefined, { numeric: true }));
  },
});

/** Today's register status per section in my divisions (same /attendance/sheet the web uses). */
export function useTodayAttendance(sections: [string, string][]) {
  const date = todayISO();
  const qs = useQueries({
    queries: sections.map(([c, s]) => ({
      queryKey: ["t-att", c, s, date],
      queryFn: () => api.get(`/attendance/sheet?class_name=${encodeURIComponent(c)}&section=${encodeURIComponent(s)}&date=${date}`),
    })),
  });
  const rows = sections.map(([c, s], i) => {
    const d: any = qs[i]?.data;
    const total = d?.students?.length || 0;
    const e = d?.record?.entries || {};
    const n = { present: 0, absent: 0, late: 0 };
    Object.values(e).forEach((v: any) => { if (v === "present" || v === "absent" || v === "late") n[v as "present" | "absent" | "late"] += 1; });
    return { class_name: c, section: s, total, marked: Boolean(d?.record), final: Boolean(d?.record?.finalized), ...n, loading: qs[i]?.isLoading };
  });
  const marked = rows.filter((r) => r.marked);
  const seen = marked.reduce((a, r) => a + r.present + r.late + r.absent, 0);
  const pct = seen ? Math.round((100 * marked.reduce((a, r) => a + r.present + r.late, 0)) / seen) : null;
  return { rows, marked: marked.length, pct, loading: qs.some((q) => q.isLoading), refetch: () => Promise.all(qs.map((q) => q.refetch())) };
}

export const useSubsDay = (date: string) => useQuery({ queryKey: ["p-subs", date], queryFn: () => api.get(`/substitutions?date=${date}`) });
export const useAbsences = () => useQuery({ queryKey: ["p-absences"], queryFn: async () => (await api.get("/absences")).absences || [] });
export const useTeachers = () => useQuery({ queryKey: ["p-teachers"], queryFn: async () => (await api.get("/teachers?limit=500")).items || [] });
