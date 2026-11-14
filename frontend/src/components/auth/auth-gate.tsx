"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Compass, KeyRound, LockKeyhole, LogIn, LogOut, Orbit, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useEffect, useId, useState } from "react";
import { toast } from "sonner";

import { ScreenDirectoryDialog } from "@/components/shell/breadcrumbs";
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
 * Renders the application only for a signed-in user, except the public /landing page.
 * Anyone else sees the sign-in screen at the same URL, so deep links survive signing in.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const status = useAuth((s) => s.status);
  const canStream = useAuth((s) => !!s.session?.permissions.includes("health:read"));
  const pathname = usePathname() ?? "/";
  const qc = useQueryClient();

  useEffect(() => {
    if (status === "signed_in" && !canStream) useLive.getState().setConnection("offline", 0);
  }, [status, canStream]);

  useEffect(() => {
    void loadSession();
  }, []);

  useEffect(() => {
    if (status === "signed_out") {
      qc.clear();
      useLive.getState().reset();
      clearEcg();
    }
  }, [status, qc]);

  if (pathname === "/landing") {
    return <>{children}</>;
  }

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

export function SignIn() {
  const reason = useAuth((s) => s.reason);
  const session = useAuth((s) => s.session);
  const router = useRouter();
  const [username, setUsername] = useState("astronaut@astramed.org");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [mode, setMode] = useState<"signin" | "forgot" | "register">("signin");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dirOpen, setDirOpen] = useState(false);
  const errorId = useId();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    // Map email-style demo usernames (e.g. astronaut@astramed.org -> operator) if needed while keeping exact usernames working
    const trimmed = username.trim();
    const mappedUser =
      trimmed.toLowerCase() === "astronaut@astramed.org" || trimmed.toLowerCase() === "alex.carter@astramed.org"
        ? "operator"
        : trimmed.includes("@")
          ? trimmed.split("@")[0]
          : trimmed;
    try {
      const nextSession = await unwrap(api.POST("/api/auth/login", { body: { username: mappedUser, password } }));
      setPassword("");
      useAuth.getState().setSession(nextSession);
      toast.success(`Signed in as ${nextSession.user.display_name}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  async function signOutCurrent() {
    try {
      await api.POST("/api/auth/logout");
    } catch {
      // ignore
    }
    useAuth.getState().signedOut(null);
    toast.success("Signed out of mission workspace");
  }

  return (
    <div id="main" className="aero-grid flex min-h-dvh flex-col justify-between bg-[#050d1a] px-4 py-6 sm:px-8">
      {/* Top Bar */}
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between">
        <Link href="/landing" className="flex items-center gap-2 text-foreground hover:text-telemetry">
          <Orbit className="size-6 text-telemetry" aria-hidden />
          <span className="font-heading text-xl font-bold tracking-wider">
            ASTRA<span className="text-telemetry">-MED</span>
          </span>
        </Link>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setDirOpen(true)} className="text-telemetry">
            <Compass className="size-4" aria-hidden /> All 26 Screens
          </Button>
          <Button asChild variant="outline" size="sm" className="border-bulkhead bg-hull/70">
            <Link href="/landing">Landing Page</Link>
          </Button>
        </div>
      </div>

      {/* Main Split Card matching Screen 2 */}
      <div className="mx-auto my-8 grid w-full max-w-5xl overflow-hidden rounded-2xl border border-bulkhead bg-hull shadow-2xl lg:grid-cols-12">
        {/* Left Visual Panel */}
        <div className="relative flex flex-col justify-between overflow-hidden border-b border-bulkhead bg-gradient-to-b from-[#0b213d] via-[#08172c] to-[#050e1c] p-8 lg:col-span-6 lg:border-r lg:border-b-0">
          <svg
            viewBox="0 0 420 260"
            className="w-full drop-shadow-[0_0_30px_rgba(61,216,234,0.2)]"
            aria-hidden
          >
            <defs>
              <radialGradient id="authHorizon" cx="50%" cy="100%" r="80%">
                <stop offset="0%" stopColor="#3dd8ea" stopOpacity="0.5" />
                <stop offset="55%" stopColor="#123a63" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#050e1c" stopOpacity="0" />
              </radialGradient>
            </defs>
            <ellipse cx="210" cy="275" rx="310" ry="135" fill="url(#authHorizon)" />
            <path d="M -40 225 Q 210 135 460 225" fill="none" stroke="#3dd8ea" strokeWidth="2" opacity="0.8" />
            {/* ISS Orbital Silhouette */}
            <g transform="translate(95, 42) rotate(-8)" stroke="#3dd8ea" strokeWidth="1.5" fill="#0d223d">
              <line x1="0" y1="40" x2="210" y2="40" stroke="#8fb4ff" strokeWidth="2" />
              <rect x="8" y="6" width="26" height="30" />
              <rect x="8" y="44" width="26" height="30" />
              <rect x="40" y="6" width="26" height="30" />
              <rect x="40" y="44" width="26" height="30" />
              <rect x="88" y="30" width="36" height="20" rx="3" fill="#173861" />
              <rect x="100" y="16" width="14" height="48" rx="2" fill="#173861" />
              <rect x="142" y="6" width="26" height="30" />
              <rect x="142" y="44" width="26" height="30" />
              <rect x="174" y="6" width="26" height="30" />
              <rect x="174" y="44" width="26" height="30" />
            </g>
          </svg>

          <div className="space-y-3 pt-4">
            <div className="flex items-center gap-2">
              <Orbit className="size-7 text-telemetry" aria-hidden />
              <span className="font-heading text-3xl font-bold tracking-wider">ASTRA-MED</span>
            </div>
            <p className="font-heading text-xl font-medium text-ink-1">Secure Access to Mission Systems</p>
            <p className="text-xs leading-relaxed text-ink-2">
              Role-based access control (Flight Surgeon, Mission Operator, Analyst, Administrator) with scrypt password
              hashing, HttpOnly session cookies, CSRF validation, and append-only audit logging.
            </p>
            <div className="flex flex-wrap gap-1.5 pt-2 text-[11px] text-ink-3">
              {["operator", "surgeon", "analyst", "admin"].map((roleUser) => (
                <button
                  key={roleUser}
                  type="button"
                  onClick={() => setUsername(roleUser)}
                  className="rounded border border-bulkhead bg-abyss/60 px-2 py-0.5 text-ink-2 hover:border-telemetry hover:text-telemetry"
                >
                  Use `{roleUser}`
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right Sign-In Form Panel */}
        <div className="flex flex-col justify-center p-8 sm:p-10 lg:col-span-6">
          {session && (
            <div className="mb-5 rounded-lg border border-nominal/40 bg-nominal/10 p-3.5 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 font-semibold text-nominal">
                  <ShieldCheck className="size-4" aria-hidden />
                  Signed in as {session.user.display_name} ({session.user.role_label})
                </span>
                <div className="flex gap-2">
                  <Button size="xs" onClick={() => router.push("/")}>
                    Mission Control <ArrowRight className="size-3" aria-hidden />
                  </Button>
                  <Button size="xs" variant="outline" onClick={signOutCurrent}>
                    <LogOut className="size-3" aria-hidden /> Sign Out
                  </Button>
                </div>
              </div>
            </div>
          )}

          <div className="mb-6">
            <h1 className="flex items-center gap-2 font-heading text-3xl font-bold">
              <LockKeyhole className="size-6 text-telemetry" aria-hidden />
              {mode === "signin" ? "Sign In" : mode === "forgot" ? "Credential Recovery" : "Request Mission Account"}
            </h1>
            <p className="mt-1 text-sm text-ink-2">
              {mode === "signin"
                ? "Access your mission workspace"
                : mode === "forgot"
                  ? "Reset local prototype credentials via the backend CLI"
                  : "Provision a mission role account"}
            </p>
          </div>

          {reason === "expired" && (
            <p className="mb-4 rounded-md border border-caution/40 bg-caution/10 px-3 py-2 text-sm text-caution">
              Your session ended. Sign in again to continue.
            </p>
          )}

          {mode === "signin" ? (
            <>
              <form onSubmit={submit} className="space-y-4" aria-describedby={error ? errorId : undefined}>
                <div className="space-y-1.5">
                  <label htmlFor="username" className="text-xs font-medium text-ink-2">
                    Email address or Username
                  </label>
                  <input
                    id="username"
                    name="username"
                    autoComplete="username"
                    required
                    placeholder="astronaut@astramed.org or operator"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="h-10 w-full rounded-md border border-input bg-abyss px-3 text-sm text-foreground outline-none focus-visible:border-telemetry focus-visible:ring-2 focus-visible:ring-telemetry/30"
                  />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="password" className="text-xs font-medium text-ink-2">
                    Password
                  </label>
                  <input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    placeholder="••••••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="h-10 w-full rounded-md border border-input bg-abyss px-3 text-sm text-foreground outline-none focus-visible:border-telemetry focus-visible:ring-2 focus-visible:ring-telemetry/30"
                  />
                </div>

                <div className="flex items-center justify-between text-xs">
                  <label className="inline-flex cursor-pointer items-center gap-2 text-ink-2">
                    <input
                      type="checkbox"
                      checked={remember}
                      onChange={(e) => setRemember(e.target.checked)}
                      className="size-3.5 rounded border-bulkhead accent-telemetry"
                    />
                    Remember me
                  </label>
                  <button
                    type="button"
                    onClick={() => setMode("forgot")}
                    className="text-telemetry hover:underline"
                  >
                    Forgot password?
                  </button>
                </div>

                {error && (
                  <p id={errorId} role="alert" className="flex items-start gap-2 text-sm text-critical">
                    <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden /> {error}
                  </p>
                )}

                <Button
                  type="submit"
                  size="lg"
                  className="aero-glow w-full bg-telemetry font-semibold text-[#04131c] hover:bg-telemetry/90"
                  disabled={busy}
                >
                  <LogIn aria-hidden /> {busy ? "Signing in..." : "Sign In"}
                </Button>
              </form>

              <div className="my-5 flex items-center gap-3 text-xs text-ink-3">
                <span className="h-px flex-1 bg-bulkhead" />
                <span>Or continue with</span>
                <span className="h-px flex-1 bg-bulkhead" />
              </div>

              <Button
                type="button"
                variant="outline"
                size="lg"
                className="w-full border-bulkhead bg-abyss/80 text-foreground hover:border-telemetry"
                onClick={() => {
                  setUsername("operator");
                  toast.info(
                    "Username set to 'operator'. Enter the password from backend/.dev-users.json (generated via python scripts/create_users.py dev).",
                  );
                }}
              >
                <KeyRound className="size-4 text-telemetry" aria-hidden />
                Google / Mission SSO (Fill Operator ID)
              </Button>

              <p className="mt-5 text-center text-xs text-ink-2">
                Need a new mission role account?{" "}
                <button
                  type="button"
                  onClick={() => setMode("register")}
                  className="font-medium text-telemetry hover:underline"
                >
                  Create an account
                </button>
              </p>
            </>
          ) : mode === "forgot" ? (
            <div className="space-y-4 text-sm text-ink-2">
              <p>
                ASTRA-MED stores passwords using salted <code className="text-foreground">scrypt</code> hashes in the
                mission database. To reset local demo accounts, run:
              </p>
              <pre className="rounded-md border border-bulkhead bg-abyss p-3 font-mono text-xs text-telemetry">
                cd backend{"\n"}python scripts/create_users.py dev
              </pre>
              <p className="text-xs text-ink-3">
                Generated credentials are saved locally in <code>backend/.dev-users.json</code>.
              </p>
              <Button variant="outline" className="w-full" onClick={() => setMode("signin")}>
                Back to Sign In
              </Button>
            </div>
          ) : (
            <div className="space-y-4 text-sm text-ink-2">
              <p>
                For mission security, new user accounts are provisioned by an Administrator in{" "}
                <Link href="/admin" className="text-telemetry hover:underline">
                  User &amp; Role Management (/admin)
                </Link>{" "}
                or via the backend CLI:
              </p>
              <pre className="rounded-md border border-bulkhead bg-abyss p-3 font-mono text-xs text-telemetry">
                python scripts/create_users.py dev
              </pre>
              <Button variant="outline" className="w-full" onClick={() => setMode("signin")}>
                Back to Sign In
              </Button>
            </div>
          )}
        </div>
      </div>

      <p className="mx-auto max-w-xl text-center text-xs text-ink-3">
        Research prototype with simulated crew data. Not a medical device.
      </p>
      <ScreenDirectoryDialog open={dirOpen} onOpenChange={setDirOpen} />
    </div>
  );
}
