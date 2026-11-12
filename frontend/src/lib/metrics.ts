import type { ActivityState, Metric, TimeRange } from "@/lib/api/types";

export interface MetricMeta {
  label: string;
  short: string;
  unit: string;
  decimals: number;
}

export const METRICS: Record<Metric, MetricMeta> = {
  heart_rate: { label: "Heart rate", short: "HR", unit: "bpm", decimals: 0 },
  spo2: { label: "SpO₂", short: "SpO₂", unit: "%", decimals: 1 },
  systolic: { label: "Systolic pressure", short: "SYS", unit: "mmHg", decimals: 0 },
  diastolic: { label: "Diastolic pressure", short: "DIA", unit: "mmHg", decimals: 0 },
  temperature_c: { label: "Body temperature", short: "Temp", unit: "°C", decimals: 1 },
  respiratory_rate: { label: "Respiratory rate", short: "RR", unit: "br/min", decimals: 0 },
  activity_met: { label: "Activity load", short: "MET", unit: "MET", decimals: 1 },
};

export const COMPARABLE_METRICS: Metric[] = [
  "heart_rate",
  "spo2",
  "temperature_c",
  "respiratory_rate",
  "systolic",
  "diastolic",
];

export const ACTIVITY_LABEL: Record<ActivityState, string> = {
  sleep: "Asleep",
  rest: "Resting",
  work: "On duty",
  exercise: "Exercising",
};

export type ChartRange = TimeRange | "live";

export const RANGE_OPTIONS: { value: ChartRange; label: string }[] = [
  { value: "live", label: "Live 10 min" },
  { value: "1h", label: "1 h" },
  { value: "6h", label: "6 h" },
  { value: "24h", label: "24 h" },
  { value: "7d", label: "7 d" },
];

export const SCENARIO_LABEL: Record<string, string> = {
  tachycardia: "Elevated heart rate",
  bradycardia: "Low heart rate",
  desaturation: "Oxygen desaturation",
  elevated_temperature: "Elevated temperature",
  abnormal_respiratory_rate: "Abnormal breathing rate",
  irregular_rhythm: "Irregular rhythm",
  solar_particle_event: "Solar particle event",
  sleep_disruption: "Sleep disruption",
  habitat_atmosphere: "Habitat atmosphere anomaly",
};
