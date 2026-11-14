"use client";

import {
  BellRing,
  BrainCircuit,
  FlaskConical,
  GanttChart,
  HeartPulse,
  ServerCog,
  Sun,
  Users,
  Wind,
  Radiation as RadiationIcon,
} from "lucide-react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ErrorState, LoadingState } from "@/components/data/states";
import { DataCard, Meter, Stat, Unavailable } from "@/components/mc/card";
import { ExperimentalTag, LivePulse, OriginChip, PriorityBadge, SandboxTag, SeverityDot } from "@/components/mc/chips";
import { ErrorBoundary } from "@/components/mc/error-boundary";
import { STATUS_RAIL, StatusPill } from "@/components/status/status";
import { EcgTrace } from "@/components/vitals/ecg-trace";
import { Sparkline } from "@/components/vitals/sparkline";
import { useMissionControl } from "@/lib/api/mission-hooks";
import type { ComponentStatus, DashboardSection, MissionControlOverview, SimState } from "@/lib/api/types";
import { crewColor } from "@/lib/crew";
import { duration, fmt, relativeTime, utcDay, utcTime } from "@/lib/format";
import { preferLive } from "@/lib/live/freshness";
import { liveStatus } from "@/lib/live/reducer";
import { useLive } from "@/lib/live/store";
import { ACTIVITY_LABEL, SCENARIO_LABEL } from "@/lib/metrics";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

import type {
  AiSectionData,
  AlertsSectionData,
  CrewSectionData,
  EnvironmentSectionData,
  HealthSectionData,
  IncidentsSectionData,
  RadiationSectionData,
  SpaceSectionData,
} from "./dashboard-types";

function data<T>(s: DashboardSection | undefined): T | null {
  return s?.available ? (s.data as unknown as T) : null;
}

const RISK_TONE: Record<string, "nominal" | "advisory" | "caution" | "critical"> = {
  normal: "nominal",
  low_concern: "advisory",
  moderate_concern: "caution",
  high_concern: "critical",
};

// ------------------------------------------------------------------------ KPI band ----
function KpiBand({ o }: { o: MissionControlOverview }) {
  const crew = data<CrewSectionData>(o.crew);
  const alerts = data<AlertsSectionData>(o.alerts);
  const ai = data<AiSectionData>(o.ai);
  const space = data<SpaceSectionData>(o.space_weather);
  const sim = o.simulation as unknown as SimState;
  const urgent = alerts ? Number(alerts.summary.by_priority["1"] ?? 0) + Number(alerts.summary.by_priority["2"] ?? 0) : 0;
  const swxTotal = space ? Object.values(space.counts).reduce((a, b) => a + b, 0) : null;
  return (
    <section aria-label="Mission summary" className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-bulkhead/80 bg-bulkhead/60 sm:grid-cols-3 xl:grid-cols-6">
      <div className="bg-hull px-4 py-3">
        <Stat
          label="Mission"
          value={o.mission ? `Day ${o.mission.mission_day}` : "—"}
          sub={o.mission ? `${o.mission.earth_distance_au} AU, light delay ${duration(o.mission.one_way_light_delay_s)}` : undefined}
        />
      </div>
      <div className="bg-hull px-4 py-3">
        <Stat
          label="Active astronauts"
          value={crew ? `${crew.active}/${crew.total}` : "—"}
          tone={crew && crew.active < crew.total ? "caution" : "telemetry"}
          sub={crew ? `live within ${crew.live_window_s} s` : "crew data unavailable"}
        />
      </div>
      <div className="bg-hull px-4 py-3">
        <Stat
          label="Unresolved alerts"
          value={alerts ? alerts.summary.unresolved : "—"}
          tone={urgent > 0 ? "critical" : undefined}
          sub={alerts ? `${urgent} P1/P2, ${alerts.summary.experimental_open} experimental AI` : undefined}
        />
      </div>
      <div className="bg-hull px-4 py-3">
        <Stat
          label="Highest AI risk"
          value={ai?.highest?.risk_score != null ? fmt(ai.highest.risk_score, 0) : "—"}
          unit={ai?.highest?.risk_score != null ? "/100" : undefined}
          tone={ai?.highest?.category ? (RISK_TONE[ai.highest.category] === "nominal" ? undefined : RISK_TONE[ai.highest.category]) : undefined}
          sub={ai?.highest ? `${ai.highest.name}, experimental` : ai?.model_loaded === false ? "no model loaded" : "awaiting sweep"}
        />
      </div>
      <div className="bg-hull px-4 py-3">
        <Stat
          label="Space weather, 7 days"
          value={swxTotal ?? "—"}
          unit={swxTotal != null ? "events" : undefined}
          sub={space ? `NASA DONKI, ${space.freshness.mode}` : o.space_weather.reason ?? undefined}
        />
      </div>
      <div className="bg-hull px-4 py-3">
        <Stat
          label="Mission simulation"
          value={sim?.active ? sim.t_plus ?? "Running" : "Idle"}
          tone={sim?.active ? "sandbox" : undefined}
          sub={sim?.active ? `${sim.status} at ${fmt(sim.speed ?? 0, 0)}x, ${sim.open_alerts} sandbox alerts` : "no sandbox run"}
        />
      </div>
    </section>
  );
}

