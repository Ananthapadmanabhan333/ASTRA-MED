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
| Anomaly detection, v1 | Threshold rules + personal-baseline deviation (EWMA z-score) | Transparent and testable. ML models (Isolation Forest, LSTM autoencoder) are phase 3. |
| Insights, v1 | Deterministic rule engine with cited evidence | Every statement can be traced to data. LLM summarisation is a later, optional layer. |

## Status (2026-11-09)

Phases 1 and 2 are implemented: 62 backend tests and 18 frontend unit tests pass, and the production
build succeeds. The end-to-end alert path (scenario → detection → alert → notification → acknowledge →
resolve) was verified in the browser against a SQLite database. The PostgreSQL schema compiles for the
asyncpg dialect, but the Docker Compose stack has not been run yet in this environment.

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

### Phase 3 — Predictive models (next)
- Train an Isolation Forest per crew member on baseline windows; score live samples.
- LSTM autoencoder on multivariate vitals for reconstruction-error anomaly scores (PyTorch).
- Model registry and evaluation report against injected-event ground truth from the simulator.
- Replace the synthetic radiation model with a NASA dataset adapter (see `NASA_DATA_INTEGRATION.md`).

### Phase 4 — Hardening
- Alembic migrations, authentication for operator actions, audit log, TimescaleDB hypertables
  for long histories, end-to-end tests (Playwright), accessibility audit.

## Working agreement
- Modules land one at a time with tests before the next starts.
- No measurement is shown without a "simulated" marker, and no screen claims clinical validity.
- No secrets in the repository; all configuration comes from environment variables.
