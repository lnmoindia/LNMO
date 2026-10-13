import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Menu, X, Moon, Sun, LogOut, ChevronDown, Search, MessageSquareWarning } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../context/ThemeContext";
import { useReportIssue } from "../../context/ReportIssue";
import { ScopeChip } from "./ScopeChip";
import CommandPalette from "../common/CommandPalette";
import NotificationBell from "../common/NotificationBell";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "../ui/dropdown-menu";

const SidebarNav = ({ nav, onNavigate, badges = {} }) => (
  <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
    {nav.map((group) => (
      <div key={group.group}>
        <p className="px-3 mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{group.group}</p>
        <div className="space-y-0.5">
          {group.items.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={onNavigate}
              data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors duration-150 ${
                  isActive
                    ? "bg-indigo-600 text-white font-medium"
                    : "text-slate-400 hover:text-white hover:bg-slate-800"
                }`
              }
            >
              <item.icon size={16} strokeWidth={1.8} />
              {item.label}
              {badges[item.path] > 0 && (
                <span className="ml-auto inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-rose-500 text-white text-[10px] font-bold" data-testid="nav-badge-issues">{badges[item.path]}</span>
              )}
            </NavLink>
          ))}
        </div>
      </div>
    ))}
  </nav>
);

export default function AppShell({ nav, consoleLabel }) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const { openReport } = useReportIssue();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [badges, setBadges] = useState({});

  useEffect(() => {
    if (user?.role === "platform_admin") {
      import("../../lib/api").then(({ default: api }) =>
        api.get("/support/issues/stats")
          .then(({ data }) => setBadges({ "/platform/issues": data.open_issues }))
          .catch(() => {}));
    }
  }, [user?.role]);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const sidebar = (
    <div className="flex h-full w-64 flex-col bg-slate-950 border-r border-slate-800">
      <div className="flex items-center gap-3 px-5 h-16 border-b border-slate-800/70 shrink-0">
        <div className="h-8 w-8 rounded-lg bg-indigo-600 flex items-center justify-center font-heading font-bold text-white text-sm">L</div>
        <div>
          <p className="font-heading font-bold text-white leading-none tracking-tight">LNMO</p>
          <p className="text-[10px] uppercase tracking-wider text-slate-500 mt-1">{consoleLabel}</p>
        </div>
      </div>
      <SidebarNav nav={nav} onNavigate={() => setMobileOpen(false)} badges={badges} />
      {user?.is_principal && (
        <div className="px-5 py-3 border-t border-slate-800/70 shrink-0">
          <ScopeChip user={user} variant="dark" />
        </div>
      )}
      {user?.institution_name && (
        <div className="px-5 py-3 border-t border-slate-800/70 shrink-0">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">Institution</p>
          <p className="text-sm text-slate-300 truncate" data-testid="sidebar-institution-name">{user.institution_name}</p>
        </div>
      )}
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#0B0F17]">
      <aside className="hidden lg:block fixed inset-y-0 left-0 z-30">{sidebar}</aside>
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-40 flex">
          <div className="relative z-10">{sidebar}</div>
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
          <button className="absolute top-4 left-[17rem] z-20 text-white" onClick={() => setMobileOpen(false)} data-testid="mobile-sidebar-close">
            <X size={20} />
          </button>
        </div>
      )}

      <div className="lg:pl-64 flex flex-col min-h-screen">
        <header className="sticky top-0 z-20 h-16 flex items-center gap-3 px-4 md:px-6 border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl">
          <button className="lg:hidden text-slate-600 dark:text-slate-300" onClick={() => setMobileOpen(true)} data-testid="mobile-sidebar-toggle">
            <Menu size={20} />
          </button>
          <div className="flex-1 flex items-center">
            <button
              onClick={() => setPaletteOpen(true)}
              data-testid="command-palette-trigger"
              className="hidden md:flex items-center gap-2 h-9 w-64 rounded-lg border border-slate-200 dark:border-slate-700 px-3 text-sm text-slate-400 hover:border-slate-300 dark:hover:border-slate-600 transition-colors"
            >
              <Search size={14} /> Search…
              <kbd className="ml-auto text-[10px] font-mono border rounded px-1 py-0.5 border-slate-200 dark:border-slate-700 text-slate-400">⌘K</kbd>
            </button>
            <button
              onClick={() => setPaletteOpen(true)}
              data-testid="command-palette-trigger-mobile"
              className="md:hidden h-9 w-9 rounded-lg flex items-center justify-center text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              <Search size={17} />
            </button>
          </div>
          <button
            onClick={toggle}
            data-testid="theme-toggle-btn"
            className="h-9 w-9 rounded-lg flex items-center justify-center text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <NotificationBell />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-2 rounded-lg pl-1.5 pr-2 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors" data-testid="user-menu-trigger">
                <div className="h-7 w-7 rounded-full bg-indigo-600 text-white text-xs font-semibold flex items-center justify-center overflow-hidden">
                  {user?.has_photo
                    ? <img src={`${process.env.REACT_APP_BACKEND_URL}/api/users/${user.id}/photo`} alt="" className="h-full w-full object-cover" data-testid="sidebar-avatar" />
                    : (user?.name || "?").charAt(0).toUpperCase()}
                </div>
                <span className="hidden md:block text-sm text-slate-700 dark:text-slate-200 max-w-[140px] truncate">{user?.name}</span>
                <ChevronDown size={14} className="text-slate-400" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel>
                <p className="text-sm font-medium">{user?.name}</p>
                <p className="text-xs text-muted-foreground font-normal">{user?.email}</p>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={openReport} data-testid="menu-report-issue">
                <MessageSquareWarning size={14} className="mr-2" /> Report an issue
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleLogout} data-testid="logout-btn" className="text-red-600 focus:text-red-600">
                <LogOut size={14} className="mr-2" /> Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>
        <main className="flex-1 p-4 md:p-8">
          <Outlet />
        </main>
      </div>
      <CommandPalette open={paletteOpen} setOpen={setPaletteOpen} nav={nav} />
    </div>
  );
}
