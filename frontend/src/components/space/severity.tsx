import type { SpaceAlert, SpaceWeatherEvent } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export const TYPE_ORDER = ["FLR", "CME", "SEP", "GST", "RBE", "IPS", "HSS", "MPC", "WSA"] as const;
export const TYPE_SHORT: Record<string, string> = {
  FLR: "Flares", CME: "CMEs", SEP: "SEP events", GST: "Geomagnetic storms", RBE: "Radiation belt",
  IPS: "Interplanetary shocks", HSS: "High-speed streams", MPC: "Magnetopause crossings", WSA: "WSA-ENLIL runs",
};

/** Colour for a 0-5 level; always paired with the level text in the UI. */
export function levelColour(level: number | null | undefined): string {
  if (level == null || level === 0) return "var(--ink-3)";
  if (level === 1) return "var(--advisory)";
  if (level <= 3) return "var(--caution)";
  return "var(--critical)";
}

export function LevelChip({ e }: { e: Pick<SpaceWeatherEvent, "scale" | "severity" | "severity_label" | "event_type"> }) {
  const level = e.severity;
  const text = e.scale ?? (level ? e.severity_label : e.severity_label === "unclassified" ? "unclassified" : "below scale");
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap"
      style={{ borderColor: `color-mix(in oklab, ${levelColour(level)} 45%, transparent)`, color: levelColour(level) }}
    >
      <span className="size-1.5 rounded-full" style={{ background: levelColour(level) }} aria-hidden />
      {text}
    </span>
  );
}

export function AlertChip({ a }: { a: Pick<SpaceAlert, "severity" | "status"> }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={cn(
          "rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize",
          a.severity === "caution" ? "border-caution/50 bg-caution/10 text-caution" : "border-advisory/45 bg-advisory/10 text-advisory",
        )}
      >
        {a.severity}
      </span>
      <span
        className={cn(
          "text-[11px] uppercase tracking-wide",
          a.status === "active" ? "text-foreground" : a.status === "recent" ? "text-ink-2" : "text-ink-3",
        )}
      >
        {a.status}
      </span>
    </span>
  );
}
