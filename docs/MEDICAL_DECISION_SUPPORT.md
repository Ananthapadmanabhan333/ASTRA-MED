# Digital twin and medical decision support (phase 5)

Phase 5 adds an astronaut digital health twin, multisystem health intelligence, explainable decision
support for alerts, an emergency scenario simulator, structured incident reports with PDF export, a
source-grounded medical data assistant, a mission health overview, and authentication with
role-based access and an audit log ([SECURITY.md](SECURITY.md)).

> **Scope and honesty.** All crew data is simulated and crew members are fictional. Nothing here is
> clinically validated, and no output is a diagnosis or a treatment recommendation. The twin is a
> structured record of simulated measurements, statistics, events and context. It is not a
> physiological model and does not reproduce the complete biological state of a person. Every
> statistical band and alert limit is a software setting for a prototype, not a clinical threshold.
> The review workflow lists process steps only; a real deployment must replace it with the
> mission's approved medical procedures.

## Architecture

```
                 ┌──────────────── existing (phases 1-4, unchanged) ─────────────────┐
 simulator ──► MonitoringService ──► alerts, vitals, sleep, dose (PostgreSQL)        │
                     │                       │                                         │
                     │                AIService (baselines, anomaly ensemble,          │
                     │                forecasts, risk rules, alert explanations)       │
                     │                SpaceDataService (DONKI, EDA, OSDR)              │
                 └───┼───────────────────────┼────────────────────────────────────────┘
                     ▼                       ▼
 TwinService ──► twin_daily (one row per crew member per mission day)
       │
       ▼
 MultisystemEngine (6 systems, cross-system patterns) ◄── EmergencyService overlays
       │                       │
       ▼                       ▼
 decision.packet (8 parts) ──► ReportService ──► incident_reports ──► PDF (app/reports/pdf.py)
       │
 AssistantService (TF-IDF retrieval + data tools + safety layer, optional Claude)
 overview route (aggregates all of the above)
 security: AuthService, AuditLog, require(permission) on every router
```

New backend packages: `app/twin`, `app/medical`, `app/emergency`, `app/reports`, `app/assistant`,
`app/security`. New routers: `twin_routes`, `medical_routes`, `emergency_routes`, `report_routes`,
`assistant_routes`, `overview_routes`, `auth_routes`. Phase 1–4 modules were extended only where
noted below.

### Changes to earlier phases

| Where | Change | Why |
| --- | --- | --- |
| `simulator/scenarios.py` | Two operator-only scenarios: `sleep_disruption`, `habitat_atmosphere` (never picked at random, so the historical scenario generator is unchanged) | Emergency simulator |
| `simulator/habitat.py` (new) | Simulated cabin CO₂, temperature and humidity | Environmental-anomaly scenario |
| `services/monitoring.py` | `start_scenario_group()` starts several scenarios on one target atomically | Composite "multiple deviations" runs |
| `ai/service.py` | Alert explanations no longer crash on rhythm and baseline alerts (they formatted a `None` threshold) | Bug found while testing decision support |
| `main.py` | Unhandled errors are answered inside the CORS middleware | Browsers saw a 500 as "API unreachable" |
| `core/logging.py` | `httpx` request lines are no longer logged at INFO | They contained the NASA `api_key` query parameter |
| `api/*` | Every router requires a permission | Authentication and RBAC |

## Module 1: digital health twin (`app/twin`)

- **Store:** `twin_daily` holds one row per crew member per mission day: per-signal statistics
  (mean, SD, percentiles, awake-at-rest mean, sleep mean), activity minutes, sleep, simulated dose,
  alerts and test scenarios that day, and coverage (samples, interval, completeness).
- **Basis:** a day is `stored` when at least 80 % of its hours have stored samples. Older days,
  whose samples the 30-day retention pruned, are recomputed by the same deterministic simulator and
  seed and labelled `regenerated`. Alerts are not available for regenerated days.
- **Updates:** a background task builds missing days at start-up (about 14 s for 4 × 146 days on
  SQLite), then refreshes yesterday and today every 5 minutes. The "current state" comes from the
  live monitoring stream.
- **Views:**
  - profile with current state;
  - baseline against current: configured simulator value, early mission (days 0–14), last 7 days,
    last 24 hours and the Phase 3 learned baseline, each labelled with its category;
  - daily timeline with real NASA DONKI events for the same date;
  - longitudinal trends: 7-day rolling mean, and an OLS slope per 30 days with a CI whose degrees
    of freedom are reduced for lag-1 autocorrelation;
  - mission-stage comparison with Welch CIs.
- **Stages:** the fictional mission timeline (`twin/stages.py`): launch and early adaptation
  (days 0–14), early, mid and late transit, arrival from day 240.
