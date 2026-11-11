import type { components } from "./schema";

type Schemas = components["schemas"];

export type Astronaut = Schemas["Astronaut"];
export type AstronautSummary = Schemas["AstronautSummary"];
export type VitalReading = Schemas["VitalReading"];
export type HealthSnapshot = Schemas["HealthSnapshot"];
export type HistorySeries = Schemas["HistorySeries"];
export type HistoryPoint = Schemas["HistoryPoint"];
export type ComparisonSeries = Schemas["ComparisonSeries"];
export type SleepSession = Schemas["SleepSession"];
export type MissionStatus = Schemas["MissionStatus"];
export type RadiationOverview = Schemas["RadiationOverview"];
export type CrewRadiation = Schemas["CrewRadiation"];
export type Alert = Schemas["Alert"];
export type Insight = Schemas["Insight"];
export type ScenarioInfo = Schemas["ScenarioInfo"];
export type SimulationEvent = Schemas["SimulationEvent"];
export type SimulationEventCreate = Schemas["SimulationEventCreate"];
export type SystemHealth = Schemas["SystemHealth"];
export type ThresholdInfo = Schemas["ThresholdInfo"];

export type EcgSegment = Schemas["EcgSegment"];
export type WsHello = Schemas["WsHello"];
export type WsVitals = Schemas["WsVitals"];
export type WsAlert = Schemas["WsAlert"];
export type WsSimulation = Schemas["WsSimulation"];
export type WsPong = Schemas["WsPong"];
export type WsServerMessage = WsHello | WsVitals | WsAlert | WsSimulation | WsPong;

export type TimeRange = HistorySeries["range"];
export type Metric = ComparisonSeries["metric"];
export type Severity = Alert["severity"];
export type AlertStatus = Alert["status"];
export type CrewStatus = AstronautSummary["status"];
export type ActivityState = VitalReading["activity_state"];
export type ScenarioKey = ScenarioInfo["key"];
