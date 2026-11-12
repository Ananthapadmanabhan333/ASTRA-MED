"use client";

import { ShieldOff } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { routePermissions } from "@/components/shell/nav";
import { useAuth } from "@/lib/auth/store";

/**
 * Shows a clear notice instead of a page the signed-in role cannot use. The API enforces the same
 * rules on every request; this only avoids empty or failing views.
 */
export function RouteAccess({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const session = useAuth((s) => s.session);
  const needed = routePermissions(pathname);
  if (!session || needed.some((p) => session.permissions.includes(p))) return <>{children}</>;
  const healthOnly = needed.includes("health:read");
  return (
    <div role="alert" className="mx-auto mt-10 max-w-lg rounded-lg border border-bulkhead bg-hull p-6 text-center">
      <ShieldOff className="mx-auto size-8 text-ink-3" aria-hidden />
      <h1 className="mt-3 font-heading text-xl font-semibold">Not available for your role</h1>
      <p className="mt-1 text-sm text-ink-2">
        {healthOnly
          ? `The ${session.user.role_label} role does not include access to crew health records.`
          : `The ${session.user.role_label} role does not include the permission this page needs (${needed.join(" or ")}).`}
      </p>
      <Link href={session.permissions.includes("space:read") ? "/space/weather" : "/"} className="mt-4 inline-block text-sm text-telemetry hover:underline">
        Go to a page you can use
      </Link>
    </div>
  );
}
