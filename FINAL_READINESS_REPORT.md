# ASTRA-MED final project readiness report

**Date:** 2026-11-14. **Challenge:** NASA Space Apps Challenge 2026, "Create Health Monitoring Software
for Astronauts on Space Missions". **Submission closes Sunday 15 November 2026, 23:59 local time of
your Local Event.**

## Overall status

ASTRA-MED is **ready to demonstrate and to submit**, subject to the team's decisions in "Outstanding
risks". It is **not production-deployed**: deployment is configured and documented, but the Docker
images were never built here, and no public deployment was made.

## Completed modules

| Module | State |
| --- | --- |
| Physiological monitoring (simulated) and rule alerts | Complete; live stream, history, alert lifecycle |
| **Crew self-check** (new) | Glucose, mood and symptom check-ins with ADA-based orientation bands, personal mood baseline, daily prompts, a clickable body-systems map built from real assessments, process-only guidance |
| AI intelligence | Baselines, 5 detectors + ensemble, 4 forecasters + baselines with conformal intervals, risk, explanations, model registry, pinning, inference monitoring |
| Digital twin and decision support | Daily record, trends, stages, six systems, decision packets, emergency simulator, sealed reports with PDF, cited assistant |
| NASA data | DONKI, OSDR EDA, OSDR catalogue with provenance; data explorer; inventory verified today |
| Mission control | Dashboard, crew monitoring, unified events and alert centre, timeline, sandbox, analytics, system status |
| **Guided demo mode** (new) | `/demo`: 12 automatically tracked steps; start, pause, resume, reset, scenario and speed controls; isolated sandbox |
| Security | Roles and permissions, sessions, CSRF, audit, production profile, CSP and HSTS |
| Deployment configuration | Alembic (0001, 0002), Docker, Compose, Render blueprint, probes, rollback guide |

## Remaining incomplete features

- A full screen-by-screen visual redesign and a public landing page (the phase 6 design system is
  kept).
- A slide file with real screenshots: the outline is complete, but signed-in screenshots need a
  sign-in.
- Browser end-to-end tests, multi-factor authentication, row-level access, and the open audit items
  (5 medium, 15 low).
- Real-data, analogue and clinical validation.

## Architecture summary

FastAPI + PostgreSQL (Alembic) + a Next.js 16 dashboard over REST and WebSocket, with a single API
process that runs the simulator, AI service, NASA clients, orchestrator and sandbox. Contracts flow
from Pydantic through OpenAPI to TypeScript types. Diagrams: [docs/RESEARCH_PAPER.md §6–9](docs/RESEARCH_PAPER.md),
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## AI model evaluation

Simulated data, 3 independent datasets, chronological splits:

| Result | Value |
| --- | --- |
| Learned detectors, F1 | 0.62–0.81 (fixed limits 0.36) |
| Ensemble vs LOF alone, F1 | 0.800 ± 0.052 vs 0.811 ± 0.029 (indistinguishable) |
| XGBoost heart-rate error at 1 h | 2.19 ± 0.16 bpm (climatology 3.85; neural models about 3.0) |
| 90 % interval coverage | 0.89–0.91 |
| Reproducibility | Identical metrics across retraining runs |

No clinical validation. Details: [docs/SCIENTIFIC_VALIDATION.md](docs/SCIENTIFIC_VALIDATION.md).

## NASA dataset inventory

DONKI (3,296 events stored), OSDR EDA (17 missions, 2014–2024), OSDR catalogue (188 studies), the
MSL RAD cruise dose rate, and NASA HRP references. All URLs were checked on 2026-11-14. The
api.nasa.gov DONKI proxy returns 404 and the CCMC fallback works. See [docs/DATASETS.md](docs/DATASETS.md).

## Security audit results

- **Audit:** every high-severity finding fixed or handled by configuration
  ([docs/PHASE7_AUDIT.md](docs/PHASE7_AUDIT.md)).
- **Dependencies:** `pip-audit` 0; `npm audit` production 0.
- **Self-check writes:** need the new `selfcheck:write` permission; reads are audited.

## Test execution results

[docs/TEST_REPORT.md](docs/TEST_REPORT.md):

- **Backend, full suite:** 316 passed; 2 time-of-day test failures, fixed and re-run (102 passed in
  the affected suites).
- **Frontend:** 63 passed; type-check, lint and build clean.
- **Live demo:** 10/10 steps.

## Deployment status

| Item | Status |
| --- | --- |
| Configuration and documentation | Complete |
| Migrations | Verified |
| Docker build | Not verified (no Docker engine on this machine) |
| Public deployment | None. It needs a domain layout with the frontend and API on the same registrable domain. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |

## Documentation inventory

**Root:**

- README.md
- CONTRIBUTING.md
- MASTER_PROJECT_AUDIT.md
- MASTER_COMPLETION_TRACKER.md
- this report

**docs/:**

| Topic | Files |
| --- | --- |
| Architecture, API and data | ARCHITECTURE, API, DATABASE_SCHEMA |
| AI and science | AI_ENGINE, SCIENTIFIC_VALIDATION, RESEARCH_PAPER |
| NASA data | NASA_DATA_SOURCES, NASA_DATA_INTEGRATION, DATASETS |
| Security and deployment | SECURITY, DEPLOYMENT |
| Users and limits | USER_GUIDE, LIMITATIONS |
| Quality and readiness | BENCHMARKS, TEST_REPORT, PHASE7_AUDIT, PHASE7_REPORT |
| Third parties | THIRD_PARTY |
| Product areas | MEDICAL_DECISION_SUPPORT, MISSION_CONTROL, SPACE_ENVIRONMENT |
| Competition | competition/: SUBMISSION, PRESENTATION, DEMO_SCRIPT, VIDEO_STORYBOARD |

## Competition submission readiness

- **Ready:** the text for every form field, NASA data and references, the AI-use disclosure draft,
  the challenge-fit analysis (now covered by the self-check), the 7-slide demo deck and 30-second
  video plans, and the 15-slide presentation outline.
- **The team must:**
  1. resolve the pre-event-work rule with the organisers;
  2. edit the AI disclosure;
  3. add a licence;
  4. fill in team details;
  5. produce the deck or video;
  6. submit before the deadline.

## Demonstration instructions

1. Start the `backend-postgres` and `frontend` launch configurations, and create demo accounts with
   `python scripts/create_users.py dev`.
2. Sign in as the operator.
3. Open **Crew self-check** (`/self-check`) and record a check.
4. Open **Guided demo** (`/demo`): choose a scenario and a speed, then **Start**. Watch the 12 steps
   tick, acknowledge the alert and generate the report.
5. For the operations path, run `python scripts/demo_phase7.py --sync --keep` and follow
   [docs/competition/DEMO_SCRIPT.md](docs/competition/DEMO_SCRIPT.md).

## Outstanding risks and blockers

| Risk | Impact | Action |
| --- | --- | --- |
| Space Apps FAQ forbids starting work before the event; the history starts 11 November | Eligibility | Ask the Local Lead or the organisers before submitting |
| AI-generated code must be disclosed | Eligibility and judging | Use and edit the draft in [SUBMISSION.md §2.H](docs/competition/SUBMISSION.md) |
| No LICENSE file | Apache-2.0 applies by default | Choose and add a licence |
| Signed-in UI not visually verified after the latest frontend changes | Possible visual issues | Sign in once in the browser pane, or click through the pages yourself before recording |
| Docker untested; not deployed | A public link would need more work | Submit the GitHub repository as the final project link |
| Simulated data only | Validity scoring | State it plainly; it is a strength of the honesty, not something to hide |
