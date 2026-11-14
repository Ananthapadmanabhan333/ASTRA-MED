# ASTRA-MED master project audit

**Date:** 2026-11-14. **Baseline:** commit `607fbcc` (phases 1–7).

This audit maps the master brief's nine areas to what exists, and lists what was added in this pass
(phase 8). The detailed code-level audit, with severities, file references and fix status, is
[docs/PHASE7_AUDIT.md](docs/PHASE7_AUDIT.md): 65 findings, every high-severity one fixed or handled
in configuration. It is not repeated here.

## Area by area

| # | Area | Complete | Incomplete or open |
| --- | --- | --- | --- |
| 1 | Foundation and architecture | FastAPI, async SQLAlchemy, PostgreSQL via Alembic (revisions 0001, 0002), contract-first OpenAPI to TypeScript types, Next.js 16 dashboard, REST + WebSocket | Single process (no horizontal scaling) |
| 2 | Physiological monitoring | Simulator (vitals, ECG, sleep, activity, dose), rule engine, alert lifecycle, live stream, history in SQL buckets; **crew self-check (glucose, mood, symptoms) added in phase 8** | No device or camera input |
| 3 | AI predictive intelligence | Personal baselines, 5 detectors + ensemble, XGBoost/LSTM/GRU/TCN with conformal intervals, risk rules, explanations, model registry with hashes, pinning, inference monitoring, experiment index, replication study | No real-data validation; the ensemble is no better than LOF |
| 4 | NASA data integration | DONKI, OSDR EDA and OSDR catalogue with provenance, retries and a circuit breaker; NASA data explorer; dataset inventory | RadLab detector series not integrated (portal errors); GeneLab omics only as catalogue metadata |
| 5 | Digital twin | Daily record, baselines against current values, trends with autocorrelation-adjusted CIs, mission stages, NASA events per day, six-system assessment; **body-systems map in the self-check (phase 8)** | The twin is a record, not a physiological model (by design) |
| 6 | AI medical decision support | Eight-part decision packets, process-only review workflow, emergency simulator, sealed incident reports with PDF, cited assistant with a safety layer and in-session conversation history | No approved aerospace-medicine reference library |
| 7 | Mission control | Command dashboard, crew monitoring, unified events and alert centre, situational timeline, sandbox with playback, analytics, system status; **guided demo mode (phase 8)** | — |
| 8 | Scientific validation | Chronological splits, leakage controls, all requested metrics, ablations, hyperparameters, 3-dataset replication, reproducibility check | Validation tiers 2–4 not done |
| 9 | Deployment | Dockerfiles, Compose, Render blueprint, migrations, production profile, probes, CSP and HSTS, rollback guide | Docker never built here; not deployed |

## Brief checks

| Check | Result |
| --- | --- |
| Frontend connected to the backend | Every page reads the API (contract-generated types); no `Math.random` measurements and no placeholder buttons (frontend audit) |
| Loading, error and empty states | Present on data views; gaps fixed in phase 7; the new pages use the shared state components |
| Nonfunctional buttons and placeholders | None found by the code audit. A signed-in visual walkthrough is still pending (a manual sign-in is needed) |
| Duplicate components | Small duplicates (tone maps, date helpers, pill components) and three unused shadcn components remain (low; listed in the audit) |
| Missing backend logic or database relationships | All crew tables reference `astronauts` with cascade; the new `crew_self_reports` follows the same pattern ([DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md)) |
| Unused dependencies | `next-themes` is effectively unused; backend dependencies are all used |
| Security | See [SECURITY.md](docs/SECURITY.md) and the audit. `pip-audit` 0; `npm audit` production 0, development no critical or high |
| Performance | See [BENCHMARKS.md](docs/BENCHMARKS.md) |
| Inconsistent UI | One design system (dark navy, cyan, restrained amber), shared cards, chips and states; no full redesign was done in phase 8 |

## Prioritised task list (this pass)

1. **Challenge fit:** a crew self-check with a body-systems map and glucose, mood and symptom
   check-ins (highest judging impact: Relevance). *Done.*
2. **Guided demo mode:** the twelve-step story with start, pause, resume, reset, scenario and speed
   controls. *Done* (see the tracker for verification).
3. **Requested documents:** database schema, user guide, limitations, contributing, research paper
   structure, 15-slide outline. *Done.*
4. **Verification:** tests, build and the live API. *Done*, except the signed-in visual walkthrough.
5. **Not attempted in this pass:**
   - a full UI redesign of every screen (the phase 6 design system stays);
   - a public landing page;
   - new NASA datasets (none is scientifically needed);
   - a public deployment (needs a domain decision and credentials).
