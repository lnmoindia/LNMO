// Sign-out warning when registers saved offline haven't synced yet.
import { unsyncedCount } from "./outbox";

export function signOutWarning() {
  const n = unsyncedCount();
  if (!n) return "";
  return `\n\nYou have ${n} unsynced register${n > 1 ? "s" : ""}. They stay hidden on this phone (no one else can send them) and sync when you sign in again.`;
}
