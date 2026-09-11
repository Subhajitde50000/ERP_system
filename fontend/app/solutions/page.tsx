import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";

import { CtaBand, MarketingShell, Section, SectionHeading } from "@/components/marketing/marketing-shell";
import { AUDIENCES } from "@/lib/marketing";

export const metadata: Metadata = {
  title: "Solutions — for schools, colleges, universities and groups",
  description:
    "shikshasync.me adapts to your structure: K-12 schools, colleges, multi-faculty universities and multi-campus groups, all under one platform account.",
};

export default function SolutionsPage() {
  return (
    <MarketingShell>
      <Section className="!pb-10 text-center">
        <SectionHeading
          eyebrow="Solutions"
          title="Shaped to how your institution actually works."
          lede="Whether you run a single school or a multi-campus group, shikshasync.me adapts to your structure — one account manages them all."
          align="center"
        />
      </Section>

      {AUDIENCES.map((a, i) => (
        <section key={a.slug} id={a.slug} className={i % 2 === 1 ? "bg-[#F8FAFC]" : ""}>
          <Section className="!py-16 lg:!py-20">
            <div className="grid gap-10 lg:grid-cols-2 lg:items-center lg:gap-16">
              <div className={i % 2 === 1 ? "lg:order-2" : ""}>
                <span className="inline-flex rounded-xl bg-accent-light p-3 text-accent">
                  <a.icon className="h-6 w-6" aria-hidden="true" />
                </span>
                <p className="mt-5 text-sm font-bold uppercase tracking-[0.14em] text-accent">{a.tagline}</p>
                <h2 className="mt-2 font-display text-3xl font-extrabold tracking-tight text-primary">{a.title}</h2>
                <p className="mt-4 text-base leading-7 text-[#475569]">{a.description}</p>
                <ul className="mt-6 grid gap-3 sm:grid-cols-2">
                  {a.highlights.map((h) => (
                    <li key={h} className="flex items-center gap-2 text-sm text-[#334155]">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-success-light text-success-text">
                        <Check className="h-3 w-3" aria-hidden="true" />
                      </span>
                      {h}
                    </li>
                  ))}
                </ul>
                <div className="mt-8">
                  <Link href="/contact" className="inline-flex h-11 items-center justify-center gap-2 rounded-field border border-border bg-white px-5 text-sm font-semibold text-primary transition hover:border-accent hover:text-accent">
                    Talk to us about {a.title.replace("For ", "")} <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </div>
              </div>
              <div className={i % 2 === 1 ? "lg:order-1" : ""}>
                <div className="rounded-card border border-border bg-white p-6 shadow-card">
                  <div className="grid grid-cols-2 gap-4">
                    {SOLUTION_STATS[a.slug].map((s) => (
                      <div key={s.label} className="rounded-field bg-[#F8FAFC] p-4">
                        <p className="font-display text-2xl font-extrabold text-primary">{s.value}</p>
                        <p className="mt-1 text-xs text-muted-foreground">{s.label}</p>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 rounded-field border border-accent-border bg-accent-light p-4">
                    <p className="text-sm font-semibold text-primary">{SOLUTION_QUOTES[a.slug]}</p>
                  </div>
                </div>
              </div>
            </div>
          </Section>
        </section>
      ))}

      <CtaBand
        title="Not sure where you fit?"
        body="Tell us about your institution and we’ll map the right modules, plan and rollout for you."
        primary={{ label: "Start free", href: "/signup" }}
        secondary={{ label: "Book a demo", href: "/contact" }}
      />
    </MarketingShell>
  );
}

const SOLUTION_STATS: Record<string, { value: string; label: string }[]> = {
  schools: [
    { value: "K–12", label: "Full age range" },
    { value: "2-way", label: "Parent links" },
    { value: "House", label: "Exam & report cards" },
    { value: "Auto", label: "Fee reminders" },
  ],
  colleges: [
    { value: "Dept.", label: "Programme hierarchy" },
    { value: "CGPA", label: "Semester results" },
    { value: "Drives", label: "Placement cell" },
    { value: "18", label: "Role-based access" },
  ],
  universities: [
    { value: "Multi", label: "Faculty governance" },
    { value: "1 TB+", label: "Storage tiers" },
    { value: "Audit", label: "Ready records" },
    { value: "SLA", label: "Enterprise support" },
  ],
  "multi-campus": [
    { value: "1 account", label: "Many institutions" },
    { value: "1 bill", label: "Consolidated" },
    { value: "1 inbox", label: "Support tickets" },
    { value: "∞", label: "Scalable" },
  ],
};

const SOLUTION_QUOTES: Record<string, string> = {
  schools: "Attendance and parent communication that just work — every single day.",
  colleges: "From departments to degrees, with placements and accreditation-ready records.",
  universities: "Centralised governance and finance across every faculty and campus.",
  "multi-campus": "Own them all under one account. One login, one bill, one team.",
};
