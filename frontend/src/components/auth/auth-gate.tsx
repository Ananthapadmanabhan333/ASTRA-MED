"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LockKeyhole, LogIn, Orbit, ShieldAlert } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useId, useState } from "react";

import { LiveBridge } from "@/components/shell/live-bridge";
import { Button } from "@/components/ui/button";
import { api, ApiError, unwrap } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/store";
import { clearEcg } from "@/lib/live/ecg-buffer";
import { useLive } from "@/lib/live/store";

async function loadSession() {
  const { setSession, signedOut } = useAuth.getState();
  try {
    setSession(await unwrap(api.GET("/api/auth/me")));
  } catch {
    signedOut(null); // not signed in, or the API is unreachable (the sign-in form reports that)
  }
}

/**
 * Renders the application only for a signed-in user. Anyone else sees the sign-in screen at the
 * same URL, so deep links survive signing in. The live WebSocket connects only after sign-in.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const status = useAuth((s) => s.status);
  const canStream = useAuth((s) => !!s.session?.permissions.includes("health:read"));
  const qc = useQueryClient();

  useEffect(() => {
    // Roles without crew health access never open the live stream (the server would refuse it).
    if (status === "signed_in" && !canStream) useLive.getState().setConnection("offline", 0);
  }, [status, canStream]);

  useEffect(() => {
    void loadSession();
  }, []);

  useEffect(() => {
    // Never keep health records in memory once the session has ended: REST caches, the live
    // store (readings, trails, alerts, events, sandbox state) and the ECG sample buffer.
    if (status === "signed_out") {
      qc.clear();
      useLive.getState().reset();
      clearEcg();
    }
  }, [status, qc]);

  if (status === "loading") {
    return (
      <div role="status" className="flex min-h-dvh items-center justify-center gap-3 text-ink-2">
        <Orbit className="size-6 animate-spin text-telemetry motion-reduce:animate-none" aria-hidden />
        Checking your session
      </div>
    );
  }
  if (status === "signed_out") return <SignIn />;
  return (
    <>
      {canStream && <LiveBridge />}
      {children}
    </>
  );
}

function SignIn() {
  const reason = useAuth((s) => s.reason);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const errorId = useId();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await unwrap(api.POST("/api/auth/login", { body: { username, password } }));
      setPassword("");
      useAuth.getState().setSession(session);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main id="main" className="flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center gap-2">
          <Orbit className="size-7 text-telemetry" aria-hidden />
          <span className="font-heading text-2xl font-bold tracking-tight">
            ASTRA<span className="font-medium text-ink-2">-MED</span>
          </span>
        </div>
        <div className="rounded-lg border border-bulkhead bg-hull p-5">
          <h1 className="flex items-center gap-2 font-heading text-xl font-semibold">
            <LockKeyhole className="size-5 text-ink-3" aria-hidden /> Sign in
          </h1>
          <p className="mt-1 text-sm text-ink-2">Crew health records are restricted to authorised mission staff.</p>
          {reason === "expired" && (
            <p className="mt-3 rounded-md border border-caution/40 bg-caution/10 px-3 py-2 text-sm text-caution">
              Your session ended. Sign in again to continue.
            </p>
          )}
          <form onSubmit={submit} className="mt-4 space-y-3" aria-describedby={error ? errorId : undefined}>
            <div className="space-y-1">
              <label htmlFor="username" className="text-sm font-medium">Username</label>
              <input
                id="username"
                name="username"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-abyss px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="password" className="text-sm font-medium">Password</label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-abyss px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
              />
            </div>
            {error && (
              <p id={errorId} role="alert" className="flex items-start gap-2 text-sm text-critical">
                <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden /> {error}
              </p>
            )}
            <Button type="submit" size="lg" className="w-full" disabled={busy}>
              <LogIn aria-hidden /> {busy ? "Signing in" : "Sign in"}
            </Button>
          </form>
        </div>
        <p className="text-xs leading-relaxed text-ink-3">
          Research prototype with simulated crew data. Not a medical device.
          {process.env.NODE_ENV === "development" && (
            <>
              {" "}For local demo accounts run <code className="text-ink-2">python scripts/create_users.py dev</code> in
              the backend; the credentials are written to <code className="text-ink-2">backend/.dev-users.json</code>.
            </>
          )}
        </p>
      </div>
    </main>
  );
}
