"use client";

import { InstitutionRoleConsole } from "@/components/institution-console/institution-role-console";
import { MentorShell } from "@/components/mentor/mentor-shell";

/** Mentor console; the API derives reach from the caller's active mentor assignments. */
export default function MentorLayout({ children }: { children: React.ReactNode }) {
  return (
    <InstitutionRoleConsole requiredRole="MENTOR" loadingLabel="Loading mentor console…" Shell={MentorShell}>
      {children}
    </InstitutionRoleConsole>
  );
}
