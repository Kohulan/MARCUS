import httpx
import pytest
from sqlalchemy import select

from marcus.api.main import create_app
from marcus.api.uploads import sanitize_display_name
from marcus.core.db import get_db
from marcus.core.models import Paper, Step
from marcus.core.settings import get_settings
from tests.api._upload_helpers import pdf_bytes, upload, upload_image

MB = 1024 * 1024


@pytest.fixture
def app(async_db_session):
    app = create_app()

    async def _db():
        yield async_db_session

    app.dependency_overrides[get_db] = _db
    return app


def make_client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")


async def test_upload_returns_202_and_one_check_pdf_step(app, async_db_session):
    async with make_client(app) as c:
        r = await upload(c)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "checking"
    assert "marcus_owner=" in r.headers["set-cookie"]
    paper = (await async_db_session.execute(select(Paper))).scalar_one()
    assert str(paper.id) == body["paper_id"]
    assert paper.engine == "decimer" and paper.ocsr_mode == "auto"
    assert paper.bytes == 2048 and len(paper.pdf_sha256) == 64
    assert paper.display_name == "paper.pdf"
    steps = (await async_db_session.execute(select(Step))).scalars().all()
    assert len(steps) == 1
    s = steps[0]
    assert (s.kind, s.queue, s.seq, s.status) == ("check_pdf", "q.cpu", 0, "pending")
    assert s.paper_id == paper.id
    pdf = get_settings().data_root / "papers" / str(paper.id) / "source.pdf"
    assert pdf.read_bytes() == pdf_bytes()
    assert pdf.stat().st_mode & 0o777 == 0o600


async def test_20mb_plus_one_byte_is_413(app, async_db_session):
    async with make_client(app) as c:
        r = await upload(c, pdf_bytes(20 * MB + 1))
    assert r.status_code == 413
    assert (await async_db_session.execute(select(Paper))).first() is None
    assert not (get_settings().data_root / "papers").exists()


async def test_exactly_20mb_is_accepted(app):
    async with make_client(app) as c:
        r = await upload(c, pdf_bytes(20 * MB))
    assert r.status_code == 202


async def test_png_named_pdf_is_415(app):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    async with make_client(app) as c:
        r = await upload(c, png, name="x.pdf")
    assert r.status_code == 415


async def test_traversal_filename_never_reaches_disk(app, async_db_session):
    async with make_client(app) as c:
        r = await upload(c, name="../../../tmp/evil.pdf")
    assert r.status_code == 202
    root = get_settings().data_root
    paper = (await async_db_session.execute(select(Paper))).scalar_one()
    assert paper.display_name == "evil.pdf"
    assert (root / "papers" / str(paper.id) / "source.pdf").is_file()
    files = [p.relative_to(root) for p in root.rglob("*") if p.is_file()]
    assert [str(f) for f in files] == [f"papers/{paper.id}/source.pdf"]
    assert not (root / "tmp" / "evil.pdf").exists()
    assert not (root.parent / "tmp" / "evil.pdf").exists()


async def test_fourth_active_paper_is_429(app):
    async with make_client(app) as c:
        for _ in range(3):
            assert (await upload(c)).status_code == 202
        r = await upload(c)
    assert r.status_code == 429


async def test_per_ip_limit_is_429(app, async_db_session, monkeypatch):
    monkeypatch.setenv("MARCUS_IP_MAX_ACTIVE_PAPERS", "2")
    monkeypatch.setenv("MARCUS_BROWSER_MAX_ACTIVE_PAPERS", "5")
    get_settings.cache_clear()
    async with make_client(app) as c1, make_client(app) as c2:
        assert (await upload(c1)).status_code == 202
        assert (await upload(c2)).status_code == 202
        assert (await upload(c2)).status_code == 429


async def _expire_everything(db) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from marcus.core.models import ImageJob

    past = datetime.now(UTC) - timedelta(seconds=1)
    await db.execute(update(Paper).values(expires_at=past))
    await db.execute(update(ImageJob).values(expires_at=past))
    await db.commit()


