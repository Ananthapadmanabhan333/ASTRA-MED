"use client";

import Link from "next/link";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { TrendChart, type ChartRow } from "@/components/charts/trend-chart";
import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { StatusPill } from "@/components/status/status";
import { useOverview } from "@/lib/api/medical-hooks";
import type { CrewStatus, MissionOverview, Severity, SystemStatus } from "@/lib/api/types";
import { crewColor, crewDash } from "@/lib/crew";
import { fmt, utcDay, utcDayTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { CrewPicker, KindChip, SimulatedBanner, SystemStatusPill } from "./common";

const SYSTEM_SHORT: Record<string, string> = {
  cardiovascular: "Cardio", respiratory: "Resp", thermoregulation: "Thermo", sleep_circadian: "Sleep",
  activity_recovery: "Activity", radiation: "Radiation",
};

function CrewCards({ o }: { o: MissionOverview }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {o.crew.map((c) => (
        <article key={c.astronaut_id} className="rounded-lg border border-bulkhead/70 bg-hull/55 p-3">
          <header className="flex items-center gap-2">
            <span className="size-2.5 rounded-full" style={{ background: crewColor(c.astronaut_id) }} aria-hidden />
            <h3 className="font-heading text-base font-semibold">{c.name}</h3>
            <span className="ml-auto"><StatusPill status={c.status as CrewStatus} /></span>
          </header>
          <p className="text-xs text-ink-3">{c.role} · {c.astronaut_id}</p>
          {c.risk && <p className="mt-1.5 text-sm"><KindChip kind="model" /> {c.risk.category_label} <span className="text-ink-3">({fmt(c.risk.score, 0)}/100)</span></p>}
          <ul className="mt-2 grid grid-cols-3 gap-1">
            {Object.entries(c.systems).map(([k, v]) => (
              <li key={k} className="flex items-center gap-1 text-[11px] text-ink-2" title={`${k}: ${v}`}><SystemStatusPill status={v as SystemStatus} compact /> {SYSTEM_SHORT[k] ?? k}</li>
            ))}
          </ul>
          {c.patterns.length > 0 && <p className="mt-1.5 text-xs text-caution">{c.patterns.join("; ")}</p>}
          <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <dt className="text-ink-3">Open alerts</dt><dd className="tabular-nums">{c.open_alerts}</dd>
            <dt className="text-ink-3">Alerts in period</dt><dd className="tabular-nums">{Object.entries(c.alerts_in_period).map(([k, v]) => `${v} ${k}`).join(", ") || "0"}</dd>
            <dt className="text-ink-3">Resting HR</dt><dd className="tabular-nums">{fmt(c.resting_hr_mean, 1)} bpm</dd>
            <dt className="text-ink-3">Sleep</dt><dd className="tabular-nums">{fmt(c.sleep_mean_hours, 1)} h</dd>
            <dt className="text-ink-3">Dose (sim.)</dt><dd className="tabular-nums">{fmt(c.dose_period_msv, 1)} mSv</dd>
            <dt className="text-ink-3">Reports</dt><dd className="tabular-nums">{c.reports_in_period}</dd>
          </dl>
          <p className="mt-2 flex gap-3 text-xs">
            <Link className="text-telemetry hover:underline" href={`/twin?astronaut=${c.astronaut_id}`}>Twin</Link>
            <Link className="text-telemetry hover:underline" href={`/medical?astronaut=${c.astronaut_id}`}>Systems</Link>
          </p>
        </article>
      ))}
    </div>
  );
}

function AlertHistory({ o }: { o: MissionOverview }) {
  const rows = o.alert_history.map((d) => ({ ...d, label: utcDay(d.day) }));
  return (
    <div className="h-56" role="img" aria-label="Alerts opened per day by severity">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.5} vertical={false} />
          <XAxis dataKey="label" tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--bulkhead)" }} minTickGap={16} />
          <YAxis allowDecimals={false} tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={false} width={28} />
          <Tooltip cursor={{ fill: "var(--bulkhead)", fillOpacity: 0.3 }} contentStyle={{ background: "var(--popover)", border: "1px solid var(--bulkhead)", fontSize: 12 }} isAnimationActive={false} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="critical" stackId="a" fill="var(--critical)" name="Critical" isAnimationActive={false} />
          <Bar dataKey="caution" stackId="a" fill="var(--caution)" name="Caution" isAnimationActive={false} />
          <Bar dataKey="advisory" stackId="a" fill="var(--advisory)" name="Advisory" isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function CrewTrend({ o, metric, unit, label, decimals }: { o: MissionOverview; metric: "heart_rate" | "sleep_duration_hours"; unit: string; label: string; decimals: number }) {
  const byDay = new Map<number, ChartRow>();
  for (const s of o.trends[metric] ?? []) {
    for (const p of s.points) {
      const t = Date.parse(p.day);
      const row = byDay.get(t) ?? { t };
      row[s.astronaut_id] = p.value ?? null;
      byDay.set(t, row);
    }
  }
  const data = [...byDay.values()].sort((a, b) => a.t - b.t);
  const series = (o.trends[metric] ?? []).map((s) => ({
    key: s.astronaut_id, label: o.crew.find((c) => c.astronaut_id === s.astronaut_id)?.name.split(" ")[0] ?? s.astronaut_id,
    color: crewColor(s.astronaut_id), dash: crewDash(s.astronaut_id),
  }));
  if (data.length < 2) return <p className="text-sm text-ink-2">Pick a longer period to see daily trends.</p>;
  return <TrendChart data={data} series={series} unit={unit} decimals={decimals} height={190} endLabels ariaLabel={`${label} per day for each crew member`} />;
}

