# Replication across independent simulated datasets

> **Synthetic data only.** Each run generates a new simulated crew history (different events, noise and missing data) and retrains every model with a new seed. The spread shows run-to-run variability of the method on simulated data; it is not evidence of real-world or clinical performance.

Seeds: 7, 11, 23 (3 runs). Configuration: `default`. Commit `8fae33c`. Generated 2026-11-14T12:05:47.196038+00:00. Values are mean ± sample standard deviation across runs.

## Anomaly detection (test split)

| Model | F1 | AUROC | AUPRC | False-positive rate | False-negative rate | Event recall |
| --- | --- | --- | --- | --- | --- | --- |
| statistical | 0.527 ± 0.080 | 0.968 ± 0.014 | 0.773 ± 0.072 | 0.0088 ± 0.0032 | 0.604 ± 0.094 | 0.63 ± 0.10 |
| isolation_forest | 0.616 ± 0.047 | 0.941 ± 0.008 | 0.728 ± 0.067 | 0.0097 ± 0.0015 | 0.514 ± 0.041 | 0.88 ± 0.05 |
| lof | 0.811 ± 0.029 | 0.960 ± 0.007 | 0.875 ± 0.025 | 0.0075 ± 0.0007 | 0.270 ± 0.039 | 0.93 ± 0.05 |
| one_class_svm | 0.789 ± 0.041 | 0.955 ± 0.016 | 0.857 ± 0.041 | 0.0105 ± 0.0024 | 0.280 ± 0.035 | 0.94 ± 0.04 |
| autoencoder | 0.688 ± 0.030 | 0.922 ± 0.017 | 0.764 ± 0.052 | 0.0074 ± 0.0018 | 0.437 ± 0.019 | 0.90 ± 0.05 |
| ensemble | 0.800 ± 0.052 | 0.962 ± 0.011 | 0.863 ± 0.045 | 0.0094 ± 0.0012 | 0.271 ± 0.056 | 0.94 ± 0.04 |
| fixed_thresholds | 0.357 ± 0.080 | 0.774 ± 0.021 | 0.486 ± 0.040 | 0.0063 ± 0.0031 | 0.767 ± 0.071 | 0.58 ± 0.07 |

## Forecasting (test split, physical units)

### heart rate (bpm)

| Model | MAE 1h | MAE 24h | RMSE 1h | Coverage 1h (90% nominal) | MAPE 1h (%) |
| --- | --- | --- | --- | --- | --- |
| persistence | 7.143 ± 0.079 | 5.586 ± 0.258 | 13.018 ± 0.200 | 0.906 ± 0.002 | 10.07 ± 0.14 |
| seasonal_naive | 5.658 ± 0.272 | 5.586 ± 0.258 | 9.487 ± 0.521 | 0.907 ± 0.011 | 8.57 ± 0.38 |
| climatology | 3.853 ± 0.275 | 3.847 ± 0.277 | 6.032 ± 0.651 | 0.892 ± 0.015 | 5.82 ± 0.35 |
| xgboost | 2.189 ± 0.159 | 3.147 ± 0.247 | 3.946 ± 0.771 | 0.904 ± 0.010 | 3.40 ± 0.20 |
| lstm | 3.046 ± 0.178 | 3.656 ± 0.218 | 5.158 ± 0.593 | 0.909 ± 0.010 | 4.61 ± 0.23 |
| gru | 2.975 ± 0.066 | 3.677 ± 0.220 | 5.109 ± 0.518 | 0.908 ± 0.013 | 4.49 ± 0.06 |
| tcn | 3.104 ± 0.141 | 3.744 ± 0.228 | 5.204 ± 0.572 | 0.908 ± 0.010 | 4.69 ± 0.16 |

### spo2 (%)

