from types import SimpleNamespace

import httpx
import pytest
from fastapi import APIRouter, Depends
from sqlalchemy import select, update

from marcus.api.deps import client_ip, current_owner
from marcus.api.main import create_app
from marcus.core.db import get_db
from marcus.core.enums import OwnerKind, PriorityClass
from marcus.core.models import Owner
from marcus.core.tokens import hash_token, new_token

COOKIE = "marcus_owner"


def fake_request(peer, xff=None):
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


@pytest.fixture
def app(async_db_session):
    app = create_app()
    router = APIRouter()

    @router.get("/api/v2/_whoami")
    async def whoami(owner: Owner = Depends(current_owner)):
        return {"id": str(owner.id), "kind": owner.kind, "priority": owner.priority_class}

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


async def test_eleventh_new_owner_from_one_ip_in_an_hour_is_429(app):
    async with make_client(app) as c:
        for _ in range(10):
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


async def test_concurrent_new_owners_respect_the_ip_limit(migrated_db, app, async_db_session):
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
