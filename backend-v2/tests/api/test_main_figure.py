"""The main figure: one page per paper marked as its compound list (PUT /papers/{id}/main-figure),
repeats of its structures on other pages (SegmentOut.repeat_of), and exports that count each
compound once."""

import csv
import io
import json
import uuid
from collections import OrderedDict

from fastapi import HTTPException
from rdkit import Chem

from marcus.api import read
from marcus.core.models import Paper, Prediction, Segment
from tests.api.conftest import make_client, new_owner, seed_paper


async def _three_pages(db, owner):
    """A 3-page paper. Page 0 (seed_paper): s0 and s1, both "CCO". Page 1: a "OCC" (the same
    compound as CCO), b "CCN". Page 2: c "*CC" (a scaffold, R-group label R)."""
    seeded = await seed_paper(db, owner)
    s0, s1 = seeded.segment_ids

    def add(s):
        s.get(Paper, seeded.paper_id).pages = 3
        rows = [(1, 0, "OCC", []), (1, 1, "CCN", []), (2, 0, "*CC", ["R"])]
        ids = []
        for page, idx, smiles, rgroups in rows:
            seg = Segment(
                id=uuid.uuid4(),
                paper_id=seeded.paper_id,
                page=page,
                idx=idx,
                bbox=[0, 0, 10, 10],
                image_sha256=f"{page}{idx}".ljust(64, "a"),
            )
            s.add(seg)
            s.flush()
            s.add(
                Prediction(
                    segment_id=seg.id,
                    engine="decimer",
                    engine_version="t1",
                    smiles=smiles,
                    valid=True,
                    ms=1,
                    rgroups=rgroups,
                )
            )
            ids.append(seg.id)
        return ids

    a, b, c = await db.run_sync(add)
    await db.commit()
    return seeded.paper_id, (s0, s1, a, b, c)


async def _mark(app, token, paper_id, page):
    async with make_client(app, token) as client:
        return await client.put(f"/api/v2/papers/{paper_id}/main-figure", json={"page": page})


async def _paper(app, token, paper_id):
    async with make_client(app, token) as client:
        r = await client.get(f"/api/v2/papers/{paper_id}")
    assert r.status_code == 200
    return r.json()


def _repeats(paper: dict) -> dict[str, str | None]:
    return {s["id"]: s["repeat_of"] for s in paper["segments"]}


