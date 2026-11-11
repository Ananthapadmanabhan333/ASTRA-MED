import type { TrailPoint } from "@/lib/live/reducer";

type NumericKey = Exclude<keyof TrailPoint, "t">;

/** Tiny trend line for the last few minutes; purely visual (the value next to it is the data). */
export function Sparkline({
  points,
  metric,
  className,
  width = 120,
  height = 28,
}: {
  points: TrailPoint[] | undefined;
  metric: NumericKey;
  className?: string;
  width?: number;
  height?: number;
}) {
  const data = (points ?? []).slice(-180);
  if (data.length < 2) return <svg className={className} width={width} height={height} aria-hidden />;
  const values = data.map((p) => p[metric]);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (max - min < 1e-6) {
    min -= 1;
    max += 1;
  }
  const t0 = data[0].t;
  const span = Math.max(1, data[data.length - 1].t - t0);
  const d = data
    .map((p, i) => {
      const x = ((p.t - t0) / span) * (width - 2) + 1;
      const y = height - 2 - ((p[metric] - min) / (max - min)) * (height - 4);
      return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join("");
  return (
    <svg className={className} width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      <path d={d} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
