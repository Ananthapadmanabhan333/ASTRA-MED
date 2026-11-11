"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { WS_URL } from "@/lib/env";
import type { ConnectionState } from "@/lib/live/store";
import { useLive } from "@/lib/live/store";
import { cn } from "@/lib/utils";

const COPY: Record<ConnectionState, { label: string; detail: string; dot: string; text: string }> = {
  connecting: {
    label: "Connecting",
    detail: "Opening the live telemetry stream.",
    dot: "bg-ink-3",
    text: "text-ink-2",
  },
  live: {
    label: "Live",
    detail: "Receiving simulated telemetry every second.",
    dot: "bg-nominal",
    text: "text-nominal",
  },
  stale: {
    label: "Delayed",
    detail: "No telemetry for over 5 seconds. Values on screen may be out of date.",
    dot: "bg-caution",
    text: "text-caution",
  },
  reconnecting: {
    label: "Reconnecting",
    detail: "The live stream dropped. Retrying automatically.",
    dot: "bg-caution",
    text: "text-caution",
  },
  offline: {
    label: "Offline",
    detail: "Can't reach the telemetry stream. Start the backend; the dashboard keeps retrying.",
    dot: "bg-critical",
    text: "text-critical",
  },
};

export function ConnectionIndicator({ className }: { className?: string }) {
  const state = useLive((s) => s.connection);
  const attempts = useLive((s) => s.attempts);
  const copy = COPY[state];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          role="status"
          aria-live="polite"
          className={cn("inline-flex items-center gap-2 text-xs font-medium", copy.text, className)}
        >
          <span className="relative flex size-2.5">
            {state === "live" && (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-nominal/60 motion-reduce:hidden" />
            )}
            <span className={cn("relative inline-flex size-2.5 rounded-full", copy.dot)} />
          </span>
          {copy.label}
        </span>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-xs">
        <p>{copy.detail}</p>
        {attempts > 0 && state !== "live" && <p className="mt-1 opacity-80">Attempt {attempts}</p>}
        <p className="mt-1 break-all opacity-70">{WS_URL}</p>
      </TooltipContent>
    </Tooltip>
  );
}
