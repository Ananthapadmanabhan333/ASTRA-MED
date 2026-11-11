"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";

import { keys } from "@/lib/api/hooks";
import type { AstronautSummary, WsAlert, WsServerMessage } from "@/lib/api/types";
import { WS_URL } from "@/lib/env";
import { fmt } from "@/lib/format";
import { pushEcg } from "@/lib/live/ecg-buffer";
import { LiveSocket } from "@/lib/live/socket";
import { useLive } from "@/lib/live/store";

/**
 * Owns the single WebSocket connection. Feeds the live store and ECG buffer, keeps REST
 * caches fresh when alerts or scenarios change, and raises alert notifications.
 */
export function LiveBridge() {
  const qc = useQueryClient();
  const router = useRouter();

  useEffect(() => {
    const { receive, setConnection } = useLive.getState();

    const nameOf = (id: string) =>
      qc.getQueryData<AstronautSummary[]>(keys.astronauts)?.find((a) => a.id === id)?.name ?? id;

    const notify = (msg: WsAlert) => {
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

    const socket = new LiveSocket(WS_URL, {
      onState: setConnection,
      onMessage: (msg: WsServerMessage, at: number) => {
        if (msg.type === "vitals") msg.ecg.forEach(pushEcg);
        receive(msg, at);
        if (msg.type === "alert") {
          notify(msg);
          qc.invalidateQueries({ queryKey: keys.allAlerts });
          qc.invalidateQueries({ queryKey: keys.astronauts });
          qc.invalidateQueries({ queryKey: keys.mission });
          qc.invalidateQueries({ queryKey: keys.snapshot(msg.alert.astronaut_id) });
        } else if (msg.type === "simulation") {
          qc.invalidateQueries({ queryKey: keys.events });
          qc.invalidateQueries({ queryKey: keys.mission });
          qc.invalidateQueries({ queryKey: ["snapshot"] });
          qc.invalidateQueries({ queryKey: ["insights"] });
        }
      },
    });
    socket.connect();
    return () => socket.close();
  }, [qc, router]);

  return null;
}
