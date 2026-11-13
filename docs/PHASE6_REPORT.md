# Phase 6 report: unified mission control and crew intelligence platform

Date: 2026-11-13. Scope: integrate phases 1 to 5 into one mission control platform (brief modules 1
to 10). Technical design: [MISSION_CONTROL.md](MISSION_CONTROL.md). API: [API.md](API.md).

> All crew data are simulated; the crew is fictional. NASA DONKI space-weather data are real and
> labelled. AI results come from models trained and evaluated on simulated data only. Nothing in
> ASTRA-MED is a diagnosis or clinically validated.

## 1. Architecture audit

The repository was inspected before any change (backend 265 tests passing, 3 PostgreSQL tests
opt-in; frontend 27 tests passing).

### What existed

| Area | State before phase 6 |
| --- | --- |
| Frontend | Next.js 16 (Cache Components), TypeScript, Tailwind v4, shadcn/ui, Recharts; 23 routes; one WebSocket owned by `LiveBridge`; types generated from OpenAPI. Dark navy theme already in place |
| Backend | FastAPI app factory; thin routers per phase; services in `services/`, `ai/`, `space/`, `twin/`, `medical/`, `emergency/`, `reports/`, `assistant/`, `security/` |
| Database | SQLAlchemy 2 async, PostgreSQL or SQLite, `create_all` plus ad hoc PostgreSQL `ALTER`s (no Alembic). 19 tables |
| Authentication | Server-side sessions (cookie + CSRF) or bearer tokens, scrypt, lockout, four roles, permission matrix, audit log, security headers |
| Physiological monitoring | 1 Hz simulator with ECG, activity-aware threshold, rhythm and personal-baseline rules, alert lifecycle, operator scenarios |
| AI anomaly detection | Five detectors plus a calibrated ensemble on 5-minute windows; explanations |
| Forecasting | XGBoost, LSTM, GRU, TCN and baselines with conformal intervals; rule-based risk |
| NASA integrations | DONKI, OSDR EDA and OSDR catalogue with resilient clients, provenance, offline fallback; correlation engine |
| Digital twin | Daily summaries over the whole mission, stages, trends |
| Medical assistant | Cited extractive assistant with a safety layer; optional Claude mode |
| Emergency simulator | Seven composite scenarios injected into the live stream, AI analysis snapshots |

### Findings

**Duplicated components**
- Four alert views (`/alerts` rule console, `/medical` decision queue, `/overview` active alerts,
  the old `/` alerts panel), each with its own idea of "open".
- Three timelines (space mission timeline, twin timeline, emergency run timeline) and two
  dashboards (`/` and `/overview`) with overlapping content.
- Two simulation entry points (`/anomalies`, `/emergency`), both writing into the live crew history.

**Integration gaps**
- NASA radiation-relevant events were computed on read with no lifecycle, so they could not be
  acknowledged and never reached notifications.
- AI risk, anomaly and forecast results existed only when someone opened an AI page; nothing turned
  them into events or alerts.
- The simulated habitat atmosphere was visible only inside the emergency and multisystem views.
- Emergency runs and incident reports were not in any event stream.
- The monitor had no server-side change hook (alert changes were only pushed to connected sockets).
- `/api/system/health` checked only the database and the simulator flag.
- No simulation had a speed, pause, reset or playback.

**Technical debt**
- No migrations (`create_all` plus hand-written `ALTER`s).
- `space/timeline.py` reaches into crew alert and vitals repositories.
- The AI service is coupled to the wall clock and to stored history (forecasts need 12 h of it).
- 21 navigation items with duplicated mobile and desktop navigation.
- Open items from the development plan: Playwright end-to-end tests, an accessibility audit, MFA,
  row-level access, a tamper-evident audit store, a shared rate-limit store.

### What phase 6 changed (and deliberately did not)

- **Added, did not rewrite.** Every earlier endpoint and page still works; new tables only (no
  column changes, so existing SQLite and PostgreSQL databases upgrade in place on start-up).
- **One event store and one alert centre** fed by every module (section 2). The phase 2 monitor
  stays authoritative for rule alerts; its legacy acknowledge and resolve routes now go through the
  alert centre so decisions are attributed in both places.
