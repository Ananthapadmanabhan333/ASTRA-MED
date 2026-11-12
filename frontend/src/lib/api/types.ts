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

// AI intelligence engine (phase 3)
export type AIStatus = Schemas["AIStatus"];
export type AIExplanation = Schemas["Explanation"];
export type AIContributor = Schemas["Contributor"];
export type BaselineResponse = Schemas["BaselineResponse"];
export type SignalBaseline = Schemas["SignalBaseline"];
export type AnomalyDetectionResponse = Schemas["AnomalyDetectionResponse"];
export type AnomalyPoint = Schemas["AnomalyPoint"];
export type AnomalyDetection = Schemas["Detection"];
export type ForecastResponse = Schemas["ForecastResponse"];
export type SignalForecast = Schemas["SignalForecast"];
export type RiskAssessment = Schemas["RiskAssessmentResponse"];
export type RiskWarning = Schemas["RiskWarning"];
export type RiskCategory = RiskAssessment["category"];
export type CrewRiskOverview = Schemas["CrewRiskOverview"];
export type CrewRiskSummary = Schemas["CrewRiskSummary"];
export type ModelPerformance = Schemas["ModelPerformanceResponse"];
export type AlertExplanation = Schemas["AlertExplanationResponse"];

// Space environment intelligence (phase 4): real NASA open data
export type DataCategory = Schemas["SpaceWeatherEvent"]["category"];
export type Freshness = Schemas["Freshness"];
export type FreshnessMode = Freshness["mode"];
export type SpaceWeatherEvent = Schemas["SpaceWeatherEvent"];
export type SpaceWeatherEventDetail = Schemas["SpaceWeatherEventDetail"];
export type SpaceNotification = Schemas["SpaceNotification"];
export type SpaceAlert = Schemas["SpaceAlert"];
export type WeatherSummary = Schemas["WeatherSummary"];
export type RadiationIntel = Schemas["RadiationIntel"];
export type EnvMission = Schemas["EnvMission"];
export type EnvMissionDetail = Schemas["EnvMissionDetail"];
export type EnvSeries = Schemas["EnvSeries"];
export type OsdrStudy = Schemas["OsdrStudy"];
export type DataSourceStatus = Schemas["DataSourceStatus"];
export type SourcesResponse = Schemas["SourcesResponse"];
export type Timeline = Schemas["Timeline"];
export type TimelineItem = Schemas["TimelineItem"];
export type NearbyEvents = Schemas["NearbyEvents"];
export type CorrelationSeriesInfo = Schemas["CorrelationSeriesInfo"];
export type CorrelationResult = Schemas["CorrelationResult"];
export type MatrixResult = Schemas["MatrixResult"];
