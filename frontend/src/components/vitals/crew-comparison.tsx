"use client";

import { useState } from "react";

import { ChartTable } from "@/components/charts/chart-table";
import { RangePicker } from "@/components/charts/range-picker";
import { TrendChart, type ChartSeries } from "@/components/charts/trend-chart";
import { Panel } from "@/components/data/panel";
import { QueryView } from "@/components/data/states";
import { SimulatedNote } from "@/components/shell/simulated-marker";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useComparison, useThresholds } from "@/lib/api/hooks";
import type { Metric, TimeRange } from "@/lib/api/types";
import { COMPARABLE_METRICS, METRICS, type ChartRange } from "@/lib/metrics";
import { mergeSeries } from "@/lib/series";
import { referenceLines } from "@/lib/thresholds";

function Legend({ series }: { series: ChartSeries[] }) {
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-2" aria-label="Legend">
      {series.map((s) => (
        <li key={s.key} className="flex items-center gap-2">
          <svg width="22" height="6" aria-hidden>
            <line
              x1="1"
              y1="3"
              x2="21"
              y2="3"
              stroke={s.color}
              strokeWidth="2"
              strokeDasharray={s.dash !== "0" ? s.dash : undefined}
              strokeLinecap="round"
            />
          </svg>
          {s.label}
        </li>
      ))}
    </ul>
  );
}

export function CrewComparison() {
  const [metric, setMetric] = useState<Metric>("heart_rate");
  const [range, setRange] = useState<TimeRange>("24h");
  const [view, setView] = useState<"chart" | "table">("chart");
  const query = useComparison(metric, range);
  const rules = useThresholds();
  const meta = METRICS[metric];

  return (
    <Panel
      raised
      title="Crew comparison"
      description="One measurement for every crew member over the same window, averaged into matching buckets."
      actions={
        <>
          <Select value={metric} onValueChange={(v) => setMetric(v as Metric)}>
            <SelectTrigger className="w-48" aria-label="Measurement">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {COMPARABLE_METRICS.map((m) => (
                <SelectItem key={m} value={m}>
                  {METRICS[m].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <RangePicker value={range} onChange={(v: ChartRange) => v !== "live" && setRange(v)} includeLive={false} />
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
      <QueryView query={query} isEmpty={(d) => d.series.every((s) => s.points.length === 0)}>
        {(data) => {
          const { rows, series } = mergeSeries(data);
          const decimals = meta.decimals;
          return (
            <div className="space-y-3">
              <Legend series={series} />
              {view === "chart" ? (
                <TrendChart
                  data={rows}
                  series={series}
                  unit={meta.unit}
                  decimals={decimals}
                  refs={referenceLines(metric, rules.data)}
                  endLabels
                  height={320}
                  ariaLabel={`${meta.label} for all crew, last ${range}`}
                />
              ) : (
                <ChartTable
                  data={rows}
                  series={series}
                  unit={meta.unit}
                  decimals={decimals}
                  limit={60}
                  caption={`${meta.label} for all crew`}
                />
              )}
              <SimulatedNote>
                Simulated data. {Math.round(data.resolution_seconds / 60) || 1}-minute buckets; dashed amber lines
                are prototype caution limits at rest.
              </SimulatedNote>
            </div>
          );
        }}
      </QueryView>
    </Panel>
  );
}
