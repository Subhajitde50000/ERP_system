"use client";

import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Building2,
  Globe,
  LayoutGrid,
  ListChecks,
  PartyPopper,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  AvailableBadge,
  CheckoutHeader,
  Field,
  inputClass,
  ModuleCheckbox,
  PrimaryButton,
  PriceSummary,
} from "./checkout-ui";
import { ReviewStep } from "./review-step";
import { SuccessStep } from "./success-step";
import { tenantHost, tenantUrl } from "@/lib/platform-shared";
import { checkSubdomain, createOrder, fetchQuote, formatINR, getCatalog, payOrder } from "@/lib/signup";
import type {
  Catalog,
  InstitutionDraft,
  OwnerDraft,
  ModuleInfo,
  PlanInfo,
  ProvisionResult,
  Quote,
  SubdomainCheck,
} from "@/lib/signup";

/**
 * Public checkout — the full Step 1 → Step 8 journey:
 *
 *   Platform account → Institution URL → Plan → Modules (fixed or BYO) →
 *   Review (+coupon) → Payment → Automatic provisioning → Success
 *
 * The backend is the price source of truth (`fetchQuote`), but a local
 * mirror keeps the live price responsive while the network round-trip is
 * in flight and keeps the demo reviewable without a running API.
 */

type Mode = "PURCHASE" | "TRIAL";

interface Draft {
  owner: OwnerDraft;
  institution: InstitutionDraft;
  urlSlug: string;
  password: string;
  planSlug: string | null;
  moduleKeys: string[];
  billingCycle: "MONTHLY" | "YEARLY";
  couponCode: string;
  mode: Mode;
}

const DRAFT_KEY = "erp_signup_draft";

const EMPTY_DRAFT: Draft = {
  owner: {
    name: "",
    email: "",
  },
  institution: {
    name: "",
    type: "COLLEGE",
    email: "",
    phone: null,
    country: "India",
    state: null,
    city: null,
    address: null,
  },
  urlSlug: "",
  password: "",
  planSlug: null,
  moduleKeys: [],
  billingCycle: "MONTHLY",
  couponCode: "",
  mode: "PURCHASE",
};

function loadDraft(): Draft {
  if (typeof localStorage === "undefined") return EMPTY_DRAFT;
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return EMPTY_DRAFT;
    return { ...EMPTY_DRAFT, ...(JSON.parse(raw) as Partial<Draft>) };
  } catch {
    return EMPTY_DRAFT;
  }
}

/** Local mirror of the backend quote rules (bundled modules are free). */
function clientQuote(catalog: Catalog, draft: Draft): Quote {
  if (draft.mode === "TRIAL") {
    return {
      mode: "TRIAL",
      planSlug: draft.planSlug ?? "",
      billingCycle: draft.billingCycle,
      moduleKeys: draft.moduleKeys,
      currency: "INR",
      lines: [{ label: "Free trial", amount: 0 }],
      subtotal: 0,
      discount: 0,
      total: 0,
      coupon: null,
    };
  }
  const plan = catalog.plans.find((p) => p.slug === draft.planSlug);
  const lines: { label: string; amount: number }[] = [];
  let subtotal = 0;
  const mult = draft.billingCycle === "YEARLY" ? 12 : 1;
  if (plan) {
    const price = draft.billingCycle === "YEARLY" ? plan.priceYearly : plan.priceMonthly;
    lines.push({ label: `${plan.name} plan · ${draft.billingCycle === "YEARLY" ? "yearly" : "monthly"}`, amount: price });
    subtotal += price;
  }
  const bundled = new Set(plan?.allowedModules ?? []);
  const selected = new Set(draft.moduleKeys);
  for (const m of catalog.modules) {
    if (m.isCore || bundled.has(m.key) || !selected.has(m.key)) continue;
    const amount = m.priceMonthly * mult;
    lines.push({ label: `${m.name} module`, amount });
    subtotal += amount;
    bundled.add(m.key);
  }
  let discount = 0;
  if (draft.couponCode.trim() && subtotal > 0) {
    const code = draft.couponCode.trim().toUpperCase();
    if (code === "WELCOME10") discount = Math.round(subtotal * 0.1);
    else if (code === "LAUNCH500") discount = Math.min(500, subtotal);
  }
  return {
    mode: "PURCHASE",
    planSlug: draft.planSlug ?? "",
    billingCycle: draft.billingCycle,
    moduleKeys: draft.moduleKeys,
    currency: "INR",
    lines,
    subtotal,
    discount,
    total: Math.max(subtotal - discount, 0),
    coupon: discount > 0 ? { code: draft.couponCode.trim().toUpperCase(), discountType: "", value: discount, message: "Coupon applied" } : null,
  };
}

