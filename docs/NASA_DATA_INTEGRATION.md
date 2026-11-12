# Integrating NASA datasets

**Status (phase 4, 2026-11-12):**

- **Integrated:** three public NASA sources (DONKI space weather, the OSDR Environmental Data App
  for ISS telemetry and dosimetry, and the OSDR study catalogue). They feed the space environment
  module, labelled by category and never mixed into the simulated crew data. See
  [NASA_DATA_SOURCES.md](NASA_DATA_SOURCES.md) and [SPACE_ENVIRONMENT.md](SPACE_ENVIRONMENT.md).
- **Not implemented:** this guide also covers how archival data could calibrate or replace parts of
  the simulator; those sections remain design proposals. In particular, DONKI events are **not**
  replayed into the simulator. An environmental event must never become a fabricated crew dose.

> Access to identifiable astronaut medical data is restricted. Most crew physiological datasets
> must be requested through NASA's Life Sciences Data Archive, under data-use agreements. Public
> sources are best used to **calibrate** the simulator and to **replay** environmental events,
> not to show any individual's health.

## Candidate sources

| Domain | Source | What it offers | How ASTRA-MED would use it |
| --- | --- | --- | --- |
| Space weather | NASA **DONKI** (Space Weather Database of Notifications, Knowledge, Information), via `api.nasa.gov` | Solar energetic particle (SEP) events, flares, CMEs with timestamps | Replay historical SEP events as `solar_particle_event` scenarios at their real onset times and durations |
| Interplanetary radiation | **MSL RAD** (Curiosity Radiation Assessment Detector) data in NASA's Planetary Data System (PDS) | Measured dose-rate time series in cruise and on Mars | Calibrate `simulator/radiation.py` (currently a constant 1.84 mSv/day reference plus noise) with measured variability |
| ISS radiation | ISS radiation instrument data published through NASA open-data channels | Dose rates in low Earth orbit | Alternative baseline for an ISS-scenario mission profile |
| Space biology and human research | NASA **Open Science Data Repository (OSDR)**, which combines GeneLab and the Ames Life Sciences Data Archive | Curated studies with public APIs and metadata | Literature-grade parameter ranges (for example, fluid-shift or cardiovascular deconditioning trends) to tune physiology coefficients |
| Crew physiology | NASA **Life Sciences Data Archive (LSDA)** | Restricted archives from flight and analog studies (for example actigraphy, sleep, cardiovascular measures) | Requested, de-identified data to fit personal-baseline models and validate detectors |
| Analog missions | Human Exploration Research Analog (HERA) and similar analog studies, via LSDA requests | Long-duration isolation data with schedules | Validate sleep and circadian insight rules against realistic schedules |
| Standards | **NASA-STD-3001** (Space Flight Human-System Standard) | Health and performance limits, including the 600 mSv career effective-dose limit | Source of reference lines and documented thresholds (already used for the radiation reference) |

## Integration design

### 1. A source adapter interface

Every source becomes an adapter that yields the same domain objects the simulator produces:

```python
class VitalsSource(Protocol):
    data_source: str            # e.g. "simulated", "replay:lsda-study-1234"
    async def readings(self, since: datetime) -> AsyncIterator[VitalReading]: ...

class EnvironmentSource(Protocol):
    async def events(self, start: datetime, end: datetime) -> list[ActiveScenario]: ...
```

`MonitoringService` already separates generation (`engine.step`) from detection, persistence and
broadcast, so an adapter can stand in for the engine without touching detection, storage, the API
or the frontend.

### 2. Provenance everywhere

`data_source` is already a column on every measurement table and a field on every API model.
Its type is currently `Literal["simulated"]`; integrating real data widens it to an enum such as
`simulated | replay | archival`, and the frontend's "Simulated data" marker becomes a provenance
badge driven by that field. A screen must never mix sources without labelling each series.

### 3. Example: replaying DONKI solar particle events (proposal, deliberately not implemented)

