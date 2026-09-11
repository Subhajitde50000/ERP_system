import { headers } from "next/headers";
import { redirect } from "next/navigation";
import type { Metadata } from "next";

import { BrandingPanel } from "@/components/auth/branding-panel";
import { LoginForm } from "@/components/auth/login-form";
import { MobileBanner } from "@/components/auth/mobile-banner";
import { resolveTenant } from "@/lib/tenant";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to your shikshasync.me institution account.",
};

/**
 * Login page — shikshasync.me ERP + LMS
 * Split-screen layout per login_page_design.md §5.
 *
 * The tenant is resolved server-side from the Host header so the correct
 * institution badge is in the first paint (no flash of the wrong brand).
 * Locally, append ?tenant=abc-college to preview a specific institution.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ tenant?: string }>;
}) {
  const [headerList, params] = await Promise.all([headers(), searchParams]);
  const tenant = await resolveTenant(headerList.get("host"), params.tenant);

  /*
   * `shikshasync.me` (the apex domain) and bare localhost resolve to no institution.
   * Under the account-holder model, `shikshasync.me/login` is the *owner* platform
   * login — the door Rahul uses to manage every institution he owns. (Staff
   * — Super Admin, Support, Sales — still sign in at `/platform/login`, reached
   * in production by rewriting `app.shikshasync.me/login`.)
   *
   * Previously this redirected to the staff console, but that door is for the
   * platform's own employees, not for customers. Send apex-domain visitors to
   * their account login instead. Institution members still sign in at their
   * own subdomain, e.g. `green.shikshasync.me/login`.
   */
  if (tenant.isPlatform) redirect("/account/login");

  return (
    <div className="flex min-h-screen flex-col bg-[#F8FAFC] lg:flex-row">
      <BrandingPanel />
      <MobileBanner />

      <main className="flex flex-1 items-start justify-center bg-white p-6 lg:items-center lg:bg-[#F8FAFC] lg:p-10">
        <div className="w-full max-w-[400px] animate-fade-up py-4 lg:py-0">
          <LoginForm tenant={tenant} />

          <p className="mt-6 text-center text-[11px] leading-relaxed text-[#475569]">
            Protected by tenant isolation · All logins are audited ·{" "}
            <span className="font-medium text-[#0F172A]">v0.1.0</span>
          </p>
        </div>
      </main>
    </div>
  );
}
