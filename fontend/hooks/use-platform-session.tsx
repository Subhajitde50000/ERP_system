"use client";

/**
 * `usePlatformSession` — whoever is signed in to the platform console, or null.
 *
 * Two different account types share `app.shikshasync.me`:
 *   - `platform_users`  — Super Admin / Support / Sales / Finance (staff)
 *   - `platform_owners` — the paying customer who owns institutions
 * The shell needs one answer to "who is this and what may they see", so both
 * are resolved here and normalised to a single shape.
 *
 * `usePlatformAuth` / `useOwnerAuth` throw when their provider is absent,
 * which is correct for console pages but wrong for shared chrome:
 * `PlatformShell` also renders in `?role=` previews where no provider exists.
 * Reading the contexts directly returns null there instead of crashing, so one
 * shell serves the authenticated console and the design-doc preview alike.
 *
 * Read-only on purpose — anything that mutates a session belongs in the two
 * auth hooks, so there is exactly one place that logs in and out.
 */

import { useContext } from "react";

import { PlatformAuthContext } from "./use-platform-auth";
import { OwnerAuthContext } from "./use-owner-auth";
import type { PlatformRole } from "@/types/auth";

export interface PlatformSession {
  id: string;
  name: string;
  email: string;
  role: PlatformRole;
}

export function usePlatformSession(): PlatformSession | null {
  const staff = useContext(PlatformAuthContext);
  const owner = useContext(OwnerAuthContext);

  // Staff wins if both somehow exist: the staff console is the more privileged
  // surface, so it must never be masked by a stale owner session.
  if (staff?.user && staff.role) {
    return {
      id: staff.user.id,
      name: staff.user.name,
      email: staff.user.email,
      role: staff.role,
    };
  }

  if (owner?.owner) {
    return {
      id: owner.owner.id,
      name: owner.owner.name,
      email: owner.owner.email,
      role: "OWNER",
    };
  }

  return null;
}
