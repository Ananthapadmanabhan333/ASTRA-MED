import type { Alert, ThresholdInfo, VitalReading } from "@/lib/api/types";

export function reading(overrides: Partial<VitalReading> = {}): VitalReading {
  return {
    astronaut_id: "AST-01",
    ts: "2026-11-09T11:00:00Z",
    heart_rate: 64,
    spo2: 98,
    systolic: 118,
    diastolic: 76,
    temperature_c: 36.8,
    respiratory_rate: 14,
    activity_state: "work",
    activity_met: 1.7,
    rhythm: "regular",
    hrv_rmssd_ms: 40,
    scenario: null,
    data_source: "simulated",
    ...overrides,
  };
}

export function alert(overrides: Partial<Alert> = {}): Alert {
  return {
    id: "a1",
    astronaut_id: "AST-01",
    rule_key: "spo2:low",
    category: "threshold",
    metric: "spo2",
    direction: "low",
    severity: "caution",
    status: "active",
    title: "Oxygen desaturation",
    message: "SpO2 93 % is below the caution limit of 94 %.",
    unit: "%",
    trigger_value: 93,
    threshold_value: 94,
    peak_value: 93,
    activity_state: "work",
    scenario: null,
    opened_at: "2026-11-09T11:00:00Z",
    updated_at: "2026-11-09T11:00:00Z",
    condition_cleared_at: null,
    acknowledged_at: null,
    resolved_at: null,
    operator_note: null,
    data_source: "simulated",
    ...overrides,
  };
}

export const RULES: ThresholdInfo[] = [
  {
    key: "heart_rate:high",
    metric: "heart_rate",
    direction: "high",
    title: "Elevated heart rate",
    unit: "bpm",
    caution: 120,
    critical: 140,
    overrides: { exercise: [172, 188] },
  },
  {
    key: "heart_rate:low",
    metric: "heart_rate",
    direction: "low",
    title: "Low heart rate",
    unit: "bpm",
    caution: 45,
    critical: 40,
    overrides: { sleep: [40, 36] },
  },
  {
    key: "spo2:low",
    metric: "spo2",
    direction: "low",
    title: "Oxygen desaturation",
    unit: "%",
    caution: 94,
    critical: 90,
    overrides: {},
  },
];
