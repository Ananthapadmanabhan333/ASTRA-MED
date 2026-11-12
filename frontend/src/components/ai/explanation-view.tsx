import { Info } from "lucide-react";

import type { AIExplanation } from "@/lib/api/types";
import { fmt } from "@/lib/format";
import { cn } from "@/lib/utils";

const SIGNIFICANCE_TONE = {
  none: "text-ink-2",
  minor: "text-advisory",
  notable: "text-caution",
  major: "text-critical",
} as const;

const KIND_LABEL: Record<string, string> = {
  sudden_change: "Sudden change",
  gradual_deviation: "Gradual deviation",
  sustained_offset: "Sustained offset",
  risk_assessment: "Risk assessment",
  forecast: "Forecast",
  threshold_breach: "Threshold breach",
  rhythm: "Rhythm check",
  baseline: "Personal baseline",
};

/**
 * The five answers every AI output gives: what changed, which signals contributed, how
 * significant, how confident, and what limits the data has.
 */
export function ExplanationView({
  explanation,
  compact = false,
  className,
}: {
  explanation: AIExplanation;
  compact?: boolean;
  className?: string;
}) {
  const e = explanation;
  return (
    <div className={cn("space-y-4 text-sm", className)}>
      <div>
        <p className="text-xs text-ink-3">{KIND_LABEL[e.kind] ?? e.kind}</p>
        <p className="mt-0.5 text-foreground">{e.what_changed}</p>
      </div>

      {e.contributors.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-ink-2">Contributing signals</h4>
          <ul className="mt-2 space-y-2">
            {e.contributors.map((c) => (
              <li key={c.signal} className="grid grid-cols-[8.5rem_1fr_auto] items-center gap-3">
                <span className="truncate text-ink-2">{c.label}</span>
                <div className="h-1.5 rounded-full bg-bulkhead/60" aria-hidden>
                  <div className="h-full rounded-full bg-telemetry" style={{ width: `${Math.max(4, c.share * 100)}%` }} />
                </div>
                <span className="text-right text-xs tabular-nums text-ink-2">
                  {Math.round(c.share * 100)}%
                  {c.z != null && (
                    <span className="ml-2 text-foreground">
                      {fmt(c.value, 1)} vs {fmt(c.baseline, 1)} {c.unit} (z {c.z > 0 ? "+" : ""}
                      {fmt(c.z, 1)})
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <dl className="grid gap-3 sm:grid-cols-2">
        <div>
          <dt className="text-xs text-ink-3">Significance</dt>
          <dd className={cn("font-medium", SIGNIFICANCE_TONE[e.significance.level])}>
            {e.significance.level === "none" ? "Not significant" : <span className="capitalize">{e.significance.level}</span>}
            <span className="ml-1.5 font-normal text-ink-2">
              {e.significance.description}
              {e.significance.max_abs_z > 0 && `, max |z| ${fmt(e.significance.max_abs_z, 1)}`}
            </span>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-3">Model confidence</dt>
          <dd className="font-medium capitalize text-foreground">
            {e.confidence.level}
            <span className="ml-1.5 font-normal text-ink-2">({fmt(e.confidence.score, 2)})</span>
          </dd>
          {!compact && <dd className="mt-0.5 text-xs text-ink-3">{e.confidence.basis.join(" / ")}</dd>}
        </div>
      </dl>

      {!compact && e.limitations.length > 0 && (
        <div className="rounded-md border border-bulkhead/70 bg-abyss/40 p-3">
          <h4 className="flex items-center gap-1.5 text-xs font-medium text-ink-2">
            <Info className="size-3.5" aria-hidden /> Data limitations
          </h4>
          <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs text-ink-2">
            {e.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </div>
      )}
      {!compact && e.method && <p className="text-xs text-ink-3">Method: {e.method}</p>}
    </div>
  );
}
