"use client";

/**
 * Owner console data hooks — the shikshasync.me account-holder's dashboard.
 *
 * Thin bindings over the shared `useResource` primitive, exactly like the
 * Super Admin hooks: one place owns loading/error/refetch, so neither console
 * repeats it. The API client (`lib/owner.ts`) and the backend routes
 * (`/api/v1/owner/*`) already existed — only the pages were never wired.
 */

import {
  fetchBillingSummary,
  fetchOwnerInstitutions,
  fetchOwnerInvoices,
  fetchOwnerPayments,
  fetchOwnerSubscriptions,
  fetchOwnerTickets,
} from "@/lib/owner";
import type {
  BillingSummary,
  OwnerInstitution,
  OwnerInvoice,
  OwnerPayment,
  OwnerSubscription,
  SupportTicket,
} from "@/types/owner";
import { useResource, type Resource } from "./use-resource";

export function useOwnerInstitutions(): Resource<OwnerInstitution[]> {
  return useResource(() => fetchOwnerInstitutions(), []);
}

export function useOwnerBilling(): Resource<BillingSummary> {
  return useResource(() => fetchBillingSummary(), []);
}

export function useOwnerSubscriptions(): Resource<OwnerSubscription[]> {
  return useResource(() => fetchOwnerSubscriptions(), []);
}

export function useOwnerInvoices(): Resource<OwnerInvoice[]> {
  return useResource(() => fetchOwnerInvoices(), []);
}

export function useOwnerPayments(): Resource<OwnerPayment[]> {
  return useResource(() => fetchOwnerPayments(), []);
}

export function useOwnerTickets(): Resource<SupportTicket[]> {
  return useResource(() => fetchOwnerTickets(), []);
}
