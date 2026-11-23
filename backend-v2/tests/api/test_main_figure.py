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
    # no main figure: no links, and nothing to wait for
    paper = await _paper(app, token, paper_id)
    assert set(_repeats(paper).values()) == {None} and paper["links_ready"] is True

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
    paper = await _paper(app, token, paper_id)
    assert set(_repeats(paper).values()) == {None}
    assert paper["links_ready"] is False  # the client must not send to COCONUT on this read
    assert (await _export(app, token, paper_id, "json")).status_code == 503

    monkeypatch.undo()
    assert (await _paper(app, token, paper_id))["links_ready"] is True


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

    # an accepted repeat makes its group accepted (the main one was to review)
    async with make_client(app, token) as client:
        body = {"items": [{"segment_id": str(a), "status": "accepted"}]}
        assert (await client.put(f"/api/v2/papers/{paper_id}/curation", json=body)).is_success
    assert _counts(await _listed(app, token, paper_id)) == (4, 1, 0, 3, 0)

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


# --- one status per linked group (main structure + repeats) ---------------------------------


async def _decide(app, token, paper_id, **statuses):
    items = [{"segment_id": str(sid), "status": st} for sid, st in statuses.items()]
    async with make_client(app, token) as client:
        r = await client.put(f"/api/v2/papers/{paper_id}/curation", json={"items": items})
    assert r.is_success


async def _export_json(app, token, paper_id, status):
    async with make_client(app, token) as client:
        r = await client.get(
            f"/api/v2/papers/{paper_id}/export", params={"format": "json", "status": status}
        )
    return {s["segment_id"]: s for s in json.loads(r.content)["segments"]}


async def test_an_accepted_repeat_of_an_unchecked_main_is_exported_and_counted(
    app, async_db_session
):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, s1, a, b, c) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)
    await _decide(app, token, paper_id, **{str(a): "accepted"})  # OCC on page 1; s0 unchecked

    # the group is accepted: its record is the accepted repeat, at the main one's place
    accepted = await _export_json(app, token, paper_id, "accepted")
    assert list(accepted) == [str(a)]
    assert accepted[str(a)]["status"] == "accepted" and accepted[str(a)]["smiles"] == "OCC"
    assert accepted[str(a)]["also_on_pages"] == [0]
    everything = await _export_json(app, token, paper_id, "all")
    assert list(everything) == [str(a), str(s1), str(b), str(c)]

    async with make_client(app, token) as client:
        sdf = (await client.get(f"/api/v2/papers/{paper_id}/export?format=sdf")).content
    names = [m.GetProp("segment_id") for m in Chem.ForwardSDMolSupplier(io.BytesIO(sdf)) if m]
    assert names == [str(a)]  # SDF exports accepted structures by default

    assert _counts(await _listed(app, token, paper_id)) == (4, 1, 0, 3, 0)
    assert _counts(await _paper(app, token, paper_id)) == (4, 1, 0, 3, 0)


async def test_an_accepted_repeat_of_a_rejected_main_is_kept(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, s1, a, b, c) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)
    await _decide(app, token, paper_id, **{str(s0): "rejected", str(a): "accepted"})
    everything = await _export_json(app, token, paper_id, "all")
    assert everything[str(a)]["status"] == "accepted" and str(s0) not in everything
    async with make_client(app, token) as client:
        rows = (await client.get(f"/api/v2/papers/{paper_id}/export?format=csv")).text
    assert str(a) in rows
    assert _counts(await _listed(app, token, paper_id)) == (4, 1, 0, 3, 0)


async def test_a_group_is_rejected_only_when_every_member_is(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, s1, a, b, c) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)

    # the main one rejected, its repeat to review by its own decision: to review
    await _decide(app, token, paper_id, **{str(s0): "rejected", str(a): "unchecked"})
    assert (await _export_json(app, token, paper_id, "all"))[str(s0)]["status"] == "unchecked"
    assert _counts(await _listed(app, token, paper_id)) == (4, 0, 0, 4, 0)

    # every member rejected: rejected, once
    await _decide(app, token, paper_id, **{str(a): "rejected"})
    everything = await _export_json(app, token, paper_id, "all")
    assert everything[str(s0)]["status"] == "rejected" and str(a) not in everything
    assert await _export_json(app, token, paper_id, "accepted") == {}
    assert _counts(await _listed(app, token, paper_id)) == (4, 0, 1, 3, 0)
    assert _counts(await _paper(app, token, paper_id)) == (4, 0, 1, 3, 0)


# --- the InChIKeys: chunked trips, a partial result kept ------------------------------------


