import { describe, expect, it } from "vitest";

import { applyMessage, initialLive, liveStatus, TRAIL_SECONDS } from "@/lib/live/reducer";

import { alert, reading } from "./fixtures";

const T0 = Date.parse("2026-11-09T11:00:00Z");
const iso = (offsetS: number) => new Date(T0 + offsetS * 1000).toISOString();

describe("live reducer", () => {
  it("seeds state from hello", () => {
    const s = applyMessage(
      initialLive(),
      {
        type: "hello",
        server_time: iso(0),
        tick_seconds: 1,
        ecg_sample_rate_hz: 125,
        astronaut_ids: ["AST-01"],
        latest: [reading()],
        open_alerts: [alert()],
        active_scenarios: [],
        data_source: "simulated",
      },
      T0 + 250,
    );
    expect(s.latest["AST-01"].heart_rate).toBe(64);
    expect(Object.keys(s.openAlerts)).toEqual(["a1"]);
    expect(s.serverOffsetMs).toBe(-250);
    expect(s.trails["AST-01"]).toHaveLength(1);
  });

  it("appends vitals to a bounded trail and ignores duplicates", () => {
    let s = initialLive();
    for (let i = 0; i <= TRAIL_SECONDS + 30; i++) {
      s = applyMessage(
        s,
        { type: "vitals", ts: iso(i), readings: [reading({ ts: iso(i), heart_rate: 60 + (i % 5) })], ecg: [], data_source: "simulated" },
        T0 + i * 1000,
      );
    }
    const trail = s.trails["AST-01"];
    expect(trail[trail.length - 1].t - trail[0].t).toBeLessThanOrEqual(TRAIL_SECONDS * 1000);
    const before = trail.length;
    s = applyMessage(
      s,
      { type: "vitals", ts: iso(TRAIL_SECONDS + 30), readings: [reading({ ts: iso(TRAIL_SECONDS + 30) })], ecg: [], data_source: "simulated" },
      T0,
    );
    expect(s.trails["AST-01"]).toHaveLength(before);
  });

  it("tracks the alert lifecycle and drops resolved alerts", () => {
    let s = applyMessage(initialLive(), { type: "alert", event: "opened", alert: alert() }, T0);
    expect(s.openAlerts.a1.status).toBe("active");
    s = applyMessage(s, { type: "alert", event: "acknowledged", alert: alert({ status: "acknowledged" }) }, T0);
    expect(s.openAlerts.a1.status).toBe("acknowledged");
    s = applyMessage(s, { type: "alert", event: "resolved", alert: alert({ status: "resolved" }) }, T0);
    expect(s.openAlerts).toEqual({});
  });

  it("adds and removes running scenarios", () => {
    const scenario = {
      id: "s1",
      scenario: "tachycardia" as const,
      label: "Tachycardia-like elevated heart rate",
      astronaut_id: "AST-02",
      intensity: 1,
      started_at: iso(0),
      ends_at: iso(240),
      cancelled_at: null,
      triggered_by: "operator" as const,
      active: true,
    };
    let s = applyMessage(initialLive(), { type: "simulation", event: "started", scenario }, T0);
    expect(Object.keys(s.scenarios)).toEqual(["s1"]);
    s = applyMessage(s, { type: "simulation", event: "cancelled", scenario }, T0);
    expect(s.scenarios).toEqual({});
  });
});

describe("liveStatus", () => {
  it("returns the worst severity whose condition is still present", () => {
    expect(liveStatus([])).toBe("nominal");
    expect(liveStatus([alert({ severity: "advisory" }), alert({ id: "b", severity: "critical" })])).toBe("critical");
    expect(
      liveStatus([alert({ severity: "critical", condition_cleared_at: iso(10) }), alert({ id: "b", severity: "caution" })]),
    ).toBe("caution");
  });
});
