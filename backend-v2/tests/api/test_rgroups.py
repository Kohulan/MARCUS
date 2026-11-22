"""The R-group routes: start, read (per paper, per prediction), ownership, refusals, the rate
limit, the paper's progress, and the exports."""

import json
import uuid

import pytest
from rdkit import Chem
from sqlalchemy import select

from marcus.core.models import Prediction, Segment, Step
from tests.api.conftest import (
    finish,
    make_client,
    new_owner,
    ocsr_result,
    paper_row,
    seed_paper,
    steps_of,
)

SCAFFOLD = "[1*]c1ccc(O)cc1"  # MolScribe style: a dummy atom, valid, exportable
ROWS = [
    {"compound": "3a", "groups": {"R1": "OMe"}},
    {"compound": "3b", "groups": {"R1": "H"}},
]


def model_result(rows=ROWS, labels=("R1",)) -> dict:
    return {
        "model": "nuextract3-rgroup-v1",
        "model_version": "vision Q8_0 llama.cpp b12554",
        "labels": list(labels),
        "rows": rows,
        "truncated": False,
        "ms": 3300,
    }


async def seed_scaffold(db, owner):
    """A done paper: segment 0 a scaffold (R1), segment 1 a plain structure. Returns
    (paper_id, scaffold prediction id, plain prediction id, scaffold segment id)."""
    seeded = await seed_paper(db, owner, ocsr=False)

    def run(s):
        for kind in ("docling", "doi"):
            (step,) = steps_of(s, seeded.paper_id, kind)
            finish(s, step, {"text_path": "text.json"} if kind == "docling" else {"doi": None})
        first, second = steps_of(s, seeded.paper_id, "ocsr")
        finish(s, first, ocsr_result(SCAFFOLD))
        finish(s, second, ocsr_result("CCO"))
        preds = s.execute(
            select(Prediction.id, Prediction.rgroups)
            .join(Segment)
            .where(Segment.paper_id == seeded.paper_id)
            .order_by(Segment.idx)
        ).all()
        return [p.id for p in preds], [p.rgroups for p in preds]

    ids, labels = await db.run_sync(run)
    await db.commit()
    assert labels == [["R1"], []]
    assert (await paper_row(db, seeded.paper_id)).status == "done"
    return seeded.paper_id, ids[0], ids[1], seeded.segment_ids[0]


async def run_rgroups(db, paper_id, result) -> None:
    def run(s):
        (step,) = steps_of(s, paper_id, "rgroups", "pending")
        finish(s, step, result)

    await db.run_sync(run)
    await db.commit()


@pytest.fixture
def enabled(monkeypatch, clear_settings_cache):
    """R-groups offered, and a live q.rgroup consumer (the /ready consumer check, faked)."""
    from marcus.api.routes import health

    monkeypatch.setenv("MARCUS_RGROUP_ENABLED", "1")
    clear_settings_cache()
    monkeypatch.setattr(health, "inspect_live_queues", lambda: {"q.cpu", "q.rgroup"})
    monkeypatch.setattr(health, "_live_queues", health.LiveQueues())


@pytest.fixture
async def ready(app, async_db_session, enabled):
    db = async_db_session
    alice, token = await new_owner(db)
    _, bob = await new_owner(db)
    paper_id, scaffold, plain, segment = await seed_scaffold(db, alice)
    return token, paper_id, scaffold, plain, segment, bob


