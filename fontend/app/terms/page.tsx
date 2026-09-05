import type { Metadata } from "next";
import Link from "next/link";
import { FileCheck, Shield, Database } from "lucide-react";

import { MarketingShell, Section, SectionHeading } from "@/components/marketing/marketing-shell";

export const metadata: Metadata = {
  title: "Terms of Service — xyz.com ERP & Learning Platform",
  description:
    "Terms and conditions governing the use of xyz.com educational software, cloud services, and subscriptions operated by xyz.com Technologies Private Limited.",
};

export default function TermsOfServicePage() {
  return (
    <MarketingShell>
      <Section className="!pb-8">
        <SectionHeading
          eyebrow="Legal & Terms"
          title="Terms of Service"
          lede="These Terms of Service constitute a legally binding agreement between xyz.com Technologies Private Limited and your educational institution or individual account."
        />
        <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span className="rounded-full bg-slate-100 px-3 py-1 font-semibold text-slate-700">
            Last Revised: September 1, 2026
          </span>
          <span className="rounded-full bg-emerald-50 px-3 py-1 font-semibold text-emerald-700">
            GST & India IT Act Compliant
          </span>
          <span>Version 2.0</span>
        </div>
      </Section>

      <section className="border-t border-border bg-[#F8FAFC]">
        <Section className="!py-12">
          <div className="grid gap-12 lg:grid-cols-[280px_1fr]">
            {/* Sticky Table of Contents */}
            <aside className="hidden lg:block">
              <div className="sticky top-28 rounded-card border border-border bg-white p-5 shadow-sm">
                <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Quick Navigation
                </p>
                <nav className="mt-4 space-y-2 text-xs">
                  <a href="#acceptance" className="block text-slate-600 transition hover:text-accent">
                    1. Acceptance & User Roles
                  </a>
                  <a href="#services" className="block text-slate-600 transition hover:text-accent">
                    2. Platform Services & Tiers
                  </a>
                  <a href="#accounts" className="block text-slate-600 transition hover:text-accent">
                    3. Account Security & Responsibilities
                  </a>
                  <a href="#subscriptions" className="block text-slate-600 transition hover:text-accent">
                    4. Subscriptions, Fees & GST
                  </a>
                  <a href="#data-ownership" className="block font-semibold text-accent transition hover:underline">
                    5. Data Ownership & IP Rights
                  </a>
                  <a href="#acceptable-use" className="block text-slate-600 transition hover:text-accent">
                    6. Acceptable Use Policy
                  </a>
                  <a href="#sla" className="block text-slate-600 transition hover:text-accent">
                    7. Availability & Service Levels
                  </a>
                  <a href="#termination" className="block text-slate-600 transition hover:text-accent">
                    8. Grace Periods & Termination
                  </a>
                  <a href="#liability" className="block text-slate-600 transition hover:text-accent">
                    9. Limitation of Liability
                  </a>
                  <a href="#governing-law" className="block text-slate-600 transition hover:text-accent">
                    10. Governing Law & Jurisdiction
                  </a>
                </nav>
              </div>
            </aside>

            {/* Terms Articles */}
            <article className="space-y-12 text-sm leading-relaxed text-[#334155]">
              {/* Summary Banner */}
              <div className="rounded-card border border-border bg-white p-6 sm:p-7 shadow-sm">
                <div className="flex items-start gap-4">
                  <span className="rounded-xl bg-accent-light p-3 text-accent shrink-0">
                    <FileCheck className="h-6 w-6" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 className="font-display text-base font-bold text-primary">
                      At a Glance: Key Tenets of Our Partnership
                    </h3>
                    <p className="mt-2 text-xs leading-6 text-slate-600">
                      By registering an account, ordering a plan, or accessing xyz.com, you agree to these Terms. You confirm you are authorized to bind your institution. We pledge continuous tenant isolation, strict customer data ownership, and transparent statutory invoicing.
                    </p>
                  </div>
                </div>
              </div>

              {/* 1. Acceptance & User Roles */}
              <section id="acceptance" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  1. Acceptance of Terms & User Roles
                </h2>
                <p>
                  These Terms of Service (&ldquo;Terms&rdquo;) govern access to the software-as-a-service application suite, mobile apps, and developer interfaces provided by <strong>xyz.com Technologies Private Limited</strong> (&ldquo;Company&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo;).
                </p>
                <p>
                  Our services are provided to distinct user categories:
                </p>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-card border border-border bg-white p-4">
                    <p className="font-bold text-primary">Account Holders</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Trustees, founders, or corporate owners managing multiple institution tenants and global billing.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <p className="font-bold text-primary">Institution Staff</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Principals, HODs, teachers, coordinators, accountants, and administrative officials.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <p className="font-bold text-primary">Students & Parents</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      End-users accessing timetables, attendance, online exams, report cards, and fee receipts.
                    </p>
                  </div>
                </div>
              </section>

              {/* 2. Platform Services & Tiers */}
              <section id="services" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  2. Platform Description & Service Tiers
                </h2>
                <p>
                  xyz.com provides an integrated ERP, Learning Management System (LMS), and communication platform designed for schools, colleges, and multi-campus trusts. Core features include student admissions, timetable scheduling, attendance tracking, examination management, automated grading, fee collection, and parent communication channels.
                </p>
                <p>
                  Features available to your institution depend on the active subscription plan (Starter, Professional, Enterprise, or tailored bespoke modules) configured in your subscription agreement.
                </p>
              </section>

              {/* 3. Account Security & Responsibilities */}
              <section id="accounts" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  3. Account Management & Security Responsibilities
                </h2>
                <ul className="space-y-3 pl-2">
                  <li className="flex items-start gap-2.5">
                    <Shield className="h-4 w-4 text-accent shrink-0 mt-1" />
                    <span>
                      <strong>Credential Confidentiality:</strong> Account holders and staff members are responsible for maintaining the confidentiality of their passwords, authentication tokens, and access credentials.
                    </span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <Shield className="h-4 w-4 text-accent shrink-0 mt-1" />
                    <span>
                      <strong>Authorized Personnel:</strong> The institution represents that only authorized administrative staff are granted administrative roles (`INSTITUTION_ADMIN`, `PRINCIPAL`, `EXAM_CONTROLLER`, etc.).
                    </span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <Shield className="h-4 w-4 text-accent shrink-0 mt-1" />
                    <span>
                      <strong>Notification of Breach:</strong> You agree to immediately notify xyz.com at <a href="mailto:security@xyz.com" className="text-accent underline">security@xyz.com</a> upon discovering any unauthorized account access or security compromise.
                    </span>
                  </li>
                </ul>
              </section>

              {/* 4. Subscriptions, Fees & GST */}
              <section id="subscriptions" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  4. Subscriptions, Invoicing & GST Taxation
                </h2>
                <div className="rounded-card border border-border bg-white p-5 space-y-3">
                  <p>
                    <strong>A. Subscription Billing:</strong> Subscriptions are billed in advance on an annual or monthly cycle as selected by the customer. All stated prices are in Indian Rupees (INR), unless explicitly quoted in another currency for overseas customers.
                  </p>
                  <p>
                    <strong>B. Goods & Services Tax (GST):</strong> In accordance with Indian tax statutes, applicable Goods and Services Tax (GST at 18%) is levied on all subscription fees. Customers in Karnataka are billed CGST + SGST; interstate customers are billed IGST.
                  </p>
                  <p>
                    <strong>C. Statutory Tax Invoices:</strong> We provide formal, gapless GST-compliant tax invoices detailing our GSTIN, SAC codes, and your institution&apos;s GSTIN (if provided) for input tax credit eligibility.
                  </p>
                  <p>
                    <strong>D. Renewal & Payment Terms:</strong> Invoices are payable upon receipt or within the credit terms agreed in writing. Failure to settle outstanding dues within 15 days of the due date may trigger grace period safeguards.
                  </p>
                </div>
              </section>

              {/* 5. Data Ownership & Intellectual Property */}
              <section id="data-ownership" className="scroll-mt-28 space-y-4">
                <div className="rounded-card border border-accent/20 bg-accent/5 p-6">
                  <div className="flex items-start gap-3">
                    <Database className="h-6 w-6 text-accent shrink-0 mt-0.5" />
                    <div>
                      <h2 className="font-display text-base font-bold text-primary">
                        5. Data Ownership & Intellectual Property Fencing
                      </h2>
                      <p className="mt-2 text-xs leading-6 text-slate-700">
                        We enforce an uncompromising boundary between customer data and platform intellectual property:
                      </p>
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="rounded-card border border-border bg-white p-4">
                    <h3 className="font-semibold text-primary">A. Your Institution Owns 100% of Your Data</h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      The institution retains exclusive ownership, title, copyright, and intellectual property rights in all data uploaded to the platform, including student rosters, exam results, faculty records, curriculum materials, and parent communications. xyz.com claims zero ownership over your data.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <h3 className="font-semibold text-primary">B. xyz.com Retains Software IP</h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      xyz.com Technologies Private Limited retains all right, title, and interest in and to the platform, including user interfaces, designs, software algorithms, APIs, database schemas, trademarks, logos, and accompanying documentation.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <h3 className="font-semibold text-primary">C. Limited License to Host</h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      You grant us a strictly limited, non-exclusive license to host, copy, process, and transmit your data solely to provide, secure, and maintain the platform services for your institution.
                    </p>
                  </div>
                </div>
              </section>

              {/* 6. Acceptable Use Policy */}
              <section id="acceptable-use" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  6. Acceptable Use Policy & Platform Restrictions
                </h2>
                <p>
                  Users agree not to engage in any prohibited activities:
                </p>
                <div className="rounded-card border border-border bg-white p-5 text-xs text-slate-700 space-y-2">
                  <p>• Do not probe, scan, or test the vulnerability of the system without prior written authorization.</p>
                  <p>• Do not reverse engineer, decompile, or disassemble any portion of the software.</p>
                  <p>• Do not attempt to bypass multi-tenant security boundaries or access another tenant&apos;s data.</p>
                  <p>• Do not upload unlawful, obscene, defamatory, harmful, or copyright-infringing content.</p>
                  <p>• Do not use automated scripts or scrapers to crawl or collect data from the services.</p>
                  <p>• Do not introduce viruses, trojans, worms, or other malicious code.</p>
                </div>
              </section>

              {/* 7. Availability & Service Levels */}
              <section id="sla" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  7. Service Availability & Maintenance
                </h2>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-card border border-border bg-white p-4">
                    <p className="font-bold text-primary">99.9% Target Uptime</p>
                    <p className="mt-1.5 text-xs text-muted-foreground">
                      We engineer our multi-tier infrastructure for high availability across academic peak periods, such as admission cycles and semester examinations.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <p className="font-bold text-primary">Scheduled Maintenance</p>
                    <p className="mt-1.5 text-xs text-muted-foreground">
                      Routine updates and system maintenance are conducted during low-traffic windows (typically 01:00–04:00 IST) with advance notice to administrators.
                    </p>
                  </div>
                </div>
              </section>

              {/* 8. Grace Periods & Termination */}
              <section id="termination" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  8. Grace Periods, Suspension & Termination
                </h2>
                <div className="rounded-card border border-border bg-white p-5 space-y-3">
                  <p>
                    <strong>A. Grace Period Degradation:</strong> Unlike consumer software that immediately cuts off access, educational institutions in payment arrears receive a <strong>15-day read-only grace period</strong>. Teachers and students can still view timetables and attendance records while finance resolves billing.
                  </p>
                  <p>
                    <strong>B. Termination by Customer:</strong> You may cancel your subscription at any time through your platform dashboard or by written notice to support. Cancellation will take effect at the conclusion of your current billing period.
                  </p>
                  <p>
                    <strong>C. 30-Day Data Export Guarantee:</strong> Following termination, your account enters a 30-day export window during which authorized administrators can download complete academic, student, and fee ledgers. After 30 days, tenant databases are securely wiped in accordance with our retention policy.
                  </p>
                </div>
              </section>

              {/* 9. Limitation of Liability */}
              <section id="liability" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  9. Limitation of Liability
                </h2>
                <p>
                  To the maximum extent permitted by applicable Indian law:
                </p>
                <div className="rounded-card border border-border bg-white p-5 text-xs text-slate-700 space-y-2.5">
                  <p>
                    Neither party shall be liable to the other for indirect, incidental, special, consequential, or punitive damages, including loss of profits, revenue, or academic goodwill.
                  </p>
                  <p>
                    The aggregate liability of xyz.com Technologies Private Limited arising out of or related to these Terms shall not exceed the total fees actually paid by the customer in the twelve (12) months preceding the incident giving rise to liability.
                  </p>
                </div>
              </section>

              {/* 10. Governing Law & Jurisdiction */}
              <section id="governing-law" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  10. Governing Law & Dispute Resolution
                </h2>
                <div className="rounded-card border border-border bg-white p-5 space-y-3">
                  <p>
                    These Terms are governed by and construed in accordance with the laws of the <strong>Republic of India</strong>, without regard to its conflict of law principles.
                  </p>
                  <p>
                    Any dispute, controversy, or claim arising out of or relating to these Terms shall be subject to the exclusive jurisdiction of the competent courts situated in <strong>Bengaluru, Karnataka, India</strong>.
                  </p>
                  <p>
                    The parties agree to make good-faith efforts to resolve any dispute through amicable negotiation for at least thirty (30) days prior to initiating formal legal proceedings.
                  </p>
                </div>
              </section>

              {/* Contact Information Footer */}
              <div className="border-t border-border pt-6 text-xs text-muted-foreground space-y-2">
                <p>
                  Questions about these Terms? Reach our legal counsel at <a href="mailto:legal@xyz.com" className="font-semibold text-accent hover:underline">legal@xyz.com</a>.
                </p>
                <div className="flex gap-4 pt-2">
                  <Link href="/privacy" className="font-semibold text-accent hover:underline">
                    Privacy Policy →
                  </Link>
                  <Link href="/refund-policy" className="font-semibold text-accent hover:underline">
                    Refund & Cancellation Policy →
                  </Link>
                  <Link href="/contact" className="font-semibold text-accent hover:underline">
                    Contact Us →
                  </Link>
                </div>
              </div>
            </article>
          </div>
        </Section>
      </section>
    </MarketingShell>
  );
}
