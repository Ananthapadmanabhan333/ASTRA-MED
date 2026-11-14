"use client";

import { Database, ServerCog, Wrench } from "lucide-react";
import { toast } from "sonner";

import { ErrorState, LoadingState } from "@/components/data/states";
import { DataCard, Stat } from "@/components/mc/card";
import { ErrorBoundary } from "@/components/mc/error-boundary";
import { Button } from "@/components/ui/button";
import { useConsistency, usePlatformStatus, useRepairConsistency } from "@/lib/api/mission-hooks";
import type { ConsistencyReport, PlatformStatus } from "@/lib/api/types";
import { useCan } from "@/lib/auth/store";
import { fmt, relativeTime, utcDayTime } from "@/lib/format";
import { useLive } from "@/lib/live/store";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

import { ConnectivityList } from "./command-dashboard";

const CHECK_TONE: Record<ConsistencyReport["status"], string> = {
  ok: "text-nominal",
  repaired: "text-telemetry",
  warning: "text-caution",
  error: "text-critical",
};

interface CollectorView {
  name: string;
  label: string;
  interval_s: number | null;
  runs: number;
  failures: number;
  last_run_at: string | null;
  last_ok_at: string | null;
  last_error: string | null;
  last_duration_ms: number | null;
  state: string;
}

