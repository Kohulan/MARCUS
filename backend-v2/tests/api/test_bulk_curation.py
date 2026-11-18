"""PUT /papers/{id}/curation: status (and optionally note) for many segments in one call."""

import uuid

from sqlalchemy import select

from marcus.core.models import Curation, Segment
from tests.api.conftest import make_client, new_owner, seed_paper


async def _add_segment(db, paper_id, idx):
    seg = Segment(paper_id=paper_id, page=0, idx=idx, bbox=[0, 0, 1, 1], image_sha256="2" * 64)
    db.add(seg)
    await db.flush()
    db.add(Curation(segment_id=seg.id, status="unchecked"))
    await db.commit()
    return seg.id


async def _three(db, owner):
    seeded = await seed_paper(db, owner)
    third = await _add_segment(db, seeded.paper_id, 2)
    return seeded, [*seeded.segment_ids, third]


async def _row(db, seg) -> Curation:
    return (
        await db.execute(
            select(Curation)
            .where(Curation.segment_id == seg)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _put(app, token, paper, items):
    async with make_client(app, token) as c:
        return await c.put(f"/api/v2/papers/{paper}/curation", json={"items": items})


async def test_bulk_accept_three(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded, segs = await _three(db, alice)
    r = await _put(
        app, token, seeded.paper_id, [{"segment_id": str(s), "status": "accepted"} for s in segs]
    )
    assert r.status_code == 200 and r.json() == {"updated": 3}
    for s in segs:
        assert (await _row(db, s)).status == "accepted"


async def test_bulk_keeps_curated_smiles_and_molfile(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = seeded.segment_ids[0]
    async with make_client(app, token) as c:
        # molfile is not parsed here: write the row directly
        cur = await _row(db, seg)
        cur.smiles, cur.molfile, cur.note = "c1ccccc1", "M  END", "n"
        await db.commit()
        r = await c.put(
            f"/api/v2/papers/{seeded.paper_id}/curation",
            json={"items": [{"segment_id": str(seg), "status": "rejected"}]},
        )
    assert r.status_code == 200
    cur = await _row(db, seg)
    assert (cur.status, cur.smiles, cur.molfile, cur.note) == (
        "rejected",
        "c1ccccc1",
        "M  END",
        "n",
    )


async def _with_note(db, seg, note="keep me"):
    cur = await _row(db, seg)
    cur.note = note
    await db.commit()


async def test_bulk_absent_note_keeps_note(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = seeded.segment_ids[0]
    await _with_note(db, seg)
    r = await _put(app, token, seeded.paper_id, [{"segment_id": str(seg), "status": "accepted"}])
    assert r.status_code == 200
    cur = await _row(db, seg)
    assert (cur.status, cur.note) == ("accepted", "keep me")


async def test_bulk_null_note_clears_note(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    a, b = seeded.segment_ids
    await _with_note(db, a)
    await _with_note(db, b)
    r = await _put(
        app,
        token,
        seeded.paper_id,
        [
            {"segment_id": str(a), "status": "accepted", "note": None},
            {"segment_id": str(b), "status": "accepted", "note": "  new  "},
        ],
    )
    assert r.status_code == 200
    assert (await _row(db, a)).note is None
    assert (await _row(db, b)).note == "  new  "


async def test_bulk_duplicate_segment_422(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = str(seeded.segment_ids[0])
    r = await _put(
        app,
        token,
        seeded.paper_id,
        [{"segment_id": seg, "status": "accepted"}, {"segment_id": seg, "status": "rejected"}],
    )
    assert r.status_code == 422
    assert (await _row(db, seeded.segment_ids[0])).status == "unchecked"


async def test_bulk_foreign_segment_404_and_nothing_changed(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    other = await seed_paper(db, alice)
    items = [
        {"segment_id": str(seeded.segment_ids[0]), "status": "accepted"},
        {"segment_id": str(other.segment_ids[0]), "status": "accepted"},
    ]
    r = await _put(app, token, seeded.paper_id, items)
    assert r.status_code == 404 and r.json() == {"detail": "not found"}
    r = await _put(
        app, token, seeded.paper_id, [{"segment_id": str(uuid.uuid4()), "status": "accepted"}]
    )
    assert r.status_code == 404
    assert (await _row(db, seeded.segment_ids[0])).status == "unchecked"
    assert (await _row(db, other.segment_ids[0])).status == "unchecked"


async def test_bulk_other_owner_paper_404(app, async_db_session):
    db = async_db_session
    alice, _ = await new_owner(db)
    _, bob = await new_owner(db)
    seeded = await seed_paper(db, alice)
    r = await _put(
        app,
        bob,
        seeded.paper_id,
        [{"segment_id": str(seeded.segment_ids[0]), "status": "accepted"}],
    )
    assert r.status_code == 404
    assert (await _row(db, seeded.segment_ids[0])).status == "unchecked"


async def test_bulk_501_items_422(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    items = [{"segment_id": str(uuid.uuid4()), "status": "accepted"} for _ in range(501)]
    assert (await _put(app, token, seeded.paper_id, items)).status_code == 422
    items = [{"segment_id": str(uuid.uuid4()), "status": "accepted"} for _ in range(500)]
    assert (await _put(app, token, seeded.paper_id, items)).status_code == 404  # valid shape


async def test_bulk_empty_422(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    assert (await _put(app, token, seeded.paper_id, [])).status_code == 422
