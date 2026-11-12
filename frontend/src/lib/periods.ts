/** Date-range helpers for the correlation explorer (ISO UTC days, "YYYY-MM-DD"). */

export type Range = { start: string; end: string };

const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);

export function intersect(a: Range, b: Range): Range | null {
  const start = a.start > b.start ? a.start : b.start;
  const end = a.end < b.end ? a.end : b.end;
  return start <= end ? { start, end } : null;
}

const span = (r: Range) => Date.parse(r.end) - Date.parse(r.start);

/**
 * Longest period covered by both series. A series without coverage metadata (simulated crew
 * data) exists only for recent days, so it counts as the 30 days before ``now``.
 */
export function suggestPeriod(a: Range[] | undefined, b: Range[] | undefined, now: number): Range {
  const recent = { start: isoDay(now - 30 * 86_400_000), end: isoDay(now) };
  const A = a?.length ? a : [recent];
  const B = b?.length ? b : [recent];
  let best: Range | null = null;
  for (const x of A) {
    for (const y of B) {
      const i = intersect(x, y);
      if (i && (!best || span(i) > span(best))) best = i;
    }
  }
  return best ?? recent;
}
