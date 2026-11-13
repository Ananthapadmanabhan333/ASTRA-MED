import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Dashboard data card. One header line (title, optional context on the right), a body, an optional
 * footer link. ``tone`` draws a status rail on the left; ``sandbox`` draws the amber test-range edge.
 */
export function DataCard({
  title,
  icon,
  meta,
  actions,
  children,
  footer,
  href,
  hrefLabel,
  tone,
  sandbox = false,
  className,
  bodyClassName,
  id,
}: {
  title: ReactNode;
  icon?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  href?: string;
  hrefLabel?: string;
  tone?: "critical" | "caution" | "advisory" | "nominal";
  sandbox?: boolean;
  className?: string;
  bodyClassName?: string;
  id?: string;
}) {
  const headingId = id ? `${id}-title` : undefined;
  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className={cn(
        "relative flex min-w-0 flex-col rounded-lg border border-bulkhead/80 bg-hull",
        sandbox && "sandbox-edge border-sandbox/40",
        className,
      )}
    >
      {tone && !sandbox && (
        <span
          aria-hidden
          className={cn("absolute inset-y-3 left-0 w-[3px] rounded-r", {
            "bg-critical": tone === "critical",
            "bg-caution": tone === "caution",
            "bg-advisory": tone === "advisory",
            "bg-nominal": tone === "nominal",
          })}
        />
      )}
      <header className="flex min-h-11 items-center gap-2 border-b border-bulkhead/60 px-4 py-2.5">
        {icon && <span className="text-ink-3 [&_svg]:size-4">{icon}</span>}
        <h2 id={headingId} className="min-w-0 truncate font-heading text-[15px] font-semibold tracking-tight">
          {title}
        </h2>
        {meta && <div className="ml-auto flex shrink-0 items-center gap-2 text-xs text-ink-3">{meta}</div>}
        {actions && <div className={cn("flex shrink-0 items-center gap-1.5", !meta && "ml-auto")}>{actions}</div>}
      </header>
      <div className={cn("min-w-0 flex-1 px-4 py-3", bodyClassName)}>{children}</div>
      {(footer || href) && (
        <footer className="flex items-center gap-3 border-t border-bulkhead/60 px-4 py-2 text-xs text-ink-3">
          {footer}
          {href && (
            <Link href={href} className="ml-auto font-medium text-telemetry hover:underline">
              {hrefLabel ?? "Open"}
            </Link>
          )}
        </footer>
      )}
    </section>
  );
}

/** A labelled figure. The label says what it is; the unit sits next to the number. */
export function Stat({
  label,
  value,
  unit,
  sub,
  tone,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: string;
  sub?: ReactNode;
  tone?: "critical" | "caution" | "advisory" | "nominal" | "telemetry" | "sandbox";
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <p className="truncate text-xs text-ink-3">{label}</p>
      <p
        className={cn("readout mt-1 text-2xl font-semibold text-foreground", {
          "text-critical": tone === "critical",
          "text-caution": tone === "caution",
          "text-advisory": tone === "advisory",
          "text-nominal": tone === "nominal",
          "text-telemetry": tone === "telemetry",
          "text-sandbox": tone === "sandbox",
        })}
      >
        {value}
        {unit && <span className="ml-1 font-sans text-xs font-normal text-ink-3">{unit}</span>}
      </p>
      {sub && <p className="mt-0.5 truncate text-xs text-ink-2">{sub}</p>}
    </div>
  );
}

/** Horizontal proportion bar with an accessible text equivalent. */
export function Meter({ value, max = 100, tone = "telemetry", label }: {
  value: number;
  max?: number;
  tone?: "critical" | "caution" | "advisory" | "nominal" | "telemetry" | "sandbox";
  label: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={max}
      className="h-1.5 w-full overflow-hidden rounded-full bg-bulkhead/60"
    >
      <div
        className={cn("h-full rounded-full", {
          "bg-critical": tone === "critical",
          "bg-caution": tone === "caution",
          "bg-advisory": tone === "advisory",
          "bg-nominal": tone === "nominal",
          "bg-telemetry": tone === "telemetry",
          "bg-sandbox": tone === "sandbox",
        })}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/** Shown in place of a dashboard section whose source is unavailable. */
export function Unavailable({ reason, className }: { reason?: string | null; className?: string }) {
  return (
    <p className={cn("rounded-md border border-dashed border-bulkhead px-3 py-4 text-sm text-ink-2", className)}>
      {reason ?? "This source is unavailable right now. The rest of the dashboard is unaffected."}
    </p>
  );
}
