# Phase 7 readiness report

**Date:** 2026-11-14. **Scope:** scientific validation, research documentation, production
deployment readiness and NASA Space Apps competition readiness for ASTRA-MED (phases 1–6).

> **Verdict.** Technically and scientifically, ASTRA-MED is ready to be shown: audited, tested,
> reproducible, documented, with an end-to-end demonstration that passes live. It is **not
> deployed publicly**; deployment is prepared but untested in Docker and on any platform.
>
> **Whether it can be submitted** depends on four items only the team can decide: the
> pre-hackathon work rule, AI disclosure, a licence, and team details. They are in section 6. The
> submission window closes **Sunday 15 November 2026, 23:59 local time of your Local Event**.

## 1. Deliverables

| # | Deliverable | Where |
| --- | --- | --- |
| 1 | Audited repository | [PHASE7_AUDIT.md](PHASE7_AUDIT.md): 65 findings; every high one fixed or handled by configuration |
| 2 | Production deployment configuration | `backend/Dockerfile`, `.dockerignore`, `docker-compose.yml`, `render.yaml`, `backend/alembic.ini` + `migrations/`, `backend/scripts/docker-entrypoint.sh`, `backend/constraints.txt`, `frontend/next.config.ts`; [DEPLOYMENT.md](DEPLOYMENT.md) |
| 3 | Scientific validation report | [SCIENTIFIC_VALIDATION.md](SCIENTIFIC_VALIDATION.md), [latest-report.md](../backend/experiments/results/latest-report.md), [seed-study.md](../backend/experiments/results/seed-study.md), [experiment-index.md](../backend/experiments/results/experiment-index.md) |
| 4 | AI model benchmarking report | [SCIENTIFIC_VALIDATION.md §3](SCIENTIFIC_VALIDATION.md#3-results) (accuracy) and [BENCHMARKS.md §4](BENCHMARKS.md#4-ai-inference) (inference) |
| 5 | Dataset provenance | [DATASETS.md](DATASETS.md), [THIRD_PARTY.md](THIRD_PARTY.md), [nasa-data-sources-report.md](reports/nasa-data-sources-report.md) (regenerated today) |
| 6 | Technical research document | [RESEARCH_PAPER.md](RESEARCH_PAPER.md): 16 sections, 3 diagrams, 34 references (all PubMed-indexed ones checked against PubMed) |
| 7 | Competition submission package | [competition/SUBMISSION.md](competition/SUBMISSION.md), README competition section |
| 8 | Presentation outline | [competition/PRESENTATION.md](competition/PRESENTATION.md): 7-slide demo deck within the official limit, plus a 12-slide pitch |
| 9 | Demonstration storyboard | [competition/VIDEO_STORYBOARD.md](competition/VIDEO_STORYBOARD.md) (30 s) and [competition/DEMO_SCRIPT.md](competition/DEMO_SCRIPT.md) |
| 10 | Deployment and execution guide | [DEPLOYMENT.md](DEPLOYMENT.md), README "Run it" and "Tests and checks" |

## 2. Completed work by section of the brief

| Section | Done |
| --- | --- |
| 1. Technical audit | Three parallel reviews, all findings re-checked. Fixed: 2 high backend (PDF denial of service, report-event leak), 3 high deployment, 3 high frontend, and a high reproducibility bug in AI serving. Plus 19 medium and 12 low findings |
| 2. Scientific validation | False-negative rate, specificity and ratio-scale MAPE added; per-model hyperparameters recorded; library versions recorded; experiment index; replication on three independent simulated datasets; reproducibility check (identical metrics across two training runs) |
| 3. NASA data provenance | Inventory of 10 datasets and references with every requested field; all URLs re-checked live today (the api.nasa.gov DONKI proxy still returns 404, and the CCMC fallback works); a live DONKI sync succeeded during the demo |
| 4. AI optimisation | Batched explanation attribution (2.1× faster, identical output); lazy loading of comparison forecasters; inference monitoring; model version pinning (rollback); library-mismatch detection; hash-dependent forecast nondeterminism found and fixed |
| 5. Security | `system:maintain` permission; model reload fixed; locked-account enumeration fixed; phase 6 reads audited; production profile; CSP and HSTS; SQL parameters hidden in logs; request IDs sanitised. `pip-audit`: 0. `npm audit` production: 0; development: no critical or high |
| 6. Performance and reliability | SQL time bucketing (6.7× faster 7-day history); concurrent throughput 15.6 → 32.5 req/s; 50 WebSocket clients stable; PDF rendering off the event loop; periodic retention; `/livez` and `/readyz` |
| 7. Production deployment | Alembic migrations (verified on PostgreSQL and SQLite); migrate mode; adopt script for existing databases; images built from the repository root with baked models and pinned versions; proxy headers; Render blueprint; Vercel and AWS instructions; rollback table |
| 8. Research document | Written, with verified references and no invented findings |
| 9. Competition package | Official 2026 rules, deadlines, fields, demo limits and judging criteria read from the site today; draft text A–K; challenge-fit gap analysis |
| 10. Final demonstration | `scripts/demo_phase7.py`: all 10 steps passed against the live PostgreSQL API ([transcript](demo/demo-run.md)) |
| 11. Presentation | Slide-by-slide outline with speaker notes and the charts to build from repository data |
| 12. Quality gate | Section 3 |

## 3. Quality gate results

| Check | Result |
| --- | --- |
| Backend test suite (SQLite plus the PostgreSQL integration tests) | **311 passed, 0 failed, 0 skipped** (11 min 5 s). Tests added after that run (request-ID sanitising): passed in the targeted re-run below |
| Targeted re-run after the final edits (phase 7, security, API, history) | **92 passed, 0 failed.** It took 60 minutes because the live demo API and the scrypt-heavy security tests shared the CPU |
| AI model tests | Included above (`tests/ai`, 37; phase 7 AI and evaluation tests, 10) |
| Integration tests | PostgreSQL tests included above (`ASTRA_TEST_POSTGRES_URL` set) |
| End-to-end | `demo_phase7.py`: 10/10 steps live on PostgreSQL; phase 6 end-to-end test in the suite |
| Database migrations | `alembic upgrade head` → `alembic check` (no drift) → `downgrade base` → `upgrade head` on PostgreSQL 16 and SQLite; migrate-mode start-up test; the existing development database matches the models exactly |
| Lint | `ruff`: clean. Frontend: `eslint`, `tsc` clean |
| Frontend tests | 43 passed (vitest 5.1.0) |
| Frontend production build | Succeeds; 30 routes |
| Deployment configuration | `render.yaml` and `docker-compose.yml` parse; entrypoint shell syntax OK; production build serves CSP (no `unsafe-eval`), HSTS and Permissions-Policy with no CSP violations. **Docker images not built:** the Docker engine does not run on this machine |
| Navigation routes | All 30 routes build; the 25 navigation links resolve (frontend audit); deep links render the sign-in screen and survive sign-in |
| NASA source references | All URLs checked live today; PubMed-indexed references checked against PubMed |
| Simulation isolation | Phase 6 sandbox tests in the suite (the sandbox writes only to its own tables) |
| Final demonstration | Passed (section 2, item 10) |
| Broken buttons / missing data in the signed-in UI | **Partly verified.** Code-level audit found no placeholder buttons; error and empty states were fixed. A signed-in browser walkthrough after the phase 7 frontend changes was **not done** (section 5) |

## 4. Measured outcomes

**Model accuracy** (simulated data, three datasets):

- **Detection:** learned detectors F1 0.62–0.81, against 0.36 for fixed limits.
- **Ensemble:** F1 0.800 ± 0.052, statistically indistinguishable from LOF (0.811 ± 0.029).
- **Forecasting:** XGBoost heart-rate MAE 2.19 ± 0.16 bpm at 1 h, against 3.85 ± 0.28 for
  climatology and about 3.0 for the neural models.
- **Intervals:** coverage of 90 % intervals 0.89–0.91.

**Engineering:**

- **History:** 7-day history 968 → 145 ms; comparison 3,093 → 488 ms.
- **Concurrency:** p50 under 20 concurrent clients 682 → 126 ms.
- **Detection with explanations:** 710 → 343 ms.
- **Reports:** PDF worst case 4.4 s → 0.012 s.

## 5. Incomplete items and remaining blockers

| Item | Status | What is needed |
| --- | --- | --- |
| Signed-in browser walkthrough of the phase 7 frontend changes | Not done. The local permission policy blocked reading the demo credentials and creating a test account; unit tests, type-check, lint and the production build pass | Sign in once in the browser pane (any demo account) and the walkthrough can be finished, or check the pages listed in [DEMO_SCRIPT.md](competition/DEMO_SCRIPT.md) by hand |
| Docker images and Compose stack | Reviewed, never built or run | Run `docker compose up --build` on a machine where Docker works |
| Public deployment (Render / Vercel / AWS) | Prepared, not deployed (the brief says not to deploy without verification) | Choose a domain layout (same registrable domain) and run the pre-launch checklist |
| Real-data validation (tiers 2–4) | Not done; cannot be done with open data | Data-use agreement for analogue or clinical data |
| Crew self-assessment mode (challenge fit) | Not built; gap analysis in the submission package | Team decision; see section 6 |
| Open audit items | 5 medium and 15 low | Listed in [PHASE7_AUDIT.md](PHASE7_AUDIT.md) |
| Hashed dependency lock, nonce-based CSP, JSON logs | Open | Hardening for a real deployment |

## 6. Decisions for the team before submitting

1. **Pre-event work.** The official FAQ says teams are not allowed to begin work before the
   hackathon (14–15 Nov). This repository's history starts on 11 November. Ask the Local Lead or the
   organisers before submitting.
2. **AI disclosure.** SI use must be described, and AI-generated code must be acknowledged in text
   and metadata. A factual draft is in [SUBMISSION.md §2.H](competition/SUBMISSION.md); the README
   now carries a disclosure, and the commits carry co-author trailers.
3. **Licence.** Add an OSI licence (for example Apache-2.0). Without one, NASA distributes the
   content under Apache-2.0.
4. **Team details** (name, members, contributions) for the slides and the form.
5. **Optional, for the Relevance score:** a small crew self-check view (prompted measurements,
   glucose and mood entry, plain-language status with colour and text). It is not built.

## 7. Files changed in phase 7 (overview)

- **Backend:** `ai/service.py` (batched attribution, lazy models, pinning, inference stats),
  `ai/monitoring.py` (new), `ai/timeline.py` and `medical/multisystem.py` (deterministic
  tie-break), `ai/metrics.py`, `ai/experiments/{runner,report,tracking}.py`,
  `ai/forecasting/data.py`, `api/{ai_routes,mission_routes,report_routes,routes,ws}.py`,
  `core/config.py` (production profile, schema mode, retention, docs flag, model pin),
  `db/{migrations,retention}.py` (new), `db/session.py`, `main.py` (probes, retention, request IDs,
  docs), `mission/{events,views}.py`, `reports/pdf.py`, `repositories/vitals.py` (SQL buckets),
  `security/{audit,rbac,service}.py`, `services/{history,hub}.py`, `space/timeline.py`; Alembic
  (`alembic.ini`, `migrations/`); scripts `bench_ai.py`, `bench_api.py`, `seed_study.py`,
  `demo_phase7.py`, `db_adopt.py`, `docker-entrypoint.sh`, `local_postgres.py`; `tests/phase7/`
  (new); `constraints.txt`, `requirements.txt`, `.env.example`, `Dockerfile`.
- **Frontend:** notification centre, placeholder identity (`lib/api/placeholder.ts`), live freshness
  (`lib/live/freshness.ts`), sign-out clean-up, error and threshold states, wording, history-panel
  performance, accessibility labels, the system view's repair permission, `next.config.ts` (CSP,
  HSTS), dependency moves and upgrades, regenerated API types.
- **Repository:** `.dockerignore` (moved to the root), `docker-compose.yml`, `render.yaml`, `.env.example`,
  `.claude/launch.json` (benchmark and production-frontend configurations).
- **Docs:** this report, the audit, scientific validation, benchmarks, datasets, third-party
  licences, deployment, research document, the competition package, the demo transcript, and
  updates to README, ARCHITECTURE, API, SECURITY and DEVELOPMENT_PLAN.