export function OverviewView() {
  const [period, setPeriod] = useState<"24h" | "7d" | "30d">("7d");
  const [aid, setAid] = useState<string | null>(null);
  const q = useOverview(period, aid);
  return (
    <div className="space-y-5">
      <SimulatedBanner />
      <div className="flex flex-wrap items-center gap-4">
        <div role="radiogroup" aria-label="Period" className="flex gap-1">
          {(["24h", "7d", "30d"] as const).map((p) => (
            <button key={p} type="button" role="radio" aria-checked={period === p} onClick={() => setPeriod(p)}
              className={cn("rounded-md border px-2.5 py-1 text-sm", period === p ? "border-telemetry bg-telemetry/10 text-foreground" : "border-bulkhead text-ink-2")}>{p}</button>
          ))}
        </div>
        <CrewPicker value={aid} onChange={setAid} allowAll />
      </div>
      {q.isPending ? <LoadingState label="Building the mission overview" rows={6} /> : q.error && !q.data ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (() => {
        const o = q.data!;
        return (
          <>
            <Panel raised title="Mission health summary" description={o.summary.method}>
              <ul className="space-y-1.5">
                {o.summary.statements.map((s) => <li key={s.text} className="text-sm"><KindChip kind={s.kind} className="mr-1.5 align-middle" />{s.text}</li>)}
              </ul>
            </Panel>
            <CrewCards o={o} />
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
              <Panel title="Alert history" description={`Alerts opened per day, ${utcDay(o.start)} to ${utcDay(o.end)}.`}><AlertHistory o={o} /></Panel>
              <Panel title="Resting heart rate" description="Daily awake-at-rest mean from the digital twin." actions={<KindChip kind="derived" />}>
                <CrewTrend o={o} metric="heart_rate" unit="bpm" label="Resting heart rate" decimals={1} />
              </Panel>
            </div>
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
              <Panel title="Active alerts">
                {o.active_alerts.length === 0 ? <EmptyState title="No open alerts in this period" /> : (
                  <ul className="max-h-72 space-y-1.5 overflow-auto">
                    {o.active_alerts.map((a) => (
                      <li key={a.id} className="text-sm">
                        <Link href={`/medical?alert=${a.id}&astronaut=${a.astronaut_id}`} className="flex flex-wrap items-center gap-2 hover:underline">
                          <StatusPill status={a.severity as Severity} /> {a.title}
                        </Link>
                        <span className="text-xs text-ink-3">{a.astronaut_id} · {utcDayTime(a.opened_at)} UTC{a.scenario ? " · simulated test" : ""}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
              <Panel title="Historical incidents">
                {!o.incidents_visible ? <p className="text-sm text-ink-2">Your role cannot read incident reports.</p> : o.incidents.length === 0 ? <EmptyState title="No reports in this period" /> : (
                  <ul className="space-y-1.5">
                    {o.incidents.map((r) => (
                      <li key={r.id} className="text-sm"><Link href={`/reports?report=${r.id}`} className="font-medium hover:underline">{r.title}</Link>
                        <span className="block text-xs text-ink-3">{r.astronaut_id} · {utcDayTime(r.occurred_at)} UTC · {r.review_status.replace("_", " ")}</span></li>
                    ))}
                  </ul>
                )}
                {o.runs.length > 0 && <p className="mt-3 text-xs text-ink-2">{o.runs.length} simulated emergency run(s): {o.runs.slice(0, 3).map((r) => r.label).join(", ")}.</p>}
              </Panel>
              <Panel title="Environment" actions={<KindChip kind="indicator" />}>
                {(() => {
                  const env = o.environment as { counts: Record<string, number>; strongest_flare: { classification: string } | null; simulated_dose_msv: number; note: string; window_days: number };
                  return (
                    <div className="space-y-2 text-sm">
                      <p>NASA DONKI, last {env.window_days} d: {env.counts.FLR ?? 0} flares, {env.counts.CME ?? 0} CMEs, {env.counts.SEP ?? 0} SEP, {env.counts.GST ?? 0} storms{env.strongest_flare ? `; strongest ${env.strongest_flare.classification}` : ""}.</p>
                      <p><KindChip kind="simulated" /> Crew dose in period: {fmt(env.simulated_dose_msv, 1)} mSv (all shown crew).</p>
                      <p className="text-xs text-ink-3">{env.note}</p>
                      <Link href="/space/correlation" className="text-xs text-telemetry hover:underline">Explore environment-health correlations</Link>
                    </div>
                  );
                })()}
              </Panel>
            </div>
            <Panel title="Sleep duration" description="Nightly sleep from the digital twin." actions={<KindChip kind="simulated" />}>
              <CrewTrend o={o} metric="sleep_duration_hours" unit="h" label="Sleep duration" decimals={2} />
            </Panel>
            <p className="text-xs text-ink-3">{o.disclaimer}</p>
          </>
        );
      })()}
    </div>
  );
}
