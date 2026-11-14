# NASA Space Apps Challenge 2026: submission package

Everything here was prepared from the official pages, read on **2026-11-14**:

- the [challenge statement](https://www.spaceappschallenge.org/2026/challenges/health-monitoring-software/);
- the [Participant FAQs](https://www.spaceappschallenge.org/resources/participant-faqs/);
- the [Project Submission Guide](https://www.spaceappschallenge.org/resources/project-submission-guide/);
- the [Judging & Awards Guide](https://www.spaceappschallenge.org/resources/judging-awards-guide/);
- the [Participant Terms](https://www.spaceappschallenge.org/legal/).

Re-check them before submitting; they can change during the event.

## 0. Read first: items only the team can resolve

1. **Pre-event work.** The FAQ says: "Teams are not allowed to begin working on the challenges
   prior to the hackathon." The hackathon runs on **14–15 November 2026**. This repository's first
   commit is dated **11 November 2026**, and `docs/DEVELOPMENT_PLAN.md` records phases 1–2 as
   finished on 9 November. Ask your Local Lead, or the Global Organizing team via the
   [contact page](https://www.spaceappschallenge.org/contact-us/) or Space Apps Connect, whether and
   how this project can be submitted, before you submit. Do not alter the git history or the dates.
2. **Use of AI ("Super Intelligence", SI, in the 2026 rules).**
   - SI tools are allowed and must be described in the submission.
   - SI-generated code and data must be acknowledged "in descriptive text and metadata".
   - SI must not be used to "come up with your idea of how to solve the challenge".
   - Images and videos must carry a visible SI watermark.

   This codebase and its documents were written with an AI coding assistant (Claude); the commits
   carry `Co-Authored-By: Claude` trailers. A factual draft disclosure is in section 2. Edit it so it
   accurately describes what your team did.
3. **Original-work checkbox.** Submitting requires confirming that "the submitted project represents
   my team's original work" and that all external resources are listed. Decide as a team whether you
   can confirm that, given items 1 and 2.
4. **Licence.** The terms require original content to be open-source licensed (OSI). If none is
   given, NASA distributes it under Apache-2.0. The repository includes an Apache-2.0 [LICENSE](../../LICENSE)
   file in the root directory.
5. **Challenge fit.** The challenge asks for a tool that helps astronauts *assess their own health*
   and gives guidance. ASTRA-MED is built for mission control and flight surgeons. See section 3 for
   the gap analysis.
6. **Team details.** Team name, members and contributions are unknown to this repository. Fill in
   section 2.J; nothing there may be invented.

## 1. Verified requirements

| Item | Requirement (2026) |
| --- | --- |
| Event | 14–15 November 2026, at a Local Event or the virtual Universal Event |
| Submission window | Opens Saturday 14 Nov, 09:00 local time of your Local Event; **closes Sunday 15 Nov, 23:59** local time (Universal Event: the Team Owner's local time). Late saves are not judged |
| Where | The team's Project page on spaceappschallenge.org → Edit → **Submit for Judging** |
| Team | Local Event: at least 1 member; Universal Event: at least 2; at most 6. All members registered for the same event, not waitlisted, listed on the Members tab |
| Language | English on the page and in linked materials (a video may be in another language with English subtitles) |
| Project demo | **Either a video of 30 seconds or less, or a slide deck of at most 7 slides** (including title and intro slides). Longer or larger demos are not eligible for global judging. Host externally with a public link (no login) |
| Required fields | Project name; high-level summary; demo link; final project link (public, no login); detailed description; use of SI; NASA data; Space Agency Partner data and other references |
| NASA data | At least one NASA data source or resource is required for a Global Award |
| References | List **all** data, code, text and images used, including open-source ones |
| Uploads | The page accepts JPG, PNG and GIF up to 10 MB; videos and documents must be links |
| Judging criteria | Impact, Creativity, Validity, Relevance, Presentation (each scored 1–5). Presentation uses the demo plus the full project |
| Timeline | Global Nominees 3 Dec 2026; Global Finalists 17 Dec 2026; Global Winners 26 Jan 2027 |
| Minors | No images, video, audio or likeness of anyone under 18 |
| Website access | Optional: request a FortiGuard web-filter classification for a new project website, so judges can open it |

## 2. Draft submission text

### A. Project name

**ASTRA-MED**: personal, explainable health monitoring for long-duration crews.

### B. Problem statement

Far from Earth, astronauts will have to spot health changes themselves, with delayed or no help from
the ground. A single number such as a heart rate of 104 bpm means different things for different
people, during exercise or at rest, and after a radiation event. Fixed alarm limits either ring
constantly or miss slow deterioration. Opaque AI cannot be trusted by a crew that must act on it
alone.

### C. High-level summary (for the "High-Level Project Summary" field)

ASTRA-MED is an open-source health-monitoring prototype for crews on long missions. It:

- learns each crew member's own normal ranges for every activity and time of day;
- flags unusual patterns with an ensemble of five detectors;
- forecasts vital signs up to 24 hours ahead with honest uncertainty ranges;
- explains every alert with the measurements, the personal baseline and the signals that drove it;
- gives each crew member a self-check: a body-systems map, glucose, mood and symptom check-ins, daily
  check prompts and plain-language guidance on when to involve the flight surgeon.

It places each alert in its space-environment context using real NASA DONKI space-weather records
and ISS environment data from NASA's OSDR. A digital record ("twin") of each crew member, a cited
assistant and incident reports turn an alert into evidence a crew member or flight surgeon can
check. All crew data in the prototype are simulated. It is decision support, not a diagnosis.

### D. Detailed description

**What it does**

- **Monitoring:** monitors heart rate, SpO₂, blood pressure, temperature, respiratory rate, ECG
  rhythm, sleep, activity and radiation dose (all simulated).
- **Personal baselines:** compares each value with the person's own baseline instead of a
  population norm.
- **Alerts and context:** raises explainable alerts and links them to NASA space-weather events within
  ±48 hours.
- **Forecasts:** forecasts the next 24 hours with 90 % prediction intervals.
- **Workflow:** keeps a reviewed, audited workflow from alert to incident report.
- **Sandbox:** includes a sandbox that simulates whole missions at up to 120× speed, kept fully
  separate from live data.

**How it works**

- **Stack:** a Python FastAPI backend with PostgreSQL and a Next.js dashboard, connected over REST
  and WebSocket.
- **Models:** scikit-learn and PyTorch anomaly detectors calibrated to a 1 % false-alarm rate,
  XGBoost forecasting with split-conformal intervals, and transparent rule-based risk scoring.
- **NASA data:** NASA clients retry, fall back between endpoints and record the provenance of every
  record.
- **Labelling:** every value is labelled as measured, indicator, estimate, model output or simulated,
  and categories are never mixed.

**Results (simulated data, three independent datasets)**

- **Detection:** learned detectors reached F1 0.62–0.81, against 0.36 for fixed alarm limits, at a
  similar false-positive rate.
- **Forecasting:** heart-rate forecast error at 1 hour was 2.2 bpm, against 3.9 bpm for a personal
  baseline.
- **Intervals:** prediction intervals covered 89–91 % of outcomes, against 90 % nominal.
- **Negative results:** the ensemble was not reliably better than its best detector, and neural
  networks did not beat gradient-boosted trees.
- **Scope:** none of this is clinical validation.

**Tools:** Python 3.11, FastAPI, SQLAlchemy, Alembic, PostgreSQL, scikit-learn, XGBoost, PyTorch,
Next.js 16, React 19, TanStack Query, Recharts, Tailwind CSS.

**What we hope to achieve:** a credible open baseline for crew-side health monitoring that others
can validate on real analogue-mission data.

### E. Technical architecture

The diagrams are in [RESEARCH_PAPER.md §6–9](../RESEARCH_PAPER.md#6-proposed-architecture) and
[ARCHITECTURE.md](../ARCHITECTURE.md). In short:

- the simulator feeds a monitoring engine;
- the AI service provides baselines, the anomaly ensemble, forecasts, risk and explanations;
- the space-environment service handles DONKI, EDA and OSDR;
- an orchestrator combines events, alerts and correlation;
- the twin, decision support, assistant and reports build on these;
- the dashboard connects over REST and WebSocket.

### F. NASA data (for the "NASA Data" field)

- **DONKI**, NASA Community Coordinated Modeling Center
  (https://ccmc.gsfc.nasa.gov/tools/DONKI/). Solar flares, CMEs, solar energetic particle events,
  geomagnetic storms, radiation-belt enhancements and notifications, synchronised continuously. Used
  as environmental context around crew alerts, on the mission timeline and in correlation analysis.
- **OSDR Environmental Data App**, NASA Open Science Data Repository
  (https://visualization.osdr.nasa.gov/eda/). ISS cabin temperature, humidity, CO₂ and measured
  absorbed dose from 17 missions, 2014–2024.
- **OSDR study catalogue** (https://osdr.nasa.gov/bio/repo/). Space-biology study metadata used as
  research context.
- **NASA Human Research Program**, "5 Hazards of Human Spaceflight" and "Risks of Human Spaceflight"
  (https://www.nasa.gov/hrp/hazards/, https://www.nasa.gov/hrp/risks/). Used to choose the
  monitored indicators and frame the problem.
- **MSL Radiation Assessment Detector** cruise dose rate (Zeitlin et al., Science 2013), used as a
  cited Mars-cruise estimate.

### G. Space Agency Partner data and other references

- **CSA:** "Monitoring radiation for astronaut health" (2026-02-26),
  https://www.asc-csa.gc.ca/eng/news/articles/2026/2026-02-26-monitoring-radiation-astronaut-health.asp,
  as background on radiation monitoring.
- **NOAA:** Space Weather Scales (https://www.swpc.noaa.gov/noaa-scales-explanation) for flare and
  storm severity.
- **Scientific references:** the 35 references in [RESEARCH_PAPER.md §19](../RESEARCH_PAPER.md#19-references).
- **Software:** every direct dependency and its licence in [THIRD_PARTY.md](../THIRD_PARTY.md);
  fonts Barlow Semi Condensed and IBM Plex Sans (SIL OFL); Lucide icons (ISC).
- **Images:** no third-party images are used in the application.

### H. Use of Super Intelligence (draft; the team must make it accurate)

> We used an AI coding assistant (Anthropic's Claude, through Claude Code) extensively during
> development. It wrote most of the source code, tests and documentation from our specifications,
> and helped with debugging, performance analysis and preparing this submission text. Commits it
> co-wrote carry a `Co-Authored-By: Claude` trailer in the git history. [Team: describe here who
> conceived the idea and the requirements, and what you reviewed, changed and verified yourselves.]
> The application's medical-data assistant uses an offline TF-IDF retrieval method by default; an
> optional mode can call a Claude model and is off by default. The anomaly detection and forecasting
> models are conventional machine-learning models trained on simulated data, and their evaluation
> is documented in the repository. No AI-generated images, video or audio are used.

### I. Impact and practical applications

- **Long missions:** crew-side health awareness when real-time contact with flight surgeons is
  delayed or lost.
- **Analogue research:** reproducible, open tooling for analogue missions and isolation studies,
  where the same monitoring and validation questions arise.
- **On Earth:** remote and isolated settings such as polar stations, ships and rural clinics, where
  personal baselines and explainable alerts help non-specialists judge when to escalate.
- **Method:** a worked example of separating simulated, measured and modelled data, and of reporting
  negative results.

### J. Limitations and future scope

**Limitations**

- Crew data are simulated; there is no real-data or clinical validation.
- Glucose, mood and symptoms are entered by hand; there is no device or camera input yet.
- Self-check guidance is process guidance only, with no treatment advice.
- DONKI is observed from near Earth.

**Next steps**

- Validation on analogue-mission data.
- A crew self-assessment mode with prompted measurements and plain-language guidance tied to
  approved procedures.
- Geometry-aware radiation context.
- Clinician-calibrated thresholds.

### K. Team contribution summary (to be completed by the team)

| Member | Role | Contributions |
| --- | --- | --- |
| *name* | *e.g. product and requirements* | *…* |
| *name* | *…* | *…* |

## 3. Challenge fit: gap analysis

What the challenge statement asks for, against what ASTRA-MED provides today:

| Challenge asks for | ASTRA-MED today | Gap |
| --- | --- | --- |
| A visual tool that helps **astronauts assess their own health** | **Crew self-check** (`/self-check`, added after phase 7): body-systems map, plain-language status per indicator, today's checks, when to involve the flight surgeon; plus the mission-control views | Covered (first version) |
| Guidance on treatments and health improvements | Process-only review workflow; the assistant deliberately declines diagnosis and treatment questions | **Partly, by design:** guidance must come from approved procedures, which the prototype does not have |
| Indicators such as blood pressure, heart rate, **blood sugar**, body temperature, sleep hours, **mood** | BP, HR, temperature, sleep, SpO₂, respiratory rate, ECG rhythm, HRV, activity, dose (simulated); **glucose and mood entered in the self-check** | Covered |
| Input by keyboard, mouse or camera | Self-check form (glucose, mood, symptoms, note); typed sandbox telemetry; no camera input | Mostly covered |
| Use NASA HRP resources to choose indicators and understand hazards | Hazards framing; radiation categories; DONKI and EDA data | Covered |
| When a result warrants crew or flight-surgeon attention | Severity, priority, escalation levels, explanations | Covered |
| Optional: prompts to take measurements, gamification, dynamic charts, colour coding, a clickable human figure, simple instructions | Daily check prompts (done, due, overdue); clickable body-systems map; dynamic charts; colour coding always with text; plain-language guidance | Gamification absent |

Frame it for judges as **"crew-side self-check and ground-side decision support built on personal
baselines"**. Open the demo with the Crew self-check page: it answers the challenge statement most
directly.

## 4. Demo and presentation

- **Required demo:** 7 slides or 30 seconds. See [PRESENTATION.md](PRESENTATION.md) (7-slide demo
  deck) and [VIDEO_STORYBOARD.md](VIDEO_STORYBOARD.md) (30-second video).
- **Live or recorded walkthrough** for local judging: [DEMO_SCRIPT.md](DEMO_SCRIPT.md).
- **Final project link:** a public repository (GitHub) is the simplest option that needs no login.
  A public deployment needs the checks in [DEPLOYMENT.md](../DEPLOYMENT.md) first.
