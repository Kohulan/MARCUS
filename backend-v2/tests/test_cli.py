import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from marcus.api.main import create_app
from marcus.cli import main
from marcus.core import storage
from marcus.core.db import async_db_url, get_db
from marcus.core.enums import OwnerKind, PriorityClass
from marcus.core.models import ImageJob, Owner, Paper, Step
from marcus.core.settings import get_settings
from marcus.core.tokens import hash_token
from tests.api.conftest import _dispatcher_alive, _limiter_redis  # noqa: F401 (autouse)
from tests.api.test_images import image_bytes
from tests.factories import make_owner, make_paper


def run(capsys, *argv) -> tuple[int, str, str]:
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def create_key(capsys, *extra, label="lab") -> tuple[str, str]:
    code, out, _ = run(capsys, "apikey", "create", "--label", label, *extra)
    assert code == 0
    fields = dict(line.split(": ", 1) for line in out.splitlines())
    return fields["id"], fields["key"]


def test_create_prints_key_once_and_stores_hash_only(db_session, capsys):
    code, out, err = run(capsys, "apikey", "create", "--label", "my lab", "--daily-pages", "50")
    assert code == 0
    key = dict(line.split(": ", 1) for line in out.splitlines())["key"]
    assert key.startswith("mk_") and out.count(key) == 1 and key not in err
    owner = db_session.execute(select(Owner)).scalar_one()
    assert owner.kind == OwnerKind.API_KEY.value
    assert owner.priority_class == int(PriorityClass.API)
    assert (owner.label, owner.daily_page_quota) == ("my lab", 50)
    assert owner.token_hash == hash_token(key) and key not in owner.token_hash
    code, out, _ = run(capsys, "apikey", "list")
    assert key not in out and owner.token_hash not in out


def test_create_defaults_and_validation(db_session, capsys):
    create_key(capsys)
    assert db_session.execute(select(Owner.daily_page_quota)).scalar_one() == 2000
    assert run(capsys, "apikey", "create", "--label", "x" * 101)[0] == 1
    assert run(capsys, "apikey", "create", "--label", "  ")[0] == 1
    assert run(capsys, "apikey", "create", "--label", "a", "--daily-pages", "0")[0] == 1
    assert db_session.execute(select(Owner)).scalars().all().__len__() == 1


def test_usage_errors_exit_2(db_session, capsys):
    assert run(capsys, "apikey", "create")[0] == 2  # label required
    assert run(capsys, "purge")[0] == 2
    assert run(capsys, "purge", "--paper", "x", "--expired")[0] == 2
    assert run(capsys, "nonsense")[0] == 2
    assert run(capsys)[0] == 2


def test_list_prints_no_secrets_and_json(db_session, capsys):
    key_id, key = create_key(capsys, label="lab")
    browser = make_owner(db_session)
    db_session.commit()
    code, out, _ = run(capsys, "apikey", "list", "--json")
    rows = json.loads(out)
    assert code == 0 and len(rows) == 1  # browser owners are not keys
    row = rows[0]
    assert set(row) == {
        "id", "label", "created_at", "revoked_at", "daily_page_quota", "pages_today"
    }
    assert row["id"] == key_id and row["pages_today"] == 0 and row["revoked_at"] is None
    token_hash = hash_token(key)
    code, text, _ = run(capsys, "apikey", "list")
    assert key not in out + text and token_hash not in out + text and str(browser.id) not in text
    assert key_id in text and "'lab'" in text


def test_revoke_idempotent_and_exit_codes(db_session, capsys):
    key_id, _ = create_key(capsys)
    assert run(capsys, "apikey", "revoke", key_id)[0] == 0
    db_session.expire_all()
    first = db_session.get(Owner, uuid.UUID(key_id)).revoked_at
    assert first is not None
    code, out, _ = run(capsys, "apikey", "revoke", key_id)
    assert code == 0 and "already revoked" in out
    db_session.expire_all()
    assert db_session.get(Owner, uuid.UUID(key_id)).revoked_at == first
    assert run(capsys, "apikey", "revoke", str(uuid.uuid4()))[0] == 1
    assert run(capsys, "apikey", "revoke", "not-a-uuid")[0] == 1
    browser = make_owner(db_session)
    db_session.commit()
    assert run(capsys, "apikey", "revoke", str(browser.id))[0] == 1  # not an API key


@pytest.fixture
def app(async_db_session):
    app = create_app()

    async def _db():
        yield async_db_session

    app.dependency_overrides[get_db] = _db
    return app


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")


def pdf() -> bytes:
    return b"%PDF-1.4\n" + b"0" * 2048


