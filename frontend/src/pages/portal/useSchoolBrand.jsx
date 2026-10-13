import { useEffect, useState } from "react";
import api from "../../lib/api";

const API = process.env.REACT_APP_BACKEND_URL;
export const NEUTRAL = "#3f6b8a";
export const absUrl = (u) => (u && u.startsWith("/api") ? `${API}${u}` : u);

const setFavicon = (href) => {
  let link = document.querySelector("link[rel~='icon']");
  if (!link) { link = document.createElement("link"); link.rel = "icon"; document.head.appendChild(link); }
  if (!link.dataset.orig) link.dataset.orig = link.href || "/favicon.ico";
  link.href = href || link.dataset.orig;
};

// School brand for parent/student/teacher portals: name, logo, accent colour; sets tab title + favicon.
export function useSchoolBrand(label) {
  const [brand, setBrand] = useState(null);
  useEffect(() => {
    api.get("/me/branding").then((r) => setBrand(r.data)).catch(() => setBrand({}));
  }, []);
  useEffect(() => {
    if (!brand) return undefined;
    const prevTitle = document.title;
    if (brand.name) document.title = `${brand.name} · ${label}`;
    if (brand.logo_url) setFavicon(absUrl(brand.logo_url));
    return () => { document.title = prevTitle; setFavicon(null); };
  }, [brand, label]);
  return {
    loaded: Boolean(brand),
    name: brand?.name || "",
    logo: absUrl(brand?.logo_url),
    tagline: brand?.tagline || "",
    color: brand?.primary_color || NEUTRAL,
  };
}

export const brandVars = (color) => ({
  "--brand": color,
  "--brand-ink": `color-mix(in srgb, ${color} 72%, #0f172a)`,
  "--brand-soft": `color-mix(in srgb, ${color} 12%, transparent)`,
  "--brand-line": `color-mix(in srgb, ${color} 35%, transparent)`,
});

export const BrandMark = ({ brand, size = "h-9 w-9", testid = "school-logo" }) => (
  brand.logo
    ? <img src={brand.logo} alt="" className={`${size} rounded-xl object-cover bg-white ring-1 ring-black/5 shrink-0`} data-testid={testid} />
    : (
      <div className={`${size} rounded-xl flex items-center justify-center font-heading font-bold text-white text-sm shrink-0`} style={{ background: "var(--brand)" }} data-testid={`${testid}-initials`}>
        {(brand.name || "S").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase()}
      </div>
    )
);
