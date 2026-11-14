# Performance and reliability benchmarks (phase 7)

Measured on 2026-11-14 on the development laptop: Windows 11, 16 logical CPUs, Python 3.11.9 and
PostgreSQL 16 (embedded `pgserver`). The API and the load generator ran on the same machine, so these
are **relative** numbers for finding bottlenecks and checking optimisations, not capacity figures for
a production host. Raw results are in [`docs/benchmarks/`](benchmarks/).

## Summary

| Area | Before | After | Change |
| --- | --- | --- | --- |
| 7-day vitals history, p50 | 968 ms | 145 ms | 6.7× faster (SQL bucketing) |
| 7-day crew comparison (4 crew), p50 | 3,093 ms | 488 ms | 6.3× faster |
| Throughput, 20 concurrent clients | 15.6 req/s | 32.5 req/s | 2.1× |
| Latency under load, p50 / p95 | 682 / 2,953 ms | 126 / 1,713 ms | event loop no longer blocked by Python bucketing |
| 24 h anomaly detection with explanations, p50 | 710 ms | 343 ms | 2.1× faster (batched attribution), identical output |
| WebSocket fan-out, 50 clients × 30 s | 0 failures, 1.03 msg/s each | same | stable before and after |
| PDF report with a 2,000-character word | 4.4 s on the event loop | 0.012 s for 20,000 characters, in a worker thread | linear-time line breaking, identical output |

Every optimisation was checked for identical results: output fingerprints, bucket-by-bucket
comparisons and the PDF layout test.

## 1. API latency on a large history (PostgreSQL)

**Setup.**

- **Database:** a dedicated `astra_med_bench` database holding about **2.0 million** `vital_samples`
  rows: 29 days × 4 crew at the live store's 5-second cadence. These are synthetic load-test rows
  (`scripts/bench_api.py seed`), not crew data.
- **API:** started with `.claude/launch.json` → `backend-bench` (simulator running, NASA sync off).
- **Load:** `scripts/bench_api.py run` signs in with a temporary benchmark account and makes 15
  sequential requests per endpoint after one warm-up.
- **Measurement:** latencies are client-side, through HTTP on localhost.

| Endpoint | Before p50 (ms) | Before p95 | After p50 | After p95 |
| --- | --- | --- | --- | --- |
| system health (`/api/system/health`) | 6 | 6 | 6 | 9 |
| crew list (`/api/astronauts`) | 8 | 9 | 10 | 10 |
| live snapshot (`/api/health/AST-01`) | 11 | 13 | 11 | 14 |
| history 1 h | 17 | 21 | 16 | 18 |
| history 24 h | 101 | 288 | 31 | 32 |
| **history 7 d** | **968** | **1,162** | **145** | **160** |
| **crew comparison 7 d** | **3,093** | **3,318** | **488** | **525** |
| mission control overview | 81 | 374 | 37 | 48 |
| crew monitoring | 22 | 157 | 24 | 26 |
| alert centre | 12 | 12 | 11 | 13 |
| event history (7 d) | 10 | 12 | 11 | 13 |
| situational timeline 24 h | 13 | 15 | 13 | 17 |
| analytics (30 d) | 21 | 25 | 22 | 24 |
| stored NASA space weather (30 d) | 12 | 14 | 12 | 13 |
| AI risk assessment (30 s cache) | 8 | 9 | 8 | 8 |

**Bottleneck found.**

- History and comparison loaded every raw sample, about 123,000 rows per crew member for 7 days, and
  averaged them in a Python loop on the event loop.
- The PostgreSQL plan for the raw query uses the `ix_vitals_astronaut_ts` index (bitmap index scan,
  76 ms). It then sorts 123,000 rows with an external merge on disk, and the Python loop added about
  0.9 s on top.

**Fix.**

- `vitals_repo.bucket_means` groups the samples into the same buckets inside the database:
  `floor((epoch(ts) − start) / resolution)` on PostgreSQL, the julianday equivalent on SQLite.
  Only one row per bucket leaves the database.
- The history route, the comparison route and the space timeline use it.

**Equivalence.**

- On the 2-million-row PostgreSQL database, every bucket's timestamp and count matched the Python
  implementation, and the means differed by at most 2.7 × 10⁻¹³.
- On SQLite the same is checked by `tests/phase7/test_hardening.py::test_sql_buckets_match_python_bucketing`.

## 2. Concurrent load

20 concurrent clients made 15 requests each, rotating through the overview, crew monitoring,
alert centre, 24 h history and event history.

| | Requests | Errors | Wall time | Throughput | p50 | p95 | max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Before | 300 | 0 | 19.2 s | 15.6 req/s | 682 ms | 2,953 ms | 7,437 ms |
| After | 300 | 0 | 9.2 s | 32.5 req/s | 126 ms | 1,713 ms | 5,906 ms |

The remaining p95 tail comes from the overview and crew-monitoring aggregations competing with the
1 Hz simulator tick and the orchestrator's AI sweep in a single process. It is acceptable for a
mission-control room with a handful of users. It is not a capacity figure for a public deployment,
which runs exactly one API instance (see [DEPLOYMENT.md](DEPLOYMENT.md)).

## 3. WebSocket stability

50 simultaneous authenticated clients stayed on `/ws/health-monitoring` for 30 seconds, before and
after the changes:

