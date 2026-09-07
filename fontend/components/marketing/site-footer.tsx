import Link from "next/link";
import { GraduationCap } from "lucide-react";

/**
 * Public site footer — shared by every marketing page. Multi-column like a real
 * company site, with product, solution, company, legal, and resource links.
 */
const COLUMNS: { title: string; links: { label: string; href: string }[] }[] = [
  {
    title: "Product",
    links: [
      { label: "Features", href: "/features" },
      { label: "Modules", href: "/features#modules" },
      { label: "Security", href: "/security" },
      { label: "Pricing", href: "/pricing" },
    ],
  },
  {
    title: "Solutions",
    links: [
      { label: "Schools", href: "/solutions#schools" },
      { label: "Colleges", href: "/solutions#colleges" },
      { label: "Universities", href: "/solutions#universities" },
      { label: "Multi-campus groups", href: "/solutions#multi-campus" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "About", href: "/about" },
      { label: "Customers", href: "/customers" },
      { label: "Contact", href: "/contact" },
      { label: "FAQ", href: "/faq" },
    ],
  },
  {
    title: "Legal & Trust",
    links: [
      { label: "Privacy Policy", href: "/privacy" },
      { label: "Terms of Service", href: "/terms" },
      { label: "Refund Policy", href: "/refund-policy" },
      { label: "Security Overview", href: "/security" },
    ],
  },
  {
    title: "Account",
    links: [
      { label: "Sign in", href: "/account/login" },
      { label: "Create account", href: "/signup" },
      { label: "Support", href: "/support" },
      { label: "Book a demo", href: "/contact" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-primary text-slate-300">
      <div className="mx-auto max-w-7xl px-5 py-14 sm:px-8 lg:px-10">
        <div className="grid gap-10 lg:grid-cols-[1.4fr_repeat(5,1fr)]">
          <div className="max-w-xs">
            <Link href="/" className="flex items-center gap-2" aria-label="xyz.com home">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-white text-primary">
                <GraduationCap className="h-5 w-5" aria-hidden="true" />
              </span>
              <span className="font-display text-lg font-bold text-white">xyz.com</span>
            </Link>
            <p className="mt-4 text-sm leading-6 text-slate-400">
              The connected ERP and learning platform for schools, colleges and universities — one
              account, many institutions.
            </p>
            <p className="mt-4 text-xs text-slate-500">
              Made in India · GST-compliant billing · Asia/Kolkata
            </p>
          </div>

          {COLUMNS.map((col) => (
            <div key={col.title}>
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">{col.title}</h3>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <Link href={link.href} className="text-sm text-slate-300 transition hover:text-white">
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-4 border-t border-white/10 pt-6 text-xs text-slate-400 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-1">
            <span>© {new Date().getFullYear()} xyz.com Technologies Private Limited. Education, connected.</span>
            <span className="text-[11px] text-slate-500">
              CIN: U72900KA2024PTC189421 · GSTIN: 29AABCX1234F1Z9 · Bengaluru, Karnataka, India
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-5">
            <Link href="/privacy" className="hover:text-white transition">Privacy Policy</Link>
            <Link href="/terms" className="hover:text-white transition">Terms of Service</Link>
            <Link href="/refund-policy" className="hover:text-white transition">Refund & Cancellation</Link>
            <Link href="/contact" className="hover:text-white transition">Contact</Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
