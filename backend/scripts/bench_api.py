"""API, database and WebSocket benchmark against a running ASTRA-MED API.

    # 1. Start the API on a separate benchmark database (.claude/launch.json "backend-bench"); its
    #    start-up creates the schema and the crew. 2. Fill it with load-test rows (never the demo database):
    python scripts/bench_api.py seed --db-url postgresql+asyncpg://postgres@127.0.0.1:PORT/astra_med_bench --days 7
    python scripts/bench_api.py seed --db-url ... --days 22 --end-offset-days 7
    # 3. Measure:
    python scripts/bench_api.py run --base http://127.0.0.1:8010 \
        --db-url postgresql+asyncpg://postgres@127.0.0.1:PORT/astra_med_bench --label before \
        --out ../docs/benchmarks/api-before.json

The seeded rows are synthetic load-test values (a smooth daily pattern plus noise) at the live
store's 5-second cadence. They exist only to give the database a realistic volume; they are not the
physiology simulator's output and must not be presented as crew data.

``run`` signs in with a temporary benchmark account it creates directly in the database (random
password kept in memory only), then measures:
  - sequential latency of representative endpoints (p50/p95/max),
  - throughput and latency under concurrent load,
  - WebSocket fan-out: many simultaneous clients on the live stream for a fixed time,
  - the PostgreSQL plan of the main history query (index use).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
import secrets
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

ENDPOINTS = [
    ("system health", "GET", "/api/system/health"),
    ("crew list", "GET", "/api/astronauts"),
    ("live snapshot", "GET", "/api/health/AST-01"),
    ("history 1h", "GET", "/api/health/AST-01/history?range=1h"),
    ("history 24h", "GET", "/api/health/AST-01/history?range=24h"),
    ("history 7d", "GET", "/api/health/AST-01/history?range=7d"),
    ("crew comparison 7d", "GET", "/api/health/compare?metric=heart_rate&range=7d"),
    ("mission control overview", "GET", "/api/mission-control/overview"),
    ("crew monitoring", "GET", "/api/crew/monitoring"),
    ("alert centre", "GET", "/api/alert-center"),
    ("event history", "GET", "/api/events?hours=168"),
    ("situational timeline 24h", "GET", "/api/events/timeline?hours=24"),
    ("analytics 30d", "GET", "/api/analytics/summary"),
    ("space weather (stored NASA)", "GET", "/api/space/weather/events?days=30"),
    ("AI risk assessment", "GET", "/api/ai/astronaut/AST-01/risk-assessment"),
]


def _summary(ms: list[float]) -> dict:
    s = sorted(ms)

    def pct(p):
        k = (len(s) - 1) * p
        lo, hi = int(k), min(int(k) + 1, len(s) - 1)
        return s[lo] + (s[hi] - s[lo]) * (k - lo)

    return {"n": len(s), "p50_ms": round(pct(0.5), 1), "p95_ms": round(pct(0.95), 1),
            "max_ms": round(s[-1], 1), "mean_ms": round(statistics.fmean(s), 1)}


# --------------------------------------------------------------------------- seed ----
async def seed(db_url: str, days: int, interval_s: int, end_offset_days: float) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.db.session import create_schema
    from app.simulator.profiles import CREW

    engine = create_async_engine(db_url)
    await create_schema(engine)
    await engine.dispose()
    import asyncpg
    import numpy as np

    raw = await asyncpg.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        end = datetime.now(UTC).replace(microsecond=0) - timedelta(days=end_offset_days)
        start = end - timedelta(days=days)
        n = int((end - start).total_seconds() // interval_s)
        t = np.arange(n) * interval_s
        rng = np.random.default_rng(2026)
        total = 0
        for p in CREW:
            phase = 2 * math.pi * ((t / 86400.0) % 1.0)
            hr = 68 + 8 * np.sin(phase) + rng.normal(0, 2, n)
            rows = (
                (p.id, start + timedelta(seconds=int(ti)), float(h), float(97.5 + rng.normal(0, 0.4)),
                 118.0, 76.0, 36.7, 14.0, "work", 1.5, "sinus", None, None, "simulated")
                for ti, h in zip(t, hr)
            )
            await raw.copy_records_to_table(
                "vital_samples",
                records=list(rows),
                columns=["astronaut_id", "ts", "heart_rate", "spo2", "systolic", "diastolic", "temperature_c",
                         "respiratory_rate", "activity_state", "activity_met", "rhythm", "hrv_rmssd_ms", "scenario",
                         "data_source"],
            )
            total += n
            print(f"{p.id}: {n:,} rows", flush=True)
        await raw.execute("ANALYZE vital_samples")
        count = await raw.fetchval("SELECT count(*) FROM vital_samples")
        print(f"seeded {total:,} load-test rows; vital_samples now has {count:,} rows")
    finally:
        await raw.close()


# ---------------------------------------------------------------------------- run ----
async def _bench_account(db_url: str) -> tuple[str, str]:
    from app.core.config import Settings
    from app.db.session import create_engine, create_session_factory
    from app.security.service import AuthService

    username, password = f"bench-{secrets.token_hex(3)}", "Bx-" + secrets.token_urlsafe(18)
    engine = create_engine(db_url)
    try:
        auth = AuthService(Settings(database_url=db_url), create_session_factory(engine))
        await auth.create_user(username, "Benchmark (temporary)", "mission_operator", password)
    finally:
        await engine.dispose()
    return username, password


async def _login(client: httpx.AsyncClient, username: str, password: str) -> None:
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]


async def _sequential(client, reps: int) -> dict:
    out = {}
    for name, method, path in ENDPOINTS:
        times, status = [], None
        for _ in range(reps):
            t = time.perf_counter()
            r = await client.request(method, path)
            times.append((time.perf_counter() - t) * 1000)
            status = r.status_code
        out[name] = {"path": path, "status": status, **_summary(times)}
        print(f"  {name:28s} {status} p50 {out[name]['p50_ms']:8.1f} ms  p95 {out[name]['p95_ms']:8.1f} ms", flush=True)
    return out


async def _concurrent(base: str, cookies, headers, workers: int, per_worker: int) -> dict:
    paths = ["/api/mission-control/overview", "/api/crew/monitoring", "/api/alert-center",
             "/api/health/AST-02/history?range=24h", "/api/events?hours=24"]
    times: list[float] = []
    errors = 0

    async def worker(i: int):
        nonlocal errors
        async with httpx.AsyncClient(base_url=base, cookies=cookies, headers=headers, timeout=60) as c:
            for k in range(per_worker):
                t = time.perf_counter()
                try:
                    r = await c.get(paths[(i + k) % len(paths)])
                    if r.status_code >= 400:
                        errors += 1
                except httpx.HTTPError:
                    errors += 1
                times.append((time.perf_counter() - t) * 1000)

    started = time.perf_counter()
    await asyncio.gather(*(worker(i) for i in range(workers)))
    wall = time.perf_counter() - started
    return {"workers": workers, "requests": len(times), "errors": errors, "wall_s": round(wall, 2),
            "throughput_rps": round(len(times) / wall, 1), **_summary(times)}


async def _websockets(ws_url: str, cookie_header: str, origin: str, clients: int, seconds: float) -> dict:
    import websockets

    counts = [0] * clients
    gaps: list[float] = []
    failures = 0
    closed_early = 0

    async def one(i: int):
        nonlocal failures, closed_early
        try:
            async with websockets.connect(ws_url, additional_headers={"Cookie": cookie_header, "Origin": origin},
                                          open_timeout=20, max_size=2**22) as ws:
                last = None
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
                    except TimeoutError:
                        break
                    now = time.monotonic()
                    if last is not None and i == 0:
                        gaps.append((now - last) * 1000)
                    last = now
                    counts[i] += 1
        except websockets.ConnectionClosed:
            closed_early += 1
        except Exception:
            failures += 1

    await asyncio.gather(*(one(i) for i in range(clients)))
    received = [c for c in counts if c]
    return {
        "clients": clients, "seconds": seconds, "failed_to_connect": failures, "closed_early": closed_early,
        "messages_per_client_min": min(counts) if counts else 0,
        "messages_per_client_median": statistics.median(counts) if counts else 0,
        "messages_per_client_per_s": round(statistics.fmean(received) / seconds, 2) if received else 0,
        "client0_gap_p95_ms": _summary(gaps)["p95_ms"] if len(gaps) > 2 else None,
    }


async def _plan(db_url: str) -> list[str]:
    import asyncpg

    raw = await asyncpg.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        rows = await raw.fetch(
            "EXPLAIN ANALYZE SELECT ts, heart_rate FROM vital_samples "
            "WHERE astronaut_id = 'AST-01' AND ts >= now() - interval '7 days' ORDER BY ts")
        count = await raw.fetchval("SELECT count(*) FROM vital_samples")
        return [f"vital_samples rows: {count:,}"] + [r[0] for r in rows]
    finally:
        await raw.close()


async def run(args) -> dict:
    username, password = await _bench_account(args.db_url)
    out: dict = {"label": args.label, "created_at": datetime.now(UTC).isoformat(), "base": args.base,
                 "environment": {"python": platform.python_version(), "platform": platform.platform(),
                                 "cpu_count": os.cpu_count()}}
    async with httpx.AsyncClient(base_url=args.base, timeout=120) as client:
        await _login(client, username, password)
        print("sequential latency:", flush=True)
        await _sequential(client, 1)  # warm-up (model load, caches)
        out["sequential"] = await _sequential(client, args.reps)
        print("concurrent load:", flush=True)
        out["concurrent"] = await _concurrent(args.base, client.cookies, dict(client.headers), args.workers, args.per_worker)
        print(" ", out["concurrent"], flush=True)
        cookie = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
    ws_url = args.base.replace("http", "ws", 1) + "/ws/health-monitoring"
    print("websocket fan-out:", flush=True)
    out["websocket"] = await _websockets(ws_url, cookie, args.origin, args.ws_clients, args.ws_seconds)
    print(" ", out["websocket"], flush=True)
    out["history_query_plan"] = await _plan(args.db_url)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--db-url", required=True)
    s.add_argument("--days", type=int, default=28)
    s.add_argument("--interval", type=int, default=5)
    s.add_argument("--end-offset-days", type=float, default=0.0, help="newest seeded row is this many days old")
    r = sub.add_parser("run")
    r.add_argument("--base", default="http://127.0.0.1:8010")
    r.add_argument("--db-url", required=True)
    r.add_argument("--origin", default="http://localhost:3000")
    r.add_argument("--label", default="run")
    r.add_argument("--out", default="")
    r.add_argument("--reps", type=int, default=15)
    r.add_argument("--workers", type=int, default=20)
    r.add_argument("--per-worker", type=int, default=15)
    r.add_argument("--ws-clients", type=int, default=50)
    r.add_argument("--ws-seconds", type=float, default=30)
    a = ap.parse_args()
    if "astra_med_bench" not in a.db_url:
        sys.exit("refusing: use a dedicated benchmark database whose name contains astra_med_bench")
    if a.cmd == "seed":
        asyncio.run(seed(a.db_url, a.days, a.interval, a.end_offset_days))
        return 0
    result = asyncio.run(run(a))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
