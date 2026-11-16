"""GET /api/v2/ready: DB, Redis and a live consumer for every expected queue."""

import pytest
from pydantic import ValidationError

from marcus.api.routes import health
from marcus.core.db import get_db
from marcus.core.settings import Settings, get_settings
from tests.api.conftest import make_client


@pytest.fixture
def inspect_calls(monkeypatch):
    """Fresh per-test cache; inspect answers with whatever `calls["live"]` holds."""
    calls = {"n": 0, "live": set(), "raise": None}

    def fake_inspect() -> set[str]:
        calls["n"] += 1
        if calls["raise"]:
            raise calls["raise"]
        return set(calls["live"])

    monkeypatch.setattr(health, "inspect_live_queues", fake_inspect)
    monkeypatch.setattr(health, "_live_queues", health.LiveQueues())
    return calls


def _expect(monkeypatch, value: str) -> None:
    monkeypatch.setenv("MARCUS_EXPECTED_QUEUES", value)
    get_settings.cache_clear()


async def test_ready_without_expected_queues_checks_db_and_redis(app, inspect_calls):
    async with make_client(app) as c:
        r = await c.get("/api/v2/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}
    assert inspect_calls["n"] == 0  # nothing expected: no broker broadcast at all


async def test_ready_503_lists_queue_without_consumer(app, inspect_calls, monkeypatch):
    _expect(monkeypatch, "q.cpu,q.fake")
    inspect_calls["live"] = {"q.cpu", "q.tools"}
    async with make_client(app) as c:
        r = await c.get("/api/v2/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable", "missing": ["queue:q.fake"]}


async def test_ready_200_when_every_expected_queue_has_a_consumer(app, inspect_calls, monkeypatch):
    _expect(monkeypatch, "q.cpu, q.fake")
    inspect_calls["live"] = {"q.cpu", "q.fake", "q.tools"}
    async with make_client(app) as c:
        r = await c.get("/api/v2/ready")
    assert r.status_code == 200, r.text


async def test_inspect_result_is_cached_for_5_seconds(app, inspect_calls, monkeypatch):
    _expect(monkeypatch, "q.cpu")
    inspect_calls["live"] = {"q.cpu"}
    now = [1000.0]
    monkeypatch.setattr(health, "_monotonic", lambda: now[0])
    async with make_client(app) as c:
        assert (await c.get("/api/v2/ready")).status_code == 200
        inspect_calls["live"] = set()  # the worker died, but the cached answer still holds
        now[0] += 4.9
        assert (await c.get("/api/v2/ready")).status_code == 200
        assert inspect_calls["n"] == 1
        now[0] += 0.2  # 5.1 s after the first broadcast: asked again
        r = await c.get("/api/v2/ready")
    assert inspect_calls["n"] == 2
    assert r.status_code == 503 and r.json()["missing"] == ["queue:q.cpu"]


async def test_inspect_error_counts_every_expected_queue_missing(app, inspect_calls, monkeypatch):
    _expect(monkeypatch, "q.cpu,q.tools")
    inspect_calls["raise"] = OSError("broker gone")
    async with make_client(app) as c:
        r = await c.get("/api/v2/ready")
    assert r.status_code == 503
    assert r.json()["missing"] == ["queue:q.cpu", "queue:q.tools"]


async def test_redis_down_is_reported_and_skips_the_broadcast(app, inspect_calls, monkeypatch):
    _expect(monkeypatch, "q.cpu")
    monkeypatch.setenv("MARCUS_REDIS_URL", "redis://127.0.0.1:1/0")  # nothing listens there
    get_settings.cache_clear()
    async with make_client(app) as c:
        r = await c.get("/api/v2/ready")
    assert r.status_code == 503
    assert r.json()["missing"] == ["redis", "queue:q.cpu"]
    assert inspect_calls["n"] == 0


async def test_database_down_is_reported(app, inspect_calls):
    class DeadSession:
        async def execute(self, *args, **kwargs):
            raise OSError("connection refused")

        async def rollback(self):
            pass

    async def dead_db():
        yield DeadSession()

    app.dependency_overrides[get_db] = dead_db
    async with make_client(app) as c:
        r = await c.get("/api/v2/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable", "missing": ["database"]}


def test_expected_queues_setting_parses_a_comma_list(monkeypatch):
    monkeypatch.setenv("MARCUS_EXPECTED_QUEUES", " q.cpu , q.tools,,q.fake ")
    assert Settings().expected_queues == ["q.cpu", "q.tools", "q.fake"]
    monkeypatch.setenv("MARCUS_EXPECTED_QUEUES", "")
    assert Settings().expected_queues == []


def test_expected_queues_setting_refuses_unknown_queue(monkeypatch):
    monkeypatch.setenv("MARCUS_EXPECTED_QUEUES", "q.cpu,q.cpuu")
    with pytest.raises(ValidationError, match="q.cpuu"):
        Settings()


async def test_hung_inspect_is_bounded_and_cached_as_no_consumer(app, monkeypatch):
    """kombu's pidbox publish retries forever if the broker drops after the PING: the
    broadcast thread is abandoned after INSPECT_BUDGET_S and the timeout is cached."""
    import threading
    import time

    release = threading.Event()
    calls = {"n": 0}

    def hung_inspect() -> set[str]:
        calls["n"] += 1
        release.wait(10)
        return {"q.cpu"}

    monkeypatch.setattr(health, "inspect_live_queues", hung_inspect)
    monkeypatch.setattr(health, "_live_queues", health.LiveQueues())
    monkeypatch.setattr(health, "INSPECT_BUDGET_S", 0.3)
    _expect(monkeypatch, "q.cpu")
    try:
        async with make_client(app) as c:
            t0 = time.monotonic()
            r = await c.get("/api/v2/ready")
            assert time.monotonic() - t0 < 2
            assert r.status_code == 503 and r.json()["missing"] == ["queue:q.cpu"]
            r = await c.get("/api/v2/ready")  # cached timeout: no second broadcast
            assert r.status_code == 503
        assert calls["n"] == 1
    finally:
        release.set()


async def test_lock_waiters_are_bounded_too(monkeypatch):
    """A request waiting behind a hung broadcast gets an answer within its own budget."""
    import threading
    import time

    import anyio

    release = threading.Event()
    calls = {"n": 0}

    def hung_inspect() -> set[str]:
        calls["n"] += 1
        release.wait(10)
        return {"q.cpu"}

    monkeypatch.setattr(health, "inspect_live_queues", hung_inspect)
    monkeypatch.setattr(health, "INSPECT_BUDGET_S", 0.3)
    live = health.LiveQueues()
    results = []

    async def ask():
        results.append(await live.get())

    try:
        t0 = time.monotonic()
        async with anyio.create_task_group() as tg:
            for _ in range(3):
                tg.start_soon(ask)
        assert time.monotonic() - t0 < 2
        assert results == [frozenset()] * 3
        assert calls["n"] == 1  # one broadcast; the waiters reuse the cached timeout
    finally:
        release.set()
