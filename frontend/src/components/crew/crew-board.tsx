"use client";

import { FlaskConical } from "lucide-react";
import Link from "next/link";

import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { STATUS_RAIL, StatusPill } from "@/components/status/status";
import { EcgTrace } from "@/components/vitals/ecg-trace";
import { Readout } from "@/components/vitals/readout";
import { useAstronauts, useThresholds } from "@/lib/api/hooks";
import type { AstronautSummary, ThresholdInfo } from "@/lib/api/types";
import { liveStatus } from "@/lib/live/reducer";
import { useLive } from "@/lib/live/store";
import { ACTIVITY_LABEL, SCENARIO_LABEL } from "@/lib/metrics";
import { classify } from "@/lib/thresholds";
import { cn } from "@/lib/utils";

function useLiveStatus(astronaut: AstronautSummary) {
  const connection = useLive((s) => s.connection);
  const alerts = useLive((s) => s.openAlerts);
  if (connection !== "live") return astronaut.status;
  return liveStatus(Object.values(alerts).filter((a) => a.astronaut_id === astronaut.id));
}

function CrewRow({ astronaut, rules }: { astronaut: AstronautSummary; rules?: ThresholdInfo[] }) {
  const live = useLive((s) => s.latest[astronaut.id]);
  const scenario = useLive((s) =>
    Object.values(s.scenarios).find((sc) => sc.astronaut_id === astronaut.id),
  );
  const status = useLiveStatus(astronaut);
  const r = live ?? astronaut.latest ?? undefined;
  const act = r?.activity_state;
  const b = (metric: string, v: number | undefined) => (v === undefined ? null : classify(metric, v, act, rules));

  return (
    <li className="relative grid grid-cols-1 gap-x-5 gap-y-3 border-b border-bulkhead/60 py-4 pl-4 pr-1 last:border-b-0 md:grid-cols-[13rem_1fr] xl:grid-cols-[13rem_minmax(14rem,1fr)_auto]">
      <span aria-hidden className={cn("absolute inset-y-3 left-0 w-1 rounded-full", STATUS_RAIL[status])} />

      <div className="min-w-0">
        <Link
          href={`/crew/${astronaut.id}`}
          className="font-heading text-lg font-semibold leading-tight hover:text-telemetry focus-visible:text-telemetry"
        >
          {astronaut.name}
        </Link>
        <p className="text-sm text-ink-2">{astronaut.role}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <StatusPill status={status} />
          {act && <span className="text-xs text-ink-2">{ACTIVITY_LABEL[act]}</span>}
        </div>
        {scenario && (
          <p className="mt-2 inline-flex items-center gap-1 text-xs text-caution">
            <FlaskConical className="size-3" aria-hidden />
            Test: {SCENARIO_LABEL[scenario.scenario] ?? scenario.label}
          </p>
        )}
      </div>

      <div className="relative h-24 min-w-0 self-center overflow-hidden rounded-md bg-abyss/60 ring-1 ring-bulkhead/60">
        <EcgTrace astronautId={astronaut.id} label={`Live synthetic ECG, ${astronaut.name}`} />
        <span className="pointer-events-none absolute top-1.5 left-2 text-[11px] text-ink-3">
          ECG {r?.rhythm === "irregular" ? <span className="text-caution">irregular</span> : "lead II, synthetic"}
        </span>
      </div>

      <div className="grid grid-cols-3 items-start gap-x-5 gap-y-3 sm:grid-cols-5 md:col-span-2 xl:col-span-1 xl:w-[31rem]">
        <Readout
          label="Heart rate"
          value={r?.heart_rate}
          unit="bpm"
          size="lg"
          accent
          breach={b("heart_rate", r?.heart_rate)}
        />
        <Readout label="SpO₂" value={r?.spo2} decimals={1} unit="%" size="lg" breach={b("spo2", r?.spo2)} />
        <Readout
          label="BP"
          value={r?.systolic}
          secondary={r ? `${r.systolic}/${r.diastolic}` : undefined}
          unit="mmHg"
          size="md"
          breach={b("systolic", r?.systolic)}
        />
        <Readout
          label="Temp"
          value={r?.temperature_c}
          decimals={1}
          unit="°C"
          size="md"
          breach={b("temperature_c", r?.temperature_c)}
        />
        <Readout
          label="Resp. rate"
          value={r?.respiratory_rate}
          unit="/min"
          size="md"
          breach={b("respiratory_rate", r?.respiratory_rate)}
        />
      </div>
    </li>
  );
}

export function CrewBoard() {
  const crew = useAstronauts();
  const rules = useThresholds();

  if (crew.isPending) return <LoadingState label="Loading crew" rows={4} className="py-2" />;
  if (crew.error && !crew.data) return <ErrorState error={crew.error} onRetry={() => crew.refetch()} />;
  if (!crew.data?.length)
    return <EmptyState title="No crew registered">Start the backend to seed the simulated crew.</EmptyState>;

  return (
    <ul aria-label="Crew status board">
      {crew.data.map((a) => (
        <CrewRow key={a.id} astronaut={a} rules={rules.data} />
      ))}
    </ul>
  );
}
