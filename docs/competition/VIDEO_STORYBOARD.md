# 30-second demo video storyboard

**Official limits:**

- **Length:** the video may be **30 seconds or less**; longer videos are not eligible for global
  judging.
- **Language:** English, or English subtitles.
- **Hosting:** on an external site (for example YouTube or Google Drive) with a public link.
- **Minors:** no one under 18 may appear or be heard.

The timing follows the organisers' suggested structure from the Project Submission Guide:
introduction, then the challenge, then the name, then the idea, then the future.

**Recording:**

- Use the local stack (`backend-postgres` and `frontend` launch configurations), signed in as a demo
  operator.
- Start `python scripts/demo_phase7.py --keep` about one minute before recording, so a fresh alert
  and report exist.
- Keep the "simulated data" marker on screen whenever crew values are visible.
- Every screen in the video is a screen recording of the real application. No AI-generated imagery
  is planned; if any is used, it needs a visible "SI-generated" watermark.

| Time | Screen | Narration / caption (≈ 75 words in total) |
| --- | --- | --- |
| 0:00–0:02 | Team name over the dashboard header | "We're team [name]." |
| 0:02–0:05 | Challenge title card, then the NASA HRP hazards line | "On missions to Mars, astronauts will have to catch health problems themselves." |
| 0:05–0:10 | ASTRA-MED title over the dashboard; tagline | "ASTRA-MED learns each crew member's own normal and explains every alert." |
| 0:10–0:14 | Live vitals; SpO₂ trending down; an alert appears in mission control | "Here a simulated desaturation develops. ASTRA-MED flags it…" |
| 0:14–0:17 | Alert detail: measurements, personal baseline, contributing signals, confidence | "…shows why, against her own baseline…" |
| 0:17–0:20 | Space-weather panel: NASA DONKI events near the alert | "…and checks real NASA space-weather data around it." |
| 0:20–0:24 | Assistant answer with citations; incident report PDF | "A cited assistant summarises the evidence, and a report is ready for the flight surgeon." |
| 0:24–0:30 | Roadmap card: analogue validation, crew self-check, open source; repository URL | "Next: validation on analogue missions. Open source, so anyone can build on it." |

**On-screen footer throughout:** "Research prototype. Simulated crew data. Not a medical device. NASA
data: DONKI, OSDR."

**Checks before uploading:**

- Running time ≤ 0:30.
- English subtitles, if the narration is not in English.
- No people under 18 shown or heard.
- The link opens in a private browser window without a login.