- **Hooks instead of coupling:** the monitor, emergency service and report service gained
  non-blocking `listeners`; the orchestrator subscribes to them.
- **A sandbox instead of more live injection:** mission simulation runs on its own engine and clock
  and never writes the live crew tables.
- **AI over supplied streams:** `AIService.analyse_stream` scores, forecasts and assesses risk on a
  supplied telemetry stream warmed with stored history, and `current_deviations` gives a cheap
  baseline comparison for the latest reading.
- **Consolidated UI:** new shell, command dashboard, crew monitoring, alert centre, timeline,
  simulation, analytics and system pages. The old crew board, crew roster, mission strip and home
  panels were removed (the live ECG moved into the dashboard crew tiles). The phase 2 rule console
  remains as a tab in the alert centre.
- Not done: Alembic migrations, Playwright, MFA and the other open hardening items (see known issues).

## 2. Integrated modules

| Brief module | Implementation |
| --- | --- |
| 1 Unified mission control dashboard | `/` from `GET /api/mission-control/overview`: mission overview, active astronauts, health monitoring status, active alerts by priority, AI risk summary, space weather status (NASA), environmental monitoring, 7-day radiation event timeline, recent incidents, system connectivity. Each section reports its own availability |
| 2 Multi-astronaut crew monitoring | `/crew` from `GET /api/crew/monitoring`: cards with live measurements, deviation from the learned personal baseline, open anomalies (rule and AI), AI risk, 7-day trends; `/crew/[id]` profile with crew navigation to the digital twin, medical intelligence, AI, alerts and timeline |
| 3 Real-time mission event orchestration | `app/mission/events.py`, `orchestrator.py`: producers from physiological monitoring, AI anomaly detection, predictive forecasting, NASA DONKI, the habitat environment, emergency and mission simulations; timestamp synchronisation, prioritisation, de-duplication, event history, alert acknowledgement and resolution, audit trail; `mission_event`, `mission_alert`, `sim_state` on the WebSocket |
| 4 Mission situational awareness | `/timeline` from `GET /api/events/timeline`: lanes for crew physiology, AI predictions, environment, radiation, solar activity, medical incidents and simulation control; filters by crew member, category, time range and sandbox run; table view |
| 5 Intelligent alert management | `/alerts` and `/api/alert-center`: identifier, astronaut, timestamps, source module, priority, supporting measurements, AI or rule explanation, confidence and uncertainty, acknowledgement, required resolution notes, action trail; experimental AI capped at P3 and labelled |
| 6 Mission simulation mode | `/simulation` and `/api/mission-sim`: start, pause, resume, stop, reset, speed, crew selection, five presets, health / environment / space-weather injection, telemetry ingestion, scheduled and on-demand AI analysis, sandbox incident reports, playback with a scrubber; amber "sandbox" marking everywhere |
| 7 Mission analytics | `/analytics` and `/api/analytics`: crew health trends, anomalies over time, sleep, environmental changes, radiation event history, model prediction performance, alert frequency, event distribution; date ranges; CSV, JSON and Markdown export |
| 8 Premium user experience | Collapsible sidebar (icon rail, mobile drawer), mission header, reusable data cards, interactive charts with tooltips and legends, notification centre, crew profile navigation, loading, empty and error states; dark navy, cyan, restrained amber reserved for the sandbox |
| 9 System reliability | `/system`, `GET /api/system/status`, consistency checks with safe repair (also at start-up), collector health and back-off, WebSocket reconnection with refetch, panel and global error boundaries, structured logs, graceful NASA and model failure, sandbox isolation, batched cache invalidation |
| 10 End-to-end testing | `tests/phase6/` (20 tests including the eleven-step workflow) and `scripts/e2e_mission.py` (the same workflow against a running API) |

## 3. Test results

All results below come from runs on 2026-11-13 in this environment (Windows, Python 3.11.9,
Node 24, PostgreSQL 16 via pgserver).

| Check | Result |
| --- | --- |
| Backend test suite (`pytest -q`, SQLite) | 285 passed, 3 skipped (the opt-in PostgreSQL tests), 6 min 10 s; the 265 earlier tests all still pass |
| Phase 6 tests (`tests/phase6`) | 20 passed |
| PostgreSQL integration tests (opt-in) | 3 passed |
| Backend lint (`ruff check app tests scripts`) | passed |
| Frontend unit tests (`npm test`) | 31 passed (27 earlier + 4 new) |
| Frontend type check and lint | passed |
| Frontend production build | passed, 30 routes |
| Live end-to-end script against the running API on PostgreSQL | 12 of 12 checks passed |