export function CheckoutFlow({
  initialPlan,
  initialMode,
  orderId,
  ownerToken,
}: {
  /** Pre-selected plan from ?plan= on the pricing page. */
  initialPlan?: string | null;
  /** Trial mode from ?mode=trial. */
  initialMode?: "TRIAL" | null;
  /** Recover the success page after a refresh (?order=<id>&done=1). */
  orderId?: string | null;
  /**
   * When set, the checkout runs against the owner-scoped endpoints
   * (/owner/orders) so the provisioned institution is linked to the signed-in
   * owner's account. Anonymous public checkout leaves it unset.
   */
  ownerToken?: string | null;
}) {
  const router = useRouter();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  // Lazy initialiser: the persisted draft (plus any ?plan=/?mode= overrides)
  // is known on first render — no effect round-trip needed.
  const [draft, setDraft] = useState<Draft>(() => {
    const saved = loadDraft();
    if (initialMode) saved.mode = initialMode;
    if (initialPlan === "custom") saved.planSlug = "custom";
    else if (initialPlan) saved.planSlug = initialPlan;
    return saved;
  });
  const [step, setStep] = useState(0);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [provision, setProvision] = useState<ProvisionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const quoteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load the catalogue on mount.
  useEffect(() => {
    let cancelled = false;
    getCatalog()
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch(() => setCatalog(null));
    return () => {
      cancelled = true;
    };
  }, []);

  // Recover the success page from ?order=<id>&done=1 (post-refresh).
  useEffect(() => {
    if (!orderId || provision) return;
    let cancelled = false;
    import("@/lib/signup").then(({ fetchOrderResult }) =>
      fetchOrderResult(orderId, ownerToken ?? undefined)
        .then((result) => {
          if (!cancelled) setProvision(result);
        })
        .catch(() => {
          /* order not found — the wizard continues normally */
        }),
    );
    return () => {
      cancelled = true;
    };
  }, [orderId, provision, ownerToken]);

  // Persist the draft as it changes.
  useEffect(() => {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    }
  }, [draft]);

  // Server-authoritative quote, debounced; local quote covers the gap.
  const localQuote = useMemo(
    () => (catalog ? clientQuote(catalog, draft) : null),
    [catalog, draft],
  );
  useEffect(() => {
    if (!catalog || draft.mode !== "PURCHASE" || !draft.planSlug) return;
    if (quoteTimer.current) clearTimeout(quoteTimer.current);
    quoteTimer.current = setTimeout(async () => {
      try {
        const q = await fetchQuote({
          mode: "PURCHASE",
          plan: draft.planSlug!,
          modules: draft.moduleKeys,
          cycle: draft.billingCycle,
          coupon: draft.couponCode.trim() || null,
        });
        setQuote(q);
      } catch {
        /* keep the local quote — server is unreachable */
      }
    }, 350);
    return () => {
      if (quoteTimer.current) clearTimeout(quoteTimer.current);
    };
  }, [catalog, draft, localQuote]);

  function update(patch: Partial<Draft>) {
    setDraft((d) => ({ ...d, ...patch }));
  }

  function chooseMode(mode: Mode) {
    update({ mode });
    setStep(0);
  }

  // Server quote once it lands; the local mirror keeps the UI live meanwhile.
  const effectiveQuote = quote ?? localQuote;

  const plan = catalog?.plans.find((p) => p.slug === draft.planSlug) ?? null;
  const selectedOptional = catalog?.modules.filter(
    (m) => !m.isCore && draft.moduleKeys.includes(m.key),
  );

  /* ── Step 8 — Success (also reached directly via ?order=&done=1) ───────── */
  if (provision) {
    return (
      <CheckoutShell step={5} onBack={undefined}>
        <SuccessStep result={provision} />
      </CheckoutShell>
    );
  }

  /* ── Step 1 — Platform owner account + institution draft ───────────────── */
  if (step === 0) {
    return (
      <CheckoutShell step={step} onBack={undefined}>
        <RegistrationStep
          draft={draft}
          onChange={update}
          onNext={() => setStep(1)}
          onStartTrial={() => chooseMode("TRIAL")}
          busy={busy}
          setBusy={setBusy}
          isOwnerSession={Boolean(ownerToken)}
        />
      </CheckoutShell>
    );
  }

  /* ── Step 2 — Institution URL ───────────────────────────────────────────── */
  if (step === 1) {
    return (
      <CheckoutShell step={step} onBack={() => setStep(0)}>
        <UrlStep draft={draft} onChange={update} onNext={() => setStep(2)} />
      </CheckoutShell>
    );
  }

  /* ── Step 3 — Plan selection ────────────────────────────────────────────── */
  if (step === 2) {
    return (
      <CheckoutShell step={step} onBack={() => setStep(1)}>
        <PlanStep
          catalog={catalog}
          draft={draft}
          onChange={update}
          onContinue={() => setStep(3)}
        />
      </CheckoutShell>
    );
  }

  /* ── Step 4 — Modules (4A fixed package / 4B build your own) ────────────── */
  if (step === 3) {
    return (
      <CheckoutShell step={step} onBack={() => setStep(2)}>
        <ModulesStep
          catalog={catalog}
          draft={draft}
          plan={plan}
          quote={effectiveQuote}
          onChange={update}
          onContinue={() => setStep(4)}
        />
      </CheckoutShell>
    );
  }

  /* ── Step 5 — Order review ──────────────────────────────────────────────── */
  if (step === 4) {
    return (
      <CheckoutShell step={step} onBack={() => setStep(3)}>
        <ReviewStep
          draft={draft}
          planName={plan?.name ?? draft.planSlug ?? ""}
          selectedOptional={selectedOptional ?? []}
          quote={effectiveQuote}
          onChange={update}
          onContinue={() => setStep(5)}
        />
      </CheckoutShell>
    );
  }

  /* ── Step 6 → 7 — Payment, provisioning ─────────────────────────────────── */
  return (
    <CheckoutShell step={5} onBack={() => setStep(4)}>
      <PaymentStep
          draft={draft}
          quote={effectiveQuote}
          busy={busy}
          setBusy={setBusy}
          ownerToken={ownerToken ?? undefined}
          onPaid={(result) => {
            setProvision(result);
            const doneUrl = ownerToken
              ? `/account/institutions/new?order=${result.orderId}&done=1`
              : `/signup?order=${result.orderId}&done=1`;
            router.replace(doneUrl);
          }}
        />
    </CheckoutShell>
  );
}

