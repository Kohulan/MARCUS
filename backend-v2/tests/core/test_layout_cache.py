"""The OCSR cache and the paper layout (marcus.workers.ocsr.handler): a MolScribe row from before
the layout is read once more and then holds it; '' = tried, none; the fit is not in `ms`."""

import time

import pytest
from sqlalchemy import select

from marcus.core import storage
from marcus.core.enums import Engine
from marcus.core.models import OcsrCache
from marcus.workers.ocsr import handler
from marcus.workers.ocsr.base import OcsrResult
from tests.core.test_caches import _job_image, _run_ocsr, _sha
from tests.factories import make_owner

GRAPH = {
    "atoms": [{"atom_symbol": "C", "x": 0.0, "y": 0.0}, {"atom_symbol": "O", "x": 1.0, "y": 1.0}],
    "bonds": [{"bond_type": "single", "endpoint_atoms": [0, 1]}],
}


class GraphEngine:
    """MolScribe's stand-in: a SMILES, a molfile and (optionally) the raw graph."""

    name = Engine.MOLSCRIBE
    version = "stub-9"

    def __init__(self, graph=GRAPH, smiles="CO"):
        self.graph = graph
        self.smiles = smiles
        self.calls = 0

    def load(self):
        pass

    def predict(self, image):
        self.calls += 1
        return OcsrResult(self.smiles, "MOLFILE", self.graph)


@pytest.fixture
def molscribe(monkeypatch):
    from marcus.workers.ocsr import base

    monkeypatch.setattr(base, "_ENGINES", {})
    seen = []

    def fake_layout(image, atoms, bonds):
        seen.append((image.is_file(), atoms, bonds))
        return "LAYOUT"

    monkeypatch.setattr(handler, "layout_molfile", fake_layout)

    def use(engine):
        base._ENGINES.clear()
        monkeypatch.setitem(base.FACTORIES, "molscribe", lambda: engine)
        engine.seen = seen
        return engine

    return use


def _rows(s):
    s.expire_all()
    return list(s.execute(select(OcsrCache)).scalars())


def test_a_molscribe_read_returns_and_caches_the_layout(db_session, molscribe):
    owner = make_owner(db_session)
    eng = molscribe(GraphEngine())
    out = _run_ocsr(_job_image(db_session, owner), "molscribe")
    assert out["layout"] == "LAYOUT" and out["cached"] is False
    # built from the file the engine read and the graph it returned
    assert eng.seen == [(True, GRAPH["atoms"], GRAPH["bonds"])]
    (row,) = _rows(db_session)
    assert (row.smiles, row.molfile, row.layout) == ("CO", "MOLFILE", "LAYOUT")

    eng2 = molscribe(GraphEngine())
    hit = _run_ocsr(_job_image(db_session, owner), "molscribe")
    assert eng2.calls == 0
    assert hit == {
        "smiles": "CO",
        "molfile": "MOLFILE",
        "valid": True,
        "ms": 0,
        "cached": True,
        "engine_version": "stub-9",
        "layout": "LAYOUT",
    }


def test_a_row_from_before_the_layout_is_read_once_more(db_session, molscribe):
    """NULL = never tried: the engine reads again, the row gets the layout (its SMILES and
    molfile stay), and the next request is a hit."""
    owner = make_owner(db_session)
    job = _job_image(db_session, owner)
    sha = _sha(storage.image_job_path(job).read_bytes())
    db_session.add(
        OcsrCache(owner_id=owner.id, image_sha256=sha, engine="molscribe",
                  engine_version="stub-9", smiles="CCO", molfile="OLD", layout=None)
    )  # fmt: skip
    db_session.commit()
    eng = molscribe(GraphEngine())
    out = _run_ocsr(job, "molscribe")
    assert eng.calls == 1 and out["cached"] is False and out["layout"] == "LAYOUT"
    (row,) = _rows(db_session)
    assert (row.smiles, row.molfile, row.layout) == ("CCO", "OLD", "LAYOUT")
    eng2 = molscribe(GraphEngine())
    assert _run_ocsr(job, "molscribe")["cached"] is True and eng2.calls == 0


def test_no_layout_is_remembered_as_tried(db_session, molscribe, monkeypatch):
    """'' = tried, none: a hit (no second read), and the reply's layout is null."""
    monkeypatch.setattr(handler, "layout_molfile", lambda *a: None)
    owner = make_owner(db_session)
    molscribe(GraphEngine())
    first = _run_ocsr(_job_image(db_session, owner), "molscribe")
    assert first["layout"] is None
    assert [r.layout for r in _rows(db_session)] == [""]
    eng = molscribe(GraphEngine())
    hit = _run_ocsr(_job_image(db_session, owner), "molscribe")
    assert eng.calls == 0 and hit["cached"] is True and hit["layout"] is None


def test_an_engine_without_a_graph_is_tried_none(db_session, molscribe):
    owner = make_owner(db_session)
    eng = molscribe(GraphEngine(graph=None))
    out = _run_ocsr(_job_image(db_session, owner), "molscribe")
    assert out["layout"] is None and eng.seen == []
    assert [r.layout for r in _rows(db_session)] == [""]


def test_a_failed_fit_is_not_remembered(db_session, molscribe, monkeypatch):
    """A fit that raised leaves NULL (never tried): the prediction stands, the next read tries
    again."""

    def boom(*a):
        raise RuntimeError("no cv2")

    monkeypatch.setattr(handler, "layout_molfile", boom)
    owner = make_owner(db_session)
    molscribe(GraphEngine())
    out = _run_ocsr(_job_image(db_session, owner), "molscribe")
    assert out["smiles"] == "CO" and out["layout"] is None
    assert [r.layout for r in _rows(db_session)] == [None]
    eng = molscribe(GraphEngine())
    _run_ocsr(_job_image(db_session, owner), "molscribe")
    assert eng.calls == 1


def test_the_fit_is_not_in_the_engine_time(db_session, molscribe, monkeypatch):
    def slow(*a):
        time.sleep(0.3)
        return "LAYOUT"

    monkeypatch.setattr(handler, "layout_molfile", slow)
    molscribe(GraphEngine())
    out = _run_ocsr(_job_image(db_session, make_owner(db_session)), "molscribe")
    assert out["layout"] == "LAYOUT" and out["ms"] < 200


def test_other_engines_have_no_layout_key_and_old_rows_still_hit(db_session, monkeypatch):
    """DECIMER and MolParser read no positions: no `layout` in the reply, and a row with NULL
    is a hit as before."""
    from marcus.workers.ocsr import base
    from tests.core.test_caches import CountingEngine

    monkeypatch.setattr(base, "_ENGINES", {})
    eng = CountingEngine("CCO")
    monkeypatch.setitem(base.FACTORIES, "decimer", lambda: eng)
    owner = make_owner(db_session)
    first = _run_ocsr(_job_image(db_session, owner))
    second = _run_ocsr(_job_image(db_session, owner))
    assert "layout" not in first and "layout" not in second
    assert eng.calls == 1 and second["cached"] is True
    assert [r.layout for r in _rows(db_session)] == [None]
