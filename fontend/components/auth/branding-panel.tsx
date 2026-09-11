import { Logo } from "./logo";

/**
 * Left branding panel — design §5, §6.4
 * 45% width on desktop, hidden below lg (mobile shows a gradient top banner).
 */

const STATS = [
  { value: "500+", label: "Institutions" },
  { value: "22", label: "Roles Supported" },
  { value: "15", label: "Modules" },
] as const;

export function BrandingPanel() {
  return (
    <aside className="relative hidden flex-col justify-between overflow-hidden bg-primary p-10 lg:flex lg:w-[45%]">
      {/* Radial indigo gradient + subtle dot pattern */}
      <div className="bg-brand-radial absolute inset-0" aria-hidden="true" />
      <div
        className="bg-brand-dots absolute inset-0 opacity-[0.05]"
        aria-hidden="true"
      />

      <div className="relative z-10">
        <Logo variant="light" />
      </div>

      <div className="relative z-10">
        {/*
          A <p>, not an <h1>. This panel is `hidden lg:flex`, so on a phone it
          contributed no heading at all and every auth page had zero h1. It is
          also a slogan rather than the page's title — the card heading is.
        */}
        <p className="font-display text-[32px] font-bold leading-[1.2] text-white">
          One Platform for <br />
          <span className="text-accent-soft">Your Entire Institution</span>
        </p>

        <p className="mt-4 max-w-[360px] text-[15px] leading-6 text-[#94A3B8]">
          Attendance, exams, assignments, fees, hostel &amp; more — trusted by
          500+ schools and colleges across India.
        </p>

        <dl className="mt-10 flex gap-6">
          {STATS.map((stat, i) => (
            <div key={stat.label} className="flex gap-6">
              {i > 0 && <div className="w-px bg-white/10" aria-hidden="true" />}
              <div>
                <dt className="sr-only">{stat.label}</dt>
                <dd>
                  <span className="block font-display text-2xl font-bold text-white">
                    {stat.value}
                  </span>
                  <span className="text-xs text-[#94A3B8]">{stat.label}</span>
                </dd>
              </div>
            </div>
          ))}
        </dl>
      </div>

      <p className="relative z-10 text-xs text-white/40">
        © {new Date().getFullYear()} shikshasync.me · Secure, Multi-Tenant ERP + LMS
      </p>
    </aside>
  );
}
