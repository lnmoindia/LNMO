import {
  LayoutDashboard, Building2, CreditCard, ScrollText, GraduationCap,
  Users, UserCog, School, Rows3, BookOpen, Settings, CalendarRange, UserPlus,
  ClipboardList, CalendarCheck, FileSpreadsheet, Layers, Table2, Megaphone, UserX, CalendarClock, BookMarked, ClipboardCheck, Activity, MessageSquare, Sparkles, ArrowRightLeft, Bug, LifeBuoy, Wallet,
} from "lucide-react";

export const platformNav = [
  {
    group: "Overview",
    items: [{ label: "Dashboard", path: "/platform/dashboard", icon: LayoutDashboard }],
  },
  {
    group: "Tenancy",
    items: [
      { label: "Institutions", path: "/platform/institutions", icon: Building2 },
    ],
  },
  {
    group: "Commercial",
    items: [{ label: "Plans", path: "/platform/plans", icon: CreditCard }],
  },
  {
    group: "Content",
    items: [{ label: "LNMO Library", path: "/platform/library", icon: BookMarked }],
  },
  {
    group: "Support",
    items: [{ label: "Issues", path: "/platform/issues", icon: Bug }],
  },
  {
    group: "Messaging",
    items: [{ label: "Communication", path: "/platform/communication", icon: MessageSquare }],
  },
  {
    group: "Governance",
    items: [
      { label: "Audit Log", path: "/platform/audit", icon: ScrollText },
      { label: "Settings", path: "/platform/settings", icon: Settings },
    ],
  },
];

export const institutionNav = [
  {
    group: "Main",
    items: [{ label: "Dashboard", path: "/app/dashboard", icon: LayoutDashboard }],
  },
  {
    group: "People",
    items: [
      { label: "Students", path: "/app/students", icon: GraduationCap },
      { label: "Teachers", path: "/app/teachers", icon: Users },
      { label: "Users", path: "/app/users", icon: UserCog },
    ],
  },
  {
    group: "Academics",
    items: [
      { label: "Class Hub", path: "/app/class-hub", icon: School },
      { label: "Subjects", path: "/app/subjects", icon: BookOpen },
      { label: "Academic Years", path: "/app/academic-years", icon: CalendarRange },
      { label: "Academic Units", path: "/app/academic-units", icon: Layers },
      { label: "Promotion", path: "/app/promotion", icon: ArrowRightLeft },
    ],
  },
  {
    group: "Finance",
    items: [
      { label: "Fees", path: "/app/fees", icon: Wallet },
      { label: "Fee Defaulters", path: "/app/fees?tab=defaulters", icon: Wallet },
    ],
  },
  {
    group: "Operations",
    items: [
      { label: "Timetable", path: "/app/timetable", icon: Table2 },
      { label: "Substitutions", path: "/app/substitutions", icon: UserX },
      { label: "Attendance", path: "/app/attendance", icon: CalendarCheck },
      { label: "Assessments", path: "/app/assessments", icon: FileSpreadsheet },
      { label: "Exams", path: "/app/exams", icon: CalendarClock },
      { label: "Homework Monitor", path: "/app/homework-monitor", icon: Activity },
      { label: "AI Tutor", path: "/app/ai-tutor", icon: Sparkles },
      { label: "Notices", path: "/app/notices", icon: Megaphone },
    ],
  },
  {
    group: "Administration",
    items: [
      { label: "Communication", path: "/app/communication", icon: MessageSquare },
      { label: "Audit Log", path: "/app/audit", icon: ScrollText },
      { label: "Support", path: "/app/support", icon: LifeBuoy },
      { label: "Settings", path: "/app/settings", icon: Settings },
    ],
  },
];

export const teacherNav = [
  {
    group: "Main",
    items: [{ label: "Dashboard", path: "/teacher/dashboard", icon: LayoutDashboard }],
  },
  {
    group: "Teaching",
    items: [
      { label: "My Class", path: "/teacher/my-class", icon: School },
      { label: "My Students", path: "/teacher/students", icon: GraduationCap },
      { label: "My Timetable", path: "/teacher/timetable", icon: Table2 },
      { label: "My Substitutions", path: "/teacher/substitutions", icon: UserX },
      { label: "Marks Entry", path: "/teacher/marks", icon: FileSpreadsheet },
      { label: "Homework", path: "/teacher/homework", icon: BookMarked },
      { label: "Assignments", path: "/teacher/assignments", icon: ClipboardCheck },
      { label: "Notices", path: "/teacher/notices", icon: Megaphone },
      { label: "AI Tutor", path: "/teacher/ai-tutor", icon: Sparkles },
      { label: "Attendance", path: "/teacher/attendance", icon: CalendarCheck },
      { label: "Fee Defaulters", path: "/teacher/fee-defaulters", icon: Wallet },
      { label: "My Profile", path: "/teacher/profile", icon: UserCog },
    ],
  },
];

// A principal is an elevated teacher: their sidebar MERGES their personal teacher workspace with
// scoped institution-management pages (one experience, no role switcher). Excluded admin-only areas
// (Settings, Academic Years, Divisions, Users, Setup, Principal management) are intentionally absent.
export const buildPrincipalNav = () => [
  {
    group: "Workspace",
    items: [{ label: "My Dashboard", path: "/teacher/dashboard", icon: LayoutDashboard }],
  },
  {
    group: "Principal",
    items: [
      { label: "Overview", path: "/app/dashboard", icon: LayoutDashboard },
      { label: "Class Hub", path: "/app/class-hub", icon: School },
      { label: "Students", path: "/app/students", icon: GraduationCap },
      { label: "Teachers", path: "/app/teachers", icon: Users },
      { label: "Subjects", path: "/app/subjects", icon: BookOpen },
      { label: "Promotion", path: "/app/promotion", icon: ArrowRightLeft },
      { label: "Fees", path: "/app/fees", icon: Wallet },
      { label: "Fee Defaulters", path: "/app/fees?tab=defaulters", icon: Wallet },
      { label: "Timetable", path: "/app/timetable", icon: Table2 },
      { label: "Substitutions", path: "/app/substitutions", icon: UserX },
      { label: "Attendance", path: "/app/attendance", icon: CalendarCheck },
      { label: "Assessments", path: "/app/assessments", icon: FileSpreadsheet },
      { label: "Homework Monitor", path: "/app/homework-monitor", icon: Activity },
      { label: "AI Tutor", path: "/app/ai-tutor", icon: Sparkles },
      { label: "Notices", path: "/app/notices", icon: Megaphone },
      { label: "Support", path: "/app/support", icon: LifeBuoy },
      { label: "Audit Log", path: "/app/audit", icon: ScrollText },
    ],
  },
  {
    group: "Teaching",
    items: [
      { label: "My Class", path: "/teacher/my-class", icon: School },
      { label: "My Students", path: "/teacher/students", icon: GraduationCap },
      { label: "My Timetable", path: "/teacher/timetable", icon: Table2 },
      { label: "My Substitutions", path: "/teacher/substitutions", icon: UserX },
      { label: "Marks Entry", path: "/teacher/marks", icon: FileSpreadsheet },
      { label: "Homework", path: "/teacher/homework", icon: BookMarked },
      { label: "Assignments", path: "/teacher/assignments", icon: ClipboardCheck },
      { label: "Notices", path: "/teacher/notices", icon: Megaphone },
      { label: "AI Tutor", path: "/teacher/ai-tutor", icon: Sparkles },
      { label: "My Attendance", path: "/teacher/attendance", icon: CalendarCheck },
      { label: "My Profile", path: "/teacher/profile", icon: UserCog },
    ],
  },
];
