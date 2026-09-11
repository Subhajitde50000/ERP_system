"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/text-field";
import { FormAlert } from "./form-alert";
import { ERROR_MESSAGES, platformLogin } from "@/lib/auth";
import { PLATFORM_ROLE_HOME, PLATFORM_ROLE_LABELS } from "@/lib/platform";
import { AuthError } from "@/types/auth";

/**
 * Platform console sign-in — `app.shikshasync.me/login`.
 *
 * `login_page_design.md` §1 requires the page to serve
 * "`app.shikshasync.me` → Platform roles (Super Admin, Support, Sales, Finance)",
 * and §8 redirects `SUPER_ADMIN → app.shikshasync.me/dashboard`. The eight platform
 * pages were built but nothing signed anyone in to them; this is that door.
 *
 * Reuses `TextField`, `Button` and `FormAlert` — the palette, the 44px
 * control height and the focus ring are identical to the tenant login. What
 * differs is only what genuinely differs in the domain:
 *
 *   • **No `TenantBadge`.** There is no institution here, so the badge that
 *     tells a student which school they are signing in to has nothing to say.
 *   • **Email only.** `platform_users.email` is the unique key (DB §4.5);
 *     roll numbers are an institution concept.
 *   • **No "Forgot?" link.** `platform_users` has no reset-token columns —
 *     `users` has `password_reset_token`, `platform_users` does not. Offering
 *     a link to a flow the schema cannot support would be the same dead end
 *     `/forgot-password` had before `/reset-password` existed. Staff recover
 *     through the Super Admin, and the card says so.
 *   • **One role, no switcher.** `platform_role` is a scalar column, not a
 *     join table, so the destination is decided by that single value.
 */

type Status =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "error"; message: string }
  | { kind: "success"; message: string };

export function PlatformLoginForm() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [fieldErrors, setFieldErrors] = useState<{
    email?: string;
    password?: string;
  }>({});

  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const submitting = status.kind === "submitting";
  const succeeded = status.kind === "success";
  const busy = submitting || succeeded;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;

    const email = emailRef.current?.value.trim() ?? "";
    const password = passwordRef.current?.value ?? "";
    const remember =
      (event.currentTarget.elements.namedItem("remember") as HTMLInputElement)
        ?.checked ?? false;

    const errors: typeof fieldErrors = {};
    if (!email) errors.email = "Enter your work email";
    // Deliberately loose: the server is the authority on whether an account
    // exists. A strict client-side pattern only rejects valid addresses.
    else if (!email.includes("@")) errors.email = "Enter a valid email address";
    if (!password) errors.password = "Enter your password";
    else if (password.length < 6)
      errors.password = "Password must be at least 6 characters";

    setFieldErrors(errors);
    if (Object.keys(errors).length) {
      (errors.email ? emailRef : passwordRef).current?.focus();
      setStatus({ kind: "idle" });
      return;
    }

    setStatus({ kind: "submitting" });

    try {
      const result = await platformLogin({ email, password, remember });

      setStatus({
        kind: "success",
        message: `Signed in as ${PLATFORM_ROLE_LABELS[result.role]} — redirecting…`,
      });

      // One role, so one destination — no switcher, no primaryRole() merge.
      router.push(PLATFORM_ROLE_HOME[result.role]);
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
      <div className="mb-6">
        <h1 className="font-display text-[22px] font-bold text-[#0F172A]">
          Platform console
        </h1>
        <p className="mt-1 text-[13px] text-[#64748B]">
          Sign in to manage institutions, plans and billing.
        </p>
      </div>

      {/*
        Stands in for the tenant login's TenantBadge: same slot, same weight,
        but it says which *console* you are entering rather than which school.
      */}
      <div className="mb-6 flex items-center gap-2.5 rounded-field border border-accent-border bg-accent-light px-3.5 py-2.5">
        <ShieldCheck
          className="h-4 w-4 shrink-0 text-accent"
          aria-hidden="true"
        />
        <p className="min-w-0 text-[12px] leading-snug text-[#334155]">
          <span className="font-semibold text-[#0F172A]">Staff access only.</span>{" "}
          Institution accounts sign in at their own address.
        </p>
      </div>

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
          ref={emailRef}
          name="email"
          type="email"
          label="Work email"
          placeholder="you@shikshasync.me"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          enterKeyHint="next"
          disabled={busy}
          error={fieldErrors.email}
          onChange={() => setFieldErrors((p) => ({ ...p, email: undefined }))}
        />

        <TextField
          ref={passwordRef}
          name="password"
          label="Password"
          placeholder="••••••••"
          autoComplete="current-password"
          enterKeyHint="go"
          revealable
          disabled={busy}
          error={fieldErrors.password}
          onChange={() => setFieldErrors((p) => ({ ...p, password: undefined }))}
        />

        <div className="flex items-center gap-2 py-1">
          <input
            type="checkbox"
            id="platform-remember"
            name="remember"
            disabled={busy}
            className="h-4 w-4 cursor-pointer rounded border-[#CBD5E1] text-accent accent-accent focus:ring-accent/20"
          />
          <label
            htmlFor="platform-remember"
            className="cursor-pointer select-none text-[13px] text-[#475569]"
          >
            Keep me signed in
          </label>
        </div>

        <Button type="submit" loading={submitting} loadingText="Signing in…">
          Sign in
          {!busy && <ArrowRight className="h-4 w-4" aria-hidden="true" />}
        </Button>
      </form>

      <p className="mt-6 border-t border-[#E2E8F0] pt-4 text-[12px] leading-relaxed text-[#475569]">
        Locked out? Platform accounts are managed by the Super Admin — ask them
        to reset your password from Platform users.
      </p>
    </div>
  );
}
