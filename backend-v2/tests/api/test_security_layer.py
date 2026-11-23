"""Security layer: headers, request ids, rate limits, client IP, safe errors, CORS, docs.

The limiter's Redis is a fresh fakeredis per app (autouse fixture in conftest.py); tests that
need the real pipeline semantics or a dead Redis swap `app.state.rate_limiter.redis`.
"""

import asyncio
import json
import logging
import re
import uuid

import fakeredis
import fakeredis.aioredis
import httpx
import pydantic
import pytest
import redis.asyncio as aioredis
import redis.exceptions as redis_exceptions
from fastapi import APIRouter, Response
from starlette.datastructures import Headers

from marcus.api import security
from marcus.api.deps import UNKNOWN_IP, client_ip, rate_key_for_ip
from marcus.api.main import create_app
from marcus.api.routes import events as events_route
from marcus.api.routes import health as health_route
from marcus.core.db import get_db
from marcus.core.events import paper_channel
from marcus.core.settings import Settings, get_settings
from tests.api.conftest import new_owner, seed_paper
from tests.api.test_events import SSE, parse_snapshot
from tests.conftest import TEST_REDIS_URL

SECURITY_HEADERS = {
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-resource-policy": "same-origin",
}
REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
FIXED_NOW = 1_800_000_030.0  # 30 s into a window: Retry-After is 30
_REAL_LIMITER_REDIS = security.limiter_redis  # before conftest swaps in fakeredis


# Every route the app serves. A new route must be added here on purpose.
ALLOWED_ROUTES = {
    ("GET", "/api/v2/health"),
    ("GET", "/api/v2/ready"),
    ("POST", "/api/v2/papers"),
    ("GET", "/api/v2/papers"),
    ("GET", "/api/v2/papers/{paper_id}"),
    ("DELETE", "/api/v2/papers/{paper_id}"),
    ("GET", "/api/v2/papers/{paper_id}/segments"),
    ("GET", "/api/v2/papers/{paper_id}/steps"),
    ("GET", "/api/v2/papers/{paper_id}/pages/{n}/image"),
    ("POST", "/api/v2/papers/{paper_id}/pages/{n}/retry"),
    ("GET", "/api/v2/papers/{paper_id}/text"),
    ("GET", "/api/v2/papers/{paper_id}/export"),
    ("GET", "/api/v2/papers/{paper_id}/events"),
    ("GET", "/api/v2/papers/{paper_id}/annotation"),
    ("POST", "/api/v2/papers/{paper_id}/annotation"),
    ("PUT", "/api/v2/papers/{paper_id}/annotation/curation"),
    ("DELETE", "/api/v2/papers/{paper_id}/annotation/curation"),
    ("GET", "/api/v2/papers/{paper_id}/rgroups"),
    ("GET", "/api/v2/predictions/{prediction_id}/rgroups"),
    ("POST", "/api/v2/predictions/{prediction_id}/rgroups"),
    ("POST", "/api/v2/images"),
    ("GET", "/api/v2/images"),
    ("GET", "/api/v2/images/{job_id}"),
    ("GET", "/api/v2/images/{job_id}/image"),
    ("GET", "/api/v2/images/{job_id}/events"),
    ("POST", "/api/v2/images/{job_id}/predictions"),
    ("GET", "/api/v2/segments/{segment_id}/image"),
    ("GET", "/api/v2/segments/{segment_id}/depiction"),
    ("POST", "/api/v2/segments/{segment_id}/predictions"),
    ("PUT", "/api/v2/segments/{segment_id}/curation"),
    ("PUT", "/api/v2/papers/{paper_id}/curation"),
    ("PUT", "/api/v2/papers/{paper_id}/main-figure"),
    ("GET", "/api/v2/queue"),
    ("POST", "/api/v2/tools/depict"),
    ("POST", "/api/v2/tools/smiles-to-molfile"),
    ("POST", "/api/v2/tools/mcs"),
    ("POST", "/api/v2/tools/compare"),
}


def route_table(app) -> set[tuple[str, str]]:
    """(method, path) of every route, including routers FastAPI includes lazily."""
    found: set[tuple[str, str]] = set()

    def walk(routes):
        for r in routes:
            if hasattr(r, "effective_route_contexts"):  # FastAPI's included router
                walk(list(r.effective_route_contexts()))
            elif hasattr(r, "methods") and hasattr(r, "path"):
                found.update((m, r.path) for m in r.methods if m != "HEAD")
            else:
                raise AssertionError(f"unexpected route object {r!r} (a mount?)")

    walk(app.routes)
    return found


@pytest.fixture
def app(async_db_session):
    app = create_app()
    router = APIRouter()

    @router.get("/api/v2/_boom")
    async def boom():
        raise RuntimeError("secret detail /srv/marcus/data/papers")

    @router.get("/api/v2/_own_csp")
    async def own_csp():
        return Response(
            "hi", media_type="text/plain", headers={"Content-Security-Policy": "sandbox"}
        )

    app.include_router(router)

    async def _db():
        yield async_db_session

    app.dependency_overrides[get_db] = _db
    return app


def client(app, peer=("127.0.0.1", 123), **kw) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=peer)
    return httpx.AsyncClient(transport=transport, base_url="https://test", **kw)


@pytest.fixture
def frozen_time(monkeypatch):
    monkeypatch.setattr(security, "_now", lambda: FIXED_NOW)


def env(monkeypatch, **values):
    for k, v in values.items():
        monkeypatch.setenv(f"MARCUS_{k.upper()}", v)
    get_settings.cache_clear()