async def test_mark_set_move_and_clear(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, _ = await _three_pages(db, alice)
    assert (await _paper(app, token, paper_id))["main_figure_page"] is None

    r = await _mark(app, token, paper_id, 1)
    assert r.status_code == 200 and r.json() == {"main_figure_page": 1}
    assert (await _paper(app, token, paper_id))["main_figure_page"] == 1

    assert (await _mark(app, token, paper_id, 2)).json() == {"main_figure_page": 2}  # one only
    assert (await _paper(app, token, paper_id))["main_figure_page"] == 2

    assert (await _mark(app, token, paper_id, None)).json() == {"main_figure_page": None}
    assert (await _paper(app, token, paper_id))["main_figure_page"] is None


async def test_mark_rejects_bad_pages_and_other_owners(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    _, bob_token = await new_owner(db)
    paper_id, _ = await _three_pages(db, alice)
    assert (await _mark(app, token, paper_id, 3)).status_code == 422  # pages 0..2
    assert (await _mark(app, token, paper_id, -1)).status_code == 422
    async with make_client(app, token) as client:
        url = f"/api/v2/papers/{paper_id}/main-figure"
        assert (await client.put(url, json={})).status_code == 422  # null clears; a key is due
        assert (await client.put(url, json={"page": 0, "x": 1})).status_code == 422
    assert (await _mark(app, bob_token, paper_id, 0)).status_code == 404
    assert (await _paper(app, token, paper_id))["main_figure_page"] is None


async def test_repeats_link_to_the_main_figure_by_inchikey(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, s1, a, b, c) = await _three_pages(db, alice)
    # no main figure: no links
    assert set(_repeats(await _paper(app, token, paper_id)).values()) == {None}

    await _mark(app, token, paper_id, 0)
    links = _repeats(await _paper(app, token, paper_id))
    # OCC on page 1 is CCO: it repeats the first CCO of the main page. The two CCO on the main
    # page stay two structures; CCN is another compound; a scaffold is never a repeat.
    assert links == {str(s0): None, str(s1): None, str(a): str(s0), str(b): None, str(c): None}

    async with make_client(app, token) as client:
        segs = (await client.get(f"/api/v2/papers/{paper_id}/segments")).json()["segments"]
    assert {s["id"]: s["repeat_of"] for s in segs} == links

    # another main page: page 1's structures are now the main ones, page 0's CCO repeat OCC
    await _mark(app, token, paper_id, 1)
    links = _repeats(await _paper(app, token, paper_id))
    assert links == {str(s0): str(a), str(s1): str(a), str(a): None, str(b): None, str(c): None}


async def test_a_curated_structure_links_by_what_it_shows(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, _, a, b, _) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)
    async with make_client(app, token) as client:
        # b is corrected to CCO (as a molfile): now a repeat of s0
        molfile = Chem.MolToMolBlock(Chem.MolFromSmiles("CCO"))
        body = {"status": "accepted", "smiles": None, "molfile": molfile, "note": None}
        assert (await client.put(f"/api/v2/segments/{b}/curation", json=body)).is_success
        # a is corrected to something else: no longer a repeat
        body = {"status": "unchecked", "smiles": "CCCC", "molfile": None, "note": None}
        assert (await client.put(f"/api/v2/segments/{a}/curation", json=body)).is_success
    links = _repeats(await _paper(app, token, paper_id))
    assert links[str(a)] is None and links[str(b)] == str(s0)


async def _export(app, token, paper_id, fmt):
    async with make_client(app, token) as client:
        return await client.get(
            f"/api/v2/papers/{paper_id}/export", params={"format": fmt, "status": "all"}
        )


async def test_exports_count_each_compound_once(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, s1, a, b, c) = await _three_pages(db, alice)

    doc = json.loads((await _export(app, token, paper_id, "json")).content)
    assert len(doc["segments"]) == 5 and doc["paper"]["main_figure_page"] is None
    assert all(seg["also_on_pages"] == [] for seg in doc["segments"])

    await _mark(app, token, paper_id, 0)
    doc = json.loads((await _export(app, token, paper_id, "json")).content)
    assert doc["paper"]["main_figure_page"] == 0
    by_id = {seg["segment_id"]: seg for seg in doc["segments"]}
    assert set(by_id) == {str(s0), str(s1), str(b), str(c)}  # a (OCC = CCO) is left out
    assert by_id[str(s0)]["also_on_pages"] == [1]
    assert by_id[str(s1)]["also_on_pages"] == []

    rows = list(csv.reader(io.StringIO((await _export(app, token, paper_id, "csv")).text)))
    assert {r[0] for r in rows[1:]} == {str(s0), str(s1), str(b), str(c)}

    sdf = (await _export(app, token, paper_id, "sdf")).content
    names = {m.GetProp("segment_id") for m in Chem.ForwardSDMolSupplier(io.BytesIO(sdf)) if m}
    assert str(a) not in names and str(s0) in names


async def test_busy_chem_process_a_read_shows_no_links_an_export_waits(
    app, async_db_session, monkeypatch
):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, _ = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)

    async def busy(fn, *args):
        raise HTTPException(status_code=503, detail="busy, try again")

    monkeypatch.setattr(read, "_KEYS", OrderedDict())  # nothing known yet
    monkeypatch.setattr(read.CHEM, "run", busy)
    assert set(_repeats(await _paper(app, token, paper_id)).values()) == {None}
    assert (await _export(app, token, paper_id, "json")).status_code == 503


