"""SSE route. httpx's ASGITransport buffers whole responses, so these tests drive the ASGI app
directly: `receive` hands out the request, then blocks until the test "disconnects".
"""

import asyncio
import json
import logging

import fakeredis
import fakeredis.aioredis
import pydantic
import pytest
import redis.asyncio as aioredis

from marcus.api.deps import COOKIE_NAME
from marcus.api.routes import events as events_route
from marcus.core.events import paper_channel
from marcus.core.pipeline import cancel_paper
from marcus.core.settings import Settings, get_settings
from tests.api.conftest import (
    finish,
    make_client,
    new_owner,
    ocsr_result,
    seed_paper,
    steps_of,
)

WAIT = 5.0


@pytest.fixture
def redis_server(monkeypatch):
    server = fakeredis.FakeServer()
    monkeypatch.setattr(
        events_route, "redis_client", lambda: fakeredis.aioredis.FakeRedis(server=server)
    )
    return server


@pytest.fixture
def fast_ping(monkeypatch):
    monkeypatch.setenv("MARCUS_SSE_PING_INTERVAL_S", "0.2")
    get_settings.cache_clear()


class SSE:
    def __init__(self, app, path: str, token: str, spec_version: str = "2.4"):
        self.sent: asyncio.Queue = asyncio.Queue()
        self.gone = asyncio.Event()
        self._first = True
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": spec_version},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"test"),
                (b"cookie", f"{COOKIE_NAME}={token}".encode()),
                (b"accept", b"text/event-stream"),
            ],
            "client": ("127.0.0.1", 50000),
            "server": ("test", 443),
        }
        self.task = asyncio.create_task(app(scope, self._receive, self._send))

    async def _receive(self):
        if self._first:
            self._first = False
            return {"type": "http.request", "body": b"", "more_body": False}
        await self.gone.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message):
        await self.sent.put(message)

    async def start(self) -> dict:
        msg = await asyncio.wait_for(self.sent.get(), WAIT)
        assert msg["type"] == "http.response.start"
        return {
            "status": msg["status"],
            "headers": {k.decode().lower(): v.decode() for k, v in msg["headers"]},
        }

    async def chunk(self) -> str:
        msg = await asyncio.wait_for(self.sent.get(), WAIT)
        assert msg["type"] == "http.response.body"
        return msg["body"].decode()

    async def rest(self) -> str:
        """Everything the server still sends until it ends the response by itself."""
        out = []
        while True:
            msg = await asyncio.wait_for(self.sent.get(), WAIT)
            assert msg["type"] == "http.response.body"
            out.append(msg["body"].decode())
            if not msg.get("more_body", False):
                break
        await asyncio.wait_for(self.task, WAIT)  # finished without a client disconnect
        return "".join(out)

    async def disconnect(self) -> None:
        self.gone.set()
        await asyncio.wait_for(self.task, WAIT)


def parse_snapshot(text: str) -> dict:
    lines = text.split("\n")
    assert lines[0] == "event: snapshot" and text.endswith("\n\n")
    assert lines[1].startswith("data: ")
    return json.loads(lines[1][len("data: ") :])


def subscribers(server, channel: str) -> int:
    return dict(fakeredis.FakeRedis(server=server).pubsub_numsub(channel))[channel.encode()]


@pytest.mark.parametrize("spec_version", ["2.0", "2.4"])
async def test_snapshot_events_ping_and_cleanup(
    app, async_db_session, redis_server, fast_ping, spec_version
):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    channel = paper_channel(seeded.paper_id)

    sse = SSE(app, f"/api/v2/papers/{seeded.paper_id}/events", token, spec_version)
    head = await sse.start()
    assert head["status"] == 200
    assert head["headers"]["content-type"].startswith("text/event-stream")
    assert head["headers"]["cache-control"] == "no-cache"
    assert head["headers"]["x-accel-buffering"] == "no"

    snap = parse_snapshot(await sse.chunk())
    assert snap == {
        "status": "processing",
        "counts": {"steps_by_status": {"done": 5, "pending": 2}},
    }
    assert subscribers(redis_server, channel) == 1
    # the open stream holds no database transaction (no pooled connection per listener)
    assert not db.in_transaction()

    event = {"step_id": "x", "kind": "doi", "status": "done"}
    fakeredis.FakeRedis(server=redis_server).publish(channel, json.dumps(event))
    fakeredis.FakeRedis(server=redis_server).publish(channel, "not json\n\ndata: forged")
    fakeredis.FakeRedis(server=redis_server).publish(channel, json.dumps([1]))  # not an object
    fakeredis.FakeRedis(server=redis_server).publish(channel, json.dumps({"status": ["x"]}))
    fakeredis.FakeRedis(server=redis_server).publish(channel, json.dumps({"multi": "a\nb"}))
    assert await sse.chunk() == f"data: {json.dumps(event)}\n\n"
    # a malformed message is dropped; an odd status does not break the stream; newlines
    # inside JSON strings stay escaped
    assert await sse.chunk() == 'data: {"status": ["x"]}\n\n'
    assert await sse.chunk() == 'data: {"multi": "a\\nb"}\n\n'
    assert await sse.chunk() == ": ping\n\n"

    await sse.disconnect()
    assert subscribers(redis_server, channel) == 0


