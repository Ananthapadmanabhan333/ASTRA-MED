"""Live end-to-end check of the unified mission workflow against a running ASTRA-MED API.

    python scripts/e2e_mission.py                       # http://127.0.0.1:8000, user "operator"
    python scripts/e2e_mission.py --base http://host:8000 --user operator --keep

The password is read from ASTRA_E2E_PASSWORD or, for local demo accounts, from backend/.dev-users.json
(created by scripts/create_users.py dev). It is never printed. The script signs in with a bearer
token, listens on the live WebSocket, and walks the eleven workflow steps:

 1 start a simulated mission           2 generate physiological data    3 send measurements to the backend
 4 run anomaly detection               5 generate predictive analysis   6 retrieve NASA environmental information
 7 correlate relevant mission events   8 generate an alert              9 display it in mission control
10 open the astronaut digital twin    11 generate an incident report

Everything runs in the mission simulation sandbox, so the live crew stream is not touched. The run is
reset at the end unless --keep is given. Exit code 0 means every step passed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]


class Step:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, float]] = []

    def record(self, name: str, ok: bool, detail: str, started: float) -> None:
        self.rows.append((name, "PASS" if ok else "FAIL", detail, time.perf_counter() - started))
        print(f"{'PASS' if ok else 'FAIL'}  {name:<42} {detail}  ({time.perf_counter() - started:.1f} s)", flush=True)

    @property
    def ok(self) -> bool:
        return all(r[1] == "PASS" for r in self.rows)


def password_for(user: str) -> str:
    if os.environ.get("ASTRA_E2E_PASSWORD"):
        return os.environ["ASTRA_E2E_PASSWORD"]
    path = ROOT / ".dev-users.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if user in data:
            return data[user]["password"]
    sys.exit("Set ASTRA_E2E_PASSWORD or create demo accounts with scripts/create_users.py dev.")


async def listen(url: str, token: str, sink: list[dict], stop: asyncio.Event) -> None:
    async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {token}"}, max_size=None) as ws:
        while not stop.is_set():
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 1.0))
            except TimeoutError:
                continue
            if msg.get("type") in ("mission_event", "mission_alert", "sim_state", "hello"):
                sink.append(msg)


async def main(args: argparse.Namespace) -> int:
    steps = Step()
    base = args.base.rstrip("/")
    async with httpx.AsyncClient(base_url=base, timeout=180) as c:
        t = time.perf_counter()
        r = await c.get("/api/system/health")
        steps.record("API reachable", r.status_code == 200, f"status {r.json().get('status')}", t)
        r = await c.post("/api/auth/token", json={"username": args.user, "password": password_for(args.user)})
        if r.status_code != 200:
            print(f"Sign-in failed: {r.status_code} {r.text[:200]}")
            return 2
        token = r.json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"

        ws_url = base.replace("http", "ws", 1) + "/ws/health-monitoring"
        received: list[dict] = []
        stop = asyncio.Event()
        listener = asyncio.create_task(listen(ws_url, token, received, stop))

        try:
            state = (await c.get("/api/mission-sim/state")).json()
            if state.get("active"):
                await c.post(f"/api/mission-sim/runs/{state['id']}/reset")

            # 1 Start a simulated mission.
            t = time.perf_counter()
            r = await c.post("/api/mission-sim/runs", json={"preset": "desaturation_emergency", "speed": args.speed,
                                                            "name": "Live end-to-end check"})
            ok = r.status_code == 201
            sim = r.json() if ok else {}
            rid, crew = sim.get("id"), sim.get("crew", [])
            steps.record("1 Start a simulated mission", ok, f"run {rid}, crew {crew}, {args.speed}x" if ok else r.text[:120], t)
            if not ok:
                return 1

            # 2 Generate physiological data (wait for 20 simulated minutes).
            t = time.perf_counter()
            while True:
                state = (await c.get("/api/mission-sim/state")).json()
                elapsed = (datetime.fromisoformat(state["sim_time"]) - datetime.fromisoformat(state["sim_start"])).total_seconds()
                if elapsed >= 20 * 60 or time.perf_counter() - t > 240:
                    break
                await asyncio.sleep(2)
            samples = state["stats"].get("samples", 0)
            steps.record("2 Generate astronaut physiological data", elapsed >= 20 * 60 and samples > 0,
                         f"{state['t_plus']}, {samples} samples, latest {[(x['astronaut_id'], x['spo2']) for x in state['latest']]}", t)

            # 3 Send measurements to the backend.
            t = time.perf_counter()
            end = datetime.fromisoformat(state["sim_time"])
            readings = [{"astronaut_id": crew[1], "ts": (end - timedelta(seconds=10 * (5 - i))).isoformat(),
                         "spo2": 86.0, "heart_rate": 108} for i in range(6)]
            r = await c.post(f"/api/mission-sim/runs/{rid}/telemetry", json={"readings": readings, "source": "e2e"})
            ing = r.json()
            steps.record("3 Send measurements to the backend", r.status_code == 200 and ing["accepted"] == 6,
                         f"accepted {ing.get('accepted')}, rejected {ing.get('rejected')}, alerts opened {ing.get('alerts_opened')}", t)

            # 4 + 5 Anomaly detection and predictive analysis on the stream.
            t = time.perf_counter()
            r = await c.post(f"/api/mission-sim/runs/{rid}/analyze")
            ana = r.json() if r.status_code == 200 else {}
            a = ana.get(crew[0], {})
            steps.record("4 Run anomaly detection", r.status_code == 200 and a.get("available") and a.get("windows", 0) > 0,
                         f"{crew[0]}: {a.get('flagged_windows')} of {a.get('windows')} windows flagged, "
                         f"{len(a.get('detections') or [])} detection(s)" if a else r.text[:160], t)
            fc = a.get("forecast") or []
            h6 = [f"{s['signal']} {next(h['value'] for h in s['horizons'] if h['horizon_h'] == 6)}" for s in fc]
            steps.record("5 Generate predictive analysis", bool(fc) and a.get("risk") is not None,
                         f"risk {a.get('risk', {}).get('risk_score')}/100 {a.get('risk', {}).get('category')}; 6 h: {', '.join(h6)}", t)

            # 6 Retrieve NASA environmental information.
            t = time.perf_counter()
            ws_ = await c.get("/api/space/weather/summary", params={"days": 30})
            fresh = ws_.json().get("freshness", {}) if ws_.status_code == 200 else {}
            counts = ws_.json().get("counts", {}) if ws_.status_code == 200 else {}
            steps.record("6 Retrieve NASA environmental information", ws_.status_code == 200,
                         f"DONKI 30 d: {sum(counts.values())} events, mode {fresh.get('mode')}", t)

            # 7 + 8 An alert with correlated context.
            t = time.perf_counter()
            alerts = (await c.get("/api/alert-center", params={"context": "simulation", "simulation_id": rid})).json()
            rule = next((x for x in alerts if x["source"] == "physiological_monitoring" and x["astronaut_id"] == crew[0]), None)
            steps.record("8 Generate an alert", rule is not None,
                         f"{len(alerts)} sandbox alert(s); {rule['title']} P{rule['priority']}" if rule else "no rule alert", t)
            t = time.perf_counter()
            detail = (await c.get(f"/api/alert-center/{rule['id']}")).json() if rule else {}
            corr = detail.get("correlations", {})
            sw = (corr.get("space_weather") or {}).get("events", [])
            steps.record("7 Correlate relevant mission events", bool(corr.get("injected_scenarios")),
                         f"injected: {[s['scenario'] for s in corr.get('injected_scenarios', [])]}, "
                         f"{len(sw)} NASA event(s) within {(corr.get('space_weather') or {}).get('window_hours')} h, "
                         f"{len(corr.get('related_events', []))} related event(s)", t)

            # 9 Display it in mission control (REST and live socket).
            t = time.perf_counter()
            o = (await c.get("/api/mission-control/overview")).json()
            sim_sum = (o["alerts"]["data"] or {}).get("simulation_summary") or {}
            ws_alerts = [m for m in received if m.get("type") == "mission_alert" and m["alert"].get("simulation_id") == rid]
            steps.record("9 Display it in mission control", o["simulation"].get("id") == rid and sim_sum.get("unresolved", 0) > 0
                         and len(ws_alerts) > 0,
                         f"dashboard: {sim_sum.get('unresolved')} unresolved sandbox alerts; socket delivered "
                         f"{len(ws_alerts)} sandbox alert message(s)", t)

            # 10 Open the astronaut digital twin.
            t = time.perf_counter()
            tw = await c.get(f"/api/twin/{crew[0]}")
            steps.record("10 Open the astronaut digital twin", tw.status_code == 200,
                         f"{tw.json()['astronaut']['name']}, mission day {tw.json()['mission']['day']}" if tw.status_code == 200 else tw.text[:120], t)

            # 11 Generate an incident report.
            t = time.perf_counter()
            rep = await c.post(f"/api/mission-sim/runs/{rid}/report", json={"alert_id": rule["id"] if rule else None})
            ok = rep.status_code == 201
            body = rep.json() if ok else {}
            pdf = await c.get(f"/api/reports/{body['id']}/pdf") if ok else None
            steps.record("11 Generate an incident report", ok and body.get("integrity") == "intact" and pdf is not None
                         and pdf.content[:4] == b"%PDF",
                         f"report {body.get('id')} ({body.get('review_status')}, {body.get('integrity')}), PDF {len(pdf.content) if pdf else 0} bytes", t)
        finally:
            if not args.keep and "rid" in locals() and rid:
                await c.post(f"/api/mission-sim/runs/{rid}/reset")
            stop.set()
            try:
                await asyncio.wait_for(listener, 5)
            except (TimeoutError, Exception):
                listener.cancel()

    print(f"\n{sum(1 for r in steps.rows if r[1] == 'PASS')} of {len(steps.rows)} checks passed.")
    return 0 if steps.ok else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument("--user", default="operator")
    p.add_argument("--speed", type=float, default=60)
    p.add_argument("--keep", action="store_true", help="leave the sandbox run in place for the dashboard")
    sys.exit(asyncio.run(main(p.parse_args())))
