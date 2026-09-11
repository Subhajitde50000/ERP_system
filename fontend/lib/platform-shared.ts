import type { ModuleKey } from "@/types/auth";
import type { BillingCycle } from "@/types/platform";
import { ROOT_DOMAIN } from "./tenant";

/**
 * Small helpers shared by the platform data layer.
 *
 * Kept separate from `lib/navigation.ts` because that module imports Lucide
 * icons, which drags a client-only dependency into server data files — and
 * separate from `lib/platform.ts` for the same reason.
 */

/** Custom display labels that a plain capitalise would not format properly. */
const MODULE_CUSTOM_LABELS: Partial<Record<ModuleKey, string>> = {
  hr: "HR",
  parent: "Parent Portal",
};

/** Human label for a module key. */
export function moduleLabel(key: ModuleKey): string {
  return MODULE_CUSTOM_LABELS[key] ?? key.charAt(0).toUpperCase() + key.slice(1);
}

/** The platform's root domain, for display. */
export const ROOT_DOMAIN_LABEL = ROOT_DOMAIN;

/**
 * Returns the effective root domain at runtime.
 *
 * NEXT_PUBLIC_ROOT_DOMAIN is embedded at compile time, so if .env.local
 * changes without a server restart the stale value is used. This function
 * reads window.location.hostname at runtime in the browser so the correct
 * host is always used, regardless of the compiled env value.
 *
 * Rules:
 *  - On localhost / 127.0.0.1 → always returns "localhost:<port>"
 *  - On a real subdomain like abc.shikshasync.me → returns "shikshasync.me" (last 2 parts)
 *  - Server-side (no window) → falls back to NEXT_PUBLIC_ROOT_DOMAIN env
 */
function getRootDomain(): string {
  if (typeof window !== "undefined") {
    const hostname = window.location.hostname;
    const port = window.location.port;

    // Local development: bare localhost or 127.0.0.1
    if (hostname === "localhost" || hostname === "127.0.0.1" || hostname === "0.0.0.0") {
      return port ? `localhost:${port}` : "localhost";
    }

    // On a subdomain (e.g. abc.shikshasync.me) extract the root (shikshasync.me)
    const parts = hostname.split(".");
    if (parts.length >= 2) {
      return parts.slice(-2).join(".");
    }
    return hostname;
  }
  // Server-side rendering fallback
  return ROOT_DOMAIN;
}

/**
 * A tenant's public host — `green.localhost:3000` in dev, `green.shikshasync.me` in prod.
 *
 * Uses getRootDomain() so it always reflects the actual running environment,
 * not a potentially stale compiled env value.
 */
export function tenantHost(slug: string): string {
  const domain = getRootDomain();
  return `${slug}.${domain}`;
}

/** A tenant's login URL — uses http for localhost, https for everything else. */
export function tenantUrl(slug: string, path = ""): string {
  const host = tenantHost(slug);
  const protocol = host.includes("localhost") ? "http" : "https";
  return `${protocol}://${host}${path}`;
}



/** The platform console's own host — `app.shikshasync.me`. */
export const PLATFORM_HOST = `app.${ROOT_DOMAIN}`;

/**
 * Normalise a charge to a month so mixed billing cycles can be summed.
 *
 * A yearly commitment is still recurring revenue every month. Lives here
 * rather than in `lib/sales.ts` because `platform-data` needs it too, and
 * two implementations of MRR would eventually disagree.
 */
export function toMrr(amount: number, cycle: BillingCycle): number {
  return cycle === "YEARLY" ? Math.round(amount / 12) : amount;
}
