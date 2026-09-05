/**
 * Auth API client — xyz.com ERP + LMS
 *
 * All calls go to the FastAPI backend at NEXT_PUBLIC_API_URL.
 * The slug (institution subdomain) is resolved before calls are made and
 * passed in the request body — the backend uses it to look up the tenant.
 *
 * Token storage:
 *   accessToken  — memory only (module-level variable). Never hits localStorage.
 *   refreshToken — localStorage under "erp_refresh". Cleared on logout.
 *
 * On every page load the in-memory access token is empty. `getAccessToken()`
 * silently tries a refresh so the user stays signed in across reloads without
 * storing the short-lived access token anywhere persistent.
 */

import { AuthError } from "@/types/auth";
import type {
  AuthErrorCode,
  LoginCredentials,
  LoginResponse,
  PlatformLoginCredentials,
  PlatformLoginResponse,
} from "@/types/auth";

// ── Config ────────────────────────────────────────────────────────────────────

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TENANT_LOGIN = `${API_BASE_URL}/api/v1/tenant/auth/login`;
const TENANT_LOGOUT = `${API_BASE_URL}/api/v1/tenant/auth/logout`;
const TENANT_REFRESH = `${API_BASE_URL}/api/v1/tenant/auth/refresh`;
const TENANT_FORGOT = `${API_BASE_URL}/api/v1/tenant/auth/forgot-password`;
const TENANT_VERIFY_TOKEN = `${API_BASE_URL}/api/v1/tenant/auth/reset-password/verify`;
const TENANT_RESET = `${API_BASE_URL}/api/v1/tenant/auth/reset-password`;

const PLATFORM_LOGIN = `${API_BASE_URL}/api/v1/platform/auth/login`;
const PLATFORM_LOGOUT = `${API_BASE_URL}/api/v1/platform/auth/logout`;
const PLATFORM_REFRESH = `${API_BASE_URL}/api/v1/platform/auth/refresh`;

const REFRESH_KEY = "erp_refresh";

// ── In-memory token store ─────────────────────────────────────────────────────
// Module-level so it survives component remounts but not page reloads —
// that is exactly the security property we want.

let _accessToken: string | null = null;

export function setAccessToken(t: string | null): void {
  _accessToken = t;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

// ── Refresh token persistence (localStorage) ─────────────────────────────────

function saveRefreshToken(token: string): void {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(REFRESH_KEY, token);
  }
}

function loadRefreshToken(): string | null {
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

function clearRefreshToken(): void {
  if (typeof localStorage !== "undefined") {
    localStorage.removeItem(REFRESH_KEY);
  }
}

// ── HTTP helpers ──────────────────────────────────────────────────────────────

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
async function apiFetch<T>(
  url: string,
  options: RequestInit,
  signal?: AbortSignal,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, { ...options, signal, credentials: "include" });
  } catch {
    throw new AuthError("NETWORK_ERROR", ERROR_MESSAGES.NETWORK_ERROR);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    // The FastAPI backend returns { detail: "..." } on errors
    const message: string =
      body?.message ?? body?.detail ?? ERROR_MESSAGES[codeFromStatus(res.status)];
    const code: AuthErrorCode =
      (body?.code as AuthErrorCode) ?? codeFromStatus(res.status);
    throw new AuthError(code, message);
  }

  const envelope = await res.json() as { success: boolean; data: T; message: string };
  return envelope.data;
}

// ── Tenant auth ───────────────────────────────────────────────────────────────

/**
 * Sign an institution user in.
 * Stores the refresh token in localStorage; keeps the access token in memory.
 */
export async function login(
  credentials: LoginCredentials,
  signal?: AbortSignal,
): Promise<LoginResponse> {
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
  }>(
    TENANT_LOGIN,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: credentials.tenantId,
        identifier: credentials.identifier,
        password: credentials.password,
      }),
    },
    signal,
  );

  setAccessToken(data.tokens.access_token);
  saveRefreshToken(data.tokens.refresh_token);

  return {
    user: {
      id: data.user.id,
      name: data.user.name,
      email: data.user.email ?? "",
      avatarUrl: null,
    },
    roles: data.user.roles as LoginResponse["roles"],
    enabledModules: [],  // populated from /me after login if needed
    tenant: {
      name: data.tenant.name,
      logo_url: data.tenant.logo_url,
      type: data.tenant.type as LoginResponse["tenant"]["type"],
    },
    accessToken: data.tokens.access_token,
  };
}

