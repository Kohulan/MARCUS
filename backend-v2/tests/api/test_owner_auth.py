from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select, update
from starlette.datastructures import Headers

from marcus.api.deps import client_ip, current_owner
from marcus.api.main import create_app
from marcus.core.db import get_db
from marcus.core.enums import OwnerKind, PriorityClass
from marcus.core.models import Owner
from marcus.core.settings import get_settings
from marcus.core.tokens import hash_token, new_token

COOKIE = "marcus_owner"


def fake_request(peer, xff=None):
    raw = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=Headers(raw=raw))


@pytest.fixture
def app(async_db_session):
    app = create_app()
    router = APIRouter()

    @router.get("/api/v2/_whoami")
    async def whoami(owner: Owner = Depends(current_owner)):
        return {"id": str(owner.id), "kind": owner.kind, "priority": owner.priority_class}

    @router.get("/api/v2/_file")
    async def file(owner: Owner = Depends(current_owner)):
        path = get_settings().data_root / "f.txt"
        path.write_text("file body")
        return FileResponse(path, media_type="text/plain")

    @router.get("/api/v2/_stream")
    async def stream(owner: Owner = Depends(current_owner)):
        async def body():
            yield "data: one\n\n"
            yield "data: two\n\n"

        return StreamingResponse(body(), media_type="text/event-stream")

    @router.get("/api/v2/_own_cookie")
    async def own_cookie(owner: Owner = Depends(current_owner)):
        response = Response("ok")
        response.set_cookie(COOKIE, "route-value", path="/api/v2")
        return response

    @router.get("/api/v2/_boom_after_owner")
    async def boom(owner: Owner = Depends(current_owner)):
        raise RuntimeError("late failure")

    app.include_router(router)

    async def _db():
        yield async_db_session

    app.dependency_overrides[get_db] = _db
    return app


def make_client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")


def test_token_helpers():
    t = new_token()
    assert len(t) >= 43 and new_token() != t
    h = hash_token("abc")
    assert h == hash_token("abc") and len(h) == 64 and h != "abc"


async def test_health_needs_no_owner(app):
    async with make_client(app) as c:
        r = await c.get("/api/v2/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert COOKIE not in r.cookies


async def test_first_request_sets_httponly_cookie(app):
    async with make_client(app) as c:
        r = await c.get("/api/v2/_whoami")
    assert r.status_code == 200
    assert r.json()["kind"] == "browser" and r.json()["priority"] == PriorityClass.BROWSER
    sc = r.headers["set-cookie"].lower()
    assert f"{COOKIE}=" in sc
    assert "httponly" in sc and "samesite=strict" in sc and "secure" in sc
    assert "path=/api/v2" in sc and "max-age=2592000" in sc


async def test_cookie_not_secure_when_disabled(app, monkeypatch, clear_settings_cache):
    monkeypatch.setenv("MARCUS_COOKIE_SECURE", "false")
    clear_settings_cache()
    async with make_client(app) as c:
        r = await c.get("/api/v2/_whoami")
    assert "secure" not in r.headers["set-cookie"].lower()


async def test_same_cookie_same_owner(app, async_db_session):
    async with make_client(app) as c:
        a = (await c.get("/api/v2/_whoami")).json()["id"]
        b = (await c.get("/api/v2/_whoami")).json()["id"]
    assert a == b
    n = len((await async_db_session.execute(select(Owner))).scalars().all())
    assert n == 1


async def test_unknown_cookie_gets_new_owner(app):
    async with make_client(app) as c:
        c.cookies.set(COOKIE, "nonsense", path="/api/v2")
        r = await c.get("/api/v2/_whoami")
    assert r.status_code == 200
    assert COOKIE in r.headers["set-cookie"]


async def test_api_key_owner_and_revoked_key_401(app, async_db_session):
    key = new_token()
    owner = Owner(
        kind=OwnerKind.API_KEY.value,
        token_hash=hash_token(key),
        priority_class=int(PriorityClass.API),
        label="t",
    )
    async_db_session.add(owner)
    await async_db_session.commit()
    async with make_client(app) as c:
        r = await c.get("/api/v2/_whoami", headers={"Authorization": f"Bearer {key}"})
        assert r.status_code == 200
        assert r.json()["id"] == str(owner.id) and r.json()["priority"] == PriorityClass.API
        assert "set-cookie" not in r.headers
        bad = await c.get("/api/v2/_whoami", headers={"Authorization": "Bearer nope"})
        assert bad.status_code == 401
        await async_db_session.execute(
            update(Owner).where(Owner.id == owner.id).values(revoked_at=owner.created_at)
        )
        await async_db_session.commit()
        gone = await c.get("/api/v2/_whoami", headers={"Authorization": f"Bearer {key}"})
        assert gone.status_code == 401


async def _new_used_owner(c) -> None:
    """A browser that keeps its cookie: first request creates the owner, the second uses it."""
    c.cookies.clear()
    first = await c.get("/api/v2/_whoami")
    assert first.status_code == 200
    again = await c.get("/api/v2/_whoami")
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]


