# ASTRA-MED API reference

Base URL (local): `http://localhost:8000`. Interactive docs: `/docs` (Swagger UI) and `/redoc`.
Machine-readable contract: `/openapi.json`, also exported to `backend/openapi.json`, which
generates the frontend's TypeScript types (`npm run gen:api`).

> Every measurement returned is **simulated** and carries `"data_source": "simulated"`. Crew members
> are fictional. Thresholds and insights are software test values, not clinical criteria.

## Authentication (phase 5)

Every endpoint except `GET /api/system/health`, `POST /api/auth/login` and `POST /api/auth/token`
needs a signed-in user whose role grants the endpoint's permission ([SECURITY.md](SECURITY.md)).

- **Browsers:** `POST /api/auth/login` sets an HttpOnly session cookie and returns `csrf_token`.
  Send it as `X-CSRF-Token` on every POST, PATCH and DELETE, and send requests with credentials.
- **Scripts:** `POST /api/auth/token` returns `access_token`. Send `Authorization: Bearer <token>`;
  no CSRF token is needed.
- **WebSocket:** the session cookie (or bearer header) is checked before the connection is accepted.

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/token -H 'Content-Type: application/json' \
  -d '{"username":"operator","password":"<password>"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s localhost:8000/api/twin/AST-01 -H "Authorization: Bearer $TOKEN"
```

## Conventions

- JSON field names are `snake_case`; timestamps are ISO 8601 UTC (mission time is UTC).
- Every response carries an `X-Request-ID` header (echoed if you send one).
- Errors share one envelope:

```json
{ "error": { "code": "not_found", "message": "Astronaut AST-99 not found.", "details": null } }
```

| Status | `code` | When |
| --- | --- | --- |
| 401 | `unauthenticated` | Not signed in, or the session expired, went idle or was revoked |
| 403 | `forbidden` | Role lacks the permission (`details.reason = "permission"`, `details.required`), missing CSRF token (`"csrf"`), or simulation control disabled |
| 429 | `rate_limited` | Too many sign-in attempts from one client (`Retry-After` header) |
| 404 | `not_found` | Unknown astronaut, alert or scenario |
| 409 | `conflict` | Scenario already running for that target; alert already acknowledged/resolved |
| 409 | `insufficient_data` | AI endpoint: not enough stored history to build a baseline, features or a forecast |
| 422 | `validation_error` | Bad query/body; `details` lists each failing field |
| 500 | `internal_error` | Unexpected server error (logged with the request ID) |
| 503 | `models_unavailable` | AI endpoint: no trained model version (run `python -m app.ai.train`) or `ASTRA_AI_ENABLED=false` |

## REST endpoints

### System
| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/system/health` | `SystemHealth`: API status, database check, simulator state, WebSocket client count |
| GET | `/livez` | `{"status": "alive"}`: liveness probe, no dependencies, no auth *(phase 7)* |
| GET | `/readyz` | `{"status": "ready"}`, or **503** `starting` / `database_unavailable`: readiness probe for load balancers, no auth *(phase 7)* |

