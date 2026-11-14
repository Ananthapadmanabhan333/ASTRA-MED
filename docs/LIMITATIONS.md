# Known limitations

ASTRA-MED is a research prototype. This page collects every limitation the project knows of in one
place; each links to where it is discussed in detail.

## Data and science

| Limitation | Consequence | Detail |
| --- | --- | --- |
| All crew vital signs are simulated by a parametric model; the crew are fictional | No result says anything about real astronauts | [SCIENTIFIC_VALIDATION.md](SCIENTIFIC_VALIDATION.md) |
| Simulator, injected events and evaluation labels share one design | Detection is easier than in real monitoring | [SCIENTIFIC_VALIDATION.md §5](SCIENTIFIC_VALIDATION.md#5-limitations) |
| Planned activity equals actual activity in the simulator | Forecasts look better than they would with real timelines | same |
| No validation on real data, in analogue missions or in clinical use (tiers 2–4) | Not usable for medical decisions | [SCIENTIFIC_VALIDATION.md §1](SCIENTIFIC_VALIDATION.md#1-validation-tiers) |
| The ensemble is not reliably better than its best detector; neural forecasters do not beat XGBoost | Model complexity is not justified by accuracy on this data | [SCIENTIFIC_VALIDATION.md §3.4](SCIENTIFIC_VALIDATION.md) |
| Detection thresholds are calibrated on labelled simulated data | A real deployment needs clinician-reviewed calibration | [AI_ENGINE.md](AI_ENGINE.md) |
| DONKI space weather is observed from near Earth | Relevance to a spacecraft elsewhere is not modelled | [DATASETS.md](DATASETS.md) |
| EDA doses are experiment-location doses from historical ISS missions | Never a crew dose, never current conditions | [DATASETS.md](DATASETS.md) |
| The digital twin is a structured record, not a physiological simulation | No organ-level or biological state is modelled | [MEDICAL_DECISION_SUPPORT.md](MEDICAL_DECISION_SUPPORT.md) |
| Self-check glucose bands come from ADA criteria for laboratory plasma glucose in non-pregnant adults | Orientation only; finger-stick meters and microgravity physiology may differ | `backend/app/selfcheck/service.py` |
| The medical assistant has no approved aerospace-medicine reference library and declines diagnosis and treatment | It summarises data and documentation only | [MEDICAL_DECISION_SUPPORT.md](MEDICAL_DECISION_SUPPORT.md) |

## Product scope

- **No treatment guidance.** The challenge asks for guidance on treatments. ASTRA-MED deliberately
  gives process guidance only ("tell the flight surgeon") because it has no approved procedures.
- **Self-check is a first version:** glucose, mood and symptoms entered by hand. There is no camera
  input, no gamification and no device integration.
- **Single process.** One API process and one database: the simulator, live stream, collectors and
  sandbox cannot be scaled out.
- **Guided demo runs in the sandbox.** Its "twin snapshot" is separate from the operational digital
  twin.

## Engineering and operations

- **Untested images.** Docker images and Docker Compose were never run on the development machine.
- **Not deployed.** Render and Vercel configurations exist; no public deployment has been made.
- **Open audit items.** 5 medium and 15 low findings remain open ([PHASE7_AUDIT.md](PHASE7_AUDIT.md)),
  among them the OSDR live-search permission, the unbounded audit rows from rejected sockets and the
  legacy alert-resolve path.
- **Security gaps.** No multi-factor authentication, no row-level (per crew member) access, and an
  audit log without tamper-evidence ([SECURITY.md](SECURITY.md)).
- **Dependencies.** Pinned by version (`constraints.txt`), not by hash; CSP still allows inline
  scripts for Next.js.
- **UI verification.** No automated browser end-to-end tests. Signed-in UI checks after the phase 7
  and 8 frontend changes depend on a manual sign-in.
