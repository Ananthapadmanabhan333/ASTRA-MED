# ASTRA-MED development plan

ASTRA-MED is a research prototype for the NASA Space Apps Challenge 2026. It demonstrates how
crew health could be monitored, and how emerging risks could be surfaced to a flight-surgeon
team, during a long-duration mission.

> **Every physiological value in this prototype is simulated.** No real astronaut data is used.
> ASTRA-MED is not a medical device and has not been clinically validated. Thresholds and
> insights are software test scenarios, not diagnoses.

## Guiding decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Single source of simulated data | The Python simulator in the backend | One physiology model, one set of thresholds; the frontend never fabricates measurements. |
| Contract-first API | Pydantic schemas → OpenAPI → generated TypeScript types | The frontend cannot drift from the backend without a type error. |
| Live transport | One WebSocket stream (`/ws/health-monitoring`) + REST for history | REST is cacheable and simple; the socket carries 1 Hz vitals, ECG segments and alert events. |
| Storage | PostgreSQL (SQLAlchemy 2 async); SQLite allowed for tests/offline dev | Same models in both; Docker Compose provides Postgres. |
| Anomaly detection, v1 | Threshold rules + personal-baseline deviation (EWMA z-score) | Transparent and testable. Phase 3 adds learned detectors alongside them, not instead. |
| Risk scoring, v1 | Configurable point rules (`risk_config.json`) | Inspectable and adjustable; a probabilistic risk model only after validation on real data. |
| Insights, v1 | Deterministic rule engine with cited evidence | Every statement can be traced to data. LLM summarisation is a later, optional layer. |

## Status (2026-11-12)

Phase 3 is implemented (see [AI_ENGINE.md](AI_ENGINE.md)): personal baselines, five anomaly
detectors plus an ensemble, XGBoost/LSTM/GRU/TCN forecasters with conformal intervals, rule-based
risk scoring, explanations, the AI intelligence center and a reproducible evaluation pipeline. The
backend suite now has 100 tests (including the PostgreSQL integration test and 37 AI tests). All
results are on synthetic data.

Phases 1 and 2 (2026-11-09) are implemented: 62 backend unit/API tests, 1 PostgreSQL integration test and 18
frontend unit tests pass, and the production build succeeds. The end-to-end alert path (scenario →
detection → alert → notification → acknowledge → resolve) was verified in the browser on SQLite and
on PostgreSQL 16 (embedded via `pgserver`, `scripts/local_postgres.py`). The Docker Compose stack
has not been run in this environment because Docker Desktop's engine would not start.

## Phases

### Phase 1 — Mission control dashboard (this iteration)
- App shell: navigation rail, mission strip, connection status, persistent "simulated data" marker.
- Mission control overview with the live crew status board.
- Astronaut profiles, vitals, HR/SpO2 charts, anomaly list, radiation, sleep and circadian,
  generated insights, and alert/incident management pages.
- Loading, error and empty states on every data view.

### Phase 2 — Health monitoring engine (this iteration)
- Python physiological simulator: HR, SpO2, BP, temperature, respiratory rate, synthetic ECG,
  sleep, physical activity, radiation dose; multiple crew profiles; circadian and activity effects.
- Event simulation engine: tachycardia-like, bradycardia-like, desaturation, elevated temperature,
  abnormal respiratory rate, irregular rhythm, solar particle event.
- FastAPI REST + WebSocket, Pydantic validation, PostgreSQL history, structured logging and
  consistent error responses.
- Frontend integration: live cards, interactive history with time ranges, astronaut selection,
  alert notifications, connection indicator.
- Unit and API tests, Docker Compose, environment configuration.

### Phase 3 — Predictive health intelligence (this iteration)
- Personal baselines per signal, activity state and time of day, updated incrementally.
- Statistical, Isolation Forest, LOF, One-Class SVM and autoencoder detectors with a calibrated ensemble.
- Forecasts at 1/6/12/24 h (XGBoost, LSTM, GRU, TCN vs three baselines) with split-conformal intervals.
- Transparent risk rules, explanations (occlusion attribution, TreeSHAP), AI intelligence center UI.
- Versioned, hash-verified model registry; evaluation report with ablations on a chronological test split.

Still open from the phase 3 brief:
- Validation on real data. None has been used; see `NASA_DATA_INTEGRATION.md`.
- A NASA dataset adapter for radiation.

### Phase 4 — Hardening
- Alembic migrations, authentication for operator actions, audit log, TimescaleDB hypertables
  for long histories, end-to-end tests (Playwright), accessibility audit.

## Working agreement
- Modules land one at a time with tests before the next starts.
- No measurement is shown without a "simulated" marker, and no screen claims clinical validity.
- No secrets in the repository; all configuration comes from environment variables.
