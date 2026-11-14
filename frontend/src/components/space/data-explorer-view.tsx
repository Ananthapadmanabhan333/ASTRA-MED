"use client";

import { ArrowRight, Database, ExternalLink, KeyRound, RefreshCw, Search, Sun, Thermometer } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useOsdrStudies, useSpaceSources, useSpaceSync } from "@/lib/api/hooks";
import type { DataSourceStatus } from "@/lib/api/types";
import { fmt } from "@/lib/format";
import { cn } from "@/lib/utils";

import { CATEGORY, CategoryBadge, FreshnessBadge, When, ZoneSelect } from "./provenance";

const HEALTH_CLS: Record<string, string> = {
  healthy: "text-nominal",
  degraded: "text-caution",
  offline: "text-critical",
  unknown: "text-ink-3",
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

function SourceCard({ s }: { s: DataSourceStatus }) {
  const sync = useSpaceSync();
  return (
    <Panel
      raised
      title={s.name}
      description={s.provider}
      actions={
        <Button
          size="sm"
          variant="outline"
          disabled={sync.isPending || !!s.running}
          onClick={() =>
            sync.mutate({ source: s.id as "donki" | "eda" | "osdr" }, {
              onSuccess: () => toast.success(`${s.id.toUpperCase()} synchronised`),
              onError: (e) => toast.error(e instanceof Error ? e.message : "Synchronisation failed"),
            })
          }
        >
          <RefreshCw className={cn(sync.isPending || s.running ? "animate-spin" : "")} aria-hidden />
          {s.running ? `Running ${s.running}` : sync.isPending ? "Synchronising" : "Synchronise now"}
        </Button>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          {s.categories.map((c) => <CategoryBadge key={c} category={c} />)}
          <FreshnessBadge freshness={{ source_id: s.id, mode: s.availability, message: s.availability_message, retrieved_at: s.health.last_success ?? null }} />
        </div>
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 xl:grid-cols-4">
          <Field label="Collection period (stored)">
            {s.collection_start ? <><When iso={s.collection_start} kind="date" /> to <When iso={s.collection_end} kind="date" /></> : "nothing stored yet"}
          </Field>
          <Field label="Records stored">
            <span className="tabular-nums">{s.records.toLocaleString()}</span>
            {Object.keys(s.breakdown).length > 0 && (
              <span className="block text-xs text-ink-3">
                {Object.entries(s.breakdown).map(([k, v]) => `${k} ${v}`).join(" · ")}
              </span>
            )}
          </Field>
          <Field label="Update frequency">{s.update_frequency}</Field>
          <Field label="Data format">{s.data_format}</Field>
          <Field label="Measurement units">
            {Object.keys(s.units).length ? Object.entries(s.units).map(([k, v]) => `${k}: ${v}`).join("; ") : "not applicable (metadata)"}
          </Field>
          <Field label="Availability">
            <span className={HEALTH_CLS[s.health.status]}>{s.health.status}</span>
            <span className="block text-xs text-ink-3">{s.availability_message}</span>
          </Field>
          <Field label="Data quality">
            <span className="tabular-nums">
              {s.quality.records_received.toLocaleString()} received · {s.quality.invalid} invalid ({fmt(s.quality.invalid_rate * 100, 2)}%) ·{" "}
              {s.quality.duplicates.toLocaleString()} duplicates skipped
            </span>
            <span className="block text-xs text-ink-3">
              {s.quality.sync_runs} sync runs, {s.quality.failed_runs} failed; last: {s.quality.last_sync_status ?? "none"}
            </span>
          </Field>
          <Field label="Request health">
            <span className="tabular-nums text-xs text-ink-2">
              {s.health.requests} requests · {s.health.failures} failed · {s.health.cache_hits} cache hits
              {s.health.last_latency_ms != null && <> · {fmt(s.health.last_latency_ms, 0)} ms</>}
            </span>
            {s.health.last_error && <span className="block text-xs text-caution">Last error: {s.health.last_error}</span>}
          </Field>
        </dl>

        <div>
          <h3 className="text-xs font-medium text-ink-2">Endpoints (tried in order)</h3>
          <ul className="mt-1.5 space-y-1.5 text-sm">
            {s.endpoints.map((e) => (
              <li key={e.name} className="flex flex-wrap items-baseline gap-x-2">
                <span className={cn("size-2 shrink-0 rounded-full", e.available ? "bg-nominal" : "bg-caution")} aria-hidden />
                <code className="text-xs text-foreground">{e.base_url}</code>
                <span className="text-xs text-ink-3">{e.available ? "available" : `skipped: ${e.reason ?? "unavailable"}`}</span>
                {e.needs_key && <span className="inline-flex items-center gap-1 text-xs text-ink-3"><KeyRound className="size-3" aria-hidden />API key (server side)</span>}
                {e.rate_limit_remaining != null && <span className="text-xs text-ink-3">rate limit {e.rate_limit_remaining}/{e.rate_limit_limit ?? "?"} left</span>}
                <span className="basis-full pl-4 text-xs text-ink-3">{e.note}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <h3 className="text-xs font-medium text-ink-2">Licence and use</h3>
            <p className="mt-1 text-sm text-ink-2">{s.license}</p>
            <p className="mt-1 text-xs text-ink-3">{s.citation}</p>
            <a href={s.license_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs text-telemetry hover:underline">
              Provider terms <ExternalLink className="size-3" aria-hidden />
            </a>
          </div>
          <div>
            <h3 className="text-xs font-medium text-ink-2">Scientific limitations</h3>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-ink-2">
              {s.caveats.map((c) => <li key={c}>{c}</li>)}
            </ul>
          </div>
        </div>

        <details>
          <summary className="cursor-pointer text-xs text-ink-2">Recent synchronisation runs</summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[40rem] text-left text-xs">
              <thead className="text-ink-3">
                <tr>{["Started", "Task", "Status", "Endpoint", "Received", "New", "Updated", "Duplicates", "Invalid"].map((h) => <th key={h} className="py-1 pr-3 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="tabular-nums">
                {s.recent_runs.map((r) => (
                  <tr key={r.id} className="border-t border-bulkhead/40" title={r.error ?? undefined}>
                    <td className="py-1 pr-3 whitespace-nowrap"><When iso={r.started_at} suffix={false} /></td>
                    <td className="py-1 pr-3">{r.task}</td>
                    <td className={cn("py-1 pr-3", r.status === "failed" ? "text-critical" : r.status === "partial" ? "text-caution" : "text-nominal")}>{r.status}</td>
                    <td className="py-1 pr-3">{r.endpoint ?? "—"}</td>
                    <td className="py-1 pr-3">{r.records_received}</td>
                    <td className="py-1 pr-3">{r.records_new}</td>
                    <td className="py-1 pr-3">{r.records_updated}</td>
                    <td className="py-1 pr-3">{r.duplicates}</td>
                    <td className="py-1 pr-3">{r.invalid}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </div>
    </Panel>
  );
}

function StudyCatalogue() {
  const [topic, setTopic] = useState<string>("radiation");
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState<{ q?: string; live?: boolean }>({});
  const studies = useOsdrStudies({ topic: query.q ? undefined : topic, q: query.q, live: query.live, limit: 60 });
  const data = studies.data;
  return (
    <Panel
      title="OSDR study catalogue"
      description="Spaceflight and radiation biology studies in NASA's Open Science Data Repository. Metadata only: no study files are downloaded."
      actions={<><CategoryBadge category="metadata" /><FreshnessBadge freshness={data?.freshness} /></>}
    >
      <div className="flex flex-wrap items-center gap-3">
        <ToggleGroup type="single" value={query.q ? "" : topic} onValueChange={(v) => { if (v) { setTopic(v); setQuery({}); } }} variant="outline" size="sm" className="flex-wrap" aria-label="Topic">
          {(data?.topics ?? []).map((t) => <ToggleGroupItem key={t.key} value={t.key}>{t.label}</ToggleGroupItem>)}
        </ToggleGroup>
        <form className="flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); setQuery({ q: draft.trim() || undefined, live: !!draft.trim() }); }}>
          <label className="sr-only" htmlFor="osdr-q">Search OSDR</label>
          <input id="osdr-q" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Search OSDR (e.g. bone loss)"
            className="h-8 w-56 rounded-md border border-bulkhead bg-abyss/60 px-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" maxLength={120} />
          <Button size="sm" type="submit" variant="outline"><Search aria-hidden />Search</Button>
        </form>
      </div>
      <div className="mt-3">
        {studies.isPending ? (
          <LoadingState rows={5} />
        ) : studies.error && !data ? (
          <ErrorState error={studies.error} onRetry={() => studies.refetch()} />
        ) : !data?.items.length ? (
          <EmptyState title="No studies stored for this selection">Try another topic or a broader search.</EmptyState>
        ) : (
          <>
            <p className="mb-2 text-xs text-ink-3">{data.total} matching studies stored{query.q ? ` for "${query.q}" (also queried live from OSDR)` : ""}.</p>
            <div className="max-h-[36rem] overflow-auto">
              <table className="w-full min-w-[48rem] text-left text-sm">
                <caption className="sr-only">OSDR studies</caption>
                <thead className="sticky top-0 bg-hull text-xs text-ink-2">
                  <tr>{["Study", "Title", "Organism", "Type", "Mission", "Released"].map((h) => <th key={h} scope="col" className="py-2 pr-3 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {data.items.map((s) => (
                    <tr key={s.accession} className="border-t border-bulkhead/50 align-top">
                      <td className="py-1.5 pr-3 whitespace-nowrap"><a href={s.link} target="_blank" rel="noreferrer" className="text-telemetry hover:underline">{s.accession}</a></td>
                      <td className="py-1.5 pr-3">
                        {s.title}
                        {s.assay_type && <span className="block text-xs text-ink-3">{s.assay_type}</span>}
                      </td>
                      <td className="py-1.5 pr-3 text-ink-2">{s.organism ?? "—"}</td>
                      <td className="py-1.5 pr-3 text-ink-2">{s.project_type ?? "—"}</td>
                      <td className="py-1.5 pr-3 text-ink-2">{s.mission_name ?? "—"}</td>
                      <td className="py-1.5 pr-3 whitespace-nowrap text-ink-3"><When iso={s.release_date} kind="date" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}

export function DataExplorerView() {
  const q = useSpaceSources();
  const data = q.data;
  const [searchText, setSearchText] = useState("");
  const [pillFilter, setPillFilter] = useState<"all" | "osdr" | "donki" | "hrp" | "iss">("all");

  const boardCatalog = [
    {
      id: "donki",
      group: "donki" as const,
      title: "DONKI - Space Weather Events",
      desc: "Solar flares, CMEs, SEPs and geomagnetic storms.",
      meta: "Source: NASA CCMC · Updated: Live",
      icon: Sun,
      iconColor: "text-[#f97316]",
      href: "/space/datasets?dataset=donki",
    },
    {
      id: "osdr",
      group: "osdr" as const,
      title: "NASA OSDR - Space Biology",
      desc: "Spaceflight biological experiments and research datasets.",
      meta: "Source: NASA OSDR · 240+ Studies",
      icon: Database,
      iconColor: "text-telemetry",
      href: "/space/datasets?dataset=osdr",
    },
    {
      id: "iss",
      group: "iss" as const,
      title: "ISS Environmental Data",
      desc: "Cabin environment, CO₂, temperature and humidity.",
      meta: "Source: NASA EDA · Telemetry Feed",
      icon: Thermometer,
      iconColor: "text-nominal",
      href: "/space/datasets?dataset=eda",
    },
    {
      id: "hrp",
      group: "hrp" as const,
      title: "NASA Human Research Program (HRP)",
      desc: "Physiological adaptation benchmarks, radiation career limits, and clinical countermeasures.",
      meta: "Source: NASA HRP · Reference Corpus",
      icon: Database,
      iconColor: "text-[#c084fc]",
      href: "/space/datasets?dataset=hrp",
    },
  ];

  const filteredCatalog = boardCatalog.filter((item) => {
    if (pillFilter !== "all" && item.group !== pillFilter) return false;
    if (searchText.trim()) {
      const qLower = searchText.toLowerCase();
      return (
        item.title.toLowerCase().includes(qLower) ||
        item.desc.toLowerCase().includes(qLower) ||
        item.meta.toLowerCase().includes(qLower)
      );
    }
    return true;
  });

  return (
    <div className="space-y-5">
      {/* Header matching Screen 13 */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            NASA Data Explorer
          </h1>
          <p className="text-sm text-ink-2">Access and explore NASA open datasets</p>
        </div>
        <Button asChild size="sm" variant="outline">
          <Link href="/space/datasets">
            Dataset Details & Schema Inspector <ArrowRight className="ml-1 size-3.5" aria-hidden />
          </Link>
        </Button>
      </div>

      {/* Search & Category Filter Bar matching Screen 13 */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-bulkhead bg-hull/80 p-3.5">
        <div className="relative min-w-[240px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
          <input
            type="search"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Search NASA datasets..."
            className="h-9 w-full rounded-lg border border-bulkhead bg-[#091526] pl-9 pr-3 text-xs text-foreground placeholder:text-ink-3 outline-none focus:border-telemetry"
          />
        </div>

        <div className="flex flex-wrap gap-1.5">
          {(
            [
              ["all", "All"],
              ["osdr", "OSDR"],
              ["donki", "DONKI"],
              ["hrp", "HRP"],
              ["iss", "ISS Env."],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setPillFilter(key)}
              className={cn(
                "rounded-md px-3.5 py-1.5 text-xs font-semibold transition-colors",
                pillFilter === key
                  ? "bg-telemetry text-abyss shadow-[0_0_12px_rgba(61,216,234,0.3)]"
                  : "bg-abyss/70 text-ink-2 hover:text-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Screen 13 Highlighted Dataset Cards */}
      <div className="space-y-3">
        {filteredCatalog.map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.id}
              className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-bulkhead bg-hull/80 p-4 transition-colors hover:border-telemetry/50"
            >
              <div className="flex items-start gap-3.5">
                <div className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-bulkhead bg-abyss/80">
                  <Icon className={cn("size-5", item.iconColor)} aria-hidden />
                </div>
                <div>
                  <h2 className="text-base font-bold text-foreground">{item.title}</h2>
                  <p className="text-xs text-ink-2">{item.desc}</p>
                  <p className="mt-1 text-[11px] text-ink-3">{item.meta}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="rounded-full border border-nominal/40 bg-nominal/15 px-3 py-1 text-xs font-semibold text-nominal">
                  Active
                </span>
                <Button asChild size="sm" variant="outline">
                  <Link href={item.href}>Inspect</Link>
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {data && Object.entries(data.categories).map(([key]) => <CategoryBadge key={key} category={key as keyof typeof CATEGORY} />)}
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-ink-3">
          {data && (
            <span className="inline-flex items-center gap-1.5">
              <KeyRound className="size-3.5" aria-hidden />
              {data.api_key_configured ? "Personal NASA API key configured (kept on the server)" : "Using NASA's public DEMO_KEY (rate limited)"}
            </span>
          )}
          {data && <span>Background sync {data.sync_enabled ? "on" : "off"}</span>}
          <ZoneSelect />
        </div>
      </div>
      {q.isPending ? (
        <LoadingState rows={6} />
      ) : q.error && !data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : data ? (
        <>
          {data.sources.map((s) => <SourceCard key={s.id} s={s} />)}
          <Panel title="Evaluated, not integrated" description="Sources reviewed for this phase and why they are not used.">
            <ul className="space-y-2 text-sm">
              {data.evaluated.map((e) => (
                <li key={e.name}>
                  <a href={e.url} target="_blank" rel="noreferrer" className="text-telemetry hover:underline">{e.name}</a>
                  <span className="block text-xs text-ink-2">{e.status}</span>
                </li>
              ))}
            </ul>
          </Panel>
          <StudyCatalogue />
        </>
      ) : null}
    </div>
  );
}