async def test_event_racing_the_snapshot_is_delivered(
    app, async_db_session, redis_server, monkeypatch
):
    """A worker event published after the subscribe but before the snapshot is read must
    reach the client (after the snapshot; it may duplicate what the snapshot shows)."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    channel = paper_channel(seeded.paper_id)
    racing = {"step_id": "r", "kind": "doi", "status": "done"}
    original = events_route._snapshot
    calls = []

    async def publish_then_snapshot(session, paper_id):
        calls.append(subscribers(redis_server, channel))
        fakeredis.FakeRedis(server=redis_server).publish(channel, json.dumps(racing))
        return await original(session, paper_id)

    monkeypatch.setattr(events_route, "_snapshot", publish_then_snapshot)
    sse = SSE(app, f"/api/v2/papers/{seeded.paper_id}/events", token)
    assert (await sse.start())["status"] == 200
    assert parse_snapshot(await sse.chunk())["status"] == "processing"
    assert await sse.chunk() == f"data: {json.dumps(racing)}\n\n"
    await sse.disconnect()
    assert calls == [1]  # the snapshot was read while already subscribed


async def test_state_complete_after_sse_disconnect(app, async_db_session, redis_server):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)  # 2 ocsr + docling + doi pending

    sse = SSE(app, f"/api/v2/papers/{seeded.paper_id}/events", token)
    assert (await sse.start())["status"] == 200
    assert parse_snapshot(await sse.chunk())["status"] == "processing"
    await sse.disconnect()

    def finish_rest(s):
        for st in steps_of(s, seeded.paper_id, status="pending"):
            result = {
                "ocsr": ocsr_result("c1ccccc1"),
                "doi": {"doi": "10.1/x"},
                "docling": {},
            }[st.kind]
            finish(s, st, result)

    await db.run_sync(finish_rest)
    await db.commit()

    async with make_client(app, token) as c:
        r = await c.get(f"/api/v2/papers/{seeded.paper_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done" and body["doi"] == "10.1/x"
    assert body["counts"]["steps_by_status"] == {"done": 7}
    assert [len(s["predictions"]) for s in body["segments"]] == [1, 1]
    assert {p["smiles"] for s in body["segments"] for p in s["predictions"]} == {"c1ccccc1"}


async def test_events_not_owned_is_404_without_subscribing(app, async_db_session, redis_server):
    db = async_db_session
    alice, _ = await new_owner(db)
    _, bob_token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, bob_token) as c:
        r = await c.get(f"/api/v2/papers/{seeded.paper_id}/events")
    assert r.status_code == 404 and r.json() == {"detail": "not found"}
    assert subscribers(redis_server, paper_channel(seeded.paper_id)) == 0


# --- limits: streams per owner, end of stream, Redis trouble --------------------------------

END_DONE = 'event: end\ndata: {"status": "done"}\n\n'


def finish_pending(s, paper_id) -> None:
    for st in steps_of(s, paper_id, status="pending"):
        result = {"ocsr": ocsr_result(), "doi": {"doi": "10.1/x"}, "docling": {}}[st.kind]
        finish(s, st, result)


def slot_key(owner) -> str:
    return f"sse:{owner.id}"


async def test_at_most_four_streams_per_owner(app, async_db_session, redis_server):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    path = f"/api/v2/papers/{seeded.paper_id}/events"
    r = fakeredis.aioredis.FakeRedis(server=redis_server)
    streams = []
    for _ in range(4):
        sse = SSE(app, path, token)
        assert (await sse.start())["status"] == 200
        parse_snapshot(await sse.chunk())
        streams.append(sse)
    assert int(await r.get(slot_key(alice))) == 4
    assert 0 < await r.ttl(slot_key(alice)) <= 60  # a crashed process cannot hold slots forever

    fifth = SSE(app, path, token)
    assert (await fifth.start())["status"] == 429
    assert json.loads(await fifth.rest()) == {"detail": "Too many open event streams"}
    assert int(await r.get(slot_key(alice))) == 4  # the refused stream took no slot

    await streams.pop().disconnect()
    assert int(await r.get(slot_key(alice))) == 3
    again = SSE(app, path, token)
    assert (await again.start())["status"] == 200
    streams.append(again)
    for sse in streams:
        await sse.disconnect()
    assert int(await r.get(slot_key(alice)) or 0) == 0


async def test_stream_slot_ttl_refreshed_on_ping(app, async_db_session, redis_server, fast_ping):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    r = fakeredis.aioredis.FakeRedis(server=redis_server)
    sse = SSE(app, f"/api/v2/papers/{seeded.paper_id}/events", token)
    assert (await sse.start())["status"] == 200
    parse_snapshot(await sse.chunk())
    await r.expire(slot_key(alice), 5)
    assert await sse.chunk() == ": ping\n\n"
    assert 5 < await r.ttl(slot_key(alice)) <= 60
    await sse.disconnect()


async def test_stream_ends_after_terminal_event(app, async_db_session, redis_server):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    channel = paper_channel(seeded.paper_id)
    sse = SSE(app, f"/api/v2/papers/{seeded.paper_id}/events", token)
    assert (await sse.start())["status"] == 200
    assert parse_snapshot(await sse.chunk())["status"] == "processing"

    await db.run_sync(lambda s: finish_pending(s, seeded.paper_id))
    await db.commit()
    last = {"type": "step", "step_id": "z", "kind": "doi", "status": "done"}
    fakeredis.FakeRedis(server=redis_server).publish(channel, json.dumps(last))
    # the terminal event is forwarded, then an `end` frame, then the server closes
    assert await sse.chunk() == f"data: {json.dumps(last)}\n\n"
    assert await sse.rest() == END_DONE
    assert subscribers(redis_server, channel) == 0
    r = fakeredis.aioredis.FakeRedis(server=redis_server)
    assert int(await r.get(slot_key(alice)) or 0) == 0


async def test_stream_of_a_finished_paper_ends_after_snapshot(app, async_db_session, redis_server):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    await db.run_sync(lambda s: finish_pending(s, seeded.paper_id))
    await db.commit()
    sse = SSE(app, f"/api/v2/papers/{seeded.paper_id}/events", token)
    assert (await sse.start())["status"] == 200
    assert parse_snapshot(await sse.chunk())["status"] == "done"
    assert await sse.rest() == END_DONE


async def test_stream_ends_when_paper_is_deleted(
    app, async_db_session, redis_server, fast_ping, migrated_db
):
    """Deletion publishes no event: the status is re-read on each ping."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from marcus.core.db import async_db_url

    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    sse = SSE(app, f"/api/v2/papers/{seeded.paper_id}/events", token)
    assert (await sse.start())["status"] == 200
    parse_snapshot(await sse.chunk())
    engine = create_async_engine(async_db_url(get_settings().database_url), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine)() as other:
            await other.run_sync(lambda s: cancel_paper(s, seeded.paper_id))
            await other.commit()
    finally:
        await engine.dispose()
    tail = await sse.rest()
    assert tail.endswith('event: end\ndata: {"status": "deleted"}\n\n')
    assert set(tail.split("\n\n")[:-2]) <= {": ping"}


