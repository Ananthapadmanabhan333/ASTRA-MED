# AI intelligence engine (phase 3)

Personal baselines, multivariate anomaly detection, 1–24 h forecasts with intervals, a transparent
early-warning score and an explanation for every output. Code lives in `backend/app/ai/`. The
dashboard view is **AI intelligence** (`/intelligence`), and **Model evaluation**
(`/intelligence/models`) shows the evaluation results.

> **Experimental, simulated-data decision support.** Every model is trained and evaluated only on data
> from the ASTRA-MED simulator. The results show how well each method recovers the simulator's own
> injected events and dynamics. They do **not** establish clinical or real-world accuracy. No model
> has been validated on astronaut or patient populations. No output is a diagnosis.

## Pipeline at a glance

```
stored 1 Hz / 5-min samples ──► windows.py ──► baseline.py ──► features.py ──┬─► anomaly/ (5 detectors + ensemble)
  (or POSTed readings)          5-min medians   personal        32 causal     │
                                plausibility    reference per   features in   ├─► forecasting/ (XGBoost, LSTM, GRU, TCN
                                filter          signal × state  6 groups      │    + 3 baselines, conformal intervals)
                                                × time of day                 │
                                                                              └─► risk.py (JSON rules) ──► explain.py
```

`service.py` (`AIService`) runs all of this behind the API. It loads a hash-verified model bundle,
keeps each crew member's baseline current, and does CPU-heavy work in a worker thread.

## Module 1: personal baselines (`baseline.py`)

- **Cells:** one per signal × activity state (sleep, rest, work, exercise) × 4-hour time-of-day
  bucket. Each cell keeps running Welford mean/std and a 600-value reservoir. From the reservoir it
  derives a robust center (median), a robust scale (IQR/1.349, with a per-signal floor) and percentiles.
- **Fallback:** a cell with fewer than 30 windows falls back to the whole activity, which needs
  12 windows (1 hour). It never falls back to a reference pooled across activities. An activity
  with less history gets no z-score: its signals are reported but not scored for deviation, and
  the explanation says so. Otherwise an ordinary first workout would score as z ≈ 6 against the
  pooled rest and sleep values. The pooled value is still used as a rough expectation for the
  climatology forecast. The response reports which level was used and how many windows it rests on.
- **Updates:** `update()` adds windows one at a time, so the live service updates incrementally
  every 60 s. It refits from stored history every 6 h. Rolling 24 h / 7 d mean, std and percentiles
  come from `rolling_stats()`.
- **Outputs:** expected value for the current state and time, z-score, percentile, and deviation.
  These are served at `GET /api/ai/astronaut/{id}/baseline`.

Signals: heart rate, SpO₂, systolic and diastolic pressure, temperature, respiratory rate. Sleep and
activity enter as context (state, MET, sleep fraction).

## Module 2: anomaly detection (`anomaly/`)

**Features** (`features.py`, all causal, so window *t* uses only data up to *t*):

| Group | Examples |
| --- | --- |
| `level` | z-score of each signal against its personal reference |
| `sudden` | 5-minute change in z |
| `sustained` | 2-hour rolling mean of z |
| `trend` | 6-hour rolling slope of z |
| `context` | activity state one-hot, MET, sleep fraction, time of day |
| `quality` | fraction of the window that was missing |

Implausible values (sensor artefacts) become missing before windowing. Short gaps are
forward-filled for up to 15 minutes; longer gaps keep a neutral z of 0 and raise the
missing-fraction feature. Z-scores are clipped at ±20.

**Detectors** (`detectors.py`): a statistical personal-baseline detector, Isolation Forest, Local
Outlier Factor (novelty mode), One-Class SVM, and a PyTorch autoencoder (d→64→16→64→d). All
train on clean training windows only.

- Each detector gets per-feature attributions by occlusion: replace one signal's features with the
  reference value and measure the score drop.
- Each detector's threshold is set on validation normal windows for a 1 % false-alarm rate.
- Each learned detector picks its feature set by **validation** AUPRC from five candidates (see the
  ablation below).
- The **ensemble** is a weighted mean of calibrated scores, with its own threshold calibrated on
  validation data. Members need validation AUPRC ≥ 80 % of the best detector; weight = AUPRC above
  the base rate.

The phase 2 fixed alert thresholds are scored on the same windows as a reference (`fixed.py`).

## Module 3: forecasting (`forecasting/`)

