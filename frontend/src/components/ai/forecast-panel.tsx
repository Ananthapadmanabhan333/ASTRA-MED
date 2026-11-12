"use client";

import { useState } from "react";
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
import { SimulatedNote } from "@/components/shell/simulated-marker";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useForecast } from "@/lib/api/hooks";
import type { SignalForecast } from "@/lib/api/types";
import { fmt, utcDayTime, utcTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { ExplanationView } from "./explanation-view";

const MODEL_LABEL: Record<string, string> = {
  xgboost: "XGBoost",
  lstm: "LSTM",
  gru: "GRU",
  tcn: "TCN",
  climatology: "Personal climatology",
  persistence: "Persistence",
  seasonal_naive: "Seasonal naive",
};
const SIGNAL_TABS = [
  { value: "heart_rate", label: "Heart rate" },
  { value: "spo2", label: "SpO₂" },
  { value: "respiratory_rate", label: "Resp. rate" },
  { value: "temperature_c", label: "Temperature" },
];

function decimals(signal: string) {
  return signal === "temperature_c" ? 2 : signal === "spo2" ? 1 : 0;
}

function ForecastChart({ s }: { s: SignalForecast }) {
  const d = decimals(s.signal);
  const rows: Record<string, number | number[] | null>[] = s.history.map((h) => ({ t: Date.parse(h.ts), actual: h.value }));
  const lastObserved = [...s.history].reverse().find((h) => h.value != null);
  if (lastObserved) {
    rows[rows.length - 1] = { ...rows[rows.length - 1], forecast: lastObserved.value, band: [lastObserved.value!, lastObserved.value!] };
  }
  for (const p of s.forecast) rows.push({ t: Date.parse(p.ts), forecast: p.value, band: [p.lower, p.upper] });
  const limit = s.horizons.find((h) => h.caution_limit != null);
  const now = Date.parse(s.forecast[0].ts) - 15 * 60_000;
  const values = rows.flatMap((r) => [r.actual, ...(Array.isArray(r.band) ? r.band : [])]).filter((v): v is number => typeof v === "number");
  if (limit?.caution_limit != null) values.push(limit.caution_limit);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pad = Math.max((hi - lo) * 0.08, d ? 0.2 : 1);
  return (
    <div className="h-72" role="img" aria-label={`${s.label}: last 24 h and 24 h forecast with 90% interval`}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.55} vertical={false} />
          <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t: number) => utcTime(t, false)}
            tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--bulkhead)" }} minTickGap={48} />
          <YAxis domain={[Math.floor((lo - pad) * 10) / 10, Math.ceil((hi + pad) * 10) / 10]} tick={{ fill: "var(--ink-3)", fontSize: 11 }}
            tickLine={false} axisLine={false} width={44} tickFormatter={(v: number) => fmt(v, d ? 1 : 0)} />
          <Area dataKey="band" stroke="none" fill="var(--telemetry)" fillOpacity={0.14} isAnimationActive={false} connectNulls />
          <Line dataKey="actual" stroke="var(--ink-2)" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
          <Line dataKey="forecast" stroke="var(--telemetry)" strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={false} connectNulls />
          <ReferenceLine x={now} stroke="var(--ink-3)" strokeDasharray="2 3" label={{ value: "now", position: "insideTopLeft", fill: "var(--ink-3)", fontSize: 10 }} />
          {limit?.caution_limit != null && (
            <ReferenceLine y={limit.caution_limit} stroke="var(--caution)" strokeOpacity={0.7} strokeDasharray="4 4"
              label={{ value: `Caution ${limit.caution_limit} ${s.unit}`, position: "insideTopRight", fill: "var(--ink-3)", fontSize: 10 }} />
          )}
          <Tooltip
            isAnimationActive={false}
            cursor={{ stroke: "var(--ink-3)", strokeDasharray: "3 3" }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload as { actual?: number | null; forecast?: number; band?: number[] };
              return (
                <div className="rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs">
                  <p className="text-ink-2">{utcDayTime(Number(label))} UTC</p>
                  {row.actual != null && <p>Observed {fmt(row.actual, d)} {s.unit}</p>}
                  {row.forecast != null && row.band && (
                    <p className="text-telemetry">
                      Forecast {fmt(row.forecast, d)} {s.unit} <span className="text-ink-2">(90%: {fmt(row.band[0], d)} to {fmt(row.band[1], d)})</span>
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

export function ForecastPanel({ astronautId, name }: { astronautId: string; name: string }) {
  const [model, setModel] = useState("xgboost");
  const [signal, setSignal] = useState("heart_rate");
  const q = useForecast(astronautId, model);
  const s = q.data?.series.find((x) => x.signal === signal);

  return (
    <Panel
      raised
      title="Predictive health trends"
      description={`24-hour forecast for ${name} in 30-minute steps, with 90% prediction intervals calibrated on held-out simulated data.`}
      actions={
        <>
          <ToggleGroup type="single" size="sm" variant="outline" value={signal} onValueChange={(v) => v && setSignal(v)} aria-label="Signal">
            {SIGNAL_TABS.map((t) => (
              <ToggleGroupItem key={t.value} value={t.value} className="px-2.5 text-xs">
                {t.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <Select value={model} onValueChange={setModel}>
            <SelectTrigger className="w-44" aria-label="Forecast model">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(q.data?.available_models ?? ["xgboost", "lstm", "gru", "tcn", "climatology"]).map((m) => (
                <SelectItem key={m} value={m}>
                  {MODEL_LABEL[m] ?? m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </>
      }
    >
      {q.isPending ? (
        <LoadingState label="Running forecast" rows={5} />
      ) : q.error && !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : s ? (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-ink-2">
            <span className="inline-flex items-center gap-2"><span className="h-0.5 w-5 bg-ink-2" aria-hidden /> Observed</span>
            <span className="inline-flex items-center gap-2"><span className="h-0.5 w-5 border-t-2 border-dashed border-telemetry" aria-hidden /> Forecast</span>
            <span className="inline-flex items-center gap-2"><span className="h-3 w-5 rounded-sm bg-telemetry/15" aria-hidden /> 90% interval</span>
            <span className="ml-auto text-ink-3">{q.data!.model_label}, model {q.data!.model_version}</span>
          </div>
          <ForecastChart s={s} />
          <div className="grid gap-px overflow-hidden rounded-md border border-bulkhead bg-bulkhead sm:grid-cols-4">
            {s.horizons.map((h) => (
              <div key={h.horizon_h} className="bg-hull p-3">
                <p className="text-xs text-ink-3">In {h.horizon_h} h ({utcTime(h.ts, false)} UTC)</p>
                <p className={cn("readout mt-1 text-2xl", h.crossing === "likely" ? "text-critical" : h.crossing ? "text-caution" : "text-foreground")}>
                  {fmt(h.value, decimals(s.signal))} <span className="text-xs text-ink-3">{s.unit}</span>
                </p>
                <p className="text-xs text-ink-2">
                  {fmt(h.lower, decimals(s.signal))} to {fmt(h.upper, decimals(s.signal))}
                </p>
                {h.crossing && (
                  <p className={cn("mt-1 text-xs", h.crossing === "likely" ? "text-critical" : "text-caution")}>
                    {h.crossing === "likely" ? "Reaches" : "May reach"} caution limit {h.caution_limit}
                  </p>
                )}
                {h.validation_mae != null && (
                  <p className="mt-1 text-[11px] text-ink-3">
                    Test MAE {fmt(h.validation_mae, 2)}, coverage {Math.round((h.validation_coverage ?? 0) * 100)}%
                  </p>
                )}
              </div>
            ))}
          </div>
          <div className="grid gap-5 lg:grid-cols-[1fr_1.2fr]">
            <div>
              <h3 className="text-sm font-medium">What drives this forecast</h3>
              {s.drivers.length ? (
                <ul className="mt-2 space-y-2" aria-label="Forecast drivers (TreeSHAP share at 6 h)">
                  {s.drivers.map((dr) => (
                    <li key={dr.name} className="grid grid-cols-[1fr_6rem_2.5rem] items-center gap-3 text-xs">
                      <span className="text-ink-2">{dr.name}</span>
                      <span className="h-1.5 rounded-full bg-bulkhead/60" aria-hidden>
                        <span className="block h-full rounded-full bg-telemetry" style={{ width: `${dr.share * 100}%` }} />
                      </span>
                      <span className="text-right tabular-nums">{Math.round(dr.share * 100)}%</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-xs text-ink-2">Per-forecast attribution is available for XGBoost (TreeSHAP). Choose it to see drivers.</p>
              )}
            </div>
            <ExplanationView explanation={s.explanation} />
          </div>
          <SimulatedNote>Forecasts extrapolate simulated physiology. They are not validated predictions of real crew health.</SimulatedNote>
        </div>
      ) : null}
    </Panel>
  );
}
