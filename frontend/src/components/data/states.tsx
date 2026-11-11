"use client";

import { RefreshCw, WifiOff } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

export function LoadingState({
  label = "Loading",
  rows = 3,
  className,
}: {
  label?: string;
  rows?: number;
  className?: string;
}) {
  return (
    <div role="status" aria-live="polite" className={cn("space-y-2.5", className)}>
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-9 w-full bg-bulkhead/50" style={{ opacity: 1 - i * 0.18 }} />
      ))}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
}) {
  const api = error instanceof ApiError ? error : null;
  const heading = title ?? (api?.isNetwork ? "Monitoring API unreachable" : "Couldn't load this data");
  const message =
    api?.message ?? (error instanceof Error ? error.message : "An unexpected error occurred.");
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-start gap-3 rounded-md border border-critical/35 bg-critical/8 p-4 sm:flex-row sm:items-center",
        className,
      )}
    >
      <WifiOff className="size-5 shrink-0 text-critical" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">{heading}</p>
        <p className="text-sm text-ink-2">{message}</p>
      </div>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          <RefreshCw aria-hidden /> Retry
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
  icon,
  className,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-bulkhead px-6 py-8 text-center",
        className,
      )}
    >
      {icon && <div className="text-ink-3">{icon}</div>}
      <p className="text-sm font-medium text-foreground">{title}</p>
      {children && <p className="max-w-sm text-sm text-ink-2">{children}</p>}
      {action}
    </div>
  );
}

interface QueryLike<T> {
  data: T | undefined;
  error: unknown;
  isPending: boolean;
  refetch: () => unknown;
}

/** Standard loading → error → empty → content switch for a TanStack query. */
export function QueryView<T>({
  query,
  loading,
  isEmpty,
  empty,
  children,
}: {
  query: QueryLike<T>;
  loading?: ReactNode;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <>{loading ?? <LoadingState />}</>;
  if (query.error && query.data === undefined)
    return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (query.data === undefined) return <>{loading ?? <LoadingState />}</>;
  if (isEmpty?.(query.data)) return <>{empty ?? <EmptyState title="Nothing to show yet" />}</>;
  return <>{children(query.data)}</>;
}
