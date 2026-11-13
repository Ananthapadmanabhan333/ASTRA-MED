# Unified mission control (phase 6)

Phase 6 joins the earlier modules into one operations platform: a command dashboard, crew
monitoring, one event history, one alert centre, a situational-awareness timeline, an isolated
mission simulation sandbox, mission analytics and platform health checks.

> All crew data are simulated and the crew is fictional. NASA DONKI space weather is real and is
> labelled **NASA data** wherever it appears. Experimental AI output is labelled and never ranked
> above P3. Nothing here is a diagnosis or clinically validated.

## Event orchestration

```
 monitor change hook ─┐  (rule alerts, scenarios)
 emergency hook ──────┤                                   ┌─► mission_events (history)
 report hook ─────────┼─► queue ─► consumer ─┐            │
                      │                      ├─► publish ─┼─► WebSocket "mission_event"
 AI sweep (120 s) ────┤                      │  normalise │
 NASA scan (300 s) ───┤   collectors call    │  prioritise└─► alert centre (mission_alerts,
 habitat check (10 s) ┘   publish directly ──┘  de-duplicate     mission_alert_actions)
```

`app/mission/`:

| Module | Responsibility |
| --- | --- |
| `taxonomy.py` | Sources, categories, data origins, classifications and the shared priority model |
| `events.py` | `MissionEventService.publish`: timestamp synchronisation, prioritisation, de-duplication, persistence, broadcast |
| `alerts.py` | `AlertCenter`: one lifecycle for every module, rule-alert mirroring, delegation, audit trail |
| `orchestrator.py` | Producers, the queue consumer, collectors with health, correlation |
| `sandbox.py`, `presets.py` | Mission simulation sandbox and its scenario presets |
| `views.py` | Command dashboard, crew monitoring and timeline read models |
| `analytics.py` | Daily aggregates and CSV / JSON / Markdown export |
| `system.py` | Component health and database consistency checks |

### Timestamp synchronisation

Every time is converted to timezone-aware UTC. An event keeps its **source time**
(`occurred_at`; the simulation clock for sandbox events) and the **wall-clock time** the pipeline
received it (`received_at`), so the latency is visible. An operations event stamped more than
`ASTRA_MISSION_CLOCK_SKEW_TOLERANCE_S` in the future is clamped to `received_at` and the skew is
stored in `clock_skew_s`. Sandbox clocks may legitimately run ahead and are not clamped; telemetry
sent to a sandbox run with a timestamp ahead of its clock is clamped and reported per reading.

### Prioritisation

| Level | Score | Typical cause |
| --- | --- | --- |
| P1 Critical | ≥ 80 | Rule-based detection of a critical simulated value |
| P2 High | ≥ 60 | Caution-level rule detection; NASA SEP or strong-flare indicator; simulated SPE or habitat anomaly |
| P3 Medium | ≥ 35 | Advisory detections; **every experimental AI output** (capped) |
| P4 Low | < 35 | Information (scenario starts, risk category changes back to normal) |

Score = severity base (critical 90, caution 65, advisory 40, info 15) + 5 for a specific crew
member + 5 on escalation, then capped by classification: experimental AI at 59 (never above P3,
never `critical`), NASA environmental indicators at 79 (never P1).

### De-duplication

A fingerprint identifies each event. Events that describe a source record (`ref_type` + `ref_id`:
a rule alert, a DONKI event, a scenario, a report) are merged whenever they recur; other events are
merged when they repeat within `ASTRA_MISSION_EVENT_DEDUPE_MINUTES`. A merge increments
`occurrences`, refreshes `last_seen_at` and raises the severity if the repeat is worse. Alerts are
unique per `(source, source_ref)`; a resolved alert is never reopened, a new episode gets a new
reference.

## Alert centre

Every alert carries: identifier, astronaut (where applicable), observed and received timestamps,
source module, priority, severity, supporting measurements, explanation (rule or AI), confidence
and uncertainty, classification, correlations, acknowledgement and resolution with notes, and an
append-only action trail (`mission_alert_actions`).

- **Rule alerts** from the phase 2 monitor are mirrored. The monitor stays authoritative: an
  acknowledgement or resolution in the alert centre goes through `MonitoringService.update_alert`,
  and `/api/alerts/{id}/acknowledge|resolve` now goes through the alert centre, so both paths are
  attributed to the operator. The consistency check repairs any drift.
