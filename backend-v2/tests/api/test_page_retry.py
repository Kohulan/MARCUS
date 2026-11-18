"""POST /api/v2/papers/{id}/pages/{n}/retry: retry one failed page (0-based)."""

import uuid

from sqlalchemy import func, select

from marcus.core import pipeline as pipeline_module
from marcus.core.enums import ErrorClass
from marcus.core.models import Owner, Step
from marcus.core.pipeline import complete_step, fail_step
from tests.api.conftest import (
    SEGS,
    finish,
    make_client,
    new_owner,
    ocsr_result,
    paper_row,
    steps_of,
)
from tests.factories import make_paper


def _failed_page_paper(s, owner_id, pages=1):
    paper = make_paper(s, s.get(Owner, owner_id))
    (check,) = steps_of(s, paper.id, "check_pdf")
    finish(s, check, {"pages": pages})
    for r in steps_of(s, paper.id, "render_page"):
        if r.page == 0:
            r.status, r.attempts = "running", 1
            s.flush()
            fail_step(s, r.id, ErrorClass.BAD_INPUT, "broken", retryable=False)
        else:
            (seg,) = finish(s, r, {})
            for o in finish(s, seg, {"segments": SEGS, "seg_version": "v"}):
                finish(s, o, ocsr_result())
    for st in steps_of(s, paper.id):
        if st.kind in ("docling", "doi"):
            finish(s, st, {"doi": None, "text_path": "text.json"})
    return paper.id


async def seed(db, owner, pages=1) -> uuid.UUID:
    pid = await db.run_sync(lambda s: _failed_page_paper(s, owner.id, pages))
    await db.commit()
    return pid


def url(pid, n=0) -> str:
    return f"/api/v2/papers/{pid}/pages/{n}/retry"


async def test_retry_failed_page_creates_render_step_and_reopens_paper(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    pid = await seed(db, alice)
    assert (await paper_row(db, pid)).status == "failed"
    async with make_client(app, token) as c:
        r = await c.post(url(pid))
    assert r.status_code == 202
    step = (
        await db.execute(select(Step).where(Step.id == uuid.UUID(r.json()["step_id"])))
    ).scalar_one()
    assert (step.kind, step.page, step.status) == ("render_page", 0, "pending")
    assert (await paper_row(db, pid)).status == "processing"


async def test_retry_first_page_0_allowed(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    pid = await seed(db, alice, pages=2)  # page 0 failed, page 1 done: paper done
    assert (await paper_row(db, pid)).status == "done"
    async with make_client(app, token) as c:
        assert (await c.post(url(pid, 0))).status_code == 202
    assert (await paper_row(db, pid)).status == "processing"


async def test_retry_page_not_failed_409(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    pid = await seed(db, alice, pages=2)
    async with make_client(app, token) as c:
        r = await c.post(url(pid, 1))
    assert r.status_code == 409 and r.json() == {"detail": "Page has not failed"}


async def test_retry_busy_409(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    pid = await seed(db, alice)
    async with make_client(app, token) as c:
        assert (await c.post(url(pid))).status_code == 202
        r = await c.post(url(pid))
    assert r.status_code == 409 and r.json() == {"detail": "Page is still running"}


async def test_third_retry_409_limit(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    pid = await seed(db, alice)

    async def fail_pending():
        def go(s):
            (st,) = steps_of(s, pid, "render_page", "pending")
            st.status, st.attempts = "running", 1
            s.flush()
            fail_step(s, st.id, ErrorClass.BAD_INPUT, "again", retryable=False)

        await db.run_sync(go)
        await db.commit()

    async with make_client(app, token) as c:
        for _ in range(2):
            assert (await c.post(url(pid))).status_code == 202
            await fail_pending()
        r = await c.post(url(pid))
    assert r.status_code == 409 and r.json() == {"detail": "No retries left for this page"}


async def test_retry_other_owner_404(app, async_db_session):
    db = async_db_session
    alice, _ = await new_owner(db)
    _, bob = await new_owner(db)
    pid = await seed(db, alice)
    n = (await db.execute(select(func.count()).select_from(Step))).scalar_one()
    async with make_client(app, bob) as c:
        other = await c.post(url(pid))
        missing = await c.post(url(uuid.uuid4()))
    assert other.status_code == 404 and other.json() == missing.json()
    assert (await db.execute(select(func.count()).select_from(Step))).scalar_one() == n


async def test_retry_page_equal_to_pages_404(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    pid = await seed(db, alice)
    async with make_client(app, token) as c:
        assert (await c.post(url(pid, 1))).status_code == 404


async def test_retry_negative_page_404(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    pid = await seed(db, alice)
    async with make_client(app, token) as c:
        assert (await c.post(url(pid, -1))).status_code == 404


async def test_retried_page_success_finishes_paper_done(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    pid = await seed(db, alice)
    async with make_client(app, token) as c:
        r = await c.post(url(pid))

    def drive(s):
        (seg,) = finish(s, s.get(Step, uuid.UUID(r.json()["step_id"])), {})
        for o in finish(s, seg, {"segments": SEGS, "seg_version": "v"}):
            finish(s, o, ocsr_result())

    await db.run_sync(drive)
    await db.commit()
    assert (await paper_row(db, pid)).status == "done"


async def _failed_pages(c) -> int:
    return (await c.get("/api/v2/papers")).json()["papers"][0]["failed_pages"]


async def test_failed_pages_follows_newest_step_across_render_and_segment(app, async_db_session):
    """Failed segment_page -> retry (render in flight: not counted) -> render done and the
    segmentation served from the cache (no new segment_page): the page is not failed."""
    db = async_db_session
    alice, token = await new_owner(db)

    def seed_seg_failed(s):
        paper = make_paper(s, s.get(Owner, alice.id))
        (check,) = steps_of(s, paper.id, "check_pdf")
        finish(s, check, {"pages": 1})
        (render,) = steps_of(s, paper.id, "render_page")
        (seg,) = finish(s, render, {})
        seg.status, seg.attempts = "running", 1
        s.flush()
        fail_step(s, seg.id, ErrorClass.ENGINE_ERROR, "crash", retryable=False)
        return paper.id

    pid = await db.run_sync(seed_seg_failed)
    await db.commit()
    async with make_client(app, token) as c:
        assert await _failed_pages(c) == 1
        r = await c.post(url(pid))
        assert r.status_code == 202
        assert await _failed_pages(c) == 0  # retry in flight
        assert (await c.post(url(pid))).status_code == 409  # retry_page still says busy

        def cached_segmentation(s):
            step = s.get(Step, uuid.UUID(r.json()["step_id"]))
            step.status, step.attempts = "running", 1
            s.flush()
            monkey = pipeline_module._cached_page
            pipeline_module._cached_page = lambda *_a: []  # cache hit: no segment_page step
            try:
                complete_step(s, step.id, {})
            finally:
                pipeline_module._cached_page = monkey

        await db.run_sync(cached_segmentation)
        await db.commit()
        segs = await db.run_sync(lambda s: steps_of(s, pid, "segment_page"))
        assert [x.status for x in segs] == ["failed"]  # none added by the cached retry
        assert await _failed_pages(c) == 0
