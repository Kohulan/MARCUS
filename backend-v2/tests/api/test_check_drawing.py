"""GET /papers/{id}: each segment says whether its crop needs a look ("check this drawing")."""

from marcus.core.models import DrawingFlag
from tests.api.conftest import make_client, new_owner, seed_paper


async def test_segments_carry_the_drawing_check(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    first, second = seeded.segment_ids

    db.add(DrawingFlag(segment_id=first))  # the second has no row: clean, or not told
    await db.commit()
    async with make_client(app, token) as client:
        r = await client.get(f"/api/v2/papers/{seeded.paper_id}")
    assert r.status_code == 200
    got = {s["id"]: s["check_drawing"] for s in r.json()["segments"]}
    assert got == {str(first): True, str(second): False}
