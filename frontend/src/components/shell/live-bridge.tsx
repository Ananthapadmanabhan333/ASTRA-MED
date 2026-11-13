"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";

import { keys } from "@/lib/api/hooks";
import { mcKeys } from "@/lib/api/mission-hooks";
import type { AstronautSummary, WsAlert, WsMissionAlert, WsServerMessage } from "@/lib/api/types";
import { WS_URL } from "@/lib/env";
import { fmt } from "@/lib/format";
import { pushEcg } from "@/lib/live/ecg-buffer";
import { LiveSocket } from "@/lib/live/socket";
import { useLive } from "@/lib/live/store";

const BATCH_MS = 1500;

/**
 * Owns the single WebSocket connection. Feeds the live store and ECG buffer, keeps REST caches
 * fresh when alerts, scenarios, mission events or the sandbox change, and raises notifications.
 * After a reconnect (a new hello) every mission query is refetched, so events missed while the
 * socket was down are picked up from the REST history.
 */
export function LiveBridge() {
  const qc = useQueryClient();
  const router = useRouter();

  useEffect(() => {
    const { receive, setConnection } = useLive.getState();
    let helloCount = 0;

    // Batch cache invalidations: a fast sandbox run can emit many events per second.
    const pending = new Set<string>();
    let timer: ReturnType<typeof setTimeout> | null = null;
    const invalidate = (...queryKeys: (readonly unknown[])[]) => {
      for (const k of queryKeys) pending.add(JSON.stringify(k));
      if (timer) return;
      timer = setTimeout(() => {
        timer = null;
        for (const k of pending) qc.invalidateQueries({ queryKey: JSON.parse(k) as unknown[] });
        pending.clear();
      }, BATCH_MS);
    };

    const nameOf = (id: string) =>
      qc.getQueryData<AstronautSummary[]>(keys.astronauts)?.find((a) => a.id === id)?.name ?? id;

    const notifyRule = (msg: WsAlert) => {
      if (msg.event !== "opened" && msg.event !== "escalated") return;
      const a = msg.alert;
      const verb = msg.event === "escalated" ? "Escalated to critical" : `New ${a.severity} alert`;
      const show = a.severity === "critical" ? toast.error : a.severity === "caution" ? toast.warning : toast.info;
      show(`${verb}: ${a.title}`, {
        id: `alert-${a.id}`,
        description: `${nameOf(a.astronaut_id)}, ${fmt(a.trigger_value, 1)} ${a.unit}. Simulated data.`,
        duration: a.severity === "critical" ? 12_000 : 7_000,
        action: { label: "View", onClick: () => router.push(`/crew/${a.astronaut_id}`) },
      });
    };

    // Rule alerts on the live stream already raise a toast above; this covers the other sources
    // (AI, NASA, environment) and the simulation sandbox.
    const notifyUnified = (msg: WsMissionAlert) => {
      const a = msg.alert;
      if (msg.event !== "opened" && msg.event !== "escalated") return;
      if (a.source === "physiological_monitoring" && a.context === "operations") return;
      if (a.priority > 3) return;
      const sandbox = a.context === "simulation";
      const show = a.priority === 1 ? toast.error : a.priority === 2 ? toast.warning : toast.info;
      show(a.title, {
        id: `malert-${a.id}`,
        description: `${a.priority_label} priority. ${a.classification_label}${sandbox ? " (simulation sandbox)" : ""}.`,
        duration: a.priority <= 2 ? 9_000 : 6_000,
        action: { label: "Open", onClick: () => router.push(sandbox ? "/simulation" : `/alerts?alert=${a.id}`) },
      });
    };

    const socket = new LiveSocket(WS_URL, {
      onState: setConnection,
      onMessage: (msg: WsServerMessage, at: number) => {
        if (msg.type === "vitals") msg.ecg.forEach(pushEcg);
        receive(msg, at);
        switch (msg.type) {
          case "hello":
            helloCount += 1;
            if (helloCount > 1) {
              // Reconnected: refetch everything that may have changed while we were away.
              invalidate(mcKeys.allEvents, mcKeys.allAlerts, mcKeys.allSummaries, mcKeys.overview, mcKeys.crew,
                keys.allAlerts, keys.mission, mcKeys.simState);
            }
            break;
          case "alert":
            notifyRule(msg);
            qc.invalidateQueries({ queryKey: keys.allAlerts });
            qc.invalidateQueries({ queryKey: keys.astronauts });
            qc.invalidateQueries({ queryKey: keys.mission });
            qc.invalidateQueries({ queryKey: keys.snapshot(msg.alert.astronaut_id) });
            break;
          case "simulation":
            qc.invalidateQueries({ queryKey: keys.events });
            qc.invalidateQueries({ queryKey: keys.mission });
            qc.invalidateQueries({ queryKey: ["snapshot"] });
            qc.invalidateQueries({ queryKey: ["insights"] });
            break;
          case "mission_event":
            invalidate(mcKeys.allEvents, mcKeys.allTimeline, mcKeys.overview);
            break;
          case "mission_alert":
            notifyUnified(msg);
            invalidate(mcKeys.allAlerts, mcKeys.allSummaries, mcKeys.overview, mcKeys.crew, mcKeys.alert(msg.alert.id));
            break;
          case "sim_state":
            qc.setQueryData(mcKeys.simState, msg.state);
            if (!msg.state.active) invalidate(mcKeys.simRuns);
            break;
        }
      },
    });
    socket.connect();
    return () => {
      if (timer) clearTimeout(timer);
      socket.close();
    };
  }, [qc, router]);

  return null;
}