function Collectors({ s }: { s: PlatformStatus }) {
  const now = useNow(5_000);
  const o = s.orchestrator as { queue_depth: number; processed: number; errors: number; dropped: number; events: Record<string, number>; collectors: CollectorView[] };
  return (
    <DataCard title="Event orchestration" icon={<ServerCog />} meta={`queue ${o.queue_depth}, ${o.processed} processed`}>
      <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Events stored" value={o.events.created ?? 0} />
        <Stat label="Duplicates merged" value={o.events.merged ?? 0} />
        <Stat label="Clock skew clamped" value={o.events.clock_skew_clamped ?? 0} />
        <Stat label="Processing errors" value={o.errors} tone={o.errors ? "caution" : undefined} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-ink-3">
            <tr><th className="py-1 pr-3 font-medium">Producer</th><th className="pr-3 font-medium">State</th><th className="pr-3 text-right font-medium">Runs</th><th className="pr-3 text-right font-medium">Failures</th><th className="pr-3 font-medium">Last success</th><th className="font-medium">Last error</th></tr>
          </thead>
          <tbody>
            {o.collectors.map((c) => (
              <tr key={c.name} className="border-t border-bulkhead/40 align-top">
                <td className="py-1.5 pr-3">{c.label}{c.interval_s ? <span className="block text-xs text-ink-3">every {fmt(c.interval_s, 0)} s</span> : <span className="block text-xs text-ink-3">change hook</span>}</td>
                <td className={cn("pr-3", c.state === "ok" ? "text-nominal" : c.state === "degraded" ? "text-caution" : "text-ink-2")}>{c.state}</td>
                <td className="pr-3 text-right tabular-nums">{c.runs}</td>
                <td className="pr-3 text-right tabular-nums">{c.failures}</td>
                <td className="pr-3 text-ink-2">{c.last_ok_at && now ? relativeTime(c.last_ok_at, now) : "—"}</td>
                <td className="max-w-xs truncate text-xs text-ink-3" title={c.last_error ?? undefined}>{c.last_error ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </DataCard>
  );
}

function Consistency() {
  const allowed = useCan("audit:read");
  const operator = useCan("simulation:control");
  const canRepair = useCan("system:maintain");
  const q = useConsistency();
  const repair = useRepairConsistency();
  if (!allowed && !operator) {
    return (
      <DataCard title="Database consistency" icon={<Database />}>
        <p className="text-sm text-ink-2">Consistency checks are available to mission operators and administrators.</p>
      </DataCard>
    );
  }
  const r = q.data;
  return (
    <DataCard
      title="Database consistency"
      icon={<Database />}
      meta={r ? <span className={CHECK_TONE[r.status]}>{r.status}</span> : undefined}
      actions={canRepair &&
        <Button size="sm" variant="outline" disabled={repair.isPending}
          onClick={() => repair.mutate(undefined, { onSuccess: (d) => toast.success(`Checks ${d.status}`), onError: (e) => toast.error(e instanceof Error ? e.message : "Repair failed") })}>
          <Wrench aria-hidden /> Check and repair
        </Button>
      }
      footer={r ? `Checked ${utcDayTime(r.ran_at)} UTC${r.repair ? ", with repair" : ", read-only"}` : undefined}
    >
      {q.isPending ? <LoadingState rows={4} /> : q.error && !r ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : r ? (
        <ul className="space-y-2">
          {r.checks.map((c) => (
            <li key={c.key} className="grid grid-cols-[6rem_1fr] gap-3 text-sm">
              <span className={cn("font-medium", CHECK_TONE[c.status])}>{c.status}{c.found ? ` (${c.found})` : ""}</span>
              <span>
                {c.label}
                <span className="block text-xs text-ink-3">{c.detail}{c.repaired ? ` Repaired ${c.repaired}.` : ""}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="mt-3 text-xs text-ink-3">Safe repairs only: mirrors, links, interrupted runs and orphaned sandbox samples. A modified incident report is reported, never repaired.</p>
    </DataCard>
  );
}

export function SystemView() {
  const q = usePlatformStatus();
  const connection = useLive((s) => s.connection);
  if (q.isPending) return <LoadingState rows={8} />;
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const s = q.data!;
  const tone = s.status === "ok" ? "nominal" : s.status === "degraded" ? "caution" : "critical";
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
          Deployment &amp; System Health
        </h1>
        <p className="text-sm text-ink-2">
          Live platform probes (/livez, /readyz), container topology, event orchestrator queues, and database consistency verification
        </p>
      </div>

      {/* Deployment Topology Strip */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Backend Service</p>
          <p className="mt-1 font-mono text-base font-bold text-nominal">FastAPI + Uvicorn (8000)</p>
          <p className="mt-1 text-xs text-ink-2">/livez &amp; /readyz probes nominal</p>
        </div>
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Frontend Runtime</p>
          <p className="mt-1 font-mono text-base font-bold text-telemetry">Next.js 16 App Router (3000)</p>
          <p className="mt-1 text-xs text-ink-2">WebSocket + React Query v5</p>
        </div>
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Persistence Engine</p>
          <p className="mt-1 font-mono text-base font-bold text-foreground">SQLite WAL + Artifacts</p>
          <p className="mt-1 text-xs text-ink-2">ACID transactions + SHA-256 digests</p>
        </div>
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Container &amp; CI Pipeline</p>
          <p className="mt-1 font-mono text-base font-bold text-nominal">Docker Compose Ready</p>
          <p className="mt-1 text-xs text-ink-2">Full 7-gate selfcheck suite</p>
        </div>
      </div>

      <section aria-label="Platform summary" className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-bulkhead/80 bg-bulkhead/60 md:grid-cols-4">
        <div className="bg-hull px-4 py-3"><Stat label="Platform" value={s.status} tone={tone} sub={`${s.components.filter((c) => c.status === "ok").length} of ${s.components.length} components ok`} /></div>
        <div className="bg-hull px-4 py-3"><Stat label="Version" value={s.version} sub={s.environment} /></div>
        <div className="bg-hull px-4 py-3"><Stat label="API uptime" value={fmt(s.uptime_s / 3600, 1)} unit="h" /></div>
        <div className="bg-hull px-4 py-3"><Stat label="This browser's stream" value={connection} tone={connection === "live" ? "nominal" : "caution"} sub="reconnects automatically" /></div>
      </section>
      <div className="grid gap-4 xl:grid-cols-2">
        <ErrorBoundary label="Components">
          <DataCard title="Component health" meta={`checked ${utcDayTime(s.generated_at)} UTC`}>
            <ConnectivityList components={s.components} />
          </DataCard>
        </ErrorBoundary>
        <ErrorBoundary label="Consistency"><Consistency /></ErrorBoundary>
        <div className="xl:col-span-2"><ErrorBoundary label="Orchestration"><Collectors s={s} /></ErrorBoundary></div>
      </div>
    </div>
  );
}
