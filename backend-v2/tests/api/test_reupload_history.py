"""Owner requests 2026-11-26: the same PDF uploaded again by the same owner opens the earlier
paper instead of reading it again; and the landing page asks whether this browser has a
history (papers or images) without making a new browser owner."""

from sqlalchemy import func, select

from marcus.core.models import Owner, Paper
from tests.api import _upload_helpers as helpers
from tests.api.conftest import make_client, new_owner, seed_paper

PDF = helpers.pdf_bytes(tag=1)
OTHER = helpers.pdf_bytes(tag=2)


async def upload(c, data=PDF):
    r = await helpers.upload(c, data)
    assert r.status_code == 202, r.text
    return r.json()


async def papers(db) -> int:
    return (await db.execute(select(func.count()).select_from(Paper))).scalar_one()


async def test_same_pdf_again_opens_the_earlier_paper(app, async_db_session):
    _, token = await new_owner(async_db_session)
    async with make_client(app, token) as c:
        first = await upload(c)
        again = await upload(c)
        other = await upload(c, OTHER)
    assert again["paper_id"] == first["paper_id"] and again["reused"] is True
    assert "reused" not in first
    assert other["paper_id"] != first["paper_id"]
    assert await papers(async_db_session) == 2


async def test_failed_or_deleted_earlier_paper_is_read_again(app, async_db_session):
    db = async_db_session
    _, token = await new_owner(db)
    async with make_client(app, token) as c:
        first = await upload(c)
        paper = await db.get(Paper, first["paper_id"])
        paper.status = "failed"
        await db.commit()
        second = await upload(c)
        await c.delete(f"/api/v2/papers/{second['paper_id']}")
        third = await upload(c)
    assert len({first["paper_id"], second["paper_id"], third["paper_id"]}) == 3


async def test_another_owner_never_gets_my_paper(app, async_db_session):
    _, mine = await new_owner(async_db_session)
    _, theirs = await new_owner(async_db_session)
    async with make_client(app, mine) as a, make_client(app, theirs) as b:
        first = await upload(a)
        second = await upload(b)
    assert second["paper_id"] != first["paper_id"] and "reused" not in second


async def test_history_without_a_cookie_makes_no_owner(app, async_db_session):
    db = async_db_session
    before = (await db.execute(select(func.count()).select_from(Owner))).scalar_one()
    async with make_client(app) as c:
        r = await c.get("/api/v2/history")
    after = (await db.execute(select(func.count()).select_from(Owner))).scalar_one()
    assert r.status_code == 200 and r.json() == {"items": 0}
    assert "set-cookie" not in r.headers
    assert after == before


async def test_history_counts_my_papers(app, async_db_session):
    db = async_db_session
    owner, token = await new_owner(db)
    await seed_paper(db, owner)
    async with make_client(app, token) as c:
        r = await c.get("/api/v2/history")
    assert r.status_code == 200 and r.json() == {"items": 1}
