"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/text-field";
import { FormAlert } from "./form-alert";
import { TenantBadge } from "./tenant-badge";
import { ERROR_MESSAGES, login } from "@/lib/auth";
import { identifierLabel, identifierPlaceholder } from "@/lib/tenant";
import { primaryRole, redirectForRoles, roleLabel } from "@/lib/roles";
import { AuthError } from "@/types/auth";
import type { Tenant } from "@/types/auth";

/**
 * Login form — design §5 (right panel), §6, §7, §9.
 * Tab order: identifier → password → remember → submit, with "Forgot?"
 * reachable after the field it belongs to (§10).
 */

type Status =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "error"; message: string }
  | { kind: "success"; message: string };

export function LoginForm({ tenant }: { tenant: Tenant }) {
  const router = useRouter();
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [fieldErrors, setFieldErrors] = useState<{
    identifier?: string;
    password?: string;
  }>({});

  const identifierRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const submitting = status.kind === "submitting";
  const succeeded = status.kind === "success";

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting || succeeded) return;

    const identifier = identifierRef.current?.value.trim() ?? "";
    const password = passwordRef.current?.value ?? "";
    const remember =
      (event.currentTarget.elements.namedItem("remember") as HTMLInputElement)
        ?.checked ?? false;

    // Client-side validation before hitting the network
    const errors: typeof fieldErrors = {};
    if (!identifier) errors.identifier = "Enter your email or roll number";
    if (!password) errors.password = "Enter your password";
    else if (password.length < 6)
      errors.password = "Password must be at least 6 characters";

    setFieldErrors(errors);
    if (Object.keys(errors).length) {
      (errors.identifier ? identifierRef : passwordRef).current?.focus();
      setStatus({ kind: "idle" });
      return;
    }

    // Unknown subdomain — fail fast with the §7 message
    if (tenant.notFound) {
      setStatus({ kind: "error", message: ERROR_MESSAGES.TENANT_NOT_FOUND });
      return;
    }

    setStatus({ kind: "submitting" });

    try {
      const result = await login({
        identifier,
        password,
        remember,
        tenantId: tenant.slug,
      });

      const role = primaryRole(result.roles);
      setStatus({
        kind: "success",
        message: `Signed in as ${roleLabel(role)} — redirecting…`,
      });

      const destination = redirectForRoles(result.roles);
      if (destination.startsWith("http")) {
        window.location.assign(destination);
      } else {
        router.push(destination);
      }
    } catch (err) {
      const message =
        err instanceof AuthError
          ? err.message || ERROR_MESSAGES[err.code]
          : ERROR_MESSAGES.UNKNOWN;

      setStatus({ kind: "error", message });
      passwordRef.current?.select();
    }
  }

  return (
    <div className="rounded-card bg-white p-0 lg:border lg:border-[#E2E8F0] lg:p-8 lg:shadow-card">
      <div className="mb-7">
        <h1 className="font-display text-[22px] font-bold text-[#0F172A]">
          Welcome back
        </h1>
        <p className="mt-1 text-[13px] text-[#64748B]">
          {tenant.isPlatform
            ? "Sign in to the shikshasync.me platform console"
            : "Sign in to your institution account"}
        </p>
      </div>

      <TenantBadge tenant={tenant} />

      {tenant.notFound && (
        <FormAlert variant="error" className="mb-5">
          Institution not found. Check the subdomain in your address bar.
        </FormAlert>
      )}

      {status.kind === "error" && (
        <FormAlert variant="error" className="mb-5 animate-shake">
          {status.message}
        </FormAlert>
      )}

      {succeeded && (
        <FormAlert variant="success" className="mb-5">
          {status.message}
        </FormAlert>
      )}

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <TextField
          ref={identifierRef}
          name="identifier"
          label={identifierLabel(tenant)}
          placeholder={identifierPlaceholder(tenant)}
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          enterKeyHint="next"
          disabled={submitting || succeeded}
          error={fieldErrors.identifier}
          onChange={() =>
            setFieldErrors((p) => ({ ...p, identifier: undefined }))
          }
        />

        <TextField
          ref={passwordRef}
          name="password"
          label="Password"
          placeholder="••••••••"
          autoComplete="current-password"
          enterKeyHint="go"
          revealable
          disabled={submitting || succeeded}
          error={fieldErrors.password}
          onChange={() => setFieldErrors((p) => ({ ...p, password: undefined }))}
          labelAction={
            <Link
              href="/forgot-password"
              className="rounded text-[12px] font-medium text-accent transition-colors hover:text-accent-hover"
            >
              Forgot?
            </Link>
          }
        />

        <div className="flex items-center gap-2 py-1">
          <input
            type="checkbox"
            id="remember"
            name="remember"
            defaultChecked
            disabled={submitting || succeeded}
            className="h-4 w-4 cursor-pointer rounded border-[#CBD5E1] text-accent accent-accent focus:ring-accent/20"
          />
          <label
            htmlFor="remember"
            className="cursor-pointer select-none text-[13px] text-[#475569]"
          >
            Remember me for 7 days
          </label>
        </div>

        <Button type="submit" loading={submitting} loadingText="Signing in…">
          {succeeded ? "Redirecting…" : "Sign in"}
          {!succeeded && <ArrowRight className="h-4 w-4" aria-hidden="true" />}
        </Button>

        {tenant.ssoProvider && (
          <>
            <div className="relative py-2">
              <div className="absolute inset-0 flex items-center" aria-hidden="true">
                <div className="w-full border-t border-[#E2E8F0]" />
              </div>
              <div className="relative flex justify-center">
                <span className="bg-white px-3 text-[12px] text-[#475569]">
                  or continue with
                </span>
              </div>
            </div>

            <Button
              type="button"
              variant="secondary"
              disabled={submitting || succeeded}
              // TODO(Dev-A): kick off the SSO redirect for this tenant
              onClick={() => undefined}
            >
              {tenant.ssoProvider}
            </Button>
          </>
        )}

        <p className="pt-2 text-center text-[12px] text-[#64748B]">
          Having trouble?{" "}
          <Link
            href="/support"
            className="rounded font-medium text-accent transition-colors hover:text-accent-hover"
          >
            Contact Institution Admin
          </Link>
        </p>
      </form>
    </div>
  );
}
