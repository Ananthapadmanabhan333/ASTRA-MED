"use client";

import { Bell, Check } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { OriginChip, PriorityBadge, SandboxTag, SeverityDot } from "@/components/mc/chips";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAlertCenter, useAlertCenterAction, useMissionEvents } from "@/lib/api/mission-hooks";
import type { MissionAlert, MissionEvent } from "@/lib/api/types";
import { useCan } from "@/lib/auth/store";
import { relativeTime, utcTime } from "@/lib/format";
import { useLive } from "@/lib/live/store";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

function AlertItem({ a, onNavigate }: { a: MissionAlert; onNavigate: () => void }) {
  const canManage = useCan("alerts:manage");
  const ack = useAlertCenterAction("acknowledge");
  const now = useNow(15_000);
  return (
    <li className="flex gap-3 border-b border-bulkhead/50 py-3 last:border-0">
      <PriorityBadge priority={a.priority} compact />
      <div className="min-w-0 flex-1">
        <Link
          href={a.context === "simulation" ? "/simulation" : `/alerts?alert=${a.id}`}
          onClick={onNavigate}
          className="line-clamp-2 text-sm font-medium hover:text-telemetry"
        >
          {a.title}
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
          {a.context === "simulation" ? <SandboxTag /> : <OriginChip origin={a.data_origin} />}
          <span>{a.source_label}</span>
          <span aria-hidden>/</span>
          <span>{now ? relativeTime(a.created_at, now) : utcTime(a.created_at)}</span>
          {a.status === "acknowledged" && <span className="text-ink-2">acknowledged</span>}
        </div>
      </div>
      {canManage && a.status === "open" && (
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label={`Acknowledge ${a.title}`}
          title="Acknowledge"
          disabled={ack.isPending}
          onClick={() =>
            ack.mutate({ id: a.id }, { onError: (e) => toast.error(e instanceof Error ? e.message : "Could not acknowledge") })
          }
        >
          <Check aria-hidden />
        </Button>
      )}
    </li>
  );
}

function EventItem({ e }: { e: MissionEvent }) {
  return (
    <li className="flex gap-2.5 border-b border-bulkhead/50 py-2.5 last:border-0">
      <SeverityDot severity={e.severity} className="mt-1.5" />
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-sm">{e.title}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
          <span className="tabular-nums">{utcTime(e.received_at)} UTC</span>
          <span>{e.source_label}</span>
          {e.context === "simulation" && <span className="text-sandbox">sandbox</span>}
          {e.occurrences > 1 && <span>x{e.occurrences}</span>}
        </p>
      </div>
    </li>
  );
}

/** Bell in the mission header: unresolved alerts from every module and the live event feed. */
export function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const unread = useLive((s) => s.unread);
  const markRead = useLive((s) => s.markRead);
  const live = useLive((s) => s.missionEvents);
  const allowed = useCan("health:read");
  const alerts = useAlertCenter({ status: ["open", "acknowledged"] });
  const recent = useMissionEvents({ hours: 12, limit: 40 }, open && live.length < 10);
  if (!allowed) return null;
  const items = alerts.data ?? [];
  const events = live.length >= 10 ? live : [...live, ...(recent.data ?? []).filter((e) => !live.some((l) => l.id === e.id))];
  const urgent = items.filter((a) => a.status === "open" && a.priority <= 2).length;

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (v) markRead();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="relative" aria-label={`Notifications, ${urgent} urgent`}>
          <Bell aria-hidden />
          {(unread > 0 || urgent > 0) && (
            <span
              className={cn(
                "absolute -top-0.5 -right-0.5 min-w-4 rounded-full px-1 text-[10px] leading-4 font-semibold tabular-nums",
                urgent > 0 ? "bg-critical text-[#2a0606]" : "bg-telemetry text-primary-foreground",
              )}
            >
              {urgent > 0 ? urgent : unread}
            </span>
          )}
        </Button>
      </DialogTrigger>
      <DialogContent className="top-0 right-0 left-auto flex h-dvh max-h-dvh w-full max-w-md translate-x-0 translate-y-0 flex-col gap-0 rounded-none border-y-0 border-r-0 border-l border-bulkhead bg-sidebar p-0 sm:max-w-md">
        <div className="border-b border-bulkhead px-5 pt-5 pb-3">
          <DialogTitle className="font-heading text-lg">Notification centre</DialogTitle>
          <DialogDescription className="text-sm text-ink-2">
            Unresolved alerts from every module and the latest mission events.
          </DialogDescription>
        </div>
        <Tabs defaultValue="alerts" className="flex min-h-0 flex-1 flex-col">
          <TabsList className="mx-5 mt-3">
            <TabsTrigger value="alerts">Unresolved alerts ({items.length})</TabsTrigger>
            <TabsTrigger value="activity">Activity</TabsTrigger>
          </TabsList>
          <TabsContent value="alerts" className="scroll-quiet min-h-0 flex-1 overflow-y-auto px-5">
            {items.length === 0 ? (
              <p className="py-8 text-center text-sm text-ink-2">
                {alerts.isPending ? "Loading alerts" : "No unresolved alerts. New ones appear here as they open."}
              </p>
            ) : (
              <ul>
                {items.slice(0, 40).map((a) => (
                  <AlertItem key={a.id} a={a} onNavigate={() => setOpen(false)} />
                ))}
              </ul>
            )}
          </TabsContent>
          <TabsContent value="activity" className="scroll-quiet min-h-0 flex-1 overflow-y-auto px-5">
            {events.length === 0 ? (
              <p className="py-8 text-center text-sm text-ink-2">No mission events in the last 12 hours.</p>
            ) : (
              <ul>
                {events.slice(0, 50).map((e) => (
                  <EventItem key={e.id} e={e} />
                ))}
              </ul>
            )}
          </TabsContent>
        </Tabs>
        <div className="flex gap-2 border-t border-bulkhead px-5 py-3">
          <Button asChild size="sm" className="flex-1" onClick={() => setOpen(false)}>
            <Link href="/alerts">Open alert centre</Link>
          </Button>
          <Button asChild size="sm" variant="outline" className="flex-1" onClick={() => setOpen(false)}>
            <Link href="/timeline">Situational awareness</Link>
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