### Crew
| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/astronauts` | `AstronautSummary[]`: profile, baseline vitals, current status, latest reading, open alert count, running scenario |
| GET | `/api/astronauts/{astronaut_id}` | `Astronaut`: profile only |

### Health
| Method | Path | Query | Returns |
| --- | --- | --- | --- |
| GET | `/api/health/{astronaut_id}` | | `HealthSnapshot`: latest vitals, sleep summary, activity and exercise, radiation brief, open alerts, active scenarios |
| GET | `/api/health/{astronaut_id}/history` | `range` = `1h`·`6h`·`24h`·`7d` (default `6h`), `max_points` 30–1000 (default 360) | `HistorySeries`: stored vitals averaged into equal buckets (`resolution_seconds`) |
| GET | `/api/health/{astronaut_id}/sleep` | `days` 1–30 (default 7) | `SleepSession[]`: scheduled vs actual window, duration, efficiency, onset offset |
| GET | `/api/health/compare` | `metric` (`heart_rate`, `spo2`, `systolic`, `diastolic`, `temperature_c`, `respiratory_rate`, `activity_met`), `range`, `max_points` | `ComparisonSeries`: one series per crew member on shared buckets |

Example:

```bash
curl "http://localhost:8000/api/health/AST-02/history?range=24h&max_points=96"
```

```json
{
  "astronaut_id": "AST-02", "range": "24h", "resolution_seconds": 900,
  "start": "2026-11-08T18:00:00Z", "end": "2026-11-09T18:00:00Z",
  "points": [
    { "ts": "2026-11-08T18:07:30Z", "heart_rate": 61.2, "spo2": 98.1, "systolic": 123.0,
      "diastolic": 79.0, "temperature_c": 36.88, "respiratory_rate": 13.1, "activity_met": 1.71, "samples": 3 }
  ],
  "data_source": "simulated"
}
```

### Mission
| Method | Path | Query | Returns |
| --- | --- | --- | --- |
| GET | `/api/mission/status` | | `MissionStatus`: mission day and elapsed time, Earth distance and light delay, crew status counts, open/critical alerts, habitat dose rate |
| GET | `/api/radiation` | `days` 1–365 (default 30) | `RadiationOverview`: per-crew mission/career dose, % of the 600 mSv reference, current dose rate, daily doses with SPE flags |

### Alerts
| Method | Path | Query / body | Returns |
| --- | --- | --- | --- |
| GET | `/api/alerts` | `status` (repeatable: `active`, `acknowledged`, `resolved`), `severity` (repeatable: `advisory`, `caution`, `critical`), `astronaut_id`, `hours` 1–720 (default 168), `limit` ≤ 500 | `Alert[]`, newest first |
| GET | `/api/alerts/{alert_id}` | | `Alert` |
| POST | `/api/alerts/{alert_id}/acknowledge` | `{"note": "optional, ≤500 chars"}` | `Alert` (`status: acknowledged`) |
| POST | `/api/alerts/{alert_id}/resolve` | `{"note": "..."}` | `Alert` (`status: resolved`); the detector is released so a continuing breach opens a fresh alert |
| GET | `/api/monitoring/thresholds` | | `ThresholdInfo[]`: the prototype limits the detector uses, including activity overrides |

Alert lifecycle: a breach sustained for 5 samples opens an alert (`active`). A worse severity
escalates it and re-activates it if it was acknowledged. Values back within limits for 10
samples set `condition_cleared_at`, but the alert stays open until an operator resolves it.

Categories: `threshold` (fixed, activity-aware limits), `rhythm` (beat-interval irregularity in
the synthetic ECG), `baseline` (|z| ≥ 4 against the person's expected value for 20 samples,
severity `advisory`).

### Insights
| Method | Path | Query | Returns |
| --- | --- | --- | --- |
| GET | `/api/insights` | `astronaut_id` (optional) | `Insight[]`: rule-based findings with `evidence[]`, `suggested_action`, `method: "rule-based"` |

### Simulation (software test scenarios)
| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET | `/api/simulation/scenarios` | | `ScenarioInfo[]`: catalogue with descriptions, default duration, affected metrics |
| GET | `/api/simulation/events` | query: `astronaut_id`, `hours` (default 48), `limit` | `SimulationEvent[]` (operator and simulator-triggered) |
| POST | `/api/simulation/events` | `SimulationEventCreate` | `201 SimulationEvent` |
| DELETE | `/api/simulation/events/{event_id}` | | `SimulationEvent` with `cancelled_at`; the effect fades over 8 s |

```bash
curl -X POST http://localhost:8000/api/simulation/events \
  -H "Content-Type: application/json" \
  -d '{"scenario": "desaturation", "astronaut_id": "AST-02", "intensity": 1.0, "duration_seconds": 240}'
