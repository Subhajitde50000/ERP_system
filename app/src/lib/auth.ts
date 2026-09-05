/**
 * Auth API client — xyz.com ERP + LMS (mobile port of fontend/lib/auth.ts)
 *
 * All calls go to the FastAPI backend at EXPO_PUBLIC_API_URL. The institution
 * slug is typed on the login screen (the website resolves it from the
 * subdomain; the app asks for it directly) and passed in the request body.
 *
 * Token storage mirrors the website:
 *   accessToken  — memory only (module-level variable).
 *   refreshToken — expo-secure-store under "erp_refresh". Cleared on logout.
 */

import * as SecureStore from "expo-secure-store";

import { errorMessage } from "./api-client";

// ── Config ────────────────────────────────────────────────────────────────────

/**
 * Resolve the backend URL for this build (B7).
 *
 * Dev keeps the localhost default — that is correct for an emulator
 * (10.0.2.2 is aliased by Android) and for Expo Go against a local server.
 * A *release* build that still points at localhost is broken by definition:
 * on a physical phone localhost is the phone itself, so the app ships dead.
 * Instead of shipping that, fail fast with an actionable message at startup.
 */
export function resolveApiBaseUrl(env: {
  EXPO_PUBLIC_API_URL?: string;
  NODE_ENV?: string;
}): string {
  const raw = (env.EXPO_PUBLIC_API_URL ?? "").trim();
  const isProduction = env.NODE_ENV === "production";
  if (!raw) {
    if (isProduction) {
      throw new Error(
        "This app was built without EXPO_PUBLIC_API_URL. Set it in eas.json " +
          "(or as an EAS secret) before producing a release build — see app/README.md.",
      );
    }
    return "http://localhost:8000";
  }
  if (isProduction && /^http:\/\/(localhost|127\.0\.0\.1|10\.0\.2\.2)/.test(raw)) {
    throw new Error(
      `EXPO_PUBLIC_API_URL (${raw}) is only reachable from a development ` +
        "machine. Release builds must use the HTTPS API URL — see app/README.md.",
    );
  }
  return raw.replace(/\/$/, "");
}

export const API_BASE_URL = resolveApiBaseUrl({
  EXPO_PUBLIC_API_URL: process.env.EXPO_PUBLIC_API_URL,
  NODE_ENV: process.env.NODE_ENV,
});

const TENANT_LOGIN = `${API_BASE_URL}/api/v1/tenant/auth/login`;
const TENANT_LOGOUT = `${API_BASE_URL}/api/v1/tenant/auth/logout`;
const TENANT_REFRESH = `${API_BASE_URL}/api/v1/tenant/auth/refresh`;
const TENANT_FORGOT = `${API_BASE_URL}/api/v1/tenant/auth/forgot-password`;

const REFRESH_KEY = "erp_refresh";
const INSTITUTION_SLUG_KEY = "erp_institution_slug";

// ── In-memory token store ─────────────────────────────────────────────────────

let _accessToken: string | null = null;

export function setAccessToken(t: string | null): void {
  _accessToken = t;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

// ── Refresh token persistence (secure store) ─────────────────────────────────

async function saveRefreshToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(REFRESH_KEY, token).catch(() => undefined);
}

async function loadRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_KEY).catch(() => null);
}

async function clearRefreshToken(): Promise<void> {
  await SecureStore.deleteItemAsync(REFRESH_KEY).catch(() => undefined);
}

// ── Institution slug persistence (secure store) ──────────────────────────────

export async function saveInstitutionSlug(slug: string): Promise<void> {
  await SecureStore.setItemAsync(INSTITUTION_SLUG_KEY, slug.trim().toLowerCase()).catch(() => undefined);
}

export async function loadInstitutionSlug(): Promise<string | null> {
  return SecureStore.getItemAsync(INSTITUTION_SLUG_KEY).catch(() => null);
}

export async function clearInstitutionSlug(): Promise<void> {
  await SecureStore.deleteItemAsync(INSTITUTION_SLUG_KEY).catch(() => undefined);
}

// ── HTTP helpers ──────────────────────────────────────────────────────────────

export type AuthErrorCode =
  | "INVALID_CREDENTIALS"
  | "TENANT_NOT_FOUND"
  | "MODULE_DISABLED"
  | "ACCOUNT_LOCKED"
  | "NETWORK_ERROR"
  | "UNKNOWN";

export class AuthError extends Error {
  code: AuthErrorCode;
  constructor(code: AuthErrorCode, message: string) {
    super(message);
    this.code = code;
  }
}

