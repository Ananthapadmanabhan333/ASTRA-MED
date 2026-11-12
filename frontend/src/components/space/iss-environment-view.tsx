"use client";

import { History } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useIssMission, useIssMissions } from "@/lib/api/hooks";
import type { EnvMissionDetail, EnvSeries } from "@/lib/api/types";
import { fmt } from "@/lib/format";
import { inZone, useDisplayZone } from "@/lib/timezone";

import { CategoryBadge, FreshnessBadge, SourceLine, When, ZoneSelect } from "./provenance";
import { LevelChip } from "./severity";

const TELEMETRY = [
  { q: "temperature_c", title: "Cabin temperature", digits: 1 },
  { q: "humidity_pct", title: "Relative humidity", digits: 0 },
  { q: "co2_ppm", title: "CO₂ concentration", digits: 0 },
] as const;

function TelemetryChart({ detail, quantity, digits }: { detail: EnvMissionDetail; quantity: string; digits: number }) {
  const zone = useDisplayZone((s) => s.zone);
  const iss = detail.series.find((s) => s.quantity === quantity && s.platform === "iss");
  const ground = detail.series.find((s) => s.quantity === quantity && s.platform === "ground");
  const rows = useMemo(() => {
    const map = new Map<number, { t: number; iss?: number; ground?: number }>();
    for (const [key, s] of [["iss", iss], ["ground", ground]] as const) {
      for (const p of s?.points ?? []) {
        const t = Date.parse(p.ts);
        const row = map.get(t) ?? { t };
        row[key] = p.value;
        map.set(t, row);
      }
    }
    return [...map.values()].sort((a, b) => a.t - b.t);
  }, [iss, ground]);
  if (!iss) return <EmptyState title="Not recorded for this mission" />;
  return (
    <div className="h-56" role="img" aria-label={`${iss.label}: ISS and ground-control values over the mission`}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.5} vertical={false} />
          <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t: number) => inZone(t, zone, "date")}
            tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--bulkhead)" }} minTickGap={56} />
          <YAxis domain={["auto", "auto"]} tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={false} width={48}
            tickFormatter={(v: number) => fmt(v, digits)} />
          {detail.mission.milestones.map((m) => (
            <ReferenceLine key={m.time + m.label} x={Date.parse(m.time)} stroke="var(--ink-3)" strokeDasharray="2 4" strokeOpacity={0.6} />
          ))}
          <Line dataKey="iss" name="ISS" stroke="var(--telemetry)" strokeWidth={1.6} dot={false} isAnimationActive={false} connectNulls={false} />
          <Line dataKey="ground" name="Ground control" stroke="var(--ink-3)" strokeWidth={1.2} dot={false} isAnimationActive={false} connectNulls={false} />
          <Tooltip
            isAnimationActive={false}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const r = payload[0].payload as (typeof rows)[number];
              return (
                <div className="rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs">
                  <p className="text-ink-2">{inZone(Number(label), zone)}</p>
                  <p>ISS {fmt(r.iss, digits)} {iss.unit}</p>
                  {r.ground != null && <p className="text-ink-3">Ground {fmt(r.ground, digits)} {iss.unit}</p>}
                </div>
              );
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function DoseChart({ detail }: { detail: EnvMissionDetail }) {
  const zone = useDisplayZone((s) => s.zone);
  const gcr = detail.series.find((s) => s.quantity === "dose_gcr_mgy_day");
  const saa = detail.series.find((s) => s.quantity === "dose_saa_mgy_day");
  const rows = useMemo(() => {
    // Events go on the same daily grid as the bars: separate scatter data with minute-level
    // timestamps would shrink Recharts' band width and collapse the bars to hairlines.
    const byDay = new Map<string, EnvMissionDetail["space_weather"]>();
    for (const e of detail.space_weather) {
      if (!["SEP", "FLR", "GST", "RBE"].includes(e.event_type) || (e.event_type === "FLR" && (e.severity ?? 0) < 1)) continue;
      const day = (e.peak_time ?? e.start_time).slice(0, 10);
      byDay.set(day, [...(byDay.get(day) ?? []), e]);
    }
    return (gcr?.points ?? []).map((p, i) => {
      const day = p.ts.slice(0, 10);
      return {
        t: Date.parse(p.ts) + 12 * 3_600_000,
        gcr: p.value,
        saa: saa?.points[i]?.value ?? null,
        approximate: p.approximate,
        events: byDay.get(day) ?? [],
      };
    });
  }, [gcr, saa, detail.space_weather]);
  const top = Math.max(0.3, ...rows.map((r) => (r.gcr ?? 0) + (r.saa ?? 0))) * 1.15;
  const data = rows.map((r) => ({ ...r, marker: r.events.length ? top * 0.95 : null }));
  if (!gcr) return <EmptyState title="No dosimetry for this mission" />;
  return (
    <div className="h-64" role="img" aria-label="Daily absorbed dose split into GCR and SAA, with days of space-weather events marked">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} barCategoryGap="15%">
          <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.5} vertical={false} />
          <XAxis dataKey="t" type="number" scale="time" domain={[(rows[0]?.t ?? 0) - 86_400_000, (rows.at(-1)?.t ?? 0) + 86_400_000]}
            tickFormatter={(t: number) => inZone(t, zone, "date")} tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false}
            axisLine={{ stroke: "var(--bulkhead)" }} minTickGap={56} />
          <YAxis domain={[0, Number(top.toFixed(2))]} tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={false} width={48}
            tickFormatter={(v: number) => fmt(v, 2)} label={{ value: "mGy/day", angle: -90, position: "insideLeft", fill: "var(--ink-3)", fontSize: 11 }} />
          <Bar dataKey="gcr" stackId="d" name="GCR" fill="var(--telemetry)" isAnimationActive={false}
            shape={(p: { x?: number; y?: number; width?: number; height?: number; payload?: { approximate: boolean } }) => (
              <rect x={p.x} y={p.y} width={p.width} height={p.height} fill="var(--telemetry)" fillOpacity={p.payload?.approximate ? 0.35 : 0.85} />
            )} />
          <Bar dataKey="saa" stackId="d" name="SAA" fill="var(--chart-3)" isAnimationActive={false}
            shape={(p: { x?: number; y?: number; width?: number; height?: number; payload?: { approximate: boolean } }) => (
              <rect x={p.x} y={p.y} width={p.width} height={p.height} fill="var(--chart-3)" fillOpacity={p.payload?.approximate ? 0.35 : 0.85} />
            )} />
          <Scatter dataKey="marker" fill="var(--advisory)" shape="diamond" isAnimationActive={false} />
          <Tooltip
            isAnimationActive={false}
            cursor={{ fill: "var(--bulkhead)", fillOpacity: 0.25 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const r = payload[0].payload as (typeof data)[number];
              return (
                <div className="max-w-xs rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs">
                  <p className="text-ink-2">{inZone(r.t, zone, "date")}{r.approximate ? " · approximate (launch vehicle)" : ""}</p>
                  <p>GCR {fmt(r.gcr, 3)} mGy/day</p>
                  <p>SAA {fmt(r.saa, 3)} mGy/day</p>
                  {r.events.length > 0 && (
                    <p className="mt-1 text-ink-3">
                      DONKI that day: {r.events.map((e) => `${e.event_type}${e.scale ? ` ${e.scale}` : ""}`).join(", ")} (indicators, no dose implied)
                    </p>
                  )}
                </div>
              );
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function QualityTable({ series }: { series: EnvSeries[] }) {
  const rows = series.filter((s) => s.quality).sort((a, b) => a.quantity.localeCompare(b.quantity) || a.platform.localeCompare(b.platform));
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[46rem] text-left text-sm">
        <caption className="sr-only">Data quality per series</caption>
        <thead className="text-xs text-ink-2">
          <tr>{["Series", "Platform", "Unit", "Raw points", "Completeness", "Out of range", "Duplicates", "Gaps", "Sampling", "Approx."].map((h) => <th key={h} scope="col" className="py-2 pr-3 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody className="tabular-nums">
          {rows.map((s) => {
            const q = s.quality!;
            return (
              <tr key={s.quantity + s.platform} className="border-t border-bulkhead/50">
                <td className="py-1.5 pr-3">{s.label}</td>
                <td className="py-1.5 pr-3 uppercase text-ink-2">{s.platform}</td>
                <td className="py-1.5 pr-3 text-ink-2">{s.unit}</td>
                <td className="py-1.5 pr-3">{q.raw_points.toLocaleString()}</td>
                <td className="py-1.5 pr-3">{fmt(q.completeness * 100, 1)}%</td>
                <td className={q.out_of_range ? "py-1.5 pr-3 text-caution" : "py-1.5 pr-3"}>{q.out_of_range}</td>
                <td className={q.duplicates ? "py-1.5 pr-3 text-caution" : "py-1.5 pr-3"}>{q.duplicates}</td>
                <td className="py-1.5 pr-3">{q.gaps}{q.gaps ? ` (max ${fmt(q.longest_gap_hours, 1)} h)` : ""}</td>
                <td className="py-1.5 pr-3 text-ink-2">{q.median_interval_min != null ? (q.median_interval_min >= 1440 ? "daily" : `${fmt(q.median_interval_min, 0)} min`) : "—"}</td>
                <td className="py-1.5 pr-3">{q.approximate_points || "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function IssEnvironmentView() {
  const missions = useIssMissions();
  const withData = (missions.data ?? []).filter((m) => m.has_telemetry || m.has_radiation);
  const [chosen, setName] = useState<string | null>(null);
  const [resolution, setResolution] = useState<"1h" | "6h" | "1d">("6h");
  const name = chosen ?? withData[0]?.name ?? null;  // default: first mission with data
  const q = useIssMission(name, resolution);
  const d = q.data;

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3 rounded-lg border border-dashed border-telemetry/50 bg-telemetry/5 px-4 py-3 text-sm">
        <History className="mt-0.5 size-5 shrink-0 text-telemetry" aria-hidden />
        <p className="text-ink-2">
          <span className="font-medium text-foreground">Historical measurements, not live ISS telemetry.</span> These values were
          recorded in the ISS cabin and in ground-control habitats during specific past missions (2014 onward) and published
          through NASA&apos;s Open Science Data Repository. Radiation values are absorbed dose at the experiment location, not
          any astronaut&apos;s dose.
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          {missions.isPending ? (
            <LoadingState rows={1} className="w-56" />
          ) : (
            <Select value={name ?? undefined} onValueChange={setName}>
              <SelectTrigger className="w-72" aria-label="ISS mission">
                <SelectValue placeholder={withData.length ? "Choose a mission" : "No mission data yet"} />
              </SelectTrigger>
              <SelectContent>
                {(missions.data ?? []).map((m) => (
                  <SelectItem key={m.name} value={m.name} disabled={!m.has_telemetry && !m.has_radiation}>
                    {m.name}: {m.title}
                    {m.start_time
                      ? ` (${inZone(m.start_time, "UTC", "date").slice(-4)})`
                      : m.telemetry_synced_at || m.radiation_synced_at
                        ? " (no usable data published)"
                        : " (not synchronised yet)"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <ToggleGroup type="single" value={resolution} onValueChange={(v) => v && setResolution(v as typeof resolution)} variant="outline" size="sm" aria-label="Telemetry resolution">
            <ToggleGroupItem value="1h">Hourly</ToggleGroupItem>
            <ToggleGroupItem value="6h">6 h</ToggleGroupItem>
            <ToggleGroupItem value="1d">Daily</ToggleGroupItem>
          </ToggleGroup>
          <ZoneSelect />
        </div>
        <FreshnessBadge freshness={d?.freshness} />
      </div>

      {!name ? (
        missions.isPending ? null : <EmptyState title="No ISS environment data stored yet">The EDA synchronisation runs in the background; missions appear here as they are ingested.</EmptyState>
      ) : q.isPending ? (
        <LoadingState rows={6} />
      ) : q.error && !d ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : d ? (
        <>
          <Panel
            raised
            title={`${d.mission.name}: ${d.mission.title}`}
            description={<>Mission data from <When iso={d.mission.start_time} kind="date" /> to <When iso={d.mission.end_time} kind="date" />. Dashed lines mark mission milestones.</>}
            actions={<CategoryBadge category="measured" />}
          >
            <div className="flex flex-wrap gap-2 text-xs text-ink-3">
              {d.mission.milestones.map((m) => (
                <span key={m.time + m.label} className="rounded border border-bulkhead/60 px-2 py-0.5">
                  {m.label}: <When iso={m.time} kind="date" />
                </span>
              ))}
            </div>
          </Panel>

          <div className="grid gap-5 xl:grid-cols-3">
            {TELEMETRY.map((t) => {
              const s = d.series.find((x) => x.quantity === t.q && x.platform === "iss");
              return (
                <Panel key={t.q} title={t.title} description={s ? `${s.unit}, ISS (blue) and ground control (grey), ${s.resolution} means` : undefined}>
                  <TelemetryChart detail={d} quantity={t.q} digits={t.digits} />
                </Panel>
              );
            })}
          </div>

          <Panel
            title="Daily absorbed dose"
            description="GCR and SAA components, mGy/day in water. Faded bars are launch-vehicle days that EDA approximates from US Lab averages. Diamonds mark days with radiation-relevant DONKI events (SEP, R1+ flares, storms, radiation belt); indicators only, no dose implied."
            actions={<CategoryBadge category="measured" />}
          >
            <DoseChart detail={d} />
            {d.space_weather.length > 0 && (
              <details className="mt-3">
                <summary className="cursor-pointer text-xs text-ink-2">{d.space_weather.length} DONKI events during this mission</summary>
                <ul className="mt-2 grid max-h-56 gap-1.5 overflow-auto text-xs sm:grid-cols-2">
                  {d.space_weather.map((e) => (
                    <li key={e.id} className="flex items-center gap-2">
                      <span className="w-28 shrink-0 text-ink-3"><When iso={e.peak_time ?? e.start_time} suffix={false} /></span>
                      <span>{e.event_type}</span>
                      <LevelChip e={e} />
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </Panel>

          <div className="grid gap-5 xl:grid-cols-3">
            <Panel title="Data quality" description="Checks run on the raw records before aggregation." className="xl:col-span-2">
              <QualityTable series={d.series} />
            </Panel>
            <Panel title="Related OSDR studies" description="Studies whose project or title refers to this mission.">
              {!d.studies.length ? (
                <EmptyState title="No linked studies stored" />
              ) : (
                <ul className="max-h-72 space-y-2 overflow-auto text-sm">
                  {d.studies.map((s) => (
                    <li key={s.accession}>
                      <a href={s.link} target="_blank" rel="noreferrer" className="text-telemetry hover:underline">{s.accession}</a>{" "}
                      <span className="text-ink-2">{s.title}</span>
                      <p className="text-xs text-ink-3">{[s.organism, s.assay_type].filter(Boolean).join(" · ")}</p>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>

          <Panel title="About this data">
            <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">
              {d.caveats.map((c) => <li key={c}>{c}</li>)}
            </ul>
            <SourceLine href="https://visualization.osdr.nasa.gov/eda/" className="mt-3">NASA OSDR Environmental Data App</SourceLine>
          </Panel>
        </>
      ) : null}
    </div>
  );
}
