"use client";

/**
 * Institution auth hook — the real tenant session behind the /admin console.
 *
 * Uses the tenant JWT from `lib/auth.ts` (in-memory access token, refresh token
 * in localStorage) and `/tenant/auth/me` to load the signed-in user's roles.
 * The /admin shell gates on `isAuthenticated` and a role of INSTITUTION_ADMIN.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import {
  API_BASE_URL,
  getAccessToken,
  refreshAccessToken,
  logout as tenantLogout,
} from "@/lib/auth";
import { disableWebPush } from "@/lib/web-push";

export interface InstitutionUser {
  id: string;
  name: string;
  email: string | null;
  tenantId: string;
  roles: string[];
}

interface InstitutionAuthContextType {
  user: InstitutionUser | null;
  isAuthenticated: boolean;
  /** Live role check used by every protected institution console. */
  hasRole: (role: string) => boolean;
  isLoading: boolean;
  logout: () => Promise<void>;
}

const InstitutionAuthContext = createContext<InstitutionAuthContextType | undefined>(undefined);

async function fetchMe(): Promise<InstitutionUser | null> {
  const token = getAccessToken();
  if (!token) return null;
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/tenant/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      credentials: "include",
    });
    if (!res.ok) return null;
    const env = await res.json();
    const d = env?.data;
    if (!d) return null;
    return {
      id: d.id,
      name: d.name,
      email: d.email,
      tenantId: d.tenant_id,
      roles: d.roles ?? [],
    };
  } catch {
    return null;
  }
}

export function InstitutionAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<InstitutionUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        if (!getAccessToken()) await refreshAccessToken();
        const me = await fetchMe();
        if (mounted) setUser(me);
      } finally {
        if (mounted) setIsLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const logout = useCallback(async () => {
    try {
      // Unregister this browser from web push first (best-effort, no-op when
      // Firebase isn't configured) so private notifications never land on a
      // signed-out shared device.
      await disableWebPush();
      await tenantLogout();
    } finally {
      setUser(null);
    }
  }, []);

  return (
    <InstitutionAuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        hasRole: (role: string) => !!user && user.roles.includes(role),
        isLoading,
        logout,
      }}
    >
      {children}
    </InstitutionAuthContext.Provider>
  );
}

export function useInstitutionAuth(): InstitutionAuthContextType {
  const ctx = useContext(InstitutionAuthContext);
  if (!ctx) throw new Error("useInstitutionAuth must be used within an InstitutionAuthProvider");
  return ctx;
}
