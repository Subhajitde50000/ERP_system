"use client";

import { ArrowRight, CheckCircle2, Tag } from "lucide-react";
import { useState } from "react";

import { inputClass, PrimaryButton, PriceSummary } from "./checkout-ui";
import { fetchQuote, formatINR } from "@/lib/signup";
import type { InstitutionDraft, ModuleInfo, Quote } from "@/lib/signup";

interface ReviewDraft {
  institution: InstitutionDraft;
  urlSlug: string;
  planSlug: string | null;
  moduleKeys: string[];
  billingCycle: "MONTHLY" | "YEARLY";
  couponCode: string;
  mode: "PURCHASE" | "TRIAL";
}

/** Step 5 — Order review with coupon apply. */
export function ReviewStep({
  draft,
  planName,
  selectedOptional,
  quote,
  onChange,
  onContinue,
}: {
  draft: ReviewDraft;
  planName: string;
  selectedOptional: ModuleInfo[];
  quote: Quote | null;
  onChange: (patch: Partial<ReviewDraft>) => void;
  onContinue: () => void;
}) {
  const [couponInput, setCouponInput] = useState(draft.couponCode);
  const [couponState, setCouponState] = useState<"idle" | "applying" | "applied" | "invalid">(
    draft.couponCode ? "applied" : "idle",
  );
  const [couponMessage, setCouponMessage] = useState("");

  async function applyCoupon() {
    const code = couponInput.trim().toUpperCase();
    if (!code) return;
    if (draft.mode === "TRIAL") {
      setCouponState("invalid");
      setCouponMessage("Coupons don't apply to free trials.");
      return;
    }
    setCouponState("applying");
    try {
      const q = await fetchQuote({
        mode: "PURCHASE",
        plan: draft.planSlug ?? "starter",
        modules: draft.moduleKeys,
        cycle: draft.billingCycle,
        coupon: code,
      });
      onChange({ couponCode: code });
      setCouponState("applied");
      setCouponMessage(
        q.coupon ? `Coupon ${code} applied — you save ${formatINR(q.discount)}` : "Coupon not recognised",
      );
      if (!q.coupon) setCouponState("invalid");
    } catch {
      setCouponState("invalid");
      setCouponMessage("Couldn't validate the coupon right now.");
    }
  }

  const rows: { label: string; value: string }[] = [
    { label: "Institution", value: draft.institution.name },
    { label: "URL", value: `${draft.urlSlug || "…"}.shikshasync.me` },
    { label: "Plan", value: draft.planSlug === "custom" ? "Custom Plan" : planName },
  ];

  return (
    <div className="animate-fade-up">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-xl bg-accent-light text-accent">
          <CheckCircle2 className="h-5 w-5" aria-hidden="true" />
        </span>
        <div>
          <h1 className="font-display text-2xl font-extrabold tracking-tight text-primary">
            Review Order
          </h1>
          <p className="mt-1 text-sm text-[#64748B]">
            Confirm the details — your institution is created automatically after payment.
          </p>
        </div>
      </div>

      <div className="mt-8 grid gap-4 lg:grid-cols-[1fr_300px]">
        <div className="space-y-4">
          <div className="rounded-card border border-border bg-white p-6 shadow-card">
            <dl className="space-y-3">
              {rows.map((row) => (
                <div key={row.label} className="flex items-baseline justify-between gap-4 text-sm">
                  <dt className="text-[#64748B]">{row.label}</dt>
                  <dd className="text-right font-semibold text-primary">{row.value}</dd>
                </div>
              ))}
            </dl>

            {(selectedOptional.length > 0 || draft.planSlug === "custom") && (
              <div className="mt-5 border-t border-border pt-4">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#64748B]">
                  Modules
                </p>
                <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                  {selectedOptional.length === 0 ? (
                    <li className="text-sm text-[#475569]">Core modules only</li>
                  ) : (
                    selectedOptional.map((m) => (
                      <li key={m.key} className="flex items-center gap-2 text-sm text-[#475569]">
                        <span className="text-success-text">✓</span> {m.name}
                      </li>
                    ))
                  )}
                </ul>
              </div>
            )}

            <div className="mt-5 flex items-end justify-between gap-3 border-t border-border pt-4">
              <div className="flex-1">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#64748B]">Coupon</p>
                <div className="mt-2 flex gap-2">
                  <input
                    className={inputClass}
                    value={couponInput}
                    onChange={(e) => {
                      setCouponInput(e.target.value);
                      setCouponState("idle");
                      setCouponMessage("");
                    }}
                    placeholder="WELCOME10"
                    disabled={draft.mode === "TRIAL"}
                  />
                  <button
                    type="button"
                    onClick={() => void applyCoupon()}
                    disabled={couponState === "applying" || !couponInput.trim()}
                    className="inline-flex h-[42px] shrink-0 items-center gap-1.5 rounded-field border border-accent-border bg-accent-light px-4 text-sm font-semibold text-accent transition hover:bg-accent hover:text-white disabled:opacity-50"
                  >
                    <Tag className="h-4 w-4" aria-hidden="true" /> Apply
                  </button>
                </div>
                {couponMessage ? (
                  <p
                    className={`mt-1.5 text-xs font-medium ${
                      couponState === "applied" ? "text-success-text" : "text-destructive-text"
                    }`}
                  >
                    {couponMessage}
                  </p>
                ) : null}
              </div>
            </div>
          </div>

          <div className="flex justify-end">
            <PrimaryButton onClick={onContinue}>
              Continue <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </PrimaryButton>
          </div>
        </div>

        <div className="lg:self-start">{quote ? <PriceSummary quote={quote} /> : null}</div>
      </div>
    </div>
  );
}
