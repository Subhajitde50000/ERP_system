import type { Metadata } from "next";

import { BrandingPanel } from "@/components/auth/branding-panel";
import { MobileBanner } from "@/components/auth/mobile-banner";
import { PlatformLoginForm } from "@/components/auth/platform-login-form";

export const metadata: Metadata = {
  title: "Platform console · Sign in",
  description: "Sign in to the shikshasync.me platform console.",
  // The staff console must never be indexed, and a referrer must not leak the
  // path to a third party.
  robots: { index: false, follow: false },
};

/**
 * Platform console sign-in — C-PB-01 for the `app.shikshasync.me` origin.
 *
 * `login_page_design.md` §1 requires the login page to serve
 * "`app.shikshasync.me` → Platform roles (Super Admin, Support, Sales, Finance)",
 * and §8 sends `SUPER_ADMIN → app.shikshasync.me/dashboard`. All eight platform
 * pages existed, but there was no way to sign in to any of them.
 *
 * ── Why a separate route from `/login` ────────────────────────────────────
 *
 * In production these are two hosts, not two paths: `abc-college.shikshasync.me/login`
 * and `app.shikshasync.me/login`. One file could serve both by branching on the Host
 * header — the tenant resolver already reports `isPlatform`. It is kept
 * separate because the two pages authenticate against **different tables**
 * (`users` vs `platform_users`), post to **different endpoints**, and have
 * **different failure states**: the tenant form must handle
 * `TENANT_NOT_FOUND`, which cannot occur here, and this form must not offer
 * a password reset, which the tenant form must. Branching a single component
 * on `isPlatform` would put two auth flows behind one set of conditionals.
 *
 * The route is `/platform/login` on a single-origin deployment (and in local
 * dev). Behind the real DNS split, rewrite `app.shikshasync.me/login` to it:
 *
 *     // next.config.mjs
 *     async rewrites() {
 *       return [{
 *         source: "/login",
 *         has: [{ type: "host", value: "app.shikshasync.me" }],
 *         destination: "/platform/login",
 *       }];
 *     }
 */
export default function PlatformLoginPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[#F8FAFC] lg:flex-row">
      <BrandingPanel />
      <MobileBanner />

      <main className="flex flex-1 items-start justify-center bg-white p-6 lg:items-center lg:bg-[#F8FAFC] lg:p-10">
        <div className="w-full max-w-[400px] animate-fade-up py-4 lg:py-0">
          <PlatformLoginForm />

          <p className="mt-6 text-center text-[11px] leading-relaxed text-[#475569]">
            Every platform sign-in is audited ·{" "}
            <span className="font-medium text-[#0F172A]">v0.1.0</span>
          </p>
        </div>
      </main>
    </div>
  );
}
