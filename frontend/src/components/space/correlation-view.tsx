"use client";

import { Play, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useCorrelation, useCorrelationMatrix, useCorrelationSeries } from "@/lib/api/hooks";
import type { CorrelationResult, CorrelationSeriesInfo, MatrixResult } from "@/lib/api/types";
import { fmt } from "@/lib/format";
import { inZone, useDisplayZone } from "@/lib/timezone";
import { type Range, suggestPeriod } from "@/lib/periods";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

import { CategoryBadge } from "./provenance";

const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);

function SeriesPicker({ series, value, onChange, label }: {
  series: CorrelationSeriesInfo[]; value: string; onChange: (v: string) => void; label: string;
}) {
  const groups = useMemo(() => {
    const m = new Map<string, CorrelationSeriesInfo[]>();
    for (const s of series) m.set(s.group, [...(m.get(s.group) ?? []), s]);
    return [...m.entries()];
  }, [series]);
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-full" aria-label={label}><SelectValue placeholder={label} /></SelectTrigger>
      <SelectContent className="max-h-96">
        {groups.map(([g, items]) => (
          <SelectGroup key={g}>
            <SelectLabel>{g}</SelectLabel>
            {items.map((s) => <SelectItem key={s.id} value={s.id}>{s.label} ({s.unit})</SelectItem>)}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-bulkhead/70 bg-hull/55 px-4 py-3">
      <p className="text-xs text-ink-2">{label}</p>
      <p className="readout mt-1 text-2xl font-semibold">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-ink-3">{sub}</p>}
    </div>
  );
}

const p = (v: number | null | undefined) => (v == null ? "—" : v < 0.001 ? "< 0.001" : fmt(v, 3));

function ResultView({ r }: { r: CorrelationResult }) {
  const zone = useDisplayZone((s) => s.zone);
  if (r.status !== "ok") {
    return (
      <div className="space-y-3">
        <EmptyState title="Not enough overlapping data">{r.interpretation}</EmptyState>
        <Warnings items={r.warnings} />
      </div>
    );
  }
  const lags = r.lags.map((l) => ({ ...l, sig: l.q != null && l.q < 0.05 }));
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Pearson r (95% CI)" value={fmt(r.pearson?.r, 2)} sub={`[${fmt(r.pearson?.ci[0], 2)}, ${fmt(r.pearson?.ci[1], 2)}] · p ${p(r.pearson?.p)}`} />
        <Stat label="Spearman ρ (95% CI)" value={fmt(r.spearman?.r, 2)} sub={`[${fmt(r.spearman?.ci[0], 2)}, ${fmt(r.spearman?.ci[1], 2)}] · p ${p(r.spearman?.p)}`} />
        <Stat label="Days paired / effective n" value={`${r.n} / ${fmt(r.n_eff, 0)}`} sub={`lag-1 autocorrelation ${fmt(r.lag1_autocorr_x, 2)} and ${fmt(r.lag1_autocorr_y, 2)}`} />
        <Stat label="Trend-adjusted r" value={fmt(r.trend_adjusted?.r, 2)} sub={r.trend_adjusted ? `p ${p(r.trend_adjusted.p)} after removing a linear trend` : "not computable"} />
      </div>
      <p className="max-w-4xl text-sm text-foreground">{r.interpretation}</p>
      <Warnings items={r.warnings} />
      <div className="grid gap-5 xl:grid-cols-3">
        <Panel title="Scatter" description={`${r.x.label} (x) against ${r.y.label} (y), one point per day.`}>
          <div className="h-60" role="img" aria-label="Scatter of daily paired values">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 6, right: 8, bottom: 4, left: 0 }}>
                <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.45} />
                <XAxis dataKey="x" type="number" domain={["auto", "auto"]} tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} name={r.x.label ?? "x"} />
                <YAxis dataKey="y" type="number" domain={["auto", "auto"]} tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} width={44} name={r.y.label ?? "y"} />
                <Scatter data={r.scatter} fill="var(--telemetry)" fillOpacity={0.6} isAnimationActive={false} />
                <Tooltip isAnimationActive={false} content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0].payload as { ts: string; x: number; y: number };
                  return <div className="rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs"><p className="text-ink-2">{inZone(d.ts, zone, "date")}</p><p>x {fmt(d.x, 3)} · y {fmt(d.y, 3)}</p></div>;
                }} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel title="Time-lagged correlation" description="Positive lag: y follows x by that many days. Bright bars pass q < 0.05 (Benjamini-Hochberg).">
          <div className="h-60" role="img" aria-label="Correlation by lag in days">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={lags} margin={{ top: 6, right: 8, bottom: 4, left: 0 }}>
                <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.45} vertical={false} />
                <XAxis dataKey="lag_days" tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} />
                <YAxis domain={[-1, 1]} tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} width={32} />
                <ReferenceLine y={0} stroke="var(--ink-3)" />
                <Bar dataKey="r" isAnimationActive={false}>
                  {lags.map((l) => <Cell key={l.lag_days} fill="var(--telemetry)" fillOpacity={l.sig ? 0.95 : 0.3} />)}
                </Bar>
                <Tooltip isAnimationActive={false} cursor={{ fill: "var(--bulkhead)", fillOpacity: 0.25 }} content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const l = payload[0].payload as (typeof lags)[number];
                  return <div className="rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs"><p>Lag {l.lag_days} d · r {fmt(l.r, 2)} · n {l.n}</p><p className="text-ink-3">p {p(l.p)} · q {p(l.q)}</p></div>;
                }} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel title={`Rolling correlation (${r.rolling_window} days)`} description="How the same-day association changes over the period.">
          {r.rolling.length ? (
            <div className="h-60" role="img" aria-label="Rolling correlation over time">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={r.rolling.map((x) => ({ t: Date.parse(x.ts), r: x.r }))} margin={{ top: 6, right: 8, bottom: 4, left: 0 }}>
                  <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.45} vertical={false} />
                  <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t: number) => inZone(t, zone, "date")} tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} minTickGap={48} />
                  <YAxis domain={[-1, 1]} tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} width={32} />
                  <ReferenceLine y={0} stroke="var(--ink-3)" />
                  <Line dataKey="r" stroke="var(--telemetry)" strokeWidth={1.8} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState title="Period too short for a rolling window" />
          )}
        </Panel>
      </div>
    </div>
  );
}

