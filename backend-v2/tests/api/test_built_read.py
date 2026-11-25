"""Built structures in the paper's read and exports (Markush Phase 3): each a structure with its
compound ID and `built_from`; the scaffold lists the rows that could not be built; built cards
never take a printed compound ID and are never read by an engine."""

import csv
import io
import json

import pytest

from marcus.core import storage
from tests.api.conftest import make_client
from tests.api.test_build_route import scaffold_with_rows
from tests.api.test_compound_ids import document, id_box
from tests.api.test_rgroups import enabled  # noqa: F401 - fixture

pytestmark = pytest.mark.usefixtures("enabled")


async def built_paper(app, db, before_build=None):
    token, paper_id, seg, _ = await scaffold_with_rows(app, db)
    if before_build is not None:
        before_build(paper_id)
    async with make_client(app, token) as c:
        before = (await c.get(f"/api/v2/papers/{paper_id}")).json()
        r = await c.post(f"/api/v2/segments/{seg}/build")
        assert r.status_code == 200, r.text
        after = (await c.get(f"/api/v2/papers/{paper_id}")).json()
    return token, paper_id, str(seg), before, after


async def test_built_cards_carry_built_from_and_their_compound_id(app, async_db_session):
    _, _, seg, _, paper = await built_paper(app, async_db_session)
    built = [s for s in paper["segments"] if s["built_from"]]
    assert {s["compound_id"] for s in built} == {"3a", "3b"}
    for s in built:
        assert s["built_from"] == seg and s["agree"] is None and s["candidate"] is False
        shown = {p["id"]: p["engine"] for p in s["predictions"]}
        assert shown[s["default_prediction_id"]] == "enumerated"
    (scaffold,) = [s for s in paper["segments"] if s["id"] == seg]
    assert scaffold["build_failures"] == [{"compound": "3c", "reason": 'unknown substituent "Tig"'}]
    others = [s for s in paper["segments"] if s["id"] != seg and not s["built_from"]]
    assert others and all(s["build_failures"] is None for s in others)


async def test_built_cards_count_as_structures(app, async_db_session):
    _, _, _, before, after = await built_paper(app, async_db_session)
    assert after["structures"] == before["structures"] + 2


async def test_a_built_card_never_takes_the_id_printed_under_its_scaffold(app, async_db_session):
    def write_ids(paper_id):
        doc = document([id_box("13", 0, 15, 1)])  # under the scaffold crop [0, 0, 10, 10]
        storage.text_path(paper_id).write_text(json.dumps(doc))

    _, _, seg, _, paper = await built_paper(app, async_db_session, write_ids)
    by_id = {s["id"]: s for s in paper["segments"]}
    assert by_id[seg]["compound_id"] == "13"
    assert {s["compound_id"] for s in paper["segments"] if s["built_from"]} == {"3a", "3b"}
    assert all(s["same_id_pages"] == [] for s in paper["segments"])


async def test_predictions_and_read_routes_are_409_for_a_built_card(app, async_db_session):
    token, _, _, _, paper = await built_paper(app, async_db_session)
    built = next(s["id"] for s in paper["segments"] if s["built_from"])
    async with make_client(app, token) as c:
        run = await c.post(f"/api/v2/segments/{built}/predictions", json={"engine": "molscribe"})
        read = await c.post(f"/api/v2/segments/{built}/read")
    assert run.status_code == 409 and run.json() == {"detail": "built"}
    assert read.status_code == 409 and read.json() == {"detail": "built"}


async def test_export_marks_built_records(app, async_db_session):
    token, paper_id, seg, _, _ = await built_paper(app, async_db_session)
    async with make_client(app, token) as c:
        js = (await c.get(f"/api/v2/papers/{paper_id}/export?format=json")).json()
        cs = (await c.get(f"/api/v2/papers/{paper_id}/export?format=csv")).text
        sdf = (await c.get(f"/api/v2/papers/{paper_id}/export?format=sdf&status=all")).text
    built = [r for r in js["segments"] if r.get("built_from")]
    assert len(built) == 2
    for r in built:
        assert (r["source"], r["engine"], r["built_from"]) == ("enumerated", "enumerated", seg)
    header = next(csv.reader(io.StringIO(cs)))
    assert header[-1] == "built_from"
    assert "MARCUS_BUILT_FROM" in sdf