/** Page frame shared by every checkout step. */
function CheckoutShell({
  step,
  onBack,
  children,
}: {
  step: number;
  onBack?: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-[#F8FAFC]">
      <CheckoutHeader step={step} onBack={onBack} />
      <main className="mx-auto max-w-3xl px-5 py-10 sm:px-8">{children}</main>
    </div>
  );
}

/* ── Step 1 — Registration ───────────────────────────────────────────────── */

function RegistrationStep({
  draft,
  onChange,
  onNext,
  onStartTrial,
  busy,
  setBusy,
  isOwnerSession = false,
}: {
  draft: Draft;
  onChange: (patch: Partial<Draft>) => void;
  onNext: () => void;
  onStartTrial: () => void;
  busy: boolean;
  setBusy: (v: boolean) => void;
  isOwnerSession?: boolean;
}) {
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  function validate(): boolean {
    const e: Record<string, string> = {};
    const inst = draft.institution;
    if (!isOwnerSession) {
      if (draft.owner.name.trim().length < 2) e.ownerName = "Enter the owner name";
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(draft.owner.email)) e.ownerEmail = "Enter a valid owner email";
    }
    if (inst.name.trim().length < 2) e.name = "Enter the institution name";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(inst.email)) e.email = "Enter a valid official email";
    if (!inst.phone) e.phone = "Enter a phone number";
    if (!inst.country.trim()) e.country = "Enter the country";
    if (!inst.state?.trim()) e.state = "Enter the state";
    if (!inst.city?.trim()) e.city = "Enter the city";
    if (draft.password.length < 6) e.password = "Password must be at least 6 characters";
    else if (draft.password !== confirm) e.confirm = "Passwords do not match";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function handleNext() {
    if (!validate()) return;
    setBusy(true);
    // Cross-check the slug before leaving registration so a taken URL is
    // caught early (the URL step re-checks live anyway).
    const slug = slugify(draft.institution.name);
    try {
      const check = await checkSubdomain(slug);
      if (!check.available) {
        // Still fine — the URL step will offer suggestions.
        onChange({ urlSlug: "" });
      } else {
        onChange({ urlSlug: check.slug });
      }
    } catch {
      /* offline — proceed; the URL step handles the live check */
    }
    setBusy(false);
    onNext();
  }

  const inst = draft.institution;
  return (
    <div className="animate-fade-up">
      <StepTitle
        icon={<Building2 className="h-5 w-5" aria-hidden="true" />}
        title={isOwnerSession ? "Set up your new institution" : "Create your platform account"}
        subtitle={
          isOwnerSession
            ? "Configure institution identity and admin credentials. This institution will be linked to your platform account."
            : "Sign up once at shikshasync.me. This owner account can create and manage multiple institutions, billing, invoices and support."
        }
      />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void handleNext();
        }}
        className="mt-8 space-y-5 rounded-card border border-border bg-white p-6 shadow-card sm:p-8"
      >
        {!isOwnerSession && (
          <>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Owner Name" required error={errors.ownerName}>
                <input
                  className={inputClass}
                  value={draft.owner.name}
                  onChange={(e) => onChange({ owner: { ...draft.owner, name: e.target.value } })}
                  placeholder="Rahul Sharma"
                  autoComplete="name"
                />
              </Field>
              <Field label="Owner Email / Platform Login" required error={errors.ownerEmail}>
                <input
                  className={inputClass}
                  type="email"
                  value={draft.owner.email}
                  onChange={(e) => onChange({ owner: { ...draft.owner, email: e.target.value } })}
                  placeholder="rahul@gmail.com"
                  autoComplete="email"
                />
              </Field>
            </div>

            <div className="rounded-field border border-accent-border bg-accent-light px-4 py-3 text-sm text-[#3730A3]">
              Your platform account is the owner account. After email verification, sign in at
              shikshasync.me/login to open My Institutions, Billing, Subscriptions, Invoices,
              Support Tickets and Profile. Daily ERP users still sign in at the
              institution subdomain.
            </div>
          </>
        )}

        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Institution Name" required error={errors.name}>
            <input
              className={inputClass}
              value={inst.name}
              onChange={(e) => onChange({ institution: { ...inst, name: e.target.value } })}
              placeholder="Green College"
            />
          </Field>
          <Field label="Institution Type" required>
            <select
              className={inputClass}
              value={inst.type}
              onChange={(e) =>
                onChange({ institution: { ...inst, type: e.target.value as "SCHOOL" | "COLLEGE" } })
              }
            >
              <option value="COLLEGE">College / University</option>
              <option value="SCHOOL">School</option>
            </select>
          </Field>
          <Field label="Official Email" required error={errors.email}>
            <input
              className={inputClass}
              type="email"
              value={inst.email}
              onChange={(e) => onChange({ institution: { ...inst, email: e.target.value } })}
              placeholder="admin@green.edu"
            />
          </Field>
          <Field label="Phone Number" required error={errors.phone}>
            <input
              className={inputClass}
              value={inst.phone ?? ""}
              onChange={(e) => onChange({ institution: { ...inst, phone: e.target.value || null } })}
              placeholder="+91 98765 43210"
            />
          </Field>
          <Field label="Country" required error={errors.country}>
            <input
              className={inputClass}
              value={inst.country}
              onChange={(e) => onChange({ institution: { ...inst, country: e.target.value } })}
            />
          </Field>
          <Field label="State" required error={errors.state}>
            <input
              className={inputClass}
              value={inst.state ?? ""}
              onChange={(e) => onChange({ institution: { ...inst, state: e.target.value || null } })}
              placeholder="West Bengal"
            />
          </Field>
          <Field label="City" required error={errors.city}>
            <input
              className={inputClass}
              value={inst.city ?? ""}
              onChange={(e) => onChange({ institution: { ...inst, city: e.target.value || null } })}
              placeholder="Kolkata"
            />
          </Field>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Create Password" required error={errors.password} hint="At least 6 characters">
            <input
              className={inputClass}
              type="password"
              value={draft.password}
              onChange={(e) => onChange({ password: e.target.value })}
              autoComplete="new-password"
            />
          </Field>
          <Field label="Confirm Password" required error={errors.confirm}>
            <input
              className={inputClass}
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
            />
          </Field>
        </div>
        <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="flex items-center gap-1.5 text-xs text-[#64748B]">
            <ShieldCheck className="h-4 w-4 text-success-text" aria-hidden="true" />
            Your data is tenant-isolated. Subdomain availability is checked next.
          </p>
          <PrimaryButton type="submit" loading={busy}>
            Next <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </PrimaryButton>
        </div>
        <p className="border-t border-border pt-4 text-center text-xs text-[#64748B]">
          Prefer to evaluate first?{" "}
          <button
            type="button"
            onClick={onStartTrial}
            className="font-semibold text-accent hover:underline"
          >
            Start a free 14-day trial
          </button>{" "}
          — no card required.
        </p>
      </form>
    </div>
  );
}

