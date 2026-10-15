// Prefetch for offline use (teachers, incl. a principal in Teacher view): rosters + registers for today and
// yesterday for every class they can mark, plus today's timetable. Runs on app open / foreground / pull-to-refresh.
import { addDaysISO, todayISO } from "@/src/lib/format";
import { cachedGet, getOwner, sheetName, shrinkSheet, writeCache, readCache } from "./cache";
import { isOnlineNow } from "./net";

// Same class list as the Attendance tab: homerooms + teaching sections, de-duplicated.
export function teacherClasses(homes: any[] = [], opts: any[] = []): [string, string][] {
  const m = new Map<string, [string, string]>();
  homes.forEach((h: any) => m.set(`${h.class_name}|${h.name}`, [h.class_name, h.name]));
  opts.forEach((o: any) => m.set(`${o.class_name}|${o.section}`, [o.class_name, o.section]));
  return [...m.values()];
}

let last = 0;
let busy = false;
const done = new Set<() => void>();
export const onPrefetched = (f: () => void) => { done.add(f); return () => { done.delete(f); }; };
export async function prefetchOffline(user: any, force = false) {
  if (!user?.id || user.role !== "teacher" || user.must_change_password || !getOwner() || !isOnlineNow() || busy) return;
  if (!force && Date.now() - last < 120000) return;
  busy = true; last = Date.now();
  try {
    const [hr, op] = await Promise.all([cachedGet("myclass", "/teacher/my-class"), cachedGet("opts", "/teacher/teaching-options")]);
    const today = todayISO();
    const days = [today, addDaysISO(-1)];
    await cachedGet(`tt.${user.id}.${today}`, `/timetable/teacher/${user.id}`, { date: today }).catch(() => null);
    const classes = teacherClasses(hr?.homerooms, op?.options);
    for (const [c, s] of classes) {
      for (const d of days) await cachedGet(sheetName(c, s, d), "/attendance/sheet", { class_name: c, section: s, date: d }, shrinkSheet).catch(() => null);
    }
    await writeCache("meta", { at: new Date().toISOString(), classes: classes.map(([c, s]) => `${c} ${s}`), days });
    done.forEach((f) => f());
  } catch { /* offline or not a teacher of any class — keep what we have */ } finally { busy = false; }
}
export const readPrefetchMeta = () => readCache("meta");
