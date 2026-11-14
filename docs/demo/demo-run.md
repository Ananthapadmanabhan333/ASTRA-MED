# Demonstration run (phase 7 scenario)

> All crew measurements are **simulated** by the ASTRA-MED simulator; the deviation is a documented software test scenario, not a medical event. NASA space-weather records are real public data and are context only. Nothing here is a diagnosis.

Run at 2026-11-14T12:33:01+00:00 against `http://127.0.0.1:8000` with `backend/scripts/demo_phase7.py`. Result: **all steps passed**.

| Step | Result | What the system produced | Time |
| --- | --- | --- | --- |
| 1 Physiological data enters ASTRA-MED | pass | 3 live AST-01 readings in 3 s (data_source ['simulated']); test scenario 'desaturation' started (de71b3908561) | 3.2 s |
| 2 Monitoring engine detects the deviation | pass | rule alert 0d20b49540474a43: Oxygen desaturation (caution); SpO2 trend 98.4 -> 93.1 % | 50.0 s |
| 3 AI engine analyses the measurements | pass | model v20261114-115210-9c1cd54f: 2 of 13 windows flagged in the last hour; risk 64.4/100 (high_concern), top warning: Multivariate pattern flagged (sustained offset) | 0.8 s |
| 4 Digital twin updates | pass | last measurement 2026-11-14T12:33:55.582790Z, twin updated 2026-11-14T12:30:55.663493Z; current keys ['active_scenarios', 'category', 'open_alerts', 'reading', 'status'] | 0.6 s |
| 5 Space environment data is retrieved | pass | DONKI sync HTTP 200; 30-day NASA DONKI summary keys ['alerts', 'caveats', 'counts', 'fastest_cme', 'flare_classes']; radiation view HTTP 200 | 0.2 s |
| 6 Environmental context is investigated | pass | 7 NASA space-weather record(s) within ±48 h of the alert (indicators only, never converted into a dose) | 0.0 s |
| 7 Explainable alert | pass | rule 'Threshold rule spo2:low: spo2 below 94 % for 5 consecutive seconds (activity: work).', contributors ['spo2', 'respiratory_rate', 'heart_rate']; alert centre AL-f98e424e596b priority High, classification Rule-based detection | 0.3 s |
| 8 Medical assistant summarises the evidence | pass | 19 statement(s), 18 with citations, 18 source(s), declined=[], mode extractive | 2.0 s |
| 9 Mission control displays the incident | pass | in the mission-control overview: True; pushed live to the dashboard: True | 0.2 s |
| 10 Structured incident report | pass | report d50eae4ae429454b 'Oxygen desaturation' (draft, integrity intact, sha256 f19572ef4fdf...), PDF 8295 bytes | 0.4 s |
