import { CircleAlert, CircleCheck, OctagonX, TriangleAlert } from "lucide-react";

import type { RiskCategory } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** Risk categories reuse the status palette, always with an icon and words. */
export const CONCERN = {
  normal: { label: "Normal", icon: CircleCheck, text: "text-nominal", ring: "border-nominal/40 bg-nominal/10", bar: "bg-nominal" },
  low_concern: { label: "Low concern", icon: CircleAlert, text: "text-advisory", ring: "border-advisory/40 bg-advisory/10", bar: "bg-advisory" },
  moderate_concern: { label: "Moderate concern", icon: TriangleAlert, text: "text-caution", ring: "border-caution/45 bg-caution/10", bar: "bg-caution" },
  high_concern: { label: "High concern", icon: OctagonX, text: "text-critical", ring: "border-critical/50 bg-critical/12", bar: "bg-critical" },
} as const satisfies Record<RiskCategory, unknown>;

export function ConcernPill({ category, className }: { category: RiskCategory; className?: string }) {
  const c = CONCERN[category];
  const Icon = c.icon;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap", c.ring, c.text, className)}>
      <Icon className="size-3.5" aria-hidden />
      {c.label}
    </span>
  );
}
