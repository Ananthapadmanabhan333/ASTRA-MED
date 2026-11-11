"use client";

import {
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

import { fmt, utcDayTime, utcTime } from "@/lib/format";

export interface ChartSeries {
  key: string;
  label: string;
  color: string;
  dash?: string;
}

export interface ChartRef {
  value: number;
  label: string;
}

export type ChartRow = { t: number } & Record<string, number | null>;

const AXIS = { stroke: "var(--ink-3)", fontSize: 11 };

function tickFormatter(spanMs: number) {
  if (spanMs > 2 * 86_400_000) return (t: number) => utcDayTime(t).split(",")[0];
  if (spanMs > 3 * 3_600_000) return (t: number) => utcTime(t, false);
  return (t: number) => utcTime(t, spanMs < 20 * 60_000);
}

function ChartTooltip({
  active,
  payload,
  label,
  series,
  unit,
  decimals,
}: Partial<TooltipContentProps<number, string>> & { series: ChartSeries[]; unit: string; decimals: number }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 text-ink-2">{utcDayTime(Number(label))} UTC</p>
      <ul className="space-y-0.5">
        {series.map((s) => {
          const item = payload.find((p) => p.dataKey === s.key);
          if (!item || item.value === null || item.value === undefined) return null;
          return (
            <li key={s.key} className="flex items-center gap-2">
              <span className="inline-block h-0.5 w-3 rounded" style={{ background: s.color }} aria-hidden />
              <span className="text-ink-2">{s.label}</span>
              <span className="ml-auto pl-3 font-medium text-foreground tabular-nums">
                {fmt(Number(item.value), decimals)} {unit}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * Time-series line chart on a single y-axis. Multiple series must share a unit; identity is
 * carried by colour, dash pattern and a direct end label.
 */
export function TrendChart({
  data,
  series,
  unit,
  decimals = 0,
  refs = [],
  height = 180,
  domain,
  endLabels = false,
  ariaLabel,
}: {
  data: ChartRow[];
  series: ChartSeries[];
  unit: string;
  decimals?: number;
  refs?: ChartRef[];
  height?: number;
  domain?: [number | "auto" | "dataMin" | "dataMax", number | "auto" | "dataMin" | "dataMax"];
  endLabels?: boolean;
  ariaLabel: string;
}) {
  const span = data.length > 1 ? data[data.length - 1].t - data[0].t : 0;
  const values = data.flatMap((r) => series.map((s) => r[s.key]).filter((v): v is number => v != null));
  const lo = Math.min(...values, ...refs.map((r) => r.value));
  const hi = Math.max(...values, ...refs.map((r) => r.value));
  const pad = Math.max((hi - lo) * 0.08, decimals ? 0.2 : 1);
  const yDomain = domain ?? [Math.floor((lo - pad) * 10) / 10, Math.ceil((hi + pad) * 10) / 10];
  // End labels are laid out in series order during this render; each one steps clear of the
  // labels already placed so they never overprint.
  // Keyed by series so Recharts' internal re-renders replace a label instead of stacking it.
  const placedLabels = new Map<string, number>();
  const placeLabel = (key: string, y: number) => {
    placedLabels.delete(key);
    const others = [...placedLabels.values()];
    let target = y;
    for (let i = 0; i < 8 && others.some((p) => Math.abs(p - target) < 12); i++) {
      target = y + (i % 2 === 0 ? 12 : -12) * Math.ceil((i + 1) / 2);
    }
    placedLabels.set(key, target);
    return target;
  };

  return (
    <div role="img" aria-label={ariaLabel} style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: endLabels ? 56 : 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.55} vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={tickFormatter(span)}
            tick={AXIS}
            tickLine={false}
            axisLine={{ stroke: "var(--bulkhead)" }}
            minTickGap={48}
          />
          <YAxis
            domain={yDomain}
            tick={AXIS}
            tickLine={false}
            axisLine={false}
            width={44}
            tickFormatter={(v: number) => fmt(v, decimals && Math.abs(yDomain[1] as number) < 50 ? 1 : 0)}
          />
          {refs.map((r) => (
            <ReferenceLine
              key={r.label}
              y={r.value}
              stroke="var(--caution)"
              strokeOpacity={0.6}
              strokeDasharray="4 4"
              label={{ value: r.label, position: "insideTopRight", fill: "var(--ink-3)", fontSize: 10 }}
            />
          ))}
          <Tooltip
            cursor={{ stroke: "var(--ink-3)", strokeDasharray: "3 3" }}
            content={(props) => (
              <ChartTooltip {...(props as TooltipContentProps<number, string>)} series={series} unit={unit} decimals={decimals} />
            )}
            isAnimationActive={false}
          />
          {series.map((s) => (
            <Line
              key={s.key}
              dataKey={s.key}
              name={s.label}
              type="monotone"
              stroke={s.color}
              strokeWidth={2}
              strokeDasharray={s.dash && s.dash !== "0" ? s.dash : undefined}
              dot={false}
              activeDot={{ r: 4, stroke: "var(--hull)", strokeWidth: 2 }}
              isAnimationActive={false}
              connectNulls
            >
              {endLabels && (
                <LabelList
                  dataKey={s.key}
                  content={(props) => {
                    const { x, y, index } = props as { x?: number; y?: number; index?: number };
                    if (index !== data.length - 1 || x === undefined || y === undefined) return null;
                    return (
                      <text x={Number(x) + 6} y={placeLabel(s.key, Number(y))} dy={4} fontSize={11} fill="var(--ink-2)">
                        {s.label}
                      </text>
                    );
                  }}
                />
              )}
            </Line>
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