**Phase 6 tests** cover the priority model caps, event normalisation (clock skew clamping, sandbox
clocks), ref-based and windowed de-duplication with escalation, AI alerts never critical, rule-alert
mirroring with correlation and a lifecycle that stays in sync through both APIs, attribution of
legacy acknowledgements, alert ordering and summary, the habitat collector, the NASA scan (one
alert per recent event, no duplicates), timeline filters, consistency detection and repair, system
status, the dashboard and crew monitoring, sandbox isolation (no rows in the live tables), pause,
speed, injection, playback, frames, reset, external telemetry validation and detection, delegated
acknowledgement and resolution, sandbox reports with PDF, completion at planned length, failure
isolation, WebSocket delivery of `mission_event`, `mission_alert` and `sim_state`, role permissions,
and the eleven-step workflow with a trained model.

**Live end-to-end run** (`python scripts/e2e_mission.py`, operator account, 60x):

```
PASS  API reachable                              status ok
PASS  1 Start a simulated mission                crew ['AST-01', 'AST-02'], 60x
PASS  2 Generate astronaut physiological data    T+00:20:00, 242 samples
PASS  3 Send measurements to the backend         accepted 6, rejected 0, alerts opened 1
PASS  4 Run anomaly detection                    AST-01: 3 of 5 windows flagged, 1 detection(s)
PASS  5 Generate predictive analysis             risk 96.8/100 high_concern; 6 h forecasts for 4 signals
PASS  6 Retrieve NASA environmental information  DONKI 30 d: 171 events, mode live
PASS  8 Generate an alert                        [SIM] Maya Okafor: Oxygen desaturation P1
PASS  7 Correlate relevant mission events        injected: ['desaturation'], 6 NASA event(s) within 48 h, 3 related event(s)
PASS  9 Display it in mission control            6 unresolved sandbox alerts; socket delivered 6 sandbox alert messages
PASS  10 Open the astronaut digital twin         Maya Okafor, mission day 146
PASS  11 Generate an incident report             draft, integrity intact, PDF 5796 bytes
12 of 12 checks passed.
```

**Browser verification** (signed in as the operator, PostgreSQL backend): every route rendered
without error states, including all phase 1 to 5 pages; the dashboard, crew monitoring, alert
centre, timeline (live and sandbox), simulation, analytics and system pages showed backend data;
an alert was acknowledged in the UI and the phase 2 alert followed with the operator's note; a
desaturation preset ran at 20x, external measurements opened an alert, the scheduled and on-demand
AI analyses appeared, a sandbox incident report opened in the reports page; the digital twin opened
from the crew profile; the live stream went to "Reconnecting" when the API stopped and back to
"Live" on its own after restart; the phone layout and the navigation drawer worked. Two bugs found
this way were fixed: the alert detail jumping to another alert after an action, and a doubled
`[SIM]` prefix on sandbox report titles.

## 4. Known issues and limitations

- **Docker Compose was not run here** (the Docker engine does not start on this machine). The
  Dockerfiles need no change for phase 6, but the container stack is untested.
- **No migrations yet.** New tables are created by `create_all`; earlier tables were not altered.
- **One sandbox run at a time**, held in memory. If the API restarts, an active run is marked
  `interrupted` (its data stay for playback). Its sandbox alerts can still be acknowledged and
  resolved in the alert centre, which records the decision, but the run's evaluator is gone.
- **Sandbox AI needs the trained model and 12 h of stored crew history** in the last 24 h (forecast
  warm-up); otherwise the panel shows "unavailable" with the reason.
- **History starts at phase 6.** The event store records from the first start of this version. Rule
  alerts opened earlier were mirrored by the start-up consistency check, without correlation context.
- **NASA alerts only for recent events.** DONKI events older than 48 h become history events, not alerts.
- **Single API instance assumed.** Collectors and the sandbox run in-process; a second instance would
  run its own collectors (ref-based events would merge, windowed ones could duplicate).
