// Per-user offline cache (AsyncStorage) for the teacher's work data: rosters, registers, today's timetable.
// Keys: lnmo.off.<institution_id>.<user_id>.<name>. Cleared on sign out.
import AsyncStorage from "@react-native-async-storage/async-storage";
import { api, ApiError } from "@/src/lib/api";
import { storage } from "@/src/utils/storage";

const PFX = "lnmo.off.";
let owner: string | null = null;
export const setCacheOwner = (u: any | null) => { owner = u?.id ? `${u.institution_id}.${u.id}` : null; };
export const getOwner = () => owner;
const ck = (name: string) => (owner ? `${PFX}${owner}.${name}` : null);

export async function readCache(name: string) {
  const k = ck(name);
  if (!k) return null;
  const raw = (await storage.getItem(k, null)) as string | null;
  try { return raw ? JSON.parse(raw) : null; } catch { return null; }
}
export async function writeCache(name: string, data: any) {
  const k = ck(name);
  if (k) await storage.setItem(k, JSON.stringify(data ?? null));
}

// Network first; on a connection error, the last cached copy (if any).
export async function cachedGet(name: string, path: string, params?: Record<string, any>, shrink?: (d: any) => any) {
  try {
    const d = await api.get(path, params);
    const out = shrink ? shrink(d) : d;
    writeCache(name, out);
    return out;
  } catch (e) {
    if (e instanceof ApiError && e.status === 0) {
      const c = await readCache(name);
      if (c) return { ...c, _offline: true };
    }
    throw e;
  }
}

export async function clearOfflineCache() {
  try {
    const keys = (await AsyncStorage.getAllKeys()).filter((k) => k.startsWith(PFX));
    if (keys.length) await AsyncStorage.multiRemove(keys);
  } catch { /* ignore */ }
}

export const sheetName = (c: string, s: string, d: string) => `sheet.${c}.${s}.${d}`;
// Only what the register needs (keeps the cache small on Android).
export const shrinkSheet = (d: any) => ({
  students: (d?.students || []).map((st: any) => ({ id: st.id, first_name: st.first_name, last_name: st.last_name, admission_no: st.admission_no })),
  record: d?.record ?? null,
});