/** Log an institution user out and clear all stored tokens and cookies. */
export async function logout(signal?: AbortSignal): Promise<void> {
  const refreshToken = loadRefreshToken();
  try {
    await apiFetch<null>(
      TENANT_LOGOUT,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${_accessToken ?? ""}`,
        },
        body: JSON.stringify(refreshToken ? { refresh_token: refreshToken } : {}),
      },
      signal,
    );
  } catch {
    // Teardown best-effort
  } finally {
    setAccessToken(null);
    clearRefreshToken();
  }
}

/**
 * Silently refresh the access token using the httpOnly cookie or stored refresh token.
 * Returns the new access token, or null if the session has expired.
 * Call this on page load before any protected fetch.
 */
export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = loadRefreshToken();

  try {
    const data = await apiFetch<{ access_token: string }>(TENANT_REFRESH, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(refreshToken ? { refresh_token: refreshToken } : {}),
    });
    setAccessToken(data.access_token);
    return data.access_token;
  } catch {
    // Refresh token is invalid or expired — clear it so we don't loop
    setAccessToken(null);
    clearRefreshToken();
    return null;
  }
}


// ── Password reset (tenant users) ─────────────────────────────────────────────

/**
 * Request a password reset link.
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
    // Swallow all errors — the UI always shows the "check your inbox" screen.
    // If the server is unreachable the user would never get the email anyway,
    // but we still don't reveal that the request failed.
    if (err instanceof AuthError && err.code === "NETWORK_ERROR") throw err;
  }
}

/** Minimum password length — shared between login validation and reset form. */
export const MIN_PASSWORD_LENGTH = 6;

/** Why a reset token was refused. */
export type ResetTokenState = "VALID" | "MISSING" | "EXPIRED";

/**
 * Verify a reset token by calling the API.
 * Called server-side inside the Next.js page component before rendering.
 *
 * Returns MISSING when no token was provided, EXPIRED when the backend
 * returns a 400 (invalid or past the 30-minute window), VALID otherwise.
 */
export async function verifyResetToken(
  token: string | undefined,
): Promise<ResetTokenState> {
  if (!token?.trim()) return "MISSING";

  try {
    await apiFetch<null>(
      `${TENANT_VERIFY_TOKEN}?token=${encodeURIComponent(token)}`,
      { method: "GET" },
    );
    return "VALID";
  } catch (err) {
    if (
      err instanceof AuthError &&
      (err.code === "INVALID_CREDENTIALS" || err.code === "UNKNOWN")
    ) {
      return "EXPIRED";
    }
    // Network error — treat as expired so the UI shows "request a new link"
    return "EXPIRED";
  }
}

/** Set a new password using a valid reset token. */
export async function submitPasswordReset(
  token: string,
  password: string,
): Promise<void> {
  await apiFetch<null>(TENANT_RESET, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  });
}

// ── Platform console auth ─────────────────────────────────────────────────────

import type { PlatformRole } from "@/types/auth";

/** Normalize DB platform role enum values to frontend PlatformRole types. */
export function normalizePlatformRole(role: string): PlatformRole {
  switch (role) {
    case "SUPPORT":
    case "SUPPORT_STAFF":
      return "SUPPORT_STAFF";
    case "SALES":
    case "SALES_EXECUTIVE":
      return "SALES_EXECUTIVE";
    case "FINANCE":
    case "FINANCE_MANAGER":
      return "FINANCE_MANAGER";
    case "OWNER":
      return "OWNER";
    case "SUPER_ADMIN":
    default:
      return "SUPER_ADMIN";
  }
}

/** In-memory platform refresh token (not persisted — staff must re-auth on reload). */
let _platformRefreshToken: string | null = null;

/**
 * Sign a platform staff member in.
 * Platform refresh tokens are kept in memory only (not localStorage) because
 * platform accounts are higher-privilege and the console is a managed device.
 */
export async function platformLogin(
  credentials: PlatformLoginCredentials,
  signal?: AbortSignal,
): Promise<PlatformLoginResponse> {
  const data = await apiFetch<{
    tokens: { access_token: string; refresh_token: string };
    user: {
      id: string;
      name: string;
      email: string;
      role: string;
      last_login_at: string | null;
    };
  }>(
    PLATFORM_LOGIN,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: credentials.email,
        password: credentials.password,
      }),
    },
    signal,
  );

  setAccessToken(data.tokens.access_token);
  _platformRefreshToken = data.tokens.refresh_token;

  return {
    user: {
      id: data.user.id,
      name: data.user.name,
      email: data.user.email,
      lastLoginAt: data.user.last_login_at,
    },
    role: normalizePlatformRole(data.user.role),
    accessToken: data.tokens.access_token,
  };
}

/** Fetch currently authenticated platform staff profile. */
export async function getPlatformMe(signal?: AbortSignal): Promise<{
  id: string;
  name: string;
  email: string;
  role: PlatformRole;
  lastLoginAt: string | null;
} | null> {
  if (!_accessToken) return null;
  try {
    const data = await apiFetch<{
      id: string;
      name: string;
      email: string;
      role: string;
      is_active: boolean;
      last_login_at: string | null;
    }>(
      `${API_BASE_URL}/api/v1/platform/auth/me`,
      {
        method: "GET",
        headers: {
          Authorization: `Bearer ${_accessToken}`,
        },
      },
      signal,
    );
    return {
      id: data.id,
      name: data.name,
      email: data.email,
      role: normalizePlatformRole(data.role),
      lastLoginAt: data.last_login_at,
    };
  } catch {
    return null;
  }
}

/** Log a platform staff member out. */
export async function platformLogout(signal?: AbortSignal): Promise<void> {
  if (!_platformRefreshToken) return;
  try {
    await apiFetch<null>(
      PLATFORM_LOGOUT,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${_accessToken ?? ""}`,
        },
        body: JSON.stringify({ refresh_token: _platformRefreshToken }),
      },
      signal,
    );
  } finally {
    setAccessToken(null);
    _platformRefreshToken = null;
  }
}

