"use client";

import {
  Bot,
  Calculator,
  CircleDashed,
  CircleHelp,
  Cpu,
  FlaskConical,
  Info,
  RefreshCcw,
  Satellite,
  Settings2,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAstronauts } from "@/lib/api/hooks";
import type { SystemStatus } from "@/lib/api/types";
import { crewColor } from "@/lib/crew";
import { cn } from "@/lib/utils";

/** Every value on the phase 5 pages says what kind of value it is. */
export const KIND: Record<string, { label: string; help: string; icon: LucideIcon; cls: string }> = {
  simulated: { label: "Simulated", help: "Simulated measurement from the ASTRA-MED crew simulator. Not real astronaut data.", icon: FlaskConical, cls: "border-telemetry/40 text-telemetry" },
  data: { label: "Simulated record", help: "A stored record of simulated crew data.", icon: FlaskConical, cls: "border-telemetry/40 text-telemetry" },
  regenerated: { label: "Regenerated", help: "Recomputed by the deterministic simulator for days whose stored samples were pruned.", icon: RefreshCcw, cls: "border-ink-3/50 text-ink-2" },
  derived: { label: "Derived", help: "Statistic computed from simulated measurements (mean, z-score, trend).", icon: Calculator, cls: "border-ink-2/40 text-ink-2" },
  model: { label: "Model output", help: "Experimental AI output trained on simulated data. Not clinically validated.", icon: Cpu, cls: "border-caution/45 text-caution" },
  configured: { label: "Configured", help: "A simulator or prototype setting, not a measurement and not a clinical criterion.", icon: Settings2, cls: "border-ink-3/50 text-ink-3" },
  measured: { label: "NASA measured", help: "Real NASA measurement (ISS environment). Never a crew dose.", icon: Satellite, cls: "border-nominal/45 text-nominal" },
  indicator: { label: "NASA indicator", help: "Real NASA space-weather indicator. Context only, not a dose.", icon: Satellite, cls: "border-nominal/45 text-nominal" },
  nasa: { label: "NASA data", help: "Real NASA public data.", icon: Satellite, cls: "border-nominal/45 text-nominal" },
  documentation: { label: "Documentation", help: "ASTRA-MED documentation: how the system works (established system behaviour).", icon: Info, cls: "border-advisory/45 text-advisory" },
  reference: { label: "Reference", help: "An approved reference document from the knowledge library.", icon: Info, cls: "border-advisory/45 text-advisory" },
  safety: { label: "Safety", help: "Safety notice from the assistant.", icon: ShieldAlert, cls: "border-critical/45 text-critical" },
  estimate: { label: "Estimate", help: "Estimate from a published reference value, not a measurement.", icon: Calculator, cls: "border-ink-2/40 text-ink-2" },
  mixed: { label: "Mixed sources", help: "Draws on several kinds of source.", icon: Bot, cls: "border-ink-2/40 text-ink-2" },
  uncited: { label: "Uncited", help: "Not backed by a citation; treat with care.", icon: CircleHelp, cls: "border-critical/40 text-critical" },
};

export function KindChip({ kind, className }: { kind: string; className?: string }) {
  const k = KIND[kind] ?? KIND.derived;
  const Icon = k.icon;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          className={cn("inline-flex items-center gap-1 rounded-full border px-1.5 py-px text-[11px] font-medium whitespace-nowrap", k.cls, className)}
        >
          <Icon className="size-3" aria-hidden />
          {k.label}
        </span>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-xs text-pretty">{k.help}</TooltipContent>
    </Tooltip>
  );
}

const SYSTEM_STATUS: Record<SystemStatus | "info", { label: string; cls: string; dot: string }> = {
  within_baseline: { label: "Within baseline", cls: "border-nominal/40 bg-nominal/10 text-nominal", dot: "bg-nominal" },
  deviation: { label: "Deviation", cls: "border-caution/45 bg-caution/10 text-caution", dot: "bg-caution" },
  marked_deviation: { label: "Marked deviation", cls: "border-critical/50 bg-critical/12 text-critical", dot: "bg-critical" },
  insufficient_data: { label: "Not enough data", cls: "border-bulkhead text-ink-3", dot: "bg-ink-3" },
  info: { label: "Context", cls: "border-bulkhead text-ink-2", dot: "bg-ink-2" },
};

export function SystemStatusPill({ status, compact = false }: { status: SystemStatus | "info"; compact?: boolean }) {
  const s = SYSTEM_STATUS[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap", s.cls)}>
      {status === "insufficient_data" ? <CircleDashed className="size-3" aria-hidden /> : <span className={cn("size-2 rounded-full", s.dot)} aria-hidden />}
      {compact ? <span className="sr-only">{s.label}</span> : s.label}
    </span>
  );
}

export function SimulatedBanner({ children }: { children?: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-dashed border-caution/50 bg-caution/5 px-4 py-3 text-sm text-ink-2">
      <FlaskConical className="mt-0.5 size-4 shrink-0 text-caution" aria-hidden />
      <p>
        <span className="font-medium text-foreground">Simulated data, experimental decision support.</span>{" "}
        {children ?? "Crew members are fictional. Nothing here is a diagnosis or clinically validated, and serious findings go to the flight surgeon."}
      </p>
    </div>
  );
}

/** URL-backed selection (e.g. ?astronaut=AST-02), so links from the assistant open the right view. */
export function useParamState(name: string): [string | null, (value: string | null) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const value = params.get(name);
  const set = useCallback(
    (v: string | null) => {
      const next = new URLSearchParams(params.toString());
      if (v) next.set(name, v);
      else next.delete(name);
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, router, pathname, name],
  );
  return [value, set];
}

export function CrewPicker({ value, onChange, allowAll = false, label = "Crew member" }: {
  value: string | null;
  onChange: (id: string | null) => void;
  allowAll?: boolean;
  label?: string;
}) {
  const crew = useAstronauts();
  const options = crew.data ?? [];
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
      {allowAll && (
        <button
          type="button"
          role="radio"
          aria-checked={value === null}
          onClick={() => onChange(null)}
          className={cn("rounded-md border px-2.5 py-1 text-sm", value === null ? "border-telemetry bg-telemetry/10 text-foreground" : "border-bulkhead text-ink-2 hover:text-foreground")}
        >
          Whole crew
        </button>
      )}
      {options.map((a) => (
        <button
          key={a.id}
          type="button"
          role="radio"
          aria-checked={value === a.id}
          onClick={() => onChange(a.id)}
          className={cn(
            "inline-flex items-center gap-2 rounded-md border px-2.5 py-1 text-sm",
            value === a.id ? "border-telemetry bg-telemetry/10 text-foreground" : "border-bulkhead text-ink-2 hover:text-foreground",
          )}
        >
          <span className="size-2 rounded-full" style={{ background: crewColor(a.id) }} aria-hidden />
          {a.name}
          <span className="text-xs text-ink-3">{a.id}</span>
        </button>
      ))}
    </div>
  );
}

export function Kv({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}
