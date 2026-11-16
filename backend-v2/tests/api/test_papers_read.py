import csv
import io
import json
import uuid
from datetime import UTC, datetime, timedelta

from rdkit import Chem
from sqlalchemy import select, update

from marcus.core import storage
from marcus.core.enums import Engine
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
        "status": "unchecked", "smiles": None, "molfile": None, "note": None,
    }  # fmt: skip
    preds = segs[0]["predictions"]
    assert [p["smiles"] for p in preds] == ["CCN", "CCO"]  # newest first
    assert set(preds[0]) >= {"engine", "engine_version", "smiles", "molfile", "valid", "created_at"}
    assert [p["engine"] for p in preds] == ["molnextr", "decimer"]


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
    assert r.json() == {**body, "molfile": None}
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


# --- export -------------------------------------------------------------------------------


async def _export(app, token, paper_id, fmt):
    async with make_client(app, token) as c:
        return await c.get(f"/api/v2/papers/{paper_id}/export", params={"format": fmt})


async def test_export_sdf_uses_curated_smiles(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)  # both segments predicted "CCO"
    s0, s1 = seeded.segment_ids
    assert (await _curate(app, token, s0, {"status": "accepted", "smiles": "c1ccccc1"})).is_success
    r = await _export(app, token, seeded.paper_id, "sdf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("chemical/x-mdl-sdfile")
    assert r.headers["content-disposition"] == (
        f'attachment; filename="marcus-{seeded.paper_id}.sdf"'
    )
    mols = list(Chem.ForwardSDMolSupplier(io.BytesIO(r.content)))
    assert len(mols) == 2 and all(m is not None for m in mols)
    by_seg = {m.GetProp("segment_id"): m for m in mols}
    assert Chem.MolToSmiles(by_seg[str(s0)]) == "c1ccccc1"
    assert Chem.MolToSmiles(by_seg[str(s1)]) == "CCO"
    assert by_seg[str(s0)].GetProp("page") == "0" and by_seg[str(s1)].GetProp("idx") == "1"
    assert by_seg[str(s0)].GetNumConformers() == 1  # 2D coordinates were computed


async def test_export_prefers_paper_engine_and_skips_rejected(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    s0, s1 = seeded.segment_ids
    later = datetime.now(UTC) + timedelta(seconds=10)

    def add(s):
        # newer predictions: another engine (valid) and the paper's engine (invalid)
        s.add(
            Prediction(
                segment_id=s0,
                engine="molnextr",
                engine_version="m",
                smiles="CCN",
                valid=True,
                ms=1,
                created_at=later,
            )
        )
        s.add(
            Prediction(
                segment_id=s0,
                engine="decimer",
                engine_version="d",
                smiles="C(",
                valid=False,
                ms=1,
                created_at=later,
            )
        )

    await db.run_sync(add)
    await db.commit()
    assert (await _curate(app, token, s1, {"status": "rejected", "smiles": "CC"})).is_success

    r = await _export(app, token, seeded.paper_id, "json")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == (
        f'attachment; filename="marcus-{seeded.paper_id}.json"'
    )
    body = json.loads(r.content)
    assert body["paper"]["id"] == str(seeded.paper_id)
    assert body["paper"]["display_name"] == "paper.pdf"
    assert [(s["segment_id"], s["smiles"], s["source"]) for s in body["segments"]] == [
        (str(s0), "CCO", "predicted"),
    ]

    r = await _export(app, token, seeded.paper_id, "csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows == [
        ["segment_id", "page", "idx", "smiles", "source"],
        [str(s0), "0", "0", "CCO", "predicted"],
    ]  # noqa: E501


async def test_export_falls_back_to_any_engine_and_uses_curated_molfile(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, engine=Engine.MOLNEXTR, ocsr=False)
    s0, s1 = seeded.segment_ids

    def add(s):
        s.add(
            Prediction(
                segment_id=s0, engine="decimer", engine_version="d", smiles="CCCl", valid=True, ms=1
            )
        )

    await db.run_sync(add)
    await db.commit()
    molfile = Chem.MolToMolBlock(Chem.MolFromSmiles("CN"))
    assert (await _curate(app, token, s1, {"status": "accepted", "molfile": molfile})).is_success
    r = await _export(app, token, seeded.paper_id, "sdf")
    mols = {m.GetProp("segment_id"): m for m in Chem.ForwardSDMolSupplier(io.BytesIO(r.content))}
    assert Chem.MolToSmiles(mols[str(s0)]) == "CCCl"
    assert Chem.MolToSmiles(mols[str(s1)]) == "CN"
    r = await _export(app, token, seeded.paper_id, "csv")
    rows = list(csv.reader(io.StringIO(r.text)))[1:]
    assert [(row[0], row[4]) for row in rows] == [(str(s0), "predicted"), (str(s1), "curated")]


async def test_export_bad_format_is_422(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    assert (await _export(app, token, seeded.paper_id, "../../etc/passwd")).status_code == 422


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
