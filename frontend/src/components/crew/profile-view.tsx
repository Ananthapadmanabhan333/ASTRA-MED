"use client";

import { FlaskConical } from "lucide-react";
import Link from "next/link";

import { AlertList } from "@/components/alerts/alert-list";
import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { StatusIcon, StatusPill } from "@/components/status/status";
import { Button } from "@/components/ui/button";
import { EcgTrace } from "@/components/vitals/ecg-trace";
import { HistoryPanel } from "@/components/vitals/history-panel";
import { ApiError } from "@/lib/api/client";
import { useAstronauts, useInsights, useSleep, useSnapshot } from "@/lib/api/hooks";
import type { AstronautSummary, HealthSnapshot } from "@/lib/api/types";
import { fmt, hoursMinutes, utcDay } from "@/lib/format";
import { liveStatus } from "@/lib/live/reducer";
import { useLive } from "@/lib/live/store";
import { SCENARIO_LABEL } from "@/lib/metrics";

import { AstronautSwitcher } from "./astronaut-switcher";
import { LiveVitals } from "./live-vitals";

function hhmm(hours: number) {
  const m = Math.round(hours * 60) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

function Facts({ a }: { a: AstronautSummary }) {
  const facts: [string, string][] = [
    ["Age", `${a.age}`],
    ["Sex", a.sex],
    ["Height", `${a.height_cm} cm`],
    ["Mass", `${a.mass_kg} kg`],
    ["Blood type", a.blood_type],
    ["Prior career dose", `${fmt(a.prior_career_dose_msv, 0)} mSv`],
    ["Sleep schedule", `${hhmm(a.sleep_start_hour)} UTC, ${a.sleep_target_hours} h`],
    ["Exercise plan", `${a.exercise_target_minutes} min/day`],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4 xl:grid-cols-8">
      {facts.map(([k, v]) => (
        <div key={k}>
          <dt className="text-xs text-ink-3">{k}</dt>
          <dd className="text-sm text-foreground">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function SleepNights({ id, target }: { id: string; target: number }) {
  const sleep = useSleep(id, 7);
  if (sleep.isPending) return <LoadingState rows={3} />;
  if (sleep.error) return <ErrorState error={sleep.error} onRetry={() => sleep.refetch()} />;
  if (!sleep.data.length) return <EmptyState title="No completed nights recorded yet" />;
  const max = Math.max(9, ...sleep.data.map((n) => n.duration_hours));
  return (
    <ul className="space-y-1.5" aria-label="Sleep duration, last 7 nights">
      {[...sleep.data].reverse().map((n) => {
        const short = n.duration_hours < target - 0.75;
        return (
          <li key={n.night} className="grid grid-cols-[3.5rem_1fr_4.5rem] items-center gap-2 text-xs">
            <span className="text-ink-2">{utcDay(n.night)}</span>
            <div className="relative h-2 rounded-full bg-bulkhead/60">
              <div
                className={`h-full rounded-full ${short ? "bg-caution" : "bg-telemetry"}`}
                style={{ width: `${(n.duration_hours / max) * 100}%` }}
              />
              <span
                className="absolute -top-0.5 h-3 w-px bg-ink-2"
                style={{ left: `${(target / max) * 100}%` }}
                aria-hidden
              />
            </div>
            <span className="text-right tabular-nums">{hoursMinutes(n.duration_hours)}</span>
          </li>
        );
      })}
      <li className="pt-1 text-xs text-ink-3">Tick marks the {target} h target. Amber bars fall 45 min or more short.</li>
    </ul>
  );
}

function Sidebar({ a, snap }: { a: AstronautSummary; snap: HealthSnapshot | undefined }) {
  const insights = useInsights(a.id);
  return (
    <div className="space-y-5">
      <Panel title="Sleep, last 7 nights">
        <SleepNights id={a.id} target={a.sleep_target_hours} />
      </Panel>
      <Panel title="Radiation and countermeasures">
        {snap ? (
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-xs text-ink-3">This mission</dt>
              <dd className="readout text-2xl">{fmt(snap.radiation.mission_dose_msv, 0)} <span className="text-xs text-ink-3">mSv</span></dd>
            </div>
            <div>
              <dt className="text-xs text-ink-3">Career, of 600 mSv reference</dt>
              <dd className="readout text-2xl">{fmt(snap.radiation.career_limit_pct, 0)}<span className="text-xs text-ink-3">%</span></dd>
            </div>
            <div>
              <dt className="text-xs text-ink-3">Exercise today</dt>
              <dd className="readout text-2xl">
                {fmt(snap.activity.exercise_minutes_today, 0)}
                <span className="text-xs text-ink-3"> of {snap.activity.exercise_target_minutes} min</span>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-ink-3">Sleep debt, 7 nights</dt>
              <dd className="readout text-2xl">{fmt(snap.sleep.sleep_debt_7d_hours, 1)} <span className="text-xs text-ink-3">h</span></dd>
            </div>
          </dl>
        ) : (
          <LoadingState rows={2} />
        )}
      </Panel>
      <Panel title="Insights">
        {insights.isPending ? (
          <LoadingState rows={2} />
        ) : insights.error ? (
          <ErrorState error={insights.error} onRetry={() => insights.refetch()} />
        ) : insights.data.length === 0 ? (
          <p className="text-sm text-ink-2">No review rules are triggered for this crew member.</p>
        ) : (
          <ul className="space-y-3">
            {insights.data.map((i) => (
              <li key={i.id} className="flex gap-2">
                {i.severity === "info" ? (
                  <FlaskConical className="mt-0.5 size-4 text-ink-3" aria-label="Info" />
                ) : (
                  <StatusIcon status={i.severity} className="mt-0.5" />
                )}
                <div>
                  <p className="text-sm font-medium">{i.title}</p>
                  <p className="text-xs text-ink-2">{i.summary}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

export function ProfileView({ id }: { id: string }) {
  const crew = useAstronauts();
  const snap = useSnapshot(id);
  const alerts = useLive((s) => s.openAlerts);
  const connection = useLive((s) => s.connection);
  const scenario = useLive((s) => Object.values(s.scenarios).find((sc) => sc.astronaut_id === id));

  if (crew.isPending) return <LoadingState label="Loading crew member" rows={6} />;
  if (crew.error && !crew.data) return <ErrorState error={crew.error} onRetry={() => crew.refetch()} />;
  const a = crew.data?.find((c) => c.id === id);
  if (!a || (snap.error instanceof ApiError && snap.error.status === 404)) {
    return (
      <EmptyState title={`No crew member with ID ${id}`} action={<Button asChild size="sm"><Link href="/crew">Back to crew</Link></Button>}>
        Choose someone from the crew list.
      </EmptyState>
    );
  }

  const openForMe = Object.values(alerts).filter((x) => x.astronaut_id === id);
  const status = connection === "live" ? liveStatus(openForMe) : a.status;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-heading text-3xl font-semibold tracking-tight">{a.name}</h1>
            <StatusPill status={status} />
          </div>
          <p className="mt-0.5 text-ink-2">
            {a.role}, {a.specialty.toLowerCase()}. Crew ID {a.id}.
          </p>
          {scenario && (
            <p className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-dashed border-caution/50 px-2 py-1 text-sm text-caution">
              <FlaskConical className="size-4" aria-hidden />
              Test scenario running: {SCENARIO_LABEL[scenario.scenario] ?? scenario.label}
            </p>
          )}
        </div>
        {crew.data && <AstronautSwitcher crew={crew.data} value={id} />}
      </div>

      <Facts a={a} />

      <LiveVitals astronautId={id} fallback={snap.data?.latest ?? a.latest ?? null} />

      <Panel raised title="Synthetic ECG" description="Single-lead waveform generated from the simulated heart rate. For display testing only; not diagnostic.">
        <div className="h-40 overflow-hidden rounded-md bg-abyss/70 ring-1 ring-bulkhead/60">
          <EcgTrace astronautId={id} sweepSeconds={8} grid label={`Live synthetic ECG, ${a.name}`} />
        </div>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          <HistoryPanel astronautId={id} name={a.name} />
          <Panel title="Open alerts">
            {openForMe.length || snap.data?.open_alerts.length ? (
              <AlertList alerts={openForMe.length ? openForMe : snap.data!.open_alerts} />
            ) : (
              <p className="text-sm text-ink-2">No open alerts for {a.name}.</p>
            )}
          </Panel>
        </div>
        <Sidebar a={a} snap={snap.data} />
      </div>
    </div>
  );
}