- **Connections:** 0 failed and 0 closed early.
- **Delivery:** each client received 31 messages, about 1.03 per second, matching the 1 Hz tick.
- **Spacing:** the 95th-percentile gap between messages was 1.02–1.03 s.

The hub sends to every client in parallel with a 2 s per-client timeout, so a slow client is
dropped instead of delaying the others. The reconnection behaviour of the browser client (backoff
and refetch on reconnect) is covered by the frontend tests and phase 6 browser checks.

## 4. AI inference

**Setup.**

- `scripts/bench_ai.py` runs the real app in-process on a temporary SQLite database with 3 days of
  backfilled simulated history.
- The clock is frozen, so inputs and outputs are reproducible.
- The AI cache is off and the model version is pinned (`v20261112-164739-9c1cd54f`).
- Before and after ran **interleaved** (before, after, before, after) so machine-state drift
  affects both equally.

| Operation (12 requests each) | Before p50 (ms), runs 1 and 2 | After p50 | Before p95 | After p95 |
| --- | --- | --- | --- | --- |
| **24 h anomaly detection with explanations** | **715, 705** | **335, 351** | 830, 742 | 389, 374 |
| XGBoost forecast (4 signals × 48 steps, SHAP drivers) | 124, 123 | 123, 126 | 134, 141 | 133, 138 |
| LSTM forecast | 61, 59 | 59, 59 | 70, 67 | 70, 69 |
| Risk assessment | 244, 235 | 239, 244 | 249, 250 | 258, 260 |
| Crew overview (4 risk assessments) | 977, 947 | 995, 977 | 1,213, 1,200 | 1,229, 1,190 |

**What changed.**

- **Batched attribution.** Explanations use occlusion attribution, which needs (d + 1) model
  evaluations per explained window and detector. They used to run one window at a time, so
  `IsolationForest`, `LOF`, the SVM and the autoencoder each paid their per-call overhead once per
  window. Now every flagged window in the range is attributed in **one call per detector** and
  reused by the timeline and the detection summaries. Profiling had shown attribution at about 70 %
  of detection time.
- **Lazy loading.** The neural comparison forecasters (LSTM, GRU, TCN) now load on first use; the
  serving forecaster and the detectors load at start. A bug was found and fixed on the way:
  `Mapping`'s default `in` operator called `__getitem__` and loaded the model.
- **Memory.** Model memory after loading was 31–40 MB in all four runs, with no reliable difference
  between before and after, so no memory saving is claimed.
- **Monitoring.** `GET /api/ai/status` now reports `inference.operations` (count, errors, last error,
  p50/p95/max over the last 200 calls per operation) and the process memory. Library versions are
  recorded at training and compared at load (`library_mismatch`). `ASTRA_AI_MODEL_VERSION` pins a
  version.

**Results are unchanged.**

- The fingerprints of the detection timeline, the explanations, the XGBoost forecast and the risk
  assessment are identical in all four runs.
- The LSTM forecast is bit-identical (max |difference| 0.0) once the hash-dependent tie-break
  described in [SCIENTIFIC_VALIDATION.md](SCIENTIFIC_VALIDATION.md#31-reproducibility) was fixed.
  That bug was found by this benchmark.

**Measurement note.** Absolute timings drifted by up to 1.5× over the afternoon on this laptop
(thermal and power state). An earlier pair of runs gave 524 → 236 ms for detection. Only ratios from
interleaved runs are reported as results.

## 5. External NASA API failures

Covered by automated tests (phase 4), unchanged in phase 7:

- **Retries:** timeouts and HTTP 429/5xx are retried with exponential backoff.
- **Fallback:** a 404 from the api.nasa.gov DONKI proxy opens a 6-hour circuit breaker, and
  requests go to the CCMC origin. This happens live today, because the proxy still returns 404.
- **Offline behaviour:** when NASA is unreachable, stored data keep being served, with the age of
  the last successful sync shown.
- **Collector health:** the orchestrator's space-scan collector backs off and reports its health on
  `/api/system/status`.

During the final demonstration, a live DONKI synchronisation through the CCMC service succeeded
(HTTP 200).

## 6. What was implemented for performance and reliability

| Item | Status |
| --- | --- |
| Caching | AI results cached per crew member (`ASTRA_AI_CACHE_SECONDS`, default 30 s); NASA responses cached by the resilient client |
| Pagination / limits | List endpoints cap `limit`; history is downsampled to at most `max_points` buckets |
| Efficient queries | SQL time-bucket aggregation (new); composite index on `(astronaut_id, ts)` verified in the plan |
| Background processing | Model work in worker threads; PDF rendering moved off the event loop (new); periodic retention task (new) |
| Retry mechanisms | NASA clients (retries, backoff, circuit breaker); database wait-and-retry at start-up |
| Health checks | `/livez`, `/readyz` (new), `/api/system/health`, `/api/system/status` (deep, signed in) |
| Structured logging | Request ID per request, `astra.*` loggers, bound SQL parameters never logged (new: `hide_parameters`) |

## Reproduce

```bash
cd backend
python scripts/bench_ai.py --label after --out ../docs/benchmarks/ai-after.json
# start the "backend-bench" launch configuration, then:
python scripts/bench_api.py seed --db-url postgresql+asyncpg://postgres@127.0.0.1:PORT/astra_med_bench --days 7
python scripts/bench_api.py seed --db-url ... --days 22 --end-offset-days 7
python scripts/bench_api.py run --db-url ... --label after --out ../docs/benchmarks/api-after.json
```
