"""GET /api/v2/papers/{id}/steps: read-only step list (timestamps, error_class), no raw error text."""

import uuid

from sqlalchemy import update

from marcus.core.models import Paper, Step
from tests.api.conftest import make_client, new_owner, seed_paper

FIELDS = {"id", "kind", "page", "segment_id", "status", "attempts", "error_class",
          "created_at", "started_at", "finished_at", "engine", "background"}  # fmt: skip


async def test_steps_shape_and_order(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, token) as c:
        r = await c.get(f"/api/v2/papers/{seeded.paper_id}/steps")
    assert r.status_code == 200
    steps = r.json()["steps"]
    # check_pdf, render, segment, 2 ocsr, 4 background ocsr (the other engines), docling, doi
    assert len(steps) == 11
    assert all(set(s) == FIELDS for s in steps)
    keys = [(s["created_at"], s) for s in steps]
    assert [k for k, _ in keys] == sorted(k for k, _ in keys)
    assert {s["kind"] for s in steps} >= {"check_pdf", "render_page", "segment_page", "ocsr"}
    ocsr = [s for s in steps if s["kind"] == "ocsr"]
    assert all(s["segment_id"] for s in ocsr)


async def test_steps_other_owner_gets_same_404_as_missing(app, async_db_session):
    db = async_db_session
    alice, _ = await new_owner(db)
    _, bob_token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, bob_token) as c:
        other = await c.get(f"/api/v2/papers/{seeded.paper_id}/steps")
        missing = await c.get(f"/api/v2/papers/{uuid.uuid4()}/steps")
    assert other.status_code == 404 and missing.status_code == 404
    assert other.json() == missing.json()


async def test_steps_deleted_paper_is_404(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    await db.execute(update(Paper).where(Paper.id == seeded.paper_id).values(status="deleted"))
    await db.commit()
    async with make_client(app, token) as c:
        r = await c.get(f"/api/v2/papers/{seeded.paper_id}/steps")
    assert r.status_code == 404


async def test_steps_never_leak_error_text(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    secret = "Traceback (most recent call last):\n  File '/srv/marcus/x.py' secret-path"
    await db.execute(
        update(Step)
        .where(Step.paper_id == seeded.paper_id, Step.kind == "segment_page")
        .values(status="failed", error_class="engine_error", error=secret)
    )
    await db.commit()
    async with make_client(app, token) as c:
        r = await c.get(f"/api/v2/papers/{seeded.paper_id}/steps")
    assert "Traceback" not in r.text and "secret-path" not in r.text and "/srv/" not in r.text
    failed = [s for s in r.json()["steps"] if s["status"] == "failed"]
    assert failed and failed[0]["error_class"] == "engine_error"


async def test_step_out_has_engine(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, token) as c:
        steps = (await c.get(f"/api/v2/papers/{seeded.paper_id}/steps")).json()["steps"]
    ocsr = [s for s in steps if s["kind"] == "ocsr"]
    assert sorted(s["engine"] for s in ocsr if not s["background"]) == ["decimer", "decimer"]
    assert sorted(s["engine"] for s in ocsr if s["background"]) == [
        "molparser",
        "molparser",
        "molscribe",
        "molscribe",
    ]
    assert all(s["engine"] is None for s in steps if s["kind"] != "ocsr")