def assert_security_headers(r: httpx.Response) -> None:
    for name, value in SECURITY_HEADERS.items():
        assert r.headers.get(name) == value, (r.request.method, r.request.url, name)
    assert REQUEST_ID.fullmatch(r.headers.get("x-request-id", "")), r.headers


def fill(path: str) -> str:
    return re.sub(r"\{n\}", "0", re.sub(r"\{[a-z_]+\}", str(uuid.uuid4()), path))


# --- headers --------------------------------------------------------------------------------


async def test_headers_on_every_route(app, monkeypatch):
    env(monkeypatch, annotate_enabled="1", rgroup_enabled="1")  # else POST is a deliberate 503
    live = {"q.llm", "q.rgroup"}  # as above
    monkeypatch.setattr(health_route, "inspect_live_queues", lambda: live)
    monkeypatch.setattr(health_route, "_live_queues", health_route.LiveQueues())
    async with client(app) as c:
        assert (await c.get("/api/v2/papers")).status_code == 200  # owner cookie first
        for method, path in sorted(ALLOWED_ROUTES):
            if path.endswith("/events"):
                continue  # streams; covered below (an unknown paper is a plain 404)
            r = await c.request(method, fill(path))
            assert r.status_code < 500, (method, path, r.status_code, r.text)
            assert_security_headers(r)
        r = await c.get(fill("/api/v2/papers/{paper_id}/events"))
        assert r.status_code == 404
        assert_security_headers(r)
        for r in (
            await c.get("/api/v2/nope"),  # 404
            await c.get("/nope"),
            await c.delete("/api/v2/health"),  # 405
            await c.post("/api/v2/tools/depict", content=b"{bad json"),  # 422
            await c.get("/api/v2/_boom"),  # 500
        ):
            assert r.status_code in (404, 405, 422, 500)
            assert_security_headers(r)


async def test_request_id_reused_only_when_well_formed(app, monkeypatch):
    env(monkeypatch, trusted_proxies='["127.0.0.1"]')
    async with client(app) as c:
        ok = await c.get("/api/v2/health", headers={"X-Request-ID": "abc-DEF-12345678"})
        assert ok.headers["x-request-id"] == "abc-DEF-12345678"
        for bad in ("short", "has space in it", "x" * 65, "<script>alert(1)</script>"):
            r = await c.get("/api/v2/health", headers={"X-Request-ID": bad})
            assert r.headers["x-request-id"] != bad
            assert re.fullmatch(r"[0-9a-f]{32}", r.headers["x-request-id"])
        a = (await c.get("/api/v2/health")).headers["x-request-id"]
        b = (await c.get("/api/v2/health")).headers["x-request-id"]
    assert a != b


async def test_request_id_from_untrusted_peer_is_replaced(app, monkeypatch):
    sent = {"X-Request-ID": "abc-DEF-12345678"}
    async with client(app) as c:  # no trusted proxies at all
        r = await c.get("/api/v2/health", headers=sent)
    assert re.fullmatch(r"[0-9a-f]{32}", r.headers["x-request-id"])
    env(monkeypatch, trusted_proxies='["10.0.0.0/8"]')
    async with client(app, ("203.0.113.5", 1)) as c:  # a client, not the proxy
        r = await c.get("/api/v2/_boom", headers=sent)
    assert r.headers["x-request-id"] != sent["X-Request-ID"]
    assert r.json()["request_id"] == r.headers["x-request-id"]
    async with client(app, ("10.1.2.3", 1)) as c:  # the proxy
        r = await c.get("/api/v2/health", headers=sent)
    assert r.headers["x-request-id"] == sent["X-Request-ID"]


async def test_route_headers_are_not_overridden(app):
    async with client(app) as c:
        r = await c.get("/api/v2/_own_csp")
    assert r.headers["content-security-policy"] == "sandbox"
    assert r.headers["content-type"].startswith("text/plain")
    assert r.headers["x-frame-options"] == "DENY"


@pytest.fixture
def redis_server(monkeypatch):
    server = fakeredis.FakeServer()
    monkeypatch.setattr(
        events_route, "redis_client", lambda: fakeredis.aioredis.FakeRedis(server=server)
    )
    return server


async def test_sse_still_streams_through_the_middleware(app, async_db_session, redis_server):
    alice, token = await new_owner(async_db_session)
    seeded = await seed_paper(async_db_session, alice)
    sse = SSE(app, f"/api/v2/papers/{seeded.paper_id}/events", token)
    head = await sse.start()
    assert head["status"] == 200
    for name, value in SECURITY_HEADERS.items():
        assert head["headers"][name] == value
    assert head["headers"]["cache-control"] == "no-cache"  # the route's own header stays
    assert parse_snapshot(await sse.chunk())["status"] == "processing"
    # the stream is still open: a later event arrives as its own chunk, not buffered
    assert not sse.task.done()
    event = {"step_id": "x", "kind": "doi", "status": "done"}
    fakeredis.FakeRedis(server=redis_server).publish(
        paper_channel(seeded.paper_id), json.dumps(event)
    )
    assert await sse.chunk() == f"data: {json.dumps(event)}\n\n"
    await sse.disconnect()


# --- errors ---------------------------------------------------------------------------------