```

Scenario keys: `tachycardia`, `bradycardia`, `desaturation`, `elevated_temperature`,
`abnormal_respiratory_rate`, `irregular_rhythm`, `solar_particle_event` (crew-wide, so
`astronaut_id` is ignored). `intensity` 0.3–1.5, `duration_seconds` 30–3600.

## AI intelligence (phase 3)

Experimental models trained and evaluated on simulated data only. Every response carries
`"data_source": "simulated"`, a `disclaimer`, the `model_version`, `limitations`, and, where
relevant, an `explanation`: what changed, kind, contributing signals, significance, confidence and
data limitations. None of it is a diagnosis. Methods and results are in [AI_ENGINE.md](AI_ENGINE.md).

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/ai/status` | `AIStatus`: enabled, loaded model version, available detectors and forecasters, last error; *(phase 7)* `pinned_version` (`ASTRA_AI_MODEL_VERSION`), `forecasters_loaded` (neural forecasters load on first use), `library_mismatch` (training vs running versions), `inference` (per operation: count, errors, p50/p95/max over the last 200 calls; process memory) |
| POST | `/api/ai/anomaly-detection` | `AnomalyDetectionResponse`: per-window ensemble and per-detector scores (score ÷ threshold, flagged at ≥ 1), detector votes, detections of 10 min or more with explanations, data quality |
| GET | `/api/ai/astronaut/{id}/baseline` | `BaselineResponse`: per signal, the reference for the current state and time of day (center, scale, percentiles, depth), current z and percentile, rolling 24 h / 7 d statistics, the profile by state |
| GET | `/api/ai/astronaut/{id}/forecast` | `ForecastResponse`: per signal, observed history and 30-min forecast steps to 24 h with 90 % intervals, summaries at 1/6/12/24 h with the test MAE and coverage, explanation (TreeSHAP drivers for XGBoost) |
| GET | `/api/ai/astronaut/{id}/risk-assessment` | `RiskAssessmentResponse`: risk score 0–100, category (`normal`, `low_concern`, `moderate_concern`, `high_concern`), health score, prioritised warnings with points and evidence, components, explanation |
| GET | `/api/ai/crew-overview` | `CrewRiskOverview`: one risk summary per crew member plus the crew-wide warning queue |
| GET | `/api/ai/model-performance` | `ModelPerformanceResponse`: dataset summary, anomaly and forecast metrics, ablations, SHAP summary, limitations, registered versions, the markdown report |
| GET | `/api/ai/explanations/{alert_id}` | `AlertExplanationResponse`: why a phase 2 alert fired (its rule) plus the anomaly ensemble's attribution in the surrounding 5-minute window |
| POST | `/api/ai/models/reload` | `AIStatus` after reloading the latest verified model version. Returns 403 unless `ASTRA_SIMULATION_CONTROL_ENABLED=true` |

`POST /api/ai/anomaly-detection` body:

```json
{
  "astronaut_id": "AST-02",
  "start": "2026-11-12T08:00:00Z",
  "end": "2026-11-12T14:00:00Z",
  "models": ["lof", "one_class_svm"],
  "include_explanations": true
}
```

- `start` and `end` default to the last 6 h. Omit `models` to use the full calibrated ensemble.
  With a subset, a window is flagged when a majority of the chosen detectors flag it.
- Instead of stored data you can send up to 20,000 `readings`. Each has `ts`, an optional value for
  each signal (`heart_rate`, `spo2`, `systolic`, `diastolic`, `temperature_c`, `respiratory_rate`;
  `null` when missing), `activity_state` and `activity_met`. They are scored against the crew
  member's stored personal baseline.

`GET /api/ai/astronaut/{id}/forecast` query parameters:

- `model`: `xgboost` (default), `lstm`, `gru`, `tcn`, `persistence`, `seasonal_naive` or
  `climatology`.
- `signals`: any of `heart_rate`, `spo2`, `respiratory_rate`, `temperature_c`. Repeat the parameter
  for several signals.

Responses are cached for `ASTRA_AI_CACHE_SECONDS` (30 s).

## Space environment (phase 4)

**Real NASA open data:**
- DONKI space weather.
- OSDR Environmental Data App ISS measurements.
- OSDR study metadata.

**Every payload states:**
- each value's `category`: `measured`, `indicator`, `model`, `estimate`, `simulated` or `metadata`;
- a `freshness` object, with `source_id`, `retrieved_at` and `mode`, where mode is one of `live`,
  `cached`, `offline-fallback`, `unavailable` or `pending`, plus a message.

