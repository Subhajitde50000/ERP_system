import type { Metadata } from "next";

import { BrandingPanel } from "@/components/auth/branding-panel";
import { MobileBanner } from "@/components/auth/mobile-banner";
import { OwnerLoginForm } from "@/components/auth/owner-login-form";
import { OwnerAuthProvider } from "@/hooks/use-owner-auth";

export const metadata: Metadata = {
  title: "Sign in · Platform account",
  description: "Sign in to your shikshasync.me platform account.",
  robots: { index: false, follow: false },
};

/**
 * Owner (platform) login — the shikshasync.me "Platform Login" door.
 *
 *   shikshasync.me/login        → this page (owner / customer account)
 *   green.shikshasync.me/login  → institution login (/login) — daily ERP
 *   app.shikshasync.me/login    → staff console (/platform/login)
 *
 * Behind the real DNS split, rewrite `shikshasync.me/login` to `/account/login`:
 *
 *     // next.config.mjs
 *     async rewrites() {
 *       return [{ source: "/login", has: [{ type: "host", value: "shikshasync.me" }], destination: "/account/login" }];
 *     }
 */
export default function OwnerLoginPage() {
  return (
    <OwnerAuthProvider>
      <div className="flex min-h-screen flex-col bg-[#F8FAFC] lg:flex-row">
        <BrandingPanel />
        <MobileBanner />

        <main className="flex flex-1 items-start justify-center bg-white p-6 lg:items-center lg:bg-[#F8FAFC] lg:p-10">
          <div className="w-full max-w-[400px] animate-fade-up py-4 lg:py-0">
            <OwnerLoginForm />
          </div>
        </main>
      </div>
    </OwnerAuthProvider>
  );
}