async def test_stream_ends_after_max_duration(app, async_db_session, redis_server, monkeypatch):
    monkeypatch.setenv("MARCUS_SSE_MAX_DURATION_S", "0.3")
    get_settings.cache_clear()
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    sse = SSE(app, f"/api/v2/papers/{seeded.paper_id}/events", token)
    assert (await sse.start())["status"] == 200
    parse_snapshot(await sse.chunk())
    assert "event: end" not in await sse.rest()  # not finished: the client may reconnect
    assert subscribers(redis_server, paper_channel(seeded.paper_id)) == 0


async def test_redis_down_stream_says_retry_later(app, async_db_session, monkeypatch, caplog):
    dead = aioredis.Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    monkeypatch.setattr(events_route, "redis_client", lambda: dead)
    caplog.set_level(logging.WARNING, logger="marcus.api.routes.events")
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    try:
        sse = SSE(app, f"/api/v2/papers/{seeded.paper_id}/events", token)
        assert (await sse.start())["status"] == 200  # the slot count fails open
        assert await sse.chunk() == "retry: 15000\n\n"
        frame = await sse.chunk()
        assert frame.startswith("event: error\ndata: ") and frame.endswith("\n\n")
        assert await sse.rest() == ""
    finally:
        await dead.aclose()
    messages = [rec.getMessage() for rec in caplog.records]
    assert any("stream slot" in m for m in messages)
    assert any("lost Redis" in m for m in messages)


@pytest.mark.parametrize("bad", ["0", "-1"])
def test_ping_interval_must_be_positive(monkeypatch, bad):
    monkeypatch.setenv("MARCUS_SSE_PING_INTERVAL_S", bad)
    with pytest.raises(pydantic.ValidationError):
        Settings()


def test_events_redis_pool_is_bounded(monkeypatch):
    events_route.redis_client.cache_clear()
    try:
        assert events_route.redis_client().connection_pool.max_connections == 200
        monkeypatch.setenv("MARCUS_EVENTS_REDIS_MAX_CONNECTIONS", "7")
        get_settings.cache_clear()
        events_route.redis_client.cache_clear()
        assert events_route.redis_client().connection_pool.max_connections == 7
    finally:
        events_route.redis_client.cache_clear()
