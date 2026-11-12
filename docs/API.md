# ASTRA-MED API reference

Base URL (local): `http://localhost:8000`. Interactive docs: `/docs` (Swagger UI) and `/redoc`.
Machine-readable contract: `/openapi.json`, also exported to `backend/openapi.json`, which
generates the frontend's TypeScript types (`npm run gen:api`).

> Every measurement returned is **simulated** and carries `"data_source": "simulated"`. Crew members
> are fictional. Thresholds and insights are software test values, not clinical criteria.

## Conventions

- JSON field names are `snake_case`; timestamps are ISO 8601 UTC (mission time is UTC).
- Every response carries an `X-Request-ID` header (echoed if you send one).
- Errors share one envelope:

```json
{ "error": { "code": "not_found", "message": "Astronaut AST-99 not found.", "details": null } }
```

| Status | `code` | When |
| --- | --- | --- |
| 403 | `forbidden` | Simulation control disabled (`ASTRA_SIMULATION_CONTROL_ENABLED=false`) |
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
| GET | `/api/ai/status` | `AIStatus`: enabled, loaded model version, available detectors and forecasters, last error |
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

## WebSocket: `/ws/health-monitoring`

One connection carries everything live. All messages are JSON with a `type` discriminator; the
schemas (`WsHello`, `WsVitals`, `WsAlert`, `WsSimulation`, `WsPong`, `EcgSegment`) are in the
OpenAPI document's components.

| Direction | `type` | Payload | When |
| --- | --- | --- | --- |
| server → client | `hello` | `server_time`, `tick_seconds`, `ecg_sample_rate_hz`, `astronaut_ids`, `latest[]`, `open_alerts[]`, `active_scenarios[]` | Once, on connect |
| server → client | `vitals` | `ts`, `readings[]` (one `VitalReading` per crew member), `ecg[]` (one `EcgSegment` per crew member: `start`, `sample_rate_hz`, `values_mv[]`) | Every tick (1 s) |
| server → client | `alert` | `event` (`opened`, `escalated`, `cleared`, `recurred`, `acknowledged`, `resolved`), `alert` | On every lifecycle change |
| server → client | `simulation` | `event` (`started`, `ended`, `cancelled`), `scenario` | When a test scenario changes |
| server → client | `pong` | `server_time` | Reply to ping |
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