/** Map an HTTP status to the error codes the UI renders. */
export function codeFromStatus(httpStatus: number): AuthErrorCode {
  switch (httpStatus) {
    case 401:
    case 422:
      return "INVALID_CREDENTIALS";
    case 403:
      return "MODULE_DISABLED";
    case 404:
      return "TENANT_NOT_FOUND";
    case 423:
      return "ACCOUNT_LOCKED";
    case 429:
      return "ACCOUNT_LOCKED"; // rate-limited — show lockout message
    default:
      return "UNKNOWN";
  }
}

export const ERROR_MESSAGES: Record<AuthErrorCode, string> = {
  INVALID_CREDENTIALS: "Invalid email or password",
  TENANT_NOT_FOUND: "Institution not found. Check subdomain.",
  MODULE_DISABLED:
    "Your module access is disabled. Contact your institution admin.",
  ACCOUNT_LOCKED:
    "Account locked after too many attempts. Try again in 15 minutes.",
  NETWORK_ERROR: "Can't reach the server. Check your connection and retry.",
  UNKNOWN: "Something went wrong. Please try again.",
};

/** Shared fetch wrapper — throws AuthError on any non-ok response. */
async function apiFetch<T>(url: string, options: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, options);
  } catch {
    throw new AuthError("NETWORK_ERROR", ERROR_MESSAGES.NETWORK_ERROR);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    // The FastAPI backend returns { detail: "..." } on errors
    const message: string =
      (body as { message?: string })?.message ??
      errorMessage(body, res.status) ??
      ERROR_MESSAGES[codeFromStatus(res.status)];
    const code: AuthErrorCode =
      ((body as { code?: AuthErrorCode })?.code as AuthErrorCode) ??
      codeFromStatus(res.status);
    throw new AuthError(code, message);
  }

  const envelope = (await res.json()) as { success: boolean; data: T; message: string };
  return envelope.data;
}

// ── Tenant auth ───────────────────────────────────────────────────────────────

export interface LoginCredentials {
  identifier: string;
  password: string;
  remember: boolean;
  tenantId: string;
}

export interface LoginResponse {
  user: { id: string; name: string; email: string };
  roles: string[];
  tenant: { name: string; logo_url: string | null; type: string };
  accessToken: string;
}

/**
 * Sign an institution user in.
 * Stores the refresh token in the secure store; keeps the access token in memory.
 */
export async function login(credentials: LoginCredentials): Promise<LoginResponse> {
  const data = await apiFetch<{
    tokens: { access_token: string; refresh_token: string };
    user: {
      id: string;
      name: string;
      email: string | null;
      role: string;
      roles: string[];
      permissions: string[];
    };
    tenant: { name: string; logo_url: string | null; type: string };
  }>(TENANT_LOGIN, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      slug: credentials.tenantId,
      identifier: credentials.identifier,
      password: credentials.password,
    }),
  });

  setAccessToken(data.tokens.access_token);
  await saveRefreshToken(data.tokens.refresh_token);

  return {
    user: {
      id: data.user.id,
      name: data.user.name,
      email: data.user.email ?? "",
    },
    roles: data.user.roles,
    tenant: data.tenant,
    accessToken: data.tokens.access_token,
  };
}

/** Log an institution user out and clear all stored tokens. */
export async function logout(): Promise<void> {
  const refreshToken = await loadRefreshToken();
  if (!refreshToken) return;
  try {
    await apiFetch<null>(TENANT_LOGOUT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${_accessToken ?? ""}`,
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } finally {
    setAccessToken(null);
    await clearRefreshToken();
  }
}

/**
 * Silently refresh the access token using the stored refresh token.
 * Returns the new access token, or null if the session has expired.
 */
export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = await loadRefreshToken();
  if (!refreshToken) return null;

  try {
    const data = await apiFetch<{ access_token: string }>(TENANT_REFRESH, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    setAccessToken(data.access_token);
    return data.access_token;
  } catch {
    // Refresh token is invalid or expired — clear it so we don't loop
    setAccessToken(null);
    await clearRefreshToken();
    return null;
  }
}

/** Minimum password length — shared between login validation and reset form. */
export const MIN_PASSWORD_LENGTH = 6;

/**
 * Request a password reset link for a tenant user.
 * Always resolves — never reveals whether an account exists.
 */
export async function requestPasswordReset(
  identifier: string,
  tenantSlug: string,
): Promise<void> {
  try {
    await apiFetch<null>(TENANT_FORGOT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: tenantSlug, identifier }),
    });
  } catch (err) {
    if (err instanceof AuthError && err.code === "NETWORK_ERROR") {
      throw err;
    }
    // For privacy/security, backend always returns success or standard response
  }
}

