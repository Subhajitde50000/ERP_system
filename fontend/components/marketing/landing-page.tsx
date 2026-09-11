import Link from "next/link";
import {
  ArrowRight,
  CalendarCheck2,
  Check,
  ChevronRight,
  HeartHandshake,
  Quote,
  ShieldCheck,
  Sparkles,
  UsersRound,
} from "lucide-react";

import { ServiceRequestForm } from "@/components/marketing/service-request-form";
import { CtaBand, MarketingShell, Section, SectionHeading } from "@/components/marketing/marketing-shell";
import { AUDIENCES, FAQS, MODULES, STATS, TESTIMONIALS } from "@/lib/marketing";

const CAPABILITIES = [
  { title: "Academic operations", copy: "Attendance, timetables, assessments and results in one reliable workspace.", points: ["Class & exam-hall attendance", "Conflict-aware timetables", "Marks to report cards"] },
  { title: "Teaching & learning", copy: "Assignments, content, discussions and progress tools that keep learning moving.", points: ["Milestone coursework", "Shared content library", "Threaded discussions"] },
  { title: "Institution management", copy: "Admissions, fees, people and optional services, designed around your institution.", points: ["Online fee collection", "Admissions & enrolment", "HR, hostel, transport"] },
];

const STEPS = [
  { n: "01", title: "Create your account", copy: "Sign up at shikshasync.me with your name, email and password — one account for every institution you own." },
  { n: "02", title: "Verify & open the dashboard", copy: "Confirm your email and land on your platform dashboard: institutions, billing and support." },
  { n: "03", title: "Create an institution", copy: "Choose a plan, claim a subdomain like green.shikshasync.me, and pay. Provisioning is automatic." },
  { n: "04", title: "Run daily ERP", copy: "Open green.shikshasync.me for attendance, exams, fees and more — a separate, secure login for your team." },
];

