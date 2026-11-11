import { CircleAlert, CircleCheck, OctagonX, TriangleAlert } from "lucide-react";

import type { CrewStatus, Severity } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STATUS = {
  nominal: { label: "Nominal", icon: CircleCheck, text: "text-nominal", ring: "border-nominal/40 bg-nominal/10" },
  advisory: { label: "Advisory", icon: CircleAlert, text: "text-advisory", ring: "border-advisory/40 bg-advisory/10" },
  caution: { label: "Caution", icon: TriangleAlert, text: "text-caution", ring: "border-caution/45 bg-caution/10" },
  critical: { label: "Critical", icon: OctagonX, text: "text-critical", ring: "border-critical/50 bg-critical/12" },
} as const;

export function statusMeta(status: CrewStatus | Severity) {
  return STATUS[status];
}

/** Status always carries an icon and a word, never colour alone. */
export function StatusPill({
  status,
  className,
  compact = false,
}: {
  status: CrewStatus | Severity;
  className?: string;
  compact?: boolean;
}) {
  const meta = STATUS[status];
  const Icon = meta.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        meta.ring,
        meta.text,
        className,
      )}
    >
      <Icon className="size-3.5 shrink-0" aria-hidden />
      {compact ? <span className="sr-only">{meta.label}</span> : meta.label}
    </span>
  );
}

export function StatusIcon({ status, className }: { status: CrewStatus | Severity; className?: string }) {
  const meta = STATUS[status];
  const Icon = meta.icon;
  return <Icon className={cn("size-4 shrink-0", meta.text, className)} aria-label={meta.label} />;
}

/** Left-edge rail colour for rows whose state is not nominal. */
export const STATUS_RAIL: Record<CrewStatus, string> = {
  nominal: "bg-transparent",
  advisory: "bg-advisory",
  caution: "bg-caution",
  critical: "bg-critical",
};
