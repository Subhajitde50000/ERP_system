import type { Metadata } from "next";
import { Quote, Star } from "lucide-react";

import { CtaBand, MarketingShell, Section, SectionHeading } from "@/components/marketing/marketing-shell";
import { STATS, TESTIMONIALS } from "@/lib/marketing";

export const metadata: Metadata = {
  title: "Customers — institutions that run on shikshasync.me",
  description:
    "Schools, colleges and universities use shikshasync.me to connect academics, learning and operations. Hear what changed for them.",
};

const CASES = [
  {
    org: "Greenwood International School",
    type: "K-12 School · 1,400 learners",
    metric: "−87%",
    metricLabel: "time spent on daily attendance",
    summary:
      "Replaced paper registers and a separate fee tool with one platform. Parents now see absences before their child is home, and reminders drove fee collection up to 98%.",
  },
  {
    org: "Northstar College of Engineering",
    type: "College · 6 departments",
    metric: "1 term",
    metricLabel: "to roll out exams, fees & results",
    summary:
      "Department and HOD structure mapped cleanly. Semester results, placements and HR all live in one system, and role-based workspaces meant adoption needed almost no training.",
  },
  {
    org: "Sharma Education Trust",
    type: "Group · 3 campuses",
    metric: "3 → 1",
    metricLabel: "logins, bills and support inboxes",
    summary:
      "One platform account now owns all three campuses. Consolidated billing, subscriptions and a single support contact save the trust weeks of admin every quarter.",
  },
];

export default function CustomersPage() {
  return (
    <MarketingShell>
      <Section className="!pb-10 text-center">
        <SectionHeading
          eyebrow="Customers"
          title="Institutions that run on shikshasync.me."
          lede="From a single school to a multi-campus trust, education leaders use shikshasync.me to connect academics, learning and operations."
          align="center"
        />
        <div className="mx-auto mt-10 grid max-w-3xl grid-cols-2 gap-6 sm:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.label}>
              <p className="font-display text-2xl font-extrabold text-primary">{s.value}</p>
              <p className="mt-1 text-xs text-muted-foreground">{s.label}</p>
            </div>
          ))}
        </div>
      </Section>

      <section className="bg-[#F8FAFC]">
        <Section className="!py-16">
          <SectionHeading eyebrow="Case studies" title="What changed for them." align="center" />
          <div className="mt-12 grid gap-5 lg:grid-cols-3">
            {CASES.map((c) => (
              <article key={c.org} className="flex flex-col rounded-card border border-border bg-white p-6 shadow-card">
                <p className="text-xs font-semibold uppercase tracking-wide text-accent">{c.type}</p>
                <h3 className="mt-2 font-display text-lg font-bold text-primary">{c.org}</h3>
                <div className="mt-4 flex items-baseline gap-2">
                  <span className="font-display text-3xl font-extrabold text-primary">{c.metric}</span>
                  <span className="text-xs text-muted-foreground">{c.metricLabel}</span>
                </div>
                <p className="mt-4 flex-1 text-sm leading-6 text-[#475569]">{c.summary}</p>
              </article>
            ))}
          </div>
        </Section>
      </section>

      <Section>
        <SectionHeading eyebrow="In their words" title="What educators say." align="center" />
        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {TESTIMONIALS.map((t) => (
            <figure key={t.name} className="flex flex-col rounded-card border border-border bg-white p-6 shadow-card">
              <div className="flex gap-0.5 text-warning" aria-label="5 out of 5 stars">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Star key={i} className="h-4 w-4 fill-current" aria-hidden="true" />
                ))}
              </div>
              <Quote className="mt-3 h-6 w-6 text-accent-soft" aria-hidden="true" />
              <blockquote className="mt-2 flex-1 text-sm leading-6 text-[#334155]">“{t.quote}”</blockquote>
              <figcaption className="mt-5 border-t border-border pt-4">
                <p className="text-sm font-bold text-primary">{t.name}</p>
                <p className="text-xs text-muted-foreground">{t.role}, {t.org}</p>
              </figcaption>
            </figure>
          ))}
        </div>
      </Section>

      <CtaBand
        title="Join 500+ institutions on shikshasync.me."
        body="Start your free trial today, or let our team tailor a rollout plan for your institution."
        primary={{ label: "Start free", href: "/signup" }}
        secondary={{ label: "Talk to us", href: "/contact" }}
      />
    </MarketingShell>
  );
}
