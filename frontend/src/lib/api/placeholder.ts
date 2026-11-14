/**
 * Identity check for `placeholderData`: the previous result may stand in while a refined query
 * loads only if it belongs to the same subject (crew member, data context, simulation run...).
 * Comparing the previous query's filters, not its data, works for list responses too.
 * Missing, null and undefined count as the same "no filter" value.
 */
export function sameSubject<T extends object>(
  prev: T | null | undefined,
  next: T,
  fields: readonly (keyof T)[],
): boolean {
  if (!prev) return false;
  return fields.every((f) => (prev[f] ?? null) === (next[f] ?? null));
}
