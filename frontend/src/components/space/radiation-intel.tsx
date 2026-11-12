"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useSpaceRadiation } from "@/lib/api/hooks";
import type { RadiationIntel } from "@/lib/api/types";
import { fmt } from "@/lib/format";
import { inZone, useDisplayZone } from "@/lib/timezone";

import { CategoryBadge, FreshnessBadge, SourceLine, When } from "./provenance";
import { AlertChip, LevelChip } from "./severity";

function CategoryCard({ letter, title, badge, children }: {
  letter: string; title: string; badge: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col rounded-lg border border-bulkhead/70 bg-hull/55 p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="font-heading text-base font-semibold">
          <span className="mr-1.5 text-ink-3">{letter}.</span>
          {title}
        </p>
        {badge}
      </div>
      <div className="mt-2 flex-1 space-y-2 text-sm text-ink-2">{children}</div>
    </div>
  );
}

function Categories({ data }: { data: RadiationIntel }) {
  const m = data.measured.missions;
  const latest = m.length ? m[m.length - 1] : null;
  const crewMean = data.simulated.crew.length
    ? data.simulated.crew.reduce((acc, c) => acc + c.dose_rate_msv_day, 0) / data.simulated.crew.length
    : null;
  return (
    <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
      <CategoryCard letter="A" title="Measured dose" badge={<CategoryBadge category="measured" />}>
        <p>
          <span className="readout text-xl text-foreground">{m.length}</span> historical ISS missions with dosimetry
          {latest?.mean_total_mgy_day != null && (
            <>; latest ({latest.mission}) averaged <span className="text-foreground">{fmt(latest.mean_total_mgy_day, 3)} mGy/day</span></>
          )}
          .
        </p>
        <p className="text-xs text-ink-3">{data.measured.description}</p>
      </CategoryCard>
      <CategoryCard letter="B" title="Environmental indicators" badge={<CategoryBadge category="indicator" />}>
        <p>
          Last {data.indicators.window_days} days: <span className="text-foreground">{data.indicators.sep_events}</span> SEP events,{" "}
          <span className="text-foreground">{data.indicators.flares_r1_plus}</span> flares at R1+,{" "}
          <span className="text-foreground">{data.indicators.radiation_belt_enhancements}</span> radiation belt enhancements,{" "}
          <span className="text-foreground">{data.indicators.storms_g1_plus}</span> storms at G1+.
        </p>
        <p className="text-xs text-ink-3">{data.indicators.description}</p>
      </CategoryCard>
      <CategoryCard letter="C" title="Estimated exposure" badge={<CategoryBadge category="estimate" />}>
        <p>
          <span className="readout text-xl text-foreground">{fmt(data.estimate.mission_to_date_msv, 0)}</span> mSv over{" "}
          {data.estimate.mission_days} mission days at {fmt(data.estimate.rate_msv_day, 2)} mSv/day.
        </p>
        <p className="text-xs text-ink-3">{data.estimate.description}</p>
      </CategoryCard>
      <CategoryCard letter="D" title="Simulated scenarios" badge={<CategoryBadge category="simulated" />}>
        <p>
          Crew mean habitat rate now <span className="text-foreground">{fmt(crewMean, 2)} mSv/day</span>, including simulated
          solar particle event scenarios.
        </p>
        <p className="text-xs text-ink-3">{data.simulated.description}</p>
      </CategoryCard>
    </div>
  );
}