// ------------------------------------------------------------------- crew status ----
function CrewTile({ m, asOf }: { m: CrewSectionData["members"][number]; asOf: string }) {
  const latest = useLive((s) => s.latest[m.astronaut_id]);
  const trail = useLive((s) => s.trails[m.astronaut_id]);
  const connection = useLive((s) => s.connection);
  const alerts = useLive((s) => s.openAlerts);
  const status = connection === "live" ? liveStatus(Object.values(alerts).filter((a) => a.astronaut_id === m.astronaut_id)) : m.status;
  // The overview's values were current at `asOf`; a frozen socket reading must not override them.
  const reading = latest && preferLive(connection, latest.ts, asOf) ? latest : undefined;
  // Fields only the stream carries are shown only while it is live, never frozen after a disconnect.
  const streamed = connection === "live" ? latest : undefined;
  const hr = reading?.heart_rate ?? m.heart_rate;
  const spo2 = reading?.spo2 ?? m.spo2;
  const act = reading?.activity_state ?? m.activity_state;
  const scenario = reading?.scenario ?? m.scenario;
  return (
    <li className="relative min-w-0 rounded-md border border-bulkhead/70 bg-panel-2 p-3 pl-4">
      <span aria-hidden className={cn("absolute inset-y-2 left-0 w-1 rounded-r", STATUS_RAIL[status])} />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Link href={`/crew/${m.astronaut_id}`} className="flex items-center gap-1.5 font-heading text-base font-semibold hover:text-telemetry">
            <span className="size-2 shrink-0 rounded-full" style={{ background: crewColor(m.astronaut_id) }} aria-hidden />
            <span className="truncate">{m.name}</span>
          </Link>
          <p className="truncate text-xs text-ink-3">{m.role}</p>
        </div>
        <StatusPill status={status} compact />
      </div>
      <div className="mt-2 flex items-end gap-4">
        <div>
          <p className="text-[11px] text-ink-3">Heart rate</p>
          <p className="readout text-3xl font-semibold text-telemetry">
            {fmt(hr, 0)}
            <span className="ml-1 font-sans text-xs font-normal text-ink-3">bpm</span>
          </p>
        </div>
        <Sparkline points={trail} metric="heart_rate" className="mb-1 text-telemetry/70" width={90} height={30} />
      </div>
      <div className="relative mt-2 h-12 overflow-hidden rounded bg-abyss/60 ring-1 ring-bulkhead/50">
        <EcgTrace astronautId={m.astronaut_id} label={`Live synthetic ECG, ${m.name}`} />
        <span className="pointer-events-none absolute top-1 left-1.5 text-[10px] text-ink-3">
          ECG {streamed?.rhythm === "irregular" ? <span className="text-caution">irregular</span> : "synthetic"}
        </span>
      </div>
      <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
        <div>
          <dt className="text-ink-3">SpO₂</dt>
          <dd className="font-medium tabular-nums">{fmt(spo2, 1)}%</dd>
        </div>
        <div>
          <dt className="text-ink-3">Resp.</dt>
          <dd className="font-medium tabular-nums">{fmt(streamed?.respiratory_rate, 0)}/min</dd>
        </div>
        <div>
          <dt className="text-ink-3">Temp</dt>
          <dd className="font-medium tabular-nums">{fmt(streamed?.temperature_c, 1)}°C</dd>
        </div>
      </dl>
      <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-ink-2">
        {act ? ACTIVITY_LABEL[act as keyof typeof ACTIVITY_LABEL] ?? act : "No reading"}
        {scenario && (
          <span className="inline-flex items-center gap-1 text-caution">
            <FlaskConical className="size-3" aria-hidden />
            {SCENARIO_LABEL[scenario] ?? scenario.replace(/_/g, " ")}
          </span>
        )}
      </p>
    </li>
  );
}

