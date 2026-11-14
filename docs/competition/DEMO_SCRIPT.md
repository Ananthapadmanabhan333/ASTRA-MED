# Demonstration script: the ten-step scenario

A simulated astronaut is on a long-duration mission. Her oxygen saturation starts to fall. The demo
shows ASTRA-MED taking that from the first readings to a reviewed incident report. It takes about
6 minutes live.

**Ground rules for every demo:**

- No database values are edited by hand.
- No readings are typed in.
- The deviation is the simulator's documented **test scenario**, started through the public API.
- Say "simulated" whenever crew values are on screen; the dashboard marks them too.
- NASA data are real and are context, never a cause.

## Preparation (10 minutes before)

```bash
# 1. Database + API (PostgreSQL via pgserver) and the dashboard: launch configurations
#    "backend-postgres" and "frontend" (.claude/launch.json), or:
cd backend && python scripts/local_postgres.py serve     # API on http://127.0.0.1:8000
cd frontend && npm run dev                                # dashboard on http://localhost:3000
# 2. Demo accounts (local only; passwords go to backend/.dev-users.json, never shown on screen)
cd backend && python scripts/create_users.py dev
# 3. Rehearse the pipeline once without the UI (prints PASS/FAIL per step):
python scripts/demo_phase7.py --sync
```

`demo_phase7.py` checks the precondition itself: if AST-01 already has an open SpO₂ alert, it stops
and asks you to resolve it first. A verified run is recorded in
[docs/demo/demo-run.md](../demo/demo-run.md).

## Live run

Sign in as the operator demo account. Then run `python scripts/demo_phase7.py --sync --keep` in a
terminal beside the browser. `--keep` leaves the scenario and the alert in place for the walkthrough.

| Step | What happens (system) | Where to show it | What to say |
| --- | --- | --- | --- |
| 1. Data enters | The simulator streams AST-01's vitals at 1 Hz; the script starts the "desaturation" test scenario | **Command** → crew tile AST-01 (live, "simulated" marker); **Crew monitoring** → AST-01 live vitals | "These are simulated vital signs arriving once a second. We start a documented test scenario: a slow fall in oxygen saturation." |
| 2. Detection | The monitoring engine's personal-context rule opens an SpO₂ alert after the value stays low (in the verified run: 98.4 → 93.1 %, alert after 50 s) | Header **notification centre** (badge); **Alert centre** | "The monitoring engine flags it. It's a rule-based detection, labelled as such." |
| 3. AI analysis | Anomaly ensemble and risk assessment on the last hour (verified run: 2 of 13 windows flagged; risk 64/100, "high concern") | **AI intelligence** (AST-01): anomaly timeline, risk card, forecast with intervals | "Five detectors compare her with her own baseline. The forecast shows the next 24 hours with a 90 % range. These are experimental outputs." |
| 4. Twin update | The twin shows the latest measurement, open alert and active scenario | **Digital twin → AST-01** | "Her digital twin, a daily record of her health data, now shows the alert and the test scenario." |
| 5. Space data | The script triggers a DONKI sync from NASA CCMC (HTTP 200 in the verified run); stored DONKI and EDA data load | **Space weather**; **Radiation intelligence** (categories A–D) | "This is real NASA space-weather data. Flares and particle events are indicators; we never turn them into a dose." |
| 6. Context | NASA records within ±48 h of the alert (7 in the verified run) | **Alert centre** → alert → *Correlations*; **Situational awareness** timeline | "ASTRA-MED checks what happened in space around the alert: context, not a cause." |
| 7. Explainable alert | Rule, contributing signals (SpO₂, respiratory rate, heart rate), priority, classification, confidence | **Alert centre** → alert detail | "Every alert says what was measured, how far it is from her normal, which signals drove it, and how confident the system is." |
| 8. Assistant | A cited summary: 19 statements, 18 with citations, in the verified run | **AI medical assistant**: ask "Summarise the evidence for the current oxygen saturation alert for AST-01" | "Every sentence cites a record or document. It declines to diagnose and points to the flight surgeon." |
| 9. Mission control | The alert is in the overview and was pushed live | **Command** (active alerts, timeline) | "The whole crew's status, alerts and events in one place." |
| 10. Report | A structured incident report, SHA-256 sealed, with a PDF | **Incident reports** → the new report → **PDF** | "A sealed report for medical review: the observation, measurements, context, the AI output and its limits." |

**Close.** Acknowledge, then resolve the alert in the **Alert centre** with a note ("Demo:
simulated test scenario"). Cancel the scenario under **Anomalies & tests**, or run the script without
`--keep` next time.

## Optional: the mission simulation sandbox

`python scripts/e2e_mission.py` does the same through the sandbox: a separate engine and clock at
up to 120×, without touching the live crew history. Show **Mission simulation** with the amber "sandbox"
marking and its playback, to demonstrate the "clearly distinguish simulated information" rule.

## If something goes wrong

| Symptom | Fix |
| --- | --- |
| Script exits with "already has an open SpO₂ alert" | Resolve that alert once SpO₂ has recovered, then rerun |
| DONKI sync fails (offline) | Run without `--sync`. Stored NASA data is still shown with its last sync time |
| Dashboard says "Offline" | Check the backend terminal; the dashboard reconnects and refetches by itself |
| First page load hangs on "Checking your session" in dev mode | Reload once (first compile of the dev server) |
