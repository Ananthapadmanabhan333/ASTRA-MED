"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCan } from "@/lib/auth/store";

import { api, unwrap } from "./client";
import type { AlertStatus, Metric, Severity, SimulationEventCreate, TimeRange } from "./types";

/** Query keys in one place so socket events can invalidate the right caches. */
export const keys = {
  mission: ["mission"] as const,
  system: ["system"] as const,
  astronauts: ["astronauts"] as const,
  snapshot: (id: string) => ["snapshot", id] as const,
  history: (id: string, range: TimeRange) => ["history", id, range] as const,
  sleep: (id: string, days: number) => ["sleep", id, days] as const,
  compare: (metric: Metric, range: TimeRange) => ["compare", metric, range] as const,
  radiation: (days: number) => ["radiation", days] as const,
  alerts: (filters: AlertFilters) => ["alerts", filters] as const,
  allAlerts: ["alerts"] as const,
  insights: (id?: string) => ["insights", id ?? "all"] as const,
  scenarios: ["scenarios"] as const,
  events: ["simulation-events"] as const,
};

export interface AlertFilters {
  status?: AlertStatus[];
  severity?: Severity[];
  astronaut_id?: string;
  hours?: number;
}

export function useMissionStatus() {
  // The mission strip is on every page; roles without crew health access must not poll it.
  const allowed = useCan("health:read");
  return useQuery({
    queryKey: keys.mission,
    queryFn: () => unwrap(api.GET("/api/mission/status")),
    refetchInterval: 10_000,
    enabled: allowed,
  });
}

export function useAstronauts() {
  return useQuery({
    queryKey: keys.astronauts,
    queryFn: () => unwrap(api.GET("/api/astronauts")),
    refetchInterval: 15_000,
  });
}

export function useSnapshot(id: string) {
  return useQuery({
    queryKey: keys.snapshot(id),
    queryFn: () =>
      unwrap(api.GET("/api/health/{astronaut_id}", { params: { path: { astronaut_id: id } } })),
    refetchInterval: 10_000,
  });
}

const HISTORY_REFRESH: Record<TimeRange, number> = {
  "1h": 15_000,
  "6h": 60_000,
  "24h": 120_000,
  "7d": 300_000,
};

export function useHistory(id: string, range: TimeRange, enabled = true) {
  return useQuery({
    queryKey: keys.history(id, range),
    queryFn: () =>
      unwrap(
        api.GET("/api/health/{astronaut_id}/history", {
          params: { path: { astronaut_id: id }, query: { range, max_points: 360 } },
        }),
      ),
    refetchInterval: HISTORY_REFRESH[range],
    placeholderData: (prev) => (prev?.astronaut_id === id ? prev : undefined),
    enabled,
  });
}

export function useSleep(id: string, days = 7) {
  return useQuery({
    queryKey: keys.sleep(id, days),
    queryFn: () =>
      unwrap(
        api.GET("/api/health/{astronaut_id}/sleep", {
          params: { path: { astronaut_id: id }, query: { days } },
        }),
      ),
    staleTime: 300_000,
  });
}

export function useComparison(metric: Metric, range: TimeRange) {
  return useQuery({
    queryKey: keys.compare(metric, range),
    queryFn: () =>
      unwrap(
        api.GET("/api/health/compare", { params: { query: { metric, range, max_points: 240 } } }),
      ),
    refetchInterval: HISTORY_REFRESH[range],
    placeholderData: (prev) => prev,
  });
}

export function useRadiation(days = 30) {
  return useQuery({
    queryKey: keys.radiation(days),
    queryFn: () => unwrap(api.GET("/api/radiation", { params: { query: { days } } })),
    refetchInterval: 30_000,
  });
}

export function useAlerts(filters: AlertFilters = {}) {
  return useQuery({
    queryKey: keys.alerts(filters),
    queryFn: () => unwrap(api.GET("/api/alerts", { params: { query: { ...filters, limit: 200 } } })),
    refetchInterval: 15_000,
    placeholderData: (prev) => prev,
  });
}