async def test_keys_come_in_chunks_and_a_failed_trip_keeps_what_came_before(
    app, async_db_session, monkeypatch
):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, _, a, _, _) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)
    monkeypatch.setattr(read, "_KEYS", OrderedDict())
    monkeypatch.setattr(read, "CHEM_CHUNK", 2)  # CCO, OCC | CCN
    real = read.CHEM.run
    trips: list[int] = []
    fail_second = True

    async def flaky(fn, items):
        trips.append(len(items))
        if fail_second and len(trips) >= 2:  # the chem process stays busy after one trip
            raise HTTPException(status_code=503, detail="busy, try again")
        return await real(fn, items)

    monkeypatch.setattr(read.CHEM, "run", flaky)
    paper = await _paper(app, token, paper_id)
    assert trips == [2, 1] and paper["links_ready"] is False
    assert len(read._KEYS) == 2  # the first trip's keys are kept
    # the paper list falls back for this paper: every structure counted
    assert _counts(await _listed(app, token, paper_id)) == (5, 0, 0, 5, 0)
    assert trips == [2, 1, 1]  # it asked only for the one missing

    fail_second = False
    trips.clear()
    paper = await _paper(app, token, paper_id)
    assert trips == [1]  # only what was missing
    assert paper["links_ready"] is True and _repeats(paper)[str(a)] == str(s0)


async def test_list_counts_fall_back_per_paper_whose_keys_are_missing(
    app, async_db_session, monkeypatch
):
    db = async_db_session
    alice, token = await new_owner(db)
    ready, _ = await _three_pages(db, alice)
    await _mark(app, token, ready, 0)
    await _paper(app, token, ready)  # its keys are cached now
    late = await seed_paper(db, alice)

    def other_structure(s):
        for p in s.query(Prediction).join(Segment).filter(Segment.paper_id == late.paper_id):
            p.smiles = "CCCCCCO"

    await db.run_sync(other_structure)
    await db.commit()
    await _mark(app, token, late.paper_id, 0)

    async def busy(fn, *args):
        raise HTTPException(status_code=503, detail="busy, try again")

    monkeypatch.setattr(read.CHEM, "run", busy)
    assert _counts(await _listed(app, token, ready)) == (4, 0, 0, 4, 0)
    assert _counts(await _listed(app, token, late.paper_id)) == (2, 0, 0, 2, 0)


# --- a decision on a main card goes to its group; an inherited status that leaves it -------


async def _put(app, token, seg, status, decision=True, **extra):
    body = {"status": status, "smiles": None, "molfile": None, "note": None, **extra}
    query = "?decision=true" if decision else ""
    async with make_client(app, token) as client:
        return await client.put(f"/api/v2/segments/{seg}/curation{query}", json=body)


def _status(paper: dict, seg) -> str | None:
    s = next(s for s in paper["segments"] if s["id"] == str(seg))
    return s["curation"]["status"] if s["curation"] else None


async def _inherited(db) -> dict:
    from sqlalchemy import select

    from marcus.core.models import InheritedStatus

    rows = await db.execute(select(InheritedStatus.segment_id, InheritedStatus.main_id))
    return dict(rows.all())


async def test_rejecting_the_main_card_rejects_the_whole_group(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, s1, a, b, c) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)
    await _decide(app, token, paper_id, **{str(a): "accepted"})  # before any group decision
    assert (await _put(app, token, s0, "rejected")).status_code == 200

    paper = await _paper(app, token, paper_id)
    assert _status(paper, a) == "rejected"
    assert await _inherited(db) == {a: s0}
    assert await _export_json(app, token, paper_id, "accepted") == {}
    assert (await _export_json(app, token, paper_id, "all"))[str(s0)]["status"] == "rejected"
    assert _counts(await _listed(app, token, paper_id)) == (4, 0, 1, 3, 0)


async def test_an_inherited_status_reads_as_to_review_once_the_group_is_gone(
    app, async_db_session
):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, s1, a, b, c) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)
    assert (await _put(app, token, s0, "accepted")).status_code == 200
    paper = await _paper(app, token, paper_id)
    assert _status(paper, a) == "accepted"  # inherited from s0
    assert list(await _export_json(app, token, paper_id, "accepted")) == [str(s0)]

    # the page unmarked: a is a structure of its own again, its inherited status not reviewed
    await _mark(app, token, paper_id, None)
    paper = await _paper(app, token, paper_id)
    assert _status(paper, a) == "unchecked" and _status(paper, s0) == "accepted"
    assert list(await _export_json(app, token, paper_id, "accepted")) == [str(s0)]
    assert _counts(await _listed(app, token, paper_id)) == (5, 1, 0, 4, 0)
    assert _counts(paper) == (5, 1, 0, 4, 0)

    # marked again: it is s0's repeat once more, and the inherited status holds again
    await _mark(app, token, paper_id, 0)
    assert _status(await _paper(app, token, paper_id), a) == "accepted"

    # a decision on its own card sticks, whatever the group does after
    await _mark(app, token, paper_id, None)
    assert (await _put(app, token, a, "accepted")).status_code == 200
    assert await _inherited(db) == {}
    assert _status(await _paper(app, token, paper_id), a) == "accepted"
    assert set(await _export_json(app, token, paper_id, "accepted")) == {str(s0), str(a)}


