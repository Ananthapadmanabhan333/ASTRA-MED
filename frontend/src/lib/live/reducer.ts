import type {
  Alert,
  MissionAlert,
  MissionEvent,
  SimState,
  SimulationEvent,
  VitalReading,
  WsServerMessage,
} from "@/lib/api/types";

/** Recent unified mission events kept for the notification centre and live feeds. */
export const EVENT_BUFFER = 80;
/** Sandbox frames kept for the live sandbox charts (one row per simulation step received). */
export const SIM_TRAIL = 900;

export type SimTrailRow = { t: number } & Record<string, number | null>;

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
  /** Phase 6: newest first, de-duplicated by id. */
  missionEvents: MissionEvent[];
  /** Phase 6: unresolved unified alerts that changed since the page loaded, by id. */
  missionAlerts: Record<string, MissionAlert>;
  /** Alerts opened or escalated since the notification centre was last opened. */
  unread: number;
  /** Live state of the mission simulation sandbox (null until the first sim_state message). */
  sim: SimState | null;
  /** HR and SpO2 per crew member over simulation time, for the run in `id`. */
  simTrail: { id: string | null; rows: SimTrailRow[] };
}

export function initialLive(): LiveData {
  return {
    latest: {},
    trails: {},
    openAlerts: {},
    scenarios: {},
    serverOffsetMs: null,
    lastMessageAt: null,
    missionEvents: [],
    missionAlerts: {},
    unread: 0,
    sim: null,
    simTrail: { id: null, rows: [] },
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
    case "mission_event": {
      const rest = state.missionEvents.filter((e) => e.id !== msg.item.id);
      return { ...state, missionEvents: [msg.item, ...rest].slice(0, EVENT_BUFFER), lastMessageAt: receivedAt };
    }
    case "mission_alert": {
      const missionAlerts = { ...state.missionAlerts };
      if (msg.alert.status === "resolved") delete missionAlerts[msg.alert.id];
      else missionAlerts[msg.alert.id] = msg.alert;
      const bump = msg.event === "opened" || msg.event === "escalated" ? 1 : 0;
      return { ...state, missionAlerts, unread: state.unread + bump, lastMessageAt: receivedAt };
    }
    case "sim_state": {
      const st = msg.state;
      let simTrail = st.id === state.simTrail.id ? state.simTrail : { id: st.id ?? null, rows: [] };
      if (st.latest.length) {
        const t = Date.parse(st.latest[0].ts);
        const last = simTrail.rows[simTrail.rows.length - 1];
        if (!last || last.t < t) {
          const row: SimTrailRow = { t };
          for (const r of st.latest) {
            row[`hr_${r.astronaut_id}`] = r.heart_rate;
            row[`spo2_${r.astronaut_id}`] = r.spo2;
          }
          simTrail = { id: simTrail.id, rows: [...simTrail.rows.slice(-(SIM_TRAIL - 1)), row] };
        }
      }
      return { ...state, sim: st, simTrail, lastMessageAt: receivedAt };
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
