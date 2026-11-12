import { Orbit } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { RouteAccess } from "@/components/auth/route-access";
import { UserMenu } from "@/components/auth/user-menu";

import { MissionStrip } from "./mission-strip";
import { Nav } from "./nav";

function Wordmark() {
  return (
    <Link href="/" className="flex items-center gap-2 rounded-md px-1 py-1" aria-label="ASTRA-MED home">
      <Orbit className="size-6 text-telemetry" aria-hidden />
      <span className="font-heading text-xl font-bold tracking-tight">
        ASTRA<span className="font-medium text-ink-2">-MED</span>
      </span>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-bulkhead bg-sidebar lg:flex">
        <div className="px-4 pt-4 pb-5">
          <Wordmark />
          <p className="mt-1 px-1 text-xs text-ink-3">Crew health decision support</p>
        </div>
        <div className="flex-1 overflow-y-auto px-3">
          <Nav layout="rail" />
        </div>
        <div className="border-t border-bulkhead">
          <UserMenu />
        </div>
        <p className="border-t border-bulkhead px-4 py-3 text-xs leading-relaxed text-ink-3">
          Research prototype for NASA Space Apps 2026. Not a medical device. Not clinically validated.
        </p>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30">
          <div className="flex items-center gap-3 border-b border-bulkhead bg-sidebar px-4 py-2 lg:hidden">
            <Wordmark />
            <div className="ml-auto">
              <UserMenu compact />
            </div>
          </div>
          {/* relative: makes this scroller clip absolutely-positioned children (sr-only badge labels) */}
          <div className="relative overflow-x-auto border-b border-bulkhead bg-sidebar px-2 py-1.5 lg:hidden">
            <Nav layout="bar" />
          </div>
          <MissionStrip />
        </header>
        <main id="main" className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-5 sm:px-6 sm:py-6">
          <RouteAccess>{children}</RouteAccess>
        </main>
      </div>
    </div>
  );
}
