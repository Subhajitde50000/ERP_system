import { headers } from "next/headers";
import type { Metadata } from "next";

import { BrandingPanel } from "@/components/auth/branding-panel";
import { ForgotPasswordForm } from "@/components/auth/forgot-password-form";
import { MobileBanner } from "@/components/auth/mobile-banner";
import { resolveTenant } from "@/lib/tenant";

export const metadata: Metadata = {
  title: "Reset password",
  description: "Reset your shikshasync.me account password.",
};

/** Forgot password — same palette and layout as login (design §7). */
export default async function ForgotPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ tenant?: string }>;
}) {
  const [headerList, params] = await Promise.all([headers(), searchParams]);
  const tenant = await resolveTenant(headerList.get("host"), params.tenant);

  return (
    <div className="flex min-h-screen flex-col bg-[#F8FAFC] lg:flex-row">
      <BrandingPanel />
      <MobileBanner />

      <main className="flex flex-1 items-start justify-center bg-white p-6 lg:items-center lg:bg-[#F8FAFC] lg:p-10">
        <div className="w-full max-w-[400px] animate-fade-up py-4 lg:py-0">
          <ForgotPasswordForm tenant={tenant} />

          <p className="mt-6 text-center text-[11px] leading-relaxed text-[#475569]">
            Reset links expire in 30 minutes · All requests are audited
          </p>
        </div>
      </main>
    </div>
  );
}
