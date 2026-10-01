"use client";

import {
  BookOpen,
  Building2,
  CalendarRange,
  LayoutDashboard,
  MessageSquareMore,
  Puzzle,
  Settings,
  UserRound,
  Users,
} from "lucide-react";

import {
  InstitutionConsoleShell,
  type InstitutionConsoleNavItem,
} from "@/components/institution-console/institution-console-shell";

/** Real institution-admin navigation, rendered by the shared console shell. */
const NAVIGATION: InstitutionConsoleNavItem[] = [
  { label: "Dashboard", href: "/admin/dashboard", icon: LayoutDashboard },
  { label: "Academic Years", href: "/admin/academic-years", icon: CalendarRange },
  { label: "Departments", href: "/admin/departments", icon: Building2 },
  { label: "Classes", href: "/admin/classes", icon: BookOpen },
  { label: "Subjects", href: "/admin/subjects", icon: BookOpen },
  { label: "Staff", href: "/admin/staff", icon: Users },
  { label: "Students", href: "/admin/students", icon: Users },
  // C-IA-12: the grant side of the parent portal — who may see which child, and how much.
  { label: "Guardians", href: "/admin/guardian-links", icon: UserRound },
  { label: "Modules", href: "/admin/modules", icon: Puzzle },
  { label: "Feedback", href: "/admin/feedback", icon: MessageSquareMore },
  { label: "Settings", href: "/admin/settings", icon: Settings },
  { label: "Profile", href: "/admin/profile", icon: UserRound },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  return (
    <InstitutionConsoleShell
      navigation={NAVIGATION}
      consoleTitle="Admin console"
      headerTitle="Institution administration"
      roleLabel="Institution Admin"
    >
      {children}
    </InstitutionConsoleShell>
  );
}
