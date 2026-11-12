from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

DONKI_FILES = {
    "FLR": "donki_FLR.json", "CME": "donki_CME.json", "SEP": "donki_SEP.json", "GST": "donki_GST.json",
    "RBE": "donki_RBE.json", "IPS": "donki_IPS.json", "HSS": "donki_HSS.json", "MPC": None,
    "WSAEnlilSimulations": "donki_WSA.json", "notifications": "donki_notifications.json",
}


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeNasa:
    """A stand-in for the NASA services, routed by host and path, recording every request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.api_nasa_status = 404  # mirrors the real api.nasa.gov DONKI proxy failure seen on 2026-11-12
        self.down: set[str] = set()  # hosts that fail with a connection error
        self.overrides: dict[str, Callable[[httpx.Request], httpx.Response]] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, path = request.url.host, request.url.path
        if host in self.down:
            raise httpx.ConnectError("simulated outage", request=request)
        for prefix, handler in self.overrides.items():
            if path.startswith(prefix):
                return handler(request)
        if host == "api.nasa.gov":
            return httpx.Response(self.api_nasa_status, json={"error": "Not Found"},
                                  headers={"X-RateLimit-Limit": "10", "X-RateLimit-Remaining": "7"})
        if host == "ccmc.gsfc.nasa.gov" and path.startswith("/DONKI/WS/get/"):
            name = path.rsplit("/", 1)[-1]
            f = DONKI_FILES.get(name)
            return httpx.Response(200, json=fixture(f) if f else [])
        if host == "visualization.osdr.nasa.gov":
            if path == "/eda/api/missions/":
                return httpx.Response(200, json=fixture("eda_missions.json"))
            if path == "/eda/api/missions/RR-1/telemetry_data/":
                return httpx.Response(200, json=fixture("eda_telemetry_RR-1.json"))
            if path == "/eda/api/missions/RR-1/radiation_data/":
                return httpx.Response(200, json=fixture("eda_radiation_RR-1.json"))
            if path.startswith("/eda/api/missions/"):
                return httpx.Response(200, json=[])
        if host == "osdr.nasa.gov" and path == "/osdr/data/search":
            return httpx.Response(200, json=fixture("osdr_search.json"))
        return httpx.Response(404, json={"error": "unexpected request", "path": path})


@pytest.fixture
def fake_nasa() -> FakeNasa:
    return FakeNasa()


@pytest.fixture
def no_sleep():
    calls: list[float] = []

    async def sleep(seconds: float) -> None:
        calls.append(seconds)

    sleep.calls = calls  # type: ignore[attr-defined]
    return sleep
