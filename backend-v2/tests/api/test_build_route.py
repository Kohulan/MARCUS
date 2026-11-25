"""POST /segments/{id}/build (Markush Phase 3): the shown scaffold's rows built into cards."""

import pytest
from rdkit import Chem
from sqlalchemy import select

from marcus.core.models import BuiltSegment, Prediction
from tests.api.conftest import make_client, new_owner
from tests.api.test_rgroups import enabled, model_result, run_rgroups, seed_scaffold  # noqa: F401

ROWS = [
    {"compound": "3a", "groups": {"R1": "OMe"}},
    {"compound": "3b", "groups": {"R1": "H"}},
    {"compound": "3c", "groups": {"R1": "Tig"}},
]


def key(smiles: str) -> str:
    return Chem.MolToInchiKey(Chem.MolFromSmiles(smiles))


async def scaffold_with_rows(app, db, rows=ROWS):
    alice, token = await new_owner(db)
    paper_id, scaffold, plain, segment = await seed_scaffold(db, alice)
    async with make_client(app, token) as c:
        r = await c.post(f"/api/v2/predictions/{scaffold}/rgroups")
    assert r.status_code == 202, r.text
    await run_rgroups(db, paper_id, model_result(rows))
    return token, paper_id, segment, plain


async def built_keys(db, scaffold_segment) -> set[str]:
    rows = await db.execute(
        select(Prediction.inchikey)
        .join(BuiltSegment, BuiltSegment.segment_id == Prediction.segment_id)
        .where(BuiltSegment.scaffold_segment_id == scaffold_segment)
    )
    return set(rows.scalars())


@pytest.mark.usefixtures("enabled")
async def test_build_route_builds_the_rows_of_the_shown_scaffold(app, async_db_session):
    token, _, seg, _ = await scaffold_with_rows(app, async_db_session)
    async with make_client(app, token) as c:
        r = await c.post(f"/api/v2/segments/{seg}/build")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "built": 2, "kept": 0, "removed": 0,
        "failures": [{"compound": "3c", "reason": 'unknown substituent "Tig"'}],
    }  # fmt: skip
    assert await built_keys(async_db_session, seg) == {key("COc1ccc(O)cc1"), key("Oc1ccccc1")}


@pytest.mark.usefixtures("enabled")
async def test_build_uses_the_curated_scaffold(app, async_db_session):
    token, _, seg, _ = await scaffold_with_rows(app, async_db_session, ROWS[:1])
    async with make_client(app, token) as c:
        put = await c.put(
            f"/api/v2/segments/{seg}/curation",
            json={"status": "unchecked", "smiles": "[1*]c1ccc(N)cc1"},
        )
        assert put.status_code == 200, put.text
        r = await c.post(f"/api/v2/segments/{seg}/build")
    assert r.status_code == 200, r.text
    assert await built_keys(async_db_session, seg) == {key("COc1ccc(N)cc1")}


async def test_build_without_rows_is_409(app, async_db_session):
    alice, token = await new_owner(async_db_session)
    _, _, _, seg = await seed_scaffold(async_db_session, alice)
    async with make_client(app, token) as c:
        r = await c.post(f"/api/v2/segments/{seg}/build")
    assert r.status_code == 409 and r.json() == {"detail": "no_rows"}


@pytest.mark.usefixtures("enabled")
async def test_build_on_a_plain_structure_is_409(app, async_db_session):
    token, paper_id, _, _ = await scaffold_with_rows(app, async_db_session)
    async with make_client(app, token) as c:
        segs = (await c.get(f"/api/v2/papers/{paper_id}")).json()["segments"]
        plain = next(s["id"] for s in segs if not any(p["rgroups"] for p in s["predictions"]))
        r = await c.post(f"/api/v2/segments/{plain}/build")
    assert r.status_code == 409 and r.json() == {"detail": "no_rgroups"}


@pytest.mark.usefixtures("enabled")
async def test_build_on_a_built_segment_is_409(app, async_db_session):
    token, _, seg, _ = await scaffold_with_rows(app, async_db_session)
    async with make_client(app, token) as c:
        await c.post(f"/api/v2/segments/{seg}/build")
        built = (
            (
                await async_db_session.execute(
                    select(BuiltSegment.segment_id).where(BuiltSegment.scaffold_segment_id == seg)
                )
            )
            .scalars()
            .first()
        )
        r = await c.post(f"/api/v2/segments/{built}/build")
    assert r.status_code == 409 and r.json() == {"detail": "built"}