export function LandingPage() {
  return (
    <MarketingShell>
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative isolate overflow-hidden border-b border-slate-100 bg-[#F8FAFC]">
        <div className="absolute inset-x-0 top-0 -z-10 h-full bg-[radial-gradient(circle_at_84%_18%,rgba(6,182,212,0.16),transparent_24rem),radial-gradient(circle_at_14%_14%,rgba(79,70,229,0.14),transparent_26rem)]" />
        <div className="mx-auto grid max-w-7xl gap-12 px-5 py-16 sm:px-8 lg:grid-cols-[1.08fr_.92fr] lg:items-center lg:px-10 lg:py-24">
          <div className="max-w-2xl">
            <p className="inline-flex items-center gap-2 rounded-full border border-accent-border bg-white px-3 py-1.5 text-xs font-semibold text-accent-active shadow-sm">
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" /> One account. Many institutions. Zero chaos.
            </p>
            <h1 className="mt-6 font-display text-4xl font-extrabold leading-[1.08] tracking-tight text-primary sm:text-5xl lg:text-6xl">
              The connected home for your institution.
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-[#475569]">
              Attendance, exams, fees, hostel, LMS and more — on one secure, multi-tenant platform.
              Run a single campus or a whole group, and manage them all from one shikshasync.me account.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link href="/signup" className="inline-flex h-12 items-center justify-center gap-2 rounded-field bg-accent px-5 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover">
                Start free trial <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link href="/contact" className="inline-flex h-12 items-center justify-center gap-2 rounded-field border border-border bg-white px-5 text-sm font-semibold text-primary transition hover:border-accent">
                Book a demo <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
            <p className="mt-5 flex items-center gap-2 text-sm text-muted-foreground">
              <Check className="h-4 w-4 text-success-text" aria-hidden="true" /> 14-day free trial · no card required · automatic provisioning
            </p>
          </div>

          <HeroCard />
        </div>
      </section>

      {/* ── Trusted by / stats ───────────────────────────────────────────── */}
      <section className="border-b border-border bg-white">
        <div className="mx-auto max-w-7xl px-5 py-10 sm:px-8 lg:px-10">
          <p className="text-center text-xs font-bold uppercase tracking-[0.16em] text-[#94A3B8]">
            Trusted by 500+ schools, colleges and universities across India
          </p>
          <div className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-4">
            {STATS.map((s) => (
              <div key={s.label} className="text-center">
                <p className="font-display text-3xl font-extrabold text-primary">{s.value}</p>
                <p className="mt-1 text-xs text-muted-foreground">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Capabilities ─────────────────────────────────────────────────── */}
      <Section id="platform">
        <SectionHeading
          eyebrow="The platform"
          title="Run the day. Support every learner. See what matters."
          lede="shikshasync.me connects the work usually spread across paper, spreadsheets and disconnected apps — without asking your teams to change everything at once."
        />
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {CAPABILITIES.map((c) => (
            <article key={c.title} className="flex flex-col rounded-card border border-border p-6 transition hover:-translate-y-1 hover:border-accent-border hover:shadow-card">
              <h3 className="font-display text-xl font-bold text-primary">{c.title}</h3>
              <p className="mt-2 text-sm leading-6 text-[#64748B]">{c.copy}</p>
              <ul className="mt-4 space-y-2">
                {c.points.map((p) => (
                  <li key={p} className="flex items-center gap-2 text-sm text-[#475569]">
                    <Check className="h-4 w-4 shrink-0 text-success-text" aria-hidden="true" /> {p}
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </Section>

      {/* ── Modules ──────────────────────────────────────────────────────── */}
      <section className="bg-[#F8FAFC]">
        <Section>
          <SectionHeading
            eyebrow="16 modules, one platform"
            title="Everything your institution runs, in one place."
            lede="Eight core academic modules are always included. Switch on optional modules — finance, hostel, transport, HR and more — as you grow."
            align="center"
          />
          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {MODULES.map((m) => (
              <article key={m.key} className="rounded-card border border-border bg-white p-5 transition hover:-translate-y-0.5 hover:shadow-card">
                <div className="flex items-center justify-between">
                  <span className="inline-flex rounded-xl bg-accent-light p-2.5 text-accent">
                    <m.icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  {m.category === "Core" ? (
                    <span className="rounded-full bg-success-light px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-success-text">Core</span>
                  ) : (
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Optional</span>
                  )}
                </div>
                <h3 className="mt-4 font-display text-base font-bold text-primary">{m.name}</h3>
                <p className="mt-1 text-xs leading-5 text-[#64748B]">{m.blurb}</p>
              </article>
            ))}
          </div>
          <div className="mt-10 text-center">
            <Link href="/features" className="inline-flex items-center gap-1 text-sm font-semibold text-accent hover:underline">
              Explore every module <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </Section>
      </section>

      {/* ── Audiences ────────────────────────────────────────────────────── */}
      <Section>
        <SectionHeading
          eyebrow="Built for every institution"
          title="One platform, shaped to how you work."
          lede="Whether you run a single school or a multi-campus group, shikshasync.me adapts to your structure — not the other way around."
        />
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {AUDIENCES.map((a) => (
            <Link
              key={a.slug}
              href={`/solutions#${a.slug}`}
              className="group flex flex-col rounded-card border border-border p-6 transition hover:-translate-y-1 hover:border-accent-border hover:shadow-card"
            >
              <span className="inline-flex w-fit rounded-xl bg-accent-light p-2.5 text-accent">
                <a.icon className="h-5 w-5" aria-hidden="true" />
              </span>
              <h3 className="mt-4 font-display text-lg font-bold text-primary">{a.title}</h3>
              <p className="text-xs font-semibold uppercase tracking-wide text-accent">{a.tagline}</p>
              <p className="mt-2 flex-1 text-sm leading-6 text-[#64748B]">{a.description}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-accent">
                Learn more <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" aria-hidden="true" />
              </span>
            </Link>
          ))}
        </div>
      </Section>

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section className="bg-primary text-white">
        <Section>
          <SectionHeading
            eyebrow="How it works"
            title="From sign-up to your first class in minutes."
            lede="The account-holder model that powers shikshasync.me: create an account once, then own and manage as many institutions as you need."
            tone="light"
          />
          <ol className="mt-12 grid gap-6 md:grid-cols-4">
            {STEPS.map((s) => (
              <li key={s.n} className="rounded-card border border-white/10 bg-white/5 p-6">
                <span className="font-display text-2xl font-extrabold text-cyan-300">{s.n}</span>
                <h3 className="mt-3 font-display text-lg font-bold text-white">{s.title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-300">{s.copy}</p>
              </li>
            ))}
          </ol>
        </Section>
      </section>

      {/* ── Testimonials ─────────────────────────────────────────────────── */}
      <section className="bg-[#F8FAFC]">
        <Section>
          <SectionHeading
            eyebrow="Loved by educators"
            title="The difference a connected platform makes."
            align="center"
          />
          <div className="mt-12 grid gap-5 md:grid-cols-3">
            {TESTIMONIALS.map((t) => (
              <figure key={t.name} className="flex flex-col rounded-card border border-border bg-white p-6 shadow-card">
                <Quote className="h-7 w-7 text-accent-soft" aria-hidden="true" />
                <blockquote className="mt-3 flex-1 text-sm leading-6 text-[#334155]">“{t.quote}”</blockquote>
                <figcaption className="mt-5 border-t border-border pt-4">
                  <p className="text-sm font-bold text-primary">{t.name}</p>
                  <p className="text-xs text-muted-foreground">{t.role}, {t.org}</p>
                </figcaption>
              </figure>
            ))}
          </div>
        </Section>
      </section>

      {/* ── Security teaser ──────────────────────────────────────────────── */}
      <Section>
        <div className="grid items-center gap-10 lg:grid-cols-2">
          <div>
            <SectionHeading
              eyebrow="Security & trust"
              title="Isolated by design. Audited by default."
              lede="Every institution is a separate tenant with origin-bound tokens and role-based access. Your data never crosses institutions — and every privileged action is recorded."
            />
            <div className="mt-6">
              <Link href="/security" className="inline-flex items-center gap-1 text-sm font-semibold text-accent hover:underline">
                See how we keep data safe <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {[
              { icon: ShieldCheck, title: "Tenant isolation", copy: "Row-level data separation per institution." },
              { icon: UsersRound, title: "18 roles", copy: "Fine-grained module.action.scope permissions." },
              { icon: CalendarCheck2, title: "99.95% uptime", copy: "Health-checked, graceful degradation." },
              { icon: Sparkles, title: "GST invoicing", copy: "Gapless, compliant billing out of the box." },
            ].map((f) => (
              <div key={f.title} className="rounded-card border border-border p-5">
                <span className="inline-flex rounded-xl bg-accent-light p-2 text-accent">
                  <f.icon className="h-5 w-5" aria-hidden="true" />
                </span>
                <h3 className="mt-3 text-sm font-bold text-primary">{f.title}</h3>
                <p className="mt-1 text-xs leading-5 text-[#64748B]">{f.copy}</p>
              </div>
            ))}
          </div>
        </div>
      </Section>

      {/* ── FAQ ──────────────────────────────────────────────────────────── */}
      <section className="bg-[#F8FAFC]">
        <Section>
          <SectionHeading eyebrow="FAQ" title="Questions, answered." align="center" />
          <div className="mx-auto mt-10 max-w-3xl divide-y divide-border rounded-card border border-border bg-white">
            {FAQS.slice(0, 4).map((f) => (
              <details key={f.q} className="group p-5">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-semibold text-primary">
                  {f.q}
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-open:rotate-90" aria-hidden="true" />
                </summary>
                <p className="mt-3 text-sm leading-6 text-[#64748B]">{f.a}</p>
              </details>
            ))}
          </div>
          <div className="mt-8 text-center">
            <Link href="/faq" className="text-sm font-semibold text-accent hover:underline">View all FAQs</Link>
          </div>
        </Section>
      </section>

      {/* ── Consultation ─────────────────────────────────────────────────── */}
      <Section id="consultation">
        <div className="grid gap-10 lg:grid-cols-[.8fr_1.2fr] lg:gap-16">
          <div>
            <SectionHeading
              eyebrow="Talk with us"
              title="Let’s plan your next step."
              lede="Tell us about your institution. A specialist will help you map the right setup and implementation path."
            />
            <div className="mt-8 space-y-4">
              <Info icon={UsersRound} title="For institution leaders" copy="Designed for administrators and decision makers." />
              <Info icon={HeartHandshake} title="Human support" copy="A real conversation, with a guided rollout plan." />
            </div>
          </div>
          <div className="rounded-[20px] border border-border bg-[#F8FAFC] p-5 shadow-card sm:p-8">
            <h3 className="font-display text-2xl font-bold text-primary">Book a platform consultation</h3>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">We’ll respond within one business day.</p>
            <div className="mt-6">
              <ServiceRequestForm />
            </div>
          </div>
        </div>
      </Section>

      <CtaBand />
    </MarketingShell>
  );
}

function HeroCard() {
  return (
    <div className="rounded-[24px] border border-white/80 bg-white p-4 shadow-[0_24px_60px_rgba(15,23,42,0.12)] sm:p-5">
      <div className="rounded-[18px] bg-primary p-5 text-white sm:p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-200">Institution overview</p>
            <h2 className="mt-2 font-display text-xl font-bold">Everything in its place</h2>
          </div>
          <span className="rounded-lg bg-white/10 p-2">
            <CalendarCheck2 className="h-5 w-5" aria-hidden="true" />
          </span>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-3">
          <Metric value="24" label="active classes" />
          <Metric value="96%" label="attendance recorded" />
          <Metric value="1" label="shared workspace" />
          <Metric value="4" label="teams connected" />
        </div>
        <div className="mt-5 rounded-xl bg-white/10 p-4">
          <div className="flex items-center gap-3">
            <span className="rounded-lg bg-cyan-400/20 p-2 text-cyan-200">
              <Sparkles className="h-4 w-4" aria-hidden="true" />
            </span>
            <div>
              <p className="text-sm font-semibold">A platform shaped around you</p>
              <p className="mt-0.5 text-xs text-slate-300">Start with the tools your institution needs.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Metric({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-xl bg-white/10 p-3">
      <p className="font-display text-xl font-bold">{value}</p>
      <p className="mt-1 text-[11px] text-slate-300">{label}</p>
    </div>
  );
}

function Info({ icon: Icon, title, copy }: { icon: typeof UsersRound; title: string; copy: string }) {
  return (
    <div className="flex gap-3">
      <span className="mt-0.5 rounded-lg bg-accent-light p-2 text-accent">
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <div>
        <h3 className="text-sm font-bold text-primary">{title}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{copy}</p>
      </div>
    </div>
  );
}