Responses always come from the local store, so they work when NASA services are down. Sources,
licences and limitations are in [NASA_DATA_SOURCES.md](NASA_DATA_SOURCES.md); methods are in
[SPACE_ENVIRONMENT.md](SPACE_ENVIRONMENT.md).

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/space/sources` | `SourcesResponse`: per source, endpoints with failover and rate-limit state, collection period, record counts, units, update frequency, licence, citation, caveats, health, quality indicators and recent sync runs. Also the evaluated sources, and whether a personal NASA key is configured (the key itself is never returned) |
| POST | `/api/space/sync` | `SyncResult`. Body: `{"source": "donki" or "eda" or "osdr", "days"?, "missions"?, "force"?}`. Operator action; 403 unless `ASTRA_SIMULATION_CONTROL_ENABLED=true` |
| GET | `/api/space/weather/summary?days=30` | `WeatherSummary`: counts by type, flare classes, strongest flare, strongest storm, fastest CME, latest per type, radiation-related alerts, notifications, provider caveats |
| GET | `/api/space/weather/events` | `EventList`. Query: `start`, `end` (ISO 8601, default the last 30 days), `types` (repeatable: FLR, CME, SEP, GST, RBE, IPS, HSS, MPC, WSA), `min_severity` (0–5), `limit` |
| GET | `/api/space/weather/events/{id}` | `SpaceWeatherEventDetail`: the normalised event plus the original DONKI record in `raw` |
| GET | `/api/space/weather/notifications?days=30` | `SpaceNotification[]` |
| GET | `/api/space/alerts?days=30` | `SpaceAlert[]`: prototype radiation-related alerts from DONKI events (indicators, never doses) |
| GET | `/api/space/radiation?days=30` | `RadiationIntel`: `measured` (A, mGy/day), `indicators` (B), `estimate` (C, mSv), `simulated` (D, mSv/day), daily `timeline`, `alerts`, `rules` |
| GET | `/api/space/iss/missions` | `EnvMission[]`: EDA missions with period, milestones and what has been ingested |
| GET | `/api/space/iss/missions/{name}?resolution=6h` | `EnvMissionDetail`: series (resolution `1h`, `6h` or `1d` for telemetry; dosimetry stays daily) with per-series quality, DONKI events during the mission, linked OSDR studies, caveats |
| GET | `/api/space/osdr/studies` | `StudyList`. Query: `topic` (radiation, rodent, spaceflight, physiology, environment), `q`, `organism`, `project_type`, `mission`, `live` (also query OSDR now), `limit`, `offset` |
| GET | `/api/space/timeline` | `Timeline`. `mode=mission` (default) with `start`, `end` (at most 31 days) and `astronaut_id`; or `mode=iss&mission=RR-1` |
| GET | `/api/space/timeline/nearby?ts=…&window_hours=48` | `NearbyEvents`: space-weather events within the window, with offsets in hours |
| GET | `/api/space/correlation/series` | `CorrelationSeriesInfo[]`: available daily series with category, unit and covered date ranges |
| POST | `/api/space/correlation/analyze` | `CorrelationResult`. Body: `{x, y, start, end, max_lag (0–14), rolling_window (5–90)}`. Returns Pearson and Spearman with CIs, n and n_eff, trend-adjusted r, lags with BH q-values, cross-correlation, rolling r, scatter, warnings and interpretation. `status: insufficient` when fewer than 5 days overlap |
| POST | `/api/space/correlation/matrix` | `MatrixResult`. Body: `{series: [2..10 ids], start, end, method}`. Pairwise r, n, p and BH q |

**Error responses:**

| Status | `code` | When |
| --- | --- | --- |
| 400 | `bad_request` | Invalid type, period or mode |
| 404 | `not_found` | Unknown event, mission or series |
| 503 | `space_disabled` | `ASTRA_SPACE_ENABLED=false` |

## Auth and administration (phase 5)

| Method | Path | Permission | Returns |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | none | `SessionInfo` (user, permissions, `csrf_token`, `expires_at`); sets the session cookie |
| POST | `/api/auth/token` | none | `TokenResponse` (bearer `access_token`, `expires_at`) |
| GET | `/api/auth/me` | signed in | `SessionInfo` |
| POST | `/api/auth/logout` | signed in | 204; revokes the session and clears the cookie |
| POST | `/api/auth/password` | signed in | 204; changes your password, signs out your other sessions |
| GET | `/api/auth/roles` | signed in | `AccessMatrix`: roles, their permissions, permission descriptions |
| GET / POST | `/api/admin/users` | `users:manage` | `AdminUser[]` / create (`UserCreate`, password policy enforced) |
| PATCH | `/api/admin/users/{user_id}` | `users:manage` | role, active, display name, unlock; role change and deactivation revoke sessions |
| GET | `/api/admin/audit` | `audit:read` | `AuditEntry[]`, newest first; filters `username`, `action`, `outcome`, `resource_type`, `hours`, `limit` |

## Digital twin and medical decision support (phase 5)

All need `health:read` unless noted. All crew data is simulated; see
[MEDICAL_DECISION_SUPPORT.md](MEDICAL_DECISION_SUPPORT.md).

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/twin/{astronaut_id}` | `TwinProfile`: astronaut, mission day and stage, current reading and status, resting comparison (configured, early mission, last 7 d, last 24 h, learned baseline), exposure, 7-night sleep, coverage (stored vs regenerated days), category legend |
| GET | `/api/twin/{astronaut_id}/timeline?days=30` (or `start`, `end`) | `TwinTimeline`: one `TwinDay` per mission day (statistics, activity, sleep, simulated dose, alerts and scenarios, coverage, basis) plus NASA DONKI events that day |
| GET | `/api/twin/{astronaut_id}/trends?metric=&statistic=&days=` | `TwinTrend`: daily values, 7-day rolling mean, autocorrelation-aware slope per 30 days with 95 % CI; cumulative series for `dose_msv` |
| GET | `/api/twin/{astronaut_id}/stages` | `TwinStages`: per mission stage mean ± SD and difference from the first stage (Welch CI) |
| GET | `/api/multisystem` | `CrewSystemsOverview`: six system statuses and patterns per crew member |
| GET | `/api/multisystem/{astronaut_id}` | `MultisystemAssessment`: per system the inputs (value, reference, z, status, category, source), open alerts, Phase 3 model outputs, explanation and data quality; cross-system patterns; habitat and sleep overlays when a run is active |
| GET | `/api/decision-support/queue?hours=24&include_advisory=false&include_closed=false` | `DecisionQueue`: significant alerts with escalation level, critical first |
| GET | `/api/decision-support/alerts/{alert_id}` | `DecisionPacket`: observation, measurements, baseline comparison, environmental context, AI output, confidence and uncertainty, data quality, review workflow |
| GET | `/api/overview?period=7d&astronaut_id=` | `MissionOverview`: crew cards, active alerts, alert history per day, incidents (if `reports:read`), runs, resting HR and sleep trends, environment, rule-generated summary |