async def test_nothing_asked_for_yet(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, scaffold, _, segment = await seed_scaffold(db, alice)
    async with make_client(app, token) as c:
        listed = await c.get(f"/api/v2/papers/{paper_id}/rgroups")
        one = await c.get(f"/api/v2/predictions/{scaffold}/rgroups")
    assert listed.status_code == 200
    assert listed.json() == {"available": False, "extractions": []}
    assert one.status_code == 200
    assert one.json() == {
        "prediction_id": str(scaffold), "segment_id": str(segment), "status": "none",
        "labels": ["R1"], "rows": None, "truncated": False, "error": None, "model": None,
        "model_version": None, "created_at": None, "updated_at": None, "finished_at": None,
    }  # fmt: skip


async def test_start_is_503_where_it_is_not_available(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    _, scaffold, _, _ = await seed_scaffold(db, alice)
    async with make_client(app, token) as c:
        own = await c.post(f"/api/v2/predictions/{scaffold}/rgroups")
        missing = await c.post(f"/api/v2/predictions/{uuid.uuid4()}/rgroups")
    assert own.status_code == missing.status_code == 503
    assert own.json() == missing.json() == {"detail": "R-group reading is not available"}


async def test_start_is_503_while_no_worker_serves_q_rgroup(
    app, async_db_session, enabled, monkeypatch
):
    """The annotation worker (q.llm) does not count: it does not run the R-group model."""
    from marcus.api.routes import health

    monkeypatch.setattr(health, "inspect_live_queues", lambda: {"q.cpu", "q.llm"})
    monkeypatch.setattr(health, "_live_queues", health.LiveQueues())
    db = async_db_session
    alice, token = await new_owner(db)
    _, scaffold, _, _ = await seed_scaffold(db, alice)
    async with make_client(app, token) as c:
        r = await c.post(f"/api/v2/predictions/{scaffold}/rgroups")
    assert r.status_code == 503 and r.json() == {"detail": "The R-group model is not running"}


async def test_start_progress_and_result(app, async_db_session, ready):
    db = async_db_session
    token, paper_id, scaffold, _, segment, _ = ready
    async with make_client(app, token) as c:
        r = await c.post(f"/api/v2/predictions/{scaffold}/rgroups")
        assert r.status_code == 202
        step_id = r.json()["step_id"]
        again = await c.post(f"/api/v2/predictions/{scaffold}/rgroups", json={"rerun": True})
        assert again.status_code == 202 and again.json()["step_id"] == step_id  # repeat click
        assert (await paper_row(db, paper_id)).status == "done"  # the paper is not reopened
        queued = (await c.get(f"/api/v2/predictions/{scaffold}/rgroups")).json()
        assert queued["status"] == "queued" and queued["rows"] is None

        def start(s):
            step = s.get(Step, uuid.UUID(step_id))
            step.status = "running"
            step.attempts += 1

        await db.run_sync(start)
        await db.commit()
        listed = (await c.get(f"/api/v2/papers/{paper_id}/rgroups")).json()
        assert listed["available"] is True
        (item,) = listed["extractions"]
        assert item["status"] == "running" and item["segment_id"] == str(segment)

        def done(s):
            from marcus.core.pipeline import complete_step

            complete_step(s, uuid.UUID(step_id), model_result())

        await db.run_sync(done)
        await db.commit()
        body = (await c.get(f"/api/v2/predictions/{scaffold}/rgroups")).json()
        assert body["status"] == "done" and body["rows"] == ROWS and body["labels"] == ["R1"]
        assert body["model"] == "nuextract3-rgroup-v1" and body["error"] is None
        # has rows: 200 and no step, unless a re-run is asked for
        r = await c.post(f"/api/v2/predictions/{scaffold}/rgroups")
        assert r.status_code == 200 and r.json() == {"step_id": None}
        r = await c.post(f"/api/v2/predictions/{scaffold}/rgroups", json={"rerun": True})
        assert r.status_code == 202 and r.json()["step_id"] not in (None, step_id)
        rerun = (await c.get(f"/api/v2/predictions/{scaffold}/rgroups")).json()
        assert rerun["status"] == "queued" and rerun["rows"] == ROWS  # kept meanwhile


async def test_a_failed_run_shows_only_its_error_class(app, async_db_session, ready):
    from marcus.core.enums import ErrorClass
    from marcus.core.pipeline import fail_step

    db = async_db_session
    token, _, scaffold, _, _, _ = ready
    async with make_client(app, token) as c:
        step_id = (await c.post(f"/api/v2/predictions/{scaffold}/rgroups")).json()["step_id"]

        def fail(s):
            step = s.get(Step, uuid.UUID(step_id))
            step.status = "running"
            step.attempts += 1
            s.flush()
            fail_step(s, step.id, ErrorClass.BAD_INPUT, "secret path /data/x", retryable=False)

        await db.run_sync(fail)
        await db.commit()
        body = (await c.get(f"/api/v2/predictions/{scaffold}/rgroups")).json()
    assert body["status"] == "failed" and body["error"] == "bad_input"
    assert "secret" not in json.dumps(body)


async def test_a_structure_without_rgroups_is_refused(app, async_db_session, ready):
    token, _, _, plain, _, _ = ready
    async with make_client(app, token) as c:
        r = await c.post(f"/api/v2/predictions/{plain}/rgroups")
    assert r.status_code == 409 and r.json() == {"detail": "This structure has no R-groups"}


async def test_other_owners_and_missing_predictions_are_404(app, async_db_session, ready):
    token, paper_id, scaffold, _, _, bob = ready
    async with make_client(app, bob) as c:
        for r in (
            await c.post(f"/api/v2/predictions/{scaffold}/rgroups"),
            await c.get(f"/api/v2/predictions/{scaffold}/rgroups"),
            await c.get(f"/api/v2/papers/{paper_id}/rgroups"),
            await c.post(f"/api/v2/predictions/{uuid.uuid4()}/rgroups"),
            await c.get(f"/api/v2/predictions/{uuid.uuid4()}/rgroups"),
        ):
            assert r.status_code == 404 and r.json() == {"detail": "not found"}
    async with make_client(app, token) as c:
        await c.delete(f"/api/v2/papers/{paper_id}")
        r = await c.post(f"/api/v2/predictions/{scaffold}/rgroups")
    assert r.status_code == 404


async def test_starts_are_rate_limited_per_owner(app, async_db_session, ready, monkeypatch):
    monkeypatch.setenv("MARCUS_RATE_LIMIT_RGROUP_PER_MIN", "2")
    from marcus.core.settings import get_settings

    get_settings.cache_clear()
    token, _, scaffold, _, _, _ = ready
    async with make_client(app, token) as c:
        codes = [(await c.post(f"/api/v2/predictions/{scaffold}/rgroups")).status_code
                 for _ in range(3)]  # fmt: skip
    assert codes == [202, 202, 429]


async def test_rgroups_steps_are_not_part_of_the_paper_read(app, async_db_session, ready):
    token, paper_id, scaffold, _, _, _ = ready
    async with make_client(app, token) as c:
        before = (await c.get(f"/api/v2/papers/{paper_id}/steps")).json()["steps"]
        await c.post(f"/api/v2/predictions/{scaffold}/rgroups")
        after = (await c.get(f"/api/v2/papers/{paper_id}/steps")).json()["steps"]
        paper = (await c.get(f"/api/v2/papers/{paper_id}")).json()
        listed = (await c.get("/api/v2/papers")).json()["papers"]
    assert after == before and all(s["kind"] != "rgroups" for s in after)
    assert paper["status"] == "done" and "pending" not in paper["counts"]["steps_by_status"]
    (row,) = listed
    assert row["annotating"] is False and row["rereading"] is False


async def test_exports_carry_the_rows(app, async_db_session, ready):
    db = async_db_session
    token, paper_id, scaffold, _, segment, _ = ready
    async with make_client(app, token) as c:
        await c.post(f"/api/v2/predictions/{scaffold}/rgroups")
        await run_rgroups(db, paper_id, model_result())
        doc = (await c.get(f"/api/v2/papers/{paper_id}/export?format=json")).json()
        sdf = (await c.get(f"/api/v2/papers/{paper_id}/export?format=sdf&status=all")).text
        csv = (await c.get(f"/api/v2/papers/{paper_id}/export?format=csv")).text
    first, second = doc["segments"]
    assert first["segment_id"] == str(segment)
    rows = first["rgroup_rows"]
    assert rows["labels"] == ["R1"] and rows["rows"] == ROWS and rows["truncated"] is False
    assert rows["model"] == "nuextract3-rgroup-v1" and rows["extracted_at"]
    assert second["rgroup_rows"] is None
    mols = _sdf(sdf)
    scaffold_mol = next(m for m in mols if m.GetProp("segment_id") == str(segment))
    assert json.loads(scaffold_mol.GetProp("MARCUS_RGROUP_ROWS")) == rows
    assert all(not m.HasProp("MARCUS_RGROUP_ROWS") for m in mols if m is not scaffold_mol)
    assert csv.splitlines()[0].endswith(",rgroups")  # CSV columns unchanged


def _sdf(text: str) -> list:
    supplier = Chem.SDMolSupplier()
    supplier.SetData(text)
    return [m for m in supplier if m is not None]