function ExposureTimeline({ data }: { data: RadiationIntel }) {
  const zone = useDisplayZone((s) => s.zone);
  const rows = data.timeline.map((d) => {
    const events = Object.values(d.indicator_events).reduce((a, b) => a + b, 0);
    return {
      t: Date.parse(`${d.day}T12:00:00Z`),
      estimate: d.estimate_msv,
      simulated: d.simulated_crew_mean_msv,
      marker: events ? 0.2 : null,
      events: d.indicator_events,
      spe: d.simulated_spe,
    };
  });
  const top = Math.max(2.5, ...rows.map((r) => r.simulated ?? 0)) * 1.1;
  return (
    <div className="h-72" role="img" aria-label="Daily estimated and simulated crew dose with DONKI event days marked">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.5} vertical={false} />
          <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t: number) => inZone(t, zone, "date")}
            tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--bulkhead)" }} minTickGap={56} />
          <YAxis domain={[0, Math.ceil(top)]} tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={false} width={40}
            label={{ value: "mSv/day", angle: -90, position: "insideLeft", fill: "var(--ink-3)", fontSize: 11 }} />
          <Line dataKey="estimate" name="C. Estimate" stroke="var(--nominal)" strokeDasharray="5 4" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line dataKey="simulated" name="D. Simulated crew mean" stroke="var(--caution)" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
          <Scatter dataKey="marker" name="B. DONKI events" fill="var(--advisory)" shape="diamond" isAnimationActive={false} />
          <Tooltip
            isAnimationActive={false}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const r = payload[0].payload as (typeof rows)[number];
              const ev = Object.entries(r.events);
              return (
                <div className="max-w-xs rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs">
                  <p className="text-ink-2">{inZone(r.t, zone, "date")}</p>
                  <p>C. Estimate {fmt(r.estimate, 2)} mSv</p>
                  <p>D. Simulated crew mean {fmt(r.simulated, 2)} mSv{r.spe ? " (simulated SPE)" : ""}</p>
                  <p className="text-ink-3">B. DONKI: {ev.length ? ev.map(([k, v]) => `${v} ${k}`).join(", ") : "none"} (no dose implied)</p>
                </div>
              );
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function MeasuredHistory({ data }: { data: RadiationIntel }) {
  const zone = useDisplayZone((s) => s.zone);
  const rows = data.measured.missions
    .filter((m) => m.mean_total_mgy_day != null)
    .map((m) => ({ name: `${m.mission} (${m.start.slice(0, 4)})`, gcr: m.mean_gcr_mgy_day, saa: m.mean_saa_mgy_day, start: m.start }));
  if (!rows.length) return <EmptyState title="No ISS dosimetry stored yet">The EDA synchronisation fetches it in the background.</EmptyState>;
  return (
    <div className="h-72" role="img" aria-label="Mean daily absorbed dose per historical ISS mission, split into GCR and SAA">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.5} vertical={false} />
          <XAxis dataKey="name" tick={{ fill: "var(--ink-2)", fontSize: 10 }} tickLine={false} axisLine={{ stroke: "var(--bulkhead)" }} interval={0} angle={-35} textAnchor="end" height={64} />
          <YAxis domain={[0, "auto"]} tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={false} width={44}
            label={{ value: "mGy/day", angle: -90, position: "insideLeft", fill: "var(--ink-3)", fontSize: 11 }} />
          <Bar dataKey="gcr" name="Galactic cosmic rays" stackId="d" fill="var(--telemetry)" isAnimationActive={false} />
          <Bar dataKey="saa" name="South Atlantic Anomaly" stackId="d" fill="var(--chart-3)" isAnimationActive={false} />
          <Tooltip
            isAnimationActive={false}
            cursor={{ fill: "var(--bulkhead)", fillOpacity: 0.3 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const r = payload[0].payload as (typeof rows)[number];
              return (
                <div className="rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs">
                  <p className="font-medium">{r.name} · {inZone(r.start, zone, "date")}</p>
                  <p>GCR {fmt(r.gcr, 3)} mGy/day</p>
                  <p>SAA {fmt(r.saa, 3)} mGy/day</p>
                </div>
              );
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RadiationIntelligence() {
  const [days, setDays] = useState(30);
  const q = useSpaceRadiation(days);
  const data = q.data;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-heading text-xl font-semibold">Radiation intelligence</h2>
          <p className="max-w-3xl text-sm text-ink-2">
            Four kinds of radiation information, kept apart. A solar flare or particle event is never turned into a dose,
            and absorbed dose (mGy) is never added to dose equivalent (mSv).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <ToggleGroup type="single" value={String(days)} onValueChange={(v) => v && setDays(Number(v))} variant="outline" size="sm" aria-label="Window">
            {[7, 30, 90].map((d) => <ToggleGroupItem key={d} value={String(d)}>{d} d</ToggleGroupItem>)}
          </ToggleGroup>
          {data?.freshness.map((f) => <FreshnessBadge key={f.source_id} freshness={f} />)}
        </div>
      </div>
      {q.isPending ? (
        <LoadingState rows={4} />
      ) : q.error && !data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : data ? (
        <>
          <Categories data={data} />
          <div className="grid gap-5 xl:grid-cols-2">
            <Panel raised title="Mission exposure timeline"
              description="Fictional mission days: the cruise estimate (C) and simulated crew dose (D) in mSv, with days of radiation-relevant DONKI events (B) marked. Event markers carry no dose.">
              <ExposureTimeline data={data} />
            </Panel>
            <Panel title="Measured dose on historical ISS missions"
              description="Mean daily absorbed dose in water by mission and launch year (EDA), measured days only. For context: galactic cosmic-ray intensity is known to vary inversely with solar activity; this chart is not an analysis of that effect.">
              <MeasuredHistory data={data} />
              <SourceLine href="https://visualization.osdr.nasa.gov/eda/" className="mt-2">NASA OSDR Environmental Data App (preliminary SRAG analysis)</SourceLine>
            </Panel>
          </div>
          <Panel title="Radiation-related alerts" description="Generated from DONKI events by prototype rules; each is an environmental indicator.">
            {!data.alerts.length ? (
              <EmptyState title="No alerts in this window" />
            ) : (
              <ul className="grid gap-2.5 md:grid-cols-2">
                {data.alerts.slice(0, 12).map((a) => {
                  const e = data.indicators.events.find((x) => x.id === a.event_id);
                  return (
                    <li key={a.id} className="rounded-md border border-bulkhead/60 px-3 py-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <AlertChip a={a} />
                        <span className="text-xs text-ink-3"><When iso={a.event_time} /></span>
                      </div>
                      <p className="mt-1 text-sm">{a.title}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        {e && <LevelChip e={e} />}
                        <span className="text-xs text-ink-3">{a.rule}</span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-ink-3">
              {data.rules.map((r) => <li key={r}>{r}</li>)}
            </ul>
          </Panel>
        </>
      ) : null}
    </div>
  );
}