### Emergency simulator

| Method | Path | Permission | Returns |
| --- | --- | --- | --- |
| GET | `/api/emergency/scenarios` | `health:read` | `EmergencyScenarioInfo[]` (7 scenarios, severities, components) |
| POST | `/api/emergency/runs` | `simulation:control` | `EmergencyRun` (201). Body: `scenario`, `astronaut_id` (unless crew-wide), `severity` (`mild`/`moderate`/`severe`), `duration_seconds` (30–3600), `nights` (sleep, 1–7). 409 if something already runs on the target |
| GET | `/api/emergency/runs?hours=72` · `/api/emergency/runs/{run_id}` | `health:read` | `EmergencyRun` with status, components, overlay, stored analyses |
| POST | `/api/emergency/runs/{run_id}/cancel` | `simulation:control` | `EmergencyRun` |
| POST | `/api/emergency/runs/{run_id}/analyze` | `simulation:control` or `reports:write` | `EmergencyAnalysis` snapshot (also stored on the run) |
| GET | `/api/emergency/runs/{run_id}/timeline?astronaut_id=` | `health:read` | `EmergencyTimeline`: vitals, events, simulated environment, overlay |

### Incident reports

| Method | Path | Permission | Returns |
| --- | --- | --- | --- |
| POST | `/api/reports` | `reports:write` | `IncidentReport` (201). Body: `alert_id`, `run_id` or `astronaut_id` (+ optional `occurred_at`, `title`, `summary`) |
| GET | `/api/reports?astronaut_id=&status=&limit=` | `reports:read` | `ReportSummary[]` |
| GET | `/api/reports/{report_id}` | `reports:read` | `IncidentReport` with `content` (all ten sections), `content_sha256`, `integrity` |
| POST | `/api/reports/{report_id}/review` | `reports:write` for draft ⇄ pending review; `reports:review` for under review, reviewed, closed | `IncidentReport`. Body: `status`, `note` (required for `reviewed`). 409 for a transition that is not allowed |
| GET | `/api/reports/{report_id}/pdf?download=false` | `reports:read` | `application/pdf` (inline, or attachment with `download=true`); audited |

### Assistant

