/**
 * Platform owner (customer account) contracts — the shikshasync.me account-holder
 * who owns one or more institutions. This is the AWS / Shopify / Zoho model:
 * sign up once, manage every institution from a single platform dashboard.
 */

export interface OwnerSignupResult {
  id: string;
  name: string;
  email: string;
  isEmailVerified: boolean;
  /** Present only in dev/no-mailer mode so the flow can complete. */
  verificationToken: string | null;
}

export interface OwnerProfile {
  id: string;
  name: string;
  email: string;
  isEmailVerified: boolean;
  isActive: boolean;
  lastLoginAt: string | null;
  createdAt: string;
}

export interface OwnerTokens {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

export interface OwnerLoginResponse {
  tokens: OwnerTokens;
  owner: OwnerProfile;
}

export interface OwnerInstitution {
  id: string;
  name: string;
  slug: string;
  type: "SCHOOL" | "COLLEGE";
  planName: string | null;
  subscriptionStatus: "TRIAL" | "ACTIVE" | "PAST_DUE" | "CANCELLED" | null;
  isActive: boolean;
  trialEndsAt: string | null;
  loginUrl: string;
  createdAt: string;
}

export interface BillingSummary {
  totalInstitutions: number;
  activeSubscriptions: number;
  trialing: number;
  nextRenewalAt: string | null;
  lifetimeSpend: number;
  currency: string;
  outstanding: number;
}

export interface OwnerSubscription {
  id: string;
  tenantId: string;
  tenantName: string;
  planName: string;
  status: "TRIAL" | "ACTIVE" | "PAST_DUE" | "CANCELLED";
  amount: number;
  currency: string;
  startsAt: string;
  endsAt: string | null;
}

export interface OwnerInvoice {
  id: string;
  invoiceNumber: string;
  tenantId: string;
  tenantName: string;
  status: string;
  issuedAt: string;
  total: number;
  amountPaid: number;
  currency: string;
}

export interface OwnerPayment {
  id: string;
  tenantId: string | null;
  tenantName: string | null;
  status: string;
  method: string;
  amount: number;
  currency: string;
  gateway: string | null;
  receivedAt: string | null;
  createdAt: string;
}

export interface TicketMessage {
  id: string;
  authorRole: "OWNER" | "STAFF";
  body: string;
  createdAt: string;
}

export interface SupportTicket {
  id: string;
  subject: string;
  category: string;
  status: "OPEN" | "IN_PROGRESS" | "RESOLVED" | "CLOSED";
  priority: string;
  tenantId: string | null;
  tenantName: string | null;
  createdAt: string;
  updatedAt: string;
  messages: TicketMessage[];
}

export interface OwnerCredentials {
  email: string;
  password: string;
}
