"""Resilient asynchronous HTTP client for NASA open-data APIs.

* Retries transient failures (timeouts, connection errors, HTTP 5xx, 429) with exponential
  backoff and jitter, honouring ``Retry-After``.
* Fails over between mirrors of the same source. A mirror that answers with a structural error
  (404/410, or a body that is not JSON) is taken out of rotation for a while (circuit breaker).
* Tracks rate-limit headers and skips a mirror whose quota is exhausted.
* Caches successful responses in memory for a per-call TTL.
* Never logs, stores or returns an API key: URLs are redacted before they leave this module.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.timeutil import utcnow
from app.space.provenance import Endpoint

logger = logging.getLogger("astra.space.http")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
STRUCTURAL_STATUS = {404, 410}


class SourceUnavailable(Exception):
    """Every mirror of a source failed. ``attempts`` lists what was tried, keys redacted."""

    def __init__(self, source_id: str, attempts: list[dict[str, Any]]):
        self.source_id = source_id
        self.attempts = attempts
        last = attempts[-1]["error"] if attempts else "no mirror available"
        super().__init__(f"{source_id}: all endpoints failed ({last})")


@dataclass
class MirrorState:
    open_until: datetime | None = None  # circuit open: skip this mirror until then
    reason: str | None = None
    rate_limit_remaining: int | None = None
    rate_limit_limit: int | None = None
    rate_limited_until: datetime | None = None


@dataclass
class SourceHealth:
    source_id: str
    status: str = "unknown"  # unknown | healthy | degraded | offline
    last_attempt: datetime | None = None
    last_success: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    last_latency_ms: float | None = None
    consecutive_failures: int = 0
    requests: int = 0
    failures: int = 0
    cache_hits: int = 0
    last_endpoint: str | None = None
    mirrors: dict[str, MirrorState] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "last_attempt": self.last_attempt,
            "last_success": self.last_success,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "last_latency_ms": self.last_latency_ms,
            "consecutive_failures": self.consecutive_failures,
            "requests": self.requests,
            "failures": self.failures,
            "cache_hits": self.cache_hits,
            "last_endpoint": self.last_endpoint,
            "mirrors": [
                {
                    "name": name,
                    "available": m.open_until is None or m.open_until <= utcnow(),
                    "disabled_until": m.open_until if m.open_until and m.open_until > utcnow() else None,
                    "reason": m.reason,
                    "rate_limit_remaining": m.rate_limit_remaining,
                    "rate_limit_limit": m.rate_limit_limit,
                }
                for name, m in self.mirrors.items()
            ],
        }


@dataclass
class FetchResult:
    data: Any
    url: str  # redacted
    endpoint: str
    status_code: int
    retrieved_at: datetime
    latency_ms: float
    attempts: int
    from_cache: bool = False


def redact(url: str, secrets: tuple[str, ...]) -> str:
    for s in secrets:
        if s:
            url = url.replace(s, "***")
    return url


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _int_header(response: httpx.Response, *names: str) -> int | None:
    for n in names:
        v = response.headers.get(n)
        if v is not None:
            try:
                return int(v)
            except ValueError:
                return None
    return None


class ResilientClient:
    def __init__(
        self,
        *,
        timeout_s: float = 30.0,
        max_retries: int = 3,
        backoff_base_s: float = 1.0,
        backoff_max_s: float = 30.0,
        circuit_seconds: float = 6 * 3600,
        min_spacing_s: float = 0.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        user_agent: str = "ASTRA-MED research prototype (NASA open data client)",
    ) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=min(10.0, timeout_s)),
            transport=transport,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            follow_redirects=True,
        )
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.backoff_max_s = backoff_max_s
        self.circuit_seconds = circuit_seconds
        self.min_spacing_s = min_spacing_s
        self._sleep = sleep
        self._cache: dict[str, tuple[float, FetchResult]] = {}
        self._last_request: dict[str, float] = {}
        self.health: dict[str, SourceHealth] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    def source_health(self, source_id: str) -> SourceHealth:
        return self.health.setdefault(source_id, SourceHealth(source_id))

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(retry_after, self.backoff_max_s)
        delay = min(self.backoff_max_s, self.backoff_base_s * (2 ** attempt))
        return delay * (0.75 + 0.5 * random.random())

    async def _space_requests(self, host: str) -> None:
        if self.min_spacing_s <= 0:
            return
        last = self._last_request.get(host)
        if last is not None:
            wait = self.min_spacing_s - (time.monotonic() - last)
            if wait > 0:
                await self._sleep(wait)
        self._last_request[host] = time.monotonic()

    async def get_json(
        self,
        source_id: str,
        endpoints: list[Endpoint],
        path: str,
        params: dict[str, Any] | None = None,
        *,
        api_key: str = "",
        cache_ttl_s: float = 0.0,
    ) -> FetchResult:
        """GET ``path`` from the first healthy endpoint; fail over to the next on errors."""
        health = self.source_health(source_id)
        params = {k: v for k, v in (params or {}).items() if v is not None}
        attempts_log: list[dict[str, Any]] = []
        now = utcnow()
        candidates = []
        for ep in endpoints:
            state = health.mirrors.setdefault(ep.name, MirrorState())
            if state.open_until and state.open_until > now:
                attempts_log.append({"endpoint": ep.name, "error": f"skipped: {state.reason}"})
                continue
            if state.rate_limited_until and state.rate_limited_until > now:
                attempts_log.append({"endpoint": ep.name, "error": "skipped: rate limit exhausted"})
                continue
            candidates.append(ep)
        if not candidates:  # every circuit open: try them anyway rather than fail without asking
            candidates = list(endpoints)

        for ep in candidates:
            state = health.mirrors[ep.name]
            query = dict(params)
            if ep.needs_key:
                query["api_key"] = api_key or "DEMO_KEY"
            # No trailing slash for an empty path: some NASA services answer 404 to "/search/".
            url = f"{ep.base_url.rstrip('/')}/{path.lstrip('/')}" if path else ep.base_url.rstrip("/")
            full = f"{url}?{urlencode(query)}" if query else url
            safe_url = redact(full, (api_key,))  # DEMO_KEY is public; a real key is never exposed
            cache_key = safe_url
            if cache_ttl_s > 0:
                hit = self._cache.get(cache_key)
                if hit and hit[0] > time.monotonic():
                    health.cache_hits += 1
                    cached = hit[1]
                    return FetchResult(cached.data, cached.url, cached.endpoint, cached.status_code,
                                       cached.retrieved_at, 0.0, 0, from_cache=True)

            for attempt in range(self.max_retries + 1):
                health.last_attempt = utcnow()
                health.requests += 1
                await self._space_requests(httpx.URL(url).host)
                started = time.perf_counter()
                try:
                    response = await self._client.get(url, params=query)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    error = f"{exc.__class__.__name__}"
                    attempts_log.append({"endpoint": ep.name, "url": safe_url, "attempt": attempt + 1, "error": error})
                    if attempt < self.max_retries:
                        await self._sleep(self._backoff(attempt, None))
                        continue
                    break
                latency = (time.perf_counter() - started) * 1000
                remaining = _int_header(response, "x-ratelimit-remaining")
                if remaining is not None:
                    state.rate_limit_remaining = remaining
                    state.rate_limit_limit = _int_header(response, "x-ratelimit-limit")

                if response.status_code == 429:
                    state.rate_limited_until = utcnow() + timedelta(seconds=_retry_after_seconds(response) or 3600)
                    attempts_log.append({"endpoint": ep.name, "url": safe_url, "attempt": attempt + 1,
                                         "error": "HTTP 429 rate limited"})
                    # Prefer another mirror over waiting out a quota window.
                    if ep is not candidates[-1]:
                        break
                    if attempt < self.max_retries:
                        await self._sleep(self._backoff(attempt, _retry_after_seconds(response)))
                        continue
                    break
                if response.status_code in RETRYABLE_STATUS:
                    attempts_log.append({"endpoint": ep.name, "url": safe_url, "attempt": attempt + 1,
                                         "error": f"HTTP {response.status_code}"})
                    if attempt < self.max_retries:
                        await self._sleep(self._backoff(attempt, _retry_after_seconds(response)))
                        continue
                    break
                if response.status_code in STRUCTURAL_STATUS or response.status_code >= 400:
                    reason = f"HTTP {response.status_code} for {path}"
                    attempts_log.append({"endpoint": ep.name, "url": safe_url, "attempt": attempt + 1, "error": reason})
                    if response.status_code in STRUCTURAL_STATUS:
                        state.open_until = utcnow() + timedelta(seconds=self.circuit_seconds)
                        state.reason = reason
                    break
                try:
                    data = response.json()
                except ValueError:
                    reason = "response was not JSON"
                    attempts_log.append({"endpoint": ep.name, "url": safe_url, "attempt": attempt + 1, "error": reason})
                    state.open_until = utcnow() + timedelta(seconds=self.circuit_seconds)
                    state.reason = reason
                    break

                state.open_until, state.reason = None, None
                result = FetchResult(data=data, url=safe_url, endpoint=ep.name, status_code=response.status_code,
                                     retrieved_at=utcnow(), latency_ms=round(latency, 1), attempts=attempt + 1)
                health.status = "healthy" if not attempts_log else "degraded"
                health.last_success = result.retrieved_at
                health.last_latency_ms = result.latency_ms
                health.consecutive_failures = 0
                health.last_endpoint = ep.name
                if attempts_log:
                    health.last_error = attempts_log[-1]["error"]
                    health.last_error_at = utcnow()
                if cache_ttl_s > 0:
                    self._cache[cache_key] = (time.monotonic() + cache_ttl_s, result)
                return result

        health.failures += 1
        health.consecutive_failures += 1
        health.status = "offline"
        health.last_error = attempts_log[-1]["error"] if attempts_log else "no endpoint"
        health.last_error_at = utcnow()
        logger.warning("%s unavailable: %s", source_id, health.last_error)
        raise SourceUnavailable(source_id, attempts_log)
