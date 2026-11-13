"use client";

import { Menu, Radiation, Satellite } from "lucide-react";
import Link from "next/link";

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

import { ConnectionIndicator } from "./connection-indicator";
import { NotificationCenter } from "./notification-center";
import { useShell } from "./shell-store";
import { SimulatedMarker } from "./simulated-marker";

function MissionClock({ elapsed, fetchedAt }: { elapsed: number; fetchedAt: number }) {
  const now = useNow(1000);
  const live = elapsed + (now ? Math.max(0, now - fetchedAt) / 1000 : 0);
  const { day, clock } = missionElapsed(live);
  return (
    <div className="flex items-baseline gap-2" aria-label={`Mission day ${day}, ${clock} elapsed`}>
      <span className="text-xs text-ink-3">MET</span>
      <span className="readout text-lg font-semibold text-foreground sm:text-xl">
        Day {day}
        <span className="ml-1.5 text-telemetry">{clock}</span>
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
  const elevated = data && data.habitat_dose_rate_msv_day > 3;

  return (
    <header className="sticky top-0 z-30 border-b border-bulkhead bg-[#081426]/95 backdrop-blur supports-[backdrop-filter]:bg-[#081426]/85">
      <div className="flex min-h-14 flex-wrap items-center gap-x-5 gap-y-2 px-3 py-2 sm:px-5">
        <Button
          variant="ghost"
          size="icon-sm"
          className="lg:hidden"
          aria-label="Open navigation"
          onClick={() => setMobileOpen(true)}
        >
          <Menu aria-hidden />
        </Button>

        <div className="flex min-w-0 items-baseline gap-2">
          {isLoading ? (
            <Skeleton className="h-6 w-40 bg-bulkhead/60" />
          ) : data ? (
            <>
              <span className="font-heading text-lg font-semibold tracking-tight">{data.mission_name}</span>
              <span className="hidden truncate text-sm text-ink-2 sm:inline">{data.phase}</span>
            </>
          ) : (
            <span className="text-sm text-ink-2">
              {!allowed ? "ASTRA-MED" : error ? "Mission status unavailable" : "ASTRA-MED"}
            </span>
          )}
        </div>

        {data && (
          <>
            <MissionClock elapsed={data.mission_elapsed_seconds} fetchedAt={dataUpdatedAt} />
            <div className="hidden items-center gap-1.5 text-sm text-ink-2 xl:flex" title="One-way light delay to Earth">
              <Satellite className="size-4 text-ink-3" aria-hidden />
              <span>
                Earth delay <span className="text-foreground tabular-nums">{duration(data.one_way_light_delay_s)}</span>
              </span>
            </div>
            <div
              className={`hidden items-center gap-1.5 text-sm 2xl:flex ${elevated ? "text-caution" : "text-ink-2"}`}
              title="Simulated habitat dose rate"
            >
              <Radiation className="size-4" aria-hidden />
              <span className="tabular-nums">
                {fmt(data.habitat_dose_rate_msv_day, 2)} <span className="text-ink-3">mSv/day</span>
              </span>
            </div>
            <div className="hidden items-center gap-3 lg:flex" aria-label="Crew status">
              {(["critical", "caution", "advisory", "nominal"] as const).map((s) =>
                data.crew_status[s] ? (
                  <span key={s} className="inline-flex items-center gap-1 text-sm tabular-nums">
                    <StatusIcon status={s} />
                    {data.crew_status[s]}
                    <span className="sr-only"> {s}</span>
                  </span>
                ) : null,
              )}
            </div>
          </>
        )}

        <div className="ml-auto flex items-center gap-3">
          <SandboxIndicator />
          <SimulatedMarker />
          <ConnectionIndicator />
          <NotificationCenter />
          <div className="border-l border-bulkhead pl-2">
            <UserMenu compact />
          </div>
        </div>
      </div>
    </header>
  );
}