export function useInsights(astronautId?: string) {
  return useQuery({
    queryKey: keys.insights(astronautId),
    queryFn: () =>
      unwrap(
        api.GET("/api/insights", {
          params: { query: astronautId ? { astronaut_id: astronautId } : {} },
        }),
      ),
    refetchInterval: 30_000,
  });
}

export function useThresholds() {
  return useQuery({
    queryKey: ["thresholds"],
    queryFn: () => unwrap(api.GET("/api/monitoring/thresholds")),
    staleTime: Infinity,
  });
}

export function useScenarios() {
  return useQuery({
    queryKey: keys.scenarios,
    queryFn: () => unwrap(api.GET("/api/simulation/scenarios")),
    staleTime: Infinity,
  });
}

export function useSimulationEvents() {
  return useQuery({
    queryKey: keys.events,
    queryFn: () => unwrap(api.GET("/api/simulation/events", { params: { query: { hours: 48 } } })),
    refetchInterval: 10_000,
  });
}

// ---------------------------------------------------------------------- mutations --

export function useAlertAction(action: "acknowledge" | "resolve") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      unwrap(
        action === "acknowledge"
          ? api.POST("/api/alerts/{alert_id}/acknowledge", {
              params: { path: { alert_id: id } },
              body: { note: note || null },
            })
          : api.POST("/api/alerts/{alert_id}/resolve", {
              params: { path: { alert_id: id } },
              body: { note: note || null },
            }),
      ),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.allAlerts });
      qc.invalidateQueries({ queryKey: keys.astronauts });
      qc.invalidateQueries({ queryKey: keys.mission });
    },
  });
}

export function useStartScenario() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SimulationEventCreate) =>
      unwrap(api.POST("/api/simulation/events", { body })),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.events });
      qc.invalidateQueries({ queryKey: keys.mission });
    },
  });
}

export function useCancelScenario() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/simulation/events/{event_id}", { params: { path: { event_id: id } } })),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.events });
      qc.invalidateQueries({ queryKey: keys.mission });
    },
  });
}

// --------------------------------------------------------------- AI intelligence --

export const aiKeys = {
  status: ["ai", "status"] as const,
  crew: ["ai", "crew"] as const,
  risk: (id: string) => ["ai", "risk", id] as const,
  forecast: (id: string, model: string) => ["ai", "forecast", id, model] as const,
  anomalies: (id: string, hours: number) => ["ai", "anomalies", id, hours] as const,
  baseline: (id: string) => ["ai", "baseline", id] as const,
  performance: ["ai", "performance"] as const,
  explanation: (alertId: string) => ["ai", "explanation", alertId] as const,
};

export function useAiStatus() {
  return useQuery({ queryKey: aiKeys.status, queryFn: () => unwrap(api.GET("/api/ai/status")), staleTime: 60_000 });
}

export function useCrewRisk() {
  return useQuery({
    queryKey: aiKeys.crew,
    queryFn: () => unwrap(api.GET("/api/ai/crew-overview")),
    refetchInterval: 30_000,
  });
}

export function useRiskAssessment(id: string) {
  return useQuery({
    queryKey: aiKeys.risk(id),
    queryFn: () =>
      unwrap(api.GET("/api/ai/astronaut/{astronaut_id}/risk-assessment", { params: { path: { astronaut_id: id } } })),
    refetchInterval: 30_000,
    placeholderData: (prev) => (prev?.astronaut_id === id ? prev : undefined),
  });
}

export function useForecast(id: string, model: string) {
  return useQuery({
    queryKey: aiKeys.forecast(id, model),
    queryFn: () =>
      unwrap(
        api.GET("/api/ai/astronaut/{astronaut_id}/forecast", {
          params: { path: { astronaut_id: id }, query: { model } },
        }),
      ),
    refetchInterval: 120_000,
    placeholderData: (prev) => (prev?.astronaut_id === id ? prev : undefined),
  });
}

