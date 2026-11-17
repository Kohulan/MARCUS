"""GET /segments/{id}/depiction: the shown structure, drawn once by the tools worker, then read."""

import hashlib
import uuid

import pytest
from fastapi import HTTPException
from rdkit import Chem
from sqlalchemy import select

from marcus.api import depiction, security
from marcus.core import storage
from marcus.core.models import Curation, Prediction
from marcus.core.settings import get_settings
from tests.api.conftest import make_client, new_owner, seed_paper

FIXED_NOW = 1_800_000_030.0  # 30 s into a rate-limit window


def svg_for(smiles: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg"><!-- {smiles} --></svg>'


def url(seg, query: str = "") -> str:
    return f"/api/v2/segments/{seg}/depiction{query}"


def sha(smiles: str) -> str:
    return hashlib.sha256(smiles.encode()).hexdigest()


def depiction_files() -> list:
    root = get_settings().data_root / "depictions"
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


@pytest.fixture
def draws(monkeypatch):
    """Fake tools worker: records each call and answers with a small SVG of the SMILES."""
    seen = []
    behaviour = {}  # smiles -> callable(smiles) giving the result or raising

    def fake(name, kwargs, timeout):
        seen.append((name, kwargs, timeout))
        act = behaviour.get(kwargs["smiles"])
        return act(kwargs["smiles"]) if act else svg_for(kwargs["smiles"])

    monkeypatch.setattr(depiction, "run_tool", fake)
    fake.seen = seen
    fake.behaviour = behaviour
    return fake


async def _curation(db, seg) -> Curation:
    return (
        await db.execute(
            select(Curation)
            .where(Curation.segment_id == seg)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _curate(db, seg, *, status="unchecked", smiles=None, molfile=None) -> None:
    cur = await _curation(db, seg)
    cur.status, cur.smiles, cur.molfile = status, smiles, molfile
    await db.commit()


async def _predict(db, seg, engine: str, smiles: str, valid: bool = True) -> None:
    db.add(
        Prediction(
            segment_id=seg,
            engine=engine,
            engine_version="t1",
            smiles=smiles,
            valid=valid,
            ms=1,
        )
    )
    await db.commit()


async def _owner_paper(db, **kw):
    owner, token = await new_owner(db)
    seeded = await seed_paper(db, owner, **kw)
    return owner, token, seeded


async def test_depiction_miss_draws_once_then_reads_file(app, async_db_session, draws):
    _, token, seeded = await _owner_paper(async_db_session)
    seg = seeded.segment_ids[0]
    async with make_client(app, token) as c:
        first = await c.get(url(seg))
        second = await c.get(url(seg))
    assert first.status_code == second.status_code == 200
    assert first.content == second.content == svg_for("CCO").encode()
    assert len(draws.seen) == 1
    name, kwargs, timeout = draws.seen[0]
    assert name == "marcus.tools.depict"
    assert kwargs == {"smiles": "CCO", "fmt": "svg", "width": 512, "height": 512, "highlight": ""}
    assert timeout == 10
    assert storage.depiction_path(sha("CCO")).read_bytes() == first.content


async def test_depiction_two_segments_same_smiles_one_draw(app, async_db_session, draws):
    _, token, seeded = await _owner_paper(async_db_session)
    async with make_client(app, token) as c:
        a = await c.get(url(seeded.segment_ids[0]))
        b = await c.get(url(seeded.segment_ids[1]))
    assert a.status_code == b.status_code == 200 and a.content == b.content
    assert len(draws.seen) == 1


async def test_depiction_curated_smiles_used_without_engine(app, async_db_session, draws):
    db = async_db_session
    _, token, seeded = await _owner_paper(db)
    seg = seeded.segment_ids[0]
    await _curate(db, seg, status="accepted", smiles="c1ccccc1")
    async with make_client(app, token) as c:
        r = await c.get(url(seg))
    assert r.status_code == 200 and r.content == svg_for("c1ccccc1").encode()


async def test_depiction_curated_molfile_only_uses_derived_smiles(app, async_db_session, draws):
    db = async_db_session
    _, token, seeded = await _owner_paper(db)
    seg = seeded.segment_ids[0]
    molfile = Chem.MolToMolBlock(Chem.MolFromSmiles("c1ccncc1"))
    await _curate(db, seg, status="accepted", molfile=molfile)
    async with make_client(app, token) as c:
        r = await c.get(url(seg))
    assert r.status_code == 200
    assert [k["smiles"] for _, k, _ in draws.seen] == ["c1ccncc1"]


async def test_depiction_rejected_segment_still_drawn(app, async_db_session, draws):
    db = async_db_session
    _, token, seeded = await _owner_paper(db)
    first, second = seeded.segment_ids
    await _curate(db, first, status="rejected", smiles="CCN")
    await _curate(db, second, status="rejected")  # no curated structure: the prediction
    async with make_client(app, token) as c:
        a = await c.get(url(first))
        b = await c.get(url(second))
    assert a.status_code == b.status_code == 200
    assert a.content == svg_for("CCN").encode() and b.content == svg_for("CCO").encode()


async def test_depiction_engine_param_picks_that_engine(app, async_db_session, draws):
    db = async_db_session
    _, token, seeded = await _owner_paper(db)
    seg = seeded.segment_ids[0]
    await _predict(db, seg, "molnextr", "CCCl")
    await _predict(db, seg, "molscribe", "CCBr", valid=False)
    await _curate(db, seg, status="accepted", smiles="CCN")  # ignored with an engine
    async with make_client(app, token) as c:
        decimer = await c.get(url(seg, "?engine=decimer"))
        molnextr = await c.get(url(seg, "?engine=molnextr"))
        molscribe = await c.get(url(seg, "?engine=molscribe"))
        unknown = await c.get(url(seg, "?engine=nope"))
    assert decimer.content == svg_for("CCO").encode()
    assert molnextr.content == svg_for("CCCl").encode()
    assert molscribe.status_code == 404 and molscribe.json() == {"detail": "not found"}
    assert unknown.status_code == 422
    assert [k["smiles"] for _, k, _ in draws.seen] == ["CCO", "CCCl"]


async def test_depiction_without_engine_prefers_paper_engine(app, async_db_session, draws):
    db = async_db_session
    _, token, seeded = await _owner_paper(db)
    seg = seeded.segment_ids[0]
    await _predict(db, seg, "molnextr", "CCCl")  # newer, but not the paper's engine
    async with make_client(app, token) as c:
        r = await c.get(url(seg))
    assert r.content == svg_for("CCO").encode()


async def test_depiction_v_param_ignored(app, async_db_session, draws):
    _, token, seeded = await _owner_paper(async_db_session)
    seg = seeded.segment_ids[0]
    async with make_client(app, token) as c:
        a = await c.get(url(seg, "?v=abc"))
        b = await c.get(url(seg, "?v=xyz&engine=decimer"))
    assert a.status_code == b.status_code == 200 and a.content == b.content
    assert len(draws.seen) == 1


async def test_depiction_no_valid_prediction_404(app, async_db_session, draws):
    db = async_db_session
    _, token, seeded = await _owner_paper(db, ocsr=False)
    first, second = seeded.segment_ids
    await _predict(db, second, "decimer", "CCO", valid=False)
    async with make_client(app, token) as c:
        a = await c.get(url(first))
        b = await c.get(url(second))
    assert a.status_code == b.status_code == 404
    assert a.json() == b.json() == {"detail": "not found"}
    assert draws.seen == []


async def test_depiction_other_owner_404(app, async_db_session, draws):
    db = async_db_session
    _, _, seeded = await _owner_paper(db)
    _, bob = await new_owner(db)
    async with make_client(app, bob) as c:
        other = await c.get(url(seeded.segment_ids[0]))
        missing = await c.get(url(uuid.uuid4()))
    assert other.status_code == missing.status_code == 404
    assert other.content == missing.content
    assert draws.seen == []


async def test_depiction_headers(app, async_db_session, draws):
    _, token, seeded = await _owner_paper(async_db_session)
    async with make_client(app, token) as c:
        miss = await c.get(url(seeded.segment_ids[0]))
        hit = await c.get(url(seeded.segment_ids[0]))
    for r in (miss, hit):
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/svg+xml"
        assert r.headers["cache-control"] == "private, max-age=86400"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert (
            r.headers["content-security-policy"] == "default-src 'none'; style-src 'unsafe-inline'"
        )


@pytest.mark.parametrize("status", [504, 500, 503])
async def test_depiction_tool_timeout_503_no_file(app, async_db_session, draws, status):
    def fail(smiles):
        raise HTTPException(status_code=status, detail="tool timed out")

    draws.behaviour["CCO"] = fail
    _, token, seeded = await _owner_paper(async_db_session)
    async with make_client(app, token) as c:
        r = await c.get(url(seeded.segment_ids[0]))
    assert r.status_code == 503 and r.headers["retry-after"] == "5"
    assert "timed out" not in r.text
    assert depiction_files() == []


async def test_depiction_bad_smiles_404_marker_then_no_redraw(app, async_db_session, draws):
    def bad(smiles):
        raise HTTPException(status_code=422, detail="cannot parse SMILES: secret detail")

    draws.behaviour["CCO"] = bad
    _, token, seeded = await _owner_paper(async_db_session)
    async with make_client(app, token) as c:
        first = await c.get(url(seeded.segment_ids[0]))
        second = await c.get(url(seeded.segment_ids[1]))
    assert first.status_code == second.status_code == 404
    assert first.json() == second.json() == {"detail": "not found"}
    assert len(draws.seen) == 1
    marker = storage.depiction_marker_path(sha("CCO"))
    assert marker.is_file() and marker.read_bytes() == b""
    assert not storage.depiction_path(sha("CCO")).exists()


async def test_depiction_smiles_over_2000_404_no_draw(app, async_db_session, draws):
    db = async_db_session
    _, token, seeded = await _owner_paper(db)
    long_ok = "C" * 2000
    await _curate(db, seeded.segment_ids[0], smiles="C" * 2001)
    await _curate(db, seeded.segment_ids[1], smiles=long_ok)
    async with make_client(app, token) as c:
        too_long = await c.get(url(seeded.segment_ids[0]))
        at_limit = await c.get(url(seeded.segment_ids[1]))
    assert too_long.status_code == 404 and too_long.json() == {"detail": "not found"}
    assert at_limit.status_code == 200
    assert [k["smiles"] for _, k, _ in draws.seen] == [long_ok]


async def test_depiction_svg_over_cap_not_stored(app, async_db_session, draws):
    big = "<svg>" + "x" * (512 * 1024) + "</svg>"
    draws.behaviour["CCO"] = lambda s: big
    _, token, seeded = await _owner_paper(async_db_session)
    async with make_client(app, token) as c:
        first = await c.get(url(seeded.segment_ids[0]))
        second = await c.get(url(seeded.segment_ids[0]))
    assert first.status_code == second.status_code == 200
    assert first.content == big.encode()
    assert len(draws.seen) == 2
    assert depiction_files() == []


async def test_depiction_svg_at_cap_is_stored(app, async_db_session, draws):
    exact = "<svg>" + "x" * (512 * 1024 - 11) + "</svg>"
    assert len(exact.encode()) == 512 * 1024
    draws.behaviour["CCO"] = lambda s: exact
    _, token, seeded = await _owner_paper(async_db_session)
    async with make_client(app, token) as c:
        await c.get(url(seeded.segment_ids[0]))
    assert storage.depiction_path(sha("CCO")).read_bytes() == exact.encode()


async def test_depiction_curated_miss_counts_tools_bucket(
    app, async_db_session, draws, monkeypatch
):
    """60 curated misses a minute (the /tools/* limit); prediction misses and hits are free."""
    monkeypatch.setattr(security, "_now", lambda: FIXED_NOW)
    db = async_db_session
    big = "<svg>" + "x" * (512 * 1024) + "</svg>"  # never stored: every request is a miss
    draws.behaviour["CCN"] = lambda s: big
    draws.behaviour["CCO"] = lambda s: big
    owner, token, seeded = await _owner_paper(db)
    curated, predicted = seeded.segment_ids
    stored = (await seed_paper(db, owner)).segment_ids[0]
    await _curate(db, stored, smiles="CCC")
    await _curate(db, curated, smiles="CCN")
    async with make_client(app, token) as c:
        for _ in range(5):  # prediction misses: free
            assert (await c.get(url(predicted))).status_code == 200
        assert (await c.get(url(stored))).status_code == 200  # curated miss 1, now stored
        for _ in range(3):  # cache hits: free
            assert (await c.get(url(stored))).status_code == 200
        for i in range(59):  # curated misses 2..60
            assert (await c.get(url(curated))).status_code == 200, i
        drawn = len(draws.seen)
        over = await c.get(url(curated))
        assert over.status_code == 429 and over.headers["retry-after"] == "30"
        assert len(draws.seen) == drawn  # refused before the tool call
        assert (await c.get(url(stored))).status_code == 200  # hit
        assert (await c.get(url(predicted))).status_code == 200  # prediction miss
        assert (await c.get(url(curated, "?engine=decimer"))).status_code == 200
    assert len(draws.seen) == drawn + 2
