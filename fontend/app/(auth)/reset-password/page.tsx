import { headers } from "next/headers";
import type { Metadata } from "next";

import { BrandingPanel } from "@/components/auth/branding-panel";
import { MobileBanner } from "@/components/auth/mobile-banner";
import { ResetPasswordForm } from "@/components/auth/reset-password-form";
import { verifyResetToken } from "@/lib/auth";
import { resolveTenant } from "@/lib/tenant";

export const metadata: Metadata = {
  title: "Set a new password",
  description: "Choose a new password for your shikshasync.me account.",
  // A reset link must never be indexed or forwarded to a referrer.
  robots: { index: false, follow: false },
};

/**
 * C-PB-03 — Reset Password (`/reset-password?token=`).
 *
 * The page `/forgot-password` promises. Same palette and two-panel layout as
 * login and forgot-password (design §7).
 *
 * The token is validated on the **server** so an expired or absent one never
 * renders a form that cannot succeed. Preview both dead ends without a
 * backend: `?token=expired-demo` and `/reset-password` with no token at all.
 */
export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ tenant?: string; token?: string }>;
}) {
  const [headerList, params] = await Promise.all([headers(), searchParams]);
  const tenant = await resolveTenant(headerList.get("host"), params.tenant);
  const token = typeof params.token === "string" ? params.token : "";
  const state = await verifyResetToken(token);

  return (
    <div className="flex min-h-screen flex-col bg-[#F8FAFC] lg:flex-row">
      <BrandingPanel />
      <MobileBanner />

      <main className="flex flex-1 items-start justify-center bg-white p-6 lg:items-center lg:bg-[#F8FAFC] lg:p-10">
        <div className="w-full max-w-[400px] animate-fade-up py-4 lg:py-0">
          <ResetPasswordForm tenant={tenant} token={token} state={state} />

          <p className="mt-6 text-center text-[11px] leading-relaxed text-[#475569]">
            Reset links expire in 30 minutes · All requests are audited
          </p>
        </div>
      </main>
    </div>
  );
}