function Warnings({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <ul className="space-y-1.5 rounded-lg border border-caution/40 bg-caution/5 px-4 py-3 text-sm">
      {items.map((w) => (
        <li key={w} className="flex gap-2 text-ink-2">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-caution" aria-hidden />
          {w}
        </li>
      ))}
    </ul>
  );
}

function colourFor(r: number | null): string {
  if (r == null) return "transparent";
  const a = Math.min(1, Math.abs(r));
  return r >= 0 ? `color-mix(in oklab, var(--telemetry) ${Math.round(a * 75)}%, transparent)` : `color-mix(in oklab, var(--critical) ${Math.round(a * 75)}%, transparent)`;
}

function MatrixView({ m }: { m: MatrixResult }) {
  const k = m.series.length;
  const cell = (i: number, j: number) => m.cells.find((c) => c.i === i && c.j === j);
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-1 text-xs">
          <caption className="sr-only">{m.method} correlation matrix</caption>
          <thead>
            <tr>
              <th />
              {m.series.map((s, j) => <th key={s.id} scope="col" className="max-w-28 px-1 text-left align-bottom font-medium text-ink-2">{j + 1}. {s.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: k }, (_, i) => (
              <tr key={i}>
                <th scope="row" className="max-w-56 pr-2 text-left font-medium text-ink-2">{i + 1}. {m.series[i].label}</th>
                {Array.from({ length: k }, (_, j) => {
                  const c = cell(i, j);
                  const sig = c?.q != null && c.q < 0.05;
                  return (
                    <td key={j} className={cn("h-12 w-16 rounded text-center tabular-nums", i === j && "text-ink-3")}
                      style={{ background: i === j ? "var(--bulkhead)" : colourFor(c?.r ?? null) }}
                      title={c ? `r ${fmt(c.r, 2)}, n ${c.n}, p ${p(c.p)}, q ${p(c.q)}` : undefined}>
                      {i === j ? "—" : c?.r == null ? <span className="text-ink-3">n {c?.n ?? 0}</span> : <>{fmt(c.r, 2)}{sig ? "*" : ""}<span className="block text-[10px] text-ink-3">n {c.n}</span></>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-3">* q &lt; 0.05 after Benjamini-Hochberg correction across all pairs. Blue positive, red negative; empty cells had too few overlapping days.</p>
      <Warnings items={m.warnings} />
    </div>
  );
}

const EXAMPLES: { label: string; x: string; y: (ids: Set<string>) => string | null }[] = [
  { label: "ISS GCR dose vs flare activity (real vs real)", x: "swx:flare_max_log_flux", y: (ids) => [...ids].find((i) => i.endsWith("dose_gcr_mgy_day")) ?? null },
  { label: "ISS SAA dose vs geomagnetic storm level", x: "swx:storm_level", y: (ids) => [...ids].find((i) => i.endsWith("dose_saa_mgy_day")) ?? null },
  { label: "Crew heart rate vs CME count (negative control)", x: "swx:cme_count", y: () => "crew:AST-01:hr_mean" },
  { label: "Sleep duration vs mission day (simulated)", x: "mission:day", y: () => "crew:AST-01:sleep_hours" },
];

export function CorrelationView() {
  const cat = useCorrelationSeries();
  const series = useMemo(() => cat.data ?? [], [cat.data]);
  const byId = useMemo(() => new Map(series.map((s) => [s.id, s])), [series]);
  const [x, setX] = useState("swx:flare_count");
  const [y, setY] = useState("");
  // Default window = last 30 days, computed on the client after mount (useNow is null while prerendering).
  const now = useNow(60_000);
  const [range, setRange] = useState<Range | null>(null);
  const start = range?.start ?? (now ? isoDay(now - 30 * 86_400_000) : "");
  const end = range?.end ?? (now ? isoDay(now) : "");
  const setStart = (v: string) => setRange({ start: v, end });
  const setEnd = (v: string) => setRange({ start, end: v });
  const [maxLag, setMaxLag] = useState(3);
  const [win, setWin] = useState(14);
  const run = useCorrelation();
  const matrix = useCorrelationMatrix();
  const [picked, setPicked] = useState<string[]>([]);

  const choose = (nx: string, ny: string) => {
    setX(nx);
    setY(ny);
    setRange(suggestPeriod(byId.get(nx)?.coverage, byId.get(ny)?.coverage, now ?? 0));  // choose() runs on click, after mount
  };
  const ids = new Set(series.map((s) => s.id));

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-dashed border-caution/50 bg-caution/5 px-4 py-3 text-sm text-ink-2">
        <span className="font-medium text-foreground">Exploratory analysis. Correlation does not establish causation.</span> Space-weather and
        ISS series are real NASA data; crew series are simulated and never respond to space weather, so pairing them is a negative control.
        Results report effective sample size, multiple-comparison corrected q-values and known confounders.
      </div>

      {cat.isPending ? (
        <LoadingState rows={3} />
      ) : cat.error && !cat.data ? (
        <ErrorState error={cat.error} onRetry={() => cat.refetch()} />
      ) : (
        <Panel raised title="Pair analysis" description="Choose two daily series and a period. Suggested periods follow the data each series actually covers.">
          <div className="mb-4 flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => {
              const yy = ex.y(ids);
              const ok = ids.has(ex.x) && !!yy && ids.has(yy);
              return (
                <Button key={ex.label} size="sm" variant="outline" disabled={!ok} onClick={() => yy && choose(ex.x, yy)}>{ex.label}</Button>
              );
            })}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {[["x", x, (v: string) => choose(v, y)], ["y", y, (v: string) => choose(x, v)]].map(([k, v, set]) => {
              const info = byId.get(v as string);
              return (
                <div key={k as string} className="space-y-1.5">
                  <label className="text-xs text-ink-2">Series {(k as string).toUpperCase()}</label>
                  <SeriesPicker series={series} value={v as string} onChange={set as (v: string) => void} label={`Series ${(k as string).toUpperCase()}`} />
                  {info && (
                    <div className="flex flex-wrap items-center gap-2 text-xs text-ink-3">
                      <CategoryBadge category={info.category} />
                      {info.coverage.length ? `covers ${info.coverage.map((c) => `${c.start} to ${c.end}`).slice(-2).join(", ")}` : "daily aggregates of stored data"}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-4 flex flex-wrap items-end gap-4">
            {[["From", start, setStart], ["To", end, setEnd]].map(([l, v, set]) => (
              <label key={l as string} className="text-xs text-ink-2">
                {l as string}
                <input type="date" value={v as string} onChange={(e) => (set as (v: string) => void)(e.target.value)}
                  className="mt-1 block h-8 rounded-md border border-bulkhead bg-abyss/60 px-2 text-sm text-foreground" />
              </label>
            ))}
            <label className="text-xs text-ink-2">
              Max lag (days)
              <input type="number" min={0} max={14} value={maxLag} onChange={(e) => setMaxLag(Math.max(0, Math.min(14, Number(e.target.value))))}
                className="mt-1 block h-8 w-20 rounded-md border border-bulkhead bg-abyss/60 px-2 text-sm text-foreground" />
            </label>
            <label className="text-xs text-ink-2">
              Rolling window (days)
              <input type="number" min={5} max={90} value={win} onChange={(e) => setWin(Math.max(5, Math.min(90, Number(e.target.value))))}
                className="mt-1 block h-8 w-20 rounded-md border border-bulkhead bg-abyss/60 px-2 text-sm text-foreground" />
            </label>
            <Button disabled={!x || !y || !start || !end || run.isPending} onClick={() => run.mutate({ x, y, start, end, max_lag: maxLag, rolling_window: win })}>
              <Play aria-hidden />
              {run.isPending ? "Analysing" : "Analyse"}
            </Button>
          </div>
          <div className="mt-5">
            {run.error ? <ErrorState error={run.error} /> : run.data ? <ResultView r={run.data} /> : (
              <p className="text-sm text-ink-3">Pick a pair (or an example) and select Analyse.</p>
            )}
          </div>
        </Panel>
      )}

      {series.length > 0 && (
        <Panel title="Correlation matrix" description="Spearman correlations between up to 8 series over the period above, with q-values corrected across all pairs.">
          <div className="flex flex-wrap gap-1.5">
            {series.filter((s) => !s.id.startsWith("crew:") || s.id.startsWith("crew:AST-01")).map((s) => {
              const on = picked.includes(s.id);
              return (
                <button key={s.id} type="button" aria-pressed={on}
                  onClick={() => setPicked((prev) => prev.includes(s.id) ? prev.filter((v) => v !== s.id) : prev.length < 8 ? [...prev, s.id] : prev)}
                  className={cn("rounded-full border px-2.5 py-1 text-xs", on ? "border-telemetry bg-telemetry/15 text-foreground" : "border-bulkhead text-ink-2 hover:text-foreground")}>
                  {s.label}
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
            <Button size="sm" disabled={picked.length < 2 || !start || !end || matrix.isPending} onClick={() => matrix.mutate({ series: picked, start, end, method: "spearman" })}>
              <Play aria-hidden />Compute matrix
            </Button>
            <span className="text-xs text-ink-3">{picked.length} of up to 8 series selected · period {start || "…"} to {end || "…"} (set above)</span>
          </div>
          <div className="mt-4">
            {matrix.error ? <ErrorState error={matrix.error} /> : matrix.data ? <MatrixView m={matrix.data} /> : null}
          </div>
        </Panel>
      )}
    </div>
  );
}
