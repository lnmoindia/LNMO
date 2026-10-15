// School brand palette built from the school's primary colour (fallback calm blue-grey).
import { absUrl } from "@/src/lib/api";

export const NEUTRAL = "#3F6B8A";
export type Brand = {
  name: string; logo: string; tagline: string;
  color: string; ink: string; soft: string; line: string; onColor: string;
};

const hex = (c: string) => {
  const m = c.replace("#", "");
  const v = m.length === 3 ? m.split("").map((x) => x + x).join("") : m;
  return [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16));
};
const toHex = (rgb: number[]) => `#${rgb.map((x) => Math.round(Math.max(0, Math.min(255, x))).toString(16).padStart(2, "0")).join("")}`;
export const mix = (a: string, b: string, t: number) => {
  const A = hex(a); const B = hex(b);
  return toHex(A.map((x, i) => x * t + B[i] * (1 - t)));
};
const lum = (c: string) => {
  const [r, g, b] = hex(c).map((x) => { const s = x / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

export function makeBrand(raw: any, school: any): Brand {
  let color = raw?.primary_color || NEUTRAL;
  if (!/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(color)) color = NEUTRAL;
  const light = lum(color) > 0.4;
  return {
    name: raw?.name || school?.name || "",
    logo: absUrl(raw?.logo_url || school?.logo_url),
    tagline: raw?.tagline || school?.tagline || "",
    color,
    ink: mix(color, "#0F172A", light ? 0.55 : 0.78),
    soft: mix(color, "#FFFFFF", 0.12),
    line: mix(color, "#FFFFFF", 0.35),
    onColor: light ? "#1A1206" : "#FFFFFF",
  };
}
