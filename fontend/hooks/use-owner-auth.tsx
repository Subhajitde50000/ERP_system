"use client";

/**
 * Owner Authentication Hook — `useOwnerAuth`
 *
 * Reactive access to the platform-owner (customer account) session:
 * - `owner`: current OwnerProfile or null
 * - `isAuthenticated`, `isLoading`, `error`
 * - `login`, `logout`, `refresh`
 *
 * This is the shikshasync.me "Platform Login" door: Rahul signs in once and manages
 * every institution he owns. It is deliberately separate from the staff
 * console (`usePlatformAuth`) and the institution login (`/login`).
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
  getOwnerMe,
  ownerLogin,
  ownerLogout,
  refreshOwnerToken,
  getOwnerAccessToken,
} from "@/lib/owner";
import type { OwnerCredentials, OwnerProfile } from "@/types/owner";

interface OwnerAuthContextType {
  owner: OwnerProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (credentials: OwnerCredentials) => Promise<OwnerProfile>;
  logout: () => Promise<void>;
  refresh: () => Promise<string | null>;
}

/**
 * Exported so `usePlatformSession` can read the session without throwing when
 * no provider is mounted (shared chrome, `?role=` previews). Consumers that
 * need login/logout should use `useOwnerAuth` instead.
 */
export const OwnerAuthContext = createContext<OwnerAuthContextType | undefined>(
  undefined,
);

export function OwnerAuthProvider({ children }: { children: ReactNode }) {
  const [owner, setOwner] = useState<OwnerProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        let token = getOwnerAccessToken();
        if (!token) token = await refreshOwnerToken();
        if (token) {
          const me = await getOwnerMe();
          if (mounted && me) setOwner(me);
        }
      } catch {
        /* invalid session — stay signed out */
      } finally {
        if (mounted) setIsLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const login = useCallback(async (credentials: OwnerCredentials) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await ownerLogin(credentials);
      setOwner(res.owner);
      setIsLoading(false);
      return res.owner;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Sign in failed";
      setError(msg);
      setIsLoading(false);
      throw err;
    }
  }, []);

  const logout = useCallback(async () => {
    setIsLoading(true);
    try {
      await ownerLogout();
    } finally {
      setOwner(null);
      setError(null);
      setIsLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    const token = await refreshOwnerToken();
    if (token) {
      const me = await getOwnerMe();
      if (me) setOwner(me);
    } else {
      setOwner(null);
    }
    return token;
  }, []);

  return (
    <OwnerAuthContext.Provider
      value={{ owner, isAuthenticated: !!owner, isLoading, error, login, logout, refresh }}
    >
      {children}
    </OwnerAuthContext.Provider>
  );
}

export function useOwnerAuth(): OwnerAuthContextType {
  const ctx = useContext(OwnerAuthContext);
  if (!ctx) throw new Error("useOwnerAuth must be used within an OwnerAuthProvider");
  return ctx;
}
