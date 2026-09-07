import type { Metadata } from "next";
import Link from "next/link";
import { Building2, Mail, MapPin, MessageCircle, Phone, ShieldCheck, FileText } from "lucide-react";

import { MarketingShell, Section, SectionHeading } from "@/components/marketing/marketing-shell";
import { ServiceRequestForm } from "@/components/marketing/service-request-form";

export const metadata: Metadata = {
  title: "Contact & Legal Entity — xyz.com",
  description:
    "Book a consultation, reach customer support, or review registered corporate entity and statutory grievance officer details for xyz.com Technologies Private Limited.",
};

const CHANNELS = [
  { icon: Phone, label: "Sales & demos", value: "+91 80 4718 0000", hint: "Mon–Sat, 9:00–18:00 IST" },
  { icon: Mail, label: "General & Sales Email", value: "hello@xyz.com", hint: "We reply within one business day" },
  { icon: MessageCircle, label: "Existing customer support", value: "From your dashboard → Support", hint: "Signed-in owners can raise tickets" },
  { icon: MapPin, label: "Corporate Office", value: "Bengaluru, Karnataka, India", hint: "Remote-first team across India" },
];

export default function ContactPage() {
  return (
    <MarketingShell>
      <Section className="!pb-10">
        <SectionHeading
          eyebrow="Contact & Corporate Details"
          title="Let’s talk."
          lede="Book a consultation, ask about pricing or partnerships, or reach our compliance and support teams. We respond within one business day."
        />
      </Section>

      <section className="bg-[#F8FAFC]">
        <Section className="!py-16">
          <div className="grid gap-10 lg:grid-cols-[.9fr_1.1fr] lg:gap-16">
            <div className="space-y-6">
              <div>
                <h2 className="font-display text-xl font-bold text-primary">Reach us directly</h2>
                <ul className="mt-6 space-y-4">
                  {CHANNELS.map((c) => (
                    <li key={c.label} className="flex gap-4 rounded-card border border-border bg-white p-5">
                      <span className="inline-flex rounded-xl bg-accent-light p-2.5 text-accent shrink-0">
                        <c.icon className="h-5 w-5" aria-hidden="true" />
                      </span>
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{c.label}</p>
                        <p className="mt-0.5 text-sm font-bold text-primary">{c.value}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">{c.hint}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Registered Legal Entity Card */}
              <div className="rounded-card border border-border bg-white p-6 shadow-sm space-y-4">
                <div className="flex items-center gap-3 border-b border-border pb-4">
                  <span className="inline-flex rounded-xl bg-slate-100 p-2 text-primary">
                    <Building2 className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 className="font-display text-base font-bold text-primary">
                      Registered Legal Entity
                    </h3>
                    <p className="text-xs text-muted-foreground">Ministry of Corporate Affairs (MCA), India</p>
                  </div>
                </div>

                <div className="space-y-2 text-xs text-slate-700">
                  <div className="flex justify-between py-1 border-b border-slate-100">
                    <span className="text-muted-foreground">Legal Entity Name:</span>
                    <span className="font-semibold text-primary">xyz.com Technologies Private Limited</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-100">
                    <span className="text-muted-foreground">CIN:</span>
                    <span className="font-mono font-medium text-slate-800">U72900KA2024PTC189421</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-100">
                    <span className="text-muted-foreground">GSTIN:</span>
                    <span className="font-mono font-medium text-slate-800">29AABCX1234F1Z9</span>
                  </div>
                  <div className="pt-2">
                    <span className="text-muted-foreground block mb-1">Registered Office Address:</span>
                    <p className="leading-relaxed text-slate-800 bg-slate-50 p-3 rounded-lg border border-slate-200/60">
                      Prestige Tech Park, 4th Floor, Marathahalli - Sarjapur Outer Ring Road,
                      Kadubeesanahalli, Bengaluru, Karnataka 560103, India.
                    </p>
                  </div>
                </div>
              </div>

              {/* Grievance Redressal Card (India DPDP Act 2023 & IT Rules) */}
              <div className="rounded-card border border-border bg-white p-6 shadow-sm space-y-3">
                <div className="flex items-center gap-3 border-b border-border pb-3">
                  <span className="inline-flex rounded-xl bg-blue-50 p-2 text-blue-600">
                    <ShieldCheck className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 className="font-display text-sm font-bold text-primary">
                      Statutory Grievance Officer
                    </h3>
                    <p className="text-[11px] text-muted-foreground">Under DPDP Act 2023 & IT Rules 2021</p>
                  </div>
                </div>

                <div className="text-xs text-slate-600 space-y-1.5">
                  <p><strong>Designation:</strong> Grievance Redressal & Privacy Officer</p>
                  <p>
                    <strong>Email:</strong>{" "}
                    <a href="mailto:grievance@xyz.com" className="text-accent font-semibold hover:underline">
                      grievance@xyz.com
                    </a>
                  </p>
                  <p><strong>Escalation:</strong> legal@xyz.com</p>
                  <p className="text-[11px] text-muted-foreground pt-1">
                    Statutory SLA: Acknowledgment within 48 hours; resolution within 30 days.
                  </p>
                </div>
              </div>
            </div>

            <div className="rounded-[20px] border border-border bg-white p-5 shadow-card sm:p-8 self-start">
              <h2 className="font-display text-2xl font-bold text-primary">Book a consultation</h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Tell us about your institution and a specialist will reach out with a tailored plan.
              </p>
              <div className="mt-6">
                <ServiceRequestForm />
              </div>

              <div className="mt-8 border-t border-border pt-6">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Compliance & Legal Resources
                </p>
                <div className="mt-3 flex flex-wrap gap-4 text-xs">
                  <Link href="/privacy" className="font-semibold text-accent hover:underline flex items-center gap-1">
                    <FileText className="h-3.5 w-3.5" /> Privacy Policy
                  </Link>
                  <Link href="/terms" className="font-semibold text-accent hover:underline flex items-center gap-1">
                    <FileText className="h-3.5 w-3.5" /> Terms of Service
                  </Link>
                  <Link href="/refund-policy" className="font-semibold text-accent hover:underline flex items-center gap-1">
                    <FileText className="h-3.5 w-3.5" /> Refund Policy
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </Section>
      </section>
    </MarketingShell>
  );
}
