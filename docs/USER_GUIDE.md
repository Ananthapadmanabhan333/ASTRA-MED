# User guide

ASTRA-MED is a research prototype with **simulated** crew data. Nothing in it is a diagnosis.

## Signing in and roles

Sign in with the account an administrator created for you (local demo accounts:
`python scripts/create_users.py dev`). What you see depends on your role:

| Role | Can |
| --- | --- |
| Flight surgeon | Read all crew health data, manage alerts, write and review incident reports, record self-checks, use the assistant |
| Mission operator | As above without report sign-off; also run simulations, sync NASA data, repair the database |
| Analyst | Read crew health data and use the assistant; no actions |
| Administrator | Manage accounts, the audit log and models; no crew health data |

## Main areas (sidebar)

| Area | Use it to |
| --- | --- |
| **Mission control** (`/`) | See the whole crew, active alerts, events, space weather and system health at a glance |
| **Crew monitoring** (`/crew`) | Compare crew members; open a profile with live vitals and trends |
| **Crew self-check** (`/self-check`) | The astronaut's own view: body-systems map, glucose, mood and symptom check-ins, today's checks, when to involve the flight surgeon |
| **Alert centre** (`/alerts`) | Acknowledge and resolve alerts (resolution notes are required); see explanations and correlations |
| **Situational awareness** (`/timeline`) | Filter events by crew member, category and time |
| **Mission simulation** (`/simulation`) | Run whole missions in the isolated sandbox (speed, pause, presets, injections, playback) |
| **Guided demo** (`/demo`) | Run the twelve-step demonstration in the sandbox with automatic step tracking |
| **AI intelligence** (`/intelligence`) | Anomaly timeline, forecasts with 90 % intervals, risk and explanations |
| **Digital twin** (`/twin`) | Daily health record, baselines against current values, trends, mission stages |
| **AI medical assistant** (`/assistant`) | Ask about the data; every statement cites a record or document |
| **Incident reports** (`/reports`) | Create, review and export sealed reports (PDF) |
| **Space environment** (`/space/...`, `/radiation`) | Real NASA space weather, ISS environment and dose context |

## Recording a self-check

1. Open **Crew self-check** and pick the crew member.
2. Enter any of the following:
   - **Blood glucose:** the value in mg/dL, and whether it was taken fasting, after a meal or at
     random.
   - **Mood:** a rating from 1 to 5.
   - **Symptoms:** tick what applies, or choose "Nothing today".
   - **Note:** anything else worth recording.
3. Select **Record self-check**.

The body map and the cards update with a plain-language status:

- **Within your usual range:** no action needed.
- **Needs attention:** follow the guidance shown.
- **Tell the flight surgeon:** contact them, as the card says.

Glucose bands follow the ADA reference ranges; mood is compared with your own earlier check-ins.

## Reading statuses

- **Colours always come with words.** Green means usual, amber means needs attention, red means
  involve the flight surgeon, grey means no data.
- **Data labels.** Every value is labelled simulated, self-reported, measured (NASA), indicator,
  estimate or model output. A NASA flare is never a dose.
- **Experimental AI findings** are capped below "critical" and say so.

## Getting help

The [demo script](competition/DEMO_SCRIPT.md) walks through every area in order. Known limitations:
[LIMITATIONS.md](LIMITATIONS.md).
