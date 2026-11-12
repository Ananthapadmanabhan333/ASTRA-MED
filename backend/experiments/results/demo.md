# ASTRA-MED AI demonstration (v20261112-164739-9c1cd54f)

> Simulated data only. This shows the pipeline working on controlled, known situations; it is not evidence of clinical performance.

## 1. Anomaly detection on controlled scenarios

Crew member AST-03 (Priya Raman); baseline from 7 clean simulated days; analysis day 2026-07-01 (UTC). Model v20261112-164739-9c1cd54f.

| Situation | Should alarm | Ensemble flagged | First flag | Peak score | Fixed thresholds flagged | Top signals (ensemble attribution) | Kind |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A: sudden desaturation | yes | 11 of 12 windows | 5 min after start | 10.49x | 11 windows | SpO2 69%, Respiratory rate 17%, Heart rate 13% | sudden change |
| B: subtle heart-rate rise (below fixed limits) | yes | 11 of 12 windows | 5 min after start | 2.60x | 0 windows | Heart rate 88% | sudden change |
| C: gradual temperature drift (12 h) | yes | 97 of 120 windows | 55 min after start | 5.42x | 0 windows | Body temperature 80%, Heart rate 13% | gradual deviation |
| D: artefacts and 40-min dropout | no | 1 of 22 windows | 5 min after start | 1.04x | 0 windows | Diastolic pressure 36%, Systolic pressure 21%, Heart rate 20%, Respiratory rate 16% | sustained offset |

Outside the four situations the ensemble flagged 3 of 122 windows (2.5%); fixed thresholds flagged 0.

## 2. Forecasting on held-out simulated history

Fresh simulated history for AST-03 (seed 31, not used in training); baseline fitted on its first 36 days. Forecast origins are taken from the test period.

### XGBoost (engineered features)

| Origin (UTC) | Horizon | Actual HR | Forecast | 90% interval | Inside |
| --- | --- | --- | --- | --- | --- |
| 02-22 00:00 | 1 h | 51.9 | 51.2 | 46.2 to 56.1 | yes |
| 02-22 00:00 | 6 h | 68.5 | 66.6 | 59.6 to 73.7 | yes |
| 02-22 00:00 | 12 h | 71.7 | 66.6 | 59.3 to 73.9 | yes |
| 02-22 00:00 | 24 h | 56.9 | 53.5 | 45.9 to 61.0 | yes |
| 02-24 00:00 | 1 h | 51.5 | 53.0 | 48.0 to 57.9 | yes |
| 02-24 00:00 | 6 h | 71.5 | 69.0 | 62.0 to 76.1 | yes |
| 02-24 00:00 | 12 h | 82.8 | 67.3 | 60.0 to 74.6 | no |
| 02-24 00:00 | 24 h | 56.2 | 54.2 | 46.6 to 61.7 | yes |
| 02-26 00:00 | 1 h | 51.4 | 53.0 | 48.0 to 57.9 | yes |
| 02-26 00:00 | 6 h | 60.6 | 64.0 | 56.9 to 71.0 | yes |
| 02-26 00:00 | 12 h | 72.5 | 72.9 | 65.6 to 80.2 | yes |
| 02-26 00:00 | 24 h | 54.1 | 54.1 | 46.5 to 61.6 | yes |

Mean absolute error over these origins: Heart rate 3.17 bpm, SpO2 0.21 %, Respiratory rate 0.56 breaths/min, Body temperature 0.14 °C. 43 of 48 actual values fell inside the 90% interval.

### GRU

| Origin (UTC) | Horizon | Actual HR | Forecast | 90% interval | Inside |
| --- | --- | --- | --- | --- | --- |
| 02-22 00:00 | 1 h | 51.9 | 53.1 | 46.1 to 60.1 | yes |
| 02-22 00:00 | 6 h | 68.5 | 69.8 | 61.6 to 78.1 | yes |
| 02-22 00:00 | 12 h | 71.7 | 68.0 | 59.5 to 76.5 | yes |
| 02-22 00:00 | 24 h | 56.9 | 55.0 | 46.2 to 63.9 | yes |
| 02-24 00:00 | 1 h | 51.5 | 53.5 | 46.5 to 60.5 | yes |
| 02-24 00:00 | 6 h | 71.5 | 69.4 | 61.1 to 77.6 | yes |
| 02-24 00:00 | 12 h | 82.8 | 69.1 | 60.6 to 77.6 | no |
| 02-24 00:00 | 24 h | 56.2 | 54.7 | 45.8 to 63.5 | yes |
| 02-26 00:00 | 1 h | 51.4 | 52.7 | 45.7 to 59.7 | yes |
| 02-26 00:00 | 6 h | 60.6 | 68.6 | 60.4 to 76.8 | yes |
| 02-26 00:00 | 12 h | 72.5 | 71.2 | 62.7 to 79.7 | yes |
| 02-26 00:00 | 24 h | 54.1 | 55.1 | 46.2 to 63.9 | yes |

Mean absolute error over these origins: Heart rate 3.26 bpm, SpO2 0.24 %, Respiratory rate 0.69 breaths/min, Body temperature 0.13 °C. 45 of 48 actual values fell inside the 90% interval.

### Personal climatology (baseline for planned activity)

| Origin (UTC) | Horizon | Actual HR | Forecast | 90% interval | Inside |
| --- | --- | --- | --- | --- | --- |
| 02-22 00:00 | 1 h | 51.9 | 54.0 | 45.1 to 62.9 | yes |
| 02-22 00:00 | 6 h | 68.5 | 67.1 | 58.2 to 76.0 | yes |
| 02-22 00:00 | 12 h | 71.7 | 70.2 | 61.4 to 79.0 | yes |
| 02-22 00:00 | 24 h | 56.9 | 54.0 | 44.7 to 63.3 | yes |
| 02-24 00:00 | 1 h | 51.5 | 54.0 | 45.1 to 62.9 | yes |
| 02-24 00:00 | 6 h | 71.5 | 67.1 | 58.2 to 76.0 | yes |
| 02-24 00:00 | 12 h | 82.8 | 70.2 | 61.4 to 79.0 | no |
| 02-24 00:00 | 24 h | 56.2 | 54.0 | 44.7 to 63.3 | yes |
| 02-26 00:00 | 1 h | 51.4 | 54.0 | 45.1 to 62.9 | yes |
| 02-26 00:00 | 6 h | 60.6 | 67.1 | 58.2 to 76.0 | yes |
| 02-26 00:00 | 12 h | 72.5 | 70.2 | 61.4 to 79.0 | yes |
| 02-26 00:00 | 24 h | 54.1 | 54.0 | 44.7 to 63.3 | yes |

Mean absolute error over these origins: Heart rate 3.43 bpm, SpO2 0.24 %, Respiratory rate 0.60 breaths/min, Body temperature 0.13 °C. 46 of 48 actual values fell inside the 90% interval.