async def test_500_body_has_no_trace(app, caplog, monkeypatch):
    env(monkeypatch, trusted_proxies='["127.0.0.1"]')  # the request id comes from the proxy
    caplog.set_level(logging.ERROR)
    async with client(app) as c:
        r = await c.get("/api/v2/_boom", headers={"X-Request-ID": "req-12345678"})
    assert r.status_code == 500
    assert r.json() == {"detail": "internal error", "request_id": "req-12345678"}
    assert "secret" not in r.text and "Traceback" not in r.text
    assert_security_headers(r)
    logged = [rec for rec in caplog.records if "req-12345678" in rec.getMessage()]
    assert logged and logged[0].exc_info is not None
    assert "secret detail" in caplog.text  # the full trace stays in the server log


async def test_500_without_client_request_id_uses_the_generated_one(app):
    async with client(app) as c:
        r = await c.get("/api/v2/_boom")
    assert r.status_code == 500
    assert r.json()["request_id"] == r.headers["x-request-id"]


async def test_validation_errors_do_not_echo_input(app):
    payload = "<img src=x onerror=alert(1)>" * 200  # over the SMILES max length
    async with client(app) as c:
        r = await c.post("/api/v2/tools/depict", json={"smiles": payload, "width": "evil-w"})
    assert r.status_code == 422
    errors = r.json()["detail"]
    assert isinstance(errors, list) and len(errors) == 2
    for err in errors:
        assert "input" not in err
        assert {"type", "loc", "msg"} <= set(err)
    assert "onerror" not in r.text and "evil-w" not in r.text