- **Sandbox rule alerts** are delegated to the sandbox evaluator in the same way.
- **AI, NASA and environment alerts** live only in the alert centre.
- Resolution notes are required. An acknowledged alert that escalates is re-activated.
- **Experimental AI predictions** are `classification: experimental_ai`, severity at most
  `caution`, priority at most P3, and every screen shows "Experimental AI" with the note that they
  are not confirmed medical emergencies.

## Correlation

When an alert with a crew member opens, the orchestrator records what else was happening: injected
test scenarios affecting that crew member (the known cause of simulated deviations), the simulated
habitat state, the habitat dose-rate multiplier, real NASA DONKI events within ±48 h (temporal
proximity only, with the vantage-point note) and mission events from the 30 minutes before. For
sandbox alerts the NASA window is centred on the wall-clock time of the run.

## Mission simulation sandbox

A run has its own `SimulationEngine` (selected crew, its own random stream, no random events), its
own `AlertEvaluator` and its own clock. Every wall-clock tick the clock advances `speed` × tick
seconds in steps of at most 10 simulated seconds. It writes only `mission_simulations` and
`mission_sim_samples`; its events and alerts carry `context: simulation`, `data_origin: sandbox`
and the run id, and every title starts with `[SIM]`. A failure inside a run marks it `failed`
without touching live monitoring.

| Capability | How |
| --- | --- |
| Start, pause, resume, stop, reset | `POST /api/mission-sim/runs`, `/runs/{id}/pause|resume|stop|reset`. Reset closes the run's open sandbox alerts; data stay for playback |
| Speed | 0.5x to `ASTRA_MISSION_SIM_MAX_SPEED`, changeable while running |
| Presets | Nominal transit, desaturation emergency, solar particle event, cabin atmosphere fault, multi-system cascade (`presets.py`) |
| Event injection | Health anomalies (phase 2 catalogue), habitat atmosphere, simulated SPE, flare and storm markers; now or at a simulated minute |
| Telemetry ingestion | `POST /runs/{id}/telemetry`: validated readings through the same rule detection |
| AI | Every 15 simulated minutes (after 15 minutes of stream) or on request: the phase 3 ensemble, forecaster and risk model over the sandbox stream, warmed with the crew member's stored history (`AIService.analyse_stream`) |
| Playback | `GET /runs/{id}/playback` (bucketed series, events, alerts) and `/frame?at=` (exact state at one instant) |
| Incident report | `POST /runs/{id}/report`: same ten sections and integrity digest, sandbox-labelled |

## Reliability

- `GET /api/system/status`: database (with latency), simulator loop, WebSocket, AI models,
  orchestration and each collector, the three NASA sources, the digital twin and the sandbox.
- `GET /api/system/consistency` and `POST /api/system/consistency/repair`: rule-alert mirrors,
  orphaned mirrors, detector state, runs left active by a restart, orphaned sandbox samples, broken
  alert-event links, incident report digests (reported, never repaired) and future timestamps.
  The repairing check also runs at start-up.
- Collectors record runs, failures, last success and last error and back off after failures; a
  failing NASA source or missing model never stops the others. Each dashboard section is built
  independently and reports its own availability.
- The browser socket reconnects with capped backoff; after a reconnect every mission query is
  refetched so events missed meanwhile come from the REST history. Panels sit inside error
  boundaries; the root layout has a global error boundary.

## Frontend

| Route | Purpose |
| --- | --- |
| `/` | Command dashboard: mission, active astronauts, alert queue, AI risk, health monitoring, environment, radiation timeline, space weather, incidents, connectivity |
| `/crew`, `/crew/[id]` | Crew monitoring cards; profile with crew navigation |
| `/alerts` | Unified alert centre (and the phase 2 rule alert log) |
| `/timeline` | Situational awareness swimlanes and event list |
| `/simulation` | Mission simulation sandbox and playback |
| `/analytics` | Mission analytics and exports |
| `/system` | System status and consistency checks |

The shell has a collapsible sidebar (state kept per browser), a mission header with the MET clock,
crew status, the sandbox indicator, the live-stream state and the notification centre.
