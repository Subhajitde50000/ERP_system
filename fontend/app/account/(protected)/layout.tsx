import { AccountGate } from "@/components/owner/account-gate";

/**
 * Owner platform dashboard — /account. The shikshasync.me "Platform Dashboard":
 * My Institutions, Billing, Subscriptions, Invoices, Support Tickets, Profile.
 * All routes here require an authenticated owner.
 */
export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return <AccountGate>{children}</AccountGate>;
}
