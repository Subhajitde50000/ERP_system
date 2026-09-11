"use client";

import { FormEvent, useState } from "react";
import { ArrowRight, CheckCircle2, LoaderCircle } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type FormValues = {
  contact_name: string;
  institution_name: string;
  work_email: string;
  phone: string;
  institution_type: "SCHOOL" | "COLLEGE" | "UNIVERSITY" | "OTHER";
  student_count: string;
  service_interest:
    | "FULL_PLATFORM"
    | "ACADEMICS_AND_LMS"
    | "OPERATIONS_AND_FINANCE"
    | "CUSTOM_IMPLEMENTATION";
  message: string;
  website: string;
};

const initialValues: FormValues = {
  contact_name: "",
  institution_name: "",
  work_email: "",
  phone: "",
  institution_type: "SCHOOL",
  student_count: "",
  service_interest: "FULL_PLATFORM",
  message: "",
  website: "",
};

/** A real sales enquiry form: it stores a lead, never provisions a tenant. */
export function ServiceRequestForm() {
  const [values, setValues] = useState<FormValues>(initialValues);
  const [state, setState] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [error, setError] = useState("");

  function update<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (state === "submitting") return;

    setState("submitting");
    setError("");

    try {
      const response = await fetch(`${API_URL}/api/v1/public/service-requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...values,
          student_count: values.student_count ? Number(values.student_count) : null,
        }),
      });
      const body: { message?: string } = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(body.message ?? "We could not send your request. Please try again.");
      }
      setState("success");
      setValues(initialValues);
    } catch (submissionError) {
      setState("error");
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "We could not send your request. Please try again.",
      );
    }
  }

  if (state === "success") {
    return (
      <div className="rounded-card border border-success/25 bg-success-light p-6 text-center">
        <CheckCircle2 className="mx-auto h-9 w-9 text-success-text" aria-hidden="true" />
        <h3 className="mt-3 font-display text-xl font-bold text-primary">Request received</h3>
        <p className="mt-2 text-sm leading-6 text-[#334155]">
          Thank you. An education-platform specialist will contact you within one business day.
        </p>
        <button
          type="button"
          onClick={() => setState("idle")}
          className="mt-5 text-sm font-semibold text-accent underline-offset-4 hover:underline"
        >
          Submit another request
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Your name" htmlFor="contact_name">
          <input
            required
            id="contact_name"
            value={values.contact_name}
            onChange={(event) => update("contact_name", event.target.value)}
            autoComplete="name"
            className={inputClass}
            placeholder="Aisha Rahman"
          />
        </Field>
        <Field label="Work email" htmlFor="work_email">
          <input
            required
            id="work_email"
            type="email"
            value={values.work_email}
            onChange={(event) => update("work_email", event.target.value)}
            autoComplete="email"
            className={inputClass}
            placeholder="aisha@institution.edu"
          />
        </Field>
      </div>
      <Field label="Institution name" htmlFor="institution_name">
        <input
          required
          id="institution_name"
          value={values.institution_name}
          onChange={(event) => update("institution_name", event.target.value)}
          autoComplete="organization"
          className={inputClass}
          placeholder="Northstar Academy"
        />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Institution type" htmlFor="institution_type">
          <select
            id="institution_type"
            value={values.institution_type}
            onChange={(event) => update("institution_type", event.target.value as FormValues["institution_type"])}
            className={inputClass}
          >
            <option value="SCHOOL">School</option>
            <option value="COLLEGE">College</option>
            <option value="UNIVERSITY">University</option>
            <option value="OTHER">Other education provider</option>
          </select>
        </Field>
        <Field label="Estimated learners" htmlFor="student_count" optional>
          <input
            id="student_count"
            type="number"
            min="1"
            max="2000000"
            inputMode="numeric"
            value={values.student_count}
            onChange={(event) => update("student_count", event.target.value)}
            className={inputClass}
            placeholder="e.g. 850"
          />
        </Field>
      </div>
      <Field label="What would you like help with?" htmlFor="service_interest">
        <select
          id="service_interest"
          value={values.service_interest}
          onChange={(event) => update("service_interest", event.target.value as FormValues["service_interest"])}
          className={inputClass}
        >
          <option value="FULL_PLATFORM">A complete institution platform</option>
          <option value="ACADEMICS_AND_LMS">Academics, LMS and assessments</option>
          <option value="OPERATIONS_AND_FINANCE">Operations, fees and administration</option>
          <option value="CUSTOM_IMPLEMENTATION">A tailored implementation</option>
        </select>
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Phone number" htmlFor="phone" optional>
          <input
            id="phone"
            type="tel"
            value={values.phone}
            onChange={(event) => update("phone", event.target.value)}
            autoComplete="tel"
            className={inputClass}
            placeholder="Optional"
          />
        </Field>
        {/* Honeypot: hidden from people but useful against basic automated spam. */}
        <div className="absolute -left-[10000px]" aria-hidden="true">
          <label htmlFor="website">Website</label>
          <input
            id="website"
            tabIndex={-1}
            autoComplete="off"
            value={values.website}
            onChange={(event) => update("website", event.target.value)}
          />
        </div>
      </div>
      <Field label="Anything else we should know?" htmlFor="message" optional>
        <textarea
          id="message"
          rows={3}
          value={values.message}
          onChange={(event) => update("message", event.target.value)}
          className={`${inputClass} h-auto py-3`}
          placeholder="Goals, timeline or current tools"
        />
      </Field>
      {state === "error" && (
        <p role="alert" className="rounded-field bg-destructive-light px-3 py-2 text-sm text-destructive-text">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={state === "submitting"}
        className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-field bg-accent px-5 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-70"
      >
        {state === "submitting" ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ArrowRight className="h-4 w-4" aria-hidden="true" />}
        {state === "submitting" ? "Sending request…" : "Book a consultation"}
      </button>
      <p className="text-center text-xs leading-5 text-muted-foreground">
        By submitting, you agree that shikshasync.me may contact you about this request. No tenant account is created from this form.
      </p>
    </form>
  );
}

const inputClass = "mt-1.5 h-11 w-full rounded-field border border-border bg-white px-3 text-sm text-primary outline-none transition placeholder:text-slate-400 focus:border-accent focus:ring-3 focus:ring-accent/15";

function Field({ label, htmlFor, optional, children }: { label: string; htmlFor: string; optional?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="text-sm font-medium text-[#334155]">
        {label} {optional && <span className="font-normal text-muted-foreground">(optional)</span>}
      </label>
      {children}
    </div>
  );
}