export function useAnomalyTimeline(id: string, hours: number) {
  return useQuery({
    queryKey: aiKeys.anomalies(id, hours),
    queryFn: () => {
      const end = new Date();
      const start = new Date(end.getTime() - hours * 3_600_000);
      return unwrap(
        api.POST("/api/ai/anomaly-detection", {
          body: { astronaut_id: id, start: start.toISOString(), end: end.toISOString(), include_explanations: true },
        }),
      );
    },
    refetchInterval: 60_000,
    placeholderData: (prev) => (prev?.astronaut_id === id ? prev : undefined),
  });
}

export function useAiBaseline(id: string) {
  return useQuery({
    queryKey: aiKeys.baseline(id),
    queryFn: () =>
      unwrap(api.GET("/api/ai/astronaut/{astronaut_id}/baseline", { params: { path: { astronaut_id: id } } })),
    refetchInterval: 60_000,
    placeholderData: (prev) => (prev?.astronaut_id === id ? prev : undefined),
  });
}

export function useModelPerformance() {
  return useQuery({
    queryKey: aiKeys.performance,
    queryFn: () => unwrap(api.GET("/api/ai/model-performance")),
    staleTime: 300_000,
  });
}

export function useAlertExplanation(alertId: string, enabled: boolean) {
  return useQuery({
    queryKey: aiKeys.explanation(alertId),
    queryFn: () => unwrap(api.GET("/api/ai/explanations/{alert_id}", { params: { path: { alert_id: alertId } } })),
    enabled,
    staleTime: 60_000,
  });
}

// ------------------------------------------------------- space environment (phase 4) --

export const spaceKeys = {
  sources: ["space", "sources"] as const,
  summary: (days: number) => ["space", "summary", days] as const,
  events: (days: number, types: string[]) => ["space", "events", days, types.join(",")] as const,
  event: (id: number) => ["space", "event", id] as const,
  radiation: (days: number) => ["space", "radiation", days] as const,
  missions: ["space", "iss", "missions"] as const,
  mission: (name: string, resolution: string) => ["space", "iss", name, resolution] as const,
  studies: (params: StudyFilters) => ["space", "osdr", params] as const,
  timeline: (params: TimelineParams) => ["space", "timeline", params] as const,
  nearby: (ts: string, hours: number) => ["space", "nearby", ts, hours] as const,
  corrSeries: ["space", "correlation", "series"] as const,
  all: ["space"] as const,
};

export interface StudyFilters {
  topic?: string;
  q?: string;
  organism?: string;
  project_type?: string;
  mission?: string;
  live?: boolean;
  limit?: number;
}

export interface TimelineParams {
  mode: "mission" | "iss";
  days?: number;
  astronaut_id?: string;
  mission?: string;
}

export function useSpaceSources() {
  return useQuery({ queryKey: spaceKeys.sources, queryFn: () => unwrap(api.GET("/api/space/sources")), refetchInterval: 30_000 });
}

export function useWeatherSummary(days: number) {
  return useQuery({
    queryKey: spaceKeys.summary(days),
    queryFn: () => unwrap(api.GET("/api/space/weather/summary", { params: { query: { days } } })),
    refetchInterval: 120_000,
    placeholderData: (prev) => prev,
  });
}

export function useWeatherEvents(days: number, types: string[]) {
  return useQuery({
    queryKey: spaceKeys.events(days, types),
    queryFn: () => {
      const end = new Date();
      const start = new Date(end.getTime() - days * 86_400_000);
      return unwrap(
        api.GET("/api/space/weather/events", {
          params: { query: { start: start.toISOString(), end: end.toISOString(), types: types.length ? types : undefined, limit: 2000 } },
        }),
      );
    },
    refetchInterval: 120_000,
    placeholderData: (prev) => prev,
  });
}

