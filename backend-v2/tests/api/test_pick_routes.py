"""The "all pages or pick a structure" routes (owner decision 2026-11-25) and candidates: in
mode pick a segment the user has not picked (no OCSR step) is only a box on its page. It is
returned with `candidate: true` so the page can draw it, and left out of counts, exports, bulk
curation and links."""

import json
import uuid

from marcus.core.models import Paper, Step
from tests.api.conftest import finish, make_client, new_owner, steps_of
from tests.core.test_caches import OCSR, drive, segment_result
from tests.factories import make_paper


async def asked_paper(db, owner, pages=1) -> uuid.UUID:
    """A web upload (mode ask) with its pages rendered and its text read."""

    def run(s):
        paper = make_paper(s, s.get(type(owner), owner.id), ocsr_mode="ask")
        drive(s, paper, pages=pages)
        return paper.id

    pid = await db.run_sync(run)
    await db.commit()
    return pid


async def finish_segmenting(db, pid, page=0, boxes=3):
    def run(s):
        paper = s.get(Paper, pid)
        (st,) = steps_of(s, pid, "segment_page", "pending")
        finish(s, st, segment_result(paper, page, boxes))

    await db.run_sync(run)
    await db.commit()


async def finish_reads(db, pid):
    def run(s):
        for st in steps_of(s, pid, "ocsr", "pending"):
            finish(s, st, OCSR)

    await db.run_sync(run)
    await db.commit()


async def get(c, pid):
    r = await c.get(f"/api/v2/papers/{pid}")
    assert r.status_code == 200
    return r.json()


async def picked_with_candidates(app, db):
    alice, token = await new_owner(db)
    pid = await asked_paper(db, alice)
    async with make_client(app, token) as c:
        assert (await c.put(f"/api/v2/papers/{pid}/mode", json={"mode": "pick"})).status_code == 200
        r = await c.post(f"/api/v2/papers/{pid}/pages/0/segment")
    assert r.status_code == 202 and r.json()["step_id"]
    await finish_segmenting(db, pid)
    return pid, token


async def test_mode_route_ask_to_pick_and_conflict(app, async_db_session):
    alice, token = await new_owner(async_db_session)
    pid = await asked_paper(async_db_session, alice)
    async with make_client(app, token) as c:
        r = await c.put(f"/api/v2/papers/{pid}/mode", json={"mode": "pick"})
        again = await c.put(f"/api/v2/papers/{pid}/mode", json={"mode": "pick"})
        bad = await c.put(f"/api/v2/papers/{pid}/mode", json={"mode": "ask"})
    assert r.status_code == 200 and r.json() == {"ocsr_mode": "pick"}
    assert again.status_code == 409 and again.json() == {"detail": "mode"}
    assert bad.status_code == 422


async def test_segment_route_then_candidates_are_not_counted(app, async_db_session):
    pid, token = await picked_with_candidates(app, async_db_session)
    async with make_client(app, token) as c:
        paper = await get(c, pid)
        again = await c.post(f"/api/v2/papers/{pid}/pages/0/segment")
    assert [s["candidate"] for s in paper["segments"]] == [True, True, True]
    assert paper["structures"] == 0 and paper["to_review"] == 0
    assert again.status_code == 202 and again.json() == {"step_id": None}


async def test_read_route_makes_a_structure(app, async_db_session):
    pid, token = await picked_with_candidates(app, async_db_session)
    async with make_client(app, token) as c:
        first = (await get(c, pid))["segments"][0]["id"]
        r = await c.post(f"/api/v2/segments/{first}/read")
        twice = await c.post(f"/api/v2/segments/{first}/read")
        await finish_reads(async_db_session, pid)
        paper = await get(c, pid)
    assert r.status_code == 202 and len(r.json()["step_ids"]) == 3
    assert sorted(twice.json()["step_ids"]) == sorted(r.json()["step_ids"])
    assert [s["candidate"] for s in paper["segments"]] == [False, True, True]
    assert paper["structures"] == 1 and paper["structures_total"] == 1