| Model | MAE 1h | MAE 24h | RMSE 1h | Coverage 1h (90% nominal) | MAPE 1h (%) |
| --- | --- | --- | --- | --- | --- |
| persistence | 0.338 ± 0.024 | 0.585 ± 0.133 | 0.709 ± 0.137 | 0.899 ± 0.011 | 0.35 ± 0.03 |
| seasonal_naive | 0.587 ± 0.131 | 0.585 ± 0.133 | 1.173 ± 0.310 | 0.905 ± 0.043 | 0.61 ± 0.14 |
| climatology | 0.386 ± 0.077 | 0.384 ± 0.077 | 0.851 ± 0.235 | 0.897 ± 0.034 | 0.40 ± 0.08 |
| xgboost | 0.268 ± 0.034 | 0.385 ± 0.083 | 0.585 ± 0.126 | 0.887 ± 0.015 | 0.28 ± 0.04 |
| lstm | 0.282 ± 0.041 | 0.408 ± 0.102 | 0.610 ± 0.139 | 0.897 ± 0.023 | 0.29 ± 0.04 |
| gru | 0.268 ± 0.029 | 0.400 ± 0.092 | 0.572 ± 0.117 | 0.900 ± 0.017 | 0.28 ± 0.03 |
| tcn | 0.276 ± 0.026 | 0.392 ± 0.075 | 0.581 ± 0.123 | 0.890 ± 0.014 | 0.29 ± 0.03 |

### respiratory rate (breaths/min)

| Model | MAE 1h | MAE 24h | RMSE 1h | Coverage 1h (90% nominal) | MAPE 1h (%) |
| --- | --- | --- | --- | --- | --- |
| persistence | 1.453 ± 0.029 | 1.235 ± 0.065 | 2.584 ± 0.084 | 0.908 ± 0.006 | 9.41 ± 0.19 |
| seasonal_naive | 1.240 ± 0.051 | 1.235 ± 0.065 | 2.095 ± 0.091 | 0.897 ± 0.030 | 8.47 ± 0.39 |
| climatology | 0.816 ± 0.062 | 0.816 ± 0.065 | 1.383 ± 0.018 | 0.907 ± 0.014 | 5.46 ± 0.43 |
| xgboost | 0.513 ± 0.024 | 0.702 ± 0.061 | 0.984 ± 0.078 | 0.912 ± 0.006 | 3.50 ± 0.18 |
| lstm | 0.657 ± 0.028 | 0.805 ± 0.064 | 1.182 ± 0.060 | 0.902 ± 0.013 | 4.41 ± 0.21 |
| gru | 0.641 ± 0.009 | 0.800 ± 0.067 | 1.161 ± 0.089 | 0.911 ± 0.014 | 4.31 ± 0.09 |
| tcn | 0.659 ± 0.027 | 0.797 ± 0.063 | 1.172 ± 0.081 | 0.906 ± 0.012 | 4.45 ± 0.22 |

### temperature c (°C)

| Model | MAE 1h | MAE 24h | RMSE 1h | Coverage 1h (90% nominal) | MAPE 1h (%) |
| --- | --- | --- | --- | --- | --- |
| persistence | 0.098 ± 0.002 | 0.140 ± 0.015 | 0.163 ± 0.004 | 0.897 ± 0.005 | not meaningful |
| seasonal_naive | 0.142 ± 0.014 | 0.140 ± 0.015 | 0.235 ± 0.020 | 0.863 ± 0.035 | not meaningful |
| climatology | 0.109 ± 0.010 | 0.109 ± 0.010 | 0.180 ± 0.018 | 0.888 ± 0.033 | not meaningful |
| xgboost | 0.062 ± 0.004 | 0.100 ± 0.008 | 0.114 ± 0.010 | 0.893 ± 0.014 | not meaningful |
| lstm | 0.080 ± 0.005 | 0.112 ± 0.008 | 0.130 ± 0.010 | 0.894 ± 0.014 | not meaningful |
| gru | 0.077 ± 0.006 | 0.109 ± 0.007 | 0.126 ± 0.008 | 0.885 ± 0.012 | not meaningful |
| tcn | 0.081 ± 0.002 | 0.112 ± 0.007 | 0.129 ± 0.006 | 0.888 ± 0.026 | not meaningful |

## Reading the spread

- Two models whose means differ by less than about two standard deviations should not be ranked against each other on this evidence.
- With only a few runs the standard deviation is itself uncertain; it is a rough guide, not a confidence interval.
- All runs share the simulator's physiology and event design, so this measures sensitivity to the random draw, not to a different population or real sensors.
