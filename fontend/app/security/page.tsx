import type { Metadata } from "next";

import { CtaBand, MarketingShell, Section, SectionHeading } from "@/components/marketing/marketing-shell";
import { SECURITY_POINTS } from "@/lib/marketing";

export const metadata: Metadata = {
  title: "Security — isolated by design, audited by default",
  description:
    "Tenant data isolation, origin-bound tokens, role-based access control, encrypted credentials and audit logging — how shikshasync.me keeps institution data safe.",
};

export default function SecurityPage() {
  return (
    <MarketingShell>
      <Section className="!pb-10 text-center">
        <SectionHeading
          eyebrow="Security & trust"
          title="Isolated by design. Audited by default."
          lede="shikshasync.me is multi-tenant by architecture: every institution is a separate tenant with its own data, roles and tokens. Security is not a feature we bolted on — it is how the platform is built."
          align="center"
        />
      </Section>

      <section className="bg-[#F8FAFC]">
        <Section className="!py-16">
          <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {SECURITY_POINTS.map((p) => (
              <article key={p.title} className="rounded-card border border-border bg-white p-6">
                <span className="inline-flex rounded-xl bg-accent-light p-2.5 text-accent">
                  <p.icon className="h-5 w-5" aria-hidden="true" />
                </span>
                <h3 className="mt-4 font-display text-base font-bold text-primary">{p.title}</h3>
                <p className="mt-2 text-sm leading-6 text-[#64748B]">{p.description}</p>
              </article>
            ))}
          </div>
        </Section>
      </section>

      <Section>
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-16">
          <div>
            <SectionHeading
              eyebrow="Data residency"
              title="Indian institutions, Indian compliance."
              lede="Single-country by design. Timezones default to Asia/Kolkata, billing is GST-compliant, and every invoice carries a gapless, statutory number sequence."
            />
            <ul className="mt-6 space-y-3">
              {[
                "Default timezone Asia/Kolkata — no UTC date drift",
                "GST-compliant invoicing with CGST/SGST/IGST by place of supply",
                "Idempotent payment records — webhook replays never double-charge",
                "Data retained safely through grace periods; never hard-deleted at expiry",
              ].map((item) => (
                <li key={item} className="flex items-start gap-2 text-sm text-[#334155]">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <SectionHeading
              eyebrow="Resilience"
              title="Built to stay up when it matters."
              lede="A school mid-term still needs today’s timetable while finance resolves a payment. The platform degrades gracefully instead of locking everyone out."
            />
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              {[
                { k: "99.95%", v: "12-month uptime" },
                { k: "Read-only", v: "Grace period on overdue bills" },
                { k: "Pre-ping", v: "Stale-connection detection" },
                { k: "Per-IP", v: "Rate limiting & lockout" },
              ].map((s) => (
                <div key={s.v} className="rounded-card border border-border p-5">
                  <p className="font-display text-xl font-extrabold text-accent">{s.k}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{s.v}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Section>

      <CtaBand
        title="Security questions? We have answers."
        body="Talk to our team about data isolation, roles, audit and compliance for your institution."
        primary={{ label: "Book a demo", href: "/contact" }}
        secondary={{ label: "See features", href: "/features" }}
      />
    </MarketingShell>
  );
}
