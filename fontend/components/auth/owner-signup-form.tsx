"use client";

/**
 * Owner account sign-up — the first step of the xyz.com customer journey:
 *
 *   Sign Up (Name, Email, Password) → Verify Email → Platform Dashboard
 *
 * This creates the *account-holder* (Rahul / rahul@gmail.com), who can then own
 * many institutions. It is deliberately separate from the institution checkout:
 * the account comes first, institutions are created from the dashboard.
 */

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/text-field";
import { FormAlert } from "@/components/auth/form-alert";
import { ownerSignup } from "@/lib/owner";
import { APIError } from "@/lib/owner";

type Status =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "error"; message: string }
  | { kind: "done"; email: string; token: string | null };

export function OwnerSignupForm() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [errors, setErrors] = useState<{ name?: string; email?: string; password?: string }>({});

  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const busy = status.kind === "submitting" || status.kind === "done";

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    const name = nameRef.current?.value.trim() ?? "";
    const email = emailRef.current?.value.trim() ?? "";
    const password = passwordRef.current?.value ?? "";

    const errs: typeof errors = {};
    if (name.length < 2) errs.name = "Enter your full name";
    if (!email.includes("@")) errs.email = "Enter a valid email address";
    if (password.length < 6) errs.password = "At least 6 characters";
    setErrors(errs);
    if (Object.keys(errs).length) {
      (errs.name ? nameRef : errs.email ? emailRef : passwordRef).current?.focus();
      return;
    }

    setStatus({ kind: "submitting" });
    try {
      const res = await ownerSignup({ name, email, password });
      setStatus({ kind: "done", email: res.email, token: res.verificationToken });
    } catch (err) {
      const msg =
        err instanceof APIError
          ? err.message
          : "Could not create your account. Please try again.";
      setStatus({ kind: "error", message: msg });
    }
  }

  // ── Post-signup: "check your email" screen ────────────────────────────────
  if (status.kind === "done") {
    return (
      <div className="rounded-card bg-white p-0 lg:border lg:border-[#E2E8F0] lg:p-8 lg:shadow-card">
        <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-success-light text-success-text">
          <ShieldCheck className="h-5 w-5" aria-hidden="true" />
        </div>
        <h1 className="font-display text-[22px] font-bold text-[#0F172A]">
          Verify your email
        </h1>
        <p className="mt-2 text-[13px] leading-6 text-[#64748B]">
          We sent a verification link to{" "}
          <span className="font-semibold text-[#0F172A]">{status.email}</span>. Confirm it to
          activate your account and reach your platform dashboard.
        </p>

        {/* Dev shortcut: no mailer wired, so the token is returned to complete the flow. */}
        {status.token ? (
          <FormAlert variant="success" className="mt-5">
            Dev mode —{" "}
            <Link
              href={`/verify-email?token=${encodeURIComponent(status.token)}`}
              className="underline"
            >
              verify now
            </Link>
            .
          </FormAlert>
        ) : null}

        <div className="mt-6 flex flex-col gap-3">
          <Button onClick={() => router.push("/account/login")}>
            Continue to sign in <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Button>
          <p className="text-center text-[12px] text-[#64748B]">
            Didn&apos;t get it? Check spam, or{" "}
            <button
              type="button"
              onClick={async () => {
                const { resendOwnerVerification } = await import("@/lib/owner");
                await resendOwnerVerification(status.email);
              }}
              className="font-semibold text-accent hover:underline"
            >
              resend the link
            </button>
            .
          </p>
        </div>
      </div>
    );
  }

  // ── Sign-up form ──────────────────────────────────────────────────────────
  return (
    <div className="rounded-card bg-white p-0 lg:border lg:border-[#E2E8F0] lg:p-8 lg:shadow-card">
      <div className="mb-6">
        <h1 className="font-display text-[22px] font-bold text-[#0F172A]">
          Create your platform account
        </h1>
        <p className="mt-1 text-[13px] text-[#64748B]">
          One account to manage every institution you own — billing, subscriptions and support.
        </p>
      </div>

      {status.kind === "error" && (
        <FormAlert variant="error" className="mb-5 animate-shake">
          {status.message}
        </FormAlert>
      )}

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <TextField
          ref={nameRef}
          name="name"
          label="Full name"
          placeholder="Rahul Sharma"
          autoComplete="name"
          disabled={busy}
          error={errors.name}
          onChange={() => setErrors((p) => ({ ...p, name: undefined }))}
        />
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
          placeholder="At least 6 characters"
          autoComplete="new-password"
          revealable
          disabled={busy}
          error={errors.password}
          onChange={() => setErrors((p) => ({ ...p, password: undefined }))}
        />

        <Button type="submit" loading={status.kind === "submitting"} loadingText="Creating account…">
          Create account
          {status.kind !== "submitting" && <ArrowRight className="h-4 w-4" aria-hidden="true" />}
        </Button>

        <p className="text-center text-[11px] leading-relaxed text-[#64748B]">
          By creating an account, you agree to our{" "}
          <Link href="/terms" target="_blank" className="font-semibold text-accent hover:underline">
            Terms of Service
          </Link>{" "}
          and acknowledge our{" "}
          <Link href="/privacy" target="_blank" className="font-semibold text-accent hover:underline">
            Privacy Policy
          </Link>
          .
        </p>
      </form>

      <p className="mt-6 border-t border-[#E2E8F0] pt-4 text-center text-[12px] text-[#475569]">
        Already have an account?{" "}
        <Link href="/account/login" className="font-semibold text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
