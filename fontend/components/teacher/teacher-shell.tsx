"use client";

import {
  ArrowLeftRight,
  BookOpen,
  CalendarDays,
  ClipboardCheck,
  Database,
  FileSpreadsheet,
  LayoutDashboard,
  Megaphone,
  MessageSquare,
  PenSquare,
  Repeat2,
  UserRoundCheck,
  Users,
  Video,
} from "lucide-react";

import {
  InstitutionConsoleShell,
  type InstitutionConsoleNavItem,
} from "@/components/institution-console/institution-console-shell";
import { useInstitutionAuth } from "@/hooks/use-institution-auth";

/** C-TC-01 … C-TC-22 navigation for the teaching-scope teacher console. */
const NAVIGATION: InstitutionConsoleNavItem[] = [
  { label: "Dashboard", href: "/teacher/dashboard", icon: LayoutDashboard },
  { label: "Online classes", href: "/teacher/online-classes", icon: Video },
  { label: "My schedule", href: "/teacher/schedule", icon: CalendarDays },
  { label: "Mark attendance", href: "/teacher/attendance/mark", icon: PenSquare },
  { label: "Attendance sessions", href: "/teacher/attendance/sessions", icon: ClipboardCheck },
  { label: "Leave requests", href: "/teacher/attendance/leaves", icon: UserRoundCheck },
  { label: "Examinations", href: "/teacher/examinations", icon: FileSpreadsheet },
  { label: "Question Bank", href: "/teacher/question-bank", icon: Database },
  { label: "Assignments", href: "/teacher/assignments", icon: Repeat2 },
  { label: "Project Teams", href: "/teacher/teams", icon: Users },
  { label: "Content", href: "/teacher/content", icon: BookOpen },
  { label: "Notices", href: "/teacher/notices", icon: Megaphone },
  { label: "Discussion", href: "/teacher/discussion", icon: MessageSquare },
];

export function TeacherShell({ children }: { children: React.ReactNode }) {
  const { hasRole } = useInstitutionAuth();
  // Teachers who also mentor get a direct hop to their mentee console.
  const navigation = hasRole("MENTOR")
    ? [...NAVIGATION, { label: "Mentor console", href: "/mentor/dashboard", icon: ArrowLeftRight }]
    : NAVIGATION;
  return (
    <InstitutionConsoleShell
      navigation={navigation}
      consoleTitle="Teacher console"
      headerTitle="Classes, exams and assignments"
      roleLabel="Teacher"
    >
      {children}
    </InstitutionConsoleShell>
  );
}
