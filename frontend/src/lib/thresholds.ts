import type { ActivityState, ThresholdInfo } from "@/lib/api/types";

export type Breach = { severity: "caution" | "critical"; limit: number; rule: ThresholdInfo } | null;

function limitsFor(rule: ThresholdInfo, activity: ActivityState | undefined): [number, number] {
  const override = activity ? rule.overrides?.[activity] : undefined;
  return override ? [override[0], override[1]] : [rule.caution, rule.critical];
}

/**
 * Mirror of the backend's activity-aware threshold check, using the limits the API serves.
 * Used only to colour displays; alerts themselves come from the backend.
 */
export function classify(
  metric: string,
  value: number,
  activity: ActivityState | undefined,
  rules: ThresholdInfo[] | undefined,
): Breach {
  if (!rules) return null;
  let worst: Breach = null;
  for (const rule of rules) {
    if (rule.metric !== metric) continue;
    const [caution, critical] = limitsFor(rule, activity);
    const high = rule.direction === "high";
    const isCritical = high ? value >= critical : value <= critical;
    const isCaution = high ? value >= caution : value <= caution;
    if (isCritical) return { severity: "critical", limit: critical, rule };
    if (isCaution && !worst) worst = { severity: "caution", limit: caution, rule };
  }
  return worst;
}

/** Resting (default-activity) caution limits for a metric, for chart reference lines. */
export function referenceLines(metric: string, rules: ThresholdInfo[] | undefined) {
  return (rules ?? [])
    .filter((r) => r.metric === metric)
    .map((r) => ({ value: r.caution, direction: r.direction, label: `${r.direction === "high" ? "High" : "Low"} caution ${r.caution} ${r.unit}` }));
}
