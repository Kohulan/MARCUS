"""Dispatcher liveness: Redis key written by the loop, read by /ready and the healthcheck."""

import fakeredis
import pytest

from marcus.core import heartbeat
from marcus.dispatcher import health


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


def test_beat_writes_unix_time_with_ttl(r):
    heartbeat.beat(r, now=1000.0)
    assert float(r.get(heartbeat.KEY)) == 1000.0
    assert 0 < r.ttl(heartbeat.KEY) <= heartbeat.TTL_S == 60


def test_age_is_none_without_key(r):
    assert heartbeat.age(r, now=5.0) is None


def test_age_of_fresh_and_stale_beat(r):
    heartbeat.beat(r, now=1000.0)
    assert heartbeat.age(r, now=1010.0) == 10.0
    assert heartbeat.is_alive(heartbeat.age(r, now=1029.0))
    assert not heartbeat.is_alive(heartbeat.age(r, now=1031.0))
    assert not heartbeat.is_alive(None)


def test_garbage_value_counts_as_dead(r):
    r.set(heartbeat.KEY, "not-a-number")
    assert heartbeat.age(r, now=1.0) is None


def test_beat_failure_never_raises():
    class Broken:
        def set(self, *a, **k):
            raise ConnectionError("down")

    heartbeat.beat(Broken(), now=1.0)  # logged, swallowed


def test_health_main_exit_codes(r, monkeypatch):
    monkeypatch.setattr(health, "_client", lambda: r)
    assert health.main() == 1  # no key
    heartbeat.beat(r)
    assert health.main() == 0
    r.set(heartbeat.KEY, "1.0")  # ancient
    assert health.main() == 1


def test_health_main_redis_down_is_unhealthy(monkeypatch):
    class Down:
        def get(self, *a):
            raise ConnectionError("down")

    monkeypatch.setattr(health, "_client", lambda: Down())
    assert health.main() == 1
