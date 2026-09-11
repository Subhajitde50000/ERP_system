"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Building2,
  CreditCard,
  LifeBuoy,
  LogOut,
  Menu,
  Plus,
  ReceiptText,
  UserRound,
} from "lucide-react";

import { useOwnerAuth } from "@/hooks/use-owner-auth";
import { Button } from "@/components/ui/button";

/**
 * Platform-owner dashboard shell — the shikshasync.me account console.
 *
 * Nav mirrors the requested dashboard: My Institutions, Billing (subscriptions,
 * invoices, payments), Support Tickets and Profile, plus the "Create New
 * Institution" action. The owner signs in once here and manages every
 * institution they own.
 */

interface NavItem {
  label: string;
  href: string;
  icon: typeof Building2;
}
const NAV: NavItem[] = [
  { label: "My Institutions", href: "/account", icon: Building2 },
  { label: "Billing", href: "/account/billing", icon: CreditCard },
  { label: "Support Tickets", href: "/account/tickets", icon: LifeBuoy },
  { label: "Profile", href: "/account/profile", icon: UserRound },
];

export function OwnerShell({ children }: { children: React.ReactNode }) {
  const { owner, logout } = useOwnerAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const items = useMemo(
    () =>
      NAV.map((i) => ({
        ...i,
        active: i.href === "/account" ? pathname === "/account" : pathname.startsWith(i.href),
      })),
    [pathname],
  );

  const initials = (owner?.name ?? "U")
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col border-r border-border bg-white lg:flex">
        <SidebarContent
          items={items}
          ownerName={owner?.name ?? "Account"}
          ownerEmail={owner?.email ?? ""}
          initials={initials}
          onNavigate={() => {}}
          onLogout={async () => {
            await logout();
            router.push("/account/login");
          }}
        />
      </aside>

      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-primary/60 backdrop-blur-sm"
          />
          <div className="absolute inset-y-0 left-0 w-64 shadow-2xl">
            <SidebarContent
              items={items}
              ownerName={owner?.name ?? "Account"}
              ownerEmail={owner?.email ?? ""}
              initials={initials}
              onNavigate={() => setOpen(false)}
              onLogout={async () => {
                await logout();
                router.push("/account/login");
              }}
            />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-border bg-white px-4 lg:px-8">
          <button
            type="button"
            onClick={() => setOpen(true)}
            aria-label="Open navigation"
            className="-ml-1 rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground lg:hidden"
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
          <span className="font-display text-sm font-bold text-primary">Platform account</span>
          <div className="ml-auto">
            <Link href="/account/institutions/new">
              <Button className="!h-9 !px-3 !text-[13px]">
                <Plus className="h-4 w-4" aria-hidden="true" /> New institution
              </Button>
            </Link>
          </div>
        </header>
        <main className="flex-1 p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}

function SidebarContent({
  items,
  ownerName,
  ownerEmail,
  initials,
  onNavigate,
  onLogout,
}: {
  items: (NavItem & { active: boolean })[];
  ownerName: string;
  ownerEmail: string;
  initials: string;
  onNavigate: () => void;
  onLogout: () => void | Promise<void>;
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-5 py-5">
        <Link href="/" className="font-display text-lg font-extrabold tracking-tight text-primary">
          xyz<span className="text-accent">.com</span>
        </Link>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {items.map((i) => (
          <Link
            key={i.href}
            href={i.href}
            onClick={onNavigate}
            className={`flex items-center gap-3 rounded-field px-3 py-2.5 text-sm font-medium transition ${
              i.active
                ? "bg-accent-light text-accent"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            }`}
          >
            <i.icon className="h-4 w-4" aria-hidden="true" />
            {i.label}
          </Link>
        ))}
        <Link
          href="/account/billing"
          onClick={onNavigate}
          className="flex items-center gap-3 rounded-field px-3 py-2.5 text-sm font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          <ReceiptText className="h-4 w-4" aria-hidden="true" />
          Invoices
        </Link>
      </nav>

      <div className="border-t border-border p-3">
        <div className="flex items-center gap-3 px-2 py-2">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-light text-[13px] font-bold text-accent">
            {initials}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold text-foreground">{ownerName}</p>
            <p className="truncate text-[11px] text-muted-foreground">{ownerEmail}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onLogout}
          className="mt-1 flex w-full items-center gap-3 rounded-field px-3 py-2 text-sm font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          <LogOut className="h-4 w-4" aria-hidden="true" /> Sign out
        </button>
      </div>
    </div>
  );
}
