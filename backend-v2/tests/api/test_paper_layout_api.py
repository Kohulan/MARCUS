"""The paper layout in the API: MolScribe's layout is the first orientation template (valid or
not), every prediction says its layout, `/tools/depict` takes marks, and
`GET /segments/{id}/overlay` gives the answers on the paper."""

import uuid

import pytest
from sqlalchemy import delete

from marcus.api import depiction, security
from marcus.api import tooling as tools_route
from marcus.core import paper_layout
from marcus.core.models import Prediction
from tests.api.conftest import make_client, new_owner, seed_paper
from tests.api.test_depiction import NEXTR_MOLFILE, SCRIBE_MOLFILE, draws, svg_for  # noqa: F401

LAYOUT = paper_layout.header(0.5, 40.0, 300, 200) + "\n  layout molfile"
POOR = paper_layout.header(1.7, 40.0, 300, 200) + "\n  layout molfile"  # 4.25 % of a bond
FIXED_NOW = 1_800_000_030.0


async def _predict(db, seg, engine, smiles, valid=True, molfile=None, layout=None, rgroups=None):
    p = Prediction(
        id=uuid.uuid4(), segment_id=seg, engine=engine, engine_version="t1", smiles=smiles,
        molfile=molfile, valid=valid, ms=1, layout=layout, rgroups=rgroups,
    )  # fmt: skip
    db.add(p)
    await db.commit()
    return p.id


async def _segment(db, ocsr=True):
    owner, token = await new_owner(db)
    seeded = await seed_paper(db, owner, ocsr=ocsr)
    return owner, token, seeded.segment_ids[0], seeded


def dep(seg, query: str = "") -> str:
    return f"/api/v2/segments/{seg}/depiction{query}"


# --- the template rule ----------------------------------------------------------------------


async def test_the_layout_is_the_first_template_also_of_an_invalid_molscribe(
    app,
    async_db_session,
    draws,  # noqa: F811
):
    """MolScribe's answer is invalid (no template until now): its layout still draws every
    answer of the segment in the paper's layout. Then today's candidates."""
    db = async_db_session
    _, token, seg, _ = await _segment(db)
    await _predict(db, seg, "molnextr", "CCN", molfile=NEXTR_MOLFILE)
    await _predict(db, seg, "molscribe", "C(C)(C)(C)(C)C", valid=False, molfile="computed",
                   layout=LAYOUT)  # fmt: skip
    async with make_client(app, token) as c:
        assert (await c.get(dep(seg))).status_code == 200
        assert (await c.get(dep(seg, "?engine=molnextr"))).status_code == 200
    assert [k["template"] for _, k, _ in draws.seen] == [[LAYOUT, NEXTR_MOLFILE]] * 2


async def test_the_layout_comes_before_a_valid_molscribe_molfile(
    app,
    async_db_session,
    draws,  # noqa: F811
):
    db = async_db_session
    _, token, seg, _ = await _segment(db)
    await _predict(db, seg, "molscribe", "CCC", molfile=SCRIBE_MOLFILE, layout=LAYOUT)
    async with make_client(app, token) as c:
        assert (await c.get(dep(seg))).status_code == 200
    assert draws.seen[0][1]["template"] == [LAYOUT, SCRIBE_MOLFILE]


async def test_the_newest_molscribe_layout_is_used_and_no_other_engines(
    app,
    async_db_session,
    draws,  # noqa: F811
):
    """A re-read without a layout does not hide the older one; a layout on another engine's
    row (there is none in practice) is never a template."""
    db = async_db_session
    _, token, seg, _ = await _segment(db)
    await _predict(db, seg, "molscribe", "CCC", valid=False, layout=LAYOUT)
    await _predict(db, seg, "molscribe", "CCC", valid=False, layout=None)
    await _predict(db, seg, "molparser", "CCC", layout="MARCUS layout of another engine")
    async with make_client(app, token) as c:
        assert (await c.get(dep(seg))).status_code == 200
    assert draws.seen[0][1]["template"] == [LAYOUT]