- **Targets and grid:** heart rate, SpO₂, respiratory rate and temperature on a 30-minute grid.
  Each forecast uses 24 h of history (48 steps) and predicts 48 steps. 1, 6, 12 and 24 h are reported.
- **Covariates:** the planned mission timeline (sleep, exercise, work) for the next 24 h comes from
  the simulator's schedule (`timeline.py`).
- **Baselines:** persistence (last value), seasonal naive (same time yesterday), and personal
  climatology (the baseline for the planned activity). Skill is reported against climatology.
- **XGBoost:** horizon-as-feature over engineered features (recent values, trend, same time
  yesterday, current deviation, planned activity at the target time). Native TreeSHAP gives the
  feature contributions shown in the UI.
- **LSTM, GRU, TCN:** sequence models over 12 normalised channels. They predict a residual over
  climatology and train with a masked MSE.
- **Intervals:** split-conformal at 90 % nominal coverage, calibrated per horizon step on a
  held-out half of the validation period. The other half is used for early stopping.

## Module 4: risk scoring (`risk.py`, `risk_config.json`)

Transparent, configurable rules; no probabilistic model. Points add up to a 0–100 risk score:

| Component | Rule (defaults) |
| --- | --- |
| Baseline deviation | From \|z\| = 2: (\|z\| − 1) × 5 points, capped at 22 per signal, × a duration factor (0.4 for a new deviation, 1.0 once it has lasted 60 min) |
| Anomaly ensemble | 18 × (score / threshold), capped at 30, × the same duration factor, + 2 for each agreeing detector beyond the first |
| Forecast trend | 14 points if the point forecast crosses a caution limit within 6/12/24 h ("likely"); 6 if only the 90 % interval does ("possible") |
| Open alerts | critical 40, caution 20, advisory 7 |

Categories: **Normal** < 12 ≤ **Low concern** < 30 ≤ **Moderate concern** < 55 ≤ **High concern**.
The health score is 100 − risk. Every warning lists its points, evidence and priority. A warning is
never labelled "Normal": its category is at least Low concern. Edit the JSON and restart to change
the rules. The values are prototype settings, not clinical criteria.

## Module 5: explanations (`explain.py`)

Every anomaly, forecast, risk warning and alert explanation carries the same structure:

- **What changed:** plain-language sentence. Signals within 0.5 SD of baseline read as
  "near baseline".
- **Kind:** sudden change, gradual deviation or sustained offset. A step and a ramp are both fitted
  to the flagged run, and the better fit wins.
- **Contributing signals:** share of attribution, current value vs baseline, z-score, percentile.
  Anomalies use occlusion attribution; XGBoost forecasts use TreeSHAP.
- **Significance:** none / minor / notable / major, at |z| 1.5 / 2.5 / 4.
- **Confidence:** low / medium / high, from detector agreement, data completeness and baseline
  depth. Each response shows the numbers behind it.
- **Data limitations:** missing data, thin baselines, the 5-minute resolution, and always the
  synthetic-data caveat.

The onset-kind margins (0.8 / 0.9) were set by inspecting the demonstration cases. They are a
heuristic, not a validated classifier.

## Module 6: API

