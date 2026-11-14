# Test report

Executed on 2026-11-14 on the development machine (Windows 11, Python 3.11.9, Node 24). Every
result below comes from a run in this session; nothing is estimated.

## Summary

| Suite | Command | Result |
| --- | --- | --- |
| Backend, full (SQLite plus PostgreSQL 16 integration tests) | `ASTRA_TEST_POSTGRES_URL=… pytest -q` | **316 passed, 2 failed.** Both failures are a time-of-day dependency in the phase 5/6 test clocks, which started at the real current time and so depended on the crew schedule. They fail on the previous commit as well. Fixed by pinning the clocks to 11:00 UTC |
| Backend, re-run after the fix (phases 5, 6, 7) | `pytest tests/phase5 tests/phase6 tests/phase7 -q` | **102 passed, 1 skipped** (the opt-in PostgreSQL test of phase 5, without its URL in this run) |
| Backend lint | `ruff check app tests scripts migrations` | Clean |
| Frontend unit tests | `npx vitest run` | **63 passed** (9 files) |
| Frontend types and lint | `npx tsc --noEmit`, `npm run lint` | Clean |
| Frontend production build | `npm run build` | Succeeds; 32 routes, including `/self-check` and `/demo` |
| Migrations | `alembic upgrade head` → `alembic check` → downgrade → upgrade | Pass on PostgreSQL 16 and SQLite (revisions 0001, 0002) |
| Live end-to-end demo (API) | `python scripts/demo_phase7.py --sync` | **10/10 steps passed** on PostgreSQL ([transcript](demo/demo-run.md)) |
| Live self-check API | GET and POST against the running PostgreSQL API | 401 without sign-in; summary with prompts and indicators when signed in |
| Dependency audit | `pip-audit`, `npm audit` | Python 0; npm production 0; npm development no critical or high |

## Coverage by area (backend)

| Area | Tests |
| --- | --- |
| Unit | simulator, ECG, detection rules, history buckets, metrics, baselines, features, risk, explanations, PDF layout, self-check bands and prompts |
| API | every router: health, alerts, AI, space, twin, medical, emergency, reports, assistant, mission control, sandbox, analytics, system, self-check |
| Database | PostgreSQL integration (`tests/test_postgres.py`, `tests/space/test_space_postgres.py`, `tests/phase5/test_phase5_postgres.py`); SQL and Python bucket equivalence; migrate mode; retention |
| Authentication and authorisation | scrypt, sessions, CSRF, lockout, enumeration, role matrix, admin model reload, `system:maintain`, `selfcheck:write`, report-event visibility, audit of reads |
| Validation | 422 on bad inputs (self-check, AI, sandbox, reports); production configuration refusal; request-ID sanitising |
| AI | model training (quick run), inference, anomaly detection, forecasting, explanations, batched-attribution equivalence, lazy loading, version pinning, library mismatch, deterministic planner across hash seeds, data-quality checks (artefacts, gaps) |
| End-to-end | `tests/phase6/test_e2e_mission.py` (11-step sandbox workflow in-process) and the live `demo_phase7.py` |

## Frontend

The vitest suite covers the reducer, live store reset, socket client, thresholds, formatting, auth
client, route permissions, live-versus-REST freshness, placeholder identity and the guided-demo step
logic (20 tests).

**Not covered:**

- There are no browser end-to-end tests (Playwright).
- A signed-in visual walkthrough of the pages changed in phases 7 and 8 is pending: the local
  permission policy prevents the assistant from signing in. See
  [LIMITATIONS.md](LIMITATIONS.md).

## Fixes made because of test results in this pass

1. **Self-check mood reference** formatted a missing baseline: a 500 error caught by the new
   round-trip test, then fixed.
2. **Phase 5 and 6 test clocks** depended on the time of day; pinned to 11:00 UTC.
