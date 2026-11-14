import { describe, expect, it } from "vitest";

import type { AssistantAnswer, MissionAlert, SimFrame, SimRun, SimState, WeatherSummary } from "@/lib/api/types";
import {
  type CrewAnalysis,
  type DemoInputs,
  defaultFocus,
  evaluateSteps,
  forecastHighlights,
  mergeAnalyses,
  parseAnalyses,
  pickAnalysis,
  pickFocusAlert,
  type ReportLike,
  STEP_TITLES,
  tPlus,
} from "@/lib/demo/steps";

const T0 = Date.parse("2026-11-14T10:00:00Z");
const iso = (s: number) => new Date(T0 + s * 1000).toISOString();
const ALL = { control: true, manageAlerts: true, writeReports: true, assistant: true };

function state(overrides: Partial<SimState> = {}): SimState {
  return {
    active: true, status: "running", context: "simulation", data_source: "simulated", label: "SIMULATION SANDBOX",
    id: "run1", name: "Demo mode: Medical emergency: oxygen desaturation", preset: "desaturation_emergency",
    speed: 20, step_seconds: 10, crew: ["AST-01", "AST-02"], sim_start: iso(0), sim_time: iso(1800), t_plus: "T+00:30:00",
    progress: 0.33, created_by: "operator",
    latest: [
      { astronaut_id: "AST-01", name: "Maya Okafor", ts: iso(1800), heart_rate: 104, spo2: 86.4, systolic: 122, diastolic: 80,
        temperature_c: 36.9, respiratory_rate: 22, activity_state: "work", rhythm: "regular", scenario: "desaturation",
        status: "critical", dose_msv: 0 },
      { astronaut_id: "AST-02", name: "Lukas Brandt", ts: iso(1800), heart_rate: 70, spo2: 98, systolic: 118, diastolic: 76,
        temperature_c: 36.7, respiratory_rate: 14, activity_state: "work", rhythm: "regular", scenario: null,
        status: "nominal", dose_msv: 0 },
    ],
    active_injections: [], habitat: {}, open_alerts: 1, stats: { samples: 360, events: 4 },
    next_injection: null,
    ...overrides,
  };
}

function missionAlert(id: string, overrides: Partial<MissionAlert> = {}): MissionAlert {
  return {
    id, source: "physiological_monitoring", source_label: "Physiological monitoring", source_ref: id, event_id: null,
    astronaut_id: "AST-01", context: "simulation", simulation_id: "run1", data_origin: "sandbox",
    data_origin_label: "Sandbox", category: "crew_physiology", category_label: "Crew physiology",
    classification: "simulated_test_scenario", classification_label: "Simulated test scenario",
    classification_note: "sandbox", experimental: false, severity: "critical", priority: 1, priority_label: "Critical",
    title: "[SIM] SpO2 critically low", summary: null, status: "open", created_at: iso(600), updated_at: iso(600),
    received_at: iso(600), measurements: {}, explanation: {}, confidence: null, confidence_level: null, uncertainty: [],
    correlations: {}, condition_cleared_at: null, acknowledged_at: null, acknowledged_by: null, ack_note: null,
    resolved_at: null, resolved_by: null, resolution_notes: null, occurrences: 1, data_source: "simulated",
    ...overrides,
  };
}

const analysisFull: CrewAnalysis = {
  available: true, sim_time: iso(1800), model_version: "v3.1",
  risk: {
    risk_score: 62, category: "high", category_label: "High concern", confidence: { level: "medium" },
    contributors: [
      { signal: "spo2", label: "SpO₂", share: 0.7, value: 86.4, unit: "%", baseline: 97.8, z: -5.2 },
      { signal: "respiratory_rate", label: "Respiratory rate", share: 0.3, value: 22, unit: "/min", baseline: null },
    ],
  },
  detections: [{ start: iso(900), kind: "sudden_change", peak_score: 2.4, signals: ["spo2", "respiratory_rate"] }],
  flagged_windows: 3, windows: 6,
  forecast: [{
    signal: "heart_rate", label: "Heart rate", unit: "bpm",
    horizons: [
      { horizon_h: 1, value: 100, lower: 92, upper: 108, crossing: null },
      { horizon_h: 6, value: 88.25, lower: 79.9, upper: 96.6, crossing: null },
    ],
  }],
  forecast_error: null,
  limitations: ["Baseline for respiratory rate fell back to a coarser level (too few past windows)."],
};

const frame: SimFrame = {
  simulation_id: "run1", at: iso(1800), t_plus: "T+00:30:00", label: "SANDBOX", active_injections: [],
  crew: [{ astronaut_id: "AST-01", name: "Maya Okafor", reading: {
    ts: iso(1800), heart_rate: 104, spo2: 86.4, systolic: 122, diastolic: 80, temperature_c: 36.9, respiratory_rate: 22,
    activity_state: "work", scenario: "desaturation", source: "generator",
  } }],
  alerts: [missionAlert("a1")],
};

