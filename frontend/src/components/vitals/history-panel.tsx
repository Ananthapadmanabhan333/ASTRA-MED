"use client";

import { useState } from "react";

import { ChartTable } from "@/components/charts/chart-table";
import { RangePicker } from "@/components/charts/range-picker";
import { TrendChart, type ChartRow, type ChartSeries } from "@/components/charts/trend-chart";
import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { SimulatedNote } from "@/components/shell/simulated-marker";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useHistory, useThresholds } from "@/lib/api/hooks";
import { useLive } from "@/lib/live/store";
import type { ChartRange } from "@/lib/metrics";
import { referenceLines } from "@/lib/thresholds";

interface ChartSpec {
  title: string;
  metric: string;
  unit: string;
  decimals: number;
  series: ChartSeries[];
}

const T = "var(--telemetry)";
const CHARTS: ChartSpec[] = [
  { title: "Heart rate", metric: "heart_rate", unit: "bpm", decimals: 0, series: [{ key: "heart_rate", label: "Heart rate", color: T }] },
  { title: "SpO₂", metric: "spo2", unit: "%", decimals: 1, series: [{ key: "spo2", label: "SpO₂", color: T }] },
  { title: "Body temperature", metric: "temperature_c", unit: "°C", decimals: 2, series: [{ key: "temperature_c", label: "Temperature", color: T }] },
  { title: "Respiratory rate", metric: "respiratory_rate", unit: "br/min", decimals: 0, series: [{ key: "respiratory_rate", label: "Resp. rate", color: T }] },
  {
    title: "Blood pressure",
    metric: "systolic",
    unit: "mmHg",
    decimals: 0,
    series: [
      { key: "systolic", label: "Systolic", color: T },
      { key: "diastolic", label: "Diastolic", color: "var(--ink-2)", dash: "5 3" },
    ],
  },
];

export function HistoryPanel({ astronautId, name }: { astronautId: string; name: string }) {
  const [range, setRange] = useState<ChartRange>("6h");
  const [view, setView] = useState<"chart" | "table">("chart");
  const live = range === "live";
  const history = useHistory(astronautId, live ? "1h" : range, !live);
  const trail = useLive((s) => s.trails[astronautId]);
  const rules = useThresholds();

  const rows: ChartRow[] | undefined = live
    ? trail?.map((p) => ({ ...p }))
    : history.data?.points.map(({ ts, ...v }) => ({ t: Date.parse(ts), ...v }));

  let body;
  if (!live && history.isPending) body = <LoadingState label="Loading history" rows={5} />;
  else if (!live && history.error && !history.data)
    body = <ErrorState error={history.error} onRetry={() => history.refetch()} />;
  else if (!rows || rows.length < 2)
    body = (
      <EmptyState title={live ? "Waiting for live telemetry" : "No stored measurements in this range"}>
        {live
          ? "The live view fills as readings arrive over the WebSocket, one per second."
          : "Try a longer range, or check that the backend has been running."}
      </EmptyState>
    );
  else
    body = (
      <div className="grid gap-x-6 gap-y-5 md:grid-cols-2">
        {CHARTS.map((c, i) => {
          const refs = referenceLines(c.metric, rules.data);
          return (
            <figure key={c.metric} className={i === CHARTS.length - 1 ? "md:col-span-2" : undefined}>
              <figcaption className="mb-1 flex items-baseline justify-between">
                <span className="text-sm font-medium text-foreground">{c.title}</span>
                <span className="text-xs text-ink-3">{c.unit}</span>
              </figcaption>
              {view === "chart" ? (
                <TrendChart
                  data={rows}
                  series={c.series}
                  unit={c.unit}
                  decimals={c.decimals}
                  refs={refs}
                  endLabels={c.series.length > 1}
                  height={i === CHARTS.length - 1 ? 170 : 150}
                  ariaLabel={`${c.title} for ${name}, ${range === "live" ? "last 10 minutes" : `last ${range}`}`}
                />
              ) : (
                <ChartTable data={rows} series={c.series} unit={c.unit} decimals={c.decimals} caption={`${c.title} for ${name}`} />
              )}
            </figure>
          );
        })}
      </div>
    );

  const resolution = !live && history.data ? history.data.resolution_seconds : 1;
  return (
    <Panel
      title="Vital sign history"
      description={
        live
          ? "Live readings from the WebSocket stream, one per second."
          : `Stored measurements averaged into ${resolution >= 60 ? `${Math.round(resolution / 60)}-minute` : `${resolution}-second`} buckets. Dashed lines mark prototype caution limits at rest.`
      }
      actions={
        <>
          <RangePicker value={range} onChange={setRange} />
          <ToggleGroup
            type="single"
            size="sm"
            variant="outline"
            value={view}
            onValueChange={(v) => v && setView(v as "chart" | "table")}
            aria-label="Display as"
          >
            <ToggleGroupItem value="chart" className="px-2.5 text-xs">
              Chart
            </ToggleGroupItem>
            <ToggleGroupItem value="table" className="px-2.5 text-xs">
              Table
            </ToggleGroupItem>
          </ToggleGroup>
        </>
      }
    >
      {body}
      <SimulatedNote className="mt-4" />
    </Panel>
  );
}
