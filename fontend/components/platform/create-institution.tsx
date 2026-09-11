"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { cn } from "@/lib/utils";
import { compactINR, planLimit, RESERVED_SLUGS, slugify } from "@/lib/platform";
import { tenantHost } from "@/lib/platform-shared";
import { FormAlert } from "@/components/auth/form-alert";
import { Card } from "@/components/dashboard/primitives";
import { Button } from "@/components/ui/button";
import type { PlanRow, TenantRow } from "@/types/platform";

/**
 * C-SA-04 — Create Institution.
 * "Form: name, slug, type (school/college), plan, admin email"
 *
 * The slug is the tenant's subdomain, so it is validated hard: lowercase
 * a–z/0–9/hyphen only, not already taken, and not one of the reserved names
 * `lib/tenant.ts` routes to the platform console itself. Getting this wrong
 * would make the new tenant unreachable or shadow `app.shikshasync.me`.
 */
export function CreateInstitution({
  plans,
  existing,
  onCreate,
}: {
  plans: PlanRow[];
  existing: TenantRow[];
  /**
   * Wired by the page to POST /platform/tenants. Resolves to a success
   * message, or throws — the thrown message is shown against the form.
   * Omitted = the original unwired demo behaviour.
   */
  onCreate?: (input: {
    name: string;
    slug: string;
    type: "COLLEGE" | "SCHOOL";
    planSlug: string;
    adminName: string;
    adminEmail: string;
    trial: boolean;
  }) => Promise<string>;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [type, setType] = useState<"COLLEGE" | "SCHOOL">("COLLEGE");
  const [planSlug, setPlanSlug] = useState(plans[0]?.slug ?? "");
  const [adminName, setAdminName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [trial, setTrial] = useState(true);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const plan = plans.find((p) => p.slug === planSlug);

  /** Typing a name fills the slug until the admin edits it themselves. */
  function onName(value: string) {
    setName(value);
    if (!slugTouched) setSlug(slugify(value));
  }

  function validate() {
    const e: Record<string, string> = {};
    if (!name.trim()) e.name = "Enter the institution's name";

    if (!slug.trim()) e.slug = "Enter a subdomain";
    else if (!/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/.test(slug))
      e.slug = "Lowercase letters, numbers and hyphens only";
    else if (slug.length < 3) e.slug = "At least 3 characters";
    else if (RESERVED_SLUGS.has(slug))
      e.slug = `“${slug}” is reserved for the platform console`;
    else if (existing.some((t) => t.slug === slug))
      e.slug = "That subdomain is already taken";

    if (!adminName.trim()) e.adminName = "Enter the administrator's name";

    if (!adminEmail.trim()) e.adminEmail = "Enter the administrator's email";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(adminEmail))
      e.adminEmail = "That doesn't look like an email address";

    if (!planSlug) e.plan = "Choose a plan";
    return e;
  }

  async function onSubmit(ev: React.FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    if (busy) return;

    const e = validate();
    setErrors(e);
    if (Object.keys(e).length) return;

    setBusy(true);
    if (!onCreate) {
      // Unwired preview (no backend): report what would have been sent.
      await new Promise((r) => setTimeout(r, 800));
      setBusy(false);
      setDone(
        `POST /platform/tenants { slug: "${slug}", type: "${type}", plan: "${planSlug}"${trial ? ", trial: 30d" : ""} } — API not connected yet (Dev-A, C-SA-04).`,
      );
      return;
    }

    try {
      // Creates the tenant (§4.2), its first subscription (§4.4) and the
      // Institution Admin (§5.5), then emails an activation link.
      setDone(
        await onCreate({
          name: name.trim(),
          slug,
          type,
          planSlug,
          adminName: adminName.trim(),
          adminEmail: adminEmail.trim(),
          trial,
        }),
      );
      setErrors({});
    } catch (err) {
      setErrors({
        form: err instanceof Error ? err.message : "Could not create the institution.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto w-full min-w-0 max-w-2xl">
      <Link
        href="/platform/institutions"
        className="mb-3 inline-flex items-center gap-1.5 rounded text-[13px] font-medium text-muted-foreground transition-colors hover:text-accent focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        All institutions
      </Link>

      <h1 className="font-display text-[22px] font-bold text-foreground">
        New institution
      </h1>
      <p className="mt-1 text-[13px] text-muted-foreground">
        Creates the tenant, its first subscription and the administrator
        account. They receive an activation email.
      </p>

      {done && (
        <FormAlert variant={onCreate ? "success" : "info"} className="mt-4">
          {done}
        </FormAlert>
      )}

      {errors.form && (
        <FormAlert variant="error" className="mt-4">
          {errors.form}
        </FormAlert>
      )}

      <Card className="mt-4 min-w-0 p-5 sm:p-6">
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          <Field id="inst-name" label="Institution name" error={errors.name}>
            <input
              id="inst-name"
              value={name}
              onChange={(e) => onName(e.target.value)}
              placeholder="ABC College of Engineering"
              className={input(!!errors.name)}
            />
          </Field>

          <Field
            id="inst-slug"
            label="Subdomain"
            error={errors.slug}
            hint={slug ? tenantHost(slug) : undefined}
          >
            <input
              id="inst-slug"
              value={slug}
              onChange={(e) => {
                setSlugTouched(true);
                setSlug(e.target.value.toLowerCase());
              }}
              placeholder="abc-college"
              className={cn(input(!!errors.slug), "font-mono")}
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="inst-type" label="Type">
              <select
                id="inst-type"
                value={type}
                onChange={(e) => setType(e.target.value as "COLLEGE" | "SCHOOL")}
                className={input(false)}
              >
                <option value="COLLEGE">College</option>
                <option value="SCHOOL">School</option>
              </select>
            </Field>

            <Field id="inst-plan" label="Plan" error={errors.plan}>
              <select
                id="inst-plan"
                value={planSlug}
                onChange={(e) => setPlanSlug(e.target.value)}
                className={input(!!errors.plan)}
              >
                {plans.map((p) => (
                  <option key={p.slug} value={p.slug}>
                    {p.name} — {compactINR(p.priceMonthly)}/mo
                  </option>
                ))}
              </select>
            </Field>
          </div>

          {plan && (
            <p className="rounded-field border border-accent-border bg-accent-light px-3.5 py-2 text-[12px] text-[#3730A3]">
              {plan.name}: {planLimit(plan.maxStudents)} students ·{" "}
              {planLimit(plan.maxTeachers)} teachers · {plan.maxStorageGb} GB ·{" "}
              {plan.allowedModules.length} modules
            </p>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="inst-admin" label="Administrator name" error={errors.adminName}>
              <input
                id="inst-admin"
                value={adminName}
                onChange={(e) => setAdminName(e.target.value)}
                placeholder="Meera Krishnan"
                className={input(!!errors.adminName)}
              />
            </Field>

            <Field id="inst-email" label="Administrator email" error={errors.adminEmail}>
              <input
                id="inst-email"
                type="email"
                value={adminEmail}
                onChange={(e) => setAdminEmail(e.target.value)}
                placeholder="admin@abc-college.edu"
                className={input(!!errors.adminEmail)}
              />
            </Field>
          </div>

          {/* Explicit id + `for` rather than relying on the wrapping label —
              assistive tech resolves a bound label more reliably. */}
          <label htmlFor="inst-trial" className="flex min-w-0 items-center gap-2.5">
            <input
              id="inst-trial"
              type="checkbox"
              checked={trial}
              onChange={(e) => setTrial(e.target.checked)}
              className="h-4 w-4 shrink-0 rounded border-border text-accent focus:ring-3 focus:ring-accent/15"
            />
            <span className="text-[13px] text-[#334155]">
              Start with a 30-day trial
              <span className="text-muted-foreground">
                {" "}
                — billing begins when it ends
              </span>
            </span>
          </label>

          {Object.keys(errors).length > 0 && (
            <FormAlert variant="error">
              Check the highlighted fields and try again.
            </FormAlert>
          )}

          <div className="flex flex-wrap justify-end gap-2 pt-1">
            <Link
              href="/platform/institutions"
              className="inline-flex h-11 items-center rounded-field border border-border px-4 text-[14px] font-medium text-[#475569] transition-colors hover:bg-background focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/15"
            >
              Cancel
            </Link>
            <Button
              type="submit"
              loading={busy}
              loadingText="Creating…"
              className="w-auto px-5"
            >
              Create institution
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

function input(hasError: boolean) {
  return cn(
    "mt-1.5 h-11 w-full min-w-0 rounded-field border bg-white px-3 text-[14px] transition placeholder:text-[#94A3B8] focus:outline-none focus:ring-3",
    hasError
      ? "border-destructive focus:border-destructive focus:ring-destructive/15"
      : "border-border focus:border-accent focus:ring-accent/15",
  );
}

function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="text-[13px] font-medium text-[#334155]">
        {label}
      </label>
      {children}
      {hint && !error && (
        <p className="mt-1 font-mono text-[12px] text-muted-foreground">{hint}</p>
      )}
      {error && <p className="mt-1 text-[12px] text-destructive-text">{error}</p>}
    </div>
  );
}
