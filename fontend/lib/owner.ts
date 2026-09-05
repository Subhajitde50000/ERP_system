/**
 * Platform Owner API client — the xyz.com customer-account layer.
 *
 * One owner owns many institutions. This client backs the owner signup → verify
 * email → platform dashboard flow: My Institutions, Billing, Subscriptions,
 * Invoices, Payments, Support Tickets and Profile.
 *
 * Token storage mirrors the tenant flow: the short-lived access token lives in
 * memory (never localStorage); the refresh token is persisted under a key
 * separate from the tenant one so the two login systems never collide.
 */

import { API_BASE_URL } from "./auth";
import { APIError, requestJson, guardOwnerRefresh } from "./api-client";
import type {
  BillingSummary,
  OwnerCredentials,
  OwnerInstitution,
  OwnerInvoice,
  OwnerLoginResponse,
  OwnerPayment,
  OwnerProfile,
  OwnerSignupResult,
  OwnerSubscription,
  SupportTicket,
} from "@/types/owner";

const OWNER_REFRESH_KEY = "erp_owner_refresh";
const BASE = `${API_BASE_URL}/api/v1/owner`;

// ── In-memory access token ───────────────────────────────────────────────────
let _ownerAccessToken: string | null = null;

export function setOwnerAccessToken(t: string | null): void {
  _ownerAccessToken = t;
}

export function getOwnerAccessToken(): string | null {
  return _ownerAccessToken;
}

function saveOwnerRefresh(token: string): void {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(OWNER_REFRESH_KEY, token);
  }
}
function loadOwnerRefresh(): string | null {
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem(OWNER_REFRESH_KEY);
}
function clearOwnerRefresh(): void {
  if (typeof localStorage !== "undefined") {
    localStorage.removeItem(OWNER_REFRESH_KEY);
  }
}

const ownerFetch = <T>(
  path: string,
  init: RequestInit = {},
  auth = false,
): Promise<T> =>
  requestJson<T>(
    `${BASE}${path}`,
    init,
    auth ? _ownerAccessToken : null,
    "OwnerAPIError",
    // Only inject the refresh function for authenticated calls — unauthenticated
    // endpoints (signup, verify-email, etc.) should never attempt a token refresh.
    auth ? refreshOwnerToken : null,
    guardOwnerRefresh,
    true, // convert snake_case to camelCase for the owner API
  );

// ── Signup & verification ────────────────────────────────────────────────────

export async function ownerSignup(input: {
  name: string;
  email: string;
  password: string;
}): Promise<OwnerSignupResult> {
  return ownerFetch<OwnerSignupResult>("/signup", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function verifyOwnerEmail(token: string): Promise<OwnerProfile> {
  return ownerFetch<OwnerProfile>("/verify-email", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export async function resendOwnerVerification(email: string): Promise<void> {
  await ownerFetch("/resend-verification", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export async function ownerLogin(
  credentials: OwnerCredentials,
): Promise<OwnerLoginResponse> {
  // The API serialises camelCase (schemas/owner.py derives from `Wire`), so the
  // payload already *is* OwnerLoginResponse — no hand-written key mapping.
  const data = await ownerFetch<OwnerLoginResponse>("/login", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
  setOwnerAccessToken(data.tokens.accessToken);
  saveOwnerRefresh(data.tokens.refreshToken);
  return data;
}

export async function ownerLogout(): Promise<void> {
  const refresh = loadOwnerRefresh();
  try {
    await ownerFetch(
      "/logout",
      {
        method: "POST",
        body: JSON.stringify(refresh ? { refresh_token: refresh } : {}),
      },
      true,
    );
  } catch {
    // Teardown best-effort
  } finally {
    setOwnerAccessToken(null);
    clearOwnerRefresh();
  }
}

export async function refreshOwnerToken(): Promise<string | null> {
  const refresh = loadOwnerRefresh();
  try {
    const data = await ownerFetch<{ accessToken: string; expiresIn: number }>(
      "/refresh",
      {
        method: "POST",
        body: JSON.stringify(refresh ? { refresh_token: refresh } : {}),
      },
    );
    setOwnerAccessToken(data.accessToken);
    return data.accessToken;
  } catch {
    setOwnerAccessToken(null);
    clearOwnerRefresh();
    return null;
  }
}


export async function getOwnerMe(): Promise<OwnerProfile | null> {
  if (!_ownerAccessToken) return null;
  try {
    return await ownerFetch<OwnerProfile>("/me", { method: "GET" }, true);
  } catch {
    return null;
  }
}

// ── Password reset ───────────────────────────────────────────────────────────

export async function ownerForgotPassword(email: string): Promise<void> {
  await ownerFetch("/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  }).catch(() => undefined); // never reveals whether an account exists
}

export async function ownerResetPassword(
  token: string,
  password: string,
): Promise<void> {
  await ownerFetch("/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, password }),
  });
}

// ── Dashboard data ───────────────────────────────────────────────────────────

export async function fetchOwnerInstitutions(): Promise<OwnerInstitution[]> {
  const data = await ownerFetch<{ institutions: OwnerInstitution[] }>(
    "/institutions",
    { method: "GET" },
    true,
  );
  return data.institutions;
}

export async function fetchBillingSummary(): Promise<BillingSummary> {
  return ownerFetch<BillingSummary>("/billing/summary", { method: "GET" }, true);
}

export async function fetchOwnerSubscriptions(): Promise<OwnerSubscription[]> {
  return ownerFetch<OwnerSubscription[]>("/subscriptions", { method: "GET" }, true);
}

export async function fetchOwnerInvoices(): Promise<OwnerInvoice[]> {
  return ownerFetch<OwnerInvoice[]>("/invoices", { method: "GET" }, true);
}

export async function fetchOwnerPayments(): Promise<OwnerPayment[]> {
  return ownerFetch<OwnerPayment[]>("/payments", { method: "GET" }, true);
}

// ── Support tickets ──────────────────────────────────────────────────────────

export async function fetchOwnerTickets(): Promise<SupportTicket[]> {
  return ownerFetch<SupportTicket[]>("/tickets", { method: "GET" }, true);
}

export async function createOwnerTicket(input: {
  subject: string;
  category: string;
  priority?: string;
  tenantId?: string | null;
  message: string;
}): Promise<SupportTicket> {
  return ownerFetch<SupportTicket>("/tickets", {
    method: "POST",
    body: JSON.stringify(input),
  }, true);
}

export async function replyOwnerTicket(
  ticketId: string,
  message: string,
): Promise<SupportTicket> {
  return ownerFetch<SupportTicket>(`/tickets/${ticketId}/reply`, {
    method: "POST",
    body: JSON.stringify({ message }),
  }, true);
}

// ── Profile ──────────────────────────────────────────────────────────────────

export async function updateOwnerProfile(name: string): Promise<OwnerProfile> {
  return ownerFetch<OwnerProfile>("/profile", {
    method: "PUT",
    body: JSON.stringify({ name }),
  }, true);
}

export async function changeOwnerPassword(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  await ownerFetch("/change-password", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  }, true);
}

/** Re-exported for the owner auth forms — one error class, shared. */
export { APIError };
