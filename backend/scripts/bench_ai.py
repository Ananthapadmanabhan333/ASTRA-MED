"""AI inference benchmark: model loading, memory and per-request latency, in process.

Runs the real FastAPI app against a temporary SQLite database that the simulator backfills, using
the registered model version in ``backend/artifacts`` (or ``--artifacts``). Requests go through the
ASGI stack (validation, routing, serialisation) without a network hop, and the AI response cache is
off, so every call does the full inference. All data is simulated.

    python scripts/bench_ai.py --label before --out ../docs/benchmarks/ai-before.json
    python scripts/bench_ai.py --label after  --out ../docs/benchmarks/ai-after.json

The ``fingerprint`` section hashes model outputs on fixed inputs, so two runs can show that an
optimisation changed speed but not results.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import hashlib
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ.setdefault("ASTRA_AUTH_ENABLED", "false")
os.environ.setdefault("ASTRA_TWIN_BACKGROUND", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _rss_mb() -> float:
    return psutil.Process().memory_info().rss / 2**20


def _summary(samples_ms: list[float]) -> dict[str, float]:
    s = sorted(samples_ms)

    def pct(p: float) -> float:
        k = (len(s) - 1) * p
        lo, hi = int(k), min(int(k) + 1, len(s) - 1)
        return s[lo] + (s[hi] - s[lo]) * (k - lo)

    return {
        "n": len(s),
        "mean_ms": round(statistics.fmean(s), 1),
        "p50_ms": round(pct(0.5), 1),
        "p95_ms": round(pct(0.95), 1),
        "max_ms": round(s[-1], 1),
    }


# Same instant as the test suite: every crew member is awake and not exercising.
FROZEN_NOW = datetime(2026, 11, 9, 11, 0, tzinfo=UTC)


def _freeze_clock(at: datetime) -> None:
    """Pin app.core.timeutil.utcnow (used everywhere in the app) so outputs are reproducible.

    Every module imports the same function object, so swapping its code object freezes them all.
    """
    from app.core import timeutil

    timeutil._BENCH_NOW = at  # type: ignore[attr-defined]

    def frozen():
        return _BENCH_NOW  # noqa: F821 - resolved in timeutil's globals

    timeutil.utcnow.__code__ = frozen.__code__


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


async def _timed(client: AsyncClient, method: str, url: str, reps: int, **kw) -> tuple[dict, dict]:
    times, last = [], None
    for _ in range(reps):
        t = time.perf_counter()
        r = await client.request(method, url, **kw)
        times.append((time.perf_counter() - t) * 1000)
        r.raise_for_status()
        last = r.json()
    return _summary(times), last


async def main(args: argparse.Namespace) -> dict:
    artifacts = Path(args.artifacts) if args.artifacts else ROOT / "artifacts"
    tmp = Path(tempfile.mkdtemp(prefix="astra-bench-ai-"))
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp / 'bench.db').as_posix()}",
        simulator_enabled=False,
        random_events_per_hour=0,
        backfill_days=args.days,
        backfill_interval_minutes=5,
        ai_artifacts_dir=str(artifacts),
        ai_cache_seconds=0,
        space_sync_enabled=False,
        mission_orchestrator_enabled=False,
        log_level="WARNING",
    )
    if args.freeze:
        _freeze_clock(FROZEN_NOW)
    gc.collect()
    rss_start = _rss_mb()
    t = time.perf_counter()
    app = create_app(settings)
    out: dict = {
        "label": args.label,
        "created_at": datetime.now(UTC).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
        },
        "setup": {"backfill_days": args.days, "reps": args.reps, "cache_seconds": 0,
                  "frozen_clock": FROZEN_NOW.isoformat() if args.freeze else None},
    }
    async with app.router.lifespan_context(app):
        out["setup"]["startup_with_backfill_s"] = round(time.perf_counter() - t, 2)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://bench", timeout=300) as client:
            rss_before_models = _rss_mb()
            t = time.perf_counter()
            status = (await client.get("/api/ai/status")).json()
            load_s = time.perf_counter() - t
            if not status.get("loaded"):
                raise SystemExit(f"no model loaded: {status.get('error')}")
            gc.collect()
            out["model"] = {
                "version": status["model_version"],
                "detectors": status["detectors"],
                "forecasters": status["forecasters"],
                "cold_load_s": round(load_s, 2),
                "rss_before_load_mb": round(rss_before_models, 1),
                "rss_after_load_mb": round(_rss_mb(), 1),
                "rss_model_delta_mb": round(_rss_mb() - rss_before_models, 1),
                "rss_process_start_mb": round(rss_start, 1),
            }

            aid = "AST-01"
            end = (FROZEN_NOW if args.freeze else datetime.now(UTC)).replace(second=0, microsecond=0)
            body = {"astronaut_id": aid, "start": (end - timedelta(hours=24)).isoformat(),
                    "end": end.isoformat(), "include_explanations": True}
            # The first request fits the personal baseline; measure it on its own.
            t = time.perf_counter()
            (await client.get(f"/api/ai/astronaut/{aid}/baseline")).raise_for_status()
            out["baseline_fit_first_s"] = round(time.perf_counter() - t, 2)

            lat: dict[str, dict] = {}
            fp: dict[str, str] = {}
            lat["anomaly_detection_24h"], det = await _timed(client, "POST", "/api/ai/anomaly-detection", args.reps, json=body)
            fp["anomaly_detection_24h"] = _digest([(p["ts"], round(p["ensemble_score"], 6)) for p in det["timeline"]])
            fp["anomaly_explanations"] = _digest([
                (d["peak_ts"], d["kind"], d["signals"],
                 [(c["signal"], round(c["share"], 4)) for c in (d["explanation"] or {}).get("contributors", [])])
                for d in det["detections"]
            ])
            out["detections_24h"] = len(det["detections"])
            out["flagged_windows_24h"] = sum(p["flagged"] for p in det["timeline"])
            for model in ("xgboost", "lstm"):
                if model not in status["forecasters"]:
                    continue
                key = f"forecast_{model}"
                lat[key], fc = await _timed(client, "GET", f"/api/ai/astronaut/{aid}/forecast", args.reps,
                                            params={"model": model})
                if model == "lstm":
                    # float32 CPU kernels give last-digit differences between processes, so the
                    # neural forecast is compared numerically (max |difference|), not by hash.
                    out["lstm_values"] = {s["signal"]: [p["value"] for p in s["forecast"]] for s in fc["series"]}
                else:
                    fp[key] = _digest([(s["signal"], [round(p["value"], 5) for p in s["forecast"]])
                                       for s in fc["series"]])
            lat["risk_assessment"], risk = await _timed(client, "GET", f"/api/ai/astronaut/{aid}/risk-assessment", args.reps)
            fp["risk_assessment"] = _digest([risk.get("category"), risk.get("risk_score")])
            lat["crew_overview"], _ = await _timed(client, "GET", "/api/ai/crew-overview", max(3, args.reps // 4))
            out["latency"] = lat
            out["fingerprint"] = fp
            out["rss_end_mb"] = round(_rss_mb(), 1)
            perf = (await client.get("/api/ai/status")).json().get("inference")
            if perf:
                out["service_inference_stats"] = perf
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--label", default="run")
    p.add_argument("--out", default="")
    p.add_argument("--artifacts", default="")
    p.add_argument("--days", type=int, default=3, help="days of simulated history to backfill")
    p.add_argument("--reps", type=int, default=12)
    p.add_argument("--no-freeze", dest="freeze", action="store_false",
                   help="use the real clock (outputs then differ between runs)")
    a = p.parse_args()
    result = asyncio.run(main(a))
    text = json.dumps(result, indent=2)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)
