import { OctagonX, TriangleAlert } from "lucide-react";

import { fmt } from "@/lib/format";
import type { Breach } from "@/lib/thresholds";
import { cn } from "@/lib/utils";

const SIZES = {
  xl: "text-5xl",
  lg: "text-4xl",
  md: "text-2xl",
  sm: "text-xl",
} as const;

/**
 * Instrument readout. Breaches colour the number and add an icon, so state is never colour-only.
 */
export function Readout({
  label,
  value,
  unit,
  decimals = 0,
  breach = null,
  size = "md",
  accent = false,
  secondary,
  className,
}: {
  label: string;
  value: number | null | undefined;
  unit?: string;
  decimals?: number;
  breach?: Breach;
  size?: keyof typeof SIZES;
  accent?: boolean;
  secondary?: string;
  className?: string;
}) {
  const tone =
    breach?.severity === "critical"
      ? "text-critical"
      : breach?.severity === "caution"
        ? "text-caution"
        : accent
          ? "text-telemetry"
          : "text-foreground";
  const Icon = breach?.severity === "critical" ? OctagonX : breach ? TriangleAlert : null;
  return (
    <div className={cn("min-w-0", className)}>
      <div className="flex items-center gap-1 text-xs text-ink-2">
        <span className="truncate">{label}</span>
        {Icon && (
          <Icon
            className={cn("size-3.5 shrink-0", tone)}
            aria-label={`${breach!.severity}: beyond ${breach!.limit} ${unit ?? ""}`}
          />
        )}
      </div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className={cn("readout font-semibold", SIZES[size], tone)}>
          {secondary ? secondary : fmt(value, decimals)}
        </span>
        {unit && <span className="text-xs text-ink-3">{unit}</span>}
      </div>
    </div>
  );
}
