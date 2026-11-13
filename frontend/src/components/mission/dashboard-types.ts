/**
 * Shapes of the command dashboard sections. The API types each section's payload as an open object
 * (each section is assembled from a different module); these mirror app/mission/views.py.
 */
import type { MissionAlert, MissionEvent, AlertCenterSummary } from "@/lib/api/types";

export interface CrewSectionData {
  total: number;
  active: number;
  live_window_s: number;
  status_counts: Record<"nominal" | "advisory" | "caution" | "critical", number>;
  members: {
    astronaut_id: string;
    name: string;
    role: string;
    status: "nominal" | "advisory" | "caution" | "critical";
    live: boolean;
    heart_rate: number | null;
    spo2: number | null;
    activity_state: string | null;
    scenario: string | null;
  }[];
}

export interface HealthSectionData {
  simulator: "running" | "stalled" | "stopped";
  last_tick_age_s: number | null;
  tick_seconds: number;
  tick_failures: number;
  websocket_clients: number;
  threshold_rules: number;
  detectors: string[];
  open_rule_alerts: number;
  active_scenarios: { id: string; label: string; astronaut_id: string | null; triggered_by: string; ends_at: string }[];
}

export interface AlertsSectionData {
  summary: AlertCenterSummary;
  top: MissionAlert[];
  simulation_summary: AlertCenterSummary | null;
}

export interface AiCrewRisk {
  astronaut_id: string;
  name: string;
  risk_score: number | null;
  category: string | null;
  category_label?: string;
  health_score?: number;
  confidence_level?: string;
  top_warning?: string | null;
}

export interface AiSectionData {
  model_loaded: boolean;
  model_version: string | null;
  sweep_at: string | null;
  sweep_state: string;
  crew: AiCrewRisk[];
  highest: AiCrewRisk | null;
  note: string;
}

export interface SwxBrief {
  id: number;
  event_type: string;
  label: string;
  time: string;
  classification: string | null;
  scale: string | null;
  severity: number | null;
  magnitude: number | null;
  magnitude_unit: string | null;
  link: string | null;
}

export interface SpaceSectionData {
  window_days: number;
  counts: Record<string, number>;
  flare_classes: Record<string, number>;
  strongest_flare: SwxBrief | null;
  max_storm: SwxBrief | null;
  fastest_cme: SwxBrief | null;
  latest: Record<string, SwxBrief>;
  radiation_alerts: { id: string; event_type: string; severity: string; title: string; event_time: string; status: string; rule: string; link: string | null }[];
  freshness: { mode: string; message: string; retrieved_at: string | null };
  note: string;
}

export interface HabitatParam {
  label: string;
  value: number;
  unit: string;
  nominal: number;
  deviation_sigma: number;
}

export interface EnvironmentSectionData {
  habitat: Record<string, HabitatParam>;
  anomaly_scenario_id: string | null;
  dose_rate_msv_day: number;
  open_alerts: MissionAlert[];
  note: string;
}

export interface RadiationSectionData {
  days: { day: string; mean_crew_dose_msv: number | null; simulated_spe: boolean; nasa_events: number }[];
  nasa_events: (SwxBrief & { alert_severity: string })[];
  simulated_events: MissionEvent[];
  notes: string[];
}

export interface IncidentsSectionData {
  recent_events: MissionEvent[];
  reports: { id: string; title: string; astronaut_id: string; created_at: string; review_status: string; simulation: boolean }[];
  emergency_runs: { id: string; label: string; astronaut_id: string | null; severity: string; started_at: string; ends_at: string; cancelled_at: string | null }[];
  reports_visible: boolean;
}
