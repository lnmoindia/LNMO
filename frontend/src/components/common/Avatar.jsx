import { useState } from "react";

const SIZES = { xs: "h-6 w-6 text-[10px]", sm: "h-8 w-8 text-xs", md: "h-10 w-10 text-sm", lg: "h-14 w-14 text-lg", xl: "h-20 w-20 text-2xl" };
const initials = (name) => (name || "?").trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";

export const Avatar = ({ src, name, size = "sm", className = "", testid }) => {
  const [broken, setBroken] = useState(false);
  return (
    <span className={`${SIZES[size] || SIZES.sm} rounded-full shrink-0 overflow-hidden inline-flex items-center justify-center font-bold bg-[var(--brand-soft,#e0e7ff)] text-[var(--brand-ink,#3730a3)] ring-2 ring-white/70 dark:ring-slate-900 ${className}`} data-testid={testid}>
      {src && !broken ? <img src={src} alt={name || ""} className="h-full w-full object-cover" onError={() => setBroken(true)} /> : initials(name)}
    </span>
  );
};

export default Avatar;
