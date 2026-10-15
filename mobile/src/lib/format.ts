// Formatting helpers: ₹ in en-IN grouping, dates in the institution timezone (IST fallback).
let TZ = "Asia/Kolkata";
export const setTimezone = (tz?: string | null) => { if (tz) TZ = tz; };
export const getTimezone = () => TZ;

export function inr(n: any) {
  const v = Number(n || 0);
  const neg = v < 0;
  const [int, dec] = Math.abs(v).toFixed(2).split(".");
  const last3 = int.slice(-3);
  const rest = int.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  const body = rest ? `${rest},${last3}` : last3;
  return `${neg ? "-" : ""}₹${body}${dec !== "00" ? `.${dec}` : ""}`;
}

const parts = (d: Date) => {
  try {
    const f = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
    return f.format(d).slice(0, 10);
  } catch {
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  }
};
export const todayISO = () => parts(new Date());
export const addDaysISO = (n: number) => parts(new Date(Date.now() + n * 86400000));
export const hourNow = () => {
  try {
    return Number(new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", hour12: false }).format(new Date()));
  } catch { return new Date().getHours(); }
};

export const minutesNow = () => {
  try {
    const t = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date());
    const [h, m] = t.split(":").map(Number);
    return (h % 24) * 60 + m;
  } catch { const d = new Date(); return d.getHours() * 60 + d.getMinutes(); }
};
export const toMin = (hhmm?: string) => { const [h, m] = String(hhmm || "0:0").split(":").map(Number); return h * 60 + (m || 0); };
export const daysUntil = (iso: string) => {
  const a = todayISO().split("-").map(Number); const b = String(iso).slice(0, 10).split("-").map(Number);
  return Math.round((Date.UTC(b[0], b[1] - 1, b[2]) - Date.UTC(a[0], a[1] - 1, a[2])) / 86400000);
};

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// "2026-10-19" → "19 Oct 2026" (pure calendar date, no tz shift)
export function fmtDate(iso?: string | null, opts: { weekday?: boolean; year?: boolean } = {}) {
  if (!iso) return "—";
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return String(iso);
  const dt = new Date(Date.UTC(y, m - 1, d));
  const wd = opts.weekday ? `${WD[dt.getUTCDay()]}, ` : "";
  return `${wd}${d} ${MON[m - 1]}${opts.year === false ? "" : ` ${y}`}`;
}

// ISO timestamp → "14 Oct, 4:20 pm" in the school timezone
export function fmtDateTime(iso?: string | null) {
  if (!iso) return "";
  try {
    return new Intl.DateTimeFormat("en-IN", { timeZone: TZ, day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true }).format(new Date(iso));
  } catch {
    return String(iso).slice(0, 16).replace("T", " ");
  }
}

export const fmtTime = (hhmm?: string) => {
  if (!hhmm) return "";
  const [h, m] = hhmm.split(":").map(Number);
  const ap = h >= 12 ? "pm" : "am";
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${ap}`;
};

export const DAY_SHORT: Record<string, string> = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };
export const DAY_LONG: Record<string, string> = { mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday", sun: "Sunday" };
export function todayKey() {
  const iso = todayISO();
  const [y, m, d] = iso.split("-").map(Number);
  return ["sun", "mon", "tue", "wed", "thu", "fri", "sat"][new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
}

export const fullName = (c: any) => `${c?.first_name || ""} ${c?.last_name || ""}`.trim();
export const classLabel = (c: any) => `${c?.class_name || ""}${c?.section ? ` ${c.section}` : ""}`.trim();
export const initials = (name?: string) =>
  (name || "S").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
