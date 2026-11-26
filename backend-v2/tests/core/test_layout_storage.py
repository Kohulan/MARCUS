"""The paper layout (MolScribe's atom positions as a molfile, marcus.core.paper_layout) is stored
with the prediction and in the OCSR cache: migration 0024, the result check, the row."""

import pytest
from sqlalchemy import inspect, select

from alembic import command
from marcus.core.models import Prediction
from marcus.core.pipeline import BadResult
from tests.conftest import _assert_test_database, alembic_config
from tests.core.test_pipeline import OCSR, SEG_V, SEGS, finish, own, steps, to_processing
from tests.factories import make_paper

LAYOUT = (
    "MARCUS layout fit=0.50 bond=40.0 size=100x100\n\n\n"
    "  0  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n"
)


def _ocsr_steps(s):
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    return own(paper, finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V}))


def test_ocsr_result_stores_the_layout(db_session):
    """A layout comes with the result and is stored with the prediction; without one (every
    other engine, an empty one) the column is NULL. The R-group labels still come from the
    SMILES and the engine's own molfile, never from the layout."""
    s = db_session
    ocsr1, ocsr2 = _ocsr_steps(s)
    finish(s, ocsr1, {**OCSR, "layout": LAYOUT})
    finish(s, ocsr2, {**OCSR, "layout": ""})
    got = {p.segment_id: (p.layout, p.rgroups) for p in s.execute(select(Prediction)).scalars()}
    assert got == {ocsr1.segment_id: (LAYOUT, []), ocsr2.segment_id: (None, [])}


def test_ocsr_result_without_a_layout_key_is_taken(db_session):
    """A worker from before the layout sends no key."""
    s = db_session
    ocsr1, _ = _ocsr_steps(s)
    finish(s, ocsr1, OCSR)
    assert s.execute(select(Prediction.layout)).scalar_one() is None


@pytest.mark.parametrize("layout", [5, "a\x00b", "x" * 200_001])
def test_ocsr_result_with_a_bad_layout_is_refused(db_session, layout):
    s = db_session
    ocsr1, _ = _ocsr_steps(s)
    with pytest.raises(BadResult):
        finish(s, ocsr1, {**OCSR, "layout": layout})


def test_migration_0024_layout_columns_up_down(migrated_db):
    """0024 adds the nullable `layout` text column to predictions and ocsr_cache (no backfill);
    the downgrade drops both."""
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        for table in ("predictions", "ocsr_cache"):
            col = {c["name"]: c for c in inspect(engine).get_columns(table)}["layout"]
            assert col["nullable"] and str(col["type"]) == "TEXT"
        command.downgrade(cfg, "0023")
        for table in ("predictions", "ocsr_cache"):
            assert "layout" not in {c["name"] for c in inspect(engine).get_columns(table)}
    finally:
        command.upgrade(cfg, "head")
