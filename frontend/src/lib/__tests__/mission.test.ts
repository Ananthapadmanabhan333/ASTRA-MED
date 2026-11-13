import { describe, expect, it } from "vitest";

import { routePermissions } from "@/components/shell/nav";
import type { MissionAlert, MissionEvent, SimState } from "@/lib/api/types";
import { applyMessage, EVENT_BUFFER, initialLive, SIM_TRAIL } from "@/lib/live/reducer";

const T0 = Date.parse("2026-11-13T10:00:00Z");
const iso = (s: number) => new Date(T0 + s * 1000).toISOString();

function event(id: string, overrides: Partial<MissionEvent> = {}): MissionEvent {
  return {
    id, source: "physiological_monitoring", source_label: "Physiological monitoring", kind: "alert_opened",
    category: "crew_physiology", category_label: "Crew physiology", severity: "caution", priority: 2,
    priority_label: "High", priority_score: 70, title: `Event ${id}`, summary: null, astronaut_id: "AST-01",
    context: "operations", simulation_id: null, data_origin: "simulated", data_origin_label: "Simulated crew stream",
    classification: "rule_detection", classification_note: null, experimental: false, confidence: null,
    ref_type: null, ref_id: null, occurred_at: iso(0), received_at: iso(0), last_seen_at: iso(0), latency_s: 0,
    clock_skew_s: null, occurrences: 1, payload: {}, ...overrides,
  };
}

function missionAlert(id: string, overrides: Partial<MissionAlert> = {}): MissionAlert {
  return {
    id, source: "anomaly_detection", source_label: "AI anomaly detection", source_ref: id, event_id: null,
    astronaut_id: "AST-02", context: "operations", simulation_id: null, data_origin: "simulated",
    data_origin_label: "Simulated crew stream", category: "ai_prediction", category_label: "AI predictions",
    classification: "experimental_ai", classification_label: "Experimental AI prediction",
    classification_note: "not a confirmed medical emergency", experimental: true, severity: "advisory", priority: 3,
    priority_label: "Medium", title: "AI", summary: null, status: "open", created_at: iso(0), updated_at: iso(0),
    received_at: iso(0), measurements: {}, explanation: {}, confidence: 0.6, confidence_level: "medium",
    uncertainty: [], correlations: {}, condition_cleared_at: null, acknowledged_at: null, acknowledged_by: null,
    ack_note: null, resolved_at: null, resolved_by: null, resolution_notes: null, occurrences: 1,
    data_source: "simulated", ...overrides,
  };
}

function simState(id: string, t: number, hr: number): SimState {
  return {
    active: true, status: "running", context: "simulation", data_source: "simulated", label: "SANDBOX", id,
    crew: ["AST-01"], latest: [{
      astronaut_id: "AST-01", name: "Maya Okafor", ts: iso(t), heart_rate: hr, spo2: 97, systolic: 120, diastolic: 78,
      temperature_c: 36.9, respiratory_rate: 14, activity_state: "work", rhythm: "regular", scenario: null,
      status: "nominal", dose_msv: 0,
    }], active_injections: [], habitat: {}, open_alerts: 0, stats: {},
  };
}

describe("mission events in the live store", () => {
  it("keeps the newest first, merges repeats by id and caps the buffer", () => {
    let s = initialLive();
    for (let i = 0; i < EVENT_BUFFER + 10; i++) {
      s = applyMessage(s, { type: "mission_event", event: "created", item: event(`e${i}`) }, T0);
    }
    expect(s.missionEvents).toHaveLength(EVENT_BUFFER);
    expect(s.missionEvents[0].id).toBe(`e${EVENT_BUFFER + 9}`);
    s = applyMessage(s, { type: "mission_event", event: "updated", item: event("e50", { occurrences: 3 }) }, T0);
    expect(s.missionEvents[0]).toMatchObject({ id: "e50", occurrences: 3 });
    expect(s.missionEvents.filter((e) => e.id === "e50")).toHaveLength(1);
  });
});

describe("unified alerts in the live store", () => {
  it("tracks unresolved alerts and counts new or escalated ones as unread", () => {
    let s = applyMessage(initialLive(), { type: "mission_alert", event: "opened", alert: missionAlert("a1") }, T0);
    s = applyMessage(s, { type: "mission_alert", event: "acknowledged", alert: missionAlert("a1", { status: "acknowledged" }) }, T0);
    expect(s.missionAlerts.a1.status).toBe("acknowledged");
    expect(s.unread).toBe(1);
    s = applyMessage(s, { type: "mission_alert", event: "escalated", alert: missionAlert("a1", { severity: "caution" }) }, T0);
    expect(s.unread).toBe(2);
    s = applyMessage(s, { type: "mission_alert", event: "resolved", alert: missionAlert("a1", { status: "resolved" }) }, T0);
    expect(s.missionAlerts.a1).toBeUndefined();
  });
});

describe("sandbox state", () => {
  it("builds a per-run chart trail from sim_state frames and restarts it for a new run", () => {
    let s = initialLive();
    for (let i = 0; i < SIM_TRAIL + 5; i++) s = applyMessage(s, { type: "sim_state", state: simState("r1", i * 10, 60 + i) }, T0);
    expect(s.sim?.id).toBe("r1");
    expect(s.simTrail.rows).toHaveLength(SIM_TRAIL);
    expect(s.simTrail.rows.at(-1)?.["hr_AST-01"]).toBe(60 + SIM_TRAIL + 4);
    // A repeated frame (same simulation time) adds nothing.
    s = applyMessage(s, { type: "sim_state", state: simState("r1", (SIM_TRAIL + 4) * 10, 1) }, T0);
    expect(s.simTrail.rows).toHaveLength(SIM_TRAIL);
    s = applyMessage(s, { type: "sim_state", state: simState("r2", 0, 70) }, T0);
    expect(s.simTrail).toMatchObject({ id: "r2" });
    expect(s.simTrail.rows).toHaveLength(1);
  });
});

describe("phase 6 routes", () => {
  it("opens command pages with crew health access and system status to every role", () => {
    for (const path of ["/", "/crew", "/alerts", "/timeline", "/simulation", "/analytics"]) {
      expect(routePermissions(path)).toEqual(["health:read"]);
    }
    expect(routePermissions("/system")).toEqual(expect.arrayContaining(["health:read", "audit:read", "users:manage"]));
  });
});