See [API.md](API.md#ai-intelligence-phase-3). Endpoints: `POST /api/ai/anomaly-detection`,
`GET /api/ai/astronaut/{id}/baseline`, `/forecast`, `/risk-assessment`, `GET /api/ai/crew-overview`,
`/model-performance`, `/explanations/{alert_id}`, `/status`, and `POST /api/ai/models/reload`.

## Module 7: dashboard

`frontend/src/components/ai/`:

- `intelligence-center` lays out the page.
- `risk-board`: crew risk cards and a crew-wide early-warning queue sorted by priority.
- `forecast-panel`: observed + forecast + 90 % band, with a model and signal picker.
- `anomaly-timeline`: ensemble score, a detector-agreement strip, and detections with explanations.
- `baseline-panel`: the personal reference per signal.
- `model-performance`: the evaluation tables.
- `explanation-view` renders the shared explanation structure. It is reused by the alert
  **Explain** dialog (`components/alerts/explain-alert.tsx`) and the crew profile's
  **AI early warning** card.

## Module 8: experimental design and reproducibility

```bash
cd backend
.venv/Scripts/python -m app.ai.train            # full run, about 6 min on CPU; writes backend/artifacts/<version>/
.venv/Scripts/python -m app.ai.train --quick    # smoke run (used by the test suite)
.venv/Scripts/python -m app.ai.demo             # controlled scenarios + held-out forecasts -> experiments/results/demo.md
```

- **Data:** `datasets/synthetic.py` generates a labelled dataset from the Phase 2 simulator. The
  default is 4 crew members, 120 days, seed 7.
  - Sudden events: tachycardia, bradycardia, desaturation, temperature, respiratory rate, irregular
    rhythm.
  - Gradual drifts: heart rate, BP, SpO₂ and temperature, ramping over 6–24 h.
  - 45 % of events are "subtle", meaning they stay below the fixed alert limits.
  - Slow day-to-day variability, 2 % random missing values, sensor dropouts and artefact spikes.
    Artefacts are **not** labelled as anomalies.
  - The labels come from the generator's own event envelopes. A window is anomalous when the
    envelope is above 0.3 of full effect. Ramp-edge windows below that level are excluded from
    scoring.
- **Synthetic and real data are separate.** The dataset fingerprint, source and a `real_data`
  field are stored with every run. No real data is used today (see
  [NASA_DATA_INTEGRATION.md](NASA_DATA_INTEGRATION.md#ai-engine-datasets-and-licensing)).
- **Leakage controls:**
  - Chronological, day-aligned 60/20/20 splits.
  - Baselines and scalers are fitted on clean training windows only.
  - Features are causal.
  - Forecast targets never cross a split boundary.
  - Thresholds, ensemble membership and feature sets are chosen on validation data only.
  - The test split is used once, for reporting.
- **Metrics:**
  - Anomaly detection: precision, recall, F1, AUROC, AUPRC and false-alarm rate per window; event
    recall and median detection delay per event, by event type; false warnings per crew-day.
  - Forecasting: MAE, RMSE, interval coverage and width per horizon, and skill vs climatology.
- **Ablations:**
  - Anomaly: five feature sets per detector.
  - Forecasting: XGBoost without the planned schedule, without baseline deviation, and without
    recent values.
- **Versioning:** each run writes `backend/artifacts/v<timestamp>-<config hash>/`. It contains the
  models, `config.json`, `results.json`, `report.md`, and a `manifest.json` with a SHA-256 for every
  file, plus the git commit and dataset fingerprint. The registry verifies every hash before
  unpickling, so only artifacts you trained yourself are loaded. Never point
  `ASTRA_AI_ARTIFACTS_DIR` at files from an untrusted source. The latest report is copied to
  `backend/experiments/results/`.

## Results (version v20261112-164739-9c1cd54f, synthetic test split)

The full tables are in [`backend/experiments/results/latest-report.md`](../backend/experiments/results/latest-report.md).
The test split has 27,648 five-minute windows, 15 % of them anomalous.

| Anomaly detector | Precision | Recall | F1 | AUROC | False-alarm rate | Events detected | False warnings / crew-day |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Ensemble | 0.94 | 0.74 | 0.83 | 0.95 | 0.87 % | 96 % | 0.43 |
| Local Outlier Factor | 0.94 | 0.73 | 0.82 | 0.95 | 0.80 % | 94 % | 0.30 |
| One-Class SVM | 0.93 | 0.71 | 0.80 | 0.94 | 0.98 % | 96 % | 0.47 |
| Autoencoder | 0.95 | 0.59 | 0.72 | 0.92 | 0.59 % | 86 % | 1.20 |
| Isolation Forest | 0.90 | 0.53 | 0.67 | 0.93 | 1.10 % | 91 % | 0.32 |
| Statistical baseline | 0.89 | 0.29 | 0.44 | 0.96 | 0.64 % | 51 % | 1.83 |
| Phase 2 fixed thresholds | 0.80 | 0.20 | 0.33 | 0.77 | 0.93 % | 53 % | 1.15 |

What this does and doesn't show:

- **Personal, multivariate detection beats fixed limits on this simulator.** The ensemble finds 91 %
  of the subtle events. These are the events designed to stay below the fixed limits, which find
  24 % of them. Gradual drifts are detected, with a median delay of 100–125 min for heart-rate and BP
  ramps.
- **The ensemble is only marginally better than LOF alone.** Bradycardia (75 %) and irregular rhythm
  (83 %) are the weakest event types. Rhythm irregularity is a beat-to-beat property, and 5-minute
  medians of vitals mostly average it away.
- **The dynamics features hurt most detectors.** The `sudden` and `trend` groups add noise. Validation
  selection picked level-only or no-dynamics feature sets for three of the four learned detectors.

| Forecast MAE, 1 h / 24 h | Heart rate (bpm) | SpO₂ (%) | Resp. rate (/min) | Temperature (°C) |
| --- | --- | --- | --- | --- |
| Personal climatology | 4.17 / 4.17 | 0.47 / 0.47 | 0.89 / 0.89 | 0.115 / 0.115 |
| XGBoost | **2.34 / 3.41** | 0.30 / 0.47 | **0.53 / 0.77** | **0.067 / 0.102** |
| GRU | 3.05 / 3.91 | 0.30 / 0.50 | 0.65 / 0.88 | 0.083 / 0.110 |
| LSTM | 3.24 / 3.88 | 0.33 / 0.52 | 0.69 / 0.88 | 0.086 / 0.113 |
| TCN | 3.22 / 3.94 | 0.30 / 0.47 | 0.68 / 0.87 | 0.083 / 0.109 |

- XGBoost is the serving default.
- Measured 90 % interval coverage on test is 83–92 % across signals, models and horizons. SpO₂
  intervals under-cover the most (83–89 %).
- Skill over climatology is real at 1 h (XGBoost 36–44 %) and small at 24 h (−2 % to 18 %).
  SpO₂ at 24 h has none.
- Dropping the planned schedule nearly doubles the 1 h heart-rate error (2.34 → 4.19 bpm). The
  forecasts therefore depend on knowing the timeline, which in the simulator is exactly the timeline
  that happens.
- The current-deviation feature group adds almost nothing (2.34 vs 2.35 bpm).

**Controlled demonstration** ([`demo.md`](../backend/experiments/results/demo.md)), on an unseen
simulated day:

- A sudden desaturation, a subtle heart-rate rise and a 12-hour temperature drift are all flagged.
  The fixed thresholds miss the last two entirely.
- A day of artefacts and a 40-minute dropout raises one window.
- The ensemble flags 2.5 % of the windows outside the four situations, against the 1 % target set
  on validation data.
- On fresh simulated history (seed 31), 43 of 48 XGBoost values fell inside the 90 % interval.

## Limitations

1. **Synthetic data only.** The physiology, the injected events and the labels come from one design.
   That makes detection and forecasting easier than real monitoring, where events are unlabelled,
   heterogeneous and rare.
2. **Planned activity equals actual activity** in the simulator. Real timelines slip, and forecasts
   lean heavily on the plan.
3. **Thresholds are calibrated with labels.** A real deployment has none and would need
   clinician-reviewed calibration and monitoring for drift.
4. **Conformal coverage assumes exchangeability**, which time series only approximate. Test coverage
   is measured, not assumed.
5. **The 5-minute resolution** hides brief events. A 5-second threshold breach can look normal in its
   window. The alert explanation says so.
6. **The onset-kind margins are a heuristic** tuned on the demonstration cases.
7. **Activity transitions can raise brief flags.** A 5-minute window takes the majority activity,
   so the end of a workout can be scored as "exercise" while heart rate is already recovering.
   This was seen live as one flagged window at the end of an exercise session. The risk score's
   duration factor dampens such single windows, but they are not suppressed.
8. **Four simulated crew members** limit the person-to-person variation the models see. A new crew
   member's baseline starts thin, and the explanations report its depth. The demonstration uses
   7 days.
9. **Inference is not authenticated**, and model reload is gated only by
   `ASTRA_SIMULATION_CONTROL_ENABLED`.

## Next steps

- **Real data.** Calibrate and validate on real, de-identified physiological data. One route is
  public non-astronaut datasets such as PhysioNet, used under their licences. The other is NASA LSDA
  or OSDR data under a data-use agreement. Report the results separately from the synthetic ones.
- **Onset and change detection.** Replace the onset-kind heuristic with a validated change-point
  method (for example BOCPD or CUSUM). Detect rhythm on the beat-to-beat signal rather than on
  windowed vitals.
- **Robustness to timeline slips.** Add forecast inputs that tolerate schedule changes, such as
  actual vs planned activity and uncertainty in the plan. Re-run the schedule ablation with
  realistic timeline noise.
- **Production readiness.** Monitor drift and recalibrate thresholds online. Add authentication and
  an audit log for model reload.
- **Clinical review.** Only after clinical review should the rules move to a probabilistic risk model.