async def test_a_prediction_says_its_layout(app, async_db_session):
    db = async_db_session
    _, token, seg, seeded = await _segment(db)
    await _predict(db, seg, "molscribe", "CCC", valid=False, layout=LAYOUT)
    async with make_client(app, token) as c:
        r = await c.get(f"/api/v2/papers/{seeded.paper_id}/segments")
    preds = next(s for s in r.json()["segments"] if s["id"] == str(seg))["predictions"]
    assert {p["layout"] for p in preds if p["engine"] == "molscribe"} == {LAYOUT, None}
    assert all(p["layout"] is None for p in preds if p["engine"] != "molscribe")


# --- /tools/depict marks --------------------------------------------------------------------


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake(name, kwargs, timeout):
        seen.append((name, kwargs, timeout))
        return "<svg/>"

    monkeypatch.setattr(tools_route, "run_tool", fake)
    return seen


async def test_depict_sends_marks_only_when_there_are_some(app, calls):
    """A tools worker from before the marks never gets the argument for a plain drawing."""
    async with make_client(app) as c:
        marked = await c.post("/api/v2/tools/depict", json={"smiles": "CCO", "marks": [2, 0]})
        empty = await c.post("/api/v2/tools/depict", json={"smiles": "CCO", "marks": []})
        plain = await c.post("/api/v2/tools/depict", json={"smiles": "CCO"})
    assert marked.status_code == empty.status_code == plain.status_code == 200
    assert calls[0][1]["marks"] == [2, 0]
    assert "marks" not in calls[1][1] and "marks" not in calls[2][1]


@pytest.mark.parametrize("marks", [[-1], [0, 0], list(range(251)), [1.5], ["1"], "12", [2000]])
async def test_depict_refuses_bad_marks(app, calls, marks):
    async with make_client(app) as c:
        r = await c.post("/api/v2/tools/depict", json={"smiles": "CCO", "marks": marks})
    assert r.status_code == 422 and calls == []


# --- the overlay ----------------------------------------------------------------------------


def over(seg) -> str:
    return f"/api/v2/segments/{seg}/overlay"


@pytest.fixture
def view(monkeypatch):
    """Fake tools worker for marcus.tools.paper_view: one answer per SMILES, the third None."""
    seen = []

    def fake(name, kwargs, timeout):
        seen.append((name, kwargs, timeout))
        answers = [
            None if s == "[R1]C" else {"marks": [0], "atoms": [[1.0, 2.0, "C", True]], "bonds": []}
            for s in kwargs["smiles"]
        ]
        return {"fit": 0.5, "bond": 40.0, "width": 300, "height": 200, "overlay": True,
                "complete": True, "answers": answers}  # fmt: skip

    monkeypatch.setattr(tools_route, "run_tool", fake)
    return seen


async def test_overlay_gives_each_engines_newest_drawable_answer_on_the_layout(
    app, async_db_session, view
):
    db = async_db_session
    _, token, seg, _ = await _segment(db, ocsr=False)
    await _predict(db, seg, "decimer", "CCO")
    old = await _predict(db, seg, "molparser", "CCC")
    new = await _predict(db, seg, "molparser", "CCN")
    await _predict(db, seg, "molscribe", "C(C)(C)(C)(C)C", valid=False, layout=LAYOUT)
    rg = await _predict(db, seg, "decimer-hand", "[R1]C", valid=False, rgroups=["R1"])
    async with make_client(app, token) as c:
        r = await c.get(over(seg))
    assert r.status_code == 200, r.text
    ((name, kwargs, _),) = view
    assert name == "marcus.tools.paper_view" and kwargs["layout"] == LAYOUT
    assert sorted(kwargs["smiles"]) == ["CCN", "CCO", "[R1]C"]  # not the invalid MolScribe
    body = r.json()
    assert {k: body[k] for k in ("fit", "bond", "width", "height", "complete")} == {
        "fit": 0.5, "bond": 40.0, "width": 300, "height": 200, "complete": True,
    }  # fmt: skip
    got = {a["engine"]: a for a in body["answers"]}
    assert set(got) == {"decimer", "molparser"}  # the R-group scaffold cannot be placed
    assert got["molparser"]["prediction_id"] == str(new) != str(old)
    assert got["molparser"]["marks"] == [0]
    assert got["molparser"]["atoms"] == [[1.0, 2.0, "C", True]] and got["molparser"]["bonds"] == []
    assert str(rg) not in {a["prediction_id"] for a in body["answers"]}
    assert r.headers["cache-control"] == "private, no-store"


