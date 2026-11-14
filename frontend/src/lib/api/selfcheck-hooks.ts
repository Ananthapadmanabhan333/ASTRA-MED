"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

type Schemas = components["schemas"];

export type SelfCheckSummary = Schemas["SelfCheckSummary"];
export type SelfReportCreate = Schemas["SelfReportCreate"];

export const selfKeys = { summary: (aid: string) => ["self-check", aid] as const };

export function useSelfCheck(aid: string | null) {
  return useQuery({
    queryKey: selfKeys.summary(aid ?? ""),
    queryFn: () => unwrap(api.GET("/api/crew/{astronaut_id}/self-check", { params: { path: { astronaut_id: aid! } } })),
    enabled: !!aid,
    refetchInterval: 30_000,
  });
}

export function useAddSelfReport(aid: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SelfReportCreate) =>
      unwrap(api.POST("/api/crew/{astronaut_id}/self-check", { params: { path: { astronaut_id: aid! } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: selfKeys.summary(aid ?? "") }),
  });
}