export function useWeatherEvent(id: number | null) {
  return useQuery({
    queryKey: spaceKeys.event(id ?? -1),
    queryFn: () => unwrap(api.GET("/api/space/weather/events/{event_id}", { params: { path: { event_id: id! } } })),
    enabled: id != null,
    staleTime: 300_000,
  });
}

export function useSpaceRadiation(days: number) {
  return useQuery({
    queryKey: spaceKeys.radiation(days),
    queryFn: () => unwrap(api.GET("/api/space/radiation", { params: { query: { days } } })),
    refetchInterval: 120_000,
    placeholderData: (prev) => prev,
  });
}

export function useIssMissions() {
  return useQuery({ queryKey: spaceKeys.missions, queryFn: () => unwrap(api.GET("/api/space/iss/missions")), refetchInterval: 60_000 });
}

export function useIssMission(name: string | null, resolution: "1h" | "6h" | "1d") {
  return useQuery({
    queryKey: spaceKeys.mission(name ?? "", resolution),
    queryFn: () =>
      unwrap(api.GET("/api/space/iss/missions/{name}", { params: { path: { name: name! }, query: { resolution } } })),
    enabled: !!name,
    staleTime: 300_000,
    placeholderData: (prev) => (prev?.mission.name === name ? prev : undefined),
  });
}

export function useOsdrStudies(filters: StudyFilters) {
  return useQuery({
    queryKey: spaceKeys.studies(filters),
    queryFn: () => unwrap(api.GET("/api/space/osdr/studies", { params: { query: { ...filters, limit: filters.limit ?? 50 } } })),
    placeholderData: (prev) => prev,
  });
}

export function useSpaceTimeline(p: TimelineParams) {
  return useQuery({
    queryKey: spaceKeys.timeline(p),
    queryFn: () => {
      if (p.mode === "iss") {
        return unwrap(api.GET("/api/space/timeline", { params: { query: { mode: "iss", mission: p.mission } } }));
      }
      const end = new Date();
      const start = new Date(end.getTime() - (p.days ?? 7) * 86_400_000);
      return unwrap(
        api.GET("/api/space/timeline", {
          params: { query: { mode: "mission", start: start.toISOString(), end: end.toISOString(), astronaut_id: p.astronaut_id } },
        }),
      );
    },
    enabled: p.mode === "mission" || !!p.mission,
    refetchInterval: p.mode === "mission" ? 60_000 : false,
    placeholderData: (prev) => (prev?.mode === p.mode ? prev : undefined),
  });
}

export function useNearbyEvents(ts: string | null, hours: number) {
  return useQuery({
    queryKey: spaceKeys.nearby(ts ?? "", hours),
    queryFn: () => unwrap(api.GET("/api/space/timeline/nearby", { params: { query: { ts: ts!, window_hours: hours } } })),
    enabled: !!ts,
    staleTime: 120_000,
  });
}

export function useCorrelationSeries() {
  return useQuery({ queryKey: spaceKeys.corrSeries, queryFn: () => unwrap(api.GET("/api/space/correlation/series")), staleTime: 60_000 });
}

export function useCorrelation() {
  return useMutation({
    mutationFn: (body: { x: string; y: string; start: string; end: string; max_lag: number; rolling_window: number }) =>
      unwrap(api.POST("/api/space/correlation/analyze", { body })),
  });
}

export function useCorrelationMatrix() {
  return useMutation({
    mutationFn: (body: { series: string[]; start: string; end: string; method: "spearman" | "pearson" }) =>
      unwrap(api.POST("/api/space/correlation/matrix", { body })),
  });
}

export function useSpaceSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { source: "donki" | "eda" | "osdr"; days?: number; missions?: string[]; force?: boolean }) =>
      unwrap(api.POST("/api/space/sync", { body: { force: false, ...body } })),
    onSettled: () => qc.invalidateQueries({ queryKey: spaceKeys.all }),
  });
}