async def test_overlay_409_without_a_layout_and_with_a_poor_fit(app, async_db_session, view):
    """No overlay that does not sit on the ink: said, and the tools worker is not asked."""
    db = async_db_session
    _, token, seg, seeded = await _segment(db)
    other = seeded.segment_ids[1]
    await _predict(db, seg, "molscribe", "CCC", molfile=SCRIBE_MOLFILE)  # valid, no layout
    await _predict(db, other, "molscribe", "CCC", valid=False, layout=POOR)
    async with make_client(app, token) as c:
        none = await c.get(over(seg))
        poor = await c.get(over(other))
    assert (none.status_code, none.json()["detail"]) == (409, "no layout")
    assert (poor.status_code, poor.json()["detail"]) == (409, "poor fit")
    assert view == []


async def test_overlay_with_nothing_to_draw_asks_no_tool(app, async_db_session, view):
    db = async_db_session
    _, token, seg, _ = await _segment(db, ocsr=False)
    await _predict(db, seg, "molscribe", "C(C)(C)(C)(C)C", valid=False, layout=LAYOUT)
    async with make_client(app, token) as c:
        r = await c.get(over(seg))
    assert r.status_code == 200 and r.json()["answers"] == [] and view == []


async def test_overlay_is_the_owners_and_counts_as_a_tool_call(
    app, async_db_session, view, monkeypatch
):
    monkeypatch.setattr(security, "_now", lambda: FIXED_NOW)
    db = async_db_session
    _, token, seg, _ = await _segment(db)
    await _predict(db, seg, "molscribe", "CCC", valid=False, layout=LAYOUT)
    _, stranger = await new_owner(db)
    async with make_client(app, stranger) as c:
        assert (await c.get(over(seg))).status_code == 404
        assert (await c.get(over(uuid.uuid4()))).status_code == 404
    async with make_client(app, token) as c:
        for i in range(60):
            assert (await c.get(over(seg))).status_code == 200, i
        assert (await c.get(over(seg))).status_code == 429
    assert len(view) == 60


async def test_overlay_tool_errors_are_the_tools_errors(app, async_db_session, monkeypatch):
    from fastapi import HTTPException

    def fake(name, kwargs, timeout):
        raise HTTPException(status_code=504, detail="tool timed out")

    monkeypatch.setattr(tools_route, "run_tool", fake)
    db = async_db_session
    _, token, seg, _ = await _segment(db)
    await _predict(db, seg, "molscribe", "CCC", valid=False, layout=LAYOUT)
    async with make_client(app, token) as c:
        assert (await c.get(over(seg))).status_code == 504


async def test_overlay_of_a_segment_whose_predictions_are_gone(app, async_db_session, view):
    db = async_db_session
    _, token, seg, _ = await _segment(db)
    await db.execute(delete(Prediction).where(Prediction.segment_id == seg))
    await db.commit()
    async with make_client(app, token) as c:
        assert (await c.get(over(seg))).status_code == 409


def test_the_export_and_the_rgroup_labels_never_read_the_layout():
    """The layout is a reading aid: only the drawings use it (binding review finding)."""
    import inspect

    from marcus.api import export
    from marcus.core import pipeline, rgroups

    assert "layout" not in inspect.getsource(export)
    assert "layout" not in inspect.getsource(rgroups)
    source = inspect.getsource(pipeline._prediction)
    assert 'rgroup_labels(result["smiles"], result.get("molfile"))' in source


def test_depiction_module_names_the_template_order():
    assert depiction.TEMPLATE_ENGINES == ("molscribe", "molnextr")