async def test_export_and_bulk_skip_candidates(app, async_db_session):
    pid, token = await picked_with_candidates(app, async_db_session)
    async with make_client(app, token) as c:
        segs = (await get(c, pid))["segments"]
        await c.post(f"/api/v2/segments/{segs[0]['id']}/read")
        await finish_reads(async_db_session, pid)
        exported = await c.get(f"/api/v2/papers/{pid}/export?format=json")
        bulk = await c.put(
            f"/api/v2/papers/{pid}/curation",
            json={"items": [{"segment_id": segs[1]["id"], "status": "accepted"}]},
        )
    records = json.loads(exported.content)["segments"]
    assert [r["segment_id"] for r in records] == [segs[0]["id"]]
    assert bulk.status_code == 404


async def test_choose_auto_turns_candidates_into_structures(app, async_db_session):
    pid, token = await picked_with_candidates(app, async_db_session)
    async with make_client(app, token) as c:
        r = await c.put(f"/api/v2/papers/{pid}/mode", json={"mode": "auto"})
        await finish_reads(async_db_session, pid)
        paper = await get(c, pid)
    assert r.status_code == 200 and r.json() == {"ocsr_mode": "auto"}
    assert [s["candidate"] for s in paper["segments"]] == [False, False, False]
    assert paper["structures"] == 3


async def test_pick_routes_on_an_auto_paper_are_409(app, async_db_session):
    alice, token = await new_owner(async_db_session)
    pid = await asked_paper(async_db_session, alice)
    async with make_client(app, token) as c:
        await c.put(f"/api/v2/papers/{pid}/mode", json={"mode": "auto"})
        seg = await c.post(f"/api/v2/papers/{pid}/pages/0/segment")
        outside = await c.post(f"/api/v2/papers/{pid}/pages/9/segment")
    assert seg.status_code == 409 and seg.json() == {"detail": "mode"}
    assert outside.status_code in (404, 409)


async def test_delete_pick_paper_with_candidates(app, async_db_session):
    pid, token = await picked_with_candidates(app, async_db_session)
    async with make_client(app, token) as c:
        r = await c.delete(f"/api/v2/papers/{pid}")
        after = await c.get(f"/api/v2/papers/{pid}")
    assert r.status_code in (200, 204) and after.status_code == 404


async def test_other_owner_gets_404(app, async_db_session):
    pid, _ = await picked_with_candidates(app, async_db_session)
    _, other = await new_owner(async_db_session)
    async with make_client(app, other) as c:
        mode = await c.put(f"/api/v2/papers/{pid}/mode", json={"mode": "auto"})
        seg = await c.post(f"/api/v2/papers/{pid}/pages/0/segment")
    seg_ids = [
        s.segment_id
        for s in (
            await async_db_session.execute(Step.__table__.select().where(Step.paper_id == pid))
        ).all()
        if s.segment_id
    ]
    assert mode.status_code == 404 and seg.status_code == 404
    assert seg_ids == []  # the other owner made no step


async def test_back_to_pick_stopped_boxes_are_no_structures(app, async_db_session):
    """auto -> pick (owner, 2026-11-26): the boxes whose reads were stopped count nowhere."""
    alice, token = await new_owner(async_db_session)
    pid = await asked_paper(async_db_session, alice)
    async with make_client(app, token) as c:
        assert (await c.put(f"/api/v2/papers/{pid}/mode", json={"mode": "auto"})).status_code == 200
        await finish_segmenting(async_db_session, pid)
        r = await c.put(f"/api/v2/papers/{pid}/mode", json={"mode": "pick"})
        paper = await get(c, pid)
        listed = (await c.get("/api/v2/papers")).json()
    assert r.status_code == 200
    assert [s["candidate"] for s in paper["segments"]] == [True, True, True]
    assert paper["structures"] == 0 and paper["structures_total"] == 0
    row = next(p for p in listed["papers"] if p["id"] == str(pid))
    assert row["structures_total"] == 0 and row["structures_read"] == 0
