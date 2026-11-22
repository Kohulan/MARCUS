"""GET /papers/{id} and its steps with three engines per structure (phase B item 3): the badge
(`agree`), the structure shown (`default_prediction_id`, the export's pick too), background
steps marked and outside the paper's read."""

import json
import uuid

from sqlalchemy import select

from marcus.core.models import BackgroundStep, Step
from tests.api.conftest import (
    finish,
    make_client,
    new_owner,
    ocsr_result,
    seed_paper,
    steps_of,
)


async def _read(db, paper_id, smiles: dict[tuple[int, str], str | None], fail=()):
    """Run the pending OCSR steps: segment n's `engine` reads smiles[(n, engine)] (None: invalid);
    an (n, engine) in `fail` fails; one missing from both stays pending."""

    def run(s):
        for st in steps_of(s, paper_id, status="pending"):
            if st.kind in ("doi", "docling"):
                finish(s, st, {"doi": None} if st.kind == "doi" else {})
        segs = sorted({st.segment_id for st in steps_of(s, paper_id, "ocsr")}, key=str)
        order = {sid: n for n, sid in enumerate(segs)}
        for st in steps_of(s, paper_id, "ocsr", status="pending"):
            key = (order[st.segment_id], st.engine)
            if key in fail:
                st.status, st.attempts = "failed", 2
            elif key in smiles:
                value = smiles[key]
                finish(s, st, ocsr_result(value or "C(", valid=value is not None))
        s.flush()
        return segs

    segs = await db.run_sync(run)
    await db.commit()
    return segs


async def _get(app, token, path):
    async with make_client(app, token) as client:
        r = await client.get(path)
    assert r.status_code == 200
    return r.json()


async def test_badge_waits_for_the_engines_then_says_how_many_agree(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    segs = await _read(db, pid, {(0, "decimer"): "CCO", (1, "decimer"): "CCO"})
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    assert paper["status"] == "done"  # the paper's engine read everything
    assert {s["agree"] for s in paper["segments"]} == {None}  # the others still read
    await _read(
        db, pid,
        {(0, "molnextr"): "OCC", (0, "molscribe"): "C(C)O", (1, "molnextr"): "CCN"},
        fail={(1, "molscribe")},
    )  # fmt: skip
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    by_id = {s["id"]: s for s in paper["segments"]}
    first, second = by_id[str(segs[0])], by_id[str(segs[1])]
    assert (first["agree"], first["agree_engines"]) == (3, ["decimer", "molnextr", "molscribe"])
    assert (second["agree"], second["agree_engines"]) == (0, [])
    shown = {p["id"]: p["engine"] for p in second["predictions"]}
    assert shown[second["default_prediction_id"]] == "decimer"
    # a failed background engine is no failed structure
    assert paper["failed"] == 0 and paper["to_review"] == 2


async def test_two_agree_against_the_papers_engine(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    await _read(db, pid, {(0, "decimer"): "CCN", (0, "molnextr"): "CCO", (0, "molscribe"): "OCC",
                          (1, "decimer"): "CCO"})  # fmt: skip
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    seg = next(s for s in paper["segments"] if s["agree"] is not None)
    assert seg["agree"] == 2 and seg["agree_engines"] == ["molnextr", "molscribe"]
    shown = next(p for p in seg["predictions"] if p["id"] == seg["default_prediction_id"])
    assert shown["engine"] == "molnextr" and shown["smiles"] == "CCO"
    # the export takes the same structure
    async with make_client(app, token) as client:
        r = await client.get(f"/api/v2/papers/{pid}/export", params={"format": "json"})
    exported = {s["segment_id"]: s for s in json.loads(r.content)["segments"]}
    assert exported[seg["id"]]["smiles"] == "CCO"
    assert exported[seg["id"]]["engine"] == "molnextr"


async def test_steps_list_background_steps_marked(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    listed = (await _get(app, token, f"/api/v2/papers/{pid}/steps"))["steps"]
    ocsr = [st for st in listed if st["kind"] == "ocsr"]
    assert sorted((st["engine"], st["background"]) for st in ocsr) == [
        ("decimer", False), ("decimer", False),
        ("molnextr", True), ("molnextr", True), ("molscribe", True), ("molscribe", True),
    ]  # fmt: skip
    background = set(await db.scalars(select(BackgroundStep.step_id)))
    assert {st["id"] for st in ocsr if st["background"]} == {str(b) for b in background}
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    # the counts match the listed steps (a client compares them before refetching)
    assert sum(paper["counts"]["steps_by_status"].values()) == len(listed)
    assert paper["structures_total"] == 2  # background steps are no structures of the read


async def test_a_background_step_is_returned_to_a_repeat_request(app, async_db_session):
    """Compare asks for an engine already running in the background: it gets that step, and
    the done paper is not reopened."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    await _read(db, pid, {(0, "decimer"): "CCO", (1, "decimer"): "CCO"})
    seg = seeded.segment_ids[0]
    async with make_client(app, token) as client:
        r = await client.post(f"/api/v2/segments/{seg}/predictions", json={"engine": "molscribe"})
    assert r.status_code == 202
    step = await db.get(Step, uuid.UUID(r.json()["step_id"]))
    assert step is not None and step.engine == "molscribe" and step.status == "pending"
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    assert paper["status"] == "done"

