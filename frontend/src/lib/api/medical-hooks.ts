"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { EmergencyRunCreate, ReportCreate, ReviewStatus, RoleKey } from "./types";

export const medKeys = {
  twin: (id: string) => ["twin", id] as const,
  twinTimeline: (id: string, days: number) => ["twin-timeline", id, days] as const,
  twinTrend: (id: string, metric: string, statistic: string) => ["twin-trend", id, metric, statistic] as const,
  twinStages: (id: string) => ["twin-stages", id] as const,
  crewSystems: ["multisystem"] as const,
  systems: (id: string) => ["multisystem", id] as const,
  queue: (advisory: boolean) => ["decision-queue", advisory] as const,
  packet: (id: string) => ["decision-packet", id] as const,
  emergencyScenarios: ["emergency-scenarios"] as const,
  runs: ["emergency-runs"] as const,
  run: (id: string) => ["emergency-run", id] as const,
  runTimeline: (id: string, aid: string | null) => ["emergency-timeline", id, aid] as const,
  reports: (filters: object) => ["reports", filters] as const,
  allReports: ["reports"] as const,
  report: (id: string) => ["report", id] as const,
  assistantStatus: ["assistant-status"] as const,
  overview: (period: string, aid: string | null) => ["overview", period, aid] as const,
  users: ["admin-users"] as const,
  audit: (filters: object) => ["audit", filters] as const,
  roles: ["roles"] as const,
};

const id = (astronaut_id: string) => ({ params: { path: { astronaut_id } } });

// ------------------------------------------------------------------- twin ----
export function useTwin(aid: string) {
  return useQuery({
    queryKey: medKeys.twin(aid),
    queryFn: () => unwrap(api.GET("/api/twin/{astronaut_id}", id(aid))),
    refetchInterval: 15_000,
    enabled: !!aid,
  });
}

export function useTwinTimeline(aid: string, days: number) {
  return useQuery({
    queryKey: medKeys.twinTimeline(aid, days),
    queryFn: () => unwrap(api.GET("/api/twin/{astronaut_id}/timeline", { params: { path: { astronaut_id: aid }, query: { days } } })),
    refetchInterval: 60_000,
    // A longer or shorter window for the same crew member may stand in; another crew member's may not.
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[1] === aid ? prev : undefined),
  });
}

export function useTwinTrend(aid: string, metric: string, statistic: string) {
  return useQuery({
    queryKey: medKeys.twinTrend(aid, metric, statistic),
    queryFn: () =>
      unwrap(api.GET("/api/twin/{astronaut_id}/trends", {
        params: { path: { astronaut_id: aid }, query: { metric: metric as never, statistic: statistic as never } },
      })),
    refetchInterval: 120_000,
    // Every key part (crew member, signal, statistic) changes what the chart means, so no placeholder.
  });
}

export function useTwinStages(aid: string) {
  return useQuery({ queryKey: medKeys.twinStages(aid), queryFn: () => unwrap(api.GET("/api/twin/{astronaut_id}/stages", id(aid))), refetchInterval: 300_000 });
}

// -------------------------------------------------------- medical intelligence ----
export function useCrewSystems() {
  return useQuery({ queryKey: medKeys.crewSystems, queryFn: () => unwrap(api.GET("/api/multisystem")), refetchInterval: 15_000 });
}

export function useSystems(aid: string) {
  return useQuery({ queryKey: medKeys.systems(aid), queryFn: () => unwrap(api.GET("/api/multisystem/{astronaut_id}", id(aid))), refetchInterval: 15_000 });
}

export function useDecisionQueue(includeAdvisory: boolean) {
  return useQuery({
    queryKey: medKeys.queue(includeAdvisory),
    queryFn: () => unwrap(api.GET("/api/decision-support/queue", { params: { query: { include_advisory: includeAdvisory, hours: 48 } } })),
    refetchInterval: 10_000,
  });
}

export function useDecisionPacket(alertId: string | null) {
  return useQuery({
    queryKey: medKeys.packet(alertId ?? ""),
    queryFn: () => unwrap(api.GET("/api/decision-support/alerts/{alert_id}", { params: { path: { alert_id: alertId! } } })),
    enabled: !!alertId,
    refetchInterval: 30_000,
  });
}

// ------------------------------------------------------------- emergency ----
export function useEmergencyScenarios() {
  return useQuery({ queryKey: medKeys.emergencyScenarios, queryFn: () => unwrap(api.GET("/api/emergency/scenarios")), staleTime: Infinity });
}

export function useEmergencyRuns() {
  return useQuery({ queryKey: medKeys.runs, queryFn: () => unwrap(api.GET("/api/emergency/runs", { params: { query: { hours: 72 } } })), refetchInterval: 5_000 });
}

