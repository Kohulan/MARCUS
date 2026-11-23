"""GET /papers/{id}: the compound ID printed by each drawing and the compound's name
(marcus.core.compound_ids), read from the paper's Docling text; a repeat of a main-figure
compound links to it by that ID too (marcus.core.main_figure)."""

import json
import uuid

from marcus.api import read
from marcus.core import storage
from marcus.core.agreement import inchikey_of
from marcus.core.models import Paper, Prediction, Segment
from tests.api.conftest import make_client, new_owner, seed_paper

PT = 72 / 300  # one 300 DPI pixel in PDF points
HEIGHT = 842.0


def id_box(text, x_px, y_px, page_no):
    """A 20 x 20 px text box whose top left corner is at (x_px, y_px) of the page render."""
    bbox = {
        "l": x_px * PT, "r": (x_px + 20) * PT,
        "t": HEIGHT - y_px * PT, "b": HEIGHT - (y_px + 20) * PT,
        "coord_origin": "BOTTOMLEFT",
    }  # fmt: skip
    return {"text": text, "prov": [{"page_no": page_no, "bbox": bbox}]}


def document(texts):
    pages = {str(n): {"size": {"width": 595.0, "height": HEIGHT}, "page_no": n} for n in (1, 2)}
    return {"pages": pages, "texts": texts}


async def _paper(app, token, paper_id):
    async with make_client(app, token) as client:
        r = await client.get(f"/api/v2/papers/{paper_id}")
    assert r.status_code == 200
    return r.json()


async def test_ids_and_names_from_the_text(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)  # page 0: [0, 0, 10, 10] and [5, 5, 50, 60]
    first, second = seeded.segment_ids
    doc = document([
        id_box("3", 20, 70, 1),  # under the second crop
        {"text": "Salsubstolin C (3) was obtained as a white powder.", "prov": []},
    ])  # fmt: skip
    storage.text_path(seeded.paper_id).write_text(json.dumps(doc))
    paper = await _paper(app, token, seeded.paper_id)
    got = {s["id"]: (s["compound_id"], s["compound_name"]) for s in paper["segments"]}
    assert got[str(second)] == ("3", "Salsubstolin C")
    assert got[str(first)] == (None, None)


async def test_no_text_no_ids(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, write_files=False)
    paper = await _paper(app, token, seeded.paper_id)
    assert {(s["compound_id"], s["compound_name"]) for s in paper["segments"]} == {(None, None)}


async def test_a_compound_id_links_a_drawing_without_a_structure_and_flags_a_different_one(
    app, async_db_session
):
    """Owner decision 2026-11-22. Page 1 prints compound 3 of the main figure (page 0) twice: an
    annotated drawing no engine could read (no InChIKey) links to it by the ID; a drawing read
    as another structure (another InChIKey) stays a card of its own, and both it and the main
    card say "same ID"."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    main = seeded.segment_ids[1]

    def add(s):
        s.get(Paper, seeded.paper_id).pages = 2
        ids = []
        for idx, (bbox, smiles, valid) in enumerate(
            [([100, 100, 300, 300], "C(", False), ([400, 100, 600, 300], "CCCN", True)]
        ):
            seg = Segment(
                id=uuid.uuid4(), paper_id=seeded.paper_id, page=1, idx=idx, bbox=bbox,
                image_sha256=str(idx) * 64,
            )  # fmt: skip
            s.add(seg)
            s.flush()
            s.add(Prediction(segment_id=seg.id, engine="decimer", engine_version="t",
                             smiles=smiles, valid=valid, ms=1, rgroups=[],
                             inchikey=inchikey_of(smiles, valid)))  # fmt: skip
            ids.append(seg.id)
        return ids

    unread, other = await db.run_sync(add)
    await db.commit()
    doc = document([id_box("3", 20, 70, 1), id_box("(3)", 190, 320, 2), id_box("3", 490, 320, 2)])
    storage.text_path(seeded.paper_id).write_text(json.dumps(doc))
    read._LABELS.clear()
    async with make_client(app, token) as client:
        r = await client.put(f"/api/v2/papers/{seeded.paper_id}/main-figure", json={"page": 0})
    assert r.status_code == 200
    paper = await _paper(app, token, seeded.paper_id)
    by_id = {s["id"]: s for s in paper["segments"]}
    assert by_id[str(unread)]["compound_id"] == "3"
    assert by_id[str(unread)]["repeat_of"] == str(main)
    assert by_id[str(unread)]["same_id_pages"] == []
    assert by_id[str(other)]["compound_id"] == "3"
    assert by_id[str(other)]["repeat_of"] is None
    assert by_id[str(other)]["same_id_pages"] == [0]
    assert by_id[str(main)]["same_id_pages"] == [1]
    # the paper list counts the linked one once, the other one on its own (the same links)
    async with make_client(app, token) as client:
        listed = (await client.get("/api/v2/papers")).json()["papers"]
    assert [p["structures"] for p in listed] == [3]


async def test_the_text_is_read_once_and_a_busy_chem_process_shows_no_ids(
    app, async_db_session, monkeypatch
):
    from fastapi import HTTPException

    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    storage.text_path(seeded.paper_id).write_text(json.dumps(document([id_box("3", 20, 70, 1)])))
    read._LABELS.clear()
    real = read.CHEM.run

    async def busy(fn, *args):
        if fn is read.compound_ids.labels_from_file:
            raise HTTPException(status_code=503, detail="busy, try again")
        return await real(fn, *args)

    monkeypatch.setattr(read.CHEM, "run", busy)
    paper = await _paper(app, token, seeded.paper_id)
    assert {s["compound_id"] for s in paper["segments"]} == {None}  # the read still answers
    asked = []

    async def counting(fn, *args):
        if fn is read.compound_ids.labels_from_file:
            asked.append(fn)
        return await real(fn, *args)

    monkeypatch.setattr(read.CHEM, "run", counting)
    for _ in range(2):
        paper = await _paper(app, token, seeded.paper_id)
        assert {s["compound_id"] for s in paper["segments"]} == {None, "3"}
    assert len(asked) == 1