async def test_eleventh_new_owner_from_one_ip_in_an_hour_is_429(app):
    async with make_client(app) as c:
        for _ in range(10):
            await _new_used_owner(c)
        c.cookies.clear()
        assert (await c.get("/api/v2/_whoami")).status_code == 429


async def test_first_return_is_recorded_within_the_minute(app, async_db_session):
    """The touch throttle must not hide an owner's first return: it marks the owner as used."""
    async with make_client(app) as c:
        first = await c.get("/api/v2/_whoami")
        created = (
            await async_db_session.execute(
                select(Owner.created_at, Owner.last_seen_at).execution_options(
                    populate_existing=True
                )
            )
        ).one()
        assert created.last_seen_at == created.created_at
        assert (await c.get("/api/v2/_whoami")).json()["id"] == first.json()["id"]
    after = (
        await async_db_session.execute(
            select(Owner.created_at, Owner.last_seen_at).execution_options(populate_existing=True)
        )
    ).one()
    assert after.last_seen_at > after.created_at


async def test_parallel_first_requests_do_not_use_up_new_owner_slots(app, async_db_session):
    """Review I8: a new browser's first page load fires several requests at once, each without
    a cookie; each gets an owner and the last cookie wins. The owners whose cookie was dropped
    never come back and must not count against the 10 new owners per address per hour."""
    async with make_client(app) as c:
        for _ in range(3):  # the siblings of one first load (the browser keeps one cookie)
            c.cookies.clear()
            assert (await c.get("/api/v2/_whoami")).status_code == 200
        for _ in range(10):
            await _new_used_owner(c)
        c.cookies.clear()
        assert (await c.get("/api/v2/_whoami")).status_code == 429


