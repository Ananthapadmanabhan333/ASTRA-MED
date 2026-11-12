# Space environment intelligence (phase 4)

Real NASA open data on space weather, the ISS environment and spaceflight research, explored next to
ASTRA-MED's simulated crew. The code is in `backend/app/space/` and the dashboard pages are under
**Space environment** in the navigation. Sources, licences and per-source limitations are in
[NASA_DATA_SOURCES.md](NASA_DATA_SOURCES.md). Live record counts and quality figures are in the
[generated report](reports/nasa-data-sources-report.md).

> The NASA data are real; the crew and their physiology are simulated, and the simulator takes no
> input from NASA data. Nothing here establishes a link between space weather and anyone's health.
> Correlation does not establish causation.

## Pipeline

```
NASA services ──► http.py (ResilientClient) ──► donki.py / eda.py / osdr.py ──► repository.py ──► PostgreSQL
                   retries + backoff             validate, normalise,           idempotent upserts,
                   429 / Retry-After             quality checks,                sync-run log
                   mirror failover + circuit     keep raw record
                   TTL cache, key redaction
                                    ▲
                       service.py (SpaceDataService): scheduler, per-source locks, freshness / fallback
                                    │
        intel.py (space weather, radiation A-D, alerts) · timeline.py · correlation.py · report.py
                                    │
                     api/space_routes.py ──► /api/space/* ──► Space environment pages
```

**Asynchronous clients.**
- **Request handling:** each request uses `httpx.AsyncClient`, with a per-host politeness gap
  (`ASTRA_SPACE_REQUEST_SPACING_S`).
