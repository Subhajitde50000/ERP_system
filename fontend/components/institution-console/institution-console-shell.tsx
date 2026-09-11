"use client";

/**
 * Shared authenticated shell for institution leadership consoles.
 *
 * Admin and Principal screens have different nav policies, but they must not
 * maintain two copies of the responsive drawer, session identity and sign-out
 * flow.  Each console supplies only its title and permitted navigation items.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Bell, GraduationCap, LogOut, Menu, X, type LucideIcon } from "lucide-react";

import { useInstitutionAuth } from "@/hooks/use-institution-auth";
import { useUnreadNotifications } from "@/hooks/use-unread-notifications";

export interface InstitutionConsoleNavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

export function InstitutionConsoleShell({
  children,
  navigation,
  consoleTitle,
  headerTitle,
  roleLabel,
}: {
  children: React.ReactNode;
  navigation: InstitutionConsoleNavItem[];
  consoleTitle: string;
  headerTitle: string;
  roleLabel: string;
}) {
  const { user, logout } = useInstitutionAuth();
  const router = useRouter();
  const pathname = usePathname();
  const { unread } = useUnreadNotifications();
  const [open, setOpen] = useState(false);

  // Every console serves its own /notifications page (student/teacher/admin…
  // route prefix), so the bell links to the *current* console's inbox.
  const notificationsHref = `/${pathname.split("/")[1] || ""}/notifications`;

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const initials = (user?.name ?? roleLabel)
    .split(" ")
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-5 py-5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-white">
          <GraduationCap className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="truncate font-display text-sm font-bold text-primary">{consoleTitle}</p>
          <p className="truncate text-[11px] text-muted-foreground">{user?.name ?? "—"}</p>
        </div>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-3">
        {navigation.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setOpen(false)}
              className={`flex items-center gap-3 rounded-field px-3 py-2.5 text-sm font-medium transition ${
                active
                  ? "bg-accent-light text-accent"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <item.icon className="h-4 w-4" aria-hidden="true" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-border p-3">
        <div className="flex items-center gap-3 px-2 py-2">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-light text-[13px] font-bold text-accent">
            {initials}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold text-foreground">{user?.email ?? "—"}</p>
            <p className="truncate text-[11px] text-muted-foreground">{roleLabel}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={async () => {
            await logout();
            router.push("/login");
          }}
          className="mt-1 flex w-full items-center gap-3 rounded-field px-3 py-2 text-sm font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          Sign out
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-border bg-white lg:block">
        {sidebar}
      </aside>

      {open ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-primary/60 backdrop-blur-sm"
          />
          <div className="absolute inset-y-0 left-0 w-64 bg-white shadow-2xl">{sidebar}</div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-border bg-white px-4 lg:px-8">
          <button
            type="button"
            onClick={() => setOpen(true)}
            aria-label="Open navigation"
            className="-ml-1 rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground lg:hidden"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <GraduationCap className="hidden h-4 w-4 text-muted-foreground sm:block" aria-hidden="true" />
          <span className="font-display text-sm font-bold text-primary">{headerTitle}</span>
          <div className="ml-auto flex items-center gap-2">
            <Link
              href={notificationsHref}
              aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
              className="relative rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <Bell className="h-[18px] w-[18px]" aria-hidden="true" />
              {unread > 0 ? (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-bold text-white">
                  {unread > 99 ? "99+" : unread}
                </span>
              ) : null}
            </Link>
          </div>
        </header>
        <main className="flex-1 p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