| Method | Path | Permission | Returns |
| --- | --- | --- | --- |
| GET | `/api/assistant/status` | `health:read` | `AssistantStatus`: mode, indexed passages per source, reference library entries |
| POST | `/api/assistant/ask` | `assistant:use` | `AssistantAnswer`: `statements[]` (text, `citations`, `kind`), `sources[]` (`D#` records, `S#` passages with verbatim excerpts and links), `missing_information`, `declined`, `escalation`, `actions` (e.g. create a report), `understood`. Body: `question`, optional `astronaut_id` in focus |

## Unified mission control (phase 6)

Methods are in [MISSION_CONTROL.md](MISSION_CONTROL.md). All need `health:read` unless noted.
Every event and alert says where it came from (`source`, `data_origin`: `simulated`, `sandbox`,
`nasa`) and its `context` (`operations` for the crew stream, `simulation` for sandbox runs).

### Command dashboard and crew monitoring

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/mission-control/overview` | `MissionControlOverview`: mission status plus independent sections (`available`, `reason`, `data`): crew, health monitoring, alerts, AI, space weather (needs `space:read`), environment, radiation timeline, incidents (reports need `reports:read`); component connectivity; sandbox state |
| GET | `/api/crew/monitoring` | `CrewMonitoring`: per crew member the latest reading, live flag, deviations from the personal baseline, open rule and unified alerts, the latest AI risk sweep, a 7-day trend, active scenarios and mission dose |

### Events and situational awareness

| Method | Path | Query | Returns |
| --- | --- | --- | --- |
| GET | `/api/events` | `category`, `source`, `severity`, `priority` (repeatable), `astronaut_id` (crew-wide events included), `context` (default `operations`), `simulation_id`, `start`, `end` or `hours` (default 24), `q`, `limit` | `MissionEvent[]`, newest first: source and received times, latency, clock skew, priority, occurrences |
| GET | `/api/events/counts` | `context`, `astronaut_id`, `start`, `end`, `hours` | `EventCounts` by category, source, priority, origin and severity |
| GET | `/api/events/timeline` | `category` (repeatable), `astronaut_id`, `context`, `simulation_id` (the run's whole clock range), `start`, `end`, `hours` | `MissionTimeline`: lanes per category, counts, notes |
| GET | `/api/events/{event_id}` | | `MissionEvent` |

*(phase 7)* All four hide `incident_reports` events from roles without `reports:read` (the single
event returns 404).

### Alert centre

| Method | Path | Permission | Returns |
| --- | --- | --- | --- |
| GET | `/api/alert-center` | `health:read` | `MissionAlert[]`: unresolved first, then by priority and time. Filters: `status`, `priority`, `source`, `category`, `classification` (repeatable), `astronaut_id`, `context`, `simulation_id`, `hours` (closed alerts only; unresolved always show), `limit` |
| GET | `/api/alert-center/summary` | `health:read` | `AlertCenterSummary`: open, acknowledged, unresolved by priority and source, experimental open, resolved in 24 h, mean time to acknowledge |
| GET | `/api/alert-center/{alert_id}` | `health:read` | `MissionAlertDetail`: the alert, its originating event and the full action trail |
| POST | `/api/alert-center/{alert_id}/acknowledge` | `alerts:manage` | `MissionAlert`. Body `{"note"}` optional. 409 if already acknowledged or resolved |
| POST | `/api/alert-center/{alert_id}/resolve` | `alerts:manage` | `MissionAlert`. Body `{"note"}` **required** (resolution notes) |

Rule alerts acknowledged or resolved here are updated in the phase 2 store too, and
`/api/alerts/{id}/acknowledge|resolve` is mirrored into the alert centre with the operator's name.

### Mission simulation sandbox

| Method | Path | Permission | Returns |
| --- | --- | --- | --- |
| GET | `/api/mission-sim/catalogue` | `health:read` | `SimCatalogue`: presets with their scripts, injection types, limits |
| GET | `/api/mission-sim/state` | `health:read` | `SimState` of the active (or last) run; `status: idle` when none |
| GET | `/api/mission-sim/runs` · `/runs/{run_id}` | `health:read` | `SimRun` (config, injections, AI analyses, stats) |
| POST | `/api/mission-sim/runs` | `simulation:control` | `SimState` (201). Body: `preset`, `crew`, `speed`, `duration_minutes`, `seed`, `ai_every_minutes`, `name` (all optional). 409 if a run is active |
| POST | `/runs/{run_id}/pause` · `/resume` · `/stop` · `/reset` | `simulation:control` | `SimState` |
| POST | `/runs/{run_id}/speed` | `simulation:control` | `SimState`. Body `{"speed"}` |
| POST | `/runs/{run_id}/inject` | `simulation:control` | The fired or scheduled injection. Body: `injection`, `astronaut_id` (health only), `intensity` 0.3–1.5, `duration_s`, `at_minute` (omit for now) |
| POST | `/runs/{run_id}/telemetry` | `simulation:control` | `SimIngestResult`. Body: `readings[]` (`astronaut_id`, `ts` on the simulation clock, any of the six signals within physiological ranges, optional activity and rhythm), `source` |
| POST | `/runs/{run_id}/analyze` | `simulation:control` | Per crew member: anomaly windows and detections, forecast horizons, risk |
| GET | `/runs/{run_id}/playback?max_points=` | `health:read` | `SimPlayback`: bucketed series, injections, events, alerts |
| GET | `/runs/{run_id}/frame?at=` | `health:read` | `SimFrame`: readings, active injections and alerts at one instant |
| POST | `/runs/{run_id}/report` | `reports:write` | `IncidentReport` (201). Body `{"alert_id"}` or `{"astronaut_id"}` |

### Analytics

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/analytics/summary?start=&end=&context=&astronaut_id=` | `AnalyticsSummary`: crew trends, anomalies per day, sleep, environment, radiation history, model performance (simulated test split), alert frequency, event distribution |
| GET | `/api/analytics/export?format=csv|json|md&...` | The same range as a CSV daily table, full JSON or a Markdown summary (attachment) |

