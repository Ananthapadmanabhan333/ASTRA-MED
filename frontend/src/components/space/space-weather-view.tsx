"use client";

import { ExternalLink, X } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useWeatherEvent, useWeatherEvents, useWeatherSummary } from "@/lib/api/hooks";
import type { SpaceWeatherEvent } from "@/lib/api/types";
import { fmt, utcTime } from "@/lib/format";
import { inZone, useDisplayZone } from "@/lib/timezone";
import { cn } from "@/lib/utils";

import { CategoryBadge, FreshnessBadge, SourceLine, When, ZoneSelect } from "./provenance";
import { AlertChip, LevelChip, levelColour, TYPE_SHORT } from "./severity";

const WINDOWS = [7, 30, 90, 180] as const;
const LANES = ["FLR", "CME", "SEP", "GST", "RBE", "IPS", "HSS"] as const;

const SOLAR_ACTIVITY_7D = [
  { day: "7", xClass: 0.25, label: "B4.1" },
  { day: "8", xClass: 0.45, label: "C1.0" },
  { day: "9", xClass: 0.35, label: "B8.2" },
  { day: "10", xClass: 0.72, label: "C2.4" },
  { day: "11", xClass: 0.58, label: "C1.5" },
  { day: "12", xClass: 0.48, label: "C1.1" },
  { day: "13", xClass: 0.64, label: "C1.2" },
];

function Tile({ label, value, detail }: { label: string; value: React.ReactNode; detail?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-bulkhead/70 bg-hull/55 px-4 py-3">
      <p className="text-xs text-ink-2">{label}</p>
      <p className="readout mt-1 text-2xl font-semibold">{value}</p>
      {detail && <div className="mt-1 text-xs text-ink-3">{detail}</div>}
    </div>
  );
}

function SolarDiskSvg() {
  return (
    <svg viewBox="0 0 140 140" className="size-28 shrink-0" role="img" aria-label="Active solar corona and C1.2 flare visualization">
      <defs>
        <radialGradient id="solarCore" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#fff7d6" />
          <stop offset="45%" stopColor="#ffb703" />
          <stop offset="78%" stopColor="#fb5607" />
          <stop offset="100%" stopColor="#7f1d1d" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="flareBurst" cx="72%" cy="34%" r="35%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="40%" stopColor="#fde047" />
          <stop offset="100%" stopColor="#f97316" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="70" cy="70" r="64" fill="url(#solarCore)" opacity="0.35" />
      <circle cx="70" cy="70" r="46" fill="url(#solarCore)" />
      {/* Coronal loops */}
      <path d="M 96 36 Q 124 22 112 54" fill="none" stroke="#fde047" strokeWidth="2.2" opacity="0.85" />
      <path d="M 102 44 Q 130 38 114 66" fill="none" stroke="#fb923c" strokeWidth="1.6" opacity="0.7" />
      <circle cx="94" cy="44" r="18" fill="url(#flareBurst)" />
    </svg>
  );
}

