# ASTRA-MED architecture

```
                         ┌───────────────────────────── backend (FastAPI, Python 3.11) ─────────────────────────────┐
                         │                                                                                          │
                         │  simulator/                     detection/                    services/                  │
                         │  ┌──────────────┐  readings     ┌──────────────────┐ changes  ┌──────────────────────┐   │
                         │  │ engine.step()├──────────────►│ AlertEvaluator   ├─────────►│ MonitoringService    │   │
                         │  │  physiology  │  + ECG chunks │  threshold rules │          │  tick loop (1 Hz)    │   │
                         │  │  schedule    │               │  rhythm check    │          │  persist every 5 s   │   │
                         │  │  ecg         │               │  baseline z-score│          │  broadcast           │   │
                         │  │  scenarios   │◄──────────────┤                  │          └───┬──────────┬───────┘   │
                         │  │  radiation   │  operator      └──────────────────┘              │          │           │
                         │  └──────────────┘  scenarios                                       │          │           │
                         │                                    repositories/ ◄─────────────────┘          │           │
                         │                                    SQLAlchemy 2 async                         │           │
                         │   api/routes.py (REST)  ◄── read models: history, health, mission,            │           │
                         │   api/ws.py (WebSocket) ◄── insights ── ConnectionHub ◄────────────────────────┘           │
                         └────────────┬───────────────────────────────┬─────────────────────────────────────────────┘
                                      │ PostgreSQL (TIMESTAMPTZ)      │ JSON over HTTP + WS
                                      ▼                               ▼
                               ┌─────────────┐        ┌──────────────────────────── frontend (Next.js 16) ──────────┐
                               │ postgres:16 │        │ lib/api: openapi-fetch client + types generated from OpenAPI│
                               └─────────────┘        │ lib/live: LiveSocket → reducer → zustand store; ECG buffer  │
                                                      │ TanStack Query caches (invalidated by socket events)        │
                                                      │ components: shell, crew board, ECG canvas, charts, alerts   │
                                                      └─────────────────────────────────────────────────────────────┘
```

## Backend modules (`backend/app`)

| Package | Responsibility |
| --- | --- |
| `core/` | Settings (`ASTRA_*` env vars), logging, error envelope, UTC helpers |
| `simulator/` | Pure, deterministic data generation. `profiles` (fictional crew), `schedule` (nightly sleep and daily exercise drawn from seeded per-day streams), `physiology` (circadian + activity targets, lag, noise), `ecg` (Gaussian-wave beats, rhythm features), `scenarios` (test-event catalogue and envelopes), `radiation` (GCR + SPE dose), `engine` (ticks, random events, history backfill) |
| `detection/` | `rules` (activity-aware thresholds), `baseline` (EWMA residual z-score), `evaluator` (alert lifecycle state machine) |
| `db/` | SQLAlchemy models; a `UTCDateTime` type gives identical timezone behaviour on PostgreSQL and SQLite |
| `repositories/` | Thin query functions per aggregate; routes never touch SQL |
| `services/` | `monitoring` (runtime core), `seeding` (incremental backfill), `history` (bucketing), `health`, `mission`, `insights`, `hub` (WebSocket fan-out with per-socket send locks), `mappers` |
| `schemas/` | Pydantic models: the API contract. WebSocket message models are injected into OpenAPI |
| `api/` | Thin REST handlers and the WebSocket endpoint; `ai_routes.py` serves `/api/ai/*` |
| `ai/` | Phase 3 intelligence engine: windows, personal baselines, causal features, five anomaly detectors + ensemble, forecasters with conformal intervals, rule-based risk, explanations, experiment runner and hash-verified model registry. See [AI_ENGINE.md](AI_ENGINE.md) |

### Runtime loop

Every `ASTRA_TICK_SECONDS` (1 s):

1. `engine.step(now)` advances each crew member: activity from the schedule → target vitals → first-order lag
   toward target → Ornstein–Uhlenbeck noise → scenario deltas. It renders a contiguous ECG chunk and may start
   a random scenario (Poisson, `ASTRA_RANDOM_EVENTS_PER_HOUR`).
2. `AlertEvaluator.process(reading)` runs threshold, rhythm and baseline detectors and returns lifecycle changes.
3. Readings are buffered and written every `ASTRA_PERSIST_EVERY_TICKS` (5 s); changed alerts and scenarios are written immediately.
4. A `vitals` message plus any `alert`/`simulation` events are broadcast. Slow clients are dropped.