function weather(mode: WeatherSummary["freshness"]["mode"] = "live"): WeatherSummary {
  return {
    window_days: 30, counts: { flare: 5, cme: 3 }, flare_classes: { M: 2 }, strongest_flare: null, max_storm: null,
    fastest_cme: null, latest: {}, alerts: [], notifications: [], caveats: [],
    freshness: { source_id: "donki", retrieved_at: iso(0), mode, message: `mode ${mode}` },
  };
}

const answer = {
  question: "How is Maya doing right now?", mode: "extractive", statements: [
    { text: "Maya's latest heart rate is 72 bpm.", citations: ["D1"], kind: "data" },
    { text: "No diagnosis is given.", citations: [], kind: "safety" },
    { text: "Baselines are robust per activity.", citations: ["S1", "S2"], kind: "documentation" },
  ],
  sources: [{ id: "D1" }, { id: "S1" }, { id: "S2" }],
  escalation: { required: false, reasons: [], message: "" },
} as unknown as AssistantAnswer;

const report: ReportLike = {
  id: "rep-42", title: "[SIM] SpO2 critically low", integrity: "intact", content_sha256: "abcdef0123456789abcdef",
  review_status_label: "Draft", source_kind: "simulation", simulation_id: "run1", created_at: iso(2000),
};

const full = (overrides: Partial<DemoInputs> = {}): DemoInputs => ({
  state: state(), focusId: "AST-01", names: { "AST-01": "Maya Okafor", "AST-02": "Lukas Brandt" },
  roles: { "AST-01": "Commander" }, analysis: analysisFull, analyses: { "AST-01": analysisFull },
  run: { id: "run1", seed: 2026, config: {} } as unknown as SimRun, presetLabel: "Medical emergency: oxygen desaturation",
  alerts: [missionAlert("a1")], frame, weather: weather(), answer, report, perms: ALL, ...overrides,
});

const byId = (steps: ReturnType<typeof evaluateSteps>, n: number) => steps[n - 1];
const ev = (steps: ReturnType<typeof evaluateSteps>, n: number, label: string) =>
  byId(steps, n).evidence.find((e) => e.label === label)?.value;

describe("demo step helpers", () => {
  it("formats T+ from the run start", () => {
    expect(tPlus(iso(0), iso(3725))).toBe("T+01:02:05");
    expect(tPlus(iso(100), iso(0))).toBe("T+00:00:00");
  });

  it("keeps only per-crew analysis entries", () => {
    const parsed = parseAnalyses({ "AST-01": { available: true }, _last: { sim_time: iso(0) }, junk: 3, bad: { x: 1 } });
    expect(Object.keys(parsed)).toEqual(["AST-01"]);
    expect(parseAnalyses(null)).toEqual({});
  });

  it("picks the newer analysis by simulation time", () => {
    const old: CrewAnalysis = { available: true, sim_time: iso(900) };
    const fresh: CrewAnalysis = { available: true, sim_time: iso(1800) };
    expect(pickAnalysis(old, fresh)).toBe(fresh);
    expect(pickAnalysis(fresh, old)).toBe(fresh);
    expect(pickAnalysis(undefined, old)).toBe(old);
    expect(pickAnalysis(null, null)).toBeNull();
    const merged = mergeAnalyses({ "AST-01": old, "AST-02": old }, { "AST-01": fresh });
    expect(merged["AST-01"]).toBe(fresh);
    expect(merged["AST-02"]).toBe(old);
  });

  it("follows the first scripted crew target, else the first crew member", () => {
    const run = { config: { script: [{ injection: "solar_flare", astronaut_id: null }, { injection: "tachycardia", astronaut_id: "AST-03" }] } };
    expect(defaultFocus(run, ["AST-01", "AST-03"])).toBe("AST-03");
    expect(defaultFocus({ config: {} }, ["AST-01", "AST-03"])).toBe("AST-01");
    expect(defaultFocus(null, [])).toBeNull();
  });

  it("chooses the focus alert by crew member, priority, then time", () => {
    const alerts = [
      missionAlert("late-p1-other", { astronaut_id: "AST-02", priority: 1, created_at: iso(50) }),
      missionAlert("p2-mine", { priority: 2, created_at: iso(30) }),
      missionAlert("p1-mine-late", { priority: 1, created_at: iso(40) }),
      missionAlert("p1-mine-early", { priority: 1, created_at: iso(20) }),
    ];
    expect(pickFocusAlert(alerts, "AST-01")?.id).toBe("p1-mine-early");
    expect(pickFocusAlert(alerts, "AST-09")?.id).toBe("p1-mine-early");
    expect(pickFocusAlert([missionAlert("env", { astronaut_id: null })], "AST-01")?.id).toBe("env");
    expect(pickFocusAlert([], "AST-01")).toBeNull();
  });

  it("reads the 6 h forecast horizon, falling back to the furthest one", () => {
    expect(forecastHighlights(analysisFull.forecast)[0]).toMatchObject({ horizon_h: 6, value: 88.25, lower: 79.9, upper: 96.6 });
    const noSix = forecastHighlights([{ signal: "spo2", label: "SpO₂", unit: "%", horizons: [
      { horizon_h: 1, value: 97, lower: 96, upper: 98, crossing: null },
      { horizon_h: 3, value: 96, lower: 94, upper: 98, crossing: null },
    ] }]);
    expect(noSix[0].horizon_h).toBe(3);
    expect(forecastHighlights(null)).toEqual([]);
  });
});

