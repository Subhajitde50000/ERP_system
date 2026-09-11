import type { Metadata } from "next";

import { CtaBand, MarketingShell, Section, SectionHeading } from "@/components/marketing/marketing-shell";
import { STATS } from "@/lib/marketing";

export const metadata: Metadata = {
  title: "About — education, connected",
  description:
    "shikshasync.me is on a mission to give every institution one calm, connected home for academics, learning and operations. Made in India.",
};

const VALUES = [
  { title: "Calm over chaos", copy: "Education is noisy enough. Software should reduce the noise, not add to it." },
  { title: "One source of truth", copy: "Attendance, marks and fees belong in one place — not three spreadsheets." },
  { title: "Security by architecture", copy: "Isolation and access control are how we build, not something we patch on." },
  { title: "Made for India", copy: "GST, IST and Indian education workflows — first-class, not an afterthought." },
];

const TIMELINE = [
  { year: "2024", title: "The idea", copy: "Frustrated by fragmented tools, we set out to build one connected platform for education." },
  { year: "2025", title: "First institutions", copy: "Schools and colleges went live on the multi-tenant core — 16 modules, one data model." },
  { year: "2026", title: "Account-holder model", copy: "One account now owns many institutions, with consolidated billing and support." },
];

export default function AboutPage() {
  return (
    <MarketingShell>
      <Section className="!pb-10 text-center">
        <SectionHeading
          eyebrow="About shikshasync.me"
          title="We’re building the connected home for education."
          lede="Our mission is simple: give every institution — from a single school to a multi-campus trust — one calm, reliable place to run academics, learning and operations."
          align="center"
        />
      </Section>

      <section className="bg-[#F8FAFC]">
        <Section className="!py-16">
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {STATS.map((s) => (
              <div key={s.label} className="rounded-card border border-border bg-white p-6 text-center">
                <p className="font-display text-3xl font-extrabold text-accent">{s.value}</p>
                <p className="mt-1 text-sm text-muted-foreground">{s.label}</p>
              </div>
            ))}
          </div>
        </Section>
      </section>

      <Section>
        <SectionHeading eyebrow="What we believe" title="Principles that shape the product." />
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {VALUES.map((v) => (
            <article key={v.title} className="rounded-card border border-border p-6">
              <h3 className="font-display text-base font-bold text-primary">{v.title}</h3>
              <p className="mt-2 text-sm leading-6 text-[#64748B]">{v.copy}</p>
            </article>
          ))}
        </div>
      </Section>

      <section className="bg-primary text-white">
        <Section>
          <SectionHeading eyebrow="Our journey" title="From an idea to 500+ institutions." tone="light" />
          <ol className="mt-12 grid gap-6 md:grid-cols-3">
            {TIMELINE.map((t) => (
              <li key={t.year} className="rounded-card border border-white/10 bg-white/5 p-6">
                <span className="font-display text-xl font-extrabold text-cyan-300">{t.year}</span>
                <h3 className="mt-2 font-display text-lg font-bold text-white">{t.title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-300">{t.copy}</p>
              </li>
            ))}
          </ol>
        </Section>
      </section>

      <CtaBand
        title="Want to join us?"
        body="Whether you’re an institution leader or a future teammate, we’d love to hear from you."
        primary={{ label: "Get started", href: "/signup" }}
        secondary={{ label: "Contact us", href: "/contact" }}
      />
    </MarketingShell>
  );
}
