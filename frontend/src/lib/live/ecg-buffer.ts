import type { EcgSegment } from "@/lib/api/types";

/**
 * ECG samples arrive as one-second segments per astronaut. They are kept in a plain mutable
 * structure, outside React state, so the canvas renderer can read them every animation frame
 * without triggering re-renders.
 */
export interface EcgChunk {
  start: number; // epoch ms of the first sample
  fs: number;
  values: number[];
}

const KEEP_MS = 15_000;
const chunks = new Map<string, EcgChunk[]>();

export function pushEcg(segment: EcgSegment): void {
  const chunk: EcgChunk = {
    start: Date.parse(segment.start),
    fs: segment.sample_rate_hz,
    values: segment.values_mv,
  };
  const list = chunks.get(segment.astronaut_id) ?? [];
  const last = list[list.length - 1];
  if (last && chunk.start <= last.start) return;
  list.push(chunk);
  const cutoff = chunk.start - KEEP_MS;
  while (list.length && list[0].start + (list[0].values.length / list[0].fs) * 1000 < cutoff) list.shift();
  chunks.set(segment.astronaut_id, list);
}

export function ecgChunks(astronautId: string): readonly EcgChunk[] {
  return chunks.get(astronautId) ?? [];
}

export function clearEcg(): void {
  chunks.clear();
}
