"""Built structures (Markush Phase 3) stay out of OCSR, pick-mode candidates, the segmentation
cache and R-group reading."""

import pytest
from sqlalchemy import select

from marcus.core.built import IsBuilt
from marcus.core.models import Prediction, SegCache, Segment, Step
from marcus.core.picks import candidate_clause
from marcus.core.pipeline import (
    RgroupsNotAllowed,
    choose_mode,
    read_segment,
    request_ocsr,
    request_rgroups,
)
from tests.core.test_built import make_built
from tests.core.test_caches import (
    finish,
    segment_result,
    steps,
)
from tests.core.test_pick_mode import picked, segment
from tests.factories import make_paper

pytestmark = pytest.mark.usefixtures("seg_version")  # the cache tests' segmenter version

ROWS = {"3a": "Cc1ccccc1", "3b": "CCc1ccccc1"}


def test_a_built_segment_is_never_a_pick_candidate(db_session):
    s = db_session
    paper = picked(s)
    scaffold = segment(s, paper, 0)[0]
    built = make_built(s, scaffold.id, ROWS)
    candidates = set(s.execute(select(Segment.id).where(
        Segment.paper_id == paper.id, candidate_clause())).scalars())  # fmt: skip
    assert scaffold.id in candidates
    assert not candidates & {b.id for b in built}


def test_read_all_pages_never_reads_a_built_segment(db_session):
    s = db_session
    paper = picked(s)
    scaffold = segment(s, paper, 0)[0]
    built = {b.id for b in make_built(s, scaffold.id, ROWS)}
    choose_mode(s, paper.id, "auto")
    read = set(s.execute(select(Step.segment_id).where(Step.kind == "ocsr")).scalars())
    assert scaffold.id in read and not read & built


def test_request_ocsr_and_read_segment_refuse_a_built_segment(db_session):
    s = db_session
    paper = picked(s)
    scaffold = segment(s, paper, 0)[0]
    (b, _) = make_built(s, scaffold.id, ROWS)
    before = s.execute(select(Step.id)).all()
    with pytest.raises(IsBuilt):
        request_ocsr(s, b.id, "molscribe")
    with pytest.raises(IsBuilt):
        read_segment(s, b.id)
    assert s.execute(select(Step.id)).all() == before


def test_built_segments_never_enter_the_seg_cache(db_session):
    s = db_session
    paper = make_paper(s)
    (check,) = steps(s, paper, "check_pdf")
    finish(s, check, {"pages": 2})
    renders = steps(s, paper, "render_page")
    (seg0,) = finish(s, renders[0], {})
    finish(s, seg0, segment_result(paper, 0))
    scaffold = s.execute(select(Segment).where(Segment.paper_id == paper.id)).scalars().first()
    make_built(s, scaffold.id, ROWS)
    (seg1,) = finish(s, renders[1], {})
    finish(s, seg1, segment_result(paper, 1))
    (row,) = s.execute(select(SegCache)).scalars()
    idx = [item["idx"] for item in row.payload["segments"]]
    assert idx and max(idx) < 1000


def test_rgroups_are_never_asked_for_a_built_prediction(db_session):
    s = db_session
    paper = picked(s)
    scaffold = segment(s, paper, 0)[0]
    (b, _) = make_built(s, scaffold.id, ROWS)
    pred = s.execute(select(Prediction).where(Prediction.segment_id == b.id)).scalar_one()
    with pytest.raises(RgroupsNotAllowed):
        request_rgroups(s, pred.id)
