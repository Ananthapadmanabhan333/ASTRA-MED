"""NASA API failure handling: retries, backoff, rate limits, failover, circuit breaker, caching,
and that an API key never leaks into URLs, errors or health reports."""

from __future__ import annotations

import json

import httpx
import pytest

from app.space.http import ResilientClient, SourceUnavailable
from app.space.provenance import Endpoint

PRIMARY = Endpoint("primary", "https://api.example.test/DONKI", needs_key=True)
MIRROR = Endpoint("mirror", "https://mirror.example.test/DONKI/WS/get")
SECRET = "sk-test-0123456789"


def client(handler, no_sleep, **kw) -> ResilientClient:
    return ResilientClient(transport=httpx.MockTransport(handler), sleep=no_sleep, backoff_base_s=1.0, **kw)


async def test_transient_errors_are_retried_with_exponential_backoff(no_sleep):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json=[{"ok": 1}])

    c = client(handler, no_sleep, max_retries=3)
    result = await c.get_json("donki", [MIRROR], "FLR", {"startDate": "2026-11-01"})
    assert result.data == [{"ok": 1}] and result.attempts == 3 and result.endpoint == "mirror"
    assert len(no_sleep.calls) == 2 and no_sleep.calls[1] > no_sleep.calls[0]  # backoff grows
    assert c.source_health("donki").status == "degraded"  # succeeded after errors
    await c.aclose()


async def test_retries_stop_after_the_limit_and_raise_with_attempts(no_sleep):
    c = client(lambda r: httpx.Response(500), no_sleep, max_retries=2)
    with pytest.raises(SourceUnavailable) as err:
        await c.get_json("donki", [MIRROR], "FLR")
    assert len(err.value.attempts) == 3  # first try + 2 retries
    h = c.source_health("donki")
    assert h.status == "offline" and h.consecutive_failures == 1 and "HTTP 500" in h.last_error
    await c.aclose()


async def test_timeouts_and_connection_errors_fail_over_to_the_mirror(no_sleep):
    def handler(request):
        if request.url.host == "api.example.test":
            raise httpx.ConnectTimeout("simulated", request=request)
        return httpx.Response(200, json=[])

    c = client(handler, no_sleep, max_retries=1)
    result = await c.get_json("donki", [PRIMARY, MIRROR], "FLR", api_key=SECRET)
    assert result.endpoint == "mirror"
    await c.aclose()


async def test_rate_limit_switches_mirror_and_honours_retry_after(no_sleep):
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "api.example.test":
            return httpx.Response(429, headers={"Retry-After": "120", "X-RateLimit-Remaining": "0", "X-RateLimit-Limit": "10"})
        return httpx.Response(200, json=[1])

    c = client(handler, no_sleep)
    first = await c.get_json("donki", [PRIMARY, MIRROR], "FLR", api_key=SECRET)
    assert first.endpoint == "mirror" and no_sleep.calls == []  # did not wait out the quota
    state = c.source_health("donki").mirrors["primary"]
    assert state.rate_limit_remaining == 0 and state.rate_limit_limit == 10 and state.rate_limited_until is not None
    # While the quota window lasts the primary is skipped entirely.
    await c.get_json("donki", [PRIMARY, MIRROR], "CME", api_key=SECRET)
    assert hosts == ["api.example.test", "mirror.example.test", "mirror.example.test"]
    await c.aclose()


async def test_rate_limit_on_the_only_endpoint_waits_for_retry_after(no_sleep):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "7"}) if len(calls) == 1 else httpx.Response(200, json=[])

    c = client(handler, no_sleep)
    await c.get_json("donki", [MIRROR], "FLR")
    assert no_sleep.calls == [7.0]
    await c.aclose()


async def test_404_opens_the_circuit_so_the_broken_endpoint_is_skipped(no_sleep):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(404) if request.url.host == "api.example.test" else httpx.Response(200, json=[])

    c = client(handler, no_sleep)
    await c.get_json("donki", [PRIMARY, MIRROR], "FLR", api_key=SECRET)
    await c.get_json("donki", [PRIMARY, MIRROR], "CME", api_key=SECRET)
    assert seen == ["api.example.test", "mirror.example.test", "mirror.example.test"]
    state = c.source_health("donki").mirrors["primary"]
    assert state.open_until is not None and "404" in state.reason
    await c.aclose()


async def test_non_json_body_is_a_structural_failure(no_sleep):
    def handler(request):
        if request.url.host == "api.example.test":
            return httpx.Response(200, text="<html>maintenance</html>")
        return httpx.Response(200, json={"ok": True})

    c = client(handler, no_sleep)
    result = await c.get_json("donki", [PRIMARY, MIRROR], "FLR", api_key=SECRET)
    assert result.endpoint == "mirror"
    assert c.source_health("donki").mirrors["primary"].reason == "response was not JSON"
    await c.aclose()


async def test_api_key_never_appears_in_results_errors_or_health(no_sleep):
    sent = []

    def handler(request):
        sent.append(str(request.url))
        return httpx.Response(500)

    c = client(handler, no_sleep, max_retries=0)
    with pytest.raises(SourceUnavailable) as err:
        await c.get_json("donki", [PRIMARY], "FLR", {"startDate": "2026-11-01"}, api_key=SECRET)
    assert any(SECRET in u for u in sent)  # the key is sent to NASA...
    assert SECRET not in str(err.value) and SECRET not in json.dumps(err.value.attempts)  # ...but never echoed
    assert SECRET not in json.dumps(c.source_health("donki").as_dict(), default=str)

    c2 = client(lambda r: httpx.Response(200, json=[]), no_sleep)
    ok = await c2.get_json("donki", [PRIMARY], "FLR", api_key=SECRET)
    assert SECRET not in ok.url and "api_key=***" in ok.url
    await c.aclose()
    await c2.aclose()


async def test_responses_are_cached_for_the_ttl(no_sleep):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=[len(calls)])

    c = client(handler, no_sleep)
    a = await c.get_json("osdr", [MIRROR], "search", {"term": "x"}, cache_ttl_s=60)
    b = await c.get_json("osdr", [MIRROR], "search", {"term": "x"}, cache_ttl_s=60)
    assert len(calls) == 1 and b.from_cache and b.data == a.data
    assert c.source_health("osdr").cache_hits == 1
    await c.aclose()


async def test_empty_path_has_no_trailing_slash(no_sleep):
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(200, json={})

    c = client(handler, no_sleep)
    await c.get_json("osdr", [Endpoint("osdr", "https://osdr.example.test/osdr/data/search")], "", {"term": "rr"})
    assert urls[0].startswith("https://osdr.example.test/osdr/data/search?")  # "/search/?" returns 404 on OSDR
    await c.aclose()