/** Silently refresh a platform access token. Returns null if expired. */
export async function refreshPlatformToken(): Promise<string | null> {
  if (!_platformRefreshToken) return null;
  try {
    const data = await apiFetch<{ access_token: string }>(PLATFORM_REFRESH, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: _platformRefreshToken }),
    });
    setAccessToken(data.access_token);
    return data.access_token;
  } catch {
    setAccessToken(null);
    _platformRefreshToken = null;
    return null;
  }
}

/** Update the signed-in platform staff member's display name. */
export async function updatePlatformProfile(
  name: string,
  signal?: AbortSignal,
): Promise<{
  id: string;
  name: string;
  email: string;
  role: PlatformRole;
  lastLoginAt: string | null;
}> {
  const data = await apiFetch<{
    id: string;
    name: string;
    email: string;
    role: string;
    is_active: boolean;
    last_login_at: string | null;
  }>(
    `${API_BASE_URL}/api/v1/platform/auth/profile`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${_accessToken ?? ""}`,
      },
      body: JSON.stringify({ name }),
    },
    signal,
  );
  return {
    id: data.id,
    name: data.name,
    email: data.email,
    role: normalizePlatformRole(data.role),
    lastLoginAt: data.last_login_at,
  };
}

/** Change the signed-in platform staff member's password. */
export async function changePlatformPassword(
  currentPassword: string,
  newPassword: string,
  signal?: AbortSignal,
): Promise<void> {
  await apiFetch<null>(
    `${API_BASE_URL}/api/v1/platform/auth/change-password`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${_accessToken ?? ""}`,
      },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    },
    signal,
  );
}
