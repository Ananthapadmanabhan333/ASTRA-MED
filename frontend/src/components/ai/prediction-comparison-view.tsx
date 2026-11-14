"use client";

import { ArrowLeft, GitCompareArrows } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Panel } from "@/components/data/panel";
import { ErrorState, LoadingState } from "@/components/data/states";
import { CrewPicker, useParamState } from "@/components/medical/common";
import { SimulatedNote } from "@/components/shell/simulated-marker";
import { Button } from "@/components/ui/button";
import { useCrewRisk, useForecast, useModelPerformance } from "@/lib/api/hooks";
import { fmt, utcDayTime, utcTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const MODELS = [
  { id: "xgboost", label: "XGBoost (Gradient Boosted Trees)", color: "#3dd8ea" },
  { id: "lstm", label: "LSTM (Recurrent Neural Network)", color: "#a855f7" },
  { id: "gru", label: "GRU (Gated Recurrent Unit)", color: "#f2c14e" },
  { id: "tcn", label: "TCN (Temporal ConvNet)", color: "#5ee2a0" },
  { id: "climatology", label: "Personal Climatology (Baseline)", color: "#8ca5c2" },
] as const;

const SIGNALS = [
  { value: "heart_rate", label: "Heart Rate", unit: "bpm", decimals: 0 },
  { value: "spo2", label: "SpO₂", unit: "%", decimals: 1 },
  { value: "respiratory_rate", label: "Respiratory Rate", unit: "rpm", decimals: 0 },
  { value: "temperature_c", label: "Temperature", unit: "°C", decimals: 2 },
] as const;

export function PredictionComparisonView() {
  const crew = useCrewRisk();
  const [selected, setSelected] = useParamState("astronaut");
  const active = selected ?? crew.data?.crew[0]?.astronaut_id ?? "AST-01";
  const activeName = crew.data?.crew.find((c) => c.astronaut_id === active)?.name ?? active;

  const [signal, setSignal] = useState<string>("heart_rate");
  const [primaryModel, setPrimaryModel] = useState<string>("xgboost");
  const [secondaryModel, setSecondaryModel] = useState<string>("lstm");

  const qPrimary = useForecast(active, primaryModel);
  const qSecondary = useForecast(active, secondaryModel);
  const qClimatology = useForecast(active, "climatology");
  const perf = useModelPerformance();

  const sigMeta = SIGNALS.find((s) => s.value === signal) ?? SIGNALS[0];
  const sPrimary = qPrimary.data?.series.find((x) => x.signal === signal);
  const sSecondary = qSecondary.data?.series.find((x) => x.signal === signal);
  const sClim = qClimatology.data?.series.find((x) => x.signal === signal);

  const chartRows = useMemo(() => {
    if (!sPrimary) return [];
    const byTs = new Map<
      number,
      {
        t: number;
        observed?: number | null;
        primary?: number;
        primaryBand?: [number, number];
        secondary?: number;
        climatology?: number;
      }
    >();

    for (const h of sPrimary.history) {
      const t = Date.parse(h.ts);
      byTs.set(t, { t, observed: h.value });
    }
    const lastObs = [...sPrimary.history].reverse().find((h) => h.value != null);
    if (lastObs && lastObs.value != null) {
      const t = Date.parse(lastObs.ts);
      const existing = byTs.get(t) ?? { t };
      byTs.set(t, {
        ...existing,
        primary: lastObs.value,
        primaryBand: [lastObs.value, lastObs.value],
        secondary: lastObs.value,
        climatology: lastObs.value,
      });
    }
    for (const p of sPrimary.forecast) {
      const t = Date.parse(p.ts);
      const existing = byTs.get(t) ?? { t };
      byTs.set(t, {
        ...existing,
        primary: p.value,
        primaryBand: [p.lower, p.upper],
      });
    }
    if (sSecondary) {
      for (const p of sSecondary.forecast) {
        const t = Date.parse(p.ts);
        const existing = byTs.get(t) ?? { t };
        byTs.set(t, { ...existing, secondary: p.value });
      }
    }
    if (sClim) {
      for (const p of sClim.forecast) {
        const t = Date.parse(p.ts);
        const existing = byTs.get(t) ?? { t };
        byTs.set(t, { ...existing, climatology: p.value });
      }
    }
    return Array.from(byTs.values()).sort((a, b) => a.t - b.t);
  }, [sPrimary, sSecondary, sClim]);

  const primaryMeta = MODELS.find((m) => m.id === primaryModel) ?? MODELS[0];
  const secondaryMeta = MODELS.find((m) => m.id === secondaryModel) ?? MODELS[1];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs text-telemetry">
            <GitCompareArrows className="size-4" aria-hidden />
            <span>Multi-Architecture Forecast Benchmarking</span>
          </div>
          <h1 className="mt-1 font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Prediction Comparison — {activeName}
          </h1>
          <p className="text-xs text-ink-2">
            Compare 24-hour multi-step physiological forecasts, split-conformal 90% intervals, and horizon MAE across model families
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <CrewPicker value={active} onChange={(v) => setSelected(v)} />
          <Button asChild size="sm" variant="outline">
            <Link href={`/intelligence?astronaut=${active}`}>
              <ArrowLeft className="mr-1 size-3.5" aria-hidden /> AI Intelligence
            </Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href={`/intelligence/explainability?astronaut=${active}`}>Explainability</Link>
          </Button>
        </div>
      </div>

      <SimulatedNote>
        Experimental decision support: multi-model forecasts are trained and benchmarked on simulated orbital physiology.
      </SimulatedNote>

      {/* Control Strip: Signal Selector + Model A vs Model B */}
      <div className="grid grid-cols-1 gap-3 rounded-xl border border-bulkhead bg-hull/80 p-4 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <p className="mb-1.5 text-xs font-medium text-ink-3">Physiological Signal</p>
          <div className="flex flex-wrap gap-1.5">
            {SIGNALS.map((s) => (
              <button
                key={s.value}
                type="button"
                onClick={() => setSignal(s.value)}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
                  signal === s.value
                    ? "border-telemetry bg-telemetry/20 text-telemetry"
                    : "border-bulkhead bg-abyss/60 text-ink-2 hover:text-foreground",
                )}
              >
                {s.label} ({s.unit})
              </button>
            ))}
          </div>
        </div>

        <div className="lg:col-span-3">
          <label htmlFor="model-a" className="mb-1.5 block text-xs font-medium text-ink-3">
            Primary Architecture (with 90% Interval)
          </label>
          <select
            id="model-a"
            value={primaryModel}
            onChange={(e) => setPrimaryModel(e.target.value)}
            className="h-9 w-full rounded-md border border-bulkhead bg-abyss px-3 text-xs text-foreground outline-none focus:border-telemetry"
          >
            {MODELS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </div>

        <div className="lg:col-span-4">
          <label htmlFor="model-b" className="mb-1.5 block text-xs font-medium text-ink-3">
            Comparison Architecture
          </label>
          <select
            id="model-b"
            value={secondaryModel}
            onChange={(e) => setSecondaryModel(e.target.value)}
            className="h-9 w-full rounded-md border border-bulkhead bg-abyss px-3 text-xs text-foreground outline-none focus:border-telemetry"
          >
            {MODELS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Overlaid Forecast Chart */}
      <Panel
        raised
        title={`Overlaid 24h Forecast Trajectory: ${sigMeta.label}`}
        description={`Comparing ${primaryMeta.label} vs ${secondaryMeta.label} and Personal Climatology baseline`}
      >
        {qPrimary.isPending ? (
          <LoadingState label="Running multi-model forecast comparison" rows={5} />
        ) : qPrimary.error && !qPrimary.data ? (
          <ErrorState error={qPrimary.error} onRetry={() => qPrimary.refetch()} />
        ) : chartRows.length > 0 ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-4 text-xs text-ink-2">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-0.5 w-4 bg-[#d9ecff]" /> Observed (24h)
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-0.5 w-4 border-t-2 border-dashed border-[#3dd8ea]" /> {primaryMeta.label}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-0.5 w-4 border-t-2 border-dashed border-[#a855f7]" /> {secondaryMeta.label}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-0.5 w-4 border-t border-dotted border-[#8ca5c2]" /> Personal Climatology
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-3 w-4 rounded-sm bg-telemetry/20" /> Primary 90% Conformal Interval
              </span>
            </div>

            <div className="h-80 w-full" role="img" aria-label="Overlaid multi-model forecast comparison chart">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartRows} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="#17304f" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="t"
                    type="number"
                    scale="time"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={(t: number) => utcTime(t, false)}
                    tick={{ fill: "#8ca5c2", fontSize: 11 }}
                    minTickGap={48}
                  />
                  <YAxis
                    domain={["auto", "auto"]}
                    tick={{ fill: "#8ca5c2", fontSize: 11 }}
                    width={46}
                    tickFormatter={(v: number) => fmt(v, sigMeta.decimals)}
                  />
                  <Area
                    dataKey="primaryBand"
                    stroke="none"
                    fill="#3dd8ea"
                    fillOpacity={0.14}
                    isAnimationActive={false}
                    connectNulls
                  />
                  <Line
                    dataKey="observed"
                    stroke="#d9ecff"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                  <Line
                    dataKey="primary"
                    stroke="#3dd8ea"
                    strokeWidth={2.5}
                    strokeDasharray="6 4"
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                  <Line
                    dataKey="secondary"
                    stroke="#a855f7"
                    strokeWidth={2}
                    strokeDasharray="4 4"
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                  <Line
                    dataKey="climatology"
                    stroke="#8ca5c2"
                    strokeWidth={1.5}
                    strokeDasharray="2 3"
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                  {sPrimary?.forecast[0] && (
                    <ReferenceLine
                      x={Date.parse(sPrimary.forecast[0].ts) - 15 * 60_000}
                      stroke="#8ca5c2"
                      strokeDasharray="2 3"
                      label={{ value: "NOW", position: "insideTopLeft", fill: "#8ca5c2", fontSize: 10 }}
                    />
                  )}
                  <Tooltip
                    isAnimationActive={false}
                    content={({ active: tipActive, payload, label }) => {
                      if (!tipActive || !payload?.length) return null;
                      const row = payload[0].payload as {
                        observed?: number | null;
                        primary?: number;
                        primaryBand?: [number, number];
                        secondary?: number;
                        climatology?: number;
                      };
                      return (
                        <div className="rounded-lg border border-bulkhead bg-[#081323] p-3 text-xs shadow-lg">
                          <p className="font-mono text-ink-3">{utcDayTime(Number(label))} UTC</p>
                          {row.observed != null && (
                            <p className="mt-1 text-foreground">
                              Observed: <span className="font-mono font-bold">{fmt(row.observed, sigMeta.decimals)} {sigMeta.unit}</span>
                            </p>
                          )}
                          {row.primary != null && (
                            <p className="mt-1 text-telemetry">
                              {primaryModel.toUpperCase()}:{" "}
                              <span className="font-mono font-bold">{fmt(row.primary, sigMeta.decimals)} {sigMeta.unit}</span>
                              {row.primaryBand && (
                                <span className="ml-1 text-ink-3">
                                  [{fmt(row.primaryBand[0], sigMeta.decimals)}–{fmt(row.primaryBand[1], sigMeta.decimals)}]
                                </span>
                              )}
                            </p>
                          )}
                          {row.secondary != null && (
                            <p className="mt-1 text-[#c084fc]">
                              {secondaryModel.toUpperCase()}:{" "}
                              <span className="font-mono font-bold">{fmt(row.secondary, sigMeta.decimals)} {sigMeta.unit}</span>
                            </p>
                          )}
                          {row.climatology != null && (
                            <p className="mt-1 text-ink-2">
                              Climatology:{" "}
                              <span className="font-mono">{fmt(row.climatology, sigMeta.decimals)} {sigMeta.unit}</span>
                            </p>
                          )}
                        </div>
                      );
                    }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : null}
      </Panel>

      {/* Horizon-by-Horizon Side-by-Side Comparison Cards */}
      {sPrimary && (
        <Panel
          title="Horizon-by-Horizon Forecast Divergence (1h · 6h · 12h · 24h)"
          description="Point prediction, 90% conformal interval width, and divergence between selected architectures."
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {sPrimary.horizons.map((hPrim, idx) => {
              const hSec = sSecondary?.horizons[idx];
              const delta = hSec ? hPrim.value - hSec.value : 0;
              return (
                <div key={hPrim.horizon_h} className="rounded-xl border border-bulkhead bg-abyss/60 p-4">
                  <div className="flex items-center justify-between text-xs text-ink-3">
                    <span className="font-semibold text-foreground">+{hPrim.horizon_h}h Horizon</span>
                    <span className="font-mono">{utcTime(hPrim.ts, false)} UTC</span>
                  </div>
                  <div className="mt-3 space-y-2 text-xs">
                    <div className="flex items-baseline justify-between">
                      <span className="text-telemetry">{primaryModel.toUpperCase()}</span>
                      <span className="font-mono text-base font-bold text-foreground">
                        {fmt(hPrim.value, sigMeta.decimals)} {sigMeta.unit}
                      </span>
                    </div>
                    <p className="text-[11px] text-ink-3">
                      90% CI: {fmt(hPrim.lower, sigMeta.decimals)} – {fmt(hPrim.upper, sigMeta.decimals)} {sigMeta.unit}
                    </p>
                    {hSec && (
                      <>
                        <div className="flex items-baseline justify-between border-t border-bulkhead/50 pt-2">
                          <span className="text-[#c084fc]">{secondaryModel.toUpperCase()}</span>
                          <span className="font-mono text-base font-bold text-foreground">
                            {fmt(hSec.value, sigMeta.decimals)} {sigMeta.unit}
                          </span>
                        </div>
                        <p className="text-[11px] text-ink-3">
                          Model Δ: <span className="font-mono text-foreground">{delta >= 0 ? "+" : ""}{fmt(delta, sigMeta.decimals)} {sigMeta.unit}</span>
                        </p>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-3">
            <SimulatedNote>
              Split-conformal prediction intervals guarantee ≥90% empirical coverage on held-out simulated orbital telemetry.
            </SimulatedNote>
          </div>
        </Panel>
      )}

      {/* Test-Set Forecast Error Benchmark Table */}
      <Panel
        title="Held-Out Test Set Forecast Benchmark (All 5 Architectures)"
        description="Mean Absolute Error (MAE), 90% interval coverage, and skill score relative to personal climatology."
      >
        {perf.isPending ? (
          <LoadingState rows={5} />
        ) : perf.data ? (
          (() => {
            const fc = perf.data.forecast as {
              models: Record<
                string,
                {
                  label: string;
                  family: string;
                  by_signal?: Record<string, Record<string, { mae: number; rmse: number; coverage?: number }>>;
                  skill_vs_climatology?: Record<string, Record<string, number>>;
                }
              >;
              horizons_hours: number[];
            };
            return (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[48rem] text-left text-sm">
                  <thead className="border-b border-bulkhead text-xs text-ink-3">
                    <tr>
                      <th className="py-2 pr-4">Model Architecture</th>
                      <th className="py-2 pr-4">Family</th>
                      {fc.horizons_hours.map((h) => (
                        <th key={h} className="py-2 pr-4">
                          MAE {h}h ({sigMeta.unit})
                        </th>
                      ))}
                      <th className="py-2 pr-4">90% Coverage (1h / 24h)</th>
                      <th className="py-2 pr-4">Skill vs Climatology (1h / 24h)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-bulkhead/50 font-mono text-xs">
                    {Object.entries(fc.models)
                      .filter(([, m]) => m.by_signal?.[signal])
                      .map(([key, m]) => {
                        const s = m.by_signal![signal];
                        const sk = m.skill_vs_climatology?.[signal];
                        const isSelected = key === primaryModel || key === secondaryModel;
                        return (
                          <tr
                            key={key}
                            className={cn(isSelected && "bg-telemetry/5")}
                          >
                            <td className="py-2.5 pr-4 font-sans font-semibold text-foreground">{m.label}</td>
                            <td className="py-2.5 pr-4 font-sans text-ink-3">{m.family}</td>
                            {fc.horizons_hours.map((h) => (
                              <td key={h} className="py-2.5 pr-4">
                                {fmt(s[`${h}h`]?.mae, signal === "temperature_c" ? 3 : 2)}
                              </td>
                            ))}
                            <td className="py-2.5 pr-4 text-ink-2">
                              {s["1h"]?.coverage != null ? `${Math.round(s["1h"].coverage * 100)}%` : "—"} /{" "}
                              {s["24h"]?.coverage != null ? `${Math.round(s["24h"].coverage * 100)}%` : "—"}
                            </td>
                            <td className={cn("py-2.5 pr-4", sk && sk["1h"] > 0 ? "text-nominal" : "text-ink-2")}>
                              {sk ? `${fmt(sk["1h"], 2)} / ${fmt(sk["24h"], 2)}` : "baseline"}
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            );
          })()
        ) : null}
      </Panel>
    </div>
  );
}
