"use client";

import { Radiation, Satellite } from "lucide-react";

import { StatusIcon } from "@/components/status/status";
import { Skeleton } from "@/components/ui/skeleton";
import { useMissionStatus } from "@/lib/api/hooks";
import { useCan } from "@/lib/auth/store";
import { duration, fmt, missionElapsed } from "@/lib/format";
import { useNow } from "@/lib/use-now";

import { ConnectionIndicator } from "./connection-indicator";
import { SimulatedMarker } from "./simulated-marker";

function MissionClock({ elapsed, fetchedAt }: { elapsed: number; fetchedAt: number }) {
  const now = useNow(1000);
  const live = elapsed + (now ? Math.max(0, now - fetchedAt) / 1000 : 0);
  const { day, clock } = missionElapsed(live);
  return (
    <div className="flex items-baseline gap-2" aria-label={`Mission day ${day}, ${clock} elapsed`}>
      <span className="text-xs text-ink-3">MET</span>
      <span className="readout text-xl font-semibold text-foreground">
        Day {day}
        <span className="ml-1.5 text-telemetry">{clock}</span>
      </span>
    </div>
  );
}

export function MissionStrip() {
  const { data, dataUpdatedAt, isLoading, error } = useMissionStatus();
  const allowed = useCan("health:read");
  const elevated = data && data.habitat_dose_rate_msv_day > 3;

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-bulkhead bg-[#081426]/90 px-4 py-2.5 backdrop-blur sm:px-6">
      <div className="flex min-w-0 items-baseline gap-2">
        {isLoading ? (
          <Skeleton className="h-6 w-40 bg-bulkhead/60" />
        ) : data ? (
          <>
            <span className="font-heading text-lg font-semibold tracking-tight">{data.mission_name}</span>
            <span className="truncate text-sm text-ink-2">{data.phase}</span>
          </>
        ) : (
          <span className="text-sm text-ink-2">
            {!allowed ? "Crew status is not shown for your role" : error ? "Mission status unavailable" : "—"}
          </span>
        )}
      </div>

      {data && (
        <>
          <MissionClock elapsed={data.mission_elapsed_seconds} fetchedAt={dataUpdatedAt} />
          <div className="hidden items-center gap-1.5 text-sm text-ink-2 md:flex" title="One-way light delay to Earth">
            <Satellite className="size-4 text-ink-3" aria-hidden />
            <span>
              Earth delay <span className="text-foreground tabular-nums">{duration(data.one_way_light_delay_s)}</span>
            </span>
          </div>
          <div
            className={`hidden items-center gap-1.5 text-sm xl:flex ${elevated ? "text-caution" : "text-ink-2"}`}
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

      <div className="ml-auto flex items-center gap-4">
        <SimulatedMarker />
        <ConnectionIndicator />
      </div>
    </div>
  );
}
