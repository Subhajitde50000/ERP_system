import Link from "next/link";
import type { Metadata } from "next";
import { ArrowLeft, LifeBuoy, Mail, Phone } from "lucide-react";

import { Logo } from "@/components/auth/logo";

export const metadata: Metadata = {
  title: "Support",
  description: "Get help signing in to shikshasync.me.",
};

const CHANNELS = [
  {
    icon: Mail,
    label: "Email your institution admin",
    value: "admin@your-institution.edu",
    hint: "Fastest for password resets and account access",
  },
  {
    icon: Phone,
    label: "Platform support",
    value: "+91 80 4718 0000",
    hint: "Mon–Sat, 9:00–18:00 IST",
  },
] as const;

/** Placeholder support page so the login footer link resolves. */
export default function SupportPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F8FAFC] p-6">
      <div className="w-full max-w-[480px] animate-fade-up">
        <Logo className="mb-8" />

        <div className="rounded-card border border-[#E2E8F0] bg-white p-8 shadow-card">
          <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-full bg-accent-light">
            <LifeBuoy className="h-5 w-5 text-accent" aria-hidden="true" />
          </div>

          <h1 className="font-display text-[22px] font-bold text-[#0F172A]">
            Trouble signing in?
          </h1>
          <p className="mt-1 text-[13px] text-[#64748B]">
            Your institution admin manages accounts, roles and module access.
          </p>

          <ul className="mt-6 space-y-3">
            {CHANNELS.map(({ icon: Icon, label, value, hint }) => (
              <li
                key={label}
                className="flex gap-3 rounded-field border border-[#E2E8F0] p-4"
              >
                <Icon
                  className="mt-0.5 h-4 w-4 shrink-0 text-accent"
                  aria-hidden="true"
                />
                <div>
                  <p className="text-[13px] font-medium text-[#0F172A]">{label}</p>
                  <p className="text-[13px] text-[#475569]">{value}</p>
                  <p className="mt-0.5 text-[12px] text-[#94A3B8]">{hint}</p>
                </div>
              </li>
            ))}
          </ul>

          <Link
            href="/login"
            className="mt-6 inline-flex items-center gap-1.5 rounded text-[13px] font-medium text-accent transition-colors hover:text-accent-hover"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back to sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
