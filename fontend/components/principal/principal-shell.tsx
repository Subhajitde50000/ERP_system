"use client";

import {
  BarChart3,
  CalendarDays,
  ClipboardCheck,
  FileCheck2,
  FileSpreadsheet,
  LayoutDashboard,
  Megaphone,
  MessageSquareMore,
  Users,
  GraduationCap,
} from "lucide-react";

import {
  InstitutionConsoleShell,
  type InstitutionConsoleNavItem,
} from "@/components/institution-console/institution-console-shell";

/** The documented C-PR navigation; every item has a live Principal API page. */
const NAVIGATION: InstitutionConsoleNavItem[] = [
  { label: "Dashboard", href: "/principal/dashboard", icon: LayoutDashboard },
  { label: "Attendance", href: "/principal/attendance", icon: ClipboardCheck },
  { label: "Examinations", href: "/principal/examinations", icon: FileSpreadsheet },
  { label: "Results", href: "/principal/results", icon: FileCheck2 },
  { label: "Staff", href: "/principal/staff", icon: Users },
  { label: "Students", href: "/principal/students", icon: GraduationCap },
  { label: "Notice Board", href: "/principal/notices", icon: Megaphone },
  { label: "Timetable", href: "/principal/timetable", icon: CalendarDays },
  { label: "Feedback", href: "/principal/feedback", icon: MessageSquareMore },
  { label: "Reports", href: "/principal/reports", icon: BarChart3 },
];

export function PrincipalShell({ children }: { children: React.ReactNode }) {
  return (
    <InstitutionConsoleShell
      navigation={NAVIGATION}
      consoleTitle="Principal console"
      headerTitle="Institutional academic oversight"
      roleLabel="Principal"
    >
      {children}
    </InstitutionConsoleShell>
  );
}
