"""`GET /papers/{id}/events` and `GET /images/{id}/events`: live updates as server-sent events.

The stream starts with one `event: snapshot` ({status, counts}; an image job's is {status})
and then forwards each worker event published on `marcus:paper:{id}` (`marcus:image:{id}`) as a `data:` line, with a `: ping` comment
every `sse_ping_interval_s` seconds. Events are only a hint: the database stays the source
of truth, and a client that reconnects re-reads `GET /papers/{id}`.

Order inside the stream: subscribe first, then read the snapshot, then forward messages. An
event published while the snapshot is being read is therefore delivered after it; the
client may see a change twice (in the snapshot and as an event), which is harmless.

The snapshot is read with the request's session inside the stream. FastAPI (>= 0.118) keeps
yield dependencies open until the response ends; each read transaction is committed right
away, so an open stream holds no pooled database connection.

Limits:
- at most `sse_max_streams_per_owner` open streams per owner (429 above). The count is the
  Redis key `sse:{owner_id}`: +1 when a stream is accepted, -1 when it ends, with a TTL
  refreshed on every ping so a crashed API process cannot hold slots for ever. Without
  Redis the stream is allowed (it then fails at subscribe, below).
- the paper status is re-read after each finished step event and on each ping; once the
  paper is done, failed or deleted the stream sends `event: end` (data: {"status"}) and
  closes. A client should close its EventSource on `end`; it must not reconnect.
- after `sse_max_duration_s` the stream closes without `end`; the client reconnects.
- when Redis fails (subscribe or later), the stream sends `retry: 15000` and an
  `event: error` frame, then closes; the client reconnects after 15 s.
"""

import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import lru_cache

import anyio
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.deps import current_owner, get_owned_image_job, get_owned_paper
from marcus.api.read import steps_by_status
from marcus.api.redisutil import incr_with_ttl
from marcus.core.db import get_db
from marcus.core.enums import FINISHED_STEPS, ImageJobStatus, PaperStatus
from marcus.core.events import image_channel, paper_channel
from marcus.core.models import ImageJob, Owner, Paper
from marcus.core.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter()

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
POLL_S = 1.0  # longest wait for one Redis message; bounds how late a disconnect is noticed
CLOSE_S = 2.0  # longest wait for unsubscribe + close when the stream ends
SLOT_TTL_S = 60  # stream slot counter TTL, refreshed on every ping
RETRY_MS = 15000
TERMINAL = {PaperStatus.DONE.value, PaperStatus.FAILED.value, PaperStatus.DELETED.value}
assert TERMINAL == {  # image jobs end on the same three words
    ImageJobStatus.DONE.value,
    ImageJobStatus.FAILED.value,
    ImageJobStatus.DELETED.value,
}
TOO_MANY_STREAMS = "Too many open event streams"
ERROR_FRAME = f"retry: {RETRY_MS}\n\n", 'event: error\ndata: {"detail": "events unavailable"}\n\n'


@lru_cache
def redis_client() -> aioredis.Redis:
    """Process-wide async client; each stream takes its own pub/sub connection from its pool."""
    settings = get_settings()
    return aioredis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        max_connections=settings.events_redis_max_connections,
    )


def _event(data: bytes | str) -> dict | None:
    """A worker message as a JSON object, or None when it is not one."""
    try:
        event = json.loads(data)
    except (ValueError, TypeError):
        return None
    return event if isinstance(event, dict) else None


def _frame(event: dict) -> str:
    """One `data:` line. Re-encoding keeps it on one line, so a message cannot inject fields."""
    return f"data: {json.dumps(event)}\n\n"


def _end_frame(status: str) -> str:
    return f"event: end\ndata: {json.dumps({'status': status})}\n\n"


async def _paper_snapshot(db: AsyncSession, paper_id: uuid.UUID) -> dict:
    status = await db.scalar(select(Paper.status).where(Paper.id == paper_id))
    counts = await steps_by_status(db, paper_id)
    await db.commit()  # end the read transaction: release the pooled connection
    return {"status": status, "counts": {"steps_by_status": counts}}


async def _paper_status(db: AsyncSession, paper_id: uuid.UUID) -> str:
    status = await db.scalar(select(Paper.status).where(Paper.id == paper_id))
    await db.commit()
    return status or PaperStatus.DELETED.value  # purged rows count as deleted


async def _image_snapshot(db: AsyncSession, job_id: uuid.UUID) -> dict:
    return {"status": await _image_status(db, job_id)}


