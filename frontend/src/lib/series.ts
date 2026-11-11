import type { ComparisonSeries } from "@/lib/api/types";
import { crewColor, crewDash, surname } from "@/lib/crew";

export type Row = { t: number } & Record<string, number | null>;

export interface SeriesSpec {
  key: string;
  label: string;
  color: string;
  dash?: string;
}

/** Join per-crew comparison series into one row per bucket timestamp. */
export function mergeSeries(data: ComparisonSeries): { rows: Row[]; series: SeriesSpec[] } {
  const byTs = new Map<number, Row>();
  for (const s of data.series) {
    for (const p of s.points) {
      const t = Date.parse(p.ts);
      const row = byTs.get(t) ?? ({ t } as Row);
      row[s.astronaut_id] = p.value;
      byTs.set(t, row);
    }
  }
  return {
    rows: [...byTs.values()].sort((a, b) => a.t - b.t),
    series: data.series.map((s) => ({
      key: s.astronaut_id,
      label: surname(s.name),
      color: crewColor(s.astronaut_id),
      dash: crewDash(s.astronaut_id),
    })),
  };
}
