"""Health routes: `/health` (process is up) and `/ready` (the stack can do work).

`GET /api/v2/ready` answers 200 only if the database and Redis answer and every queue in
`expected_queues` (env MARCUS_EXPECTED_QUEUES: the queues this deployment runs) has at least
one live Celery consumer, and the dispatcher's Redis heartbeat (marcus.core.heartbeat) is at
most 30 s old; otherwise 503 with the missing parts, e.g.
`{"status": "unavailable", "missing": ["redis", "queue:q.fake"]}`.

The consumer check is a broker broadcast (`inspect(timeout=1).active_queues()`), so its result
is cached per API process for READY_CACHE_S: /ready cannot be used to hammer the broker. Only
one broadcast runs at a time per process, in a worker thread. `timeout=1` only bounds the
reply collection: kombu publishes the broadcast with retry, and `Connection.ensure` retries
for ever if the broker drops between the Redis PING and the publish. So each request waits at
most INSPECT_BUDGET_S (for the lock and the broadcast together); a broadcast that overruns is
abandoned (its thread finishes whenever kombu gives up or the broker returns) and cached as
"no live queue". At most one such thread exists per process (a 1-token limiter), so a broker
outage cannot pile up threads. /ready is not exempt from the per-IP rate limit. The database
and Redis checks run on every call, each bounded by CHECK_TIMEOUT_S.
"""

import asyncio
import logging
import time

import anyio
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.core import heartbeat
from marcus.core.db import get_db
from marcus.core.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter()

READY_CACHE_S = 5.0
INSPECT_TIMEOUT_S = 1.0  # reply collection inside the broadcast
INSPECT_BUDGET_S = INSPECT_TIMEOUT_S + 1.0  # a request's whole wait: lock + broadcast
CHECK_TIMEOUT_S = 2.0


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _monotonic() -> float:
    return time.monotonic()


def inspect_live_queues() -> set[str]:
    """Names of the queues that at least one live worker consumes (blocking broadcast)."""
    from marcus.core.celery_app import live_queue_names

    return live_queue_names(INSPECT_TIMEOUT_S)


class LiveQueues:
    """Per-process cache of inspect_live_queues(): one broadcast per READY_CACHE_S at most.

    A failed or timed-out broadcast is cached too (as no live queue), so a broken broker is
    not hammered. Every caller waits at most INSPECT_BUDGET_S, whether it runs the broadcast
    or waits for the lock behind one.
    """

    def __init__(self) -> None:
        self._at: float | None = None
        self._value: frozenset[str] = frozenset()
        self._lock: asyncio.Lock | None = None
        self._threads: anyio.CapacityLimiter | None = None

    def _fresh(self) -> bool:
        return self._at is not None and _monotonic() - self._at < READY_CACHE_S

    def _store(self, value: frozenset[str]) -> frozenset[str]:
        self._value, self._at = value, _monotonic()
        return value

    async def get(self) -> frozenset[str]:
        if self._fresh():
            return self._value
        if self._lock is None:
            self._lock = asyncio.Lock()
            self._threads = anyio.CapacityLimiter(1)
        try:
            with anyio.fail_after(INSPECT_BUDGET_S):
                async with self._lock:
                    if self._fresh():  # refreshed by the request we waited behind
                        return self._value
                    live = await anyio.to_thread.run_sync(
                        inspect_live_queues, abandon_on_cancel=True, limiter=self._threads
                    )
                    return self._store(frozenset(live))
        except TimeoutError:
            log.warning("ready: celery inspect gave no answer within %.1f s", INSPECT_BUDGET_S)
        except Exception as exc:  # noqa: BLE001
            log.warning("ready: celery inspect failed: %s", type(exc).__name__)
        if self._fresh():  # a waiter whose budget ran out after the holder stored a result
            return self._value
        return self._store(frozenset())


_live_queues = LiveQueues()


async def _database_ok(db: AsyncSession) -> bool:
    try:
        with anyio.fail_after(CHECK_TIMEOUT_S):
            await db.execute(text("SELECT 1"))
            await db.rollback()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("ready: database check failed: %s", type(exc).__name__)
        return False


async def _redis_checks() -> tuple[bool, bool]:
    """(redis answers, dispatcher heartbeat is fresh), one connection, each bounded."""
    client = aioredis.Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=CHECK_TIMEOUT_S,
        socket_timeout=CHECK_TIMEOUT_S,
    )
    try:
        with anyio.fail_after(CHECK_TIMEOUT_S):
            redis_ok = bool(await client.ping())
        with anyio.fail_after(CHECK_TIMEOUT_S):
            beat = heartbeat.parse_age(await client.get(heartbeat.KEY))
        return redis_ok, heartbeat.is_alive(beat)
    except Exception as exc:  # noqa: BLE001
        log.warning("ready: redis check failed: %s", type(exc).__name__)
        return False, False
    finally:
        await client.aclose()


@router.get("/ready", response_model=None)
async def ready(db: AsyncSession = Depends(get_db)) -> dict[str, str] | JSONResponse:
    missing: list[str] = []
    if not await _database_ok(db):
        missing.append("database")
    redis_ok, dispatcher_ok = await _redis_checks()
    if not redis_ok:
        missing.append("redis")
    elif not dispatcher_ok:  # the dispatcher's liveness lives in Redis: unknown without it
        missing.append("dispatcher")
    expected = get_settings().expected_queues
    if expected:
        # the broker is Redis: without it no worker can answer (and inspect could hang)
        live = await _live_queues.get() if redis_ok else frozenset()
        missing += [f"queue:{q}" for q in expected if q not in live]
    if missing:
        return JSONResponse({"status": "unavailable", "missing": missing}, status_code=503)
    return {"status": "ready"}
