import type { Metadata } from "next";
import Link from "next/link";
import { RefreshCw, CheckCircle, CreditCard, School } from "lucide-react";

import { MarketingShell, Section, SectionHeading } from "@/components/marketing/marketing-shell";

export const metadata: Metadata = {
  title: "Refund & Cancellation Policy — xyz.com",
  description:
    "Transparent refund and cancellation terms for xyz.com platform subscriptions, free trial protections, and institutional student fee payment guidelines.",
};

export default function RefundPolicyPage() {
  return (
    <MarketingShell>
      <Section className="!pb-8">
        <SectionHeading
          eyebrow="Billing & Policies"
          title="Refund & Cancellation Policy"
          lede="Clear, predictable billing with no surprise renewals. Here is how subscription cancellations, refund guarantees, and fee payment disputes are handled."
        />
        <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span className="rounded-full bg-slate-100 px-3 py-1 font-semibold text-slate-700">
            Effective: September 1, 2026
          </span>
          <span className="rounded-full bg-emerald-50 px-3 py-1 font-semibold text-emerald-700">
            14-Day Free Trial Guarantee
          </span>
          <span>Version 2.0</span>
        </div>
      </Section>

      <section className="border-t border-border bg-[#F8FAFC]">
        <Section className="!py-12">
          <div className="grid gap-12 lg:grid-cols-[280px_1fr]">
            {/* Table of Contents */}
            <aside className="hidden lg:block">
              <div className="sticky top-28 rounded-card border border-border bg-white p-5 shadow-sm">
                <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Policy Sections
                </p>
                <nav className="mt-4 space-y-2 text-xs">
                  <a href="#trial" className="block text-slate-600 transition hover:text-accent">
                    1. 14-Day Free Trial
                  </a>
                  <a href="#cancellation" className="block text-slate-600 transition hover:text-accent">
                    2. Subscription Cancellation
                  </a>
                  <a href="#annual-refunds" className="block text-slate-600 transition hover:text-accent">
                    3. Annual Plan 7-Day Guarantee
                  </a>
                  <a href="#institution-fees" className="block font-semibold text-accent transition hover:underline">
                    4. Student & Parent Fee Payments
                  </a>
                  <a href="#sla-refunds" className="block text-slate-600 transition hover:text-accent">
                    5. SLA Outage Credits
                  </a>
                  <a href="#processing" className="block text-slate-600 transition hover:text-accent">
                    6. Processing Turnaround & Mode
                  </a>
                  <a href="#contact" className="block text-slate-600 transition hover:text-accent">
                    7. Dispute Resolution & Contact
                  </a>
                </nav>
              </div>
            </aside>

            {/* Policy Details */}
            <article className="space-y-12 text-sm leading-relaxed text-[#334155]">
              {/* Highlight summary */}
              <div className="rounded-card border border-border bg-white p-6 sm:p-7 shadow-sm">
                <div className="flex items-start gap-4">
                  <span className="rounded-xl bg-emerald-50 p-3 text-emerald-600 shrink-0">
                    <CheckCircle className="h-6 w-6" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 className="font-display text-base font-bold text-primary">
                      Our Zero-Friction Billing Principles
                    </h3>
                    <ul className="mt-2.5 list-disc space-y-1 pl-4 text-xs text-slate-600">
                      <li><strong>No credit card required for trials:</strong> You will never be auto-charged when a trial concludes.</li>
                      <li><strong>Cancel any time:</strong> You can cancel future renewals with a single click from your platform dashboard.</li>
                      <li><strong>Transparent GST invoices:</strong> Every payment produces a downloadable, gapless statutory invoice.</li>
                    </ul>
                  </div>
                </div>
              </div>

              {/* 1. 14-Day Free Trial Guarantee */}
              <section id="trial" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  1. 14-Day Free Trial Guarantee
                </h2>
                <p>
                  Every new educational institution account is entitled to a fully-featured <strong>14-day free trial</strong> with all 16 academic and operational modules activated.
                </p>
                <div className="rounded-card border border-border bg-white p-5 text-xs text-slate-700 space-y-2">
                  <p>• <strong>Zero Automatic Charges:</strong> We do not ask for credit card, debit card, or banking details to begin a trial.</p>
                  <p>• <strong>Explicit Upgrade Only:</strong> At the conclusion of your 14-day evaluation, your account transitions to a paused state unless an authorized administrator explicitly chooses to subscribe.</p>
                  <p>• <strong>No Surprise Renewals:</strong> You will never be charged without your active authorization and selected payment method.</p>
                </div>
              </section>

              {/* 2. Subscription Cancellation */}
              <section id="cancellation" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  2. Subscription Cancellation Process
                </h2>
                <p>
                  Account holders may cancel paid subscriptions at any time:
                </p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-card border border-border bg-white p-4">
                    <p className="font-bold text-primary">Self-Serve via Dashboard</p>
                    <p className="mt-1.5 text-xs text-muted-foreground">
                      Navigate to <strong>Account Dashboard → Subscriptions</strong> and select &ldquo;Cancel Subscription&rdquo;. Cancellation takes effect immediately for future billing cycles.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <p className="font-bold text-primary">Support Request</p>
                    <p className="mt-1.5 text-xs text-muted-foreground">
                      Email <a href="mailto:billing@xyz.com" className="text-accent underline font-semibold">billing@xyz.com</a> from your registered account owner email. Our team processes requests within one business day.
                    </p>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">
                  Following cancellation, your institution retains access through the conclusion of the paid billing period. After this, accounts enter our standard 30-day read-only data export grace period.
                </p>
              </section>

              {/* 3. Annual Plan 7-Day Guarantee */}
              <section id="annual-refunds" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  3. 7-Day Money-Back Guarantee for Annual Subscriptions
                </h2>
                <p>
                  To give school leadership complete peace of mind, all first-time annual subscriptions are covered by our <strong>7-Day Money-Back Guarantee</strong>:
                </p>
                <div className="rounded-card border border-border bg-white p-5 space-y-2.5">
                  <p className="text-xs text-slate-700">
                    If your institution is not satisfied with the platform within seven (7) calendar days of initial payment, you may request a 100% refund of the subscription fee paid, less any payment gateway processing fees and non-refundable bespoke custom data-migration services.
                  </p>
                  <p className="text-xs text-slate-700">
                    Monthly subscription plans are non-refundable once the monthly billing period has commenced, as services are provisioned immediately upon receipt of payment.
                  </p>
                </div>
              </section>

              {/* 4. Student & Parent Fee Payments (Critical Educational ERP Distinction) */}
              <section id="institution-fees" className="scroll-mt-28 space-y-4">
                <div className="rounded-card border border-blue-200 bg-blue-50/70 p-6">
                  <div className="flex items-start gap-3">
                    <School className="h-6 w-6 text-blue-700 shrink-0 mt-0.5" />
                    <div>
                      <h2 className="font-display text-base font-bold text-blue-900">
                        4. Crucial Notice: Student Tuition & Institution Fee Payments
                      </h2>
                      <p className="mt-2 text-xs leading-6 text-blue-800">
                        Please read carefully if you are a parent, student, or guardian making fee payments through the xyz.com portal:
                      </p>
                    </div>
                  </div>
                </div>

                <div className="rounded-card border border-border bg-white p-5 space-y-3 text-xs text-slate-700">
                  <p>
                    <strong>A. Technology Intermediary Role:</strong> xyz.com Technologies Private Limited acts strictly as the software provider and technology intermediary connecting educational institutions with certified payment aggregators. All tuition fees, admission deposits, hostel charges, laboratory fees, and examination dues paid through the portal are deposited directly into the institution&apos;s designated bank account.
                  </p>
                  <p>
                    <strong>B. Institutional Refund Autonomy:</strong> All refund requests for student fees (such as school withdrawals, fee adjustments, or scholarship concessions) are governed exclusively by the independent fee refund policy of the respective school, college, or university.
                  </p>
                  <p>
                    <strong>C. Procedure for Student Fee Refunds:</strong> xyz.com cannot unilaterally issue refunds for institutional fees without written authorization from the school administration. Parents and students must submit fee refund applications directly to their school&apos;s administrative office or accounts department.
                  </p>
                </div>
              </section>

              {/* 5. SLA Outage Credits */}
              <section id="sla-refunds" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  5. Service Outage & SLA Credits
                </h2>
                <p>
                  We are committed to delivering 99.9% uptime. If platform downtime attributable directly to our infrastructure exceeds our SLA commitment in any given monthly billing cycle:
                </p>
                <div className="rounded-card border border-border bg-white p-5 text-xs text-slate-700 space-y-2">
                  <p>• Institutions may claim service credits or pro-rata invoice adjustments against subsequent billing cycles.</p>
                  <p>• Service credit claims must be submitted to <a href="mailto:support@xyz.com" className="text-accent underline font-semibold">support@xyz.com</a> within fifteen (15) days of the verified outage incident.</p>
                  <p>• Downtime caused by client-side network failures, third-party internet service providers, or scheduled maintenance windows announced in advance are excluded.</p>
                </div>
              </section>

              {/* 6. Processing Turnaround & Mode */}
              <section id="processing" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  6. Refund Processing Turnaround & Mode
                </h2>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-card border border-border bg-white p-4">
                    <CreditCard className="h-5 w-5 text-accent" />
                    <p className="mt-2 font-bold text-primary">Original Payment Mode</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      All approved refunds are credited back directly to the original payment source (Net Banking, UPI, Debit/Credit Card). Cash or third-party transfers are prohibited for fraud prevention.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <RefreshCw className="h-5 w-5 text-accent" />
                    <p className="mt-2 font-bold text-primary">5 to 7 Business Days</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Once approved by our finance desk, refunds are initiated within 48 hours. Depending on your banking institution, funds typically reflect within 5–7 business days.
                    </p>
                  </div>
                </div>
              </section>

              {/* 7. Dispute Resolution & Contact */}
              <section id="contact" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  7. Billing Inquiries & Dispute Escalation
                </h2>
                <p>
                  If you observe an unexpected charge or have questions regarding an invoice, please contact our billing team before initiating a chargeback with your bank so we can resolve the matter promptly:
                </p>

                <div className="rounded-card border border-border bg-white p-6 space-y-3">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="font-semibold text-primary">Finance & Billing Helpdesk</p>
                      <p className="text-xs text-muted-foreground">xyz.com Technologies Private Limited</p>
                    </div>
                    <div className="text-xs">
                      <a
                        href="mailto:billing@xyz.com"
                        className="inline-flex items-center gap-1.5 font-bold text-accent hover:underline"
                      >
                        billing@xyz.com
                      </a>
                    </div>
                  </div>
                  <p className="text-xs text-slate-500 pt-2 border-t border-border">
                    Standard response time: Within 24 business hours (Monday – Saturday, 09:00 to 18:00 IST).
                  </p>
                </div>
              </section>

              {/* Cross links */}
              <div className="border-t border-border pt-6 text-xs text-muted-foreground flex flex-wrap gap-4">
                <Link href="/terms" className="font-semibold text-accent hover:underline">
                  Terms of Service →
                </Link>
                <Link href="/privacy" className="font-semibold text-accent hover:underline">
                  Privacy Policy →
                </Link>
                <Link href="/contact" className="font-semibold text-accent hover:underline">
                  Contact Support →
                </Link>
              </div>
            </article>
          </div>
        </Section>
      </section>
    </MarketingShell>
  );
}