```python
# backend/app/sources/donki.py (proposed)
import httpx

DONKI_SEP = "https://ccmc.gsfc.nasa.gov/DONKI/WS/get/SEP"  # api.nasa.gov/DONKI returned 404 on 2026-11-12

async def fetch_sep_events(start: date, end: date, api_key: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(DONKI_SEP, params={"startDate": start.isoformat(),
                                                "endDate": end.isoformat(),
                                                "api_key": api_key})
        r.raise_for_status()
        return r.json()

def to_scenarios(events: list[dict]) -> list[ActiveScenario]:
    # Map each SEP event's eventTime to a crew-wide solar_particle_event scenario.
    ...
```

- The API key comes from an environment variable (`ASTRA_NASA_API_KEY`), never from code or the repo.
- Responses are cached in a `source_cache` table so demos work offline and stay within rate limits.
- Mapped events are stored in `simulation_events` with `triggered_by = "replay"`, so alerts, radiation
  charts and insights pick them up unchanged.

### 4. Calibrating the simulator

1. Extract distributions (resting heart rate, circadian amplitude, sleep duration and onset drift,
   exercise adherence) from the chosen dataset.
2. Store them as crew-profile parameters (`simulator/profiles.py` already models these per person).
3. Re-run the detector test suite. The simulator's injected scenarios give labelled ground truth, so
   precision and recall per detector can be reported before and after calibration (phase 3).

### 5. Units, time and de-identification

- Convert to the units in `schemas/health.py` (bpm, %, mmHg, °C, breaths/min, mSv) at the adapter boundary.
- Normalise timestamps to UTC.
- Replace any subject identifiers with study-scoped pseudonyms before ingestion. Never store names,
  and never display archival records as if they were a live crew member.

## AI engine datasets and licensing

The phase 3 models (see [AI_ENGINE.md](AI_ENGINE.md)) use **only synthetic data** generated by this
repository's simulator. That data is released with the code and has no external licence terms.
Every experiment records `"source": "synthetic"`, a dataset fingerprint and `"real_data": "none"`, so
a synthetic result cannot be mistaken for a real one. No external dataset was downloaded or used.

Candidate real datasets for a future validation stage, kept separate from the synthetic pipeline:

| Dataset | Content | Access and licence (check the current terms before use) | Fit for ASTRA-MED |
| --- | --- | --- | --- |
| NASA LSDA / OSDR crew and analog studies | Flight and analog physiology, sleep, actigraphy | Restricted; data-use agreement and review required | The only route to astronaut-population evidence |
| PhysioNet databases (for example MIMIC-III/IV waveform subsets, BIDMC PPG and respiration) | ICU or clinical HR, SpO₂, respiration, ECG time series | Some open (ODC-By / ODbL), some credentialed (PhysioNet Credentialed Health Data Licence) | Robustness of the detectors and forecasters to real sensor noise. Patients, not astronauts |
| PhysioNet sleep databases (for example Sleep-EDF) | Polysomnography with sleep staging | Open Data Commons licence | Validating the sleep and circadian features |
| NASA DONKI | Solar particle events | Public (api.nasa.gov key, no personal data) | Radiation context in risk scoring, not a physiology target |

Rules for adding one:

1. Add a source adapter in `app/ai/datasets/`, not in the simulator.
2. Keep its splits chronological and per subject. A subject never appears in both train and test.
3. Report its metrics in a separate table labelled with the dataset name and licence.
4. Never pool real and synthetic results into one number.

Results on clinical (non-astronaut) data still would not validate the models for astronauts.

## Checklist before showing non-simulated data

- [ ] Data-use agreement and licence terms allow this use and display.
- [ ] Provenance badge replaces the "Simulated data" marker for that series.
- [ ] Disclaimers updated: still not a medical device and not clinically validated.
- [ ] Thresholds reviewed by a qualified clinician before they are described as anything more than test values.
