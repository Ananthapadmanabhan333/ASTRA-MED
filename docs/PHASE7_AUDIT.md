# Phase 7 technical audit

## Scope and method

The audit covered the whole repository at commit `8fae33c` (phases 1–6) on 2026-11-14:

- **Backend:** about 24,000 lines of Python.
- **Frontend:** about 29,000 lines of TypeScript.
- **Deployment files and dependencies.**

Three read-only reviews ran in parallel (backend security and correctness, frontend, deployment
and dependencies). Each finding below was then re-checked against the code before it was fixed.
Profiling and benchmarks ([BENCHMARKS.md](BENCHMARKS.md)) found the performance items; a
reproducibility check found the AI serving bug.

**Severity:**

- **High:** a security or data-correctness failure a user can trigger.
- **Medium:** a real defect with a narrower trigger, or a production blocker.
- **Low:** hardening, robustness or hygiene.

**Status:**

- **Fixed:** changed in phase 7 and covered by a test or a measurement.
- **Documented:** cannot be fixed in code alone; handled by deployment configuration.
- **Open:** known and not fixed; see the reason.

## Summary

| Severity | Found | Fixed | Partly fixed | Documented | Open |
| --- | --- | --- | --- | --- | --- |
| High | 9 | 8 | 0 | 1 | 0 |
| Medium | 27 | 19 | 1 | 2 | 5 |
| Low (grouped by item) | 29 | 12 | 0 | 2 | 15 |

Automated checks on the final tree:

- `pip-audit`: 0 known vulnerabilities in `requirements*.txt`.
- `npm audit --omit=dev`: 0.
- Full `npm audit`: 0 critical or high; 13 low/moderate, all in development tooling (the
  typescript-eslint chain under `eslint-config-next`, and `shadcn`).
- `ruff`, `eslint` and `tsc`: clean.

## High