/* ── Step 2 — Institution URL ────────────────────────────────────────────── */

export function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function UrlStep({
  draft,
  onChange,
  onNext,
}: {
  draft: Draft;
  onChange: (patch: Partial<Draft>) => void;
  onNext: () => void;
}) {
  const [check, setCheck] = useState<SubdomainCheck | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [checkedFor, setCheckedFor] = useState("");

  useEffect(() => {
    const slug = slugify(draft.urlSlug);
    if (timer.current) clearTimeout(timer.current);
    if (slug.length < 2 || slug === checkedFor) return;
    timer.current = setTimeout(async () => {
      try {
        const result = await checkSubdomain(slug);
        setCheck(result);
        setCheckedFor(slug);
      } catch {
        setCheck(null);
      }
    }, 400);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [draft.urlSlug, checkedFor]);

  const slugged = slugify(draft.urlSlug);
  // In-flight while a check is pending for the current input.
  const checking = slugged.length >= 2 && (!check || check.slug !== slugged);

  const instName = draft.institution.name || "Your Institution";
  const derived = slugify(draft.urlSlug || instName);
  const canContinue = check?.available === true;

  return (
    <div className="animate-fade-up">
      <StepTitle
        icon={<Globe className="h-5 w-5" aria-hidden="true" />}
        title="Choose Your Institution URL"
        subtitle="This is where your teachers, students and parents will sign in."
      />
      <div className="mt-8 rounded-card border border-border bg-white p-6 shadow-card sm:p-8">
        <div className="flex items-center gap-2 text-sm text-[#475569]">
          <span>Institution</span>
          <span className="rounded-full bg-accent-light px-2.5 py-0.5 text-xs font-semibold text-accent">
            {instName}
          </span>
        </div>
        <Field label="Preferred URL" required hint="Lowercase letters, numbers and hyphens only">
          <div className="flex items-center gap-2">
            <input
              className={inputClass}
              value={draft.urlSlug}
              onChange={(e) => onChange({ urlSlug: e.target.value })}
              placeholder="green"
              spellCheck={false}
            />
            <span className="shrink-0 text-sm font-medium text-[#64748B]">.{tenantHost("").replace(/^\./, "")}</span>
          </div>
        </Field>

        <div className="mt-5 rounded-field border border-border bg-[#F8FAFC] p-4">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#64748B]">Result</p>
          <p className="mt-1 font-display text-lg font-bold text-primary">
            {tenantUrl(derived || "…")}
          </p>
          <div className="mt-2 flex items-center gap-2">
            {checking ? (
              <span className="text-xs text-[#64748B]">Checking availability…</span>
            ) : check ? (
              <AvailableBadge available={check.available} />
            ) : (
              <span className="text-xs text-[#94A3B8]">Type a URL to check availability</span>
            )}
          </div>
        </div>

        {check && !check.available && check.suggestions.length > 0 && (
          <div className="mt-5">
            <p className="text-sm font-semibold text-primary">Suggestions</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {check.suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => onChange({ urlSlug: s })}
                  className="rounded-full border border-accent-border bg-accent-light px-3 py-1.5 text-xs font-semibold text-accent transition hover:bg-accent hover:text-white"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mt-8 flex justify-end">
          <PrimaryButton onClick={onNext} disabled={!canContinue}>
            Next <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}

/* ── Step 3 — Plan selection ─────────────────────────────────────────────── */

function PlanStep({
  catalog,
  draft,
  onChange,
  onContinue,
}: {
  catalog: Catalog | null;
  draft: Draft;
  onChange: (patch: Partial<Draft>) => void;
  onContinue: () => void;
}) {
  const plans = catalog?.plans ?? [];
  const selected = draft.planSlug;

  function pick(slug: string, isCustom: boolean) {
    onChange({ planSlug: slug, moduleKeys: isCustom ? [] : draft.moduleKeys });
  }

  return (
    <div className="animate-fade-up">
      <StepTitle
        icon={<LayoutGrid className="h-5 w-5" aria-hidden="true" />}
        title="Select Subscription Type"
        subtitle="Choose a plan, or build your own from individual modules."
      />
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {(plans.length ? plans : FALLBACK_PLANS).map((p) => {
          const active = selected === p.slug;
          return (
            <button
              key={p.slug}
              type="button"
              onClick={() => pick(p.slug, false)}
              className={`rounded-card border p-5 text-left transition ${
                active
                  ? "border-accent bg-accent-light shadow-card"
                  : "border-border bg-white hover:border-accent-border hover:shadow-card"
              }`}
              aria-pressed={active}
            >
              <p className="font-display text-lg font-bold text-primary">{p.name}</p>
              <p className="mt-1 text-xs text-[#64748B]">
                Up to {p.maxStudents === -1 ? "unlimited" : p.maxStudents.toLocaleString("en-IN")} students ·{" "}
                {p.maxStorageGb} GB
              </p>
              <p className="mt-4 font-display text-2xl font-extrabold text-primary">
                {formatINR(p.priceMonthly)}
                <span className="text-sm font-medium text-[#64748B]">/month</span>
              </p>
              <p className="mt-0.5 text-xs text-[#64748B]">
                or {formatINR(p.priceYearly)}/year
              </p>
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => pick("custom", true)}
          className={`rounded-card border border-dashed p-5 text-left transition ${
            selected === "custom"
              ? "border-accent bg-accent-light shadow-card"
              : "border-border bg-white hover:border-accent-border hover:shadow-card"
          }`}
          aria-pressed={selected === "custom"}
        >
          <span className="inline-flex rounded-full bg-secondary-light p-2 text-secondary-text">
            <Sparkles className="h-5 w-5" aria-hidden="true" />
          </span>
          <p className="mt-3 font-display text-lg font-bold text-primary">Build Your Own Plan</p>
          <p className="mt-1 text-xs leading-5 text-[#64748B]">
            Pick exactly the modules you need and pay only for those.
          </p>
          <p className="mt-4 text-sm font-semibold text-accent">Select modules →</p>
        </button>
      </div>

      <div className="mt-8 flex items-center justify-between">
        <p className="text-xs text-[#64748B]">
          {draft.mode === "TRIAL" ? "Trial: free for 14 days, then this plan applies." : ""}
        </p>
        <PrimaryButton onClick={onContinue} disabled={!selected}>
          Continue <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </PrimaryButton>
      </div>
    </div>
  );
}

/** Used when the API is unreachable so the flow stays reviewable. */
const FALLBACK_PLANS: PlanInfo[] = [
  { id: "p1", name: "Starter", slug: "starter", maxStudents: 500, maxTeachers: 50, maxStorageGb: 10, priceMonthly: 4999, priceYearly: 49990, currency: "INR", allowedModules: [], isActive: true },
  { id: "p2", name: "Professional", slug: "professional", maxStudents: 5000, maxTeachers: 500, maxStorageGb: 200, priceMonthly: 7999, priceYearly: 79990, currency: "INR", allowedModules: [], isActive: true },
  { id: "p3", name: "Enterprise", slug: "enterprise", maxStudents: -1, maxTeachers: -1, maxStorageGb: 1000, priceMonthly: 19999, priceYearly: 199990, currency: "INR", allowedModules: [], isActive: true },
];

/* ── Step 4 — Modules (fixed package / build your own) ───────────────────── */

function ModulesStep({
  catalog,
  draft,
  plan,
  quote,
  onChange,
  onContinue,
}: {
  catalog: Catalog | null;
  draft: Draft;
  plan: PlanInfo | null;
  quote: Quote | null;
  onChange: (patch: Partial<Draft>) => void;
  onContinue: () => void;
}) {
  const isCustom = draft.planSlug === "custom";
  const modules = catalog?.modules ?? FALLBACK_MODULES;

  if (isCustom) {
    const optional = modules.filter((m) => !m.isCore);
    return (
      <div className="animate-fade-up">
        <StepTitle
          icon={<ListChecks className="h-5 w-5" aria-hidden="true" />}
          title="Build Your Own Plan"
          subtitle="Choose the modules your institution needs — core modules are always included."
        />
        <div className="mt-8 grid gap-4 lg:grid-cols-[1fr_300px]">
          <div className="space-y-3">
            <p className="text-sm font-bold uppercase tracking-[0.12em] text-[#64748B]">
              Optional modules
            </p>
            {optional.map((m) => (
              <ModuleCheckbox
                key={m.key}
                module={m}
                checked={draft.moduleKeys.includes(m.key)}
                onChange={(checked) => {
                  const keys = checked
                    ? [...draft.moduleKeys, m.key]
                    : draft.moduleKeys.filter((k) => k !== m.key);
                  onChange({ moduleKeys: keys });
                }}
              />
            ))}
          </div>
          <div className="lg:sticky lg:top-6 lg:self-start">
            {quote ? (
              <PriceSummary quote={quote} />
            ) : (
              <p className="text-sm text-[#64748B]">Loading price…</p>
            )}
          </div>
        </div>
        <div className="mt-8 flex justify-end">
          <PrimaryButton onClick={onContinue}>
            Continue <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </PrimaryButton>
        </div>
      </div>
    );
  }

  // Step 4A — fixed package: show what's included + price.
  const included = modules.filter((m) => m.isCore || plan?.allowedModules.includes(m.key));
  return (
    <div className="animate-fade-up">
      <StepTitle
        icon={<ListChecks className="h-5 w-5" aria-hidden="true" />}
        title={plan?.name ?? "Plan"}
        subtitle="Everything included in this package, with no hidden add-ons."
      />
      <div className="mt-8 grid gap-4 lg:grid-cols-[1fr_300px]">
        <div className="rounded-card border border-border bg-white p-6 shadow-card">
          <p className="text-sm font-bold uppercase tracking-[0.12em] text-[#64748B]">Included</p>
          <ul className="mt-4 grid gap-3 sm:grid-cols-2">
            {included.map((m) => (
              <li key={m.key} className="flex items-center gap-2 text-sm text-[#475569]">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-success-light text-success-text">
                  ✓
                </span>
                {m.name}
              </li>
            ))}
          </ul>
        </div>
        <div className="lg:self-start">
          {quote ? (
            <PriceSummary quote={quote} />
          ) : (
            <p className="text-sm text-[#64748B]">Loading price…</p>
          )}
        </div>
      </div>
      <div className="mt-8 flex justify-end">
        <PrimaryButton onClick={onContinue}>
          Continue <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </PrimaryButton>
      </div>
    </div>
  );
}

/** Fallback catalogue — mirrors the seed so the demo works offline. */
const FALLBACK_MODULES: ModuleInfo[] = [
  ...(["attendance", "examination", "assignment", "notice", "discussion", "content", "results", "timetable"] as const).map((key) => ({
    key, name: key.charAt(0).toUpperCase() + key.slice(1), description: "Core module", isCore: true, priceMonthly: 0,
  })),
  { key: "library", name: "Library", description: "Catalogue, circulation, e-resources", isCore: false, priceMonthly: 1500 },
  { key: "hostel", name: "Hostel", description: "Blocks, rooms, allotments", isCore: false, priceMonthly: 2000 },
  { key: "transport", name: "Transport", description: "Routes, stops, vehicles", isCore: false, priceMonthly: 1500 },
  { key: "placement", name: "Placement", description: "Companies, drives, offers", isCore: false, priceMonthly: 1500 },
  { key: "hr", name: "HR", description: "Staff, leave, payroll", isCore: false, priceMonthly: 2000 },
  { key: "admission", name: "Admission", description: "Cycles, applications, merit lists", isCore: false, priceMonthly: 1500 },
  { key: "inventory", name: "Inventory", description: "Stock, vendors, purchase orders", isCore: false, priceMonthly: 1500 },
  { key: "finance", name: "Finance", description: "Fee structures, collection", isCore: false, priceMonthly: 2000 },
];

/* ── Step 6 — Payment ────────────────────────────────────────────────────── */

const PAYMENT_METHODS = [
  { id: "UPI", label: "UPI" },
  { id: "CARD", label: "Credit Card" },
  { id: "DEBIT_CARD", label: "Debit Card" },
  { id: "NET_BANKING", label: "Net Banking" },
  { id: "WALLET", label: "Wallet" },
  { id: "INVOICE", label: "Invoice (Enterprise)" },
] as const;

function PaymentStep({
  draft,
  quote,
  busy,
  setBusy,
  onPaid,
  ownerToken,
}: {
  draft: Draft;
  quote: Quote | null;
  busy: boolean;
  setBusy: (v: boolean) => void;
  onPaid: (result: ProvisionResult) => void;
  ownerToken?: string;
}) {
  const [method, setMethod] = useState<(typeof PAYMENT_METHODS)[number]["id"]>("UPI");
  const [error, setError] = useState<string | null>(null);

  async function pay() {
    setError(null);
    setBusy(true);
    try {
      const order = await createOrder({
        mode: draft.mode,
        planSlug: draft.planSlug ?? "starter",
        moduleKeys: draft.moduleKeys,
        billingCycle: draft.billingCycle,
        couponCode: draft.couponCode.trim() || null,
        owner:
          !ownerToken && draft.owner.name.trim() && draft.owner.email.trim()
            ? {
                name: draft.owner.name.trim(),
                email: draft.owner.email.trim(),
              }
            : undefined,
        institution: {
          name: draft.institution.name.trim(),
          type: draft.institution.type,
          email: draft.institution.email.trim(),
          phone: draft.institution.phone?.trim() || null,
          country: draft.institution.country.trim(),
          state: draft.institution.state?.trim() || null,
          city: draft.institution.city?.trim() || null,
          address: draft.institution.address?.trim() || null,
        },
        urlSlug: draft.urlSlug.trim(),
        password: draft.password,
      }, ownerToken);
      const result = await payOrder(
        order.id,
        draft.mode === "TRIAL" ? "TRIAL" : method,
        undefined,
        ownerToken,
      );
      onPaid(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payment failed — please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="animate-fade-up">
      <StepTitle
        icon={<PartyPopper className="h-5 w-5" aria-hidden="true" />}
        title="Choose Payment Method"
        subtitle={draft.mode === "TRIAL" ? "Your free trial costs nothing — just confirm to begin." : "Secure checkout — your institution is provisioned automatically after payment."}
      />
      <div className="mt-8 grid gap-4 lg:grid-cols-[1fr_300px]">
        <div className="rounded-card border border-border bg-white p-6 shadow-card">
          <div className="grid gap-3 sm:grid-cols-2">
            {PAYMENT_METHODS.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setMethod(m.id)}
                className={`flex items-center gap-3 rounded-field border px-4 py-3 text-left text-sm font-semibold transition ${
                  method === m.id
                    ? "border-accent bg-accent-light text-accent"
                    : "border-border bg-white text-[#475569] hover:border-accent-border"
                }`}
                aria-pressed={method === m.id}
              >
                <span
                  className={`flex h-4 w-4 items-center justify-center rounded-full border ${
                    method === m.id ? "border-accent bg-accent" : "border-[#CBD5E1]"
                  }`}
                >
                  {method === m.id ? <span className="h-1.5 w-1.5 rounded-full bg-white" /> : null}
                </span>
                {m.label}
              </button>
            ))}
          </div>

          {error ? (
            <p className="mt-5 rounded-field bg-destructive-light px-4 py-3 text-sm font-medium text-destructive-text">
              {error}
            </p>
          ) : null}

          <div className="mt-6 flex items-center justify-between border-t border-border pt-5">
            <p className="text-sm text-[#64748B]">
              {draft.mode === "TRIAL" ? "Free trial · 14 days" : "You'll be redirected after payment"}
            </p>
            <PrimaryButton onClick={() => void pay()} loading={busy}>
              {draft.mode === "TRIAL" ? "Start Free Trial" : "Pay Now"}
            </PrimaryButton>
          </div>
        </div>
        <div className="lg:self-start">
          {quote ? <PriceSummary quote={quote} compact /> : null}
          <p className="mt-3 text-xs leading-5 text-[#64748B]">
            GST invoice will be generated for paid orders. Enterprise institutions can choose
            invoice-based billing.
          </p>
        </div>
      </div>
    </div>
  );
}

/* ── Shared step title ───────────────────────────────────────────────────── */

function StepTitle({
  icon,
  title,
  subtitle,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-light text-accent">
        {icon}
      </span>
      <div>
        <h1 className="font-display text-2xl font-extrabold tracking-tight text-primary">{title}</h1>
        <p className="mt-1 text-sm leading-6 text-[#64748B]">{subtitle}</p>
      </div>
    </div>
  );
}
