"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCan } from "@/lib/auth/store";

import { api, unwrap } from "./client";
import type { AlertCenterStatus, MissionContext, SimInject, SimStart, SimTelemetryReading } from "./types";

/** Query keys for phase 6 data, invalidated by mission_event / mission_alert / sim_state socket messages. */
export const mcKeys = {
  overview: ["mc-overview"] as const,
  crew: ["mc-crew"] as const,
  events: (f: EventFilters) => ["mc-events", f] as const,
  allEvents: ["mc-events"] as const,
  timeline: (f: TimelineFilters) => ["mc-timeline", f] as const,
  allTimeline: ["mc-timeline"] as const,
  alerts: (f: AlertCenterFilters) => ["mc-alerts", f] as const,
  allAlerts: ["mc-alerts"] as const,
  alert: (id: string) => ["mc-alert", id] as const,
  summary: (context: MissionContext | null, sim?: string | null) => ["mc-alert-summary", context, sim ?? null] as const,
  allSummaries: ["mc-alert-summary"] as const,
  simCatalogue: ["sim-catalogue"] as const,
  simState: ["sim-state"] as const,
  simRuns: ["sim-runs"] as const,
  playback: (id: string) => ["sim-playback", id] as const,
  analytics: (f: AnalyticsFilters) => ["analytics", f] as const,
  system: ["platform-status"] as const,
  consistency: ["consistency"] as const,
};

export interface EventFilters {
  category?: string[];
  source?: string[];
  priority?: number[];
  astronaut_id?: string;
  context?: MissionContext;
  simulation_id?: string;
  hours?: number;
  q?: string;
  limit?: number;
}

export interface TimelineFilters {
  category?: string[];
  astronaut_id?: string;
  context?: MissionContext;
  simulation_id?: string;
  hours?: number;
  start?: string;
  end?: string;
}

export interface AlertCenterFilters {
  status?: AlertCenterStatus[];
  priority?: number[];
  source?: string[];
  classification?: string[];
  astronaut_id?: string;
  context?: MissionContext;
  simulation_id?: string;
  hours?: number;
}

export interface AnalyticsFilters {
  start?: string;
  end?: string;
  context: "operations" | "simulation" | "all";
  astronaut_id?: string;
}

const clean = <T extends object>(o: T) =>
  Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && v !== "" && v !== null)) as T;

export function useMissionControl() {
  return useQuery({
    queryKey: mcKeys.overview,
    queryFn: () => unwrap(api.GET("/api/mission-control/overview")),
    refetchInterval: 10_000,
    placeholderData: (prev) => prev,
  });
}

export function useCrewMonitoring() {
  return useQuery({
    queryKey: mcKeys.crew,
    queryFn: () => unwrap(api.GET("/api/crew/monitoring")),
    refetchInterval: 15_000,
    placeholderData: (prev) => prev,
  });
}

export function useMissionEvents(filters: EventFilters, enabled = true) {
  return useQuery({
    queryKey: mcKeys.events(filters),
    queryFn: () => unwrap(api.GET("/api/events", { params: { query: clean(filters) } })),
    refetchInterval: 20_000,
    placeholderData: (prev) => prev,
    enabled,
  });
}

export function useMissionTimeline(filters: TimelineFilters) {
  return useQuery({
    queryKey: mcKeys.timeline(filters),
    queryFn: () => unwrap(api.GET("/api/events/timeline", { params: { query: clean(filters) } })),
    refetchInterval: 30_000,
    placeholderData: (prev) => prev,
  });
}

export function useAlertCenter(filters: AlertCenterFilters) {
  return useQuery({
    queryKey: mcKeys.alerts(filters),
    queryFn: () => unwrap(api.GET("/api/alert-center", { params: { query: { ...clean(filters), limit: 300 } } })),
    refetchInterval: 15_000,
    placeholderData: (prev) => prev,
  });
}

export function useAlertCenterSummary(context: MissionContext | null = "operations", simulationId?: string | null) {
  return useQuery({
    queryKey: mcKeys.summary(context, simulationId),
    queryFn: () =>
      unwrap(
        api.GET("/api/alert-center/summary", {
          params: { query: clean({ context: context ?? undefined, simulation_id: simulationId ?? undefined }) },
        }),
      ),
    refetchInterval: 15_000,
  });
}

export function useAlertDetail(id: string | null) {
  return useQuery({
    queryKey: mcKeys.alert(id ?? ""),
    queryFn: () => unwrap(api.GET("/api/alert-center/{alert_id}", { params: { path: { alert_id: id! } } })),
    enabled: !!id,
  });
}

