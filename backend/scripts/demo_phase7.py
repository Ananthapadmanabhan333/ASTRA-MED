"""Final demonstration: the ten-step scenario from the phase 7 brief, against a running ASTRA-MED API.

    python scripts/demo_phase7.py                      # http://127.0.0.1:8000, demo user "operator"
    python scripts/demo_phase7.py --transcript ../docs/demo/demo-run.md --keep

A simulated crew member (AST-01) is on a long-duration mission. The script never writes to the
database directly and never fabricates readings: it starts one of the simulator's documented
**test scenarios** (a developing desaturation) through the public API, and everything after that is
produced by ASTRA-MED's own pipeline. Every measurement involved is simulated and is labelled so.

 1 physiological data enters ASTRA-MED            6 environmental context is investigated
 2 the monitoring engine detects the deviation    7 an explainable alert is produced
 3 the AI engine analyses the measurements        8 the medical assistant summarises the evidence
 4 the digital twin updates                       9 mission control displays the incident
 5 space environment data is retrieved           10 a structured incident report is generated

The password comes from ASTRA_E2E_PASSWORD or backend/.dev-users.json and is never printed. With
--sync the NASA DONKI synchronisation for the last 3 days is triggered first (network access to
NASA's public CCMC service; skipped gracefully when offline). The scenario is cancelled and the
alert resolved at the end unless --keep is given (keep it to walk through the dashboard).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
AID = "AST-01"


def password_for(user: str) -> str:
    if os.environ.get("ASTRA_E2E_PASSWORD"):
        return os.environ["ASTRA_E2E_PASSWORD"]
    path = ROOT / ".dev-users.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if user in data:
            return data[user]["password"]
    sys.exit("Set ASTRA_E2E_PASSWORD or create demo accounts with scripts/create_users.py dev.")


class Transcript:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str, float]] = []
        self.started = datetime.now(UTC)

    def step(self, name: str, ok: bool, detail: str, t0: float) -> None:
        dt = time.perf_counter() - t0
        self.rows.append((name, ok, detail, dt))
        print(f"{'PASS' if ok else 'FAIL'}  {name:<46} {detail}  ({dt:.1f} s)", flush=True)

    @property
    def ok(self) -> bool:
        return all(r[1] for r in self.rows)

    def markdown(self, base: str) -> str:
        lines = [
            "# Demonstration run (phase 7 scenario)",
            "",
            "> All crew measurements are **simulated** by the ASTRA-MED simulator; the deviation is a "
            "documented software test scenario, not a medical event. NASA space-weather records are real "
            "public data and are context only. Nothing here is a diagnosis.",
            "",
            f"Run at {self.started.isoformat(timespec='seconds')} against `{base}` with "
            "`backend/scripts/demo_phase7.py`. Result: "
            f"**{'all steps passed' if self.ok else 'some steps failed'}**.",
            "",
            "| Step | Result | What the system produced | Time |",
            "| --- | --- | --- | --- |",
        ]
        for name, ok, detail, dt in self.rows:
            lines.append(f"| {name} | {'pass' if ok else 'FAIL'} | {detail.replace('|', '/')} | {dt:.1f} s |")
        return "\n".join(lines) + "\n"


async def listen(url: str, token: str, sink: list[dict], stop: asyncio.Event) -> None:
    async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {token}"}, max_size=None) as ws:
        while not stop.is_set():
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 1.0))
            except TimeoutError:
                continue
            sink.append(msg)


def _vitals(msgs: list[dict]) -> list[dict]:
    out = []
    for m in msgs:
        if m.get("type") == "vitals":
            for r in m.get("readings", []) or [m.get("reading", {})]:
                if r and r.get("astronaut_id") == AID:
                    out.append(r)
    return out


async def main(args) -> int:
    tr = Transcript()
    base = args.base.rstrip("/")
    async with httpx.AsyncClient(base_url=base, timeout=180) as c:
        r = await c.post("/api/auth/token", json={"username": args.user, "password": password_for(args.user)})
        if r.status_code != 200:
            print(f"Sign-in failed: {r.status_code}")
            return 2
        token = r.json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"
        msgs: list[dict] = []
        stop = asyncio.Event()
        listener = asyncio.create_task(listen(base.replace("http", "ws", 1) + "/ws/health-monitoring", token, msgs, stop))
        scenario_id = alert_id = None
        open_ = (await c.get("/api/alerts", params={"status": ["active", "acknowledged"], "astronaut_id": AID})).json()
        if any(a["metric"] == "spo2" for a in open_):
            print(f"{AID} already has an open SpO2 alert; resolve it once SpO2 has recovered, then run the demo again.")
            stop.set()
            listener.cancel()
            return 3
        try:
            # 1 Physiological data enters ASTRA-MED (simulated vitals, then a developing desaturation).
            t = time.perf_counter()
            await asyncio.sleep(3)
            before = _vitals(msgs)
            scenario_start = datetime.now(UTC) - timedelta(seconds=5)
            r = await c.post("/api/simulation/events", json={"scenario": "desaturation", "astronaut_id": AID,
                                                             "intensity": args.intensity, "duration_seconds": 900})
            scenario_id = r.json().get("id") if r.status_code == 201 else None
            ok = r.status_code == 201 and bool(before)
            src = {v.get("data_source") for v in before}
            tr.step("1 Physiological data enters ASTRA-MED", ok,
                    f"{len(before)} live {AID} readings in 3 s (data_source {sorted(src)}); test scenario "
                    f"'desaturation' started ({scenario_id})", t)

            # 2 The monitoring engine detects the developing deviation (rule alert over the socket).
            t = time.perf_counter()
            alert = None
            while time.perf_counter() - t < args.timeout:
                for m in msgs:
                    a_ = m.get("alert") or {}
                    if m.get("type") == "alert" and a_.get("astronaut_id") == AID and a_.get("metric") == "spo2" \
                            and a_.get("status") == "active" \
                            and datetime.fromisoformat(a_["opened_at"]) >= scenario_start:
                        alert = a_
                if alert:
                    break
                await asyncio.sleep(1)
            spo2 = [round(v["spo2"], 1) for v in _vitals(msgs) if v.get("spo2") is not None]
            alert_id = alert.get("id") if alert else None
            tr.step("2 Monitoring engine detects the deviation", bool(alert),
                    (f"rule alert {alert_id}: {alert.get('title')} ({alert.get('severity')}); SpO2 trend "
                     f"{spo2[0]} -> {min(spo2)} %" if alert else "no SpO2 alert within the time limit"), t)
            if not alert:
                return 1

            # 3 The AI engine analyses the measurements.
            t = time.perf_counter()
            now = datetime.now(UTC)
            det = await c.post("/api/ai/anomaly-detection", json={"astronaut_id": AID,
                                                                  "start": (now - timedelta(hours=1)).isoformat()})
            risk = await c.get(f"/api/ai/astronaut/{AID}/risk-assessment")
            d, rk = det.json() if det.status_code == 200 else {}, risk.json() if risk.status_code == 200 else {}
            flagged = sum(p["flagged"] for p in d.get("timeline", []))
            tr.step("3 AI engine analyses the measurements", det.status_code == 200 and risk.status_code == 200,
                    f"model {d.get('model_version')}: {flagged} of {len(d.get('timeline', []))} windows flagged in the "
                    f"last hour; risk {rk.get('risk_score')}/100 ({rk.get('category')}), top warning: "
                    f"{(rk.get('warnings') or [{}])[0].get('title')}", t)

            # 4 The digital twin updates.
            t = time.perf_counter()
            tw = await c.get(f"/api/twin/{AID}")
            twin = tw.json() if tw.status_code == 200 else {}
            cur = twin.get("current") or {}
            fresh = twin.get("last_measurement_at") and \
                datetime.fromisoformat(twin["last_measurement_at"]) > now - timedelta(minutes=2)
            tr.step("4 Digital twin updates", tw.status_code == 200 and bool(fresh),
                    f"last measurement {twin.get('last_measurement_at')}, twin updated {twin.get('twin_updated_at')}; "
                    f"current keys {sorted(cur)[:6]}", t)

            # 5 Space environment data is retrieved (optionally a fresh DONKI sync from NASA CCMC).
            t = time.perf_counter()
            sync_note = "sync skipped"
            if args.sync:
                s = await c.post("/api/space/sync", json={"source": "donki", "days": 3})
                sync_note = f"DONKI sync HTTP {s.status_code}"
            sw = await c.get("/api/space/weather/summary", params={"days": 30})
            rad = await c.get("/api/space/radiation", params={"days": 30})
            swj = sw.json() if sw.status_code == 200 else {}
            tr.step("5 Space environment data is retrieved", sw.status_code == 200 and rad.status_code == 200,
                    f"{sync_note}; 30-day NASA DONKI summary keys {sorted(swj)[:5]}; radiation view HTTP {rad.status_code}", t)

            # 6 The system investigates relevant environmental context.
            t = time.perf_counter()
            near = await c.get("/api/space/timeline/nearby", params={"ts": alert["opened_at"], "window_hours": 48})
            nj = near.json() if near.status_code == 200 else {}
            items = nj.get("events") or nj.get("items") or []
            tr.step("6 Environmental context is investigated", near.status_code == 200,
                    f"{len(items)} NASA space-weather record(s) within ±48 h of the alert (indicators only, "
                    "never converted into a dose)", t)

            # 7 An explainable alert is produced (rule + AI context, mirrored into the alert centre).
            t = time.perf_counter()
            ex = await c.get(f"/api/ai/explanations/{alert_id}")
            ac = None
            for _ in range(15):
                lst = (await c.get("/api/alert-center", params={"astronaut_id": AID, "context": "operations"})).json()
                ac = next((a for a in lst if a.get("source_ref") == alert_id), None)
                if ac:
                    break
                await asyncio.sleep(1)
            exj = ex.json() if ex.status_code == 200 else {}
            contrib = [c_["signal"] for c_ in ((exj.get("explanation") or {}).get("contributors") or [])][:3]
            tr.step("7 Explainable alert", ex.status_code == 200 and ac is not None,
                    f"rule '{exj.get('rule')}', contributors "
                    f"{contrib}; alert centre {ac.get('id') if ac else None} priority {ac.get('priority_label') if ac else None}, "
                    f"classification {ac.get('classification_label') if ac else None}", t)

            # 8 The medical assistant summarises the available evidence (cited, decision support only).
            t = time.perf_counter()
            q = (f"Summarise the evidence for the current oxygen saturation alert for {AID}: recent measurements, "
                 "baseline comparison and any space weather around it.")
            ans = await c.post("/api/assistant/ask", json={"question": q, "astronaut_id": AID})
            aj = ans.json() if ans.status_code == 200 else {}
            cited = sum(1 for s_ in aj.get("statements", []) if s_.get("citations"))
            tr.step("8 Medical assistant summarises the evidence", ans.status_code == 200 and cited > 0,
                    f"{len(aj.get('statements', []))} statement(s), {cited} with citations, {len(aj.get('sources', []))} "
                    f"source(s), declined={aj.get('declined')}, mode {aj.get('mode')}", t)

            # 9 Mission control displays the incident.
            t = time.perf_counter()
            ov = (await c.get("/api/mission-control/overview")).json()
            shown = alert_id in json.dumps(ov) or (ac and ac["id"] in json.dumps(ov))
            ws_alert = any(m.get("type") == "mission_alert" and (m.get("alert") or {}).get("source_ref") == alert_id
                           for m in msgs)
            tr.step("9 Mission control displays the incident", bool(shown) and ws_alert,
                    f"in the mission-control overview: {bool(shown)}; pushed live to the dashboard: {ws_alert}", t)

            # 10 A structured incident report is generated.
            t = time.perf_counter()
            rep = await c.post("/api/reports", json={"alert_id": alert_id})
            rj = rep.json() if rep.status_code in (200, 201) else {}
            pdf = await c.get(f"/api/reports/{rj.get('id')}/pdf") if rj.get("id") else None
            ok = rep.status_code in (200, 201) and rj.get("integrity") == "intact" and pdf is not None \
                and pdf.content[:4] == b"%PDF"
            tr.step("10 Structured incident report", ok,
                    f"report {rj.get('id')} '{rj.get('title')}' ({rj.get('review_status')}, integrity {rj.get('integrity')}, "
                    f"sha256 {str(rj.get('content_sha256'))[:12]}...), PDF {len(pdf.content) if pdf else 0} bytes", t)
        finally:
            if not args.keep:
                if scenario_id:
                    await c.delete(f"/api/simulation/events/{scenario_id}")
                if alert_id:
                    await c.post(f"/api/alerts/{alert_id}/resolve")
            stop.set()
            listener.cancel()
    if args.transcript:
        Path(args.transcript).parent.mkdir(parents=True, exist_ok=True)
        Path(args.transcript).write_text(tr.markdown(base), encoding="utf-8", newline="\n")
    print("\nAll ten steps passed." if tr.ok else "\nSome steps failed.")
    return 0 if tr.ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="operator")
    ap.add_argument("--intensity", type=float, default=1.3)
    ap.add_argument("--timeout", type=float, default=240)
    ap.add_argument("--sync", action="store_true", help="trigger a 3-day NASA DONKI sync first (network)")
    ap.add_argument("--keep", action="store_true", help="leave the scenario and alert in place for a walkthrough")
    ap.add_argument("--transcript", default="")
    sys.exit(asyncio.run(main(ap.parse_args())))