async def test_an_edit_that_ends_the_group_drops_the_inherited_status(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, _, a, _, _) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)
    assert (await _put(app, token, s0, "accepted")).status_code == 200
    # a note edit on a (no decision) keeps it; a new structure on a moves it out of the group
    async with make_client(app, token) as client:
        body = {"status": "accepted", "smiles": "CCCC", "molfile": None, "note": None}
        assert (await client.put(f"/api/v2/segments/{a}/curation", json=body)).is_success
    paper = await _paper(app, token, paper_id)
    assert _repeats(paper)[str(a)] is None and _status(paper, a) == "unchecked"


async def test_a_note_edit_on_the_main_card_is_not_a_decision(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, _, a, _, _) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)
    await _decide(app, token, paper_id, **{str(a): "accepted"})
    assert (await _put(app, token, s0, "unchecked", decision=False, note="hi")).is_success
    paper = await _paper(app, token, paper_id)
    assert _status(paper, a) == "accepted" and await _inherited(db) == {}


async def test_bulk_decisions_on_main_cards_cover_their_repeats(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, s1, a, b, c) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)
    await _decide(app, token, paper_id, **{str(s0): "accepted", str(b): "rejected"})
    paper = await _paper(app, token, paper_id)
    assert _status(paper, a) == "accepted" and await _inherited(db) == {a: s0}
    # a repeat decided in the same call keeps its own decision
    await _decide(app, token, paper_id, **{str(s0): "rejected", str(a): "accepted"})
    paper = await _paper(app, token, paper_id)
    assert _status(paper, a) == "accepted" and await _inherited(db) == {}


async def test_a_decision_waits_when_the_chem_process_cannot_link(
    app, async_db_session, monkeypatch
):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, _, a, _, _) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)

    async def busy(fn, *args):
        raise HTTPException(status_code=503, detail="busy, try again")

    monkeypatch.setattr(read, "_KEYS", OrderedDict())
    monkeypatch.setattr(read.CHEM, "run", busy)
    assert (await _put(app, token, s0, "accepted")).status_code == 503
    async with make_client(app, token) as client:
        body = {"items": [{"segment_id": str(s0), "status": "accepted"}]}
        r = await client.put(f"/api/v2/papers/{paper_id}/curation", json=body)
    assert r.status_code == 503
    monkeypatch.undo()
    paper = await _paper(app, token, paper_id)
    assert _status(paper, s0) == "unchecked" and _status(paper, a) is None  # nothing written
    assert await _inherited(db) == {}


async def test_a_structure_edit_that_keeps_the_status_is_no_decision(app, async_db_session):
    """The editor fixing a rejected main structure into b's compound must not reject b."""
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, _, a, b, _) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)
    assert (await _put(app, token, s0, "rejected")).status_code == 200
    await _decide(app, token, paper_id, **{str(b): "accepted"})  # CCN, on its own
    edit = await _put(app, token, s0, "rejected", decision=False, smiles="CCN")
    assert edit.status_code == 200
    paper = await _paper(app, token, paper_id)
    assert _repeats(paper)[str(b)] == str(s0) and _status(paper, b) == "accepted"
    assert await _inherited(db) == {a: s0}  # b's own decision stands
    accepted = await _export_json(app, token, paper_id, "accepted")
    assert list(accepted) == [str(b)] and accepted[str(b)]["smiles"] == "CCN"


async def test_a_note_save_keeps_an_inherited_status_shown_as_unchecked(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    paper_id, (s0, _, a, _, _) = await _three_pages(db, alice)
    await _mark(app, token, paper_id, 0)
    assert (await _put(app, token, s0, "rejected")).status_code == 200
    await _mark(app, token, paper_id, None)  # a's inherited "rejected" reads as unchecked now
    assert _status(await _paper(app, token, paper_id), a) == "unchecked"

    r = await _put(app, token, a, "unchecked", decision=False, note="seen")
    assert r.status_code == 200 and r.json()["status"] == "unchecked"
    assert await _inherited(db) == {a: s0}
    await _mark(app, token, paper_id, 0)  # linked again: the inherited status holds again
    paper = await _paper(app, token, paper_id)
    assert _status(paper, a) == "rejected"
    seg = next(s for s in paper["segments"] if s["id"] == str(a))
    assert seg["curation"]["note"] == "seen"
