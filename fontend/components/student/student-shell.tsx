"use client";

import {
  BookOpen,
  CalendarDays,
  ClipboardCheck,
  FileSpreadsheet,
  GraduationCap,
  IndianRupee,
  LayoutDashboard,
  Megaphone,
  MessageSquare,
  MessageSquareMore,
  Repeat2,
  UserRound,
  Users,
  Video,
} from "lucide-react";

import {
  InstitutionConsoleShell,
  type InstitutionConsoleNavItem,
} from "@/components/institution-console/institution-console-shell";

/** C-ST-01 … C-ST-20 navigation; everything is scoped to the signed-in student. */
const NAVIGATION: InstitutionConsoleNavItem[] = [
  { label: "Dashboard", href: "/student/dashboard", icon: LayoutDashboard },
  { label: "Online classes", href: "/student/online-classes", icon: Video },
  { label: "Profile", href: "/student/profile", icon: UserRound },
  { label: "Attendance", href: "/student/attendance", icon: ClipboardCheck },
  { label: "Timetable", href: "/student/timetable", icon: CalendarDays },
  { label: "Examinations", href: "/student/examinations", icon: FileSpreadsheet },
  { label: "Assignments", href: "/student/assignments", icon: Repeat2 },
  { label: "Project Teams", href: "/student/teams", icon: Users },
  { label: "Content", href: "/student/content", icon: BookOpen },
  { label: "Results", href: "/student/results", icon: GraduationCap },
  { label: "Notices", href: "/student/notices", icon: Megaphone },
  { label: "Discussion", href: "/student/discussion", icon: MessageSquare },
  { label: "Fees", href: "/student/fees", icon: IndianRupee },
  { label: "Feedback", href: "/student/feedback", icon: MessageSquareMore },
];

export function StudentShell({ children }: { children: React.ReactNode }) {
  return (
    <InstitutionConsoleShell
      navigation={NAVIGATION}
      consoleTitle="Student console"
      headerTitle="My learning"
      roleLabel="Student"
    >
      {children}
    </InstitutionConsoleShell>
  );
}