async def test_http_exception_detail_kept(app):
    async with client(app) as c:
        r = await c.get(f"/api/v2/papers/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json() == {"detail": "not found"}


# --- rate limits ----------------------------------------------------------------------------


def test_rate_limit_defaults():
    s = Settings()
    assert (s.rate_limit_upload_per_min, s.rate_limit_tools_per_min) == (10, 60)
    assert s.rate_limit_ip_per_min == 300 and s.rate_limit_ip_assets_per_min == 3000
    assert s.cors_origins == [] and s.expose_docs is False


@pytest.fixture
async def real_redis():
    r = aioredis.Redis.from_url(TEST_REDIS_URL)
    yield r
    await r.aclose()


async def test_rate_limit_hits_429(app, real_redis, frozen_time):
    """Real Redis: 10 uploads per owner per minute, 60 tool calls, 300 requests per IP."""
    app.state.rate_limiter.redis = real_redis
    peer = (f"198.51.100.{uuid.uuid4().int % 250 + 1}", 1000)
    await real_redis.delete(f"rl:ip:{peer[0]}:{int(FIXED_NOW) // 60}")
    async with client(app, peer) as c:
        assert (await c.get("/api/v2/papers")).status_code == 200  # owner cookie first
        for _ in range(10):  # rejected uploads still count
            r = await c.post("/api/v2/papers", files={"file": ("x.pdf", PNG, "application/pdf")})
            assert r.status_code == 415
        r = await c.post("/api/v2/papers", files={"file": ("x.pdf", PNG, "application/pdf")})
        assert r.status_code == 429
        assert r.json() == {"detail": "rate limited"}
        assert r.headers["retry-after"] == "30"
        assert_security_headers(r)
        # images share the upload bucket
        r = await c.post("/api/v2/images", files={"file": ("x.png", PNG, "image/png")})
        assert r.status_code == 429

        for _ in range(60):
            assert (await c.post("/api/v2/tools/depict", json={})).status_code == 422
        r = await c.post("/api/v2/tools/compare", json={})
        assert r.status_code == 429 and r.headers["retry-after"] == "30"

        used = int(await real_redis.get(f"rl:ip:{peer[0]}:{int(FIXED_NOW) // 60}"))
        for _ in range(300 - used):
            assert (await c.get("/api/v2/nope")).status_code == 404
        r = await c.get("/api/v2/nope")
        assert r.status_code == 429 and r.json() == {"detail": "rate limited"}
        assert r.headers["retry-after"] == "30"
        assert_security_headers(r)
        # health is the one exempt route; /ready is not (it may broadcast to the broker)
        assert (await c.get("/api/v2/ready")).status_code == 429
        assert (await c.get("/api/v2/health")).status_code == 200
    ttl = await real_redis.ttl(f"rl:ip:{peer[0]}:{int(FIXED_NOW) // 60}")
    assert 0 < ttl <= 120


SEG_ID = "0b1f6d3e-5a4c-4e8f-9a7b-1c2d3e4f5a6b"


def fresh_peer() -> tuple[str, int]:
    return (f"198.51.100.{uuid.uuid4().int % 250 + 1}", 1000)


async def test_400_asset_gets_not_limited(app, frozen_time):
    """Defaults (300 ip / 3000 assets): a page of 400 crops is not throttled."""
    async with client(app, fresh_peer()) as c:
        for _ in range(400):
            r = await c.get(f"/api/v2/segments/{SEG_ID}/image")
            assert r.status_code != 429


async def test_depiction_get_with_query_uses_asset_bucket(app, monkeypatch, frozen_time):
    env(monkeypatch, rate_limit_ip_per_min="3")
    async with client(app, fresh_peer()) as c:
        for _ in range(10):
            r = await c.get(f"/api/v2/segments/{SEG_ID}/depiction?v=abc123")
            assert r.status_code != 429


async def test_plain_gets_still_limited_at_301(app, frozen_time):
    peer = fresh_peer()
    async with client(app, peer) as c:
        codes = [(await c.get("/api/v2/nope")).status_code for _ in range(301)]
    assert codes[:300] == [404] * 300 and codes[300] == 429


async def test_post_to_asset_path_uses_plain_bucket(app, monkeypatch, frozen_time):
    env(monkeypatch, rate_limit_ip_per_min="3")
    async with client(app, fresh_peer()) as c:
        codes = [(await c.post(f"/api/v2/segments/{SEG_ID}/image")).status_code for _ in range(5)]
    assert codes[:3] != [429] * 3 and codes[3:] == [429, 429]


def test_asset_regex_rejects_traversal():
    ok = [
        f"/api/v2/papers/{SEG_ID}/pages/0/image",
        f"/api/v2/segments/{SEG_ID}/image",
        f"/api/v2/segments/{SEG_ID}/depiction",
        f"/api/v2/images/{SEG_ID}/image",
    ]
    assert all(security.ASSET_GET.match(p) for p in ok)
    bad = [
        "/api/v2/segments/../papers/x/image",
        f"/api/v2/segments/{SEG_ID}/image/",
        f"/api/v2/segments/{SEG_ID}/image/../x",
        f"/api/v2/papers/{SEG_ID}/pages/12345/image",
        f"/api/v2/segments/{SEG_ID}/curation",
        f"/x/api/v2/segments/{SEG_ID}/image",
    ]
    assert not any(security.ASSET_GET.match(p) for p in bad)


async def test_other_owner_has_own_upload_bucket(app, frozen_time):
    async with client(app) as a, client(app) as b:
        for c in (a, b):  # an error response drops a new owner's cookie: get one first
            assert (await c.get("/api/v2/papers")).status_code == 200
        for _ in range(10):
            await a.post("/api/v2/papers", files={"file": ("x.pdf", PNG, "application/pdf")})
        r = await a.post("/api/v2/papers", files={"file": ("x.pdf", PNG, "application/pdf")})
        assert r.status_code == 429
        r = await b.post("/api/v2/papers", files={"file": ("x.pdf", PNG, "application/pdf")})
        assert r.status_code == 415


async def test_xff_spoof_does_not_reset_limit(app, monkeypatch, frozen_time):
    env(monkeypatch, trusted_proxies='["10.0.0.0/8"]', rate_limit_ip_per_min="5")
    async with client(app, ("203.0.113.7", 1000)) as c:
        codes = [
            (await c.get("/api/v2/nope", headers={"X-Forwarded-For": f"192.0.2.{i}"})).status_code
            for i in range(1, 8)
        ]
    assert codes == [404] * 5 + [429] * 2
    # control: behind the trusted proxy, each forwarded client has its own bucket
    async with client(app, ("10.0.0.2", 1000)) as c:
        for i in range(1, 8):
            r = await c.get("/api/v2/nope", headers={"X-Forwarded-For": f"192.0.2.{100 + i}"})
            assert r.status_code == 404


async def test_health_is_exempt_but_other_paths_are_not(app, monkeypatch, frozen_time):
    env(monkeypatch, rate_limit_ip_per_min="5")
    async with client(app) as c:
        for _ in range(10):
            assert (await c.get("/api/v2/health")).status_code == 200
        # look-alikes of the health path are counted like any other path
        paths = ("/api/v2/health/", "/API/V2/HEALTH", "/", "/api/v2/x", "/api", "/docs")
        codes = [(await c.get(p)).status_code for p in paths]
        assert codes == [307, 404, 404, 404, 404, 429]
        assert (await c.head("/api/v2/health")).status_code == 429  # only GET is exempt


async def test_upload_fails_closed_and_others_fail_open_when_redis_is_down(app, caplog):
    dead = aioredis.Redis.from_url(
        "redis://127.0.0.1:1/0", socket_connect_timeout=0.2, socket_timeout=0.2
    )
    app.state.rate_limiter.redis = dead
    caplog.set_level(logging.WARNING, logger="marcus.api.security")
    try:
        async with client(app) as c:
            # three failed Redis calls (ip scope, fail open) open the breaker
            for _ in range(security.BREAKER_FAILURES):
                assert (await c.get("/api/v2/nope")).status_code == 404
            r = await c.post("/api/v2/papers", files={"file": ("x.pdf", PNG, "application/pdf")})
            assert r.status_code == 503
            assert_security_headers(r)
            r = await c.post("/api/v2/images", files={"file": ("x.png", PNG, "image/png")})
            assert r.status_code == 503
            for _ in range(3):
                assert (await c.get("/api/v2/nope")).status_code == 404
                assert (await c.post("/api/v2/tools/depict", json={})).status_code == 422
    finally:
        await dead.aclose()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    # throttled: one warning per scope, not one per request
    assert {w.getMessage().split()[0] for w in warnings} >= {"rate-limit"}
    assert len(warnings) <= 3


class DeadRedis:
    """Counts how often the limiter reaches for Redis; every call fails (a refused connection,
    or a call slower than the socket timeout)."""

    def __init__(self, exc=redis_exceptions.ConnectionError("down")):
        self.calls = 0
        self.exc = exc

    def pipeline(self, transaction=True):
        self.calls += 1
        raise self.exc


def slow_redis() -> DeadRedis:
    """What redis-py raises when one call takes longer than socket_timeout."""
    return DeadRedis(redis_exceptions.TimeoutError("Timeout reading from socket"))


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(security, "_monotonic", lambda: now[0])
    return now


def test_breaker_constants():
    assert security.BREAKER_FAILURES == 3
    assert security.BREAKER_WINDOW_S == 5.0
    assert security.BREAKER_OPEN_S == 5.0


async def test_one_or_two_slow_calls_do_not_open_the_breaker(clock):
    slow = slow_redis()
    limiter = security.RateLimiter(slow)
    # 1st slow call: the upload itself is let through (breaker closed), nothing is skipped
    assert await limiter.hit("upload", "o", fail_open=False) is None
    assert slow.calls == 1
    clock[0] += 1.0
    assert await limiter.hit("ip", "k", fail_open=True) is None  # 2nd slow call
    assert slow.calls == 2
    clock[0] += 1.0
    limiter.redis = fakeredis.aioredis.FakeRedis()  # Redis answers again: still closed
    assert await limiter.hit("upload", "o", fail_open=False) is None
    assert await limiter.hit("upload", "o", fail_open=False) is None
    assert len(await limiter.redis.keys("rl:upload:o:*")) == 1


async def test_three_slow_calls_in_five_seconds_open_the_breaker(clock):
    slow = slow_redis()
    limiter = security.RateLimiter(slow)
    assert await limiter.hit("ip", "k", fail_open=True) is None
    clock[0] += 2.0
    assert await limiter.hit("tools", "o", fail_open=True) is None
    clock[0] += 3.0  # 3rd failure exactly 5.0 s after the 1st: within the window, opens
    with pytest.raises(security.RateLimitUnavailable):
        await limiter.hit("upload", "o", fail_open=False)
    assert slow.calls == 3
    # open: Redis is not touched; uploads fail closed, ip and tools fail open
    clock[0] += 4.9
    with pytest.raises(security.RateLimitUnavailable):
        await limiter.hit("upload", "o", fail_open=False)
    assert await limiter.hit("ip", "k", fail_open=True) is None
    assert await limiter.hit("tools", "o", fail_open=True) is None
    assert slow.calls == 3


async def test_failures_spread_over_more_than_five_seconds_do_not_open_it(clock):
    """Sliding window: only failures in the last 5 s count (a success does not reset them)."""
    slow = slow_redis()
    limiter = security.RateLimiter(slow)
    for t in (0.0, 4.0, 9.5, 14.0):  # never 3 failures within 5 s
        clock[0] = 1000.0 + t
        assert await limiter.hit("upload", "o", fail_open=False) is None
    assert slow.calls == 4
    clock[0] = 1000.0 + 14.5  # with 9.5 and 14.0: three in 5 s
    with pytest.raises(security.RateLimitUnavailable):
        await limiter.hit("upload", "o", fail_open=False)


async def test_breaker_closes_after_five_seconds(clock):
    dead = DeadRedis()
    limiter = security.RateLimiter(dead)
    for _ in range(3):
        assert await limiter.hit("ip", "k", fail_open=True) is None
    opened_at = clock[0]
    clock[0] = opened_at + 4.99
    with pytest.raises(security.RateLimitUnavailable):
        await limiter.hit("upload", "o", fail_open=False)
    assert dead.calls == 3
    clock[0] = opened_at + 5.0  # closed: Redis is tried again; one failure does not re-open
    assert await limiter.hit("upload", "o", fail_open=False) is None
    assert dead.calls == 4
    limiter.redis = fakeredis.aioredis.FakeRedis()  # Redis is back: counting resumes
    assert await limiter.hit("upload", "o", fail_open=False) is None
    assert len(await limiter.redis.keys("rl:upload:o:*")) == 1


class _Pipe:
    def __init__(self, gate):
        self.gate = gate

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def incr(self, key):
        pass

    def expire(self, key, seconds, nx=False):
        pass

    async def execute(self):
        if self.gate is not None:
            await self.gate.wait()
        raise redis_exceptions.TimeoutError("Timeout reading from socket")


class GatedRedis:
    """Every call times out; the first one only when `gate` is set (a call still in flight)."""

    def __init__(self):
        self.gate = asyncio.Event()
        self.calls = 0

    def pipeline(self, transaction=True):
        self.calls += 1
        return _Pipe(self.gate if self.calls == 1 else None)


async def test_upload_in_flight_when_the_breaker_opens_then_failing_gets_503(clock):
    """Review D3b I1: the call started while closed, fails after the breaker opened: refused."""
    redis = GatedRedis()
    limiter = security.RateLimiter(redis)
    upload = asyncio.create_task(limiter.hit("upload", "o", fail_open=False))
    while redis.calls == 0:  # the upload call is now waiting on Redis
        await asyncio.sleep(0)
    for _ in range(security.BREAKER_FAILURES):  # other requests' calls open the breaker
        assert await limiter.hit("ip", "k", fail_open=True) is None
    assert limiter._is_open()
    redis.gate.set()  # the in-flight upload call now fails too
    with pytest.raises(security.RateLimitUnavailable):
        await upload
    # an in-flight ip call failing while open still fails open
    redis2 = GatedRedis()
    limiter.redis = redis2
    clock[0] += security.BREAKER_OPEN_S  # closed again
    ip = asyncio.create_task(limiter.hit("ip", "k2", fail_open=True))
    while redis2.calls == 0:
        await asyncio.sleep(0)
    for _ in range(security.BREAKER_FAILURES):
        assert await limiter.hit("tools", "o", fail_open=True) is None
    redis2.gate.set()
    assert await ip is None


async def test_uploads_get_503_only_while_the_breaker_is_open(app, clock):
    slow = slow_redis()
    app.state.rate_limiter.redis = slow
    upload = {"files": {"file": ("x.pdf", PNG, "application/pdf")}}
    async with client(app) as c:
        # ip call (1st failure) + upload call (2nd failure): breaker closed, upload goes on
        assert (await c.post("/api/v2/papers", **upload)).status_code == 415
        assert slow.calls == 2
        # ip call is the 3rd failure: the breaker opens and this upload is refused
        r = await c.post("/api/v2/papers", **upload)
        assert r.status_code == 503 and r.json() == {"detail": "service unavailable"}
        assert slow.calls == 3
        clock[0] += 4.9  # still open: refused without touching Redis; tools fail open
        assert (
            await c.post("/api/v2/images", files={"file": ("x.png", PNG, "image/png")})
        ).status_code == 503
        assert (await c.post("/api/v2/tools/depict", json={})).status_code == 422
        assert slow.calls == 3
        clock[0] += 0.2  # closed again (Redis still slow): one failure does not refuse
        assert (await c.post("/api/v2/papers", **upload)).status_code == 415
        assert slow.calls == 5


def test_redis_timeout_is_a_setting_with_default_one_second(monkeypatch):
    assert Settings().rate_limit_redis_timeout_s == 1.0
    kwargs = _REAL_LIMITER_REDIS().connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] == 1.0 and kwargs["socket_connect_timeout"] == 1.0
    env(monkeypatch, rate_limit_redis_timeout_s="2.5")
    kwargs = _REAL_LIMITER_REDIS().connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] == 2.5 and kwargs["socket_connect_timeout"] == 2.5


