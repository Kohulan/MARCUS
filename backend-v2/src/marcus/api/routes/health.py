"""Health routes: `/health` (process is up) and `/ready` (the stack can do work).

`GET /api/v2/ready` answers 200 only if the database and Redis answer and every queue in
`expected_queues` (env MARCUS_EXPECTED_QUEUES: the queues this deployment runs) has at least
one live Celery consumer; otherwise 503 with the missing parts, e.g.
`{"status": "unavailable", "missing": ["redis", "queue:q.fake"]}`.

The consumer check is a broker broadcast (`inspect(timeout=1).active_queues()`), so its result
is cached per API process for READY_CACHE_S: /ready cannot be used to hammer the broker. Only
one broadcast runs at a time per process; it runs in a thread (it blocks up to 1 s). /ready is
not exempt from the per-IP rate limit. The database and Redis checks run on every call, each
bounded by CHECK_TIMEOUT_S.
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

from marcus.core.db import get_db
from marcus.core.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter()

READY_CACHE_S = 5.0
INSPECT_TIMEOUT_S = 1.0
CHECK_TIMEOUT_S = 2.0


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _monotonic() -> float:
    return time.monotonic()


def inspect_live_queues() -> set[str]:
    """Names of the queues that at least one live worker consumes (blocking broadcast)."""
    from marcus.core.celery_app import celery_app

    replies = celery_app.control.inspect(timeout=INSPECT_TIMEOUT_S).active_queues() or {}
    return {q["name"] for queues in replies.values() for q in (queues or []) if q.get("name")}


class LiveQueues:
    """Per-process cache of inspect_live_queues(): one broadcast per READY_CACHE_S at most.

    A failed broadcast is cached too (as no live queue), so a broken broker is not hammered.
    """

    def __init__(self) -> None:
        self._at: float | None = None
        self._value: frozenset[str] = frozenset()
        self._lock: asyncio.Lock | None = None

    def _fresh(self) -> bool:
        return self._at is not None and _monotonic() - self._at < READY_CACHE_S

    async def get(self) -> frozenset[str]:
        if self._fresh():
            return self._value
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if not self._fresh():  # another request may have refreshed it while we waited
                try:
                    self._value = frozenset(await anyio.to_thread.run_sync(inspect_live_queues))
                except Exception as exc:  # noqa: BLE001
                    log.warning("ready: celery inspect failed: %s", type(exc).__name__)
                    self._value = frozenset()
                self._at = _monotonic()
            return self._value


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


async def _redis_ok() -> bool:
    client = aioredis.Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=CHECK_TIMEOUT_S,
        socket_timeout=CHECK_TIMEOUT_S,
    )
    try:
        with anyio.fail_after(CHECK_TIMEOUT_S):
            return bool(await client.ping())
    except Exception as exc:  # noqa: BLE001
        log.warning("ready: redis check failed: %s", type(exc).__name__)
        return False
    finally:
        await client.aclose()


@router.get("/ready", response_model=None)
async def ready(db: AsyncSession = Depends(get_db)) -> dict[str, str] | JSONResponse:
    missing: list[str] = []
    if not await _database_ok(db):
        missing.append("database")
    redis_ok = await _redis_ok()
    if not redis_ok:
        missing.append("redis")
    expected = get_settings().expected_queues
    if expected:
        # the broker is Redis: without it no worker can answer (and inspect could hang)
        live = await _live_queues.get() if redis_ok else frozenset()
        missing += [f"queue:{q}" for q in expected if q not in live]
    if missing:
        return JSONResponse({"status": "unavailable", "missing": missing}, status_code=503)
    return {"status": "ready"}
