"""Lay out an incident report snapshot as a PDF."""

from __future__ import annotations

from typing import Any

from app.reports.pdf import PdfDocument
from app.reports.service import STATUS_LABELS
from app.twin.summary import LABELS


def _fmt(v: Any, unit: str = "") -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        v = f"{v:.2f}".rstrip("0").rstrip(".")
    return f"{v} {unit}".strip()


def _ts(v: Any) -> str:
    return str(v).replace("T", " ")[:19] + " UTC" if v else "-"


def render_report(view: dict[str, Any]) -> bytes:
    c = view["content"]
    doc = PdfDocument(f"ASTRA-MED incident report {view['id']}",
                      f"ASTRA-MED - SIMULATED DATA, not clinically validated - report {view['id']} - "
                      f"SHA-256 {view['content_sha256'][:16]}")
    doc.text(50, doc.y - 18, "ASTRA-MED incident report", 18, True, (0.08, 0.2, 0.38))
    doc.y -= 26
    doc.paragraph(view["title"], 12, True)
    doc.banner("SIMULATED DATA. The crew member is fictional and every measurement comes from the ASTRA-MED "
               "simulator. Decision support only: not a diagnosis and not clinically validated.")

    doc.heading("1. Mission information")
    m = c["mission"]
    doc.key_values([("Mission", f"{m['name']} ({m['phase']})"), ("Mission start", str(m["mission_start"])),
                    ("Mission day", f"{m['mission_day']} - {m['stage']}")])

    doc.heading("2. Astronaut")
    a = c["astronaut"]
    doc.key_values([("Crew member", f"{a['name']} ({a['id']}) - fictional"), ("Role", a["role"]),
                    ("Age / sex", f"{a['age']} / {a['sex']}")])

    doc.heading("3. Timestamp")
    t = c["timestamp"]
    doc.key_values([("Event time", _ts(t["occurred_at"])), ("Report created", _ts(t["report_created_at"])),
                    ("Created by", view["created_by"]), ("Source", ", ".join(
                        f"{k} {v}" for k, v in (("alert", c["source"]["alert_id"]), ("run", c["source"]["run_id"])) if v)
                     or "manual")])
    if c.get("summary"):
        doc.paragraph(c["summary"])
    obs = c.get("observation")
    if obs and obs.get("simulated_test_scenario"):
        doc.banner(f"Simulated test scenario running at the time: {obs['simulated_test_scenario']}. "
                   "The deviation was injected by the simulator.", (0.75, 0.45, 0.05), 9)

    doc.heading("4. Measurements")
    meas = c["measurements"]
    if "trigger_value" in meas:
        doc.key_values([
            ("Signal", f"{meas['label']} ({meas['unit']})"), ("Value at trigger", _fmt(meas["trigger_value"], meas["unit"])),
            ("Peak value", _fmt(meas["peak_value"], meas["unit"])),
            ("Prototype alert limit", _fmt(meas["alert_limit"], meas["unit"])),
            ("Note", meas.get("alert_limit_note") or "-"),
        ])
        series = [p for p in meas.get("series", []) if any(p.get(k) is not None for k in ("heart_rate", "spo2"))]
        if series:
            rows = [[_ts(p["ts"])[11:16], _fmt(p.get("heart_rate")), _fmt(p.get("spo2")), _fmt(p.get("respiratory_rate")),
                     _fmt(p.get("temperature_c")), f"{_fmt(p.get('systolic'))}/{_fmt(p.get('diastolic'))}"]
                    for p in series[:: max(1, len(series) // 16)]]
            doc.paragraph("One-minute means around the event (simulated):", 9, True)
            doc.table(["Time (UTC)", "HR bpm", "SpO2 %", "RR br/min", "Temp °C", "BP mmHg"], rows, [70, 60, 60, 70, 60, 80])
    else:
        rows = [[LABELS.get(k, k), _fmt(v.get("mean")), _fmt(v.get("min")), _fmt(v.get("max")), str(v.get("n"))]
                for k, v in (meas.get("summary") or {}).items()]
        doc.table(["Signal", "Mean", "Min", "Max", "Samples"], rows, [140, 70, 70, 70, 60])

    doc.heading("5. Baseline comparison")
    bc = c["baseline_comparison"]
    if bc.get("contributors"):
        rows = [[x["label"], _fmt(x.get("value"), x.get("unit", "")), _fmt(x.get("baseline"), x.get("unit", "")),
                 _fmt(x.get("z")), _fmt(x.get("percentile")), f"{round(100 * (x.get('share') or 0))}%"]
                for x in bc["contributors"]]
        doc.table(["Signal", "Value", "Personal baseline", "z", "Percentile", "Share"], rows, [110, 70, 90, 45, 60, 50])
        if bc.get("significance"):
            doc.paragraph(f"Significance: {bc['significance'].get('description')} (max |z| {bc['significance'].get('max_abs_z')}).")
        doc.paragraph(bc.get("method") or "", 8.5)
    elif bc.get("features"):
        rows = [[f["label"], _fmt(f["value"], f["unit"]), _fmt(f["reference"], f["unit"]), _fmt(f["z"]), f["status"]]
                for f in bc["features"] if f["status"] != "info"]
        doc.table(["Input", "Value", "Reference", "z", "Status"], rows, [150, 80, 80, 45, 90])
    else:
        doc.paragraph("No baseline comparison was available.")

    doc.heading("6. Environmental conditions")
    env = c.get("environment") or {}
    rows = []
    if env.get("activity_state"):
        rows.append(("Activity at the time", env["activity_state"]))
    if env.get("mission_stage"):
        rows.append(("Mission stage", env["mission_stage"]))
    rows.append(("Simulated test scenario", env.get("simulated_test_scenario") or "none"))
    hab = env.get("habitat")
    if hab:
        rows.append(("Simulated habitat", "; ".join(f"{p['label']} {p['value']} {p['unit']}" for p in hab["parameters"].values())))
    doc.key_values(rows)
    sw = (env.get("space_weather") or {}).get("events") or []
    if sw:
        doc.paragraph("Real NASA DONKI events within 24 h (context only, never converted into dose):", 9, True)
        doc.table(["Event", "Start (UTC)", "Detail", "Offset h"],
                  [[e.get("title"), _ts(e.get("start")), e.get("detail") or "-", _fmt(e.get("offset_hours"))]
                   for e in sw[:8]], [130, 120, 150, 60])
    else:
        doc.paragraph("No NASA DONKI events recorded within 24 h of the event time.", 9)

    doc.heading("7. Anomaly-detection results")
    ar = c["anomaly_results"]
    ai = ar.get("ai_output") or {}
    if ai.get("available"):
        peak = ai.get("anomaly_peak") or {}
        doc.key_values([("Pattern kind", str(ai.get("kind"))),
                        ("Flagged windows", f"{ai.get('flagged_windows')} of {ai.get('windows')} (5-minute windows)"),
                        ("Peak ensemble score", f"{_fmt(peak.get('ensemble_score'))} x threshold, {peak.get('votes')} detectors")])
    ms = ar["multisystem"]
    doc.paragraph(f"Multisystem assessment at report time: {ms['summary']}")
    doc.table(["System", "Status", "Explanation"], [[s["label"], s["status"].replace("_", " "), s["explanation"]]
                                                     for s in ms["systems"]], [100, 80, 300])
    if ms.get("patterns"):
        doc.paragraph("Cross-system co-deviations (co-occurrence, not cause):", 9, True)
        doc.bullets([f"{p['label']}: {' '.join(p['evidence'])}" for p in ms["patterns"]])

    doc.heading("8. Model explanation")
    me = c["model_explanation"]
    doc.key_values([("Alert rule", me.get("rule") or "-"), ("What changed", me.get("what_changed") or "-"),
                    ("Model version", me.get("model_version") or "-"),
                    ("Confidence", "-" if not me.get("confidence") else
                     f"{me['confidence'].get('level')} ({me['confidence'].get('score')}): " + "; ".join(me["confidence"].get("basis", [])))])
    if me.get("uncertainty"):
        doc.paragraph("Sources of uncertainty:", 9, True)
        doc.bullets(me["uncertainty"])

    doc.heading("9. Data-quality limitations")
    dq = c["data_quality"]
    pk = dq.get("packet") or {}
    if pk:
        doc.key_values([("Samples in window", str(pk.get("samples"))), ("Completeness", _fmt(pk.get("completeness"))),
                        ("Largest gap", _fmt(pk.get("largest_gap_s"), "s"))])
    doc.bullets([*((dq.get("multisystem") or {}).get("notes") or []), *pk.get("notes", []), *dq["limitations"]])

    doc.heading("10. Review status")
    doc.key_values([("Current status", STATUS_LABELS.get(view["review_status"], view["review_status"])),
                    ("Snapshot integrity", f"{view['integrity']} (SHA-256 {view['content_sha256']})")])
    doc.table(["When (UTC)", "By", "Change", "Note"],
              [[_ts(h["ts"]), f"{h['by']} ({h['role']})", f"{h.get('from') or '-'} -> {h['to']}", h.get("note") or "-"]
               for h in view["review_history"]], [110, 120, 110, 160])
    rw = c.get("review_workflow")
    if rw:
        doc.paragraph(f"Recommended review: {rw['escalation']['label']} - {rw['escalation']['who']}.", 9.5, True)
        doc.bullets([f"{s['label']} ({s['role_label']})" for s in rw["steps"]])
        doc.paragraph(rw["note"], 8.5)
    doc.paragraph(c["disclaimer"], 8.5, rgb=(0.4, 0.1, 0.1))
    return doc.render()