# --- client IP ------------------------------------------------------------------------------


def fake_request(peer, *xff_lines):
    raw = [(b"x-forwarded-for", line.encode()) for line in xff_lines]
    client_addr = None if peer is None else type("C", (), {"host": peer})()
    return type("R", (), {"client": client_addr, "headers": Headers(raw=raw)})()


def test_xff_read_across_header_lines(monkeypatch):
    env(monkeypatch, trusted_proxies='["10.0.0.0/8"]')
    # a client-sent line first, the proxy's own line second: the proxy's line wins
    assert client_ip(fake_request("10.0.0.5", "6.6.6.6", "1.2.3.4")) == "1.2.3.4"
    assert client_ip(fake_request("10.0.0.5", "6.6.6.6", "1.2.3.4, 10.0.0.9")) == "1.2.3.4"
    assert client_ip(fake_request("10.0.0.5", "1.2.3.4", "10.0.0.9")) == "1.2.3.4"
    # untrusted peer: every line ignored
    assert client_ip(fake_request("203.0.113.1", "6.6.6.6", "1.2.3.4")) == "203.0.113.1"


def test_unparseable_peer_is_unknown(monkeypatch):
    assert UNKNOWN_IP == "unknown"
    assert client_ip(fake_request(None)) == "unknown"
    assert client_ip(fake_request("testclient")) == "unknown"
    assert client_ip(fake_request("")) == "unknown"
    env(monkeypatch, trusted_proxies='["10.0.0.0/8"]')
    assert client_ip(fake_request("testclient", "1.2.3.4")) == "unknown"