async def test_inchikeys_are_cached_per_structure(app, async_db_session, monkeypatch):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, _, a, _, _) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)
    monkeypatch.setattr(read, "_KEYS", OrderedDict())
    real = read.CHEM.run
    asked: list[int] = []

    async def counting(fn, items):
        asked.append(len(items))
        return await real(fn, items)

    monkeypatch.setattr(read.CHEM, "run", counting)
    assert _repeats(await _paper(app, token, paper_id))[str(a)] == str(s0)
    assert _repeats(await _paper(app, token, paper_id))[str(a)] == str(s0)
    assert asked == [3]  # CCO (twice the same), OCC, CCN, in one trip; the second read: none


# --- counts: the paper list counts each compound once ----------------------------------------


async def _listed(app, token, paper_id):
    async with make_client(app, token) as client:
        papers = (await client.get("/api/v2/papers")).json()["papers"]
    return next(p for p in papers if p["id"] == str(paper_id))


def _counts(p: dict) -> tuple[int, int, int, int, int]:
    return p["structures"], p["accepted"], p["rejected"], p["to_review"], p["failed"]


async def test_the_paper_list_leaves_repeats_out_of_its_counts(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (_, _, a, _, _) = await _three_pages(db, alice)
    other = await seed_paper(db, alice)  # no main figure: counted as before
    assert _counts(await _listed(app, token, paper_id)) == (5, 0, 0, 5, 0)

    await _mark(app, token, paper_id, 0)
    assert _counts(await _listed(app, token, paper_id)) == (4, 0, 0, 4, 0)  # a repeats s0
    assert _counts(await _listed(app, token, other.paper_id)) == (2, 0, 0, 2, 0)
    # the paper's own read counts the same
    assert _counts(await _paper(app, token, paper_id)) == (4, 0, 0, 4, 0)

    # an accepted repeat leaves "accepted", not "to review"
    async with make_client(app, token) as client:
        body = {"items": [{"segment_id": str(a), "status": "accepted"}]}
        assert (await client.put(f"/api/v2/papers/{paper_id}/curation", json=body)).is_success
    assert _counts(await _listed(app, token, paper_id)) == (4, 0, 0, 4, 0)

    await _mark(app, token, paper_id, None)
    assert _counts(await _listed(app, token, paper_id)) == (5, 1, 0, 4, 0)


async def test_list_counts_ask_the_chem_process_only_for_papers_with_a_main_figure(
    app, async_db_session, monkeypatch
):
    db = async_db_session
    alice, token = await new_owner(db)
    first, _ = await _three_pages(db, alice)
    second, _ = await _three_pages(db, alice)
    monkeypatch.setattr(read, "_KEYS", OrderedDict())
    real = read.CHEM.run
    asked: list[int] = []

    async def counting(fn, items):
        asked.append(len(items))
        return await real(fn, items)

    monkeypatch.setattr(read.CHEM, "run", counting)
    await _listed(app, token, first)
    assert asked == []  # no main figure, no work
    await _mark(app, token, first, 0)
    await _mark(app, token, second, 0)
    assert _counts(await _listed(app, token, first)) == (4, 0, 0, 4, 0)
    assert _counts(await _listed(app, token, second)) == (4, 0, 0, 4, 0)
    assert asked == [3]  # both papers in one trip (same 3 structures), then the cache


async def test_list_counts_with_a_busy_chem_process_count_every_structure(
    app, async_db_session, monkeypatch
):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, _ = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)

    async def busy(fn, *args):
        raise HTTPException(status_code=503, detail="busy, try again")

    monkeypatch.setattr(read, "_KEYS", OrderedDict())
    monkeypatch.setattr(read.CHEM, "run", busy)
    assert _counts(await _listed(app, token, paper_id)) == (5, 0, 0, 5, 0)
