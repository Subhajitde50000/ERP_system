"use client";

import {
  AlertTriangle,
  BookOpen,
  CalendarDays,
  CalendarPlus,
  LayoutDashboard,
  Megaphone,
  RefreshCw,
  Repeat,
  UserRoundCheck,
  Users,
} from "lucide-react";

import {
  InstitutionConsoleShell,
  type InstitutionConsoleNavItem,
} from "@/components/institution-console/institution-console-shell";

/** C-AC-01 … C-AC-08 navigation for an institution-wide coordinator. */
const NAVIGATION: InstitutionConsoleNavItem[] = [
  { label: "Dashboard", href: "/coordinator/dashboard", icon: LayoutDashboard },
  { label: "Student records", href: "/coordinator/students", icon: Users },
  { label: "Import students", href: "/coordinator/import", icon: Users },
  { label: "Mentors", href: "/coordinator/mentors", icon: UserRoundCheck },
  { label: "Subjects", href: "/coordinator/subjects", icon: BookOpen },
  { label: "Timetable builder", href: "/coordinator/timetable", icon: CalendarDays },
  { label: "Conflict checker", href: "/coordinator/timetable/conflicts", icon: AlertTriangle },
  { label: "Substitutions", href: "/coordinator/substitutions", icon: Repeat },
  { label: "Add substitution", href: "/coordinator/substitutions/new", icon: RefreshCw },
  { label: "Academic calendar", href: "/coordinator/calendar", icon: CalendarPlus },
  { label: "Notice feed", href: "/coordinator/notices", icon: Megaphone },
  { label: "Post notice", href: "/coordinator/notices/new", icon: Megaphone },
];

export function CoordinatorShell({ children }: { children: React.ReactNode }) {
  return (
    <InstitutionConsoleShell
      navigation={NAVIGATION}
      consoleTitle="Coordinator console"
      headerTitle="Academic operations"
      roleLabel="Academic Coordinator"
    >
      {children}
    </InstitutionConsoleShell>
  );
}