A failing tick is logged and the loop continues. On startup the service backfills any gap in history
(7 days at 5-minute resolution on a fresh database), reconstructs resolved alerts for past scenarios, and
restores open alerts into the evaluator so a restart doesn't duplicate them.

### Why these choices

- **Single source of simulated data.** The browser never fabricates measurements; it shows what the API serves,
  labelled `simulated`. The frontend therefore needs the backend running, and shows clear offline/error states otherwise.
- **Determinism.** A fixed `ASTRA_SIMULATOR_SEED` reproduces the same crew history, which keeps tests and demos repeatable.
- **Activity-aware rules.** A heart rate of 150 bpm is expected on the treadmill and alarming at a desk; limits change with activity.
- **Operators close alerts.** The evaluator marks recovery but never auto-resolves, so a human decision is always recorded.

### AI engine at runtime

`AIService` (`app/ai/service.py`) sits beside `MonitoringService` and only reads.

- **Model bundle:** at startup, a background task verifies the newest version under
  `backend/artifacts/` against its SHA-256 manifest, then loads it.
- **Requests:** the service reads stored samples through the existing repositories and windows
  them to 5 minutes. It keeps one personal baseline per crew member, updated with new windows every
  60 s and refitted from 7 days of history every 6 h.
- **Concurrency:** scoring and forecasting run in `asyncio.to_thread`, so the 1 Hz tick loop is
  never blocked. Results are cached for 30 s.
- **No models:** if no model version exists, or `ASTRA_AI_ENABLED=false`, the AI endpoints return
  503. Phases 1 and 2 keep working unchanged.

Training is offline (`python -m app.ai.train`). It uses a separately generated, labelled synthetic
dataset, never the live database, so evaluation labels cannot leak into serving.

## Frontend modules (`frontend/src`)

| Path | Responsibility |
| --- | --- |
| `app/` | Routes: `/` mission control, `/crew`, `/crew/[id]`, `/vitals`, `/alerts`, `/anomalies`, `/radiation`, `/sleep`, `/insights`; `error.tsx`, `not-found.tsx` |
| `lib/api/` | `schema.d.ts` (generated), typed client, error normalisation (`ApiError`), TanStack Query hooks and keys |
| `lib/live/` | `LiveSocket` (reconnect with capped backoff, stale watchdog, ping), pure `reducer`, zustand `store`, mutable `ecg-buffer` |
| `lib/` | Formatting (UTC mission time), metric metadata, crew identity encoding (validated colour + dash), threshold classifier, series merge |
| `components/shell/` | App shell, navigation, mission strip, connection indicator, persistent "Simulated data" marker, `LiveBridge` (socket → store, cache invalidation, alert toasts) |
| `components/vitals/`, `crew/`, `charts/` | ECG canvas sweep, readouts, sparklines, history small multiples, crew comparison, profile |
| `components/alerts/`, `simulation/`, `radiation/`, `sleep/`, `insights/` | Feature views |
| `components/data/` | `Panel`, `PageHeader`, `LoadingState`, `ErrorState`, `EmptyState`, `QueryView` |

Live data flows in through one WebSocket owned by `LiveBridge`. High-frequency ECG samples bypass React
state entirely: the canvas reads the buffer each animation frame, positioning samples by timestamp
(aligned with a smoothed server clock offset), so the sweep is smooth regardless of frame rate. REST
queries cover everything historical; socket events invalidate the affected queries.

Next.js 16 with Cache Components prerenders every route's shell; all data is fetched client-side after
hydration. Hooks that read the URL (`usePathname`) and dynamic `params` sit inside `<Suspense>`, as
Cache Components requires.

## Data model

| Table | Key columns |
| --- | --- |
| `astronauts` | id, profile, baseline (JSON), sleep and exercise plan, prior career dose |
| `vital_samples` | astronaut_id, ts (index with astronaut_id), HR, SpO2, BP, temperature, RR, activity, rhythm, RMSSD, scenario, data_source |
| `alerts` | id, astronaut_id, rule_key, category, severity, status, values (trigger, threshold, peak), lifecycle timestamps, operator note |
| `simulation_events` | id, scenario, astronaut_id (null = crew-wide), intensity, started/ends/cancelled, triggered_by |
| `sleep_sessions` | astronaut_id + night (unique), scheduled vs actual window, duration, efficiency |
| `radiation_doses` | astronaut_id + day (unique), mission_day, dose_msv, solar_particle_event |

Schema creation uses `create_all` for the prototype; Alembic migrations are planned for phase 4.