def bearer(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


async def post_paper(c, key):
    return await c.post(
        "/api/v2/papers", files={"file": ("p.pdf", pdf(), "application/pdf")}, headers=bearer(key)
    )


async def test_revoked_key_401(app, db_session, capsys):
    key_id, key = await asyncio.to_thread(create_key, capsys)
    async with client(app) as c:
        assert (await c.get("/api/v2/papers", headers=bearer(key))).status_code == 200
        assert await asyncio.to_thread(run, capsys, "apikey", "revoke", key_id) == (
            0, f"revoked {key_id}\n", ""
        )
        assert (await c.get("/api/v2/papers", headers=bearer(key))).status_code == 401
        assert (await post_paper(c, key)).status_code == 401


async def test_quota_exceeded_429(app, async_db_session, db_session, capsys):
    _, key = await asyncio.to_thread(create_key, capsys, "--daily-pages", "2")
    async with client(app) as c:
        first = await post_paper(c, key)
        assert first.status_code == 202  # 0 used
        second = await post_paper(c, key)
        assert second.status_code == 202  # 1 (still checking) used < 2
        third = await post_paper(c, key)
        assert third.status_code == 429
        assert third.json() == {"detail": "daily quota exceeded"}
        assert (await async_db_session.execute(select(Paper))).scalars().all().__len__() == 2
        # check_pdf reports real page counts: 2 papers x 3 pages = 6 >= 2
        await async_db_session.execute(update(Paper).values(pages=3, status="processing"))
        await async_db_session.commit()
        assert (await post_paper(c, key)).status_code == 429


async def test_quota_counts_known_pages_not_one_per_paper(app, async_db_session, capsys):
    _, key = await asyncio.to_thread(create_key, capsys, "--daily-pages", "10")
    async with client(app) as c:
        assert (await post_paper(c, key)).status_code == 202
        await async_db_session.execute(update(Paper).values(pages=9, status="processing"))
        await async_db_session.commit()
        assert (await post_paper(c, key)).status_code == 202  # 9 < 10 (may overshoot)
        assert (await post_paper(c, key)).status_code == 429  # 9 + 1 checking >= 10


async def test_quota_counts_only_today_and_own_papers(app, async_db_session, capsys):
    _, key = await asyncio.to_thread(create_key, capsys, "--daily-pages", "1")
    async with client(app) as c:
        assert (await post_paper(c, key)).status_code == 202
        assert (await post_paper(c, key)).status_code == 429
        await async_db_session.execute(
            update(Paper).values(created_at=datetime.now(UTC) - timedelta(days=2))
        )
        await async_db_session.commit()
        assert (await post_paper(c, key)).status_code == 202  # yesterday's does not count
        _, other = await asyncio.to_thread(create_key, capsys, "--daily-pages", "1")
        assert (await post_paper(c, other)).status_code == 202  # another key's own quota


async def test_browser_owner_not_subject_to_quota(app, async_db_session):
    async with client(app) as c:
        r = await c.post("/api/v2/papers", files={"file": ("p.pdf", pdf(), "application/pdf")})
        assert r.status_code == 202
    owner = (await async_db_session.execute(select(Owner))).scalar_one()
    assert owner.daily_page_quota is None


async def test_image_jobs_count_one_page(app, async_db_session, db_session, capsys):
    _, key = await asyncio.to_thread(create_key, capsys, "--daily-pages", "2")
    async with client(app) as c:
        for expected in (202, 202, 429):
            r = await c.post(
                "/api/v2/images",
                files={"file": ("a.png", image_bytes(), "image/png")},
                headers=bearer(key),
            )
            assert r.status_code == expected
        assert (await async_db_session.execute(select(ImageJob))).scalars().all().__len__() == 2
        # a paper also finds the image jobs already used the quota
        assert (await post_paper(c, key)).status_code == 429


async def test_quota_race_concurrent_uploads_cannot_exceed(migrated_db, db_session, capsys):
    """Several uploads of one key at once, each in its own transaction: with quota 3 exactly
    3 succeed (the owner advisory lock serialises the check and the insert)."""
    _, key = create_key(capsys, "--daily-pages", "3")
    engine = create_async_engine(async_db_url(get_settings().database_url), poolclass=NullPool)
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _db():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    try:
        async with client(app) as c:
            results = await asyncio.gather(*[post_paper(c, key) for _ in range(8)])
    finally:
        await engine.dispose()
    codes = sorted(r.status_code for r in results)
    assert codes == [202] * 3 + [429] * 5
    assert db_session.execute(select(Paper)).scalars().all().__len__() == 3


def test_purge_paper_with_running_step(db_session, capsys):
    paper = make_paper(db_session)
    step = db_session.execute(select(Step).where(Step.paper_id == paper.id)).scalar_one()
    step.status = "running"
    step.attempts = 1
    other = make_paper(db_session)
    db_session.commit()
    paper_id, step_id, other_id = paper.id, step.id, other.id
    paper_dir = storage.paper_dir(paper_id)
    assert paper_dir.exists()
    code, out, _ = run(capsys, "purge", "--paper", str(paper_id))
    assert code == 0 and str(paper_id) in out
    db_session.expire_all()
    assert db_session.get(Paper, paper_id) is None
    assert db_session.get(Step, step_id) is None  # cascaded
    assert not paper_dir.exists()
    assert db_session.get(Paper, other_id) is not None and storage.paper_dir(other_id).exists()


def test_purge_paper_exit_codes(db_session, capsys):
    assert run(capsys, "purge", "--paper", str(uuid.uuid4()))[0] == 1
    assert run(capsys, "purge", "--paper", "nope")[0] == 1


def test_purge_expired_runs_once_and_prints_report(db_session, capsys):
    old = make_paper(db_session)
    fresh = make_paper(db_session)
    old.expires_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()
    old_id, fresh_id = old.id, fresh.id
    code, out, _ = run(capsys, "purge", "--expired")
    assert code == 0 and "papers: 1" in out
    db_session.expire_all()
    assert db_session.get(Paper, old_id) is None
    assert db_session.get(Paper, fresh_id) is not None
