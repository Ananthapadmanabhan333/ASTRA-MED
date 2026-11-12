"use client";

import { Fingerprint } from "lucide-react";
import { useState } from "react";

import { ChartTable } from "@/components/charts/chart-table";
import { TrendChart, type ChartRow } from "@/components/charts/trend-chart";
import { Panel } from "@/components/data/panel";
import { ErrorState, LoadingState, QueryView } from "@/components/data/states";
import { StatusPill } from "@/components/status/status";
import { useAstronauts } from "@/lib/api/hooks";
import { useTwin, useTwinStages, useTwinTimeline, useTwinTrend } from "@/lib/api/medical-hooks";
import type { TwinDay, TwinProfile } from "@/lib/api/types";
import { crewColor } from "@/lib/crew";
import { fmt, relativeTime, utcDay, utcDayTime } from "@/lib/format";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

import { CrewPicker, KindChip, Kv, SimulatedBanner, useParamState } from "./common";

const TREND_OPTIONS = [
  { metric: "heart_rate", label: "Heart rate", unit: "bpm", decimals: 1 },
  { metric: "spo2", label: "SpO₂", unit: "%", decimals: 2 },
  { metric: "respiratory_rate", label: "Respiratory rate", unit: "br/min", decimals: 1 },
  { metric: "temperature_c", label: "Temperature", unit: "°C", decimals: 2 },
  { metric: "systolic", label: "Systolic BP", unit: "mmHg", decimals: 1 },
  { metric: "sleep_duration_hours", label: "Sleep duration", unit: "h", decimals: 2 },
  { metric: "sleep_efficiency_pct", label: "Sleep efficiency", unit: "%", decimals: 1 },
  { metric: "exercise_minutes", label: "Exercise", unit: "min", decimals: 0 },
  { metric: "dose_msv", label: "Daily dose (simulated)", unit: "mSv", decimals: 3 },
] as const;

const VITALS = [
  ["heart_rate", "Heart rate", "bpm", 0],
  ["spo2", "SpO₂", "%", 1],
  ["systolic", "Systolic", "mmHg", 0],
  ["diastolic", "Diastolic", "mmHg", 0],
  ["temperature_c", "Temperature", "°C", 2],
  ["respiratory_rate", "Resp. rate", "br/min", 0],
] as const;

function Header({ p }: { p: TwinProfile }) {
  const now = useNow(5_000);
  const a = p.astronaut;
  return (
    <Panel raised>
      <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
        <div className="min-w-0 flex-1 basis-64">
          <div className="flex flex-wrap items-center gap-2">
            <span className="size-3 rounded-full" style={{ background: crewColor(a.id) }} aria-hidden />
            <h2 className="font-heading text-2xl font-semibold">{a.name}</h2>
            <StatusPill status={p.current.status} />
            <KindChip kind="simulated" />
          </div>
          <p className="mt-1 text-sm text-ink-2">{a.role}. {a.specialty}. Fictional crew member.</p>
          <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
            <Kv label="Age / sex">{a.age} / {a.sex}</Kv>
            <Kv label="Height / mass">{a.height_cm} cm / {fmt(a.mass_kg, 1)} kg</Kv>
            <Kv label="Mission day">{p.mission.day} · {p.mission.stage.label}</Kv>
            <Kv label="Last measurement">
              {p.last_measurement_at ? (now ? relativeTime(p.last_measurement_at, now) : utcDayTime(p.last_measurement_at)) : "none"}
            </Kv>
          </dl>
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <Kv label="Days in twin">{p.coverage.days_total}</Kv>
          <Kv label="Stored / regenerated">{p.coverage.days_stored} / {p.coverage.days_regenerated}</Kv>
          <Kv label="Open alerts">{p.current.open_alerts}</Kv>
          <Kv label="Twin updated">{p.twin_updated_at ? utcDayTime(p.twin_updated_at) + " UTC" : "on request"}</Kv>
        </dl>
      </div>
      {p.current.active_scenarios.length > 0 && (
        <p className="mt-3 rounded-md border border-caution/40 bg-caution/10 px-3 py-2 text-sm text-caution">
          Simulated test scenario running: {p.current.active_scenarios.join(", ")}. Current values are injected by the simulator.
        </p>
      )}
      <p className="mt-3 text-xs text-ink-3">{p.disclaimer}</p>
    </Panel>
  );
}

