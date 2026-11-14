# Presentation

Two decks share one story:

- **Submission demo deck:** at most **7 slides** including title and intro. This is an official
  limit; a deck over it is not eligible for global judging.
- **Full presentation:** 12 slides, for local judging or a live pitch. The organisers set no limit
  for local pitches, so check with your Local Lead.

**Required on the demo deck:**

- the team name, the team members' names and the challenge selected;
- an image of the project;
- the user experience;
- how NASA and space-agency data make the solution possible.

Slides must be in English. AI-generated images need a visible "SI-generated" watermark.

Every number below comes from [SCIENTIFIC_VALIDATION.md](../SCIENTIFIC_VALIDATION.md) or
[BENCHMARKS.md](../BENCHMARKS.md). Do not round them up.

## A. Submission demo deck (7 slides)

| # | Title | Content | Visual |
| --- | --- | --- | --- |
| 1 | **ASTRA-MED** | "Personal, explainable health monitoring for long-duration crews." Team name, member names, challenge: *Create Health Monitoring Software for Astronauts on Space Missions* (NASA Space Apps 2026) | Product screenshot: the mission-control dashboard with the "simulated data" marker visible |
| 2 | The problem | Far from Earth the crew must spot health changes themselves. The same heart rate means different things at rest, in exercise or after a solar event. Fixed alarm limits ring constantly or miss slow change | One line per NASA HRP hazard (radiation, isolation, distance, gravity, closed environment), with the source |
| 3 | What ASTRA-MED does | The astronaut's own self-check (body-systems map, glucose, mood, symptoms, today's checks); learns each person's normal, flags unusual patterns, forecasts 24 h ahead with uncertainty, explains every alert, links it to real NASA space weather | Screenshot: the Crew self-check page next to an alert explanation |
| 4 | User experience | A developing desaturation, end to end: simulated readings → alert → AI analysis → twin → NASA context → cited assistant summary → incident report | The 10-step flow as a horizontal strip with small screenshots; "all values simulated" label |
| 5 | NASA data inside | DONKI space weather (3,296 events stored), OSDR ISS environment and dose (17 missions), OSDR studies; measured, indicator, estimate and simulated are never mixed; a flare is never turned into a dose | The four radiation categories A–D with the NASA source of each |
| 6 | Does it work? (simulated data) | Learned detectors F1 0.62–0.81 vs 0.36 for fixed limits; HR forecast 2.2 vs 3.9 bpm at 1 h; 90 % intervals cover 89–91 %. Honest: the ensemble is not better than its best member; not clinically validated | One bar chart (F1 by method, mean ± SD over 3 datasets) |
| 7 | What's next | Validation on analogue-mission data with clinicians; device and camera input for the self-check; guidance tied to approved mission procedures; open source for others to build on | Roadmap of three steps, plus the repository link |

## B. Full presentation (15 slides)

| # | Slide | Key message | Speaker notes (what to say, what not to claim) | Visual |
| --- | --- | --- | --- | --- |
| 1 | Title: ASTRA-MED | Personal, explainable health monitoring for long missions | Team, challenge; "research prototype, simulated crew" | Dashboard screenshot |
| 2 | The problem | On Mars missions, crews self-monitor with delayed or no ground support | Cite NASA HRP hazards and Patel 2020 "red risks"; communication delay | Earth–Mars delay diagram |
| 3 | Why it matters | Individual variation and context make raw numbers misleading | The NASA Twins Study showed multisystem individual change; fixed limits miss slow change (77 % of anomalous windows missed by fixed rules in our evaluation) | Same HR value, three contexts |
| 4 | Existing limitations | Fixed alarm limits, opaque AI, data that mixes measured and modelled values | Fixed rules missed 77 % of anomalous windows in our evaluation; flares are often shown as if they were doses | Comparison table |
| 5 | Our solution | Self-check for the astronaut, personal baselines, explainable alerts, context, evidence | Decision support, not diagnosis; experimental AI can never escalate on its own | Pipeline graphic |
| 6 | Crew self-check | The astronaut's own view: body-systems map, glucose, mood and symptoms, today's checks | Glucose bands follow ADA criteria (orientation only); mood is compared with their own history; the guidance is "when to call the flight surgeon", never a treatment | Self-check screenshot |
| 7 | Architecture | One backend, real NASA data, a typed API, a live dashboard | FastAPI, PostgreSQL with Alembic, Next.js; REST and WebSocket; roles and audit | Architecture diagram ([RESEARCH_PAPER §6](../RESEARCH_PAPER.md#6-proposed-architecture)) |
| 8 | NASA data integration | DONKI, OSDR EDA, OSDR catalogue, with provenance and categories | api.nasa.gov DONKI proxy returned 404; the circuit breaker fell back to CCMC; RR-18 humidity at 125.8 % was excluded. These show real data handling | Radiation categories A–D |
| 9 | AI predictive intelligence | Five detectors, ensemble, XGBoost forecasts, conformal intervals, risk rules | Thresholds at 1 % validation false-positive rate; chronological splits; no test-set tuning | Model pipeline diagram |
| 10 | Astronaut digital twin | A daily record per crew member, trends, stages, six body systems | "Twin" means a record, not a physiological simulation; co-deviation is "not a cause" | Twin view screenshot |
| 11 | Mission control demo | The ten-step scenario, live | Run `scripts/demo_phase7.py --keep` beforehand, then walk the UI ([DEMO_SCRIPT.md](DEMO_SCRIPT.md)) | Live demo or recording |
| 12 | Scientific evaluation | Results on 3 simulated datasets, including negative results | Ensemble ≈ LOF; trees beat neural networks; coverage 89–91 %; reproducible to the 4th decimal; tiers 2–4 not done | Two small tables |
| 13 | Innovation and impact | Integration, transparency, honesty about data | Crew-side and ground-side; analogue missions; remote care on Earth | Impact map |
| 14 | Limitations and future scope | Simulated data; no clinical validation; no self-check mode yet | Next steps: analogue validation, self-check mode, glucose and mood, geometry-aware radiation | Roadmap |
| 15 | Conclusion and future vision | Personal, explainable, honest; open source | Analogue-mission validation with clinicians is the next step; thank the judges | Repository link and team |

## Charts to build (from repository data only)

1. **F1 by method:** mean ± SD over 3 datasets, from `backend/experiments/results/seed-study.json`
   (`summary` → `anomaly.<model>.f1`). Show fixed thresholds next to the learned detectors.
2. **Heart-rate MAE at 1 h and 24 h by forecaster:** from the same file
   (`forecast.<model>.heart_rate.1h.mae`).
3. **Interval coverage against nominal 90 %:** coverage per forecaster, with a reference line at
   0.90.

Label every chart "simulated data".
