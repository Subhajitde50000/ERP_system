/**
 * Formatting helpers — ported from fontend/components/principal/principal-ui.tsx
 * and fontend/components/institution-console/weekly-grid.tsx so the app shows
 * the very same strings as the website.
 */

export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value.toFixed(value % 1 ? 1 : 0)}%`;
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function dateOnly(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.valueOf())) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function statusLabel(value: string): string {
  return value.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/** "09:30:00" → "09:30" */
export function clockTime(value: string): string {
  return value.length >= 5 ? value.slice(0, 5) : value;
}

export function inr(amount: number): string {
  return `₹${amount.toLocaleString("en-IN", { minimumFractionDigits: 0 })}`;
}

/** Local calendar date as `YYYY-MM-DD` — same helper the website uses for attendance. */
export function localDate(value: Date = new Date()): string {
  const y = value.getFullYear();
  const m = `${value.getMonth() + 1}`.padStart(2, "0");
  const d = `${value.getDate()}`.padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Compact relative age for feed rows, e.g. "5m ago", "3h ago", "12 Sep". */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const at = new Date(iso);
  if (Number.isNaN(at.valueOf())) return "";
  const minutes = Math.floor((Date.now() - at.valueOf()) / 60_000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(at);
}

/** ISO / server datetime → `YYYY-MM-DDTHH:MM` for a datetime-local field. */
export function toDatetimeLocal(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "";
  const pad = (n: number) => `${n}`.padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Parse a `YYYY-MM-DDTHH:MM` (or any Date-parseable) value to ISO, or null if empty. */
export function parseDatetimeLocal(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const date = new Date(trimmed);
  if (Number.isNaN(date.valueOf())) return null;
  return date.toISOString();
}