function Current({ p }: { p: TwinProfile }) {
  const r = p.current.reading;
  return (
    <Panel title="Current state" description="Latest simulated reading streamed from the monitoring engine." actions={<KindChip kind="simulated" />}>
      {!r ? (
        <p className="text-sm text-ink-2">No reading yet.</p>
      ) : (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {VITALS.map(([k, label, unit, d]) => (
            <div key={k} className="rounded-md border border-bulkhead/70 px-3 py-2">
              <dt className="text-xs text-ink-3">{label}</dt>
              <dd className="readout text-2xl">{fmt(r[k] as number, d)} <span className="text-xs text-ink-3">{unit}</span></dd>
            </div>
          ))}
          <div className="col-span-2 text-xs text-ink-3 sm:col-span-3">
            {r.activity_state} at {fmt(r.activity_met, 1)} MET · rhythm {r.rhythm}
            {r.hrv_rmssd_ms != null && ` · HRV ${fmt(r.hrv_rmssd_ms, 0)} ms`} · {utcDayTime(r.ts)} UTC
          </div>
        </dl>
      )}
    </Panel>
  );
}

function Comparison({ p }: { p: TwinProfile }) {
  return (
    <Panel
      title="Baseline vs current"
      description="Awake-at-rest values (rest or desk work, no test scenario), so activity does not confound the comparison."
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <caption className="sr-only">Resting values: configured, early mission, last 7 days, last 24 hours, learned baseline</caption>
          <thead className="text-xs text-ink-2">
            <tr className="border-b border-bulkhead">
              <th scope="col" className="py-2 pr-3 font-medium">Signal</th>
              <th scope="col" className="py-2 pr-3 font-medium"><span className="flex items-center gap-1.5">Configured <KindChip kind="configured" /></span></th>
              <th scope="col" className="py-2 pr-3 font-medium"><span className="flex items-center gap-1.5">Early mission <KindChip kind="derived" /></span></th>
              <th scope="col" className="py-2 pr-3 font-medium">Last 7 days</th>
              <th scope="col" className="py-2 pr-3 font-medium">Last 24 h</th>
              <th scope="col" className="py-2 pr-3 font-medium"><span className="flex items-center gap-1.5">Learned baseline <KindChip kind="model" /></span></th>
              <th scope="col" className="py-2 font-medium">7 d vs early</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {p.resting_comparison.map((c) => (
              <tr key={c.metric} className="border-b border-bulkhead/50">
                <th scope="row" className="py-2 pr-3 font-medium">{c.label} <span className="text-xs font-normal text-ink-3">{c.unit}</span></th>
                <td className="py-2 pr-3 text-ink-2" title={c.configured.note ?? undefined}>{fmt(c.configured.value, 1)}</td>
                <td className="py-2 pr-3">{fmt(c.early_mission.value, 2)} <span className="text-xs text-ink-3">{c.early_mission.n_days} d</span></td>
                <td className="py-2 pr-3">{fmt(c.last_7d.value, 2)}</td>
                <td className="py-2 pr-3">{fmt(c.last_24h.value, 2)} <span className="text-xs text-ink-3">n={c.last_24h.n}</span></td>
                <td className="py-2 pr-3">{fmt(c.personal_baseline.value, 2)}</td>
                <td className="py-2">
                  {c.change_7d_vs_early ? `${c.change_7d_vs_early.abs! > 0 ? "+" : ""}${fmt(c.change_7d_vs_early.abs, 2)} (${fmt(c.change_7d_vs_early.pct, 1)}%)` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-ink-3">
        Early mission = mean of daily awake-rest means over days 0–14 (regenerated by the simulator where samples were pruned).
        The configured HRV is SDNN, not comparable with the RMSSD shown elsewhere.
      </p>
    </Panel>
  );
}

function Trend({ aid }: { aid: string }) {
  const [metric, setMetric] = useState<(typeof TREND_OPTIONS)[number]["metric"]>("heart_rate");
  const opt = TREND_OPTIONS.find((o) => o.metric === metric)!;
  const statistic = ["sleep_duration_hours", "sleep_efficiency_pct", "exercise_minutes", "dose_msv"].includes(metric) ? "mean" : "awake_rest_mean";
  const q = useTwinTrend(aid, metric, statistic);
  return (
    <Panel
      title="Longitudinal trend"
      description="One value per mission day with a 7-day rolling mean. Hollow periods are regenerated days."
      actions={
        <label className="flex items-center gap-2 text-sm">
          <span className="text-ink-3">Signal</span>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as typeof metric)}
            className="h-8 rounded-md border border-input bg-abyss px-2 text-sm"
          >
            {TREND_OPTIONS.map((o) => <option key={o.metric} value={o.metric}>{o.label}</option>)}
          </select>
        </label>
      }
    >
      <QueryView query={q} loading={<LoadingState rows={4} />}>
        {(t) => {
          const data: ChartRow[] = t.points.map((p) => ({
            t: Date.parse(p.day), value: p.value ?? null, rolling: p.rolling_7d ?? null,
            stored: p.basis === "stored" ? p.value ?? null : null,
          }));
          const series = [
            { key: "value", label: "Daily", color: "var(--ink-3)" },
            { key: "stored", label: "Daily (stored)", color: "var(--telemetry)" },
            { key: "rolling", label: "7-day mean", color: "var(--caution)", dash: "6 3" },
          ];
          return (
            <div className="space-y-3">
              <TrendChart data={data} series={series} unit={opt.unit} decimals={opt.decimals} height={220}
                ariaLabel={`${opt.label} per mission day for the selected crew member`} />
              <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
                <KindChip kind="derived" />
                {t.trend ? (
                  <span>
                    Trend {t.trend.slope_per_30d > 0 ? "+" : ""}{fmt(t.trend.slope_per_30d, opt.decimals + 1)} {opt.unit} per 30 days
                    (95% CI {fmt(t.trend.ci95[0], opt.decimals + 1)} to {fmt(t.trend.ci95[1], opt.decimals + 1)}): <strong>{t.trend.direction}</strong>
                    <span className="text-ink-3"> · {t.trend.n_days} days, effective n {fmt(t.trend.n_eff, 0)}</span>
                  </span>
                ) : (
                  <span className="text-ink-2">Not enough complete days for a trend.</span>
                )}
                {t.cumulative && <span>Cumulative {fmt(t.cumulative.at(-1)?.value, 1)} mSv (simulated)</span>}
              </div>
              {t.notes.map((n) => <p key={n} className="text-xs text-ink-3">{n}</p>)}
              <details className="text-sm">
                <summary className="cursor-pointer text-ink-2">Table view</summary>
                <ChartTable data={data} series={series.slice(0, 1).concat(series.slice(2))} unit={opt.unit} decimals={opt.decimals} caption={`${opt.label} per day`} />
              </details>
            </div>
          );
        }}
      </QueryView>
    </Panel>
  );
}

function Stages({ aid }: { aid: string }) {
  const q = useTwinStages(aid);
  return (
    <Panel title="Changes across mission stages" description="Mean of daily values per stage, compared with the first stage.">
      <QueryView query={q}>
        {(s) => (
          <div className="space-y-2">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm tabular-nums">
                <thead className="text-xs text-ink-2">
                  <tr className="border-b border-bulkhead">
                    <th scope="col" className="py-2 pr-3 font-medium">Stage</th>
                    <th scope="col" className="py-2 pr-3 font-medium">Days</th>
                    <th scope="col" className="py-2 pr-3 font-medium">Resting HR (bpm)</th>
                    <th scope="col" className="py-2 pr-3 font-medium">Δ vs first (95% CI)</th>
                    <th scope="col" className="py-2 pr-3 font-medium">Sleep (h)</th>
                    <th scope="col" className="py-2 font-medium">Dose (mSv/day)</th>
                  </tr>
                </thead>
                <tbody>
                  {s.stages.map((st) => {
                    const hr = st.metrics.heart_rate as { mean?: number; sd?: number; vs_first_stage?: { diff: number; ci95: number[] } } | undefined;
                    const sl = st.metrics.sleep_duration_hours as { mean?: number } | undefined;
                    const dose = st.metrics.dose_msv as { mean?: number } | undefined;
                    return (
                      <tr key={st.key} className="border-b border-bulkhead/50">
                        <th scope="row" className="py-2 pr-3 font-medium">{st.label} <span className="text-xs font-normal text-ink-3">d{st.first_day}–{st.last_day ?? ""}</span></th>
                        <td className="py-2 pr-3">{st.n_days} <span className="text-xs text-ink-3">{Object.entries(st.basis).map(([k, v]) => `${v} ${k}`).join(", ")}</span></td>
                        <td className="py-2 pr-3">{fmt(hr?.mean, 1)} ± {fmt(hr?.sd, 1)}</td>
                        <td className="py-2 pr-3">{hr?.vs_first_stage ? `${fmt(hr.vs_first_stage.diff, 1)} (${fmt(hr.vs_first_stage.ci95[0], 1)} to ${fmt(hr.vs_first_stage.ci95[1], 1)})` : "reference"}</td>
                        <td className="py-2 pr-3">{fmt(sl?.mean, 2)}</td>
                        <td className="py-2">{fmt(dose?.mean, 3)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {s.notes.map((n) => <p key={n} className="text-xs text-ink-3">{n}</p>)}
          </div>
        )}
      </QueryView>
    </Panel>
  );
}

function DayRow({ d }: { d: TwinDay }) {
  const hr = (d.metrics.heart_rate as { awake_rest_mean?: number } | undefined)?.awake_rest_mean;
  const sleep = d.sleep as { duration_hours?: number; efficiency_pct?: number } | null;
  const dose = d.radiation as { dose_msv?: number; solar_particle_event?: boolean } | null;
  const ev = d.events as { alert_counts?: Record<string, number>; alerts_available?: boolean; scenarios?: unknown[]; emergency_runs?: unknown[] };
  const alerts = Object.entries(ev.alert_counts ?? {});
  const sw = Object.entries(d.space_weather as Record<string, { count: number; max_scale: string | null }>);
  return (
    <tr className="border-b border-bulkhead/50 align-top">
      <th scope="row" className="py-2 pr-3 font-medium whitespace-nowrap">
        {utcDay(d.day)} <span className="block text-xs font-normal text-ink-3">day {d.mission_day}{d.complete ? "" : " · in progress"}</span>
      </th>
      <td className="py-2 pr-3"><KindChip kind={d.category} /></td>
      <td className="py-2 pr-3 tabular-nums">{fmt(hr, 1)}</td>
      <td className="py-2 pr-3 tabular-nums">{sleep ? `${fmt(sleep.duration_hours, 1)} h · ${fmt(sleep.efficiency_pct, 0)}%` : "—"}</td>
      <td className="py-2 pr-3 tabular-nums">{dose ? `${fmt(dose.dose_msv, 2)}${dose.solar_particle_event ? " SPE" : ""}` : "—"}</td>
      <td className="py-2 pr-3">
        {!ev.alerts_available ? <span className="text-xs text-ink-3">not stored</span> : alerts.length ? alerts.map(([k, v]) => `${v} ${k}`).join(", ") : "none"}
        {(ev.scenarios?.length ?? 0) > 0 && <span className="block text-xs text-caution">{ev.scenarios!.length} test scenario(s)</span>}
        {(ev.emergency_runs?.length ?? 0) > 0 && <span className="block text-xs text-caution">{ev.emergency_runs!.length} emergency run(s)</span>}
      </td>
      <td className="py-2 text-xs text-ink-2">{sw.length ? sw.map(([k, v]) => `${v.count} ${k}${v.max_scale ? ` (${v.max_scale})` : ""}`).join(", ") : "—"}</td>
    </tr>
  );
}

function Timeline({ aid }: { aid: string }) {
  const [days, setDays] = useState(14);
  const q = useTwinTimeline(aid, days);
  return (
    <Panel
      title="Health timeline"
      description="One row per mission day: summaries, sleep, simulated dose, alerts, test scenarios and real NASA space-weather events."
      actions={
        <div role="radiogroup" aria-label="Days shown" className="flex gap-1">
          {[7, 14, 30, 90].map((n) => (
            <button key={n} type="button" role="radio" aria-checked={days === n} onClick={() => setDays(n)}
              className={cn("rounded-md border px-2 py-0.5 text-xs", days === n ? "border-telemetry text-foreground" : "border-bulkhead text-ink-2")}>
              {n} d
            </button>
          ))}
        </div>
      }
    >
      <QueryView query={q}>
        {(t) => (
          <div className="max-h-[28rem] overflow-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <caption className="sr-only">Daily twin summaries, newest first</caption>
              <thead className="sticky top-0 bg-hull text-xs text-ink-2">
                <tr className="border-b border-bulkhead">
                  <th scope="col" className="py-2 pr-3 font-medium">Day</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Basis</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Resting HR</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Sleep</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Dose mSv <KindChip kind="simulated" /></th>
                  <th scope="col" className="py-2 pr-3 font-medium">Alerts and tests</th>
                  <th scope="col" className="py-2 font-medium">NASA DONKI <KindChip kind="indicator" /></th>
                </tr>
              </thead>
              <tbody>{[...t.days].reverse().map((d) => <DayRow key={d.day} d={d} />)}</tbody>
            </table>
          </div>
        )}
      </QueryView>
    </Panel>
  );
}

function Exposure({ p }: { p: TwinProfile }) {
  return (
    <Panel title="Exposure and sleep" actions={<KindChip kind="simulated" />}>
      <dl className="grid grid-cols-2 gap-3">
        <Kv label="Mission dose">{fmt(p.exposure.mission_dose_msv, 1)} mSv</Kv>
        <Kv label="Last 30 days">{fmt(p.exposure.last_30d_dose_msv, 1)} mSv</Kv>
        <Kv label="Career total">{fmt(p.exposure.career_total_msv, 0)} of {fmt(p.exposure.career_limit_msv, 0)} mSv</Kv>
        <Kv label="Simulated SPE days">{p.exposure.spe_days}</Kv>
        <Kv label="Sleep, last 7 nights">{fmt(p.sleep_7d.mean_duration_hours, 1)} h</Kv>
        <Kv label="Sleep efficiency">{fmt(p.sleep_7d.mean_efficiency_pct, 0)}%</Kv>
      </dl>
      <p className="mt-2 text-xs text-ink-3">{p.exposure.note}</p>
    </Panel>
  );
}

function Legend({ p }: { p: TwinProfile }) {
  return (
    <Panel title="What the labels mean">
      <ul className="space-y-1.5 text-sm">
        {p.categories.map((c) => (
          <li key={c.key} className="flex items-start gap-2"><KindChip kind={c.key} className="mt-0.5" /> <span className="text-ink-2">{c.description}</span></li>
        ))}
      </ul>
    </Panel>
  );
}

export function TwinView() {
  const crew = useAstronauts();
  const [param, setParam] = useParamState("astronaut");
  const aid = param ?? crew.data?.[0]?.id ?? null;
  const twin = useTwin(aid ?? "");
  return (
    <div className="space-y-5">
      <SimulatedBanner>
        The twin is a structured record of simulated measurements, statistics derived from them, events and environmental
        context. It does not reproduce the complete biological state of a person.
      </SimulatedBanner>
      <CrewPicker value={aid} onChange={(v) => setParam(v)} />
      {!aid ? (
        <LoadingState rows={4} />
      ) : twin.isPending ? (
        <LoadingState label="Building the digital twin" rows={6} />
      ) : twin.error && !twin.data ? (
        <ErrorState error={twin.error} onRetry={() => twin.refetch()} />
      ) : (
        <>
          <Header p={twin.data!} />
          <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
            <Current p={twin.data!} />
            <div className="min-w-0 xl:col-span-2"><Comparison p={twin.data!} /></div>
          </div>
          <Trend aid={aid} />
          <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
            <div className="min-w-0 xl:col-span-2"><Stages aid={aid} /></div>
            <Exposure p={twin.data!} />
          </div>
          <Timeline aid={aid} />
          <Legend p={twin.data!} />
        </>
      )}
      <p className="flex items-center gap-2 text-xs text-ink-3"><Fingerprint className="size-3.5" aria-hidden /> Twin rows refresh every 5 minutes; the current state follows the live stream.</p>
    </div>
  );
}