async def test_owners_collected_first_and_used_later_stay_at_ten(app, async_db_session):
    """Re-review N1: 100 cookie-less requests first (all owners unused, only the total cap
    applies), then each cookie used. Only 10 may become used owners; the 11th first return
    gets the same 429 as the creation limit and stays unused."""
    tokens = []
    async with make_client(app) as c:
        for _ in range(100):
            c.cookies.clear()
            r = await c.get("/api/v2/_whoami")
            assert r.status_code == 200
            tokens.append(owner_cookies(r)[0].split(";")[0].split("=", 1)[1])
        c.cookies.clear()
        assert (await c.get("/api/v2/_whoami")).status_code == 429  # total cap of 100
    codes = []
    for token in tokens:
        async with make_client(app) as c:
            c.cookies.set(COOKIE, token)
            codes.append((await c.get("/api/v2/_whoami")).status_code)
    assert codes == [200] * 10 + [429] * 90
    refused = await _httpx_detail(app, tokens[10])
    assert refused == {"detail": "Too many new sessions from this address"}
    # a used owner keeps working
    async with make_client(app) as c:
        c.cookies.set(COOKIE, tokens[0])
        assert (await c.get("/api/v2/_whoami")).status_code == 200
    used = (
        await async_db_session.execute(
            select(func.count())
            .select_from(Owner)
            .where(Owner.last_seen_at > Owner.created_at)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert used == 10


async def _httpx_detail(app, token) -> dict:
    async with make_client(app) as c:
        c.cookies.set(COOKIE, token)
        r = await c.get("/api/v2/_whoami")
    assert r.status_code == 429 and owner_cookies(r) == []
    return r.json()


async def test_a_used_owner_is_never_refused_on_its_first_return(app, async_db_session):
    """An owner already used by a cookie-less upload (it has a paper) passed the check when it
    was created: its first return is not counted again."""
    db = async_db_session
    tokens = []
    for _ in range(10):
        token = new_token()
        owner = Owner(
            kind=OwnerKind.BROWSER.value,
            token_hash=hash_token(token),
            priority_class=int(PriorityClass.BROWSER),
            created_ip="127.0.0.1",
        )
        db.add(owner)
        await db.commit()
        await db.run_sync(lambda s, o=owner: _paper_for(s, o))
        await db.commit()
        tokens.append(token)
    for token in tokens:
        async with make_client(app) as c:
            c.cookies.set(COOKIE, token)
            assert (await c.get("/api/v2/_whoami")).status_code == 200


async def test_an_owner_with_a_paper_counts_as_used(app, async_db_session):
    """A cookie-less upload creates the owner and its paper in one request: it counts."""
    db = async_db_session
    for _ in range(10):
        owner = Owner(
            kind=OwnerKind.BROWSER.value,
            token_hash=hash_token(new_token()),
            priority_class=int(PriorityClass.BROWSER),
            created_ip="127.0.0.1",
        )
        db.add(owner)
        await db.commit()
        await db.run_sync(lambda s, o=owner: _paper_for(s, o))
        await db.commit()
    async with make_client(app) as c:
        assert (await c.get("/api/v2/_whoami")).status_code == 429


def _paper_for(session, owner) -> None:
    from tests.factories import make_paper

    make_paper(session, session.merge(owner))


async def test_new_sessions_per_address_have_a_total_cap(app, monkeypatch, clear_settings_cache):
    """Owners never used are still rows: at most MARCUS_IP_MAX_NEW_SESSIONS_PER_HOUR per address
    per hour (default ten times the new-owner limit), so a cookie-less scanner cannot grow the
    owners table without bound."""
    assert get_settings().ip_max_new_sessions_per_hour == 100
    monkeypatch.setenv("MARCUS_IP_MAX_NEW_OWNERS_PER_HOUR", "2")
    clear_settings_cache()
    assert get_settings().ip_max_new_sessions_per_hour == 20
    monkeypatch.setenv("MARCUS_IP_MAX_NEW_SESSIONS_PER_HOUR", "5")
    clear_settings_cache()
    async with make_client(app) as c:
        for _ in range(5):
            c.cookies.clear()
            assert (await c.get("/api/v2/_whoami")).status_code == 200
        c.cookies.clear()
        assert (await c.get("/api/v2/_whoami")).status_code == 429


def test_xff_ignored_from_untrusted_peer(monkeypatch, clear_settings_cache):
    monkeypatch.setenv("MARCUS_TRUSTED_PROXIES", '["10.0.0.0/8"]')
    clear_settings_cache()
    assert client_ip(fake_request("203.0.113.9", "1.2.3.4")) == "203.0.113.9"


def test_xff_used_from_trusted_proxy(monkeypatch, clear_settings_cache):
    monkeypatch.setenv("MARCUS_TRUSTED_PROXIES", '["10.0.0.0/8", "192.168.1.1"]')
    clear_settings_cache()
    # spoofed left entry is ignored; right-most untrusted wins
    assert client_ip(fake_request("10.0.0.5", "9.9.9.9, 1.2.3.4, 10.0.0.7")) == "1.2.3.4"
    assert client_ip(fake_request("192.168.1.1", "1.2.3.4")) == "1.2.3.4"
    # all trusted, missing or invalid -> peer
    assert client_ip(fake_request("10.0.0.5", "10.0.0.6")) == "10.0.0.5"
    assert client_ip(fake_request("10.0.0.5")) == "10.0.0.5"
    assert client_ip(fake_request("10.0.0.5", "garbage")) == "10.0.0.5"


async def test_concurrent_new_owners_respect_the_ip_limit(
    migrated_db, app, async_db_session, monkeypatch, clear_settings_cache
):
    import asyncio

    from sqlalchemy import func
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from marcus.core.db import async_db_url
    from marcus.core.settings import get_settings

    engine = create_async_engine(
        async_db_url(get_settings().database_url), poolclass=NullPool
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _own_session():
        async with maker() as s:
            yield s

    # unused owners count against the total cap; the per-address lock must keep it exact
    monkeypatch.setenv("MARCUS_IP_MAX_NEW_SESSIONS_PER_HOUR", "10")
    clear_settings_cache()
    app.dependency_overrides[get_db] = _own_session
    try:
        async with make_client(app) as c:
            rs = await asyncio.gather(*(c.get("/api/v2/_whoami") for _ in range(30)))
    finally:
        await engine.dispose()
    codes = sorted(r.status_code for r in rs)
    assert codes == [200] * 10 + [429] * 20
    n = (await async_db_session.execute(select(func.count()).select_from(Owner))).scalar_one()
    assert n == 10


# --- the new-owner cookie reaches the client on any response ----------------------------


def owner_cookies(r: httpx.Response) -> list[str]:
    return [v for v in r.headers.get_list("set-cookie") if v.startswith(f"{COOKIE}=")]


def assert_owner_cookie(r: httpx.Response) -> None:
    (sc,) = owner_cookies(r)
    low = sc.lower()
    assert "httponly" in low and "samesite=strict" in low and "secure" in low
    assert "path=/api/v2" in low and "max-age=2592000" in low


async def owner_ids(db) -> list[str]:
    return [str(i) for i in (await db.execute(select(Owner.id))).scalars()]


async def assert_cookie_maps_to_the_new_owner(c, db) -> None:
    (created,) = await owner_ids(db)
    r = await c.get("/api/v2/_whoami")
    assert r.status_code == 200 and r.json()["id"] == created
    # a known cookie is never swapped for another token (its first return renews it once)
    token = c.cookies.get(COOKIE)
    assert all(v.startswith(f"{COOKIE}={token};") for v in owner_cookies(r))
    assert await owner_ids(db) == [created]


@pytest.mark.parametrize(
    "path,status",
    [
        ("/api/v2/papers/00000000-0000-0000-0000-000000000000", 404),
        ("/api/v2/_file", 200),
        ("/api/v2/_stream", 200),
        ("/api/v2/_boom_after_owner", 500),
    ],
)
async def test_new_owner_cookie_on_any_response(app, async_db_session, path, status):
    async with make_client(app) as c:
        r = await c.get(path)
        assert r.status_code == status
        assert_owner_cookie(r)
        await assert_cookie_maps_to_the_new_owner(c, async_db_session)


async def test_new_owner_cookie_on_413(app, async_db_session):
    big = b"%PDF-1.4\n" + b"0" * (20 * 1024 * 1024 + 1)
    async with make_client(app) as c:
        r = await c.post("/api/v2/papers", files={"file": ("p.pdf", big, "application/pdf")})
        assert r.status_code == 413
        assert_owner_cookie(r)
        await assert_cookie_maps_to_the_new_owner(c, async_db_session)


async def test_new_owner_cookie_on_429(app, async_db_session, monkeypatch, clear_settings_cache):
    monkeypatch.setenv("MARCUS_IP_MAX_ACTIVE_PAPERS", "1")
    clear_settings_cache()
    pdf = b"%PDF-1.4\n" + b"0" * 100
    async with make_client(app) as first:
        assert (await first.post("/api/v2/papers", files={"file": ("p.pdf", pdf)})).status_code == 202
    async with make_client(app) as c:
        r = await c.post("/api/v2/papers", files={"file": ("p.pdf", pdf)})
        assert r.status_code == 429 and "address" in r.json()["detail"]
        assert_owner_cookie(r)
        new_id = (await c.get("/api/v2/_whoami")).json()["id"]
    assert len(await owner_ids(async_db_session)) == 2 and new_id in await owner_ids(
        async_db_session
    )


async def test_route_cookie_is_not_duplicated(app):
    async with make_client(app) as c:
        r = await c.get("/api/v2/_own_cookie")
    assert owner_cookies(r) == [r.headers["set-cookie"]]
    assert "route-value" in r.headers["set-cookie"]


async def test_one_cookie_on_a_plain_json_response(app):
    async with make_client(app) as c:
        r = await c.get("/api/v2/_whoami")
    assert_owner_cookie(r)


# --- last_seen_at is written at most once a minute ----------------------------------------


async def _set_last_seen(db, owner_id, when) -> None:
    await db.execute(update(Owner).where(Owner.id == owner_id).values(last_seen_at=when))
    await db.commit()


async def _last_seen(db, owner_id) -> datetime:
    return (
        await db.execute(
            select(Owner.last_seen_at)
            .where(Owner.id == owner_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def test_last_seen_at_is_throttled(app, async_db_session):
    db = async_db_session
    token = new_token()
    owner = Owner(
        kind=OwnerKind.BROWSER.value,
        token_hash=hash_token(token),
        priority_class=int(PriorityClass.BROWSER),
    )
    db.add(owner)
    await db.commit()
    await db.execute(  # an owner that has been used before (see test_first_return_is_recorded)
        update(Owner)
        .where(Owner.id == owner.id)
        .values(created_at=datetime.now(UTC) - timedelta(days=1))
    )
    recent = datetime.now(UTC) - timedelta(seconds=30)
    await _set_last_seen(db, owner.id, recent)
    async with make_client(app) as c:
        c.cookies.set(COOKIE, token)
        assert (await c.get("/api/v2/_whoami")).status_code == 200
        assert await _last_seen(db, owner.id) == recent  # under a minute: no write
        stale = datetime.now(UTC) - timedelta(seconds=120)
        await _set_last_seen(db, owner.id, stale)
        before = datetime.now(UTC) - timedelta(seconds=5)
        assert (await c.get("/api/v2/_whoami")).status_code == 200
    assert await _last_seen(db, owner.id) >= before
    n = (await db.execute(select(func.count()).select_from(Owner))).scalar_one()
    assert n == 1


# --- the cookie's expiry slides: renewed on use (at most once a minute) --------------------


async def test_known_owner_cookie_is_renewed_on_use(app, async_db_session):
    """A returning curator keeps the same owner: the cookie gets a fresh Max-Age when the
    owner is seen again (with the touch, at most once a minute), not only when created."""
    db = async_db_session
    token = new_token()
    owner = Owner(
        kind=OwnerKind.BROWSER.value,
        token_hash=hash_token(token),
        priority_class=int(PriorityClass.BROWSER),
    )
    db.add(owner)
    await db.commit()
    await _set_last_seen(db, owner.id, datetime.now(UTC) - timedelta(days=29))
    async with make_client(app) as c:
        c.cookies.set(COOKIE, token)
        r = await c.get("/api/v2/_whoami")
        assert r.status_code == 200 and r.json()["id"] == str(owner.id)
        cookies = owner_cookies(r)
        assert len(cookies) == 1
        sc = cookies[0].lower()
        assert sc.startswith(f"{COOKIE}={token}".lower())
        assert "httponly" in sc and "samesite=strict" in sc and "secure" in sc
        assert "path=/api/v2" in sc and "max-age=2592000" in sc
        # seen under a minute ago: no second Set-Cookie on every request
        r2 = await c.get("/api/v2/_whoami")
        assert r2.status_code == 200 and owner_cookies(r2) == []
    n = (await db.execute(select(func.count()).select_from(Owner))).scalar_one()
    assert n == 1


async def test_renewed_cookie_on_a_file_response(app, async_db_session):
    db = async_db_session
    token = new_token()
    owner = Owner(
        kind=OwnerKind.BROWSER.value,
        token_hash=hash_token(token),
        priority_class=int(PriorityClass.BROWSER),
    )
    db.add(owner)
    await db.commit()
    await _set_last_seen(db, owner.id, datetime.now(UTC) - timedelta(hours=1))
    async with make_client(app) as c:
        c.cookies.set(COOKIE, token)
        r = await c.get("/api/v2/_file")
    assert r.status_code == 200
    assert [v.split(";")[0] for v in owner_cookies(r)] == [f"{COOKIE}={token}"]

