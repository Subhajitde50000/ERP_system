/**
 * Session context — mobile port of fontend/hooks/use-institution-auth.tsx.
 *
 * Uses the tenant JWT from lib/auth.ts (in-memory access token, refresh token
 * in the secure store) and `/tenant/auth/me` to load the signed-in user.
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
  loadInstitutionSlug,
  saveInstitutionSlug,
  clearInstitutionSlug as removeInstitutionSlug,
} from "./auth";
import { registerDevicePush, unregisterDevicePush } from "./push-registry";

export interface InstitutionUser {
  id: string;
  name: string;
  email: string | null;
  tenantId: string;
  roles: string[];
}

interface InstitutionAuthContextType {
  user: InstitutionUser | null;
  institutionSlug: string | null;
  isAuthenticated: boolean;
  hasRole: (role: string) => boolean;
  isLoading: boolean;
  logout: () => Promise<void>;
  /** Save and update current institution code */
  setInstitutionSlug: (slug: string) => Promise<void>;
  /** Clear saved institution code so user can choose another */
  clearInstitutionSlug: () => Promise<void>;
  /** Re-fetch `/tenant/auth/me` — used right after a successful login. */
  refresh: () => Promise<void>;
  /** Apply the user payload from the login response directly. */
  setUserFromLogin: (user: InstitutionUser | null) => void;
}

const InstitutionAuthContext = createContext<InstitutionAuthContextType | undefined>(undefined);

async function fetchMe(): Promise<InstitutionUser | null> {
  const token = getAccessToken();
  if (!token) return null;
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/tenant/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
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
  const [institutionSlug, setInstitutionSlugState] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const hydrate = useCallback(async () => {
    try {
      const savedSlug = await loadInstitutionSlug();
      if (savedSlug) {
        setInstitutionSlugState(savedSlug);
      }

      if (!getAccessToken()) await refreshAccessToken();
      const me = await fetchMe();
      setUser(me);
      if (me?.tenantId) {
        setInstitutionSlugState(me.tenantId);
        await saveInstitutionSlug(me.tenantId);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  /** Save and update institution slug */
  const setInstitutionSlug = useCallback(async (slug: string) => {
    const cleaned = slug.trim().toLowerCase();
    await saveInstitutionSlug(cleaned);
    setInstitutionSlugState(cleaned);
  }, []);

  /** Clear saved institution slug */
  const clearInstitutionSlug = useCallback(async () => {
    await removeInstitutionSlug();
    setInstitutionSlugState(null);
  }, []);

  /** Re-run hydration with a fresh access token (post-login). */
  const refresh = useCallback(async () => {
    const me = await fetchMe();
    setUser(me);
    if (me?.tenantId) {
      setInstitutionSlugState(me.tenantId);
      await saveInstitutionSlug(me.tenantId);
    }
  }, []);

  /** Apply the user returned by the login call itself — no extra round trip. */
  const setUserFromLogin = useCallback((next: InstitutionUser | null) => {
    setUser(next);
    if (next?.tenantId) {
      setInstitutionSlugState(next.tenantId);
      saveInstitutionSlug(next.tenantId);
    }
    setIsLoading(false);
  }, []);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  // Keep this device registered for push while a user is signed in. Runs after
  // hydration and after every login; safe to repeat — registration is an
  // idempotent upsert and degrades silently on runtimes without Firebase
  // (Expo Go / web), where push simply stays off.
  useEffect(() => {
    if (user) void registerDevicePush();
  }, [user]);

  const logout = useCallback(async () => {
    try {
      // Tell the backend this device no longer wants push before the tokens
      // are cleared. Best-effort internally — a failed unregister only leaves
      // a stale token that FCM will mark dead on the next delivery attempt.
      await unregisterDevicePush();
    } finally {
      try {
        await tenantLogout();
      } finally {
        setUser(null);
      }
    }
  }, []);

  return (
    <InstitutionAuthContext.Provider
      value={{
        user,
        institutionSlug,
        isAuthenticated: !!user,
        hasRole: (role: string) => !!user && user.roles.includes(role),
        isLoading,
        logout,
        setInstitutionSlug,
        clearInstitutionSlug,
        refresh,
        setUserFromLogin,
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
