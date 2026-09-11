"use client";

import { Suspense, useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import {
  PlatformAuthProvider,
  usePlatformAuth,
} from "@/hooks/use-platform-auth";
import { OwnerAuthProvider, useOwnerAuth } from "@/hooks/use-owner-auth";

/**
 * Platform console session gate — `app.shikshasync.me`.
 *
 * Every page under `(platform)` reads live data over an authenticated API, so
 * the console needs a session provider and a redirect for anonymous visitors.
 * Mirrors `app/admin/layout.tsx`, the pattern the institution admin console
 * uses.
 *
 * **Two different account types share this route group** and neither is a
 * superset of the other:
 *   - `platform_users` — Super Admin / Support / Sales / Finance (staff)
 *   - `platform_owners` — the paying customer who owns institutions
 * Both providers are mounted, and the gate accepts either, so an owner is not
 * bounced out of their own dashboard by the staff check (and vice versa).
 *
 * `?role=` still bypasses the gate: the design docs use it to preview a
 * platform role without a backend. It is a *rendering* preview only — the API
 * rejects any request whose bearer token is missing or of the wrong type with
 * 401/403, so previewing shows empty and error states, never another
 * account's data.
 */
export default function PlatformLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <PlatformAuthProvider>
      <OwnerAuthProvider>
        {/* `Gate` reads useSearchParams for `?role=`, which opts the tree into
            client rendering; without a boundary the prerender of every
            platform page fails at build time. */}
        <Suspense fallback={<ConsoleSpinner />}>
          <Gate>{children}</Gate>
        </Suspense>
      </OwnerAuthProvider>
    </PlatformAuthProvider>
  );
}

function ConsoleSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-3 text-muted-foreground">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        <span className="text-sm">Loading platform console…</span>
      </div>
    </div>
  );
}

function Gate({ children }: { children: React.ReactNode }) {
  const staff = usePlatformAuth();
  const owner = useOwnerAuth();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  // Design-doc preview mode — render without a session.
  const preview = params.get("role") !== null;

  // Either session grants access; each console's own pages then check the role.
  const isLoading = staff.isLoading || owner.isLoading;
  const isAuthenticated = staff.isAuthenticated || owner.isAuthenticated;

  useEffect(() => {
    if (!preview && !isLoading && !isAuthenticated) {
      router.replace(`/platform/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [preview, isLoading, isAuthenticated, pathname, router]);

  if (!preview && (isLoading || !isAuthenticated)) {
    return <ConsoleSpinner />;
  }

  return <>{children}</>;
}
