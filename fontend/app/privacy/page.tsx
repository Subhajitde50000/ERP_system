import type { Metadata } from "next";
import Link from "next/link";
import { ShieldCheck, Mail, Lock, UserCheck, EyeOff, FileText, AlertTriangle } from "lucide-react";

import { MarketingShell, Section, SectionHeading } from "@/components/marketing/marketing-shell";

export const metadata: Metadata = {
  title: "Privacy Policy — xyz.com ERP & Learning Platform",
  description:
    "How xyz.com Technologies Private Limited collects, processes, protects, and handles personal data under the India DPDP Act 2023, GDPR, and international data protection standards.",
};

export default function PrivacyPolicyPage() {
  return (
    <MarketingShell>
      <Section className="!pb-8">
        <SectionHeading
          eyebrow="Legal & Compliance"
          title="Privacy Policy"
          lede="xyz.com is built with tenant isolation and data privacy at its architectural foundation. This policy details how we handle personal data for institutions, educators, students, and parents."
        />
        <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span className="rounded-full bg-slate-100 px-3 py-1 font-semibold text-slate-700">
            Effective: September 1, 2026
          </span>
          <span className="rounded-full bg-blue-50 px-3 py-1 font-semibold text-blue-700">
            Compliant with India DPDP Act 2023 & GDPR
          </span>
          <span>Version 2.0</span>
        </div>
      </Section>

      <section className="border-t border-border bg-[#F8FAFC]">
        <Section className="!py-12">
          <div className="grid gap-12 lg:grid-cols-[280px_1fr]">
            {/* Sticky Table of Contents on Desktop */}
            <aside className="hidden lg:block">
              <div className="sticky top-28 rounded-card border border-border bg-white p-5 shadow-sm">
                <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Table of Contents
                </p>
                <nav className="mt-4 space-y-2 text-xs">
                  <a href="#overview" className="block text-slate-600 transition hover:text-accent">
                    1. Scope & Relationship
                  </a>
                  <a href="#data-collection" className="block text-slate-600 transition hover:text-accent">
                    2. Information We Collect
                  </a>
                  <a href="#minors-dpdp" className="block font-semibold text-accent transition hover:underline">
                    3. Children & Minors (DPDP Act)
                  </a>
                  <a href="#legal-basis" className="block text-slate-600 transition hover:text-accent">
                    4. Legal Grounds for Processing
                  </a>
                  <a href="#advertising" className="block text-slate-600 transition hover:text-accent">
                    5. Cookies, Analytics & Ad Policy
                  </a>
                  <a href="#data-sharing" className="block text-slate-600 transition hover:text-accent">
                    6. Data Sharing & Sub-processors
                  </a>
                  <a href="#security" className="block text-slate-600 transition hover:text-accent">
                    7. Security & Tenant Isolation
                  </a>
                  <a href="#retention" className="block text-slate-600 transition hover:text-accent">
                    8. Retention & Deletion
                  </a>
                  <a href="#rights" className="block text-slate-600 transition hover:text-accent">
                    9. Data Principal & GDPR Rights
                  </a>
                  <a href="#grievance" className="block text-slate-600 transition hover:text-accent">
                    10. Grievance Officer & Contact
                  </a>
                </nav>
              </div>
            </aside>

            {/* Policy Content */}
            <article className="space-y-12 text-sm leading-relaxed text-[#334155]">
              {/* Highlight Card for School Leaders */}
              <div className="rounded-card border border-accent/20 bg-accent/5 p-6 sm:p-7">
                <div className="flex items-start gap-3.5">
                  <span className="rounded-lg bg-accent p-2 text-white">
                    <ShieldCheck className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 className="font-display text-base font-bold text-primary">
                      Our Privacy Commitments in Brief
                    </h3>
                    <ul className="mt-2.5 list-disc space-y-1.5 pl-4 text-xs text-slate-700">
                      <li>
                        <strong>We never sell your data:</strong> Neither student records, parent contacts, nor institutional academic records are ever sold, rented, or monetized.
                      </li>
                      <li>
                        <strong>Zero targeted ads to children:</strong> We strictly prohibit behavioral profiling, student tracking, and commercial advertising directed at minors.
                      </li>
                      <li>
                        <strong>Institutions own their data:</strong> Your school, college, or university retains 100% legal ownership of all uploaded data.
                      </li>
                    </ul>
                  </div>
                </div>
              </div>

              {/* 1. Scope & Relationship */}
              <section id="overview" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  1. Scope & Legal Relationship
                </h2>
                <p>
                  This Privacy Policy applies to all services, web applications, mobile applications, APIs, and portals operated by <strong>xyz.com Technologies Private Limited</strong> (&ldquo;xyz.com&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo;, or &ldquo;our&rdquo;).
                </p>
                <p>
                  In the context of the <strong>Digital Personal Data Protection Act, 2023 (DPDP Act)</strong> of India and the <strong>General Data Protection Regulation (GDPR)</strong>:
                </p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-card border border-border bg-white p-4">
                    <p className="font-semibold text-primary">When you are an Institution (Customer):</p>
                    <p className="mt-1.5 text-xs text-muted-foreground">
                      The Educational Institution is the <strong>Data Fiduciary (Data Controller)</strong> that determines the purposes of student and staff record processing. xyz.com acts strictly as the <strong>Data Processor</strong> carrying out processing in accordance with the institution&apos;s agreement.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <p className="font-semibold text-primary">When you register an Account directly:</p>
                    <p className="mt-1.5 text-xs text-muted-foreground">
                      For institutional administrators, account-holders who sign up on our website, and prospective clients submitting service inquiries, xyz.com acts as the <strong>Data Fiduciary (Data Controller)</strong> regarding account credentials and billing records.
                    </p>
                  </div>
                </div>
              </section>

              {/* 2. Information We Collect */}
              <section id="data-collection" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  2. Categories of Information We Collect
                </h2>
                <p>
                  We collect information strictly necessary to provide education management, academic operations, examinations, attendance, fee processing, and communication services:
                </p>
                <div className="space-y-3">
                  <div className="rounded-card border border-border bg-white p-4">
                    <h3 className="font-semibold text-primary">A. Institutional & Student Educational Records</h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Uploaded by or on behalf of schools and colleges: student full names, roll numbers, admission identifiers, enrollment history, attendance records, examination marks, grade cards, timetable allocations, and classroom assignment submissions.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <h3 className="font-semibold text-primary">B. Parent & Guardian Contact Information</h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Parent/guardian names, relationship to student, verified mobile numbers, and email addresses utilized for emergency notifications, fee payment receipts, and academic progress updates.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <h3 className="font-semibold text-primary">C. Staff & Faculty Data</h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Employee codes, department affiliations, academic qualifications, institutional email addresses, substitution schedules, and attendance records.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <h3 className="font-semibold text-primary">D. Technical, Session & Security Logs</h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      IP addresses, browser/OS user-agent, session timestamps, device identifiers, and audit logs recorded to ensure multi-tenant security, prevent brute-force attacks, and trace security events.
                    </p>
                  </div>
                </div>
              </section>

              {/* 3. Children & Minors (DPDP Act & GDPR-K) */}
              <section id="minors-dpdp" className="scroll-mt-28 space-y-4">
                <div className="rounded-card border border-amber-300 bg-amber-50 p-5">
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
                    <div>
                      <h2 className="font-display text-base font-bold text-amber-900">
                        3. Special Protections for Children and Minors (India DPDP Act 2023 §9)
                      </h2>
                      <p className="mt-1.5 text-xs text-amber-800">
                        Because our platform serves primary, secondary, and senior secondary schools, we enforce rigorous legal safeguards mandated by Section 9 of the Digital Personal Data Protection Act, 2023:
                      </p>
                    </div>
                  </div>
                </div>

                <ul className="space-y-3 pl-2">
                  <li className="flex items-start gap-2.5">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                    <span>
                      <strong>Verifiable Parental Consent:</strong> Educational institutions using xyz.com collect and maintain verifiable consent from parents or lawful guardians prior to enrolling minor students (individuals under the age of 18) onto the platform.
                    </span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                    <span>
                      <strong>No Behavioral Monitoring or Tracking:</strong> We strictly refrain from tracking, behavioral profiling, or conducting automated decision-making on student behavioral data for commercial purposes.
                    </span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                    <span>
                      <strong>No Targeted Advertising:</strong> We never display targeted advertisements, sponsored placements, or third-party marketing to any child user or student account.
                    </span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                    <span>
                      <strong>Child Well-Being Safeguard:</strong> We do not undertake any processing of personal data that is likely to cause detrimental effect on the well-being of a child.
                    </span>
                  </li>
                </ul>
              </section>

              {/* 4. Legal Grounds for Processing */}
              <section id="legal-basis" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  4. Legal Grounds for Processing
                </h2>
                <p>We process personal data only when lawful under applicable data protection statutes:</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-card border border-border bg-white p-4">
                    <p className="font-semibold text-primary">Performance of Educational Contract</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Fulfilling our SaaS service agreement with schools, delivering student grade books, recording attendance, and issuing fee receipts.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <p className="font-semibold text-primary">Statutory & Legal Obligations</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Retaining statutory GST billing records, complying with tax authorities, and satisfying court orders or government directives.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <p className="font-semibold text-primary">Consent</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Obtained from account-holders upon signup for platform access, newsletter communications, or optional feature participation.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <p className="font-semibold text-primary">Legitimate Interests & Platform Security</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Preventing fraud, rate limiting, thwarting cyber attacks, and maintaining reliable server uptime across all tenants.
                    </p>
                  </div>
                </div>
              </section>

              {/* 5. Cookies, Analytics & Ad Policy Compliance */}
              <section id="advertising" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  5. Cookies, Analytics & Google / Meta Ad Policies
                </h2>
                <p>
                  In compliance with Google Ad Policies and Meta Business Tool terms, we transparently disclose our use of browser cookies and tracking technologies:
                </p>
                <div className="rounded-card border border-border bg-white p-5 space-y-3">
                  <p>
                    <strong>A. Essential Security & Session Cookies:</strong> We utilize secure HTTP-only cookies (`SameSite=Lax`) to authenticate active sessions and protect against cross-site request forgery (CSRF). These are strictly required for the software to function.
                  </p>
                  <p>
                    <strong>B. Marketing Site Analytics:</strong> On our public marketing pages (such as `/pricing`, `/features`), we may use privacy-preserving web analytics and conversion measurement tags (e.g. Google Analytics 4, Meta Conversion API) to evaluate advertising performance and guide potential school partners.
                  </p>
                  <p>
                    <strong>C. Strict Firewall Between Marketing & School Portals:</strong> Third-party advertising tags and tracking pixels are <em>strictly excluded</em> from authenticated school portals, student dashboards, and parent views. Student records are never exposed to ad network trackers.
                  </p>
                  <p>
                    <strong>D. Your Opt-Out Choices:</strong> You can manage or disable cookies via your browser preferences. To opt out of Google Analytics tracking across the web, visit the Google Analytics Opt-Out Browser Add-on.
                  </p>
                </div>
              </section>

              {/* 6. Data Sharing & Sub-processors */}
              <section id="data-sharing" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  6. Data Sharing & Sub-Processors
                </h2>
                <p>
                  We share personal information solely with vetted third-party service providers who assist us in operating our cloud infrastructure, subject to stringent Data Processing Agreements (DPAs):
                </p>
                <ul className="space-y-2 pl-2">
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                    <span><strong>Cloud Infrastructure:</strong> Secure enterprise cloud hosting located in Tier-IV data centers in India.</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                    <span><strong>Transactional Communications:</strong> Reputable enterprise email and SMS gateways for OTP verification, reset passwords, and fee alerts.</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                    <span><strong>Payment Gateways:</strong> RBI-authorized payment aggregators (e.g., Razorpay, Cashfree) adhering to PCI-DSS Level 1 compliance. We do not store raw credit/debit card details.</span>
                  </li>
                </ul>
                <p>
                  We may also disclose data where required by Indian law, valid court warrants, or lawful requests from statutory regulatory authorities.
                </p>
              </section>

              {/* 7. Security & Tenant Isolation */}
              <section id="security" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  7. Data Security & Multi-Tenant Isolation
                </h2>
                <p>
                  We deploy multi-layered defense mechanisms to safeguard institutional data:
                </p>
                <div className="grid gap-4 sm:grid-cols-3">
                  <div className="rounded-card border border-border bg-white p-4">
                    <Lock className="h-5 w-5 text-accent" />
                    <p className="mt-2 font-semibold text-primary">Encryption Standards</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      All data in transit is encrypted using TLS 1.3. Databases and backups are encrypted at rest with AES-256.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <UserCheck className="h-5 w-5 text-accent" />
                    <p className="mt-2 font-semibold text-primary">Role-Based Access Control</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      18 distinct institution roles with strict permission fences. Users access only the data scoped to their specific role.
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-white p-4">
                    <EyeOff className="h-5 w-5 text-accent" />
                    <p className="mt-2 font-semibold text-primary">Tenant Boundary Isolation</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Every database query enforces tenant isolation. Cross-tenant leakage is prevented at both ORM and database engine levels.
                    </p>
                  </div>
                </div>
              </section>

              {/* 8. Retention & Deletion */}
              <section id="retention" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  8. Data Retention, Portability & Deletion
                </h2>
                <p>
                  Educational records are retained for the duration of the institution&apos;s subscription contract to fulfill ongoing academic and accreditation needs.
                </p>
                <p>
                  <strong>Grace Period & Export:</strong> If an institution discontinues its subscription, data is placed in a read-only grace state for 30 days, enabling administrators to export student marks, attendance, and fee ledgers in standardized formats (CSV/XLSX). After the 30-day grace period, all tenant data is securely purged or permanently anonymized from active databases.
                </p>
              </section>

              {/* 9. Data Principal & GDPR Rights */}
              <section id="rights" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  9. Your Rights as a Data Principal / Data Subject
                </h2>
                <p>
                  Under the India DPDP Act 2023 and the GDPR, you hold specific enforceable statutory rights:
                </p>
                <div className="rounded-card border border-border bg-white p-5 space-y-3">
                  <ul className="space-y-2.5">
                    <li className="flex items-start gap-2">
                      <span className="font-bold text-primary min-w-32">Right to Access:</span>
                      <span>Request a summary of personal data being processed and identities of parties with whom it was shared.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="font-bold text-primary min-w-32">Right to Correction:</span>
                      <span>Request correction of inaccurate or incomplete personal records.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="font-bold text-primary min-w-32">Right to Erasure:</span>
                      <span>Request erasure of personal data that is no longer necessary for the purpose it was collected.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="font-bold text-primary min-w-32">Right to Withdraw:</span>
                      <span>Withdraw consent previously granted for optional processing activities.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="font-bold text-primary min-w-32">Right to Nominate:</span>
                      <span>Nominate an individual to exercise rights on your behalf in case of death or incapacity (DPDP Act §14).</span>
                    </li>
                  </ul>
                  <p className="pt-2 text-xs text-muted-foreground border-t border-border">
                    * For student records uploaded by an institution, requests should primarily be submitted directly to the school or college administration. xyz.com will assist institutions promptly in fulfilling legitimate requests.
                  </p>
                </div>
              </section>

              {/* 10. Grievance Officer & Statutory Contact */}
              <section id="grievance" className="scroll-mt-28 space-y-4">
                <h2 className="font-display text-xl font-bold text-primary">
                  10. Statutory Grievance Redressal & Data Protection Officer
                </h2>
                <p>
                  In accordance with the <strong>Digital Personal Data Protection Act 2023</strong> and the <strong>Information Technology (Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021</strong>, the details of our designated Grievance Officer are published below:
                </p>

                <div className="rounded-card border border-border bg-white p-6">
                  <div className="grid gap-6 sm:grid-cols-2">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        Designated Grievance Officer
                      </p>
                      <p className="mt-1 font-display text-base font-bold text-primary">
                        Grievance Redressal & Privacy Officer
                      </p>
                      <p className="mt-1 text-xs text-slate-600">
                        xyz.com Technologies Private Limited
                      </p>
                      <p className="mt-0.5 text-xs text-slate-500">
                        CIN: U72900KA2024PTC189421
                      </p>

                      <div className="mt-4 space-y-1.5 text-xs">
                        <p className="flex items-center gap-2">
                          <Mail className="h-4 w-4 text-accent" />
                          <a href="mailto:grievance@xyz.com" className="text-accent font-semibold hover:underline">
                            grievance@xyz.com
                          </a>
                        </p>
                        <p className="flex items-center gap-2 text-slate-600">
                          <FileText className="h-4 w-4 text-slate-400" />
                          <span>Legal & Compliance: legal@xyz.com</span>
                        </p>
                      </div>
                    </div>

                    <div className="rounded-xl bg-slate-50 p-4 text-xs space-y-2">
                      <p className="font-semibold text-primary">Registered Address:</p>
                      <p className="text-slate-600 leading-relaxed">
                        Prestige Tech Park, 4th Floor, Marathahalli - Sarjapur Outer Ring Road,
                        Kadubeesanahalli, Bengaluru, Karnataka 560103, India.
                      </p>
                      <p className="pt-2 font-semibold text-primary">Statutory SLA:</p>
                      <p className="text-slate-600">
                        • Acknowledgment: within 48 hours of receipt.<br />
                        • Redressal: within 30 days under the DPDP Act.
                      </p>
                    </div>
                  </div>
                </div>
              </section>

              {/* Updates to this Policy */}
              <div className="border-t border-border pt-6 text-xs text-muted-foreground">
                <p>
                  We may periodically revise this Privacy Policy to reflect statutory amendments or product enhancements. Substantial modifications will be highlighted on our website or notified to account holders via email.
                </p>
                <div className="mt-4 flex gap-4">
                  <Link href="/terms" className="font-semibold text-accent hover:underline">
                    Terms of Service →
                  </Link>
                  <Link href="/refund-policy" className="font-semibold text-accent hover:underline">
                    Refund & Cancellation Policy →
                  </Link>
                  <Link href="/contact" className="font-semibold text-accent hover:underline">
                    Contact Our Team →
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