@pytest.mark.parametrize("bad", ['["not-an-ip"]', '["10.0.0.0/8", "10.0.0.0/33"]', '[""]'])
def test_invalid_trusted_proxies_fails_startup(monkeypatch, bad):
    env(monkeypatch, trusted_proxies=bad)
    with pytest.raises(pydantic.ValidationError):
        create_app()


def test_valid_trusted_proxies_accepted(monkeypatch):
    env(monkeypatch, trusted_proxies='["10.0.0.0/8", "192.168.1.1", "fd00::/8"]')
    create_app()


async def test_unknown_peers_share_one_new_owner_bucket(app):
    for i in range(10):
        async with client(app, (f"peer-{i}", 1)) as c:
            assert (await c.get("/api/v2/papers")).status_code == 200
            assert (await c.get("/api/v2/papers")).status_code == 200  # used: it came back
    async with client(app, ("another-name", 1)) as c:
        r = await c.get("/api/v2/papers")
    assert r.status_code == 429


async def test_unknown_peers_share_one_active_paper_bucket(app, monkeypatch):
    env(monkeypatch, ip_max_active_papers="2", browser_max_active_papers="5")
    pdf = b"%PDF-1.4\n" + b"0" * 100
    async with client(app, ("a-name", 1)) as c1, client(app, ("b-name", 1)) as c2:
        assert (await c1.post("/api/v2/papers", files={"file": ("p.pdf", pdf)})).status_code == 202
        assert (await c2.post("/api/v2/papers", files={"file": ("p.pdf", pdf)})).status_code == 202
        r = await c2.post("/api/v2/papers", files={"file": ("p.pdf", pdf)})
    assert r.status_code == 429 and "address" in r.json()["detail"]


async def test_unknown_peers_share_one_ip_rate_bucket(app, monkeypatch, frozen_time):
    env(monkeypatch, rate_limit_ip_per_min="3")
    codes = []
    for name in ("p1", "p2", "p3", "p4"):
        async with client(app, (name, 1)) as c:
            codes.append((await c.get("/api/v2/nope")).status_code)
    assert codes == [404, 404, 404, 429]


def test_rate_key_for_ip():
    assert rate_key_for_ip("203.0.113.9") == "203.0.113.9"
    assert rate_key_for_ip(UNKNOWN_IP) == UNKNOWN_IP
    assert rate_key_for_ip("2001:db8:1:2:aaaa:bbbb:cccc:dddd") == "2001:db8:1:2::/64"
    assert rate_key_for_ip("2001:db8:1:2::1") == rate_key_for_ip("2001:db8:1:2:ffff::9")
    assert rate_key_for_ip("2001:db8:1:3::1") == "2001:db8:1:3::/64"


def test_ipv4_mapped_peer_is_its_ipv4_address():
    assert client_ip(fake_request("::ffff:198.51.100.7")) == "198.51.100.7"


