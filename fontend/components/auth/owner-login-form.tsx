"use client";

/**
 * Owner login — the shikshasync.me "Platform Login" door.
 *
 * Purpose: My Institutions, Billing, Subscriptions, Invoices, Support Tickets,
 * Profile. The institution's *daily* ERP work happens at green.shikshasync.me/login
 * (a different login system). In production this is `shikshasync.me/login`; on a
 * single-origin deployment it is `/account/login`.
 */

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/text-field";
import { FormAlert } from "@/components/auth/form-alert";
import { useOwnerAuth } from "@/hooks/use-owner-auth";
import { APIError } from "@/lib/owner";

export function OwnerLoginForm() {
  const router = useRouter();
  const { login } = useOwnerAuth();
  const [status, setStatus] = useState<{ kind: "idle" | "submitting"; error?: string }>({
    kind: "idle",
  });
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});

  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const busy = status.kind === "submitting";

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    const email = emailRef.current?.value.trim() ?? "";
    const password = passwordRef.current?.value ?? "";

    const errs: typeof errors = {};
    if (!email.includes("@")) errs.email = "Enter your email address";
    if (password.length < 1) errs.password = "Enter your password";
    setErrors(errs);
    if (Object.keys(errs).length) return;

    setStatus({ kind: "submitting" });
    try {
      await login({ email, password });
      router.push("/account");
    } catch (err) {
      const msg =
        err instanceof APIError ? err.message : "Could not sign in. Please try again.";
      setStatus({ kind: "idle", error: msg });
    }
  }

  return (
    <div className="rounded-card bg-white p-0 lg:border lg:border-[#E2E8F0] lg:p-8 lg:shadow-card">
      <div className="mb-6">
        <h1 className="font-display text-[22px] font-bold text-[#0F172A]">
          Sign in to your account
        </h1>
        <p className="mt-1 text-[13px] text-[#64748B]">
          Manage your institutions, billing and support.
        </p>
      </div>

      {status.error ? (
        <FormAlert variant="error" className="mb-5 animate-shake">
          {status.error}
        </FormAlert>
      ) : null}

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <TextField
          ref={emailRef}
          name="email"
          type="email"
          label="Email address"
          placeholder="rahul@gmail.com"
          autoComplete="email"
          autoCapitalize="none"
          spellCheck={false}
          disabled={busy}
          error={errors.email}
          onChange={() => setErrors((p) => ({ ...p, email: undefined }))}
        />
        <TextField
          ref={passwordRef}
          name="password"
          label="Password"
          placeholder="••••••••"
          autoComplete="current-password"
          revealable
          disabled={busy}
          error={errors.password}
          onChange={() => setErrors((p) => ({ ...p, password: undefined }))}
        />
        <Button type="submit" loading={busy} loadingText="Signing in…">
          Sign in
          {!busy && <ArrowRight className="h-4 w-4" aria-hidden="true" />}
        </Button>
      </form>

      <p className="mt-6 flex items-center justify-between border-t border-[#E2E8F0] pt-4 text-[12px] text-[#475569]">
        <Link href="/signup" className="font-semibold text-accent hover:underline">
          Create an account
        </Link>
        <Link href="/forgot-password" className="hover:text-accent">
          Forgot password?
        </Link>
      </p>

      <p className="mt-4 rounded-field bg-[#F8FAFC] px-3.5 py-2.5 text-[11px] leading-relaxed text-[#64748B]">
        Doing daily ERP work (attendance, exams, fees)? Sign in at your
        institution&apos;s address, e.g. <span className="font-semibold">green.shikshasync.me/login</span>.
      </p>
    </div>
  );
}