async def _image_status(db: AsyncSession, job_id: uuid.UUID) -> str:
    status = await db.scalar(select(ImageJob.status).where(ImageJob.id == job_id))
    await db.commit()
    return status or ImageJobStatus.DELETED.value


# --- stream slots ---------------------------------------------------------------------------


def _slot_ttl() -> int:
    # the TTL must outlive the gap between two pings, or open streams would lose their slots
    return max(SLOT_TTL_S, int(get_settings().sse_ping_interval_s * 2) + 1)


async def _take_slot(owner_id: uuid.UUID) -> str | None:
    """Count one open stream for the owner; 429 above the limit. None when Redis is down."""
    key = f"sse:{owner_id}"
    try:
        count = await incr_with_ttl(redis_client(), key, _slot_ttl())
    except (RedisError, OSError):
        log.warning("event stream slot for owner %s not counted (Redis)", owner_id, exc_info=True)
        return None  # fail open: the stream itself reports the outage
    if count > get_settings().sse_max_streams_per_owner:
        await _give_back(key)
        raise HTTPException(status_code=429, detail=TOO_MANY_STREAMS)
    return key


async def _give_back(key: str | None) -> None:
    if key is None:
        return
    try:
        await redis_client().decr(key)
    except (RedisError, OSError):
        log.warning("could not release event stream slot %s", key, exc_info=True)


async def _refresh_slot(key: str | None) -> None:
    if key is None:
        return
    with contextlib.suppress(RedisError, OSError):  # the stream notices a lost Redis itself
        await redis_client().expire(key, _slot_ttl())


# --- the stream -----------------------------------------------------------------------------


async def _stream(
    request: Request,
    db: AsyncSession,
    row_id: uuid.UUID,
    channel: str,
    snapshot_of: Callable[[AsyncSession, uuid.UUID], Awaitable[dict]],
    status_of: Callable[[AsyncSession, uuid.UUID], Awaitable[str]],
    slot: str | None,
) -> AsyncIterator[str]:
    settings = get_settings()
    ping_s = settings.sse_ping_interval_s
    deadline = time.monotonic() + settings.sse_max_duration_s
    pubsub = redis_client().pubsub(ignore_subscribe_messages=True)
    try:
        await pubsub.subscribe(channel)
        snapshot = await snapshot_of(db, row_id)  # after subscribe: no event can fall between
        yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"
        if snapshot["status"] in TERMINAL:
            yield _end_frame(snapshot["status"])
            return
        last_ping = time.monotonic()
        while not await request.is_disconnected():
            left = deadline - time.monotonic()
            if left <= 0:
                return  # no `end`: the work is still running, the client reconnects
            msg = await pubsub.get_message(timeout=min(POLL_S, ping_s, left))
            check = False
            if msg is not None and msg.get("type") == "message":
                event = _event(msg["data"])
                if event is not None:
                    yield _frame(event)
                    status = event.get("status")
                    check = isinstance(status, str) and status in FINISHED_STEPS
            if time.monotonic() - last_ping >= ping_s:
                last_ping = time.monotonic()
                await _refresh_slot(slot)
                yield ": ping\n\n"
                check = True  # a deletion publishes no event
            if check:
                status = await status_of(db, row_id)
                if status in TERMINAL:
                    yield _end_frame(status)
                    return
    except RedisError:
        log.warning("event stream %s lost Redis", channel, exc_info=True)
        for frame in ERROR_FRAME:
            yield frame
    finally:
        # Shielded (the server may be cancelling the stream) but bounded (Redis may be gone).
        with anyio.move_on_after(CLOSE_S, shield=True):
            # a failure: the connection is gone; closing it below drops the subscription
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe()
            try:
                await pubsub.aclose()
            except Exception:
                log.warning("could not close pub/sub %s", channel, exc_info=True)
            await _give_back(slot)


@router.get("/papers/{paper_id}/events")
async def paper_events(
    paper_id: uuid.UUID,
    request: Request,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    paper = await get_owned_paper(db, owner, paper_id)
    await db.commit()  # the stream reads the snapshot itself, after subscribing
    slot = await _take_slot(owner.id)
    return StreamingResponse(
        _stream(
            request, db, paper.id, paper_channel(paper.id), _paper_snapshot, _paper_status, slot
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/images/{job_id}/events")
async def image_events(
    job_id: uuid.UUID,
    request: Request,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    job = await get_owned_image_job(db, owner, job_id)
    await db.commit()
    slot = await _take_slot(owner.id)
    return StreamingResponse(
        _stream(request, db, job.id, image_channel(job.id), _image_snapshot, _image_status, slot),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
