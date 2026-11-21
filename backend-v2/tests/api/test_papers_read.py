import ast
import json
import pathlib
import uuid
from datetime import UTC, datetime, timedelta

from rdkit import Chem
from sqlalchemy import delete, event, select, update

from marcus.core import storage
from marcus.core.models import Curation, Paper, Prediction, Step
from marcus.core.settings import get_settings
from tests.api.conftest import (
    PNG,
    make_client,
    new_owner,
    paper_row,
    seed_paper,
    steps_of,
)


async def test_list_shows_only_own_papers(app, async_db_session):
    db = async_db_session
    alice, a_token = await new_owner(db)
    bob, _ = await new_owner(db)
    a1 = await seed_paper(db, alice)
    a2 = await seed_paper(db, alice, ocsr=False)
    await seed_paper(db, bob)
    # make a1 clearly older
    await db.execute(
        update(Paper)
        .where(Paper.id == a1.paper_id)
        .values(created_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db.commit()
    async with make_client(app, a_token) as c:
        r = await c.get("/api/v2/papers")
    assert r.status_code == 200
    papers = r.json()["papers"]
    assert [p["id"] for p in papers] == [str(a2.paper_id), str(a1.paper_id)]
    assert set(papers[0]) >= {"id", "display_name", "status", "pages", "created_at", "engine"}


async def test_list_for_new_visitor_is_empty_and_sets_cookie(app, async_db_session):
    async with make_client(app) as c:
        r = await c.get("/api/v2/papers")
    assert r.status_code == 200 and r.json() == {"papers": []}
    assert "marcus_owner=" in r.headers["set-cookie"]


async def test_get_paper_shape(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg0 = seeded.segment_ids[0]

    def add_newer_prediction(s):
        s.add(
            Prediction(
                segment_id=seg0, engine="molnextr", engine_version="m1", smiles="CCN",
                valid=True, ms=3, created_at=datetime.now(UTC) + timedelta(seconds=5),
            )
        )  # fmt: skip

    await db.run_sync(add_newer_prediction)
    await db.commit()
    async with make_client(app, token) as c:
        r = await c.get(f"/api/v2/papers/{seeded.paper_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(seeded.paper_id)
    assert body["status"] == "processing" and body["pages"] == 1
    assert body["engine"] == "decimer" and body["ocsr_mode"] == "auto"
    assert body["display_name"] == "paper.pdf" and body["doi"] is None
    assert body["created_at"] and body["expires_at"]
    # check_pdf, render, segment, 2 ocsr done; docling + doi pending
    assert body["counts"]["steps_by_status"] == {"done": 5, "pending": 2}
    segs = body["segments"]
    assert [(s["page"], s["idx"]) for s in segs] == [(0, 0), (0, 1)]
    assert segs[0]["id"] == str(seg0) and segs[0]["bbox"] == [0, 0, 10, 10]
    assert segs[0]["curation"] == {
        "status": "unchecked", "smiles": None, "molfile": None, "note": None, "rgroups": [],
    }  # fmt: skip
    preds = segs[0]["predictions"]
    assert [p["smiles"] for p in preds] == ["CCN", "CCO"]  # newest first
    assert set(preds[0]) >= {"engine", "engine_version", "smiles", "molfile", "valid", "created_at"}
    assert [p["engine"] for p in preds] == ["molnextr", "decimer"]


async def test_paper_shows_doi_title_first_author_and_year(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    found = await seed_paper(db, alice)
    unknown = await seed_paper(db, alice, ocsr=False)
    await db.execute(
        update(Paper)
        .where(Paper.id == found.paper_id)
        .values(doi="10.1/x", title="Coffea", first_author="Rajan", year=2025)
    )
    await db.commit()
    meta = {"doi": "10.1/x", "title": "Coffea", "first_author": "Rajan", "year": 2025}
    none = dict.fromkeys(meta)
    async with make_client(app, token) as c:
        detail = (await c.get(f"/api/v2/papers/{found.paper_id}")).json()
        bare = (await c.get(f"/api/v2/papers/{unknown.paper_id}")).json()
        listed = {p["id"]: p for p in (await c.get("/api/v2/papers")).json()["papers"]}
    assert {k: detail[k] for k in meta} == meta
    assert {k: bare[k] for k in meta} == none
    assert {k: listed[str(found.paper_id)][k] for k in meta} == meta
    assert {k: listed[str(unknown.paper_id)][k] for k in meta} == none


async def test_segments_route_matches_paper_detail(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, token) as c:
        detail = (await c.get(f"/api/v2/papers/{seeded.paper_id}")).json()
        r = await c.get(f"/api/v2/papers/{seeded.paper_id}/segments")
    assert r.status_code == 200
    assert r.json() == {"segments": detail["segments"]}
    assert [s["id"] for s in r.json()["segments"]] == [str(i) for i in seeded.segment_ids]


async def test_delete_cancels_paper(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, token) as c:
        r = await c.delete(f"/api/v2/papers/{seeded.paper_id}")
        assert r.status_code == 204 and r.content == b""
        again = await c.delete(f"/api/v2/papers/{seeded.paper_id}")
    assert again.status_code == 404
    assert (await paper_row(db, seeded.paper_id)).status == "deleted"
    left = await db.run_sync(lambda s: steps_of(s, seeded.paper_id, status="pending"))
    assert left == []
    assert not storage.paper_dir(seeded.paper_id).exists()


async def test_page_and_segment_images(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, token) as c:
        page = await c.get(f"/api/v2/papers/{seeded.paper_id}/pages/0/image")
        out_of_range = await c.get(f"/api/v2/papers/{seeded.paper_id}/pages/1/image")
        negative = await c.get(f"/api/v2/papers/{seeded.paper_id}/pages/-1/image")
        crop = await c.get(f"/api/v2/segments/{seeded.segment_ids[1]}/image")
        storage.page_image_path(seeded.paper_id, 0).unlink()
        not_rendered = await c.get(f"/api/v2/papers/{seeded.paper_id}/pages/0/image")
    assert page.status_code == 200 and page.content == PNG
    assert page.headers["content-type"] == "image/png"
    assert page.headers["cache-control"] == "private, max-age=3600"
    assert crop.status_code == 200 and crop.content == PNG + b"1"
    assert crop.headers["content-type"] == "image/png"
    assert crop.headers["cache-control"] == "private, max-age=3600"
    for r in (out_of_range, negative, not_rendered):
        assert r.status_code == 404 and r.json() == {"detail": "not found"}


async def test_text_returns_docling_json(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, token) as c:
        r = await c.get(f"/api/v2/papers/{seeded.paper_id}/text")
        (storage.paper_dir(seeded.paper_id) / "text.json").unlink()
        gone = await c.get(f"/api/v2/papers/{seeded.paper_id}/text")
    assert r.status_code == 200 and r.json() == {"texts": ["hi"]}
    assert r.headers["content-type"].startswith("application/json")
    assert gone.status_code == 404 and gone.json() == {"detail": "not found"}


# --- curation -----------------------------------------------------------------------------


async def _curate(app, token, seg, body):
    async with make_client(app, token) as c:
        return await c.put(f"/api/v2/segments/{seg}/curation", json=body)


async def _curation_row(db, seg) -> Curation:
    return (
        await db.execute(
            select(Curation)
            .where(Curation.segment_id == seg)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def test_curation_rejects_invalid_smiles(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = seeded.segment_ids[0]
    r = await _curate(app, token, seg, {"status": "accepted", "smiles": "C1CC(("})
    assert r.status_code == 422
    cur = await _curation_row(db, seg)
    assert (cur.status, cur.smiles) == ("unchecked", None)


async def test_curation_saves_valid_values(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = seeded.segment_ids[0]
    body = {"status": "accepted", "smiles": "c1ccccc1", "note": "checked by hand"}
    r = await _curate(app, token, seg, body)
    assert r.status_code == 200
    assert r.json() == {**body, "molfile": None, "rgroups": []}
    cur = await _curation_row(db, seg)
    assert (cur.status, cur.smiles, cur.note) == ("accepted", "c1ccccc1", "checked by hand")
    # status only: the other fields are cleared (PUT replaces)
    r = await _curate(app, token, seg, {"status": "rejected"})
    assert r.status_code == 200
    cur = await _curation_row(db, seg)
    assert (cur.status, cur.smiles, cur.note) == ("rejected", None, None)


async def test_curation_validation_limits(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = seeded.segment_ids[0]
    bad = [
        {"status": "maybe"},
        {"status": "accepted", "molfile": "x" * (200 * 1024 + 1)},
        {"status": "accepted", "note": "n" * 2001},
        {"status": "accepted", "note": "nul\x00byte"},
        {},
    ]
    for body in bad:
        assert (await _curate(app, token, seg, body)).status_code == 422, body
    ok = {"status": "unchecked", "note": "n" * 2000, "smiles": ""}
    assert (await _curate(app, token, seg, ok)).status_code == 200


async def test_curation_molfile_must_parse(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = seeded.segment_ids[0]
    good = Chem.MolToMolBlock(Chem.MolFromSmiles("CCO"))
    # five-valent carbon: reads as a block but fails sanitization
    bad_valence = Chem.MolToMolBlock(Chem.MolFromSmiles("C(C)(C)(C)(C)C", sanitize=False))
    for molfile in (
        "not a molfile",
        "\n\n\n  1  0  0  0  0  0  0  0  0  0999 V2000\n",
        bad_valence,
    ):
        r = await _curate(app, token, seg, {"status": "accepted", "molfile": molfile})
        assert r.status_code == 422, molfile
        assert "molfile" in json.dumps(r.json()["detail"])
    assert (await _curation_row(db, seg)).molfile is None
    r = await _curate(app, token, seg, {"status": "accepted", "molfile": good})
    assert r.status_code == 200
    assert (await _curation_row(db, seg)).molfile == good


async def test_curation_smiles_cap_matches_the_tools_routes(app, async_db_session):
    """Review I4: curation SMILES are capped like the tools routes (2000 characters)."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = seeded.segment_ids[0]
    too_long = ".".join(["C"] * 1001)  # 2001 characters, valid SMILES
    r = await _curate(app, token, seg, {"status": "accepted", "smiles": too_long})
    assert r.status_code == 422
    ok = ".".join(["C"] * 1000)  # 1999 characters
    assert (await _curate(app, token, seg, {"status": "accepted", "smiles": ok})).status_code == 200


async def test_curation_molfile_atom_cap(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = seeded.segment_ids[0]
    big = Chem.MolToMolBlock(Chem.MolFromSmiles(".".join(["C"] * 1001)))
    assert len(big.encode()) < 200 * 1024
    r = await _curate(app, token, seg, {"status": "accepted", "molfile": big})
    assert r.status_code == 422 and "atoms" in json.dumps(r.json()["detail"])


async def test_curation_of_a_foreign_segment_is_404_before_any_parse(app, async_db_session):
    """The owner check runs first: another owner's segment gives the shared 404, even for a
    body that would not parse (no RDKit work for someone else's segment)."""
    db = async_db_session
    alice, _ = await new_owner(db)
    _, bob_token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = seeded.segment_ids[0]
    r = await _curate(app, bob_token, seg, {"status": "accepted", "smiles": "C1CC(("})
    assert r.status_code == 404 and r.json() == {"detail": "not found"}


async def test_curation_parse_runs_off_the_event_loop(app, async_db_session, monkeypatch):
    """RDKit holds the GIL while it parses, so a thread would stall the loop just the same:
    the parse runs in a separate process (marcus.api.chempool). While a slow parse runs, the
    loop keeps serving."""
    import asyncio

    from marcus.api import chempool

    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = seeded.segment_ids[0]
    # warm the pool (process start and RDKit import are not what is measured)
    assert (
        await _curate(app, token, seg, {"status": "accepted", "smiles": "CC"})
    ).status_code == 200

    real = chempool.CHEM.run

    async def slow_run(fn, *args):
        import time

        await real(time.sleep, 0.6)  # stands in for a long parse, in the same pool
        return await real(fn, *args)

    monkeypatch.setattr(chempool.CHEM, "run", slow_run)
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    t = asyncio.ensure_future(ticker())
    try:
        r = await _curate(app, token, seg, {"status": "accepted", "smiles": "CCO"})
    finally:
        t.cancel()
    assert r.status_code == 200
    assert ticks >= 20  # ~60 ticks of 10 ms while the 0.6 s job ran in the other process


RGP_MOLFILE = (
    "\n  Ketcher\n\n  3  2  0  0  0  0  0  0  0  0999 V2000\n"
    "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    1.0000    0.0000    0.0000 R#  0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    2.0000    0.0000    0.0000 R#  0  0  0  0  0  0  0  0  0  0  0  0\n"
    "  1  2  1  0  0  0  0\n  1  3  1  0  0  0  0\nM  RGP  2   2   1   3   2\nM  END\n"
)


async def test_curation_stores_and_returns_rgroups(app, async_db_session):
    """A curated structure with R-group atoms (Ketcher's R#) carries its labels; one without,
    [] ; a curation without its own structure, [] in the API (NULL in the row)."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = seeded.segment_ids[0]
    r = await _curate(app, token, seg, {"status": "accepted", "molfile": RGP_MOLFILE})
    assert r.status_code == 200 and r.json()["rgroups"] == ["R1", "R2"]
    assert (await _curation_row(db, seg)).rgroups == ["R1", "R2"]
    r = await _curate(app, token, seg, {"status": "accepted", "smiles": "[1*]c1ccccc1"})
    assert r.json()["rgroups"] == ["R1"]
    r = await _curate(app, token, seg, {"status": "accepted"})
    assert r.json()["rgroups"] == []
    assert (await _curation_row(db, seg)).rgroups is None
    async with make_client(app, token) as c:
        got = (await c.get(f"/api/v2/papers/{seeded.paper_id}")).json()
    assert got["segments"][0]["curation"]["rgroups"] == []


async def test_predictions_expose_rgroups(app, async_db_session):
    """Each prediction says its R-group labels: the stored ones, [] for none, and [] for a row
    stored without (NULL)."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg0, seg1 = seeded.segment_ids

    def add(s):
        s.add(
            Prediction(
                segment_id=seg0, engine="decimer", engine_version="d", smiles="[R1]c1ccccc1[R2]",
                valid=False, ms=3, rgroups=["R1", "R2"],
                created_at=datetime.now(UTC) + timedelta(seconds=5),
            )
        )  # fmt: skip

    await db.run_sync(add)
    await db.execute(update(Prediction).where(Prediction.segment_id == seg1).values(rgroups=[]))
    await db.commit()
    async with make_client(app, token) as c:
        r = await c.get(f"/api/v2/papers/{seeded.paper_id}/segments")
    segs = {s["id"]: s for s in r.json()["segments"]}
    assert [p["rgroups"] for p in segs[str(seg0)]["predictions"]] == [["R1", "R2"], []]
    assert [p["rgroups"] for p in segs[str(seg1)]["predictions"]] == [[]]


def test_check_curation_in_the_worker_process():
    from marcus.api.chem import check_curation

    assert check_curation("CCO", None) == (None, [])
    assert check_curation("*CC", None) == (None, ["*"])
    assert check_curation(None, RGP_MOLFILE) == (None, ["R1", "R2"])
    assert check_curation("C1CC((", None) == (("smiles", "SMILES could not be parsed"), [])


def test_curation_check_in_the_worker_process():
    from marcus.api.chem import curation_error

    assert curation_error("CCO", None) is None
    assert curation_error("C1CC((", None) == ("smiles", "SMILES could not be parsed")
    assert curation_error(None, "not a molfile") == ("molfile", "molfile could not be parsed")
    assert curation_error(None, None) is None


# --- predictions --------------------------------------------------------------------------


async def test_rerun_with_other_engine_creates_step(app, async_db_session, monkeypatch):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = seeded.segment_ids[1]
    async with make_client(app, token) as c:
        r = await c.post(f"/api/v2/segments/{seg}/predictions", json={"engine": "molscribe"})
        dup = await c.post(f"/api/v2/segments/{seg}/predictions", json={"engine": "molscribe"})
        fake = await c.post(f"/api/v2/segments/{seg}/predictions", json={"engine": "fake"})
        unknown = await c.post(f"/api/v2/segments/{seg}/predictions", json={"engine": "nope"})
    assert r.status_code == 202
    step_id = uuid.UUID(r.json()["step_id"])
    step = (await db.execute(select(Step).where(Step.id == step_id))).scalar_one()
    assert (step.kind, step.engine, step.queue, step.status) == (
        "ocsr", "molscribe", "q.molscribe", "pending",
    )  # fmt: skip
    assert (step.segment_id, step.paper_id, step.page, step.seq) == (seg, seeded.paper_id, 0, 1)
    # the same request while the first is still waiting does not queue a second step
    assert dup.status_code == 202 and dup.json() == r.json()
    assert fake.status_code == 422
    assert unknown.status_code == 422
    molscribe = (await db.execute(select(Step).where(Step.engine == "molscribe"))).scalars().all()
    assert len(molscribe) == 1


async def test_fake_engine_allowed_when_enabled(app, async_db_session, monkeypatch):
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    get_settings.cache_clear()
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, token) as c:
        r = await c.post(
            f"/api/v2/segments/{seeded.segment_ids[0]}/predictions", json={"engine": "fake"}
        )
    assert r.status_code == 202


def test_routes_share_read_helpers_through_read_module():
    """Route modules never import each other; shared read helpers live in marcus.api.read."""
    from marcus.api import read
    from marcus.api.routes import events, papers, segments

    for path in pathlib.Path(events.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("marcus.api.routes"), (path.name, node.module)
    assert events.steps_by_status is read.steps_by_status
    assert papers.segments_out is read.segments_out
    assert segments.IMAGE_HEADERS is read.IMAGE_HEADERS


# --- queue --------------------------------------------------------------------------------


async def test_queue_counts_steps_ahead_and_estimates(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    bob, _ = await new_owner(db)
    mine = await seed_paper(db, alice)  # docling + doi pending on q.cpu
    theirs = await seed_paper(db, bob)
    now = datetime.now(UTC)
    # bob's two q.cpu steps were created before mine
    await db.execute(
        update(Step)
        .where(Step.paper_id == theirs.paper_id, Step.status == "pending")
        .values(created_at=now - timedelta(minutes=10))
    )
    await db.execute(
        update(Step)
        .where(Step.paper_id == mine.paper_id, Step.status == "pending")
        .values(created_at=now - timedelta(minutes=5))
    )
    # finished q.cpu steps of the last hour took 2, 4 and 30 s (median 4); an older one is ignored
    done = (
        (
            await db.execute(
                select(Step).where(Step.queue == "q.cpu", Step.status == "done").limit(4)
            )
        )
        .scalars()
        .all()
    )
    for st, secs in zip(done, [2, 4, 30, 1000], strict=True):
        st.started_at = now - timedelta(minutes=30 if secs != 1000 else 120)
        st.finished_at = st.started_at + timedelta(seconds=secs)
    await db.commit()

    async with make_client(app, token) as c:
        r = await c.get("/api/v2/queue")
    assert r.status_code == 200
    body = r.json()
    assert body["papers"] == [
        {"id": str(mine.paper_id), "steps_ahead_by_queue": {"q.cpu": 2}, "estimate_s": 8.0}
    ]
    assert body["estimate_s"] == 8.0


async def test_queue_default_duration_and_no_foreign_papers(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    bob, _ = await new_owner(db)
    await seed_paper(db, bob)
    async with make_client(app, token) as c:
        empty = (await c.get("/api/v2/queue")).json()
    assert empty == {"papers": [], "estimate_s": 0.0}

    mine = await seed_paper(db, alice)
    await db.execute(
        update(Step)
        .where(Step.paper_id == mine.paper_id, Step.status == "pending")
        .values(created_at=datetime.now(UTC) + timedelta(minutes=1))
    )
    await db.commit()
    async with make_client(app, token) as c:
        body = (await c.get("/api/v2/queue")).json()
    # bob's 2 pending q.cpu steps are ahead; no finished step has timings -> 5 s each
    assert body["papers"][0]["steps_ahead_by_queue"] == {"q.cpu": 2}
    assert body["estimate_s"] == 10.0


async def test_queue_ignores_my_expired_papers(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    expired = await seed_paper(db, alice)
    kept = await seed_paper(db, alice)
    await db.execute(
        update(Paper)
        .where(Paper.id == expired.paper_id)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db.commit()
    async with make_client(app, token) as c:
        body = (await c.get("/api/v2/queue")).json()
    assert [p["id"] for p in body["papers"]] == [str(kept.paper_id)]


async def test_prediction_exposes_cached_flag(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    await db.execute(
        update(Prediction).where(Prediction.segment_id == seeded.segment_ids[0]).values(cached=True)
    )
    await db.commit()
    async with make_client(app, token) as c:
        r = await c.get(f"/api/v2/papers/{seeded.paper_id}")
    segs = {s["id"]: s for s in r.json()["segments"]}
    assert [p["cached"] for p in segs[str(seeded.segment_ids[0])]["predictions"]] == [True]
    assert [p["cached"] for p in segs[str(seeded.segment_ids[1])]["predictions"]] == [False]


COUNT_KEYS = ("structures", "accepted", "rejected", "to_review", "failed_pages", "failed")


def _counts(p: dict) -> tuple:
    return tuple(p[k] for k in COUNT_KEYS)


async def _add_segment(db, paper_id, page=0, idx=9):
    from marcus.core.models import Segment

    seg = Segment(paper_id=paper_id, page=page, idx=idx, bbox=[0, 0, 1, 1], image_sha256="2" * 64)
    db.add(seg)
    await db.flush()
    db.add(Curation(segment_id=seg.id, status="unchecked"))
    await db.commit()
    return seg.id


async def _fail_step(db, paper_id, kind, page=0, status="failed"):
    await db.execute(
        update(Step)
        .where(Step.paper_id == paper_id, Step.kind == kind)
        .values(status=status, error_class="engine_error" if status == "failed" else None)
    )
    await db.commit()


async def _add_step(db, paper_id, kind, status, page=0):
    last = (
        await db.execute(select(Step).where(Step.paper_id == paper_id, Step.kind == kind).limit(1))
    ).scalar_one()
    db.add(
        Step(
            paper_id=paper_id, kind=kind, queue=last.queue, page=page,
            seq=last.seq + 100, status=status,
            created_at=last.created_at + timedelta(seconds=5),
        )
    )  # fmt: skip
    await db.commit()


async def _seed_counts(db, owner):
    seeded = await seed_paper(db, owner)
    s3 = await _add_segment(db, seeded.paper_id)
    a, b = seeded.segment_ids
    await db.execute(update(Curation).where(Curation.segment_id == a).values(status="accepted"))
    await db.execute(update(Curation).where(Curation.segment_id == b).values(status="rejected"))
    await db.commit()
    assert s3
    return seeded


async def test_list_papers_has_counts(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await _seed_counts(db, alice)
    await _fail_step(db, seeded.paper_id, "segment_page")
    async with make_client(app, token) as c:
        listed = (await c.get("/api/v2/papers")).json()["papers"]
        detail = (await c.get(f"/api/v2/papers/{seeded.paper_id}")).json()
    assert _counts(listed[0]) == (3, 1, 1, 1, 1, 0)
    assert _counts(detail) == (3, 1, 1, 1, 1, 0)


async def test_paper_without_segments_has_zero_counts(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    await seed_paper(db, alice, write_files=False)
    await db.execute(update(Paper).values(status="processing"))
    await db.commit()
    async with make_client(app, token) as c:
        listed = (await c.get("/api/v2/papers")).json()["papers"]
    assert _counts(listed[0]) == (2, 0, 0, 2, 0, 0)


async def _ocsr_step(db, segment_id, status, later_s=0):
    """Set the segment's ocsr step to `status`; with `later_s`, add a newer step instead."""
    step = (
        (await db.execute(select(Step).where(Step.segment_id == segment_id, Step.kind == "ocsr")))
        .scalars()
        .first()
    )
    if later_s:
        db.add(
            Step(
                paper_id=step.paper_id, kind="ocsr", queue=step.queue, engine=step.engine,
                segment_id=segment_id, seq=step.seq + 100, status=status,
                created_at=step.created_at + timedelta(seconds=later_s),
            )
        )  # fmt: skip
    else:
        step.status = status
        step.error_class = "engine_error" if status == "failed" else None
    await db.commit()


async def test_failed_structures_are_counted_apart_from_to_review(app, async_db_session):
    """A structure whose newest read failed (no valid prediction, no decision) is `failed`,
    not `to_review`, as the workspace counts it (cardState)."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    a, b = seeded.segment_ids
    await _ocsr_step(db, a, "failed")
    async with make_client(app, token) as c:
        listed = (await c.get("/api/v2/papers")).json()["papers"]
        detail = (await c.get(f"/api/v2/papers/{seeded.paper_id}")).json()
    assert _counts(listed[0]) == (2, 0, 0, 1, 0, 1)
    assert _counts(detail) == (2, 0, 0, 1, 0, 1)
    assert b


async def test_failed_structure_not_counted_when_retried_or_decided(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    a, b = seeded.segment_ids
    await _ocsr_step(db, a, "failed")
    await _ocsr_step(db, a, "running", later_s=5)  # a retry in flight: reading, to check
    await _ocsr_step(db, b, "failed")
    await db.execute(update(Curation).where(Curation.segment_id == b).values(status="rejected"))
    await db.commit()
    async with make_client(app, token) as c:
        listed = (await c.get("/api/v2/papers")).json()["papers"]
    assert _counts(listed[0]) == (2, 0, 1, 1, 0, 0)


async def test_failed_newer_read_with_a_valid_prediction_is_to_review(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)  # each segment has a valid decimer prediction
    a, _ = seeded.segment_ids
    await _ocsr_step(db, a, "failed", later_s=5)
    async with make_client(app, token) as c:
        listed = (await c.get("/api/v2/papers")).json()["papers"]
    assert _counts(listed[0]) == (2, 0, 0, 2, 0, 0)


async def test_failed_page_retried_ok_is_not_counted(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    await _fail_step(db, seeded.paper_id, "segment_page")
    await _add_step(db, seeded.paper_id, "segment_page", "done")
    async with make_client(app, token) as c:
        listed = (await c.get("/api/v2/papers")).json()["papers"]
    assert listed[0]["failed_pages"] == 0


async def test_failed_page_retry_running_is_not_counted(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    await _fail_step(db, seeded.paper_id, "render_page")
    await _add_step(db, seeded.paper_id, "render_page", "running")
    async with make_client(app, token) as c:
        listed = (await c.get("/api/v2/papers")).json()["papers"]
    assert listed[0]["failed_pages"] == 0


async def test_page_with_two_failed_kinds_counts_once(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    await _fail_step(db, seeded.paper_id, "render_page")
    await _fail_step(db, seeded.paper_id, "segment_page")
    async with make_client(app, token) as c:
        listed = (await c.get("/api/v2/papers")).json()["papers"]
    assert listed[0]["failed_pages"] == 1


async def test_list_papers_query_count_does_not_grow_with_papers(
    app, async_db_session, monkeypatch
):
    db = async_db_session
    alice, token = await new_owner(db)
    engine = db.bind.sync_engine if db.bind is not None else db.get_bind()
    n = 0

    def _count(*_a, **_k):
        nonlocal n
        n += 1

    async def statements() -> int:
        nonlocal n
        n = 0
        event.listen(engine, "before_cursor_execute", _count)
        try:
            async with make_client(app, token) as c:
                assert (await c.get("/api/v2/papers")).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", _count)
        return n

    await seed_paper(db, alice)
    await statements()  # warm-up: the first request re-loads the expired owner row
    one = await statements()
    for _ in range(4):
        await seed_paper(db, alice)
    five = await statements()
    assert one == five


PROGRESS_KEYS = (
    "pages_read", "structures_total", "structures_read", "text_read", "check_started", "rereading"
)  # fmt: skip


def _progress(p: dict) -> tuple:
    return tuple(p[k] for k in PROGRESS_KEYS)


async def test_list_rows_carry_the_reads_progress(app, async_db_session):
    """The row bar's progress comes with the list (no steps poll per row): the same figures the
    workspace reads from the steps (frontend readingProgress.ts)."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)  # 1 page read, 2 structures waiting
    a, b = seeded.segment_ids

    async def progress() -> tuple:
        async with make_client(app, token) as c:
            listed = (await c.get("/api/v2/papers")).json()["papers"]
            detail = (await c.get(f"/api/v2/papers/{seeded.paper_id}")).json()
        assert _progress(listed[0]) == _progress(detail)
        return _progress(listed[0])

    assert await progress() == (1, 2, 0, False, True, False)
    await _ocsr_step(db, a, "done")
    await _ocsr_step(db, b, "failed")  # failed with nothing in flight: handled
    assert await progress() == (1, 2, 2, False, True, False)
    await db.execute(
        update(Step)
        .where(Step.paper_id == seeded.paper_id, Step.kind.in_(("docling", "doi")))
        .values(status="done")
    )
    await db.commit()
    assert await progress() == (1, 2, 2, True, True, False)
    await _ocsr_step(db, a, "running", later_s=5)  # another engine on a read structure
    assert await progress() == (1, 2, 2, True, True, True)
    await _ocsr_step(db, b, "running", later_s=5)  # a retry of the failed one: reading
    assert await progress() == (1, 2, 1, True, True, False)


async def test_a_paper_without_a_docling_step_has_its_text_read_with_its_pages(
    app, async_db_session
):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    await db.execute(delete(Step).where(Step.paper_id == seeded.paper_id, Step.kind == "docling"))
    await db.commit()
    async with make_client(app, token) as c:
        listed = (await c.get("/api/v2/papers")).json()["papers"]
    assert listed[0]["text_read"] is True
    await _add_step(db, seeded.paper_id, "segment_page", "running")  # page 0 read again
    async with make_client(app, token) as c:
        listed = (await c.get("/api/v2/papers")).json()["papers"]
    assert (listed[0]["pages_read"], listed[0]["text_read"]) == (0, False)
