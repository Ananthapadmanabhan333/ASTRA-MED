import { fmt, utcDayTime } from "@/lib/format";

import type { ChartRow, ChartSeries } from "./trend-chart";

/** Accessible table alternative for any TrendChart (most recent rows first). */
export function ChartTable({
  data,
  series,
  unit,
  decimals = 0,
  limit = 30,
  caption,
}: {
  data: ChartRow[];
  series: ChartSeries[];
  unit: string;
  decimals?: number;
  limit?: number;
  caption: string;
}) {
  const rows = data.slice(-limit).reverse();
  return (
    <div className="max-h-64 overflow-auto rounded-md border border-bulkhead/70">
      <table className="w-full text-left text-xs">
        <caption className="sr-only">{caption}</caption>
        <thead className="sticky top-0 bg-hull text-ink-2">
          <tr>
            <th scope="col" className="px-3 py-1.5 font-medium">
              Time (UTC)
            </th>
            {series.map((s) => (
              <th key={s.key} scope="col" className="px-3 py-1.5 text-right font-medium">
                {s.label} ({unit})
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {rows.map((r) => (
            <tr key={r.t} className="border-t border-bulkhead/50">
              <td className="px-3 py-1 text-ink-2">{utcDayTime(r.t)}</td>
              {series.map((s) => (
                <td key={s.key} className="px-3 py-1 text-right">
                  {fmt(r[s.key] ?? null, decimals)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
