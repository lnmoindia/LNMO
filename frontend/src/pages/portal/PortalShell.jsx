import { useEffect, useState } from "react";
import api from "../../lib/api";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Bell, LogOut, Menu, MessageSquareWarning, Moon, Sun, UserCircle2 } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../context/ThemeContext";
import { useReportIssue } from "../../context/ReportIssue";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "../../components/ui/dropdown-menu";
import { BrandMark, brandVars } from "./useSchoolBrand";
import { PoweredBy } from "../../components/common/LnmoLogo";

// Shared parent/student layout: desktop sidebar, mobile bottom nav (4 + More), sticky top bar.
export default function PortalShell({ brand, label, nav, bottom, base, extra, query = "", testid, children }) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const { openReport } = useReportIssue();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [more, setMore] = useState(false);
  const current = nav.find((n) => pathname === `${base}/${n.key}` || pathname.startsWith(`${base}/${n.key}/`)) || nav[0];
  const to = (k) => `${base}/${k}${query}`;
  const signOut = async () => { await logout(); navigate("/login"); };
  const hasMessages = nav.some((n) => n.key === "messages");
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    if (!hasMessages) return undefined;
    const load = () => api.get("/chat/unread").then((r) => setUnread(r.data.unread || 0)).catch(() => {});
    load();
    const iv = setInterval(load, 30000);
    return () => clearInterval(iv);
  }, [hasMessages, pathname]);
  return (
    <div className="min-h-screen bg-[#f6f7f9] dark:bg-[#0B0F17] flex" style={brandVars(brand.color)} data-testid={testid}>
      <aside className="hidden md:flex w-60 flex-col shrink-0 sticky top-0 h-screen bg-white dark:bg-slate-900 border-r border-slate-200/80 dark:border-slate-800" data-testid="portal-sidebar">
        <div className="h-16 flex items-center gap-3 px-4 border-b border-slate-100 dark:border-slate-800">
          <BrandMark brand={brand} />
          <div className="min-w-0">
            <p className="font-heading font-bold text-sm leading-tight text-slate-900 dark:text-white line-clamp-2" data-testid="portal-school-name">{brand.name}</p>
            <p className="text-[10px] uppercase tracking-wider text-slate-400 mt-0.5">{label}</p>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto py-3 px-3 space-y-0.5">
          {nav.map((n) => (
            <NavLink key={n.key} to={to(n.key)} data-testid={`portal-nav-${n.key}`}
              className={({ isActive }) => `flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium transition-colors ${isActive ? "text-[var(--brand-ink)] dark:text-white bg-[var(--brand-soft)]" : "text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800"}`}>
              <n.icon size={16} /> {n.label}
              {n.key === "messages" && unread > 0 && <span className="ml-auto rounded-full bg-rose-500 text-white text-[10px] font-bold px-1.5" data-testid="portal-nav-messages-badge">{unread}</span>}
            </NavLink>
          ))}
        </nav>
        <PoweredBy className="px-5 py-3 border-t border-slate-100 dark:border-slate-800 text-[10px] text-slate-400" testid="portal-powered-by" />
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-16 flex items-center gap-2 px-3 md:px-6 bg-white/85 dark:bg-slate-900/85 backdrop-blur-xl border-b border-slate-200/80 dark:border-slate-800 sticky top-0 z-30">
          <div className="md:hidden"><BrandMark brand={brand} size="h-8 w-8" testid="portal-mobile-logo" /></div>
          <div className="min-w-0 flex-1">
            <p className="md:hidden text-[11px] font-semibold text-slate-500 truncate">{brand.name}</p>
            <h1 className="font-heading font-bold text-slate-900 dark:text-white truncate leading-tight" data-testid="portal-page-title">{current?.label}</h1>
          </div>
          {extra}
          <button onClick={() => navigate(to(unread ? "messages" : "notices"))} className="relative h-9 w-9 rounded-lg flex items-center justify-center text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" data-testid="portal-bell" aria-label={unread ? `${unread} unread messages` : "Notices"}>
            <Bell size={17} />
            {unread > 0 && <span className="absolute -top-0.5 -right-0.5 min-w-[17px] h-[17px] px-1 rounded-full bg-rose-500 text-white text-[10px] font-bold flex items-center justify-center" data-testid="portal-bell-badge">{unread}</span>}
          </button>
          <button onClick={toggle} className="h-9 w-9 rounded-lg flex items-center justify-center text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" data-testid="portal-theme-toggle" aria-label="Theme">
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="h-9 w-9 rounded-full flex items-center justify-center text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" data-testid="portal-profile-menu" aria-label="Account"><UserCircle2 size={20} /></button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuLabel className="truncate">{user?.name}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={openReport} data-testid="portal-report-btn"><MessageSquareWarning size={14} className="mr-2" /> Report an issue</DropdownMenuItem>
              <DropdownMenuItem onSelect={signOut} className="text-red-600 focus:text-red-600" data-testid="portal-logout-btn"><LogOut size={14} className="mr-2" /> Sign out</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>
        <main className="w-full max-w-5xl mx-auto px-3 sm:px-5 md:px-8 py-5 md:py-8 pb-28 md:pb-10 space-y-5">{children}</main>
        <PoweredBy className="md:hidden justify-center text-[10px] text-slate-400 pb-20" testid="portal-powered-by-mobile" />
      </div>

      <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl border-t border-slate-200 dark:border-slate-800 flex pb-[env(safe-area-inset-bottom)]" data-testid="portal-bottom-nav">
        {bottom.map((k) => {
          const n = nav.find((x) => x.key === k);
          return (
            <NavLink key={k} to={to(k)} data-testid={`portal-bnav-${k}`}
              className={({ isActive }) => `flex-1 flex flex-col items-center justify-center gap-0.5 py-2 min-h-[56px] text-[10px] font-semibold ${isActive ? "text-[var(--brand-ink)] dark:text-white" : "text-slate-400"}`}>
              <n.icon size={20} /> {n.short || n.label}
            </NavLink>
          );
        })}
        <button onClick={() => setMore(true)} className="flex-1 flex flex-col items-center justify-center gap-0.5 py-2 min-h-[56px] text-[10px] font-semibold text-slate-400" data-testid="portal-bnav-more"><Menu size={20} /> More</button>
      </nav>
      {more && (
        <div className="md:hidden fixed inset-0 z-40 flex items-end" data-testid="portal-more-sheet">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMore(false)} />
          <div className="relative w-full rounded-t-3xl bg-white dark:bg-slate-900 p-4 pb-8">
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-slate-300 dark:bg-slate-700" />
            <div className="grid grid-cols-3 gap-2.5">
              {nav.filter((n) => !bottom.includes(n.key)).map((n) => (
                <NavLink key={n.key} to={to(n.key)} onClick={() => setMore(false)} data-testid={`portal-more-${n.key}`}
                  className={({ isActive }) => `flex flex-col items-center justify-center gap-1.5 rounded-2xl border p-3 min-h-[72px] text-xs font-semibold ${isActive ? "border-[var(--brand)] bg-[var(--brand-soft)] text-[var(--brand-ink)] dark:text-white" : "border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300"}`}>
                  <n.icon size={20} /> {n.label}
                </NavLink>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export const PCard = ({ title, icon: Icon, right, children, testid, className = "" }) => (
  <section className={`rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-[0_1px_2px_rgba(15,23,42,.04),0_4px_16px_rgba(15,23,42,.04)] overflow-hidden ${className}`} data-testid={testid}>
    {title && (
      <div className="px-4 sm:px-5 py-3.5 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
        {Icon && <Icon size={16} className="text-[var(--brand-ink)] dark:text-[var(--brand)]" />}
        <h2 className="font-heading text-base font-bold text-slate-900 dark:text-slate-50">{title}</h2>
        {right && <span className="ml-auto text-xs text-slate-400">{right}</span>}
      </div>
    )}
    {children}
  </section>
);

export const PEmpty = ({ icon: Icon, text, testid }) => (
  <div className="px-5 py-10 flex flex-col items-center text-center gap-2" data-testid={testid}>
    {Icon && <div className="h-11 w-11 rounded-2xl bg-[var(--brand-soft)] text-[var(--brand-ink)] dark:text-[var(--brand)] flex items-center justify-center"><Icon size={20} /></div>}
    <p className="text-sm text-slate-500 max-w-xs">{text}</p>
  </div>
);