export function useAlertCenterAction(action: "acknowledge" | "resolve") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      unwrap(
        action === "acknowledge"
          ? api.POST("/api/alert-center/{alert_id}/acknowledge", {
              params: { path: { alert_id: id } },
              body: { note: note || null },
            })
          : api.POST("/api/alert-center/{alert_id}/resolve", {
              params: { path: { alert_id: id } },
              body: { note: note || null },
            }),
      ),
    onSettled: (_d, _e, vars) => {
      qc.invalidateQueries({ queryKey: mcKeys.allAlerts });
      qc.invalidateQueries({ queryKey: mcKeys.allSummaries });
      qc.invalidateQueries({ queryKey: mcKeys.alert(vars.id) });
      qc.invalidateQueries({ queryKey: mcKeys.overview });
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

// ------------------------------------------------------------------ simulation ----
export function useSimCatalogue() {
  return useQuery({
    queryKey: mcKeys.simCatalogue,
    queryFn: () => unwrap(api.GET("/api/mission-sim/catalogue")),
    staleTime: Infinity,
  });
}

/** REST fallback for the sandbox state; the socket's sim_state messages keep it current while connected. */
export function useSimStateQuery() {
  return useQuery({
    queryKey: mcKeys.simState,
    queryFn: () => unwrap(api.GET("/api/mission-sim/state")),
    refetchInterval: 5_000,
  });
}

export function useSimRuns() {
  return useQuery({
    queryKey: mcKeys.simRuns,
    queryFn: () => unwrap(api.GET("/api/mission-sim/runs", { params: { query: { limit: 20 } } })),
    refetchInterval: 15_000,
  });
}

export function usePlayback(id: string | null) {
  return useQuery({
    queryKey: mcKeys.playback(id ?? ""),
    queryFn: () =>
      unwrap(
        api.GET("/api/mission-sim/runs/{run_id}/playback", {
          params: { path: { run_id: id! }, query: { max_points: 240 } },
        }),
      ),
    enabled: !!id,
  });
}

function useSimInvalidate() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: mcKeys.simState });
    qc.invalidateQueries({ queryKey: mcKeys.simRuns });
    qc.invalidateQueries({ queryKey: mcKeys.allAlerts });
    qc.invalidateQueries({ queryKey: mcKeys.allSummaries });
    qc.invalidateQueries({ queryKey: mcKeys.allEvents });
  };
}

export function useStartSim() {
  const done = useSimInvalidate();
  return useMutation({
    mutationFn: (body: SimStart) => unwrap(api.POST("/api/mission-sim/runs", { body })),
    onSettled: done,
  });
}

export function useSimControl() {
  const done = useSimInvalidate();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: "pause" | "resume" | "stop" | "reset" }) => {
      const opts = { params: { path: { run_id: id } } };
      switch (action) {
        case "pause":
          return unwrap(api.POST("/api/mission-sim/runs/{run_id}/pause", opts));
        case "resume":
          return unwrap(api.POST("/api/mission-sim/runs/{run_id}/resume", opts));
        case "stop":
          return unwrap(api.POST("/api/mission-sim/runs/{run_id}/stop", opts));
        default:
          return unwrap(api.POST("/api/mission-sim/runs/{run_id}/reset", opts));
      }
    },
    onSettled: done,
  });
}

export function useSimSpeed() {
  const done = useSimInvalidate();
  return useMutation({
    mutationFn: ({ id, speed }: { id: string; speed: number }) =>
      unwrap(api.POST("/api/mission-sim/runs/{run_id}/speed", { params: { path: { run_id: id } }, body: { speed } })),
    onSettled: done,
  });
}

export function useSimInject() {
  const done = useSimInvalidate();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: SimInject }) =>
      unwrap(api.POST("/api/mission-sim/runs/{run_id}/inject", { params: { path: { run_id: id } }, body })),
    onSettled: done,
  });
}

export function useSimTelemetry() {
  const done = useSimInvalidate();
  return useMutation({
    mutationFn: ({ id, readings }: { id: string; readings: SimTelemetryReading[] }) =>
      unwrap(
        api.POST("/api/mission-sim/runs/{run_id}/telemetry", {
          params: { path: { run_id: id } },
          body: { readings, source: "manual" },
        }),
      ),
    onSettled: done,
  });
}

export function useSimAnalyze() {
  const done = useSimInvalidate();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/api/mission-sim/runs/{run_id}/analyze", { params: { path: { run_id: id } } })),
    onSettled: done,
  });
}

export function useSimReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, alertId, astronautId }: { id: string; alertId?: string; astronautId?: string }) =>
      unwrap(
        api.POST("/api/mission-sim/runs/{run_id}/report", {
          params: { path: { run_id: id } },
          body: { alert_id: alertId ?? null, astronaut_id: astronautId ?? null },
        }),
      ),
    onSettled: () => qc.invalidateQueries({ queryKey: ["reports"] }),
  });
}

// ------------------------------------------------------------------- analytics ----
export function useAnalytics(filters: AnalyticsFilters) {
  return useQuery({
    queryKey: mcKeys.analytics(filters),
    queryFn: () => unwrap(api.GET("/api/analytics/summary", { params: { query: clean(filters) } })),
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
}

// ---------------------------------------------------------------------- system ----
export function usePlatformStatus() {
  return useQuery({
    queryKey: mcKeys.system,
    queryFn: () => unwrap(api.GET("/api/system/status")),
    refetchInterval: 10_000,
    placeholderData: (prev) => prev,
  });
}

export function useConsistency() {
  const audit = useCan("audit:read");
  const control = useCan("simulation:control");
  const allowed = audit || control;
  return useQuery({
    queryKey: mcKeys.consistency,
    queryFn: () => unwrap(api.GET("/api/system/consistency")),
    enabled: allowed,
    staleTime: 30_000,
  });
}

export function useRepairConsistency() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/system/consistency/repair")),
    onSuccess: (data) => qc.setQueryData(mcKeys.consistency, data),
  });
}

export function useSimRun(id: string | null, live = false) {
  return useQuery({
    queryKey: ["sim-run", id],
    queryFn: () => unwrap(api.GET("/api/mission-sim/runs/{run_id}", { params: { path: { run_id: id! } } })),
    enabled: !!id,
    refetchInterval: live ? 5_000 : false,
  });
}

export function useSimFrame(id: string | null, at: string | null) {
  return useQuery({
    queryKey: ["sim-frame", id, at],
    queryFn: () =>
      unwrap(api.GET("/api/mission-sim/runs/{run_id}/frame", { params: { path: { run_id: id! }, query: { at: at! } } })),
    enabled: !!id && !!at,
    placeholderData: (prev) => prev,
    staleTime: Infinity,
  });
}