| # | Area | Finding | Fix | Status |
| --- | --- | --- | --- | --- |
| H1 | Reports | PDF line breaking shrank long words one character at a time and re-measured each time (cubic), synchronously on the event loop. A 2,000-character word took 4.4 s and froze the simulator tick and every request | Single-pass linear break (`pdf._break_token`); `render_report` runs in a worker thread. Identical output on all layout cases; 20,000 characters in 0.012 s | Fixed (`test_long_tokens_wrap_in_linear_time_and_fit_the_width`) |
| H2 | Access control | Incident-report events (title, ID, review status, author) were served to every `health:read` role through `/api/events`, the timeline, counts, the overview and the live stream, while the reports themselves need `reports:read` | `SOURCE_PERMISSIONS` / `hidden_sources()` filter all event reads; the WebSocket hub records each connection's permissions and sends restricted messages only to permitted sockets | Fixed (`test_incident_report_events_hidden_without_reports_read`, `test_hub_sends_restricted_messages_only_to_permitted_sockets`) |
| H3 | Deployment | Session cookie `SameSite=Strict` cannot work with the frontend and API on different sites (`vercel.app` vs `onrender.com`) | Same-site domain layout required and explained (app. and api. subdomains) | Documented ([DEPLOYMENT.md §2](DEPLOYMENT.md#2-domain-layout-required-for-sign-in)) |
| H4 | Deployment | Behind a proxy, uvicorn trusted no forwarded headers, so every client shared the proxy IP: one person could exhaust the login throttle for everyone, and audit IPs were wrong | Entrypoint passes `--forwarded-allow-ips "$FORWARDED_ALLOW_IPS"`; the Render blueprint sets it | Fixed (configuration; untested in Docker) |
| H5 | Deployment | `auth_cookie_secure` defaulted to false and nothing enforced it in production | `production_problems()` refuses to start in production without Secure cookies, with SQLite, without Alembic mode or with auth disabled | Fixed (`test_production_profile_refuses_unsafe_settings`) |
| H6 | Frontend | Notification centre showed "No unresolved alerts" when the alert request failed | Error state with retry, warning badge, "?" count | Fixed (subagent; unit tests; not yet seen signed in in a browser) |
| H7 | Frontend | Switching metric, crew member or context showed the previous selection's data under the new labels until the fetch completed (e.g. HR values labelled "%") | Placeholder data kept only for the same subject (`sameSubject`); labels from the response; placeholder dimmed | Fixed (`freshness.test.ts`) |
| H8 | Frontend | After a socket disconnect, frozen WebSocket readings were preferred over fresher REST data, still labelled "Live" | `preferLive`: live value only while connected and not older than REST | Fixed (`freshness.test.ts`) |
| H9 | AI serving | Planned dominant activity used `max(set(states))`; set order depends on the per-process string hash seed, so neural forecasts for the same input differed between processes by up to 7.8 bpm | Ties go to the earliest state, as in training | Fixed (`test_planned_state_is_independent_of_string_hashing`; forecasts bit-identical across processes) |

## Medium

| # | Area | Finding | Status |
| --- | --- | --- | --- |
| M1 | Access control | `POST /api/ai/models/reload` was unreachable for every role: admin has `models:manage` but not the router's `health:read` | **Fixed:** separate admin router (`test_admin_can_reload_models_but_not_read_health_data`) |
| M2 | Access control | The data-changing consistency repair was gated by a read permission (`audit:read`) | **Fixed:** new `system:maintain` permission (operator, admin) (`test_consistency_repair_needs_system_maintain`) |
| M3 | Sign-in | A locked account answered with a distinct message and no scrypt work, which confirmed the username exists | **Fixed:** same message and hashing as a wrong password (`test_locked_account_gets_the_same_answer_as_a_wrong_password`). The hard 15-minute lockout can still keep an account locked; progressive backoff is open |
| M4 | Audit | Phase 6 crew-data reads (crew monitoring, alert centre, events, overview, analytics export, sandbox) were never audited | **Fixed** (`test_phase6_crew_reads_are_audited`) |
| M5 | Data | Retention ran only at start-up; `vital_samples` grows about 69,000 rows a day | **Fixed:** periodic retention of vitals and expired sessions; audit log and event history kept by design (`test_retention_removes_only_rows_older_than_the_window`) |
| M6 | Performance | History and comparison loaded about 123,000 raw rows per crew member for 7 days and bucketed them in Python on the event loop (0.97 s and 3.1 s) | **Fixed:** SQL bucketing, 6.7× faster, identical buckets (`test_sql_buckets_match_python_bucketing`) |
| M7 | Performance | Anomaly explanations attributed one window at a time (about 70 % of detection time) | **Fixed:** batched per detector, 2.1× faster, identical output |
| M8 | Deployment | No database migrations: `create_all` plus hard-coded ALTERs; new columns never applied | **Fixed:** Alembic baseline `0001`, migrate mode, `db_adopt.py` (`test_migrate_mode_refuses_an_unmigrated_database_then_starts_after_upgrade`) |
| M9 | Deployment | Only `/api/system/health`, which answers 200 even when the database is down | **Fixed:** `/livez`, `/readyz` (503 until ready or when the database fails) (`test_liveness_and_readiness_probes`) |
| M10 | Deployment | Models trained at container start (about 6 min), repeated on every restart without a persistent disk; library versions not recorded | **Fixed:** `TRAIN_MODELS=1` bakes models into the image; `ASTRA_TRAIN_ON_START`; library versions recorded and compared at load |
| M11 | Deployment | A missing `ASTRA_DATABASE_URL` silently fell back to a SQLite file in the container | **Fixed:** refused in production; `postgres://` URLs accepted |
| M12 | Deployment | Frontend had no CSP, HSTS or Permissions-Policy | **Fixed:** CSP with `connect-src` limited to the API and WebSocket origins. `script-src` still needs `'unsafe-inline'` for Next.js hydration (nonce-based CSP is open) |
| M13 | Deployment | Dependencies unpinned | **Partly fixed:** `constraints.txt` pins the exact tested versions; no hashes |
| M14 | Deployment | PyTorch always installed (hundreds of MB) | **Fixed:** `INSTALL_TORCH` build argument |
| M15 | Deployment | API and WebSocket URLs fixed at frontend build time | **Documented:** build per environment; CSP derived from the same values |
| M16 | Deployment | The simulator, hub, sandbox and throttle are in-process, so only one instance can run | **Documented:** one instance, no autoscaling |
| M17 | Frontend | Admin sessions polled the alert centre and got 403 every 15 s | **Fixed:** query enabled only with `health:read` |
| M18 | Frontend | Signing out cleared the REST cache but not the live store or the ECG buffer | **Fixed** (`store-reset.test.ts`) |
| M19 | Frontend | Sign-out ignored a failed server response, so the user appeared signed out while the cookie was still valid | **Fixed** |
| M20 | Frontend | Several views showed an endless skeleton or "no alerts yet" on error; failed thresholds removed all colouring silently | **Fixed:** error states and a threshold notice |
| M21 | Frontend | Wording asserted facts without data ("regular" rhythm, "at GCR background") and a hard-coded 92 % SpO₂ line | **Fixed:** API thresholds and neutral wording |
| M22 | Frontend | The history panel re-rendered 5 charts every second on non-live ranges | **Fixed** |
| M23 | API | `GET /api/space/osdr/studies?live=true` writes to the database and calls NASA with only `space:read`; its cache grows per query | **Open:** should become a POST needing `space:sync`, with a bounded cache |
| M24 | Audit | Each rejected anonymous WebSocket handshake writes an audit row (unbounded) | **Open:** dedupe and rate-limit by IP |
| M25 | Alerts | The legacy `/api/alerts/{id}/resolve` resolves without the resolution note the alert centre requires | **Open:** route both through `AlertCenter.act` |
| M26 | Concurrency | Two concurrent sandbox starts can both succeed; concurrent report reviews can lose a history entry | **Open:** lock around start; row lock or version column for reviews |
| M27 | Performance | AI baseline frames and twin day computation still build DataFrames on the event loop | **Open:** move into worker threads |

## Low

**Fixed:**

- API docs are off in production by default.
- Bound SQL parameters are never logged (`hide_parameters`).
- Client `X-Request-ID` values are sanitised.
- `.dockerignore` patterns now apply at every depth.
- The image owns only `/app/artifacts`.
- The assistant's docs corpus is copied into the image.
- `shadcn` moved to devDependencies.
- vitest upgraded to 5.1.0, which removed two critical development-only advisories.
- The wrong service name in `.env.example` is corrected, and `backend/.env.example` is complete.
- The dev-credentials hint shows only in development builds.
- Severity dots have screen-reader text.
- `LazyModels`' membership check no longer loads the model it asks about.

**Documented:**

- Vercel preview URLs are not on the CORS list.
- Docker Compose is a local stack only.

**Open:**

| Area | Item |
| --- | --- |
| Input validation | Unknown `astronaut_id` in analytics → 500; unbounded "last N hours" in the assistant parser; OSDR offset and twin `end` far in the future overflow |
| Sign-in | Login throttle dict never pruned; password change is not throttled and failures are not audited |
| NASA sync | `SyncRequest.days` up to 3,650 runs about 10 minutes inside one request |
| Monitoring | The pending buffer is cleared before insert, so a database error drops buffered readings |
| Assistant | Claude mode creates a client per question; `anthropic` is not in requirements (optional mode) |
| Database | Request-scoped sessions plus service sessions could exhaust the pool under about 20 concurrent dashboard polls |
| Logging | Line-oriented, not JSON |
| Images | Base images pinned by tag, not digest; no frontend image healthcheck |
| Compose | Database password inside the URL |
| Rate limits | None on expensive endpoints (assistant, PDF, AI) |
| Hosts | No `TrustedHostMiddleware` |
| Frontend links | URLs from NASA and assistant data are used in `href` without a scheme allow-list (React 19 blocks `javascript:`); report download path not URL-encoded; popup after `await` |
| Frontend a11y | Hundreds of `tabIndex=0` tooltip chips; a chip inside a button; crew picker lacks arrow-key handling |
| Frontend code | Duplicated tone maps and date helpers; three unused UI components and several unused exports; `next-themes` is effectively unused |
| Frontend UX | An admin lands on a "not available for your role" home; the assistant's `/sleep?astronaut=` deep link is ignored |
| Backend code | Unused helpers (`tod_bucket`, `baseline_forecasters`, `session_scope`, …); four drifting JSON sanitisers, and the emergency one does not handle NaN (PostgreSQL rejects it in JSON) |

## Verified as sound

| Area | What was checked |
| --- | --- |
| CSRF | Enforced on every cookie-authenticated write, compared in constant time |
| Sessions | 256-bit tokens stored as SHA-256 digests; revoked on role change, password change and deactivation |
| Passwords | Hashed with scrypt (N = 2¹⁵, r = 8, p = 3) in a worker thread |
| Cookies and CORS | Cookies are `HttpOnly`; a CORS wildcard is refused |
| SQL | All raw SQL is static and LIKE filters are parameterised |
| NASA key and outbound HTTP | The key is never logged or returned; outbound HTTP has timeouts, retries and a circuit breaker |
| Background work | Queues are bounded and background loops log their exceptions |
| Frontend | No `dangerouslySetInnerHTML`, no `Math.random` measurements, no secrets in `NEXT_PUBLIC_*` |
| Containers | Both run as non-root users |
| Simulation isolation | The sandbox writes only to its own tables (phase 6 tests, re-run in the final gate) |
