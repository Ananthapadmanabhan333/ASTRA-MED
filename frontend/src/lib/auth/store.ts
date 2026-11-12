import { create } from "zustand";

import type { SessionInfo } from "@/lib/api/types";

export type AuthStatus = "loading" | "signed_in" | "signed_out";

interface AuthState {
  status: AuthStatus;
  session: SessionInfo | null;
  /** Why the user is looking at the sign-in screen, if not their first visit. */
  reason: "expired" | "signed_out" | null;
  setSession: (session: SessionInfo) => void;
  signedOut: (reason: AuthState["reason"]) => void;
}

/**
 * Who is signed in. The session token itself lives only in an HttpOnly cookie that scripts
 * cannot read; this store keeps the user, their permissions and the CSRF token in memory.
 */
export const useAuth = create<AuthState>((set) => ({
  status: "loading",
  session: null,
  reason: null,
  setSession: (session) => set({ status: "signed_in", session, reason: null }),
  signedOut: (reason) => set({ status: "signed_out", session: null, reason }),
}));

export function useCan(permission: string): boolean {
  return useAuth((s) => !!s.session?.permissions.includes(permission));
}

export function currentCsrf(): string | null {
  return useAuth.getState().session?.csrf_token ?? null;
}
