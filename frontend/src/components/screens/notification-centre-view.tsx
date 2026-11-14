"use client";

import { Bell, CheckCheck, CheckCircle2, ExternalLink, Search, Settings } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Panel } from "@/components/data/panel";
import { LoadingState } from "@/components/data/states";
import { PriorityBadge } from "@/components/mc/chips";
import { Button } from "@/components/ui/button";
import { useAlertCenter, useAlertCenterAction, useAlertCenterSummary } from "@/lib/api/mission-hooks";
import { useCan } from "@/lib/auth/store";
import { utcDayTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type NotifTab = "all" | "unread" | "critical" | "ai" | "space";

const FALLBACK_NOTIFICATIONS = [
  {
    id: "A-1047",
    title: "Elevated Heart Rate (Dr. Alex Carter — 92 bpm vs 82 bpm baseline)",
    priority: 1 as const,
    severity: "critical" as const,
    status: "open" as const,
    source: "physiological_monitoring",
    sourceLabel: "Physiological Monitoring",
    createdAt: "2026-11-14T14:21:00Z",
    astronautId: "AST-01",
    href: "/twin?astronaut=AST-01",
  },
  {
    id: "A-1048",
    title: "Increased Solar Activity — C1.2 Solar Flare (NASA DONKI)",
    priority: 2 as const,
    severity: "caution" as const,
    status: "open" as const,
    source: "space_weather",
    sourceLabel: "NASA Space Weather",
    createdAt: "2026-11-14T11:14:00Z",
    astronautId: null,
    href: "/space",
  },
  {
    id: "A-1045",
    title: "AI 24h Forecast Advisory: AST-01 Heart Rate Projected at 94 ± 5 bpm",
    priority: 3 as const,
    severity: "advisory" as const,
    status: "acknowledged" as const,
    source: "predictive_forecast",
    sourceLabel: "AI Predictive Forecasting",
    createdAt: "2026-11-14T09:30:00Z",
    astronautId: "AST-01",
    href: "/intelligence?astronaut=AST-01",
  },
  {
    id: "A-1042",
    title: "Incident Report R-1047 Signed Off by Flight Surgeon",
    priority: 4 as const,
    severity: "info" as const,
    status: "resolved" as const,
    source: "reports",
    sourceLabel: "Medical Governance",
    createdAt: "2026-11-13T18:00:00Z",
    astronautId: "AST-01",
    href: "/reports",
  },
];

export function NotificationCentreView() {
  const [tab, setTab] = useState<NotifTab>("all");
  const [search, setSearch] = useState("");
  const [readIds, setReadIds] = useState<Set<string>>(new Set(["A-1042"]));

  const summary = useAlertCenterSummary("operations");
  const alerts = useAlertCenter({ context: "operations", hours: 168 });
  const ack = useAlertCenterAction("acknowledge");
  const resolve = useAlertCenterAction("resolve");
  const canWrite = useCan("alerts:write");

  const items = useMemo(() => {
    const live = (alerts.data ?? []).map((a) => ({
      id: a.id,
      title: a.title,
      priority: (a.priority as 1 | 2 | 3 | 4) ?? 3,
      severity: a.severity,
      status: a.status,
      source: a.source,
      sourceLabel: a.source_label,
      createdAt: a.created_at,
      astronautId: a.astronaut_id,
      href: a.astronaut_id ? `/twin?astronaut=${a.astronaut_id}` : "/alerts",
    }));
    return live.length > 0 ? live : FALLBACK_NOTIFICATIONS;
  }, [alerts.data]);

  const filtered = useMemo(() => {
    return items.filter((item) => {
      const isRead = readIds.has(item.id) || item.status === "resolved";
      if (tab === "unread" && isRead) return false;
      if (tab === "critical" && item.priority > 2) return false;
      if (tab === "ai" && !item.source.includes("anomaly") && !item.source.includes("forecast")) return false;
      if (tab === "space" && !item.source.includes("space") && !item.source.includes("environment")) return false;
      if (search.trim()) {
        const q = search.toLowerCase();
        return (
          item.title.toLowerCase().includes(q) ||
          item.id.toLowerCase().includes(q) ||
          item.sourceLabel.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [items, tab, search, readIds]);

  const unreadCount = items.filter((i) => !readIds.has(i.id) && i.status !== "resolved").length;

  function markAllRead() {
    setReadIds(new Set(items.map((i) => i.id)));
    toast.success("All notifications marked as read");
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs text-telemetry">
            <Bell className="size-4" aria-hidden />
            <span>Unified Mission Dispatch &amp; Escalation Inbox</span>
          </div>
          <h1 className="mt-1 font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Notification Centre
          </h1>
          <p className="text-sm text-ink-2">
            Real-time physiological alerts, AI early warnings, NASA DONKI solar events, and Flight Surgeon sign-offs
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" onClick={markAllRead}>
            <CheckCheck className="size-3.5" aria-hidden /> Mark All Read ({unreadCount})
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href="/settings">
              <Settings className="size-3.5" aria-hidden /> Escalation Rules
            </Link>
          </Button>
        </div>
      </div>

      {/* Summary KPI Strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Unread Dispatch Items</p>
          <p className="mt-1 font-mono text-2xl font-bold text-telemetry">{unreadCount}</p>
        </div>
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Open Mission Alerts</p>
          <p className="mt-1 font-mono text-2xl font-bold text-caution">
            {summary.data?.open ?? items.filter((i) => i.status === "open").length}
          </p>
        </div>
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">P1 / P2 High Priority</p>
          <p className="mt-1 font-mono text-2xl font-bold text-critical">
            {items.filter((i) => i.priority <= 2).length}
          </p>
        </div>
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Acknowledged / Resolved</p>
          <p className="mt-1 font-mono text-2xl font-bold text-nominal">
            {items.filter((i) => i.status !== "open").length}
          </p>
        </div>
      </div>

      {/* Filter Tabs & Search */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-bulkhead bg-hull/80 p-3.5">
        <div className="flex flex-wrap gap-1.5">
          {(
            [
              ["all", "All Notifications"],
              ["unread", `Unread (${unreadCount})`],
              ["critical", "Critical P1/P2"],
              ["ai", "AI Warnings"],
              ["space", "Space Weather"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={cn(
                "rounded-md px-3.5 py-1.5 text-xs font-semibold transition-colors",
                tab === key
                  ? "bg-telemetry text-abyss shadow-[0_0_12px_rgba(61,216,234,0.3)]"
                  : "bg-abyss/70 text-ink-2 hover:text-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="relative min-w-[220px]">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter notifications..."
            className="h-9 w-full rounded-lg border border-bulkhead bg-[#091526] pl-9 pr-3 text-xs text-foreground placeholder:text-ink-3 outline-none focus:border-telemetry"
          />
        </div>
      </div>

      {/* Notification Feed */}
      <Panel raised title="Notification Stream" description="Click any notification to inspect telemetry or acknowledge/resolve.">
        {alerts.isPending ? (
          <LoadingState rows={5} />
        ) : filtered.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-3">No notifications match the selected filter.</p>
        ) : (
          <ul className="divide-y divide-bulkhead/60">
            {filtered.map((n) => {
              const isUnread = !readIds.has(n.id) && n.status !== "resolved";
              return (
                <li
                  key={n.id}
                  className={cn(
                    "flex flex-wrap items-center justify-between gap-4 py-3.5 px-3 rounded-lg transition-colors",
                    isUnread ? "bg-telemetry/5" : "opacity-85",
                  )}
                >
                  <div className="flex items-start gap-3">
                    <PriorityBadge priority={n.priority} compact />
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs font-bold text-telemetry">{n.id}</span>
                        <span className="text-sm font-semibold text-foreground">{n.title}</span>
                        {isUnread && (
                          <span className="size-2 rounded-full bg-telemetry" title="Unread" aria-label="Unread" />
                        )}
                      </div>
                      <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-3">
                        <span>{n.sourceLabel}</span>
                        <span>·</span>
                        <span className="font-mono">{utcDayTime(n.createdAt)} UTC</span>
                        <span>·</span>
                        <span className="capitalize text-ink-2">Status: {n.status}</span>
                      </p>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {canWrite && n.status === "open" && !n.id.startsWith("A-") && (
                      <Button
                        size="xs"
                        variant="outline"
                        disabled={ack.isPending}
                        onClick={() =>
                          ack.mutate(
                            { id: n.id, note: "Acknowledged from Notification Centre" },
                            { onSuccess: () => toast.success(`Alert ${n.id} acknowledged`) },
                          )
                        }
                      >
                        Acknowledge
                      </Button>
                    )}
                    {canWrite && n.status !== "resolved" && !n.id.startsWith("A-") && (
                      <Button
                        size="xs"
                        variant="outline"
                        disabled={resolve.isPending}
                        onClick={() =>
                          resolve.mutate(
                            { id: n.id, note: "Resolved from Notification Centre" },
                            { onSuccess: () => toast.success(`Alert ${n.id} resolved`) },
                          )
                        }
                      >
                        Resolve
                      </Button>
                    )}
                    {isUnread && (
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() => setReadIds((prev) => new Set([...prev, n.id]))}
                      >
                        <CheckCircle2 className="size-3.5 text-nominal" aria-hidden /> Mark read
                      </Button>
                    )}
                    <Button asChild size="xs" variant="outline">
                      <Link href={n.href}>
                        Open <ExternalLink className="ml-1 size-3" aria-hidden />
                      </Link>
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </div>
  );
}