- **Retries and failover:**
  - Timeouts, connection errors, 5xx and 429 are retried with exponential backoff and jitter;
    `Retry-After` is honoured.
  - A rate-limited endpoint is skipped in favour of the next mirror rather than waited out.
  - A structural failure (404 or 410, or a body that isn't JSON) opens a circuit breaker for that
    endpoint for 6 hours.
- **Caching:** responses are cached in memory for a per-call TTL.

**Scheduled synchronisation.** A background task runs:

| Source | Cadence | What it does |
| --- | --- | --- |
| DONKI | every 3 h | 180-day backfill on an empty store, then incremental from 3 days before the newest event |
| OSDR | daily | Five topic searches |
| EDA | weekly | Mission list, then each mission's telemetry and dosimetry, plus DONKI history for that mission's dates |

- **Logging:** every run is written to `data_sync_runs` with counts of received, new, updated,
  duplicate and invalid records, plus the endpoint used, latency and any error.
- **Manual runs:** operators can start a sync with `POST /api/space/sync`, gated like the
  simulation controls.

**Duplicate detection:**

| Source | Rule |
| --- | --- |
| DONKI | Unique on (source, external ID); a newer `versionId` or changed content updates the row |
| Notifications | Unique on message ID |
| EDA | Measurements are replaced per mission and quantity on re-ingestion, under a unique constraint; split rows are merged per timestamp |
| OSDR | Upsert on accession |

**Fallback mode.**
- **Serving:** the API always answers from the local store. Each response carries a `freshness`
  object: `live`, `cached` (sync disabled), `offline-fallback` (source unreachable; stored data with
  its retrieval time), `unavailable` (unreachable and nothing stored), or `pending`.
- **Never invented:** data is never synthesised to fill a gap.
- **Health:** a source is `healthy`, `degraded` (served after errors, or primary endpoint skipped)
  or `offline`.

## Radiation intelligence

Four categories, shown side by side and never combined:

| | Category | Content | Unit |
| --- | --- | --- | --- |
| A | Measured | EDA daily absorbed dose (GCR, SAA, total) per historical ISS mission | mGy/day |
| B | Environmental indicators | DONKI SEP, flares (R1+), radiation belt enhancements, storms (G1+), fast CMEs | none (events) |
| C | Estimate | Fictional mission days × 1.84 mSv/day (MSL RAD cruise measurement, Zeitlin et al. 2013), excluding SEPs | mSv |
| D | Simulated | Phase 2 simulator crew doses and solar particle event test scenarios | mSv/day |

- **Mission exposure timeline:** puts C and D on the mission's days and marks the days of B events.
  The markers carry no value.
- **Measured history:** shows A per ISS mission.

**Radiation-related alerts** (prototype rules on DONKI events; always indicators):

| Event | Advisory | Caution |
| --- | --- | --- |
| SEP | Model-derived detection | Instrument detection |
| Flare | R1–R2 | R3+ |
| Radiation belt enhancement | Always | — |
| Geomagnetic storm | G1–G3 | G4+ |
| CME | Speed class O | Speed class R or ER |

An alert is "active" for 24 h, "recent" up to 3 days, then "past". Every alert states that it is not
a dose and that DONKI's vantage point is near Earth.

## Mission timeline

**Two modes, because the data live on different clocks:**

- **Current mission:**
  - real DONKI events and notifications;
  - simulated crew alerts, simulation scenarios and AI anomaly detections (Phase 3);
  - hourly simulated vitals for the selected crew member.
- **Historical ISS mission:** EDA milestones and measured series, with the DONKI events from those
  dates.

**Time handling:**
- **Storage and computation:** all times are UTC.
- **Display:** the dashboard renders them in a selectable zone: UTC (mission time), Houston,
  Moscow, Cologne, Tsukuba, or the browser's own. Each instant is labelled with the offset valid at
  that instant, so daylight-saving changes are handled.

**Nearby events:** `GET /api/space/timeline/nearby` lists space-weather events within ±N hours of
any moment, such as a physiological anomaly, with exact offsets. It always states that closeness in
time is not evidence of a causal link.

## Environment-health correlation engine

The engine is exploratory. Each series is a daily UTC value:

| Series | Category | Source |
| --- | --- | --- |
| Flare count, strongest flare (log10 flux), CME count and fastest speed, storm level, SEP day, RBE day | indicator | DONKI, only on days inside successfully queried ranges |
| Daily ISS GCR, SAA and total dose; cabin temperature, RH, CO₂ | measured | EDA, measured days only |
| Mean HR, sleep HR, SpO₂, sleep duration, dose per crew member; mission day | simulated | ASTRA-MED |

**Statistics** (`app/space/correlation.py`, unit-tested on series with known properties):

- **Pearson and Spearman** on pairwise-complete days, with 95 % Fisher-z intervals.
- **Autocorrelation:** n_eff = n (1 − r₁ˣ r₁ʸ) / (1 + r₁ˣ r₁ʸ) (Bretherton et al. 1999), with p-values
  from a t-distribution on n_eff − 2 degrees of freedom. In testing, independent random walks gave
  "significant" naive correlations most of the time; with n_eff, far fewer.
- **Trend-adjusted (partial) correlation** after removing a linear time trend from both series. A
  shared trend (solar-cycle phase, mission phase) is a common confounder.
- **Time-lagged correlation** over −L…L days, with Benjamini–Hochberg q-values across the lags. The
  matrix view corrects across all pairs.
- **Rolling correlation** (window w days), and **cross-correlation** of first differences (a light
  pre-whitening).

**Warnings in every result:**
- small samples;
- strong autocorrelation;
- binary series (point-biserial);
- the number of tests run;
- uncontrolled confounders (solar-cycle phase, season, mission phase, schedule changes).

When one series is simulated, the result states that any correlation is **coincidental by
construction**. If the series barely overlap (fewer than 5 shared days), no estimate is given.

**Example results from the live store (2026-11-12):**

- **RR-1, September–October 2014:** daily strongest-flare intensity against measured ISS GCR dose:
  r = −0.29 (95 % CI −0.69 to 0.24), n = 19, p = 0.28. No evidence of an association.
- **Simulated AST-01 heart rate against CME counts (negative control):** r = −0.51 over 8 days,
  p = 0.22, flagged as coincidental. A large-looking coefficient on a tiny sample, which is the trap
  the warnings exist for.

## API

See [API.md](API.md#space-environment-phase-4). All endpoints live under `/api/space`:

| Area | Endpoints |
| --- | --- |
| Sources and sync | `sources`, `sync` |
| Space weather | `weather/summary`, `weather/events`, `weather/events/{id}`, `weather/notifications`, `alerts` |
| Radiation | `radiation` |
| ISS environment | `iss/missions`, `iss/missions/{name}` |
| OSDR catalogue | `osdr/studies` |
| Timeline | `timeline`, `timeline/nearby` |
| Correlation | `correlation/series`, `correlation/analyze`, `correlation/matrix` |

## Dashboard

`frontend/src/components/space/`:

| Page | What it shows |
| --- | --- |
| **Space weather** | Summary tiles, interactive event timeline (lanes by type, colour by NOAA level), event log with the original DONKI record, alerts, notifications, provider caveats |
| **Radiation intelligence** | Added below the existing simulated dose view: categories A–D, mission exposure timeline, measured dose by ISS mission, alerts |
| **ISS environment** | Mission picker, a "historical, not live" banner, telemetry charts (ISS vs ground) with milestones, daily dose with approximated days and DONKI event days, the quality table, linked OSDR studies |
| **NASA data explorer** | Per-source inventory: endpoints with failover state, collection period, units, availability, update frequency, quality counters, licence, citation, sync log. Also the evaluated sources and the OSDR catalogue search |
| **Mission timeline** | Lanes and series on one axis, timezone selector, nearby-events panel |
| **Environment-health** | Pair analysis with examples (including a negative control), lag, rolling and scatter charts, correlation matrix |

Every data block carries a category badge (measured, indicator, model, estimate, simulated or
metadata) and a freshness badge showing the source and retrieval time.

## Tests

`backend/tests/space/` contains 66 tests, 65 running by default:

| Area | What is tested |
| --- | --- |
| Normalisation | Real DONKI, EDA and OSDR excerpts in `tests/space/fixtures` |
| Classification | NOAA R and G boundaries, including Kp thirds |
| Timestamps | Formats and offsets |
| Data quality | Injected out-of-range, missing and duplicate values; split rows; approximate launch days |
| Failure handling | Retries, backoff, retry cap, 429 with mirror switch, 404 circuit breaker, outages, non-JSON bodies, caching, API key never leaked |
| Integration | Provenance on every record, version updates, offline fallback, empty store with NASA down, radiation category separation, UTC ordering, exact nearby offsets, correlation endpoints with NaN-free JSON |
| Access control | Operator gating, module disable |

The PostgreSQL test runs when `ASTRA_TEST_POSTGRES_URL` is set. It catches VARCHAR overflows that
SQLite ignores, which is how a real overflow was found on the first live sync.

Frontend: `src/lib/__tests__/space.test.ts` covers display-zone conversion across daylight-saving
changes and correlation period selection.

## Limitations

1. **No crew-dose link.** Crew physiology is simulated and unaffected by space weather, so
   environment-health correlations involving crew data can only show chance; they demonstrate the
   method. Real measured-to-measured analyses are limited to DONKI against EDA during historical
   ISS missions: a few weeks per mission, so samples are small.
2. **Vantage point.** DONKI is a near-Earth record. The fictional spacecraft's position is not
   modelled, so there is no event propagation to Mars transit.
3. **Research-grade sources.** DONKI is research and prototype quality (CCMC). EDA dosimetry is
   preliminary and location-specific. NOAA SWPC remains the operational authority.
4. **No SEP intensity.** DONKI has no proton flux, so SEP events are unclassified. GOES proton flux
   (NOAA) would be needed for the S-scale.
5. **Fixed prototype rules.** The alert thresholds are not operational criteria.
6. **Schema evolution.** There is no Alembic yet. A small idempotent PostgreSQL upgrade step in
   `db/session.py` covers this phase's column changes.
7. **Endpoint drift.** The DONKI endpoint moved during this phase, and the client's failover hides
   such breaks from users. The source health view and sync log make them visible.

## Next steps

- **Proton flux:** add GOES integral proton flux (NOAA SWPC JSON) to give SEP events an S-scale and
  a flux time series. Record it as a NOAA source, separate from NASA.
- **ISS detector data:** integrate RadLab detector time series once the portal is back, to get ISS
  dose rates at higher time resolution.
- **Spacecraft position:** model the spacecraft's heliocentric position (for example from a planned
  trajectory) so that events can be filtered or propagated by connectivity, instead of shown as
  Earth-observed only.
- **Multivariate analysis:** add autocorrelation-robust regression with explicit covariates
  (season, solar-cycle phase) for DONKI against ISS dose across all 11 missions with dosimetry.
- **Migrations:** add Alembic migrations.