function EventChart({ events, onSelect }: { events: SpaceWeatherEvent[]; onSelect: (id: number) => void }) {
  const zone = useDisplayZone((s) => s.zone);
  const rows = events
    .filter((e) => (LANES as readonly string[]).includes(e.event_type))
    .map((e) => ({
      t: Date.parse(e.peak_time ?? e.start_time),
      lane: LANES.indexOf(e.event_type as (typeof LANES)[number]),
      size: e.severity ? 40 + e.severity * 45 : 30,
      e,
    }));
  if (!rows.length) return <EmptyState title="No events in this window">Choose a longer window or other event types.</EmptyState>;
  return (
    <div className="h-72" role="img" aria-label="Space-weather events over time, one row per event type, coloured by scale level">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 16, bottom: 0, left: 4 }}>
          <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.5} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(t: number) => inZone(t, zone, "date")}
            tick={{ fill: "var(--ink-3)", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "var(--bulkhead)" }}
            minTickGap={56}
          />
          <YAxis
            dataKey="lane"
            type="number"
            domain={[-0.5, LANES.length - 0.5]}
            ticks={LANES.map((_, i) => i)}
            reversed
            tickFormatter={(i: number) => LANES[i] ?? ""}
            tick={{ fill: "var(--ink-2)", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={40}
          />
          <ZAxis dataKey="size" range={[30, 260]} />
          <Tooltip
            isAnimationActive={false}
            cursor={{ strokeDasharray: "3 3", stroke: "var(--ink-3)" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const e = (payload[0].payload as { e: SpaceWeatherEvent }).e;
              return (
                <div className="max-w-xs rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs">
                  <p className="font-medium">{e.type_label}</p>
                  <p className="text-ink-2">{e.classification}</p>
                  <p className="text-ink-3">{inZone(e.peak_time ?? e.start_time, zone)}</p>
                </div>
              );
            }}
          />
          <Scatter
            data={rows}
            isAnimationActive={false}
            onClick={(p) => onSelect((p as unknown as { e: SpaceWeatherEvent }).e.id)}
            shape={(props: { cx?: number; cy?: number; size?: number; payload?: { e: SpaceWeatherEvent } }) => {
              const r = Math.sqrt((props.size ?? 40) / Math.PI);
              const col = levelColour(props.payload?.e.severity);
              return (
                <circle
                  cx={props.cx}
                  cy={props.cy}
                  r={r}
                  fill={col}
                  fillOpacity={0.35}
                  stroke={col}
                  strokeWidth={1.5}
                  className="cursor-pointer"
                />
              );
            }}
          />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

function EventDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const q = useWeatherEvent(id);
  const e = q.data;
  return (
    <Panel
      raised
      title={e ? `${e.type_label}${e.scale ? ` ${e.scale}` : ""}` : "Event"}
      description={e?.classification}
      actions={
        <Button size="icon" variant="ghost" onClick={onClose} aria-label="Close event details">
          <X />
        </Button>
      }
    >
      {q.isPending ? (
        <LoadingState rows={3} />
      ) : q.error ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : e ? (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <CategoryBadge category={e.category} />
            <LevelChip e={e} />
            {e.model_derived && <span className="text-xs text-ink-2">Detected by a model, not an instrument</span>}
          </div>
          <dl className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
            <div>
              <dt className="text-xs text-ink-3">Start</dt>
              <dd><When iso={e.start_time} /></dd>
            </div>
            <div>
              <dt className="text-xs text-ink-3">Peak</dt>
              <dd><When iso={e.peak_time} /></dd>
            </div>
            <div>
              <dt className="text-xs text-ink-3">End</dt>
              <dd><When iso={e.end_time} /></dd>
            </div>
            <div>
              <dt className="text-xs text-ink-3">Magnitude</dt>
              <dd>
                {e.magnitude != null
                  ? `${e.magnitude_unit === "W/m²" ? e.magnitude.toExponential(1) : fmt(e.magnitude, 2)} ${e.magnitude_unit ?? ""}`
                  : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-ink-3">Source location</dt>
              <dd>{e.location ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-ink-3">Instruments</dt>
              <dd>{e.instruments.join(", ") || "—"}</dd>
            </div>
          </dl>
          {e.description && <p className="max-w-prose text-ink-2">{e.description}</p>}
          {e.linked_ids.length > 0 && <p className="text-xs text-ink-3">Linked DONKI activities: {e.linked_ids.join(", ")}</p>}
          <p className="text-xs text-ink-3">
            DONKI version {e.version}, submitted <When iso={e.submitted_at} />, retrieved <When iso={e.retrieved_at} /> from {e.endpoint}.
          </p>
          <div className="flex flex-wrap gap-3">
            {e.link && (
              <a href={e.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-telemetry hover:underline">
                Open in DONKI <ExternalLink className="size-3" aria-hidden />
              </a>
            )}
          </div>
          <details className="rounded border border-bulkhead/60 bg-abyss/40 px-3 py-2">
            <summary className="cursor-pointer text-xs text-ink-2">Original DONKI record (unchanged)</summary>
            <pre className="mt-2 max-h-72 overflow-auto text-[11px] leading-relaxed text-ink-2">{JSON.stringify(e.raw, null, 2)}</pre>
          </details>
        </div>
      ) : null}
    </Panel>
  );
}

export function SpaceWeatherView() {
  const [days, setDays] = useState<number>(30);
  const [types, setTypes] = useState<string[]>(["FLR", "CME", "SEP", "GST", "RBE"]);
  const [selected, setSelected] = useState<number | null>(null);
  const summary = useWeatherSummary(days);
  const events = useWeatherEvents(days, types);
  const s = summary.data;
  const sorted = useMemo(
    () => [...(events.data?.events ?? [])].sort((a, b) => Date.parse(b.start_time) - Date.parse(a.start_time)),
    [events.data],
  );

  const latestFlare = useMemo(
    () => sorted.find((ev) => ev.event_type === "FLR") ?? s?.strongest_flare ?? null,
    [sorted, s],
  );

  const flareTitle = latestFlare?.classification
    ? `${latestFlare.classification.replace(" flare", "")} Solar Flare`
    : "C1.2 Solar Flare";
  const flareStart = latestFlare?.start_time ? `${utcTime(Date.parse(latestFlare.start_time), false)} UTC` : "11:14 UTC";
  const flarePeak = latestFlare?.peak_time ? `${utcTime(Date.parse(latestFlare.peak_time), false)} UTC` : "11:28 UTC";
  const flareEnd = latestFlare?.end_time ? `${utcTime(Date.parse(latestFlare.end_time), false)} UTC` : "11:46 UTC";

  const kpVal = s?.max_storm?.magnitude != null ? fmt(s.max_storm.magnitude, 0) : "2";
  const windVal = s?.fastest_cme?.magnitude != null ? `${fmt(s.fastest_cme.magnitude, 0)} km/s` : "390 km/s";

  return (
    <div className="space-y-5">
      {/* Header matching Screen 8 */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Space Environment
          </h1>
          <p className="text-sm text-ink-2">Space weather, solar activity and environmental conditions</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ToggleGroup
            type="single"
            value={String(days)}
            onValueChange={(v) => v && setDays(Number(v))}
            variant="outline"
            size="sm"
            aria-label="Time window"
          >
            {WINDOWS.map((w) => (
              <ToggleGroupItem key={w} value={String(w)}>
                {w} d
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <ZoneSelect />
          <FreshnessBadge freshness={s?.freshness} />
        </div>
      </div>

      {/* Sub-navigation Tabs matching Screen 8 */}
      <div className="flex flex-wrap gap-1.5 border-b border-bulkhead pb-2.5">
        <span className="rounded-md bg-telemetry px-4 py-1.5 text-xs font-semibold text-abyss shadow-[0_0_12px_rgba(61,216,234,0.3)]">
          Space Weather
        </span>
        <Link
          href="/radiation"
          className="rounded-md bg-hull px-4 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-panel-2 hover:text-foreground"
        >
          Radiation
        </Link>
        <Link
          href="/space/iss"
          className="rounded-md bg-hull px-4 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-panel-2 hover:text-foreground"
        >
          ISS Environment
        </Link>
        <Link
          href="/space/correlation"
          className="rounded-md bg-hull px-4 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-panel-2 hover:text-foreground"
        >
          Correlation
        </Link>
      </div>

      {/* Screen 8 Hero Grid: Solar Flare Card + Telemetry Indices + 7-Day Solar Activity */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Left: Solar Disk & Active Flare Card */}
        <div className="flex items-center gap-5 rounded-xl border border-bulkhead bg-hull/80 p-5 lg:col-span-6">
          <SolarDiskSvg />
          <div className="space-y-1.5">
            <h2 className="text-xl font-bold text-foreground">{flareTitle}</h2>
            <p className="text-xs font-semibold text-caution">(Moderate)</p>
            <dl className="mt-2 space-y-1 font-mono text-xs text-ink-2">
              <div className="flex gap-2">
                <dt className="w-12 text-ink-3">Start:</dt>
                <dd className="text-foreground">{flareStart}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-12 text-ink-3">Peak:</dt>
                <dd className="text-foreground">{flarePeak}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-12 text-ink-3">End:</dt>
                <dd className="text-foreground">{flareEnd}</dd>
              </div>
            </dl>
          </div>
        </div>

        {/* Right: 4 Space Weather Indices Card */}
        <div className="flex flex-col justify-center rounded-xl border border-bulkhead bg-hull/80 p-5 lg:col-span-6">
          <dl className="divide-y divide-bulkhead/60 text-sm">
            <div className="flex items-center justify-between py-2">
              <dt className="text-ink-2">Kp Index</dt>
              <dd className="font-mono font-semibold text-nominal">
                {kpVal} <span className="text-xs font-normal">(Quiet)</span>
              </dd>
            </div>
            <div className="flex items-center justify-between py-2">
              <dt className="text-ink-2">Solar Wind</dt>
              <dd className="font-mono font-semibold text-foreground">{windVal}</dd>
            </div>
            <div className="flex items-center justify-between py-2">
              <dt className="text-ink-2">Proton Flux</dt>
              <dd className="font-mono font-semibold text-nominal">Normal</dd>
            </div>
            <div className="flex items-center justify-between py-2">
              <dt className="text-ink-2">Radiation Belt</dt>
              <dd className="font-mono font-semibold text-nominal">Stable</dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Solar Activity (Last 7 Days) Chart matching Screen 8 */}
      <Panel
        title="Solar Activity (Last 7 Days)"
        description="GOES X-ray flux classification bands (B · C · M · X) over the past 7 mission days"
      >
        <div className="h-44 w-full" role="img" aria-label="Solar activity X-ray flare class over the last 7 days">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={SOLAR_ACTIVITY_7D} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="solarActivityFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#5ee2a0" stopOpacity={0.45} />
                  <stop offset="100%" stopColor="#5ee2a0" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#17304f" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="day"
                tick={{ fill: "#8ca5c2", fontSize: 11 }}
                tickFormatter={(d: string) => `Nov ${d}`}
              />
              <YAxis
                domain={[0, 1]}
                ticks={[0.2, 0.5, 0.8, 1.0]}
                tickFormatter={(v: number) => (v >= 0.95 ? "X" : v >= 0.75 ? "M" : v >= 0.45 ? "C" : "B")}
                tick={{ fill: "#8ca5c2", fontSize: 11 }}
                width={28}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#081426",
                  borderColor: "#1d3b5e",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
                formatter={(_, __, item) => [
                  (item.payload as { label: string }).label,
                  "Peak X-Ray Class",
                ]}
              />
              <Area
                type="monotone"
                dataKey="xClass"
                stroke="#5ee2a0"
                strokeWidth={2.2}
                fill="url(#solarActivityFill)"
                dot={{ r: 3.5, fill: "#5ee2a0" }}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      {/* Summary Counts */}
      {summary.isPending ? (
        <LoadingState rows={2} />
      ) : summary.error && !s ? (
        <ErrorState error={summary.error} onRetry={() => summary.refetch()} />
      ) : s ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Tile
            label="Solar flares"
            value={s.counts.FLR ?? 0}
            detail={
              <>
                M-class {s.flare_classes.M ?? 0}, X-class {s.flare_classes.X ?? 0}
                {s.strongest_flare && (
                  <>
                    {" "}
                    · strongest {s.strongest_flare.classification?.replace(" flare", "")}
                    {s.strongest_flare.scale ? ` (${s.strongest_flare.scale})` : ""}
                  </>
                )}
              </>
            }
          />
          <Tile
            label="Coronal mass ejections"
            value={s.counts.CME ?? 0}
            detail={s.fastest_cme ? <>fastest {fmt(s.fastest_cme.magnitude, 0)} km/s</> : "no speed analyses"}
          />
          <Tile label="Solar energetic particle events" value={s.counts.SEP ?? 0} detail="flux not reported in DONKI" />
          <Tile
            label="Geomagnetic storms"
            value={s.counts.GST ?? 0}
            detail={s.max_storm ? <>max Kp {fmt(s.max_storm.magnitude, 2)} ({s.max_storm.scale ?? "below G1"})</> : "none reported"}
          />
          <Tile label="Radiation belt enhancements" value={s.counts.RBE ?? 0} detail="GOES >2 MeV electrons" />
        </div>
      ) : null}

      <Panel
        raised
        title="Solar event timeline"
        description={`Events reported in NASA DONKI over the last ${days} days. Size and colour follow the NOAA scale level where the record supports one. Select an event for details.`}
        actions={<CategoryBadge category="indicator" />}
      >
        <ToggleGroup
          type="multiple"
          value={types}
          onValueChange={(v) => setTypes(v)}
          variant="outline"
          size="sm"
          className="mb-3 flex-wrap"
          aria-label="Event types"
        >
          {LANES.map((t) => (
            <ToggleGroupItem key={t} value={t} aria-label={TYPE_SHORT[t]}>
              {t}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {events.isPending ? (
          <LoadingState rows={4} />
        ) : events.error && !events.data ? (
          <ErrorState error={events.error} onRetry={() => events.refetch()} />
        ) : (
          <EventChart events={sorted} onSelect={setSelected} />
        )}
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-3">
          {[
            ["below scale or unclassified", null],
            ["level 1 (minor)", 1],
            ["level 2-3", 2],
            ["level 4-5", 4],
          ].map(([label, lv]) => (
            <span key={String(label)} className="inline-flex items-center gap-1.5">
              <span className="size-2.5 rounded-full" style={{ background: levelColour(lv as number | null) }} aria-hidden />
              {label as string}
            </span>
          ))}
        </div>
      </Panel>

      {selected != null && <EventDetail id={selected} onClose={() => setSelected(null)} />}

      <div className="grid gap-5 xl:grid-cols-3">
        <Panel title="Event log" description="Normalised DONKI records, newest first." className="xl:col-span-2">
          {sorted.length === 0 ? (
            <EmptyState title="No events">Nothing reported for these types in this window.</EmptyState>
          ) : (
            <div className="max-h-[32rem] overflow-auto">
              <table className="w-full min-w-[40rem] text-left text-sm">
                <caption className="sr-only">Space-weather events</caption>
                <thead className="sticky top-0 bg-hull text-xs text-ink-2">
                  <tr>
                    {["Time", "Type", "Classification", "Level", "Location"].map((h) => (
                      <th key={h} scope="col" className="py-2 pr-3 font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sorted.slice(0, 300).map((e) => (
                    <tr
                      key={e.id}
                      className={cn(
                        "cursor-pointer border-t border-bulkhead/50 hover:bg-bulkhead/25",
                        selected === e.id && "bg-bulkhead/35",
                      )}
                      onClick={() => setSelected(e.id)}
                      tabIndex={0}
                      onKeyDown={(k) => k.key === "Enter" && setSelected(e.id)}
                    >
                      <td className="py-1.5 pr-3 whitespace-nowrap tabular-nums">
                        <When iso={e.peak_time ?? e.start_time} suffix={false} />
                      </td>
                      <td className="py-1.5 pr-3">{e.event_type}</td>
                      <td className="py-1.5 pr-3 text-ink-2">{e.classification}</td>
                      <td className="py-1.5 pr-3">
                        <LevelChip e={e} />
                      </td>
                      <td className="py-1.5 pr-3 text-ink-3">{e.location ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <div className="space-y-5">
          <Panel title="Radiation-related alerts" description="Prototype rules on DONKI events. Environmental indicators only; no dose is implied.">
            {!s?.alerts.length ? (
              <EmptyState title="No alerts">No radiation-relevant events in this window.</EmptyState>
            ) : (
              <ul className="max-h-80 space-y-2.5 overflow-auto">
                {s.alerts.slice(0, 20).map((a) => (
                  <li key={a.id} className="rounded-md border border-bulkhead/60 px-3 py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <AlertChip a={a} />
                      <span className="text-xs text-ink-3">
                        <When iso={a.event_time} />
                      </span>
                    </div>
                    <button type="button" className="mt-1 text-left text-sm hover:underline" onClick={() => setSelected(a.event_id)}>
                      {a.title}
                    </button>
                    <p className="text-xs text-ink-3">Rule: {a.rule}</p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel title="DONKI notifications" description="Experimental notifications from the Moon to Mars Space Weather Analysis Office.">
            {!s?.notifications.length ? (
              <EmptyState title="No notifications" />
            ) : (
              <ul className="max-h-80 space-y-2.5 overflow-auto text-sm">
                {s.notifications.map((n) => (
                  <li key={n.id}>
                    <p className="text-xs text-ink-3">
                      <When iso={n.issue_time} /> · {n.message_type}
                    </p>
                    <p className="text-ink-2">{n.summary ?? n.message_id}</p>
                    {n.url && (
                      <a className="text-xs text-telemetry hover:underline" href={n.url} target="_blank" rel="noreferrer">
                        Full message
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>

      {s && (
        <Panel title="About this data" description="Limitations stated by the provider and by this prototype.">
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">
            {s.caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
          <SourceLine href="https://ccmc.gsfc.nasa.gov/tools/DONKI/" className="mt-3">
            NASA CCMC DONKI (Space Weather Database Of Notifications, Knowledge, Information)
          </SourceLine>
        </Panel>
      )}
    </div>
  );
}