- **Collector cost on SQLite.** The AI sweep reads about 26 h of 1 Hz data per crew member every
  120 s; PostgreSQL is recommended for long-running use.
- **Dev-only console notice.** In `next dev`, every route logs "Could not validate that a segment in
  your UI has instant navigation". This predates phase 6 (the root sign-in gate sets
  `instant = false`) and does not affect the production build.
- **Browser end-to-end tests are not automated** (Playwright is not installed). The workflow is
  automated against the API (`tests/phase6`, `scripts/e2e_mission.py`); the UI was verified by hand.
- Open hardening items remain: MFA, row-level access per crew member, a tamper-evident audit store,
  a shared rate-limit store, an accessibility audit.

## 5. Deployment

Nothing new is required beyond phase 5; new settings have safe defaults (`backend/.env.example`,
`ASTRA_MISSION_*`).

**Local, PostgreSQL without Docker (used for this report)**

```bash
cd backend
pip install -r requirements-dev.txt -r requirements-pg.txt
python -m app.ai.train            # once, about 6 minutes on CPU (models are needed for AI features)
python scripts/local_postgres.py serve
```

In a second terminal:

```bash
cd frontend
npm ci
npm run build
npm start                         # or: npm run dev
```

Create accounts with `ASTRA_DATABASE_URL=$(python scripts/local_postgres.py url) python
scripts/create_users.py dev` (demo accounts) or `scripts/create_users.py add <name> --role <role>`.

**Docker Compose (untested in this environment):** `cp .env.example .env`, set `POSTGRES_PASSWORD`,
`docker compose up --build`; create accounts inside the `api` container.

**Production settings:** `ASTRA_ENVIRONMENT=production`, `ASTRA_AUTH_COOKIE_SECURE=true` behind
HTTPS, the dashboard origin in `ASTRA_CORS_ORIGINS`, `NEXT_PUBLIC_API_URL` at build time. Liveness:
`GET /api/system/health` (no sign-in). Readiness and component health: `GET /api/system/status`
(signed in). Run one API instance. Set `ASTRA_MISSION_SIM_ENABLED=false` or
`ASTRA_SIMULATION_CONTROL_ENABLED=false` to remove the sandbox controls.

## 6. Demo

Sign in as `operator` (demo accounts above).

1. **Mission control** (`/`): the KPI band, live crew tiles with ECG, the alert queue by priority,
   experimental AI risk, the habitat, the 7-day radiation timeline (simulated doses beside real NASA
   events), recent incidents and connectivity.
2. **Mission simulation** (`/simulation`): choose *Medical emergency: oxygen desaturation*, keep
   two crew members, choose 20x and **Start simulated mission**. Note the amber sandbox marking.
3. At T+6 min the scripted desaturation starts; watch SpO₂ fall in the sandbox charts and a
   `[SIM]` alert toast arrive.
4. In **Send measurements**, pick the second crew member and **Send to backend** (SpO₂ 86, 6
   samples): the result shows the readings accepted and an alert opened.
5. From T+15 min the AI panel fills in; or select **Run AI analysis now**. The risk, flagged windows
   and 6 h forecasts are labelled experimental.
6. In **Sandbox alerts**, select **Report** on the P1 alert: the incident report opens in
   **Incident reports**, sandbox-labelled, with nearby NASA events and the AI analysis.
7. Back on **Mission control**: the sandbox appears in its own KPI tile and as unresolved sandbox
   alerts, separate from the live crew.
8. **Alert centre** (`/alerts`): switch to *Simulation sandbox*, open the alert to see its
   measurements, explanation, correlations (injected scenario, NASA events, related events) and the
   trail; acknowledge, then resolve with a note.
9. **Situational awareness** (`/timeline`): choose the sandbox run under *Data* to see its timeline
   on the simulation clock; switch back to the crew stream and filter by crew member or category.
10. **Crew monitoring** (`/crew`) and a profile: open the **Digital twin** from the profile bar.
11. **Mission simulation, playback**: pick the finished run and press **Play** or drag the cursor.
12. **Mission analytics** (`/analytics`) and **System status** (`/system`): export the Markdown
    summary; run **Check and repair**.

The same workflow without a browser: `cd backend && python scripts/e2e_mission.py --keep`, then open
`/simulation` to look at the run it left.
