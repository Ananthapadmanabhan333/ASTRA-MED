import type { Alert, SimulationEvent, VitalReading, WsServerMessage } from "@/lib/api/types";

/** Seconds of 1 Hz readings kept in memory for the "Live" chart range and sparklines. */
export const TRAIL_SECONDS = 600;

export interface TrailPoint {
  t: number; // epoch ms
  heart_rate: number;
  spo2: number;
  systolic: number;
  diastolic: number;
  temperature_c: number;
  respiratory_rate: number;
  activity_met: number;
}

export interface LiveData {
  latest: Record<string, VitalReading>;
  trails: Record<string, TrailPoint[]>;
  openAlerts: Record<string, Alert>;
  scenarios: Record<string, SimulationEvent>;
  /** serverTime − clientTime, smoothed; lets the ECG sweep line up with sample times. */
  serverOffsetMs: number | null;
  lastMessageAt: number | null;
}

export function initialLive(): LiveData {
  return {
    latest: {},
    trails: {},
    openAlerts: {},
    scenarios: {},
    serverOffsetMs: null,
    lastMessageAt: null,
  };
}

function toPoint(r: VitalReading): TrailPoint {
  return {
    t: Date.parse(r.ts),
    heart_rate: r.heart_rate,
    spo2: r.spo2,
    systolic: r.systolic,
    diastolic: r.diastolic,
    temperature_c: r.temperature_c,
    respiratory_rate: r.respiratory_rate,
    activity_met: r.activity_met,
  };
}

function appendTrail(trail: TrailPoint[] | undefined, point: TrailPoint): TrailPoint[] {
  const base = trail ?? [];
  if (base.length && base[base.length - 1].t >= point.t) return base; // duplicate or out of order
  const cutoff = point.t - TRAIL_SECONDS * 1000;
  const start = base.findIndex((p) => p.t >= cutoff);
  const kept = start === -1 ? [] : start === 0 ? base : base.slice(start);
  return [...kept, point];
}

function smoothOffset(prev: number | null, sample: number): number {
  return prev === null ? sample : prev * 0.8 + sample * 0.2;
}

export function applyMessage(state: LiveData, msg: WsServerMessage, receivedAt: number): LiveData {
  switch (msg.type) {
    case "hello": {
      const latest = Object.fromEntries(msg.latest.map((r) => [r.astronaut_id, r]));
      const trails = { ...state.trails };
      for (const r of msg.latest) trails[r.astronaut_id] = appendTrail(trails[r.astronaut_id], toPoint(r));
      return {
        ...state,
        latest,
        trails,
        openAlerts: Object.fromEntries(msg.open_alerts.map((a) => [a.id, a])),
        scenarios: Object.fromEntries(
          msg.active_scenarios.filter((s) => s.active).map((s) => [s.id, s]),
        ),
        serverOffsetMs: smoothOffset(null, Date.parse(msg.server_time) - receivedAt),
        lastMessageAt: receivedAt,
      };
    }
    case "vitals": {
      const latest = { ...state.latest };
      const trails = { ...state.trails };
      for (const r of msg.readings) {
        latest[r.astronaut_id] = r;
        trails[r.astronaut_id] = appendTrail(trails[r.astronaut_id], toPoint(r));
      }
      return {
        ...state,
        latest,
        trails,
        serverOffsetMs: smoothOffset(state.serverOffsetMs, Date.parse(msg.ts) - receivedAt),
        lastMessageAt: receivedAt,
      };
    }
    case "alert": {
      const openAlerts = { ...state.openAlerts };
      if (msg.alert.status === "resolved") delete openAlerts[msg.alert.id];
      else openAlerts[msg.alert.id] = msg.alert;
      return { ...state, openAlerts, lastMessageAt: receivedAt };
    }
    case "simulation": {
      const scenarios = { ...state.scenarios };
      if (msg.event === "started") scenarios[msg.scenario.id] = msg.scenario;
      else delete scenarios[msg.scenario.id];
      return { ...state, scenarios, lastMessageAt: receivedAt };
    }
    case "pong":
      return {
        ...state,
        serverOffsetMs: smoothOffset(state.serverOffsetMs, Date.parse(msg.server_time) - receivedAt),
        lastMessageAt: receivedAt,
      };
    default:
      return state;
  }
}

/** Worst live condition per astronaut from open alerts whose condition is still present. */
export function liveStatus(alerts: Alert[]): "nominal" | "advisory" | "caution" | "critical" {
  const rank = { advisory: 1, caution: 2, critical: 3 } as const;
  let worst: keyof typeof rank | null = null;
  for (const a of alerts) {
    if (a.condition_cleared_at) continue;
    if (!worst || rank[a.severity] > rank[worst]) worst = a.severity;
  }
  return worst ?? "nominal";
}
