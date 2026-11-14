import type { ConnectionState } from "./store";

/**
 * Whether a reading from the live store should be shown instead of the REST value.
 * Only while the socket is actually live and only when the live reading is not older than the
 * REST one: after a disconnect the store keeps its last (frozen) reading, and a later REST refetch
 * must win over it. `restAsOf` is the time the REST value was current (null when unknown).
 */
export function preferLive(
  connection: ConnectionState,
  liveTs: string | null | undefined,
  restAsOf: string | null | undefined,
): boolean {
  if (connection !== "live" || !liveTs) return false;
  if (!restAsOf) return true;
  return Date.parse(liveTs) >= Date.parse(restAsOf);
}

export interface PickedReading<T> {
  reading: T | null;
  /** True only when the value comes from a connected live stream. */
  live: boolean;
}

/**
 * Choose between the live-store reading and the REST reading for one crew member.
 * Falls back to the last live reading (marked not live, with its own timestamp) only when there is
 * no REST reading at all.
 */
export function pickReading<T extends { ts: string }>(
  live: T | null | undefined,
  rest: T | null | undefined,
  connection: ConnectionState,
): PickedReading<T> {
  if (live && preferLive(connection, live.ts, rest?.ts)) return { reading: live, live: true };
  if (rest) return { reading: rest, live: false };
  return { reading: live ?? null, live: false };
}
