"use client";

import {
  AlertTriangle,
  ArrowLeftRight,
  BookOpen,
  LayoutDashboard,
  Megaphone,
  NotebookPen,
  Users,
  UsersRound,
} from "lucide-react";

import {
  InstitutionConsoleShell,
  type InstitutionConsoleNavItem,
} from "@/components/institution-console/institution-console-shell";
import { useInstitutionAuth } from "@/hooks/use-institution-auth";

/** Mentor console navigation — scope is derived server-side from mentor assignments. */
const NAVIGATION: InstitutionConsoleNavItem[] = [
  { label: "Dashboard", href: "/mentor/dashboard", icon: LayoutDashboard },
  { label: "My mentees", href: "/mentor/mentees", icon: Users },
  { label: "At-risk alerts", href: "/mentor/alerts", icon: AlertTriangle },
  { label: "Mentoring log", href: "/mentor/notes", icon: NotebookPen },
  { label: "Project teams", href: "/mentor/teams", icon: UsersRound },
  { label: "Classes", href: "/mentor/classes", icon: BookOpen },
  { label: "Notices", href: "/mentor/notices", icon: Megaphone },
];

export function MentorShell({ children }: { children: React.ReactNode }) {
  const { hasRole } = useInstitutionAuth();
  // Most mentors also teach; surface the other console instead of forcing a re-login.
  const navigation = hasRole("TEACHER")
    ? [...NAVIGATION, { label: "Teacher console", href: "/teacher/dashboard", icon: ArrowLeftRight }]
    : NAVIGATION;
  return (
    <InstitutionConsoleShell
      navigation={navigation}
      consoleTitle="Mentor console"
      headerTitle="Mentees, attendance and mentoring log"
      roleLabel="Mentor"
    >
      {children}
    </InstitutionConsoleShell>
  );
}