describe("evaluateSteps", () => {
  it("returns the twelve steps in order", () => {
    const steps = evaluateSteps(full());
    expect(steps.map((s) => s.id)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
    expect(steps.map((s) => s.title)).toEqual([...STEP_TITLES]);
  });

  it("locks every run step until a run is followed; space weather is independent", () => {
    const steps = evaluateSteps({ state: null, focusId: null, analysis: null, weather: weather(), perms: ALL });
    expect(steps.filter((s) => s.status === "locked").map((s) => s.id)).toEqual([1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12]);
    expect(byId(steps, 7).status).toBe("done");
    expect(evaluateSteps({ state: state({ id: null, status: "idle" }), focusId: null, analysis: null, perms: ALL })[0].status).toBe("locked");
  });

  it("ticks steps 1-10 and 12 from complete responses and copies their values as evidence", () => {
    const steps = evaluateSteps(full());
    for (const n of [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12]) expect(byId(steps, n).status, `step ${n}`).toBe("done");
    expect(byId(steps, 11).status).toBe("action");
    expect(ev(steps, 1, "Seed")).toBe("2026");
    expect(ev(steps, 1, "Preset")).toBe("Medical emergency: oxygen desaturation (desaturation_emergency)");
    expect(ev(evaluateSteps(full({ run: { id: "other", seed: 1, config: {} } as unknown as SimRun })), 1, "Seed")).toBeUndefined();
    expect(ev(steps, 1, "Crew")).toBe("Maya Okafor (AST-01, Commander); Lukas Brandt (AST-02)");
    expect(ev(steps, 2, "Samples stored")).toBe("360");
    expect(ev(steps, 2, "Latest for Maya Okafor")).toBe("HR 104 bpm, SpO₂ 86.4 %, RR 22 /min at T+00:30:00");
    expect(ev(steps, 3, "SpO₂")).toBe("86.4 vs baseline 97.8 % (z -5.2)");
    expect(ev(steps, 3, "Respiratory rate")).toBeUndefined(); // no baseline value in the response
    expect(byId(steps, 3).evidence.some((e) => e.label === "Note")).toBe(true);
    expect(ev(steps, 4, "By source")).toBe("Physiological monitoring 1");
    expect(ev(steps, 5, "Flagged windows")).toBe("3 of 6");
    expect(ev(steps, 5, "First detection")).toBe("sudden change at T+00:15:00, peak 2.40x threshold, spo2, respiratory rate");
    expect(ev(steps, 6, "Heart rate +6 h")).toBe("88.3 bpm (79.9 to 96.6)");
    expect(ev(steps, 7, "Events by type")).toBe("flare 5; cme 3");
    expect(byId(steps, 7).summary).toContain("Real NASA DONKI data");
    expect(ev(steps, 8, "Risk (experimental)")).toBe("62/100 High concern, confidence medium");
    expect(byId(steps, 8).summary).toContain("Separate from the operational Digital twin");
    expect(byId(steps, 9).summary).toBe("2 of 3 statements cite a source (3 sources).");
    expect(byId(steps, 9).evidence.map((e) => e.label)).toEqual(["Cites D1", "Cites S1, S2"]);
    expect(ev(steps, 10, "Priority")).toBe("P1 Critical (highest in this run)");
    expect(ev(steps, 12, "Integrity")).toBe("intact, SHA-256 abcdef012345…");
    expect(byId(steps, 12).href).toBe("/reports?report=rep-42");
  });

  it("waits for samples, alerts and the AI analysis", () => {
    const steps = evaluateSteps(full({
      state: state({ stats: {}, next_injection: { t_plus: "T+00:06:00", injection: "desaturation" } }),
      analysis: null, analyses: {}, alerts: [], frame: null, answer: null, report: null,
    }));
    expect(byId(steps, 2).status).toBe("waiting");
    for (const n of [3, 5, 6, 8]) expect(byId(steps, n).status, `step ${n}`).toBe("waiting");
    expect(byId(steps, 4)).toMatchObject({ status: "waiting", evidence: [{ label: "Next scripted event", value: "T+00:06:00 desaturation" }] });
    expect(byId(steps, 9).status).toBe("action");
    expect(byId(steps, 10).status).toBe("waiting");
    expect(byId(steps, 11).status).toBe("locked");
    expect(byId(steps, 12).status).toBe("action");
  });

  it("passes the backend's reason through when the AI analysis is unavailable", () => {
    const steps = evaluateSteps(full({ analysis: { available: false, reason: "The stream has no samples yet." } }));
    expect(byId(steps, 3)).toMatchObject({ status: "waiting" });
    expect(byId(steps, 3).summary).toContain("The stream has no samples yet.");
  });

  it("says the baseline comes from stored history when no per-signal baseline is listed", () => {
    const a: CrewAnalysis = { ...analysisFull, risk: { ...analysisFull.risk!, contributors: [] }, limitations: [] };
    const steps = evaluateSteps(full({ analysis: a }));
    expect(byId(steps, 3).status).toBe("done");
    expect(ev(steps, 3, "Baseline")).toBe("from stored history");
  });

  it("keeps step 5 waiting without flags and points at other flagged crew", () => {
    const quiet: CrewAnalysis = { ...analysisFull, detections: [], flagged_windows: 0 };
    const steps = evaluateSteps(full({ analysis: quiet, analyses: { "AST-01": quiet, "AST-02": analysisFull } }));
    expect(byId(steps, 5).status).toBe("waiting");
    expect(ev(steps, 5, "Flagged for other crew")).toBe("Lukas Brandt (3 windows)");
  });

  it("shows the forecast error when there is no forecast", () => {
    const steps = evaluateSteps(full({ analysis: { ...analysisFull, forecast: null, forecast_error: "Not enough history." } }));
    expect(byId(steps, 6)).toMatchObject({ status: "waiting", summary: "Not enough history." });
  });

  it("treats stored NASA data as retrieved, and pending or unavailable sources as not", () => {
    expect(byId(evaluateSteps(full({ weather: weather("offline-fallback") })), 7).status).toBe("done");
    expect(byId(evaluateSteps(full({ weather: weather("pending") })), 7).status).toBe("waiting");
    expect(byId(evaluateSteps(full({ weather: weather("unavailable") })), 7).status).toBe("unavailable");
    expect(byId(evaluateSteps(full({ weather: null, weatherError: "Network down" })), 7)).toMatchObject({ status: "unavailable", summary: "Network down" });
  });

  it("needs a frame reading and a risk assessment for the sandbox twin snapshot", () => {
    expect(byId(evaluateSteps(full({ frame: null })), 8).status).toBe("waiting");
    expect(byId(evaluateSteps(full({ frame: { ...frame, crew: [] } })), 8).status).toBe("waiting");
  });

  it("does not tick step 9 for an answer without citations", () => {
    const uncited = { ...answer, statements: [{ text: "x", citations: [], kind: "uncited" }] } as AssistantAnswer;
    expect(byId(evaluateSteps(full({ answer: uncited })), 9).status).toBe("action");
  });

  it("ticks step 11 from the alert-centre lifecycle fields", () => {
    const acked = missionAlert("a1", { status: "acknowledged", acknowledged_at: iso(1200), acknowledged_by: "operator" });
    const steps = evaluateSteps(full({ alerts: [acked] }));
    expect(byId(steps, 11).status).toBe("done");
    expect(ev(steps, 11, "Acknowledged")).toBe("operator at T+00:20:00");
  });

  it("marks permission-gated steps as not permitted, unless already done", () => {
    const none = { control: false, manageAlerts: false, writeReports: false, assistant: false };
    const steps = evaluateSteps(full({ perms: none, answer: null, report: null }));
    expect([9, 11, 12].map((n) => byId(steps, n).status)).toEqual(["blocked", "blocked", "blocked"]);
    const acked = missionAlert("a1", { acknowledged_at: iso(1200), acknowledged_by: "flight-surgeon", status: "acknowledged" });
    expect(byId(evaluateSteps(full({ perms: none, alerts: [acked] })), 11).status).toBe("done");
  });

  it("reports alert-loading errors instead of claiming there are none", () => {
    const steps = evaluateSteps(full({ alerts: undefined, alertsError: "Forbidden" }));
    expect(byId(steps, 4)).toMatchObject({ status: "unavailable", summary: "Forbidden" });
    expect(byId(steps, 10).status).toBe("unavailable");
  });
});
