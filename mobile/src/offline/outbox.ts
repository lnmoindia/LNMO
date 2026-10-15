// The offline outbox: attendance registers saved without a connection, per user + institution.
// Survives restarts (AsyncStorage). Another user's outbox on the same phone is never loaded or sent.
import { useSyncExternalStore } from "react";
import { storage } from "@/src/utils/storage";

export type Entries = Record<string, string>;
export type Snap = { entries: Entries; updated_at: string | null; marked_by?: string | null; finalized?: boolean };
export type Diff = { id: string; name: string; mine?: string; server?: string };
export type Status = "pending" | "conflict" | "rejected" | "failed";
export type Item = {
  id: string; rev: number; class_name: string; section: string; date: string;
  entries: Entries; finalized: boolean; base: Snap; students: { id: string; name: string }[];
  status: Status; created_at: string; updated_at: string; attempts: number; error?: string;
  sent?: Entries; sentRev?: number; resolved?: boolean;
  conflict?: { server: Snap; merged: Entries; list: Diff[] };
  rejected?: { locked: boolean; reason: string; by?: string | null; at?: string | null; diffs: Diff[] };
};
export type HistStatus = "synced" | "conflict_resolved" | "rejected_locked" | "rejected" | "failed";
export type Hist = { id: string; label: string; date: string; status: HistStatus; at: string; detail?: string };

type State = { owner: string | null; email: string | null; loaded: boolean; items: Item[]; history: Hist[] };
let st: State = { owner: null, email: null, loaded: false, items: [], history: [] };
const subs = new Set<() => void>();
const set = (p: Partial<State>) => { st = { ...st, ...p }; subs.forEach((f) => f()); };
const subscribe = (f: () => void) => { subs.add(f); return () => { subs.delete(f); }; };
export const getOutbox = () => st;
export const useOutbox = () => useSyncExternalStore(subscribe, getOutbox, getOutbox);

const K = (o: string) => `lnmo.outbox.${o}`;
const H = (o: string) => `lnmo.synchist.${o}`;
const parse = (raw: any, fb: any) => { try { return raw ? JSON.parse(raw) : fb; } catch { return fb; } };

export async function loadOutbox(owner: string | null, email: string | null) {
  if (owner === st.owner && (st.loaded || !owner)) return;
  set({ owner, email, loaded: false, items: [], history: [] });
  if (!owner) return;
  const [a, b] = await Promise.all([storage.getItem(K(owner), null), storage.getItem(H(owner), null)]);
  if (st.owner !== owner) return;
  set({ items: parse(a, []), history: parse(b, []), loaded: true });
}

async function persist() {
  const o = st.owner;
  if (!o) return;
  await storage.setItem(K(o), JSON.stringify(st.items));
  await storage.setItem(H(o), JSON.stringify(st.history));
}
export async function putItem(it: Item) {
  const items = st.items.some((x) => x.id === it.id) ? st.items.map((x) => (x.id === it.id ? it : x)) : [...st.items, it];
  set({ items });
  await persist();
}
export async function dropItem(id: string) { set({ items: st.items.filter((x) => x.id !== id) }); await persist(); }
export async function logHistory(h: Hist) { set({ history: [h, ...st.history.filter((x) => x.id !== h.id)].slice(0, 20) }); await persist(); }

export const sameReg = (it: Item, c: string, s: string, d: string) => it.class_name === c && it.section === s && it.date === d;
export const findItem = (c: string, s: string, d: string) => st.items.find((x) => sameReg(x, c, s, d));
export const getItem = (id: string) => st.items.find((x) => x.id === id);
export const isWaiting = (it: Item) => it.status === "pending" || it.status === "failed";
export const needsAttention = (it: Item) => it.status === "conflict" || it.status === "rejected";
export function useOutboxCounts() {
  const { items } = useOutbox();
  return { waiting: items.filter(isWaiting).length, attention: items.filter(needsAttention).length };
}
// Owner's unsynced registers (for the sign-out warning).
export const unsyncedCount = () => st.items.length;