- **Data categories** (`twin/categories.py`), shown on every value: `simulated`, `regenerated`,
  `derived`, `estimate`, `model`, `configured`, `measured` (NASA), `indicator` (NASA).

The simulator does not model long-term adaptation to spaceflight, so stage differences and trends of
vital signs are expected to be flat. The API says so in `notes`.

## Module 2: multisystem health intelligence (`app/medical/multisystem.py`)

Six systems, each assessed from listed inputs:

| System | Inputs |
| --- | --- |
| Cardiovascular | Heart rate, systolic and diastolic pressure (5-minute mean vs the Phase 3 personal baseline for the current activity), rhythm classification, HRV against its 24-hour mean |
| Respiratory | SpO₂, respiratory rate; simulated cabin CO₂ while an environmental run is active |
| Thermoregulation | Body temperature; simulated cabin temperature while an environmental run is active |
| Sleep and circadian | Last night's duration and efficiency vs the previous 14 nights, 7-night sleep debt (context), awake during the scheduled sleep window |
| Activity and recovery | Yesterday's exercise vs the plan, sleeping heart rate vs the previous 14 days, current MET (context) |
| Radiation exposure indicators | Simulated daily dose vs the previous 30 complete days, simulated SPE days, habitat dose-rate multiplier, real NASA DONKI events in 72 h (context only) |

- **Status bands** (`multisystem_config.json`): deviation at |z| ≥ 2, marked deviation at |z| ≥ 3,
  relative to the crew member's own reference. These are statistical bands, not clinical thresholds.
- **Context-only inputs:** informational inputs and real NASA indicators are shown but never change a
  crew member's status.
- **Explanations:** built only from the inputs listed (a test checks that every number in an
  explanation belongs to an input).
- **Model outputs:** the Phase 3 risk warnings whose signals belong to a system are attached to it.
- **Cross-system patterns:** configured co-deviations (for example cardiovascular + respiratory, or
  sleep shortfall + cardiovascular). Each is labelled "co-occurrence, not a cause".

## Module 3: explainable decision support (`app/medical/decision.py`)

Every caution or critical alert has an eight-part packet: observation, measurements (one-minute
means around the alert, with the prototype limit and a note that it is not a clinical criterion),
baseline comparison (Phase 3 contributors), environmental context (activity, mission stage, simulated
test scenario, simulated habitat, NASA DONKI events within 24 h), AI output (rule, pattern kind,
anomaly ensemble), confidence and uncertainty (what confidence means, sources of uncertainty), data
quality (samples, completeness, gaps), and the recommended medical review workflow.

The workflow (`review_workflow.json`) has three escalation levels (critical → immediate review by the
flight surgeon on duty; caution → prompt flight-surgeon review; advisory → routine review) and
process steps such as "check whether a simulated test scenario explains the alert". Cross-system
patterns or marked deviations in two systems raise the level to immediate. The file contains no
diagnoses, treatments, medications or thresholds; a test enforces that.

## Module 4: emergency scenario simulator (`app/emergency`)

| Scenario | Simulator components |
| --- | --- |
| Heart-rate elevation | tachycardia |
| Oxygen desaturation | desaturation |
| Abnormal respiration | abnormal respiratory rate |
| Prolonged sleep disruption | sleep disruption + a what-if overlay that shortens the last 1–7 nights (stored sleep is unchanged) |
| Multiple simultaneous deviations | tachycardia ×0.6 + desaturation ×0.7 + elevated temperature ×0.8 |
| Simulated radiation event | solar particle event (whole crew) |
| Environmental system anomaly | habitat atmosphere (whole crew): cabin CO₂ and temperature rise, modest breathing and heart-rate rise |

- **Configuration:** severity mild / moderate / severe (intensity ×0.6 / ×1.0 / ×1.4) and duration
  30 s – 60 min. One run per target at a time.
- **Analysis:** "Run AI analysis" stores a snapshot on the run: anomaly ensemble over the run window,
  Phase 3 risk rules, the six systems, patterns, alerts and escalation.
- **Timeline:** vitals, scenario start and end, alerts opened, acknowledged and resolved, analyses,
  and the simulated environment (cabin CO₂ or habitat dose rate).
- **Labelling:** every run is labelled "SIMULATED TEST SCENARIO".

Alerts keep their phase 2 semantics: while an alert for the same rule is still open, a new breach
updates it (peak value) instead of opening another.

## Module 5: structured incident reports (`app/reports`)

A report freezes the decision-support packet for an alert (or the measurements around an emergency
run or a time) into `content`, with a SHA-256 digest that is re-checked on every read
(`integrity: intact | modified`). The ten sections are:

1. mission information
2. astronaut
3. timestamp
4. measurements
5. baseline comparison
6. environmental conditions
7. anomaly-detection results
8. model explanation
9. data-quality limitations
10. review status

