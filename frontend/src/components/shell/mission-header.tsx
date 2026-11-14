"use client";

import { Compass, Menu, Radiation, Rocket, Satellite, Settings } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { UserMenu } from "@/components/auth/user-menu";
import { SandboxTag } from "@/components/mc/chips";
import { StatusIcon } from "@/components/status/status";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMissionStatus } from "@/lib/api/hooks";
import { useCan } from "@/lib/auth/store";
import { duration, fmt, missionElapsed } from "@/lib/format";
import { useLive } from "@/lib/live/store";
import { useNow } from "@/lib/use-now";

import { ScreenDirectoryDialog } from "./breadcrumbs";
import { ConnectionIndicator } from "./connection-indicator";
import { NotificationCenter } from "./notification-center";
import { useShell } from "./shell-store";
import { SimulatedMarker } from "./simulated-marker";

function MissionClock({ elapsed, fetchedAt }: { elapsed: number; fetchedAt: number }) {
  const now = useNow(1000);
  const live = elapsed + (now ? Math.max(0, now - fetchedAt) / 1000 : 0);
  const { day, clock } = missionElapsed(live);
  const utcStr = now ? new Date(now).toISOString().slice(0, 19).replace("T", " ") : "2026-11-14 14:21:05";
  return (
    <div className="flex flex-wrap items-center gap-2.5" aria-label={`Mission day ${day}, ${clock} elapsed`}>
      <span className="inline-flex items-center gap-1.5 rounded-full border border-nominal/40 bg-nominal/10 px-2.5 py-0.5 text-xs font-medium text-nominal">
        <span className="size-2 rounded-full bg-nominal" aria-hidden />
        Mission Active
      </span>
      <span className="rounded-full border border-bulkhead bg-abyss/80 px-2.5 py-0.5 text-xs font-medium text-ink-2 tabular-nums">
        ISS Simulation • Day {day} <span className="ml-1 text-telemetry">{clock}</span>
      </span>
      <span className="hidden font-mono text-xs text-ink-3 tabular-nums md:inline">
        UTC {utcStr}
      </span>
    </div>
  );
}

function SandboxIndicator() {
  const sim = useLive((s) => s.sim);
  if (!sim?.active) return null;
  return (
    <Link href="/simulation" className="hidden rounded-md focus-visible:outline-2 md:block" title="Open mission simulation">
      <SandboxTag className="py-0.5">
        Sandbox {sim.status === "paused" ? "paused" : "running"} {sim.t_plus} at {fmt(sim.speed ?? 0, 0)}x
      </SandboxTag>
    </Link>
  );
}

/** Mission identity, clock and the platform's live status, on every page. */
export function MissionHeader() {
  const { data, dataUpdatedAt, isLoading, error } = useMissionStatus();
  const allowed = useCan("health:read");
  const setMobileOpen = useShell((s) => s.setMobileOpen);
  const [dirOpen, setDirOpen] = useState(false);
  const elevated = data && data.habitat_dose_rate_msv_day > 3;

  return (
    <header className="sticky top-0 z-30 border-b border-bulkhead bg-[#081426]/95 backdrop-blur supports-[backdrop-filter]:bg-[#081426]/85">
      <div className="flex min-h-14 flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2 sm:px-5">
        <Button
          variant="ghost"
          size="icon-sm"
          className="lg:hidden"
          aria-label="Open navigation"
          onClick={() => setMobileOpen(true)}
        >
          <Menu aria-hidden />
        </Button>

        <div className="flex min-w-0 items-center gap-2.5">
          <span className="hidden items-center gap-1.5 rounded-full border border-telemetry/30 bg-telemetry/10 px-2.5 py-0.5 text-xs font-medium text-telemetry sm:inline-flex">
            <Rocket className="size-3.5" aria-hidden />
            NASA Space Apps Challenge
          </span>
          {isLoading ? (
            <Skeleton className="h-6 w-36 bg-bulkhead/60" />
          ) : data ? (
            <span className="hidden truncate text-xs text-ink-2 xl:inline">
              {data.mission_name} · {data.phase}
            </span>
          ) : (
            <span className="text-sm text-ink-2">
              {!allowed ? "ASTRA-MED" : error ? "Mission status unavailable" : "ASTRA-MED"}
            </span>
          )}
        </div>

        {data ? (
          <>
            <MissionClock elapsed={data.mission_elapsed_seconds} fetchedAt={dataUpdatedAt} />
            <div className="hidden items-center gap-1.5 text-xs text-ink-2 2xl:flex" title="One-way light delay to Earth">
              <Satellite className="size-3.5 text-ink-3" aria-hidden />
              <span>
                Delay <span className="text-foreground tabular-nums">{duration(data.one_way_light_delay_s)}</span>
              </span>
            </div>
            <div
              className={`hidden items-center gap-1.5 text-xs 2xl:flex ${elevated ? "text-caution" : "text-ink-2"}`}
              title="Simulated habitat dose rate"
            >
              <Radiation className="size-3.5" aria-hidden />
              <span className="tabular-nums">
                {fmt(data.habitat_dose_rate_msv_day, 2)} <span className="text-ink-3">mSv/day</span>
              </span>
            </div>
            <div className="hidden items-center gap-2.5 xl:flex" aria-label="Crew status">
              {(["critical", "caution", "advisory", "nominal"] as const).map((s) =>
                data.crew_status[s] ? (
                  <span key={s} className="inline-flex items-center gap-1 text-xs tabular-nums">
                    <StatusIcon status={s} />
                    {data.crew_status[s]}
                    <span className="sr-only"> {s}</span>
                  </span>
                ) : null,
              )}
            </div>
          </>
        ) : (
          <MissionClock elapsed={42 * 86400 + 51665} fetchedAt={0} />
        )}

        <div className="ml-auto flex items-center gap-2">
          <SandboxIndicator />
          <SimulatedMarker />
          <ConnectionIndicator />
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setDirOpen(true)}
            aria-label="Open 26-screen directory"
            title="All 26 Screens Directory"
            className="text-telemetry hover:bg-telemetry/10"
          >
            <Compass className="size-4" aria-hidden />
          </Button>
          <NotificationCenter />
          <Button asChild variant="ghost" size="icon-sm" aria-label="Settings" title="Settings">
            <Link href="/settings">
              <Settings className="size-4 text-ink-2" aria-hidden />
            </Link>
          </Button>
          <div className="border-l border-bulkhead pl-2">
            <UserMenu compact />
          </div>
        </div>
      </div>
      <ScreenDirectoryDialog open={dirOpen} onOpenChange={setDirOpen} />
    </header>
  );
}