async def test_ipv6_rate_bucket_is_the_64_prefix(app, monkeypatch, frozen_time):
    env(monkeypatch, rate_limit_ip_per_min="3")
    codes = []
    for host in ("2001:db8:1:2::1", "2001:db8:1:2::2", "2001:db8:1:2:ffff::3", "2001:db8:1:2::4"):
        async with client(app, (host, 1)) as c:
            codes.append((await c.get("/api/v2/nope")).status_code)
    assert codes == [404, 404, 404, 429]
    async with client(app, ("2001:db8:1:3::1", 1)) as c:  # the next /64 has its own bucket
        assert (await c.get("/api/v2/nope")).status_code == 404


async def test_ipv6_new_owner_limit_is_per_64(app):
    for i in range(10):
        async with client(app, (f"2001:db8:5:6::{i + 1:x}", 1)) as c:
            assert (await c.get("/api/v2/papers")).status_code == 200
            assert (await c.get("/api/v2/papers")).status_code == 200  # used: it came back
    async with client(app, ("2001:db8:5:6:abcd::1", 1)) as c:
        r = await c.get("/api/v2/papers")
    assert r.status_code == 429
    async with client(app, ("2001:db8:5:7::1", 1)) as c:
        assert (await c.get("/api/v2/papers")).status_code == 200


async def test_ipv6_active_paper_limit_is_per_64(app, monkeypatch):
    env(monkeypatch, ip_max_active_papers="2", browser_max_active_papers="5")
    pdf = b"%PDF-1.4\n" + b"0" * 100
    async with (
        client(app, ("2001:db8:9:9::1", 1)) as c1,
        client(app, ("2001:db8:9:9::2", 1)) as c2,
        client(app, ("2001:db8:9:a::1", 1)) as other,
    ):
        assert (await c1.post("/api/v2/papers", files={"file": ("p.pdf", pdf)})).status_code == 202
        assert (await c2.post("/api/v2/papers", files={"file": ("p.pdf", pdf)})).status_code == 202
        r = await c2.post("/api/v2/papers", files={"file": ("p.pdf", pdf)})
        assert r.status_code == 429 and "address" in r.json()["detail"]
        r = await other.post("/api/v2/papers", files={"file": ("p.pdf", pdf)})
        assert r.status_code == 202


# --- per-address active cap counts the work's own address (review I-1) ------------------------

PDF = b"%PDF-1.4\n" + b"0" * 100


async def _purge_owner_ips(db) -> None:
    """What the 30-day retention phase does to every owner's recorded IP."""
    from sqlalchemy import update

    from marcus.core.models import Owner

    await db.execute(update(Owner).values(created_ip=None))
    await db.commit()


async def _papers(db):
    from sqlalchemy import select

    from marcus.core.models import Paper

    return list(
        (await db.execute(select(Paper).execution_options(populate_existing=True))).scalars()
    )


async def test_owner_with_purged_ip_still_counts_toward_its_address(
    app, async_db_session, monkeypatch
):
    env(monkeypatch, ip_max_active_papers="2", browser_max_active_papers="5")
    async with client(app, ("198.51.100.20", 1)) as old, client(app, ("198.51.100.20", 2)) as new:
        for _ in range(2):
            assert (
                await old.post("/api/v2/papers", files={"file": ("p.pdf", PDF)})
            ).status_code == 202
        await _purge_owner_ips(async_db_session)  # the owner is over 30 days old
        r = await new.post("/api/v2/papers", files={"file": ("p.pdf", PDF)})
        assert r.status_code == 429 and "address" in r.json()["detail"]
        assert {p.started_ip for p in await _papers(async_db_session)} == {"198.51.100.20"}

        # the cap frees as the work finishes; finished work keeps no address
        from sqlalchemy import select

        from marcus.core.enums import ErrorClass
        from marcus.core.models import Step
        from marcus.core.pipeline import fail_step

        paper = (await _papers(async_db_session))[0]

        def fail_check(s):  # the worker finds the PDF bad: the paper fails, its work ends
            step = s.execute(select(Step).where(Step.paper_id == paper.id)).scalar_one()
            step.status, step.attempts = "running", 1
            s.flush()
            fail_step(s, step.id, ErrorClass.BAD_INPUT, "bad pdf", retryable=False)

        await async_db_session.run_sync(fail_check)
        await async_db_session.commit()
        done = [p for p in await _papers(async_db_session) if p.status != "checking"]
        assert [(p.status, p.started_ip) for p in done] == [("failed", None)]
        r = await new.post("/api/v2/papers", files={"file": ("p.pdf", PDF)})
        assert r.status_code == 202


async def test_owners_with_purged_ips_do_not_fill_the_unknown_bucket(
    app, async_db_session, monkeypatch
):
    env(monkeypatch, ip_max_active_papers="2", browser_max_active_papers="5")
    async with client(app, ("203.0.113.5", 1)) as known:
        for _ in range(2):
            assert (
                await known.post("/api/v2/papers", files={"file": ("p.pdf", PDF)})
            ).status_code == 202
    await _purge_owner_ips(async_db_session)
    async with client(app, ("a-name", 1)) as unknown:  # an unparseable peer: the unknown bucket
        r = await unknown.post("/api/v2/papers", files={"file": ("p.pdf", PDF)})
    assert r.status_code == 202


