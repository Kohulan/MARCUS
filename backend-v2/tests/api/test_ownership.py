"""Every owned resource of another owner gives the same 404 as a missing (or deleted) one."""

import uuid

import pytest
from sqlalchemy import func, select

from marcus.core.models import Curation, Step
from tests.api.conftest import make_client, new_owner, paper_row, seed_paper

NOT_FOUND = {"detail": "not found"}

# (method, path template, json body); {p} = paper id, {s} = segment id
ROUTES = [
    ("GET", "/api/v2/papers/{p}", None),
    ("GET", "/api/v2/papers/{p}/segments", None),
    ("DELETE", "/api/v2/papers/{p}", None),
    ("GET", "/api/v2/papers/{p}/pages/0/image", None),
    ("GET", "/api/v2/papers/{p}/text", None),
    ("GET", "/api/v2/papers/{p}/export?format=json", None),
    ("GET", "/api/v2/papers/{p}/export?format=csv", None),
    ("GET", "/api/v2/papers/{p}/export?format=sdf", None),
    ("GET", "/api/v2/papers/{p}/events", None),
    ("GET", "/api/v2/segments/{s}/image", None),
    ("POST", "/api/v2/segments/{s}/predictions", {"engine": "molnextr"}),
    ("PUT", "/api/v2/segments/{s}/curation", {"status": "accepted", "smiles": "CC"}),
]
IDS = [f"{m} {p}" for m, p, _ in ROUTES]


async def call(c, method, template, body, p, s):
    url = template.format(p=p, s=s)
    return await c.request(method, url, json=body)


@pytest.mark.parametrize(("method", "template", "body"), ROUTES, ids=IDS)
async def test_other_owner_gets_same_404_as_missing(app, async_db_session, method, template, body):
    db = async_db_session
    alice, _ = await new_owner(db)
    _, bob_token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    seg = seeded.segment_ids[0]
    n_steps = (await db.execute(select(func.count()).select_from(Step))).scalar_one()

    async with make_client(app, bob_token) as c:
        other = await call(c, method, template, body, seeded.paper_id, seg)
        missing = await call(c, method, template, body, uuid.uuid4(), uuid.uuid4())

    assert other.status_code == 404 and missing.status_code == 404
    assert other.json() == NOT_FOUND == missing.json()
    assert other.content == missing.content
    # nothing changed for alice
    assert (await paper_row(db, seeded.paper_id)).status == "processing"
    assert (await db.execute(select(func.count()).select_from(Step))).scalar_one() == n_steps
    cur = (
        await db.execute(
            select(Curation)
            .where(Curation.segment_id == seg)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert (cur.status, cur.smiles) == ("unchecked", None)


@pytest.mark.parametrize(("method", "template", "body"), ROUTES, ids=IDS)
async def test_deleted_paper_gets_same_404(app, async_db_session, method, template, body):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, token) as c:
        assert (await c.delete(f"/api/v2/papers/{seeded.paper_id}")).status_code == 204
        r = await call(c, method, template, body, seeded.paper_id, seeded.segment_ids[0])
    assert r.status_code == 404 and r.json() == NOT_FOUND


async def test_deleted_paper_is_not_listed(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, token) as c:
        await c.delete(f"/api/v2/papers/{seeded.paper_id}")
        r = await c.get("/api/v2/papers")
    assert r.status_code == 200 and r.json() == {"papers": []}
