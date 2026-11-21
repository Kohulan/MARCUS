"""Every owned resource of another owner gives the same 404 as a missing (or deleted) one."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from marcus.core.models import Curation, ImageJob, Step
from tests.api.conftest import make_client, new_owner, paper_row, seed_paper
from tests.factories import make_image_job

NOT_FOUND = {"detail": "not found"}

# (method, path template, json body); {p} = paper id, {s} = segment id, {i} = image job id
ROUTES = [
    ("GET", "/api/v2/papers/{p}", None),
    ("GET", "/api/v2/papers/{p}/segments", None),
    ("DELETE", "/api/v2/papers/{p}", None),
    ("GET", "/api/v2/papers/{p}/pages/0/image", None),
    ("POST", "/api/v2/papers/{p}/pages/0/retry", None),
    ("GET", "/api/v2/papers/{p}/text", None),
    ("GET", "/api/v2/papers/{p}/export?format=json", None),
    ("GET", "/api/v2/papers/{p}/export?format=csv", None),
    ("GET", "/api/v2/papers/{p}/export?format=sdf", None),
    ("GET", "/api/v2/papers/{p}/events", None),
    ("GET", "/api/v2/segments/{s}/image", None),
    ("GET", "/api/v2/segments/{s}/depiction", None),
    ("POST", "/api/v2/segments/{s}/predictions", {"engine": "molnextr"}),
    ("GET", "/api/v2/images/{i}", None),
    ("GET", "/api/v2/images/{i}/image", None),
    ("GET", "/api/v2/images/{i}/events", None),
    ("POST", "/api/v2/images/{i}/predictions", {"engine": "molnextr"}),
    ("PUT", "/api/v2/segments/{s}/curation", {"status": "accepted", "smiles": "CC"}),
    (
        "PUT",
        "/api/v2/papers/{p}/curation",
        {"items": [{"segment_id": "{s}", "status": "accepted"}]},
    ),
]
IDS = [f"{m} {p}" for m, p, _ in ROUTES]


async def seed_image_job(db, owner):
    job, _ = await db.run_sync(lambda s: make_image_job(s, owner))
    await db.commit()
    return job.id


async def set_image_job(db, job_id, **values) -> None:
    await db.execute(update(ImageJob).where(ImageJob.id == job_id).values(**values))
    await db.commit()


async def call(c, method, template, body, p, s, i=None):
    url = template.format(p=p, s=s, i=i)
    if body is not None:  # {s} is filled inside JSON bodies too
        body = json.loads(json.dumps(body).replace("{s}", str(s)))
    return await c.request(method, url, json=body)


@pytest.mark.parametrize(("method", "template", "body"), ROUTES, ids=IDS)
async def test_other_owner_gets_same_404_as_missing(app, async_db_session, method, template, body):
    db = async_db_session
    alice, _ = await new_owner(db)
    _, bob_token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    job_id = await seed_image_job(db, alice)
    seg = seeded.segment_ids[0]
    n_steps = (await db.execute(select(func.count()).select_from(Step))).scalar_one()

    async with make_client(app, bob_token) as c:
        other = await call(c, method, template, body, seeded.paper_id, seg, job_id)
        missing = await call(c, method, template, body, uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

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
    job_id = await seed_image_job(db, alice)
    async with make_client(app, token) as c:
        gone = await c.delete(f"/api/v2/papers/{seeded.paper_id}")
        assert gone.status_code == 204
        await set_image_job(db, job_id, status="deleted")
        r = await call(c, method, template, body, seeded.paper_id, seeded.segment_ids[0], job_id)
    assert r.status_code == 404 and r.json() == NOT_FOUND


async def test_deleted_paper_is_not_listed(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, token) as c:
        await c.delete(f"/api/v2/papers/{seeded.paper_id}")
        r = await c.get("/api/v2/papers")
    assert r.status_code == 200 and r.json() == {"papers": []}


async def _expire_paper(db, paper_id) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from marcus.core.models import Paper

    await db.execute(
        update(Paper)
        .where(Paper.id == paper_id)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db.commit()


@pytest.mark.parametrize(("method", "template", "body"), ROUTES, ids=IDS)
async def test_expired_paper_gets_same_404(app, async_db_session, method, template, body):
    """Expired but not yet purged: served to nobody, not even its owner."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    await _expire_paper(db, seeded.paper_id)
    job_id = await seed_image_job(db, alice)
    await set_image_job(db, job_id, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    async with make_client(app, token) as c:
        r = await call(c, method, template, body, seeded.paper_id, seeded.segment_ids[0], job_id)
        missing = await call(c, method, template, body, uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    assert r.status_code == 404 and r.json() == NOT_FOUND
    assert r.content == missing.content
    assert (await paper_row(db, seeded.paper_id)).status == "processing"  # DELETE did nothing


async def test_expired_paper_is_not_listed(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    expired = await seed_paper(db, alice)
    kept = await seed_paper(db, alice)
    await _expire_paper(db, expired.paper_id)
    async with make_client(app, token) as c:
        r = await c.get("/api/v2/papers")
    assert r.status_code == 200
    assert [p["id"] for p in r.json()["papers"]] == [str(kept.paper_id)]
