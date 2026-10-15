// Offline attendance sync: saves go to the outbox when offline (or on a connection error), then sync in order
// through the SAME POST /attendance/sheet, with an Idempotency-Key so a retried send is applied once.
// Before applying, the current server register is fetched and merged per student (3-way, against the base
// the teacher started from): only-teacher changes apply, only-server changes stay, both-changed = a conflict.
import { api, ApiError } from "@/src/lib/api";
import { queryClient } from "@/src/query-client";
import { fullName } from "@/src/lib/format";
import { sheetName, shrinkSheet, writeCache } from "./cache";
import { isOnlineNow } from "./net";
import { dropItem, findItem, getItem, getOutbox, isWaiting, logHistory, putItem, type Diff, type Entries, type Item, type Snap } from "./outbox";

type Notify = (msg: string, tone?: "success" | "error" | "info") => void;
let notify: Notify = () => {};
export const setSyncNotifier = (f: Notify) => { notify = f; };

const now = () => new Date().toISOString();
const newId = () => `m${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
const label = (it: Item) => `${it.class_name} ${it.section}`.trim();
export const snap = (rec: any): Snap => ({ entries: rec?.entries || {}, updated_at: rec?.updated_at || null, marked_by: rec?.marked_by || null, finalized: Boolean(rec?.finalized) });
const sameEntries = (a: Entries = {}, b: Entries = {}) => {
  const ka = Object.keys(a).filter((x) => a[x]); const kb = Object.keys(b).filter((x) => b[x]);
  return ka.length === kb.length && ka.every((x) => a[x] === b[x]);
};

export function merge3(base: Entries, mine: Entries, server: Entries, ids: string[], name: (id: string) => string) {
  const merged: Entries = {}; const list: Diff[] = [];
  for (const id of ids) {
    const b = base[id], m = mine[id], s = server[id];
    if (m === b || m === s) { if (s) merged[id] = s; } // teacher didn't change it (or same value) → server
    else if (s === b) { if (m) merged[id] = m; } // only the teacher changed it
    else { list.push({ id, name: name(id), mine: m, server: s }); if (s) merged[id] = s; }
  }
  return { merged, list };
}

// Teacher changes that differ from the server (shown when a register couldn't be applied).
const unapplied = (it: Item, server: Entries, name: (id: string) => string): Diff[] =>
  Object.keys(it.entries).filter((id) => it.entries[id] !== it.base.entries[id] && it.entries[id] !== server[id])
    .map((id) => ({ id, name: name(id), mine: it.entries[id], server: server[id] }));

async function reject(it: Item, locked: boolean, reason: string, rec: any, name: (id: string) => string) {
  const r = { locked, reason, by: rec?.marked_by || null, at: rec?.updated_at || null, diffs: unapplied(it, rec?.entries || {}, name) };
  await putItem({ ...it, status: "rejected", rejected: r, conflict: undefined, updated_at: now() });
  await logHistory({ id: it.id, label: label(it), date: it.date, status: locked ? "rejected_locked" : "rejected", at: now(), detail: reason });
  return "rejected" as const;
}

async function finish(it: Item, rec: any, students: any[]) {
  const latest = getItem(it.id);
  if (latest && latest.rev !== it.rev) { await putItem({ ...latest, status: "pending", base: snap(rec), sent: undefined }); return "done" as const; }
  await dropItem(it.id);
  await logHistory({ id: it.id, label: label(it), date: it.date, status: it.resolved ? "conflict_resolved" : "synced", at: now() });
  const sheet = shrinkSheet({ students, record: rec });
  await writeCache(sheetName(it.class_name, it.section, it.date), sheet);
  queryClient.invalidateQueries({ queryKey: ["t-att"] });
  return "done" as const;
}

async function onError(it: Item, e: any, rec: any, name: (id: string) => string) {
  const st = e instanceof ApiError ? e.status : 0;
  if (st === 0 || st === 401 || e?.detail?.code === "PASSWORD_CHANGE_REQUIRED") return "offline" as const; // keep it; retry later / after sign-in
  if (st === 403 && /finali[sz]ed/i.test(e.message)) return reject(it, true, "Register was finalised", rec, name);
  if (st >= 400 && st < 500) return reject(it, false, e.message || `Not accepted (${st})`, rec, name);
  await putItem({ ...it, status: "failed", attempts: it.attempts + 1, error: e?.message || "Server error", updated_at: now() });
  await logHistory({ id: it.id, label: label(it), date: it.date, status: "failed", at: now(), detail: e?.message });
  return "failed" as const;
}

async function syncItem(item: Item) {
  let it = item;
  const params = { class_name: it.class_name, section: it.section, date: it.date };
  let cur: any;
  const local = Object.fromEntries(it.students.map((x) => [x.id, x.name]));
  try { cur = await api.get("/attendance/sheet", params); } catch (e) { return onError(it, e, null, (id) => local[id] || "Student"); }
  const rec = cur?.record || null;
  const students = cur?.students || [];
  const names: Record<string, string> = { ...local, ...Object.fromEntries(students.map((x: any) => [x.id, fullName(x)])) };
  const name = (id: string) => names[id] || "Student";
  // A previous send went through but the reply was lost → already applied.
  if (it.sent && rec && rec.marked_by === getOutbox().email && sameEntries(rec.entries, it.sent)) {
    if (it.sentRev === it.rev && Boolean(rec.finalized) === it.finalized) return finish(it, rec, students);
    it = { ...it, base: snap(rec), sent: undefined }; // that earlier send landed — newer edits now build on it
  }
  if (rec?.finalized) return reject(it, true, `Register was finalised by ${rec.marked_by || "the school"}`, rec, name);
  const { merged, list } = merge3(it.base.entries, it.entries, rec?.entries || {}, students.map((x: any) => x.id), name);
  if (list.length) {
    await putItem({ ...it, status: "conflict", conflict: { server: snap(rec), merged, list }, updated_at: now() });
    return "conflict" as const;
  }
  const sending = { ...it, sent: merged, sentRev: it.rev };
  await putItem(sending);
  try {
    const res = await api.post("/attendance/sheet", { ...params, entries: merged, finalized: it.finalized }, { "Idempotency-Key": `${it.id}.${it.rev}` });
    return finish(sending, res, students);
  } catch (e) { return onError(sending, e, rec, name); }
}

let running: Promise<void> | null = null;
export function syncNow(manual = false) {
  if (!running) running = run(manual).finally(() => { running = null; });
  return running;
}
async function run(manual: boolean) {
  const { owner, loaded } = getOutbox();
  if (!owner || !loaded) return;
  if (!isOnlineNow()) { if (manual) notify("You're offline — registers will sync when the connection is back", "info"); return; }
  const queue = getOutbox().items.filter((i) => i.status === "pending" || (i.status === "failed" && (manual || i.attempts < 5)))
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  let ok = 0, bad = 0, failed = 0;
  for (const q of queue) {
    const it = getItem(q.id);
    if (!it || getOutbox().owner !== owner) break;
    const r = await syncItem(it);
    if (r === "offline") break;
    if (r === "done") ok += 1; else if (r === "failed") failed += 1; else bad += 1;
  }
  if (bad) notify(`${bad} register${bad > 1 ? "s need" : " needs"} attention — open More → Offline sync`, "error");
  else if (failed) notify("Sync failed — will retry", "error");
  else if (ok) notify(ok > 1 ? `Synced ✓ · ${ok} registers` : "Synced ✓", "success");
  else if (manual && !queue.length) notify("Nothing waiting to sync", "info");
}

type SaveIn = { class_name: string; section: string; date: string; entries: Entries; finalized: boolean; baseRecord: any; students: any[] };
const studentNames = (students: any[]) => students.map((x) => ({ id: x.id, name: fullName(x) }));

// Register save: online → straight to the server (as before); offline / connection error → outbox.
export async function saveRegister(p: SaveIn): Promise<"saved" | "queued" | "attention"> {
  const ex = findItem(p.class_name, p.section, p.date);
  const t = now();
  const fresh = (id = newId()): Item => ({
    id, rev: 0, class_name: p.class_name, section: p.section, date: p.date, entries: p.entries, finalized: p.finalized,
    base: snap(p.baseRecord), students: studentNames(p.students), status: "pending", created_at: t, updated_at: t, attempts: 0,
  });
  if (ex || !isOnlineNow()) {
    const it: Item = ex ? { ...ex, entries: p.entries, finalized: p.finalized, rev: ex.rev + 1, status: "pending", conflict: undefined, rejected: undefined, attempts: 0, updated_at: t, students: studentNames(p.students) } : fresh();
    await putItem(it);
    if (!isOnlineNow()) return "queued";
    await syncNow();
    const left = getItem(it.id);
    return !left ? "saved" : isWaiting(left) ? "queued" : "attention";
  }
  const id = newId();
  try {
    const rec = await api.post("/attendance/sheet", { class_name: p.class_name, section: p.section, date: p.date, entries: p.entries, finalized: p.finalized }, { "Idempotency-Key": `${id}.0` });
    await writeCache(sheetName(p.class_name, p.section, p.date), shrinkSheet({ students: p.students, record: rec }));
    return "saved";
  } catch (e) {
    if (e instanceof ApiError && e.status === 0) { await putItem({ ...fresh(id), sent: p.entries, sentRev: 0 }); return "queued"; }
    throw e;
  }
}

export async function resolveConflict(id: string, pick: Record<string, "mine" | "server">) {
  const it = getItem(id);
  if (!it?.conflict) return;
  const entries = { ...it.conflict.merged };
  for (const d of it.conflict.list) {
    const v = pick[d.id] === "mine" ? d.mine : d.server;
    if (v) entries[d.id] = v; else delete entries[d.id];
  }
  await putItem({ ...it, entries, base: it.conflict.server, rev: it.rev + 1, status: "pending", conflict: undefined, resolved: true, sent: undefined, updated_at: now() });
  await syncNow(true);
}
export async function retryItem(id: string) {
  const it = getItem(id);
  if (it) { await putItem({ ...it, status: "pending", attempts: 0, rejected: undefined }); await syncNow(true); }
}
export const dismissItem = (id: string) => dropItem(id);