function CrewStatusCard({ o }: { o: MissionControlOverview }) {
  const crew = data<CrewSectionData>(o.crew);
  const connection = useLive((s) => s.connection);
  return (
    <DataCard
      id="crew-status"
      title="Crew status"
      icon={<Users />}
      meta={
        <span className="inline-flex items-center gap-1.5">
          {connection === "live" && <LivePulse />}
          {connection === "live" ? "Live, 1 Hz" : `${connection}, values as of ${utcTime(o.generated_at)} UTC`}
          <OriginChip origin="simulated" />
        </span>
      }
      href="/crew"
      hrefLabel="Crew monitoring"
      className="xl:col-span-8"
    >
      {crew ? (
        <ul className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
          {crew.members.map((m) => (
            <CrewTile key={m.astronaut_id} m={m} asOf={o.generated_at} />
          ))}
        </ul>
      ) : (
        <Unavailable reason={o.crew.reason} />
      )}
    </DataCard>
  );
}

// ------------------------------------------------------------------ alert queue ----
function AlertQueueCard({ o }: { o: MissionControlOverview }) {
  const alerts = data<AlertsSectionData>(o.alerts);
  const now = useNow(15_000);
  const p = alerts?.summary.by_priority;
  return (
    <DataCard
      id="alert-queue"
      title="Active medical and mission alerts"
      icon={<BellRing />}
      meta={alerts ? `${alerts.summary.unresolved} unresolved` : undefined}
      href="/alerts"
      hrefLabel="Alert centre"
      className="xl:col-span-4"
      tone={p && Number(p["1"]) > 0 ? "critical" : p && Number(p["2"]) > 0 ? "caution" : undefined}
      bodyClassName="py-2"
    >
      {!alerts ? (
        <Unavailable reason={o.alerts.reason} />
      ) : (
        <>
          <div className="mb-2 flex flex-wrap gap-1.5" aria-label="Unresolved by priority">
            {[1, 2, 3, 4].map((n) => (
              <span key={n} className="inline-flex items-center gap-1 text-xs text-ink-2">
                <PriorityBadge priority={n} compact /> <span className="tabular-nums">{p?.[String(n)] ?? 0}</span>
              </span>
            ))}
          </div>
          {alerts.top.length === 0 ? (
            <p className="py-6 text-center text-sm text-ink-2">No unresolved alerts on the crew stream.</p>
          ) : (
            <ul className="scroll-quiet max-h-[340px] overflow-y-auto">
              {alerts.top.map((a) => (
                <li key={a.id} className="flex gap-2.5 border-b border-bulkhead/50 py-2 last:border-0">
                  <PriorityBadge priority={a.priority} compact className="mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <Link href={`/alerts?alert=${a.id}`} className="line-clamp-2 text-sm hover:text-telemetry">
                      {a.title}
                    </Link>
                    <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
                      {a.experimental ? <ExperimentalTag /> : <span>{a.classification_label}</span>}
                      <span>{now ? relativeTime(a.created_at, now) : utcTime(a.created_at)}</span>
                      {a.status === "acknowledged" && <span className="text-ink-2">acknowledged</span>}
                      {a.condition_cleared_at && <span className="text-nominal">condition cleared</span>}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {alerts.simulation_summary && alerts.simulation_summary.unresolved > 0 && (
            <Link href="/simulation" className="mt-2 flex items-center gap-2 text-xs text-sandbox hover:underline">
              <SandboxTag /> {alerts.simulation_summary.unresolved} unresolved sandbox alerts (not live crew data)
            </Link>
          )}
        </>
      )}
    </DataCard>
  );
}

// ---------------------------------------------------------------------- AI risk ----
function AiRiskCard({ o }: { o: MissionControlOverview }) {
  const ai = data<AiSectionData>(o.ai);
  const now = useNow(30_000);
  return (
    <DataCard
      id="ai-risk"
      title="AI risk assessment"
      icon={<BrainCircuit />}
      meta={<ExperimentalTag />}
      href="/intelligence"
      hrefLabel="AI intelligence"
      className="xl:col-span-4"
      footer={ai?.sweep_at && now ? `Sweep ${relativeTime(ai.sweep_at, now)}` : ai?.model_loaded === false ? "No trained model" : "Waiting for the first sweep"}
    >
      {!ai ? (
        <Unavailable reason={o.ai.reason} />
      ) : !ai.model_loaded ? (
        <Unavailable reason="No trained model version is loaded. Train one with python -m app.ai.train; monitoring continues without it." />
      ) : (
        <ul className="space-y-3">
          {ai.crew.map((c) => {
            const tone = c.category ? RISK_TONE[c.category] : undefined;
            return (
              <li key={c.astronaut_id}>
                <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
                  <span className="flex min-w-0 items-center gap-1.5">
                    <span className="size-2 shrink-0 rounded-full" style={{ background: crewColor(c.astronaut_id) }} aria-hidden />
                    <span className="truncate">{c.name}</span>
                  </span>
                  <span className="shrink-0 text-xs text-ink-2">
                    {c.risk_score != null ? (
                      <>
                        <span className="font-semibold text-foreground tabular-nums">{fmt(c.risk_score, 0)}</span>/100 {c.category_label}
                      </>
                    ) : (
                      "pending"
                    )}
                  </span>
                </div>
                <Meter value={c.risk_score ?? 0} tone={tone ?? "telemetry"} label={`${c.name} AI risk score`} />
                {c.top_warning && <p className="mt-1 truncate text-xs text-ink-3">{c.top_warning}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </DataCard>
  );
}

// ------------------------------------------------------------ health monitoring ----
function HealthCard({ o }: { o: MissionControlOverview }) {
  const h = data<HealthSectionData>(o.health_monitoring);
  const state = h?.simulator ?? "stopped";
  return (
    <DataCard
      id="health-monitoring"
      title="Health monitoring"
      icon={<HeartPulse />}
      meta={
        h && (
          <span className={cn("font-medium", state === "running" ? "text-nominal" : "text-caution")}>
            {state === "running" ? "Monitoring" : state === "stalled" ? "Stalled" : "Stopped"}
          </span>
        )
      }
      href="/anomalies"
      hrefLabel="Anomalies & tests"
      className="xl:col-span-4"
    >
      {!h ? (
        <Unavailable reason={o.health_monitoring.reason} />
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3">
            <Stat label="Last tick" value={h.last_tick_age_s != null ? fmt(h.last_tick_age_s, 1) : "—"} unit="s ago" />
            <Stat label="Open rule alerts" value={h.open_rule_alerts} tone={h.open_rule_alerts ? "caution" : undefined} />
            <Stat label="Live clients" value={h.websocket_clients} />
          </div>
          <p className="mt-3 text-xs text-ink-2">
            {h.threshold_rules} activity-aware threshold rules, rhythm check and personal-baseline detector at{" "}
            {fmt(1 / h.tick_seconds, 0)} Hz{h.tick_failures ? `; ${h.tick_failures} failed ticks` : ""}.
          </p>
          <div className="mt-3">
            <p className="text-xs text-ink-3">Running test scenarios</p>
            {h.active_scenarios.length === 0 ? (
              <p className="mt-1 text-sm text-ink-2">None</p>
            ) : (
              <ul className="mt-1 space-y-1">
                {h.active_scenarios.map((s) => (
                  <li key={s.id} className="flex items-center gap-1.5 text-sm text-caution">
                    <FlaskConical className="size-3.5" aria-hidden />
                    {s.label} <span className="text-ink-3">({s.astronaut_id ?? "crew"}, {s.triggered_by})</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </DataCard>
  );
}

// ------------------------------------------------------------------- environment ----
function EnvironmentCard({ o }: { o: MissionControlOverview }) {
  const env = data<EnvironmentSectionData>(o.environment);
  return (
    <DataCard
      id="environment"
      title="Environmental monitoring"
      icon={<Wind />}
      meta={<OriginChip origin="simulated" />}
      href="/space/iss"
      hrefLabel="ISS environment (NASA)"
      className="xl:col-span-4"
      tone={env?.open_alerts.length ? "caution" : undefined}
    >
      {!env ? (
        <Unavailable reason={o.environment.reason} />
      ) : (
        <>
          <ul className="space-y-2.5">
            {Object.entries(env.habitat).map(([k, p]) => {
              const sigma = Math.abs(p.deviation_sigma);
              const tone = sigma >= 8 ? "caution" : sigma >= 4 ? "advisory" : "nominal";
              return (
                <li key={k}>
                  <div className="mb-1 flex items-baseline justify-between text-sm">
                    <span className="text-ink-2">{p.label}</span>
                    <span className="tabular-nums">
                      <span className="font-semibold">{p.value}</span> {p.unit}
                      <span className="ml-1.5 text-xs text-ink-3">{p.deviation_sigma > 0 ? "+" : ""}{fmt(p.deviation_sigma, 1)} σ</span>
                    </span>
                  </div>
                  <Meter value={Math.min(10, sigma)} max={10} tone={tone} label={`${p.label} deviation from nominal`} />
                </li>
              );
            })}
          </ul>
          <div className="mt-3 flex items-center justify-between border-t border-bulkhead/50 pt-2 text-sm">
            <span className="text-ink-2">Habitat dose rate</span>
            <span className={cn("tabular-nums", env.dose_rate_msv_day > 3 && "text-caution")}>
              <span className="font-semibold">{fmt(env.dose_rate_msv_day, 2)}</span> mSv/day
            </span>
          </div>
          {env.open_alerts.length > 0 && (
            <p className="mt-2 text-xs text-caution">{env.open_alerts.length} environment or radiation alert(s) unresolved.</p>
          )}
          <p className="mt-2 text-xs text-ink-3">Simulated habitat values; nominal levels are simulator settings, not limits.</p>
        </>
      )}
    </DataCard>
  );
}

// ------------------------------------------------------------ radiation timeline ----
function RadiationTimelineCard({ o }: { o: MissionControlOverview }) {
  const r = data<RadiationSectionData>(o.radiation_timeline);
  const rows = (r?.days ?? []).map((d) => ({ ...d, label: utcDay(d.day) }));
  return (
    <DataCard
      id="radiation-timeline"
      title="Radiation event timeline, last 7 days"
      icon={<RadiationIcon />}
      href="/radiation"
      hrefLabel="Radiation intelligence"
      className="xl:col-span-8"
    >
      {!r ? (
        <Unavailable reason={o.radiation_timeline.reason} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
          <div className="space-y-1">
            <p className="flex items-center gap-2 text-xs text-ink-2">
              Mean crew daily dose <OriginChip origin="simulated" />
            </p>
            <div role="img" aria-label="Mean simulated crew dose per day" className="h-32">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={rows} margin={{ top: 6, right: 8, left: 0, bottom: 0 }} barCategoryGap={6}>
                  <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.5} vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--bulkhead)" }} />
                  <YAxis tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={false} width={40} />
                  <Tooltip
                    cursor={{ fill: "var(--bulkhead)", fillOpacity: 0.3 }}
                    contentStyle={{ background: "var(--popover)", border: "1px solid var(--bulkhead)", borderRadius: 6, fontSize: 12 }}
                    labelStyle={{ color: "var(--ink-2)" }}
                    formatter={(v) => [`${fmt(Number(v), 3)} mSv`, "Mean crew dose (simulated)"]}
                  />
                  <Bar dataKey="mean_crew_dose_msv" fill="var(--telemetry)" fillOpacity={0.85} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="flex items-center gap-2 pt-2 text-xs text-ink-2">
              Radiation-relevant space-weather events <OriginChip origin="nasa" />
            </p>
            <ol
              className="grid gap-1"
              style={{ gridTemplateColumns: `repeat(${Math.max(1, rows.length)}, minmax(0, 1fr))` }}
              aria-label="NASA events per day"
            >
              {rows.map((d) => (
                <li key={d.day} className="flex flex-col items-center gap-1 rounded-md border border-bulkhead/50 py-1.5" title={`${d.label}: ${d.nasa_events} NASA event(s)${d.simulated_spe ? ", simulated SPE" : ""}`}>
                  <span className={cn("readout text-base font-semibold", d.nasa_events ? "text-nominal" : "text-ink-3")}>{d.nasa_events}</span>
                  <span className="text-[10px] text-ink-3">{d.label}</span>
                  {d.simulated_spe && <span className="text-[10px] text-caution">SPE sim</span>}
                </li>
              ))}
            </ol>
          </div>
          <div className="min-w-0">
            <p className="text-xs text-ink-3">Latest NASA events</p>
            {r.nasa_events.length === 0 ? (
              <p className="mt-2 text-sm text-ink-2">No radiation-relevant DONKI events in this window.</p>
            ) : (
              <ul className="scroll-quiet mt-1 max-h-48 overflow-y-auto">
                {r.nasa_events.slice(0, 8).map((e) => (
                  <li key={e.id} className="border-b border-bulkhead/40 py-1.5 text-sm last:border-0">
                    <p className="truncate">
                      {e.label} {e.scale ?? ""} {e.classification ? <span className="text-ink-2">{e.classification}</span> : null}
                    </p>
                    <p className="text-xs text-ink-3">{utcDay(e.time)} {utcTime(e.time, false)} UTC, {e.alert_severity}</p>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-2 text-[11px] leading-snug text-ink-3">{r.notes.join(" ")}</p>
          </div>
        </div>
      )}
    </DataCard>
  );
}

// ---------------------------------------------------------------- space weather ----
function SpaceWeatherCard({ o }: { o: MissionControlOverview }) {
  const s = data<SpaceSectionData>(o.space_weather);
  const order = ["FLR", "CME", "SEP", "GST", "RBE", "IPS", "HSS"];
  return (
    <DataCard
      id="space-weather"
      title="Space weather status"
      icon={<Sun />}
      meta={<OriginChip origin="nasa" />}
      href="/space/weather"
      hrefLabel="Space weather"
      className="xl:col-span-4"
      tone={s?.radiation_alerts.some((a) => a.status === "active") ? "caution" : undefined}
      footer={s ? s.freshness.message : undefined}
    >
      {!s ? (
        <Unavailable reason={o.space_weather.reason} />
      ) : (
        <>
          <dl className="grid grid-cols-4 gap-2">
            {order.filter((t) => t in s.counts).map((t) => (
              <div key={t} className="rounded-md border border-bulkhead/50 px-2 py-1.5">
                <dt className="text-[11px] text-ink-3">{t}</dt>
                <dd className="readout text-lg font-semibold">{s.counts[t]}</dd>
              </div>
            ))}
          </dl>
          <dl className="mt-3 space-y-1 text-sm">
            <div className="flex justify-between gap-2">
              <dt className="text-ink-2">Strongest flare</dt>
              <dd className="truncate">{s.strongest_flare?.classification ?? "none"}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-ink-2">Strongest storm</dt>
              <dd className="truncate">{s.max_storm ? `${s.max_storm.scale ?? ""} Kp ${fmt(s.max_storm.magnitude, 1)}` : "none"}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-ink-2">Fastest CME</dt>
              <dd className="truncate">{s.fastest_cme ? `${fmt(s.fastest_cme.magnitude, 0)} km/s` : "none"}</dd>
            </div>
          </dl>
          {s.radiation_alerts.length > 0 && (
            <ul className="mt-3 space-y-1 border-t border-bulkhead/50 pt-2">
              {s.radiation_alerts.slice(0, 3).map((a) => (
                <li key={a.id} className="flex items-start gap-2 text-xs">
                  <SeverityDot severity={a.severity as "advisory"} className="mt-1" announce />
                  <span className="min-w-0 flex-1 truncate">{a.title}</span>
                  <span className="text-ink-3">{a.status}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </DataCard>
  );
}

// ---------------------------------------------------------------- incidents ----
function IncidentsCard({ o }: { o: MissionControlOverview }) {
  const inc = data<IncidentsSectionData>(o.incidents);
  return (
    <DataCard
      id="incidents"
      title="Recent mission incidents"
      icon={<GanttChart />}
      meta="last 24 h, P1 to P3"
      href="/timeline"
      hrefLabel="Situational awareness"
      className="xl:col-span-8"
    >
      {!inc ? (
        <Unavailable reason={o.incidents.reason} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_16rem]">
          {inc.recent_events.length === 0 ? (
            <p className="py-4 text-sm text-ink-2">No significant mission events in the last 24 hours.</p>
          ) : (
            <ol className="scroll-quiet max-h-72 overflow-y-auto">
              {inc.recent_events.map((e) => (
                <li key={e.id} className="grid grid-cols-[3.5rem_auto_1fr] items-start gap-2 border-b border-bulkhead/40 py-1.5 text-sm last:border-0">
                  <span className="text-xs text-ink-3 tabular-nums">{utcTime(e.occurred_at, false)}</span>
                  <PriorityBadge priority={e.priority} compact />
                  <span className="min-w-0">
                    <span className="line-clamp-1">{e.title}</span>
                    <span className="flex items-center gap-1.5 text-xs text-ink-3">
                      {e.category_label}
                      {e.experimental && <span className="text-advisory">experimental</span>}
                      {e.occurrences > 1 && <span>x{e.occurrences}</span>}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          )}
          <div className="space-y-3 text-sm">
            <div>
              <p className="text-xs text-ink-3">Incident reports</p>
              {!inc.reports_visible ? (
                <p className="mt-1 text-ink-2">Not available for your role.</p>
              ) : inc.reports.length === 0 ? (
                <p className="mt-1 text-ink-2">None yet.</p>
              ) : (
                <ul className="mt-1 space-y-1">
                  {inc.reports.map((r) => (
                    <li key={r.id}>
                      <Link href={`/reports?report=${r.id}`} className="line-clamp-1 hover:text-telemetry">
                        {r.title}
                      </Link>
                      <p className="text-xs text-ink-3">{r.review_status.replace(/_/g, " ")}, {utcDay(r.created_at)}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <p className="text-xs text-ink-3">Emergency simulator runs</p>
              {inc.emergency_runs.length === 0 ? (
                <p className="mt-1 text-ink-2">None.</p>
              ) : (
                <ul className="mt-1 space-y-1">
                  {inc.emergency_runs.map((r) => (
                    <li key={r.id}>
                      <Link href={`/emergency?run=${r.id}`} className="line-clamp-1 hover:text-telemetry">
                        {r.label}
                      </Link>
                      <p className="text-xs text-ink-3">{r.astronaut_id ?? "crew"}, {r.severity}, {utcDay(r.started_at)}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </DataCard>
  );
}

// -------------------------------------------------------------- connectivity ----
const COMP_TONE: Record<ComponentStatus["status"], string> = {
  ok: "bg-nominal",
  degraded: "bg-caution",
  down: "bg-critical",
  disabled: "bg-ink-3",
  unavailable: "bg-advisory",
};

export function ConnectivityList({ components, dense = false }: { components: ComponentStatus[]; dense?: boolean }) {
  return (
    <ul className={cn(dense ? "space-y-1.5" : "space-y-2")}>
      {components.map((c) => (
        <li key={c.key} className="flex items-start gap-2 text-sm">
          <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", COMP_TONE[c.status])} aria-hidden />
          <span className="min-w-0 flex-1">
            <span className="flex items-baseline justify-between gap-2">
              <span className="truncate">{c.label}</span>
              <span className={cn("shrink-0 text-xs", c.status === "ok" ? "text-nominal" : c.status === "down" ? "text-critical" : c.status === "degraded" ? "text-caution" : "text-ink-3")}>
                {c.status}
              </span>
            </span>
            {!dense && <span className="line-clamp-1 text-xs text-ink-3">{c.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

function ConnectivityCard({ o }: { o: MissionControlOverview }) {
  const connection = useLive((s) => s.connection);
  const bad = o.connectivity.filter((c) => c.status === "down" || c.status === "degraded").length;
  return (
    <DataCard
      id="connectivity"
      title="System connectivity"
      icon={<ServerCog />}
      meta={<span className={bad ? "text-caution" : "text-nominal"}>{bad ? `${bad} need attention` : "All systems nominal"}</span>}
      href="/system"
      hrefLabel="System status"
      className="xl:col-span-4"
      footer={<span>Browser stream: {connection}</span>}
    >
      <ConnectivityList components={o.connectivity} />
    </DataCard>
  );
}

// ------------------------------------------------------------------------ page ----
export function CommandDashboard() {
  const q = useMissionControl();
  if (q.isPending) return <LoadingState label="Loading mission control" rows={8} />;
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const o = q.data!;
  const panels: [string, React.ComponentType<{ o: MissionControlOverview }>][] = [
    ["Crew status", CrewStatusCard],
    ["Alerts", AlertQueueCard],
    ["AI risk", AiRiskCard],
    ["Health monitoring", HealthCard],
    ["Environment", EnvironmentCard],
    ["Radiation timeline", RadiationTimelineCard],
    ["Space weather", SpaceWeatherCard],
    ["Incidents", IncidentsCard],
    ["Connectivity", ConnectivityCard],
  ];
  return (
    <div className="space-y-4">
      <h1 className="sr-only">Mission control</h1>
      <ErrorBoundary label="Mission summary">
        <KpiBand o={o} />
      </ErrorBoundary>
      <div className="grid gap-4 xl:grid-cols-12">
        {panels.map(([label, Panel]) => (
          <ErrorBoundary key={label} label={label} className="xl:col-span-4">
            <Panel o={o} />
          </ErrorBoundary>
        ))}
      </div>
      <p className="text-xs text-ink-3">
        {o.notes.join(" ")} Updated {utcTime(o.generated_at)} UTC.
      </p>
    </div>
  );
}