async def test_expired_active_work_does_not_count_for_the_owner(app, async_db_session):
    """Expired papers/jobs are gone for the client (404) even before the purge: they must not
    keep holding the owner's active slots either."""
    async with make_client(app) as c:
        for _ in range(2):
            assert (await upload(c)).status_code == 202
        assert (await upload_image(c)).status_code == 202
        assert (await upload(c)).status_code == 429
        await _expire_everything(async_db_session)
        assert (await upload(c)).status_code == 202


async def test_expired_active_work_does_not_count_for_the_ip(app, async_db_session, monkeypatch):
    monkeypatch.setenv("MARCUS_IP_MAX_ACTIVE_PAPERS", "2")
    monkeypatch.setenv("MARCUS_BROWSER_MAX_ACTIVE_PAPERS", "5")
    get_settings.cache_clear()
    async with make_client(app) as c1, make_client(app) as c2:
        assert (await upload(c1)).status_code == 202
        assert (await upload(c2)).status_code == 202
        assert (await upload(c2)).status_code == 429
        await _expire_everything(async_db_session)
        assert (await upload(c2)).status_code == 202


async def test_fake_engine_refused_when_disabled(app, monkeypatch):
    monkeypatch.delenv("MARCUS_ENABLE_FAKE_ENGINES", raising=False)
    get_settings.cache_clear()
    async with make_client(app) as c:
        r = await upload(c, engine="fake")
    assert r.status_code == 422


async def test_fake_engine_allowed_when_enabled(app, monkeypatch):
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    get_settings.cache_clear()
    async with make_client(app) as c:
        r = await upload(c, engine="fake", ocsr="off")
    assert r.status_code == 202


async def test_bad_ocsr_value_is_422(app):
    async with make_client(app) as c:
        r = await upload(c, ocsr="maybe")
    assert r.status_code == 422


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, "upload.pdf"),
        ("", "upload.pdf"),
        ("a\\b\\c.pdf", "c.pdf"),
        ("dir/sub/n.pdf", "n.pdf"),
        ("ev\x00il\x07.pdf", "evil.pdf"),
        ("  x.pdf  ", "x.pdf"),
        ("ｆｕｌｌ.pdf", "full.pdf"),
        ("<b>&.pdf", "<b>&.pdf"),
        ("a/", "upload.pdf"),
        ("x" * 500 + ".pdf", ("x" * 500 + ".pdf")[:200]),
    ],
)
def test_sanitize_display_name(raw, expected):
    assert sanitize_display_name(raw) == expected


async def test_concurrent_uploads_respect_the_owner_limit(migrated_db, app, async_db_session):
    import asyncio

    from sqlalchemy import func
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from marcus.core.db import async_db_url
    from marcus.core.models import Owner
    from marcus.core.tokens import hash_token, new_token

    token = new_token()
    async_db_session.add(
        Owner(kind="browser", token_hash=hash_token(token), priority_class=0, created_ip=None)
    )
    await async_db_session.commit()

    engine = create_async_engine(async_db_url(get_settings().database_url), poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _own_session():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_db] = _own_session
    try:
        async with make_client(app) as c:
            c.cookies.set("marcus_owner", token, path="/api/v2")
            rs = await asyncio.gather(*(upload(c) for _ in range(10)))
    finally:
        await engine.dispose()
    assert sorted(r.status_code for r in rs) == [202] * 3 + [429] * 7
    n = (await async_db_session.execute(select(func.count()).select_from(Paper))).scalar_one()
    assert n == 3


async def test_uploads_refused_with_503_below_the_free_disk_floor(app, monkeypatch):
    """Review I6: below MARCUS_MIN_FREE_DISK_BYTES on the data volume, new papers and images
    are refused (503) before anything is written; work already accepted goes on."""
    from collections import namedtuple

    from marcus.core import storage

    usage = namedtuple("usage", "total used free")
    floor = get_settings().min_free_disk_bytes
    assert floor > 0
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda p: usage(10 * floor, 0, floor - 1))
    async with make_client(app) as c:
        r = await upload(c)
        img = await c.post("/api/v2/images", files={"file": ("a.png", b"x", "image/png")})
    assert r.status_code == 503 and r.json() == {"detail": "storage is full, try again later"}
    assert img.status_code == 503
    assert not (get_settings().data_root / "papers").exists()
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda p: usage(10 * floor, 0, floor))
    async with make_client(app) as c:
        assert (await upload(c)).status_code == 202