### System (any signed-in user)

| Method | Path | Permission | Returns |
| --- | --- | --- | --- |
| GET | `/api/system/status` | signed in | `SystemStatus`: overall status, components with detail and metrics, orchestrator and collector health |
| GET | `/api/system/consistency` | `audit:read` or `simulation:control` | `ConsistencyReport` (read-only) |
| POST | `/api/system/consistency/repair` | `system:maintain` *(phase 7)* | `ConsistencyReport` after safe repairs |

## WebSocket: `/ws/health-monitoring`

One connection carries everything live. All messages are JSON with a `type` discriminator; the
schemas (`WsHello`, `WsVitals`, `WsAlert`, `WsSimulation`, `WsPong`, `EcgSegment`, and since phase 6
`WsMissionEvent`, `WsMissionAlert`, `WsSimState`) are in the OpenAPI document's components.

| Direction | `type` | Payload | When |
| --- | --- | --- | --- |
| server → client | `hello` | `server_time`, `tick_seconds`, `ecg_sample_rate_hz`, `astronaut_ids`, `latest[]`, `open_alerts[]`, `active_scenarios[]` | Once, on connect |
| server → client | `vitals` | `ts`, `readings[]` (one `VitalReading` per crew member), `ecg[]` (one `EcgSegment` per crew member: `start`, `sample_rate_hz`, `values_mv[]`) | Every tick (1 s) |
| server → client | `alert` | `event` (`opened`, `escalated`, `cleared`, `recurred`, `acknowledged`, `resolved`), `alert` | On every lifecycle change |
| server → client | `simulation` | `event` (`started`, `ended`, `cancelled`), `scenario` | When a test scenario changes |
| server → client | `pong` | `server_time` | Reply to ping |
| server → client | `mission_event` | `event` (`created`, `updated`), `item` (`MissionEvent`) | A new event, or a repeat that raised its severity |
| server → client | `mission_alert` | `event` (`opened`, `escalated`, `updated`, `acknowledged`, `resolved`), `alert` (`MissionAlert`) | Every unified alert change |
| server → client | `sim_state` | `state` (`SimState`) | Every sandbox tick and control change |
| client → server | — | `{"action": "ping"}` | Optional keep-alive; other messages are ignored |

Connections from browser origins not in `ASTRA_CORS_ORIGINS` are closed with code 1008. ECG
segments are contiguous: each starts where the previous one ended, so clients can lay them
end to end.

```js
const ws = new WebSocket("ws://localhost:8000/ws/health-monitoring");
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === "vitals") console.log(msg.readings.map((r) => `${r.astronaut_id} ${r.heart_rate} bpm`));
};
```