export function useRunTimeline(runId: string | null, astronautId: string | null, live: boolean) {
  return useQuery({
    queryKey: medKeys.runTimeline(runId ?? "", astronautId),
    queryFn: () =>
      unwrap(api.GET("/api/emergency/runs/{run_id}/timeline", {
        params: { path: { run_id: runId! }, query: astronautId ? { astronaut_id: astronautId } : {} },
      })),
    enabled: !!runId,
    refetchInterval: live ? 5_000 : false,
    // Run and crew member are the whole key: no placeholder, so one run's timeline never shows under another.
  });
}

export function useStartRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EmergencyRunCreate) => unwrap(api.POST("/api/emergency/runs", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: medKeys.runs }),
  });
}

export function useCancelRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => unwrap(api.POST("/api/emergency/runs/{run_id}/cancel", { params: { path: { run_id: runId } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: medKeys.runs }),
  });
}

export function useAnalyzeRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => unwrap(api.POST("/api/emergency/runs/{run_id}/analyze", { params: { path: { run_id: runId } } })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: medKeys.runs });
      qc.invalidateQueries({ queryKey: ["emergency-timeline"] });
    },
  });
}

// --------------------------------------------------------------- reports ----
export interface ReportFilters {
  astronaut_id?: string;
  status?: ReviewStatus;
}

export function useReports(filters: ReportFilters) {
  return useQuery({
    queryKey: medKeys.reports(filters),
    queryFn: () => unwrap(api.GET("/api/reports", { params: { query: filters } })),
    refetchInterval: 20_000,
  });
}

export function useReport(reportId: string | null) {
  return useQuery({
    queryKey: medKeys.report(reportId ?? ""),
    queryFn: () => unwrap(api.GET("/api/reports/{report_id}", { params: { path: { report_id: reportId! } } })),
    enabled: !!reportId,
  });
}

export function useCreateReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ReportCreate) => unwrap(api.POST("/api/reports", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: medKeys.allReports }),
  });
}

export function useReviewReport(reportId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { status: ReviewStatus; note?: string | null }) =>
      unwrap(api.POST("/api/reports/{report_id}/review", { params: { path: { report_id: reportId } }, body })),
    onSuccess: (data) => {
      qc.setQueryData(medKeys.report(reportId), data);
      qc.invalidateQueries({ queryKey: medKeys.allReports });
    },
  });
}

// ------------------------------------------------------------- assistant ----
export function useAssistantStatus() {
  return useQuery({ queryKey: medKeys.assistantStatus, queryFn: () => unwrap(api.GET("/api/assistant/status")), staleTime: 60_000 });
}

export function useAsk() {
  return useMutation({
    mutationFn: (body: { question: string; astronaut_id?: string | null }) => unwrap(api.POST("/api/assistant/ask", { body })),
  });
}

// --------------------------------------------------------------- overview ----
export function useOverview(period: "24h" | "7d" | "30d", astronautId: string | null) {
  return useQuery({
    queryKey: medKeys.overview(period, astronautId),
    queryFn: () => unwrap(api.GET("/api/overview", { params: { query: { period, ...(astronautId ? { astronaut_id: astronautId } : {}) } } })),
    refetchInterval: 30_000,
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[2] === astronautId ? prev : undefined),
  });
}

// ------------------------------------------------------------------ admin ----
export function useUsers(enabled: boolean) {
  return useQuery({ queryKey: medKeys.users, queryFn: () => unwrap(api.GET("/api/admin/users")), enabled });
}

export function useAudit(filters: { username?: string; outcome?: string; hours: number }, enabled: boolean) {
  return useQuery({
    queryKey: medKeys.audit(filters),
    queryFn: () =>
      unwrap(api.GET("/api/admin/audit", {
        params: { query: { hours: filters.hours, limit: 300, ...(filters.username ? { username: filters.username } : {}),
          ...(filters.outcome ? { outcome: filters.outcome } : {}) } },
      })),
    enabled,
    refetchInterval: 15_000,
  });
}

export function useRoles() {
  return useQuery({ queryKey: medKeys.roles, queryFn: () => unwrap(api.GET("/api/auth/roles")), staleTime: Infinity });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { username: string; display_name: string; role: RoleKey; password: string }) =>
      unwrap(api.POST("/api/admin/users", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: medKeys.users }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, unlock = false, ...body }: { userId: string; role?: RoleKey; active?: boolean; unlock?: boolean }) =>
      unwrap(api.PATCH("/api/admin/users/{user_id}", { params: { path: { user_id: userId } }, body: { ...body, unlock } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: medKeys.users }),
  });
}
