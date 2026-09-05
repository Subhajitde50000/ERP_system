"use client";

import { Loader2 } from "lucide-react";

/** Shared presentational bits for the /admin pages — keeps them DRY. */

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 className="font-display text-2xl font-extrabold tracking-tight text-primary">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p> : null}
      </div>
      {action}
    </header>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-card border border-border bg-white p-5 sm:p-6 ${className}`}>{children}</div>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 rounded-card border border-border bg-white py-16 text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    // role="alert" so screen readers announce load failures instead of
    // leaving the user on a silently stale screen.
    <div
      role="alert"
      className="rounded-card border border-destructive-border bg-destructive-light px-5 py-10 text-center text-sm font-medium text-destructive-text"
    >
      {message}
    </div>
  );
}

export function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-card border border-dashed border-border bg-white px-6 py-12 text-center text-sm text-muted-foreground">
      {text}
    </div>
  );
}

export const inputClass =
  "h-11 w-full rounded-field border border-[#E2E8F0] bg-white px-3.5 text-sm text-primary outline-none transition placeholder:text-[#94A3B8] focus:border-accent focus:ring-3 focus:ring-accent/15";

export const labelClass = "mb-1.5 block text-[13px] font-medium text-[#334155]";
