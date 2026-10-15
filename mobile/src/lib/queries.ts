// React-Query hooks for the parent endpoints (same ones the web parent portal calls).
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/lib/api";
import { setTimezone } from "@/src/lib/format";

const base = (cid: string) => `/parent/child/${cid}`;
const on = (cid: string) => Boolean(cid);

export const useSnap = (cid: string) => useQuery({ queryKey: ["snap", cid], queryFn: () => api.get(base(cid)), enabled: on(cid) });
export const useTimetable = (cid: string) => useQuery({ queryKey: ["tt", cid], queryFn: () => api.get(`${base(cid)}/timetable`), enabled: on(cid) });
export const useHomework = (cid: string) => useQuery({ queryKey: ["hw", cid], queryFn: async () => (await api.get(`${base(cid)}/homework`)).homework || [], enabled: on(cid) });
export const useAssignments = (cid: string) => useQuery({ queryKey: ["asg", cid], queryFn: async () => (await api.get(`${base(cid)}/assignments`)).assignments || [], enabled: on(cid) });
export const useFees = (cid: string) => useQuery({ queryKey: ["fees", cid], queryFn: () => api.get(`${base(cid)}/fees`), enabled: on(cid) });
export const useExams = (cid: string) => useQuery({ queryKey: ["exams", cid], queryFn: async () => (await api.get(`${base(cid)}/exams`)).exams || [], enabled: on(cid) });
export const useAttendance = (cid: string, month: string) =>
  useQuery({ queryKey: ["att", cid, month], queryFn: () => api.get(`${base(cid)}/attendance-calendar`, { month }), enabled: on(cid) });
export const useNotices = () => useQuery({ queryKey: ["notices"], queryFn: async () => (await api.get("/notices/feed")).notices || [] });
export const usePayInfo = (inv: string) => useQuery({ queryKey: ["payinfo", inv], queryFn: () => api.get(`/fees/invoices/${inv}/pay-info`), enabled: Boolean(inv) });

export const useThreads = (poll: boolean) => useQuery({
  queryKey: ["threads"],
  queryFn: async () => { const d = await api.get("/chat/threads", { status: "" }); setTimezone(d?.timezone); return d; },
  refetchInterval: poll ? 10000 : false,
});
export const useThread = (tid: string, poll: boolean) => useQuery({
  queryKey: ["thread", tid],
  queryFn: async () => { const d = await api.get(`/chat/threads/${tid}`); setTimezone(d?.timezone); return d; },
  enabled: Boolean(tid),
  refetchInterval: poll ? 10000 : false,
});
export const useUnread = (enabled: boolean) => useQuery({
  queryKey: ["unread"], queryFn: async () => (await api.get("/chat/unread")).unread || 0, enabled, refetchInterval: 30000,
});

// homework/assignments helpers (same rules as the web portal)
export const pendingItems = (items: any[] = []) =>
  (items || []).filter((h) => h.status === "open" && (!h.my_submission || h.my_submission.status === "redo"));
export const filterWork = (items: any[] | undefined, f: string, today: string) => {
  const sub = (x: any) => Boolean(x.my_submission);
  if (!items) return items;
  if (f === "submitted") return items.filter(sub);
  if (f === "overdue") return items.filter((x) => !sub(x) && x.due_date && String(x.due_date).slice(0, 10) < today);
  if (f === "due") return items.filter((x) => !sub(x) && (!x.due_date || String(x.due_date).slice(0, 10) >= today) && x.status !== "closed");
  return items;
};

// ---------- Student (same endpoints as the web student portal) ----------
export const useMe = () => useQuery({ queryKey: ["s-me"], queryFn: () => api.get("/portal/me") });
export const useMyTimetable = () => useQuery({ queryKey: ["s-tt"], queryFn: () => api.get("/portal/timetable") });
export const useMyExams = () => useQuery({ queryKey: ["s-exams"], queryFn: async () => (await api.get("/portal/exams")).exams || [] });
export const useMyHomework = () => useQuery({ queryKey: ["s-hw"], queryFn: async () => (await api.get("/homework")).homework || [] });
export const useMyAssignments = () => useQuery({ queryKey: ["s-asg"], queryFn: async () => (await api.get("/assignments")).assignments || [] });
export const useMyAttendance = (month: string) => useQuery({ queryKey: ["s-att", month], queryFn: () => api.get("/portal/attendance-calendar", { month }) });
export const useMyFees = () => useQuery({ queryKey: ["s-fees"], queryFn: () => api.get("/portal/fees") });
export const useLibrary = () => useQuery({ queryKey: ["s-lib"], queryFn: () => api.get("/ai/library") });
export const useTutorSubjects = () => useQuery({ queryKey: ["tutor-subjects"], queryFn: () => api.get("/ai/tutor/subjects") });
export const useTutorChats = (subject: string) => useQuery({
  queryKey: ["tutor-chats", subject], queryFn: async () => (await api.get("/ai/tutor/chats", { subject })).chats || [], enabled: Boolean(subject),
});

// ---------- Teacher (same endpoints as the web teacher pages) ----------
export const useTeacherTT = (tid: string, date?: string) => useQuery({
  queryKey: ["t-tt", tid, date || ""], queryFn: () => api.get(`/timetable/teacher/${tid}`, date ? { date } : undefined), enabled: Boolean(tid),
});
export const useMySubs = () => useQuery({ queryKey: ["t-subs"], queryFn: () => api.get("/me/substitutions") });
export const useTeachingOptions = () => useQuery({ queryKey: ["t-opts"], queryFn: async () => (await api.get("/teacher/teaching-options")).options || [] });
export const useMyClass = () => useQuery({ queryKey: ["t-myclass"], queryFn: async () => (await api.get("/teacher/my-class")).homerooms || [] });
export const useSection = (id: string) => useQuery({ queryKey: ["t-section", id], queryFn: () => api.get(`/teacher/my-class/${id}`), enabled: Boolean(id) });
export const useTeacherWork = () => useQuery({
  queryKey: ["t-work"],
  queryFn: async () => {
    const [h, a] = await Promise.all([api.get("/homework"), api.get("/assignments")]);
    return [...(h.homework || []).map((x: any) => ({ ...x, kind: "homework" })), ...(a.assignments || []).map((x: any) => ({ ...x, kind: "assignment" }))];
  },
});
export const useAttendanceSheet = (cls: string, sec: string, date: string) => useQuery({
  queryKey: ["t-att", cls, sec, date], queryFn: () => api.get("/attendance/sheet", { class_name: cls, section: sec, date }), enabled: Boolean(cls && date),
});
export const useQuickReplies = (enabled: boolean) => useQuery({ queryKey: ["quick-replies"], queryFn: async () => (await api.get("/chat/quick-replies")).replies || [], enabled });
