import type { Metadata } from "next";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { CtaBand, MarketingShell, Section, SectionHeading } from "@/components/marketing/marketing-shell";
import { FAQS } from "@/lib/marketing";

export const metadata: Metadata = {
  title: "FAQ — answers to common questions",
  description:
    "How shikshasync.me works, pricing, multi-institution accounts, data isolation, implementation and support — answered.",
};

export default function FaqPage() {
  return (
    <MarketingShell>
      <Section className="!pb-10 text-center">
        <SectionHeading
          eyebrow="FAQ"
          title="Answers to common questions."
          lede="Everything from how sign-up works to data isolation, pricing and implementation. Can’t find your answer? Just ask us."
          align="center"
        />
      </Section>

      <section className="bg-[#F8FAFC]">
        <Section className="!py-16">
          <div className="mx-auto max-w-3xl divide-y divide-border rounded-card border border-border bg-white">
            {FAQS.map((f) => (
              <details key={f.q} className="group p-5">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-semibold text-primary">
                  {f.q}
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-open:rotate-90" aria-hidden="true" />
                </summary>
                <p className="mt-3 text-sm leading-6 text-[#64748B]">{f.a}</p>
              </details>
            ))}
          </div>

          <div className="mx-auto mt-8 max-w-3xl rounded-card border border-accent-border bg-accent-light p-6 text-center">
            <h2 className="font-display text-lg font-bold text-primary">Still have questions?</h2>
            <p className="mt-1 text-sm text-[#475569]">Our team is happy to help — book a call or start a free trial.</p>
            <div className="mt-4 flex flex-col justify-center gap-3 sm:flex-row">
              <Link href="/contact" className="inline-flex h-11 items-center justify-center rounded-field bg-accent px-5 text-sm font-semibold text-white transition hover:bg-accent-hover">
                Contact us
              </Link>
              <Link href="/signup" className="inline-flex h-11 items-center justify-center rounded-field border border-border bg-white px-5 text-sm font-semibold text-primary transition hover:border-accent">
                Start free
              </Link>
            </div>
          </div>
        </Section>
      </section>

      <CtaBand
        title="Try shikshasync.me free for 14 days."
        body="Create your account, spin up an institution, and explore every module. No card required."
        primary={{ label: "Start free", href: "/signup" }}
        secondary={{ label: "See pricing", href: "/pricing" }}
      />
    </MarketingShell>
  );
}
