import { headers } from "next/headers";

import { DashboardShell } from "./shell";
import { roleChip } from "@/lib/roles";
import { getSession } from "@/lib/session";
import { resolveTenant } from "@/lib/tenant";
import type { InstitutionRole } from "@/types/auth";
import type { DashboardSession } from "@/types/dashboard";

/**
 * Server-side wrapper that resolves tenant + session and renders the shell.
 * Shared by every institution page so the setup exists in exactly one place.
 */
export async function InstitutionShell({
  search,
  children,
}: {
  search: { tenant?: string; role?: string; roles?: string; modules?: string };
  children: (ctx: {
    session: DashboardSession;
    role: InstitutionRole;
  }) => React.ReactNode;
}) {
  const headerList = await headers();
  const tenant = await resolveTenant(headerList.get("host"), search.tenant);
  const session = getSession(null, search);
  const role = session.roles[0]!;

  return (
    <DashboardShell
      role={role}
      enabledModules={session.enabledModules}
      tenantName={tenant.isPlatform ? "ABC College" : tenant.name}
      tenantHost={tenant.isPlatform ? "abc-college.shikshasync.me" : tenant.host}
      userName={session.user.name}
      roleChip={roleChip(role)}
      academicYear={session.academicYear}
      unread={0}
    >
      {children({ session, role })}
    </DashboardShell>
  );
}
