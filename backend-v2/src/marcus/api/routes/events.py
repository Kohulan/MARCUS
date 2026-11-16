"""`GET /papers/{id}/events`: live step and segment updates as server-sent events.

The stream starts with one `event: snapshot` ({status, counts}) and then forwards each
worker event published on `marcus:paper:{id}` as a `data:` line, with a `: ping` comment
every `sse_ping_interval_s` seconds. Events are only a hint: the database stays the source
of truth, and a client that reconnects re-reads `GET /papers/{id}`.

Order inside the stream: subscribe first, then read the snapshot, then forward messages. An
event published while the snapshot is being read is therefore delivered after it; the
client may see a change twice (in the snapshot and as an event), which is harmless.

The snapshot is read with the request's session inside the stream. FastAPI (>= 0.118) keeps
yield dependencies open until the response ends; the read transaction is committed right
after the snapshot, so an open stream holds no pooled database connection.
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from functools import lru_cache

import anyio
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.deps import current_owner, get_owned_paper
from marcus.api.routes.papers import steps_by_status
from marcus.core.db import get_db
from marcus.core.events import paper_channel
from marcus.core.models import Owner, Paper
from marcus.core.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter()

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
POLL_S = 1.0  # longest wait for one Redis message; bounds how late a disconnect is noticed
CLOSE_S = 2.0  # longest wait for unsubscribe + close when the stream ends


@lru_cache
def redis_client() -> aioredis.Redis:
    """Process-wide async client; each stream takes its own pub/sub connection from its pool."""
    return aioredis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)


def _frame(data: bytes | str) -> str | None:
    """Re-encode a worker message as one `data:` line, or None when it is not JSON.

    Re-encoding keeps the frame on a single line, so a message can never inject SSE fields.
    """
    try:
        return f"data: {json.dumps(json.loads(data))}\n\n"
    except (ValueError, TypeError):
        return None


async def _snapshot(db: AsyncSession, paper_id: uuid.UUID) -> dict:
    status = await db.scalar(select(Paper.status).where(Paper.id == paper_id))
    counts = await steps_by_status(db, paper_id)
    await db.commit()  # end the read transaction: release the pooled connection
    return {"status": status, "counts": {"steps_by_status": counts}}


async def _stream(request: Request, db: AsyncSession, paper_id: uuid.UUID) -> AsyncIterator[str]:
    ping_s = get_settings().sse_ping_interval_s
    pubsub = redis_client().pubsub(ignore_subscribe_messages=True)
    try:
        await pubsub.subscribe(paper_channel(paper_id))
        snapshot = await _snapshot(db, paper_id)  # after subscribe: no event can fall between
        yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"
        last_ping = time.monotonic()
        while not await request.is_disconnected():
            msg = await pubsub.get_message(timeout=min(POLL_S, ping_s))
            if msg is not None and msg.get("type") == "message":
                frame = _frame(msg["data"])
                if frame is not None:
                    yield frame
            if time.monotonic() - last_ping >= ping_s:
                last_ping = time.monotonic()
                yield ": ping\n\n"
    except RedisError:
        log.warning("event stream for paper %s lost Redis", paper_id, exc_info=True)
    finally:
        # Shielded (the server may be cancelling the stream) but bounded (Redis may be gone).
        with anyio.move_on_after(CLOSE_S, shield=True):
            try:
                await pubsub.unsubscribe()
            except Exception:
                pass  # the connection is gone; closing it below drops the subscription
            try:
                await pubsub.aclose()
            except Exception:
                log.warning("could not close pub/sub for paper %s", paper_id, exc_info=True)


@router.get("/papers/{paper_id}/events")
async def paper_events(
    paper_id: uuid.UUID,
    request: Request,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    paper = await get_owned_paper(db, owner, paper_id)
    await db.commit()  # the stream reads the snapshot itself, after subscribing
    return StreamingResponse(
        _stream(request, db, paper.id), media_type="text/event-stream", headers=SSE_HEADERS
    )
