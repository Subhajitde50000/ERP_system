import type { Tenant } from "@/types/auth";
import { API_BASE_URL } from "./auth";

/**
 * Subdomain → tenant resolution.
 *
 * In production: calls GET /api/v1/tenants/by-slug/:slug which returns
 * { name, type, logo_url } or 404.
 *
 * In local development (localhost / *.localhost): the API call is still
 * attempted but falls back to the fixture map so the UI is reviewable
 * without a running database.
 */

/** Root domain; override per-environment with NEXT_PUBLIC_ROOT_DOMAIN. */
export const ROOT_DOMAIN =
  process.env.NEXT_PUBLIC_ROOT_DOMAIN ?? "shikshasync.me";

/** Hosts that never carry a tenant slug. */
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "0.0.0.0", "[::1]"]);

/** Reserved subdomains that map to the platform console, not an institution. */
const PLATFORM_SLUGS = new Set(["app", "admin", "www", "api"]);

/**
 * Local fixture — used as fallback when the backend is unreachable during
 * development. Remove entries here as real institutions are seeded.
 */
const FIXTURE_TENANTS: Record<string, Omit<Tenant, "host" | "slug">> = {
  "abc-college": {
    name: "ABC College",
    type: "COLLEGE",
    logoUrl: null,
    ssoProvider: "Google Workspace",
  },
  "dps-school": {
    name: "DPS School",
    type: "SCHOOL",
    logoUrl: null,
  },
  "nova-university": {
    name: "Nova University",
    type: "UNIVERSITY",
    logoUrl: null,
    ssoProvider: "Microsoft Entra ID",
  },
};

/** The platform console tenant (app.shikshasync.me). */
function platformTenant(host: string): Tenant {
  return {
    slug: "app",
    name: "shikshasync.me Platform",
    host,
    type: "PLATFORM",
    isPlatform: true,
    logoUrl: null,
  };
}

/**
 * Extract the tenant slug from a host header.
 * Returns null for localhost, bare apex domains and reserved subdomains.
 */
export function slugFromHost(host: string | null | undefined): string | null {
  if (!host) return null;

  const hostname = host.split(":")[0]!.toLowerCase().trim();
  if (!hostname || LOCAL_HOSTS.has(hostname)) return null;

  // Support *.localhost for local multi-tenant testing
  if (hostname.endsWith(".localhost")) {
    const sub = hostname.slice(0, -".localhost".length);
    return sub && !PLATFORM_SLUGS.has(sub) ? sub : null;
  }

  const rootParts = ROOT_DOMAIN.split(".").length;
  const parts = hostname.split(".");
  if (parts.length <= rootParts) return null;

  const sub = parts.slice(0, parts.length - rootParts).join(".");
  return sub || null;
}

/**
 * Fetch tenant details from the API.
 * Returns null on any error (404, network failure, etc.) so the caller can
 * fall back to the fixture map or show "Institution not found".
 *
 * This is a server-side only call — it runs inside Next.js Server Components
 * and page functions, never in the browser.
 */
async function fetchTenantBySlug(
  slug: string,
): Promise<Omit<Tenant, "host" | "slug"> | null> {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/v1/public/tenants/by-slug/${encodeURIComponent(slug)}`,
      {
        // Disable caching in development so new institutions are recognized immediately;
        // cache for 5 minutes in production to match the Redis TTL.
        next: { revalidate: process.env.NODE_ENV === "development" ? 0 : 300 },
      },
    );
    if (!res.ok) return null;

    const envelope = await res.json() as {
      success: boolean;
      data: {
        name: string;
        type: string;
        logo_url: string | null;
        sso_provider: string | null;
      };
    };
    if (!envelope.success || !envelope.data) return null;

    return {
      name: envelope.data.name,
      type: envelope.data.type as Tenant["type"],
      logoUrl: envelope.data.logo_url,
      ssoProvider: envelope.data.sso_provider ?? undefined,
    };
  } catch {
    return null;
  }
}

/**
 * Resolve a Host header into the tenant the login page should render for.
 * Async because it calls the API in production.
 *
 * @param host  Raw Host header, e.g. "abc-college.shikshasync.me"
 * @param slugOverride  Optional ?tenant= query value, for local development
 */
export async function resolveTenant(
  host: string | null | undefined,
  slugOverride?: string | null,
): Promise<Tenant> {
  const displayHost = (host ?? ROOT_DOMAIN).split(":")[0]!.toLowerCase();
  const slug =
    slugOverride?.trim().toLowerCase() || slugFromHost(host);

  if (!slug) return platformTenant(displayHost);
  if (PLATFORM_SLUGS.has(slug)) return platformTenant(displayHost);

  const badgeHost = slugOverride
    ? `${slug}.${ROOT_DOMAIN}`
    : displayHost;

  // 1. Try the real API
  const apiResult = await fetchTenantBySlug(slug);
  if (apiResult) {
    return { slug, host: badgeHost, ...apiResult };
  }

  // 2. Fall back to local fixture (dev only)
  const fixture = FIXTURE_TENANTS[slug];
  if (fixture) {
    return { slug, host: badgeHost, ...fixture };
  }

  // 3. Unknown slug — "Institution not found" state (design §7)
  return {
    slug,
    name: slug,
    host: badgeHost,
    type: "COLLEGE",
    notFound: true,
    logoUrl: null,
  };
}

/** Human label for the identifier field — colleges use roll numbers. */
export function identifierLabel(tenant: Tenant): string {
  if (tenant.isPlatform) return "Work email";
  return "Email or Roll Number";
}

export function identifierPlaceholder(tenant: Tenant): string {
  if (tenant.isPlatform) return "you@shikshasync.me";
  if (tenant.type === "SCHOOL") return "you@school.edu or ADM1024";
  return "you@college.edu or ROLL123";
}