Review status moves through draft → pending review → under review → reviewed → closed, with a
history of who changed it and why. Only `reports:review` (the flight surgeon) can sign off, and
"reviewed" requires a note.

PDF export uses a small dependency-free PDF 1.4 writer (`reports/pdf.py`: Helvetica, wrapping,
tables, page breaks, a "SIMULATED DATA" footer on every page). Tests check the xref table, object
offsets, page count and that all ten section headings and the simulated label are in the text.

## Module 6: AI medical assistant (`app/assistant`)

- **Retrieval:** TF-IDF (scikit-learn, light stemming, bigrams) over:
  - ASTRA-MED documentation (`docs/*.md`), chunked by heading;
  - NASA DONKI notification texts and OSDR study metadata already ingested in phase 4;
  - approved reference documents in `backend/knowledge/` (none ship with the repository; see below).
- **Data tools:** latest reading, multisystem assessment, twin comparisons and trends, sleep records,
  alerts with their decision packet, incident reports (only with `reports:read`), simulated dose,
  the DONKI summary, emergency runs and the prototype alert limits.
- **Answers:** every statement cites a data record (`D#`) or a passage (`S#`, quoted verbatim) and
  says what kind of source it is: simulated record, derived statistic, experimental model output,
  real NASA data, documentation or configuration.
- **Missing information:** the assistant says when no approved medical reference is installed, when
  no crew member is named, when no passage matches, or when ASTRA-MED cannot know something (it has
  no symptom reports).
- **Safety:**
  - diagnosis and treatment questions are declined, and the data is still shown;
  - described emergencies, unresolved critical alerts and concurrent or marked deviations produce an
    escalation notice to the flight surgeon.
- **Incident reports:** asking for one proposes an action button; asking never creates anything.
- **Storage and audit:** questions are not stored. The audit log keeps a SHA-256 prefix, the tasks
  and the crew IDs.
- **Optional Claude mode** (`ASTRA_ASSISTANT_MODE=claude`, `ANTHROPIC_API_KEY` in the backend
  environment, `pip install anthropic`):
  - sends the same records and passages as citation-enabled documents to `claude-opus-5-5` and keeps
    the citations;
  - falls back to the offline answer on any error or refusal;
  - it sends simulated crew data to an external service, so it is off by default.
  - It was tested with a stub client only (no API key in this environment).

**Reference library.** No NASA Human Research Program documents or aerospace-medicine literature are
included: downloading them needs the project owner's approval, and the assistant must never cite
something it does not have. To add one, follow `backend/knowledge/README.md`.

## Module 7: mission health overview (`/api/overview`)

Covers the whole crew or one crew member, over 24 h, 7 d or 30 d:

- crew cards: status, Phase 3 risk, six system statuses, patterns, open alerts, alerts in the period,
  resting heart rate, sleep and simulated dose;
- alert history per day;
- resting heart rate and sleep trends;
- active alerts, incident reports (if the role may read them) and emergency runs;
- the NASA DONKI context;
- a rule-generated mission summary in which every sentence restates values on the page.

## Frontend

The new "Medical decision support" navigation group holds these pages:

- **Mission health overview** (`/overview`)
- **Digital twin** (`/twin`)
- **Medical intelligence** (`/medical`, with the decision packet)
- **AI medical assistant** (`/assistant`)
- **Emergency simulator** (`/emergency`)
- **Incident reports** (`/reports`)
- **Users & audit log** (`/admin`), under Administration

Supporting changes:

- **Deep links:** URL parameters (`?astronaut=`, `?alert=`, `?report=`, `?run=`) make the assistant's
  source links open the right view.
- **Labels:** every value carries a kind chip.
- **Permissions:** navigation shows only what the role can use. A page the role cannot use shows a
  notice instead of failing.
- **Layout:** the pages follow the existing design system and keep a 375 px width without page-level
  horizontal scrolling.

## Known limitations

- No clinical validation; all statistics are relative to simulated data.
- The review workflow is a placeholder for real medical operations procedures.
- The reference library is empty, so the assistant cannot cite aerospace-medicine literature.
- Retrieval is lexical (TF-IDF). On the 8-question test set the expected section is in the top three
  for 7 questions; the forecasting-intervals question misses.
- Claude mode is untested against the live API.
- Twin days older than the 30-day retention are regenerated by the simulator, not stored.
- Vital-sign trends are flat by construction, because the simulator has no long-term adaptation.
- The sleep what-if overlay applies only while its run is active.
- The habitat atmosphere is simulated; ASTRA-MED has no life-support telemetry.
- The PDF writer is minimal (standard fonts, cp1252 text; other characters are transliterated). Its
  visual layout was not inspected in a PDF viewer here; structure and text are verified by tests.
- No per-crew-member (row-level) access restriction; see [SECURITY.md](SECURITY.md).