async def test_image_job_counts_toward_its_address_and_keeps_no_ip_once_settled(
    app, async_db_session, monkeypatch
):
    import io

    from PIL import Image
    from sqlalchemy import select

    from marcus.core.models import ImageJob

    env(monkeypatch, ip_max_active_papers="1", browser_max_active_papers="5")
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(buf, "PNG")
    async with client(app, ("198.51.100.30", 1)) as a, client(app, ("198.51.100.30", 2)) as b:
        r = await a.post("/api/v2/images", files={"file": ("i.png", buf.getvalue())})
        assert r.status_code == 202
        await _purge_owner_ips(async_db_session)
        r = await b.post("/api/v2/papers", files={"file": ("p.pdf", PDF)})
        assert r.status_code == 429
    (job,) = (await async_db_session.execute(select(ImageJob))).scalars()
    assert job.started_ip == "198.51.100.30"


# --- CORS -----------------------------------------------------------------------------------

PREFLIGHT = {"Origin": "https://app.example", "Access-Control-Request-Method": "POST"}


async def test_no_cors_by_default(app):
    async with client(app) as c:
        r = await c.options("/api/v2/papers", headers=PREFLIGHT)
        g = await c.get("/api/v2/health", headers={"Origin": "https://app.example"})
    assert "access-control-allow-origin" not in r.headers
    assert "access-control-allow-origin" not in g.headers


async def test_cors_only_for_configured_origins(monkeypatch, async_db_session):
    env(monkeypatch, cors_origins='["https://app.example"]')
    app = create_app()
    async with client(app) as c:
        ok = await c.options("/api/v2/papers", headers=PREFLIGHT)
        bad = await c.options(
            "/api/v2/papers", headers={**PREFLIGHT, "Origin": "https://evil.example"}
        )
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "https://app.example"
    assert ok.headers["access-control-allow-credentials"] == "true"
    assert set(ok.headers["access-control-allow-methods"].split(", ")) == {
        "GET",
        "POST",
        "PUT",
        "DELETE",
    }
    assert "access-control-allow-origin" not in bad.headers
    assert_security_headers(ok)


@pytest.mark.parametrize("bad", ['["*"]', '["https://app.example", " * "]'])
def test_wildcard_cors_origin_fails_startup(monkeypatch, bad):
    env(monkeypatch, cors_origins=bad)
    with pytest.raises(pydantic.ValidationError):
        create_app()


# --- docs -----------------------------------------------------------------------------------

DOC_PATHS = ["/docs", "/redoc", "/openapi.json", "/api/v2/docs", "/api/v2/redoc"]


async def test_docs_hidden_by_default(app):
    async with client(app) as c:
        for path in [*DOC_PATHS, "/api/v2/openapi.json", "/docs/oauth2-redirect"]:
            assert (await c.get(path)).status_code == 404, path


async def test_docs_only_under_api_v2_when_enabled(monkeypatch):
    env(monkeypatch, expose_docs="true")
    app = create_app()
    async with client(app) as c:
        spec = await c.get("/api/v2/openapi.json")
        assert spec.status_code == 200 and "/api/v2/papers" in spec.json()["paths"]
        for path in ("/api/v2/docs", "/api/v2/redoc"):
            r = await c.get(path)
            assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
            assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
            assert r.headers["x-frame-options"] == "DENY"
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await c.get(path)).status_code == 404, path


PINNED_CDN = re.compile(r"https://cdn\.jsdelivr\.net/npm/(swagger-ui-dist|redoc)@\d+\.\d+\.\d+/")


async def test_docs_csp_pins_cdn_paths(monkeypatch):
    env(monkeypatch, expose_docs="true")
    app = create_app()
    async with client(app) as c:
        for path in ("/api/v2/docs", "/api/v2/redoc"):
            r = await c.get(path)
            directives = {
                d.split()[0]: d.split()[1:]
                for d in r.headers["content-security-policy"].split("; ")
            }
            pinned = []
            for name in ("script-src", "style-src"):
                for src in directives[name]:
                    if "jsdelivr" in src:
                        assert PINNED_CDN.fullmatch(src), (path, name, src)
                        pinned.append(src)
            assert pinned
            # every CDN file the page loads sits under a pinned path
            urls = re.findall(r"https://cdn\.jsdelivr\.net/[^\"' ]+", r.text)
            assert urls, path
            for url in urls:
                assert any(url.startswith(p) for p in pinned), (path, url)


# --- route list -----------------------------------------------------------------------------


def test_no_admin_or_reset_routes_exposed(monkeypatch):
    app = create_app()
    assert route_table(app) == ALLOWED_ROUTES


async def test_concurrent_requests_cannot_overshoot_the_limit(app, monkeypatch, frozen_time):
    env(monkeypatch, rate_limit_ip_per_min="5")
    async with client(app) as c:
        rs = await asyncio.gather(*(c.get("/api/v2/nope") for _ in range(20)))
    assert sorted(r.status_code for r in rs) == [404] * 5 + [429] * 15


async def test_request_id_is_on_log_lines_and_paper_id_from_the_path(app):
    """The middleware binds request_id (and paper_id from /papers/<uuid>) for the request."""
    from marcus.core import logging as mlog

    seen = {}

    @app.get("/probe-log")
    async def probe():
        seen.update({n: v.get() for n, v in mlog._context.items()})
        return {}

    async with client(app) as c:
        r = await c.get("/probe-log")
    assert seen["request_id"] == r.headers["X-Request-ID"]
    assert seen["paper_id"] is None
    paper = uuid.uuid4()
    m = security._PAPER_PATH.match(f"/api/v2/papers/{paper}/segments")
    assert m and m.group(1) == str(paper)
    assert security._PAPER_PATH.match("/api/v2/papers/not-a-uuid/segments") is None
