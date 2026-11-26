""" "All pages or pick a structure" (owner decision 2026-11-25; marcus.core.pipeline): a paper in
mode `ask` renders its pages and reads its text but is not segmented until the user chooses;
in mode `pick` a page is segmented and a box read only when the user asks."""

import pytest
from sqlalchemy import select

from marcus.core.enums import Engine
from marcus.core.models import BackgroundStep, Paper, Segment, Step
from marcus.core.picks import candidate_clause
from marcus.core.pipeline import (
    MANUAL_PAGE_RETRIES,
    ModeNotAllowed,
    RetryNotAllowed,
    choose_mode,
    read_segment,
    segment_page_on_request,
)
from tests.core.test_caches import (
    OCSR,
    done_first_paper,
    drive,
    finish,
    segment_result,
    segments_of,
    steps,
)
from tests.factories import make_owner, make_paper

pytestmark = pytest.mark.usefixtures("seg_version")  # the cache tests' segmenter version


def asked(s, pages=2, owner=None) -> Paper:
    """A paper uploaded from the web UI (mode ask), with every pending step run."""
    paper = make_paper(s, owner, ocsr_mode="ask")
    drive(s, paper, pages=pages)
    s.refresh(paper)
    return paper


def picked(s, pages=2, owner=None) -> Paper:
    paper = asked(s, pages, owner)
    choose_mode(s, paper.id, "pick")
    s.refresh(paper)
    return paper


def segment(s, paper, page, per_page=2):
    step = segment_page_on_request(s, paper.id, page)
    assert step is not None
    finish(s, step, segment_result(paper, page, per_page))
    return [seg for seg in segments_of(s, paper) if seg.page == page]


def ocsr_steps(s, segment_id) -> list[Step]:
    return list(
        s.execute(select(Step).where(Step.segment_id == segment_id, Step.kind == "ocsr")).scalars()
    )


def test_ask_paper_renders_and_reads_text_but_does_not_segment(db_session):
    s = db_session
    paper = asked(s)
    assert len(steps(s, paper, "render_page", "done")) == 2
    assert steps(s, paper, "docling", "done") and steps(s, paper, "doi", "done")
    assert steps(s, paper, "segment_page") == []
    assert segments_of(s, paper) == []


def test_ask_paper_is_done_after_pages_and_text(db_session):
    """A paper waiting for the choice frees its active-paper slot."""
    assert asked(db_session).status == "done"


def test_choose_auto_from_ask_segments_every_rendered_page(db_session):
    s = db_session
    paper = asked(s)
    new = choose_mode(s, paper.id, "auto")
    s.refresh(paper)
    assert paper.ocsr_mode == "auto" and paper.status == "processing"
    assert sorted((st.kind, st.page) for st in new) == [("segment_page", 0), ("segment_page", 1)]
    drive(s, paper)
    for seg in segments_of(s, paper):
        assert {st.engine for st in ocsr_steps(s, seg.id)} == {"decimer", "molparser", "molscribe"}
    s.refresh(paper)
    assert paper.status == "done"


def test_choose_pick_then_segment_one_page(db_session):
    s = db_session
    paper = picked(s)
    assert paper.ocsr_mode == "pick"
    segs = segment(s, paper, 1)
    assert len(segs) == 2
    assert [st.page for st in steps(s, paper, "segment_page")] == [1]
    assert all(ocsr_steps(s, seg.id) == [] for seg in segs)  # candidates: nothing read


def test_read_segment_creates_three_engines(db_session):
    s = db_session
    paper = picked(s)
    seg = segment(s, paper, 0)[0]
    new = read_segment(s, seg.id)
    assert {st.engine for st in new} == {"decimer", "molparser", "molscribe"}
    background = set(s.execute(select(BackgroundStep.step_id)).scalars())
    assert {st.engine for st in new if st.id not in background} == {Engine.DECIMER.value}
    s.refresh(paper)
    assert paper.status == "processing"


def test_read_segment_twice_same_steps(db_session):
    s = db_session
    paper = picked(s)
    seg = segment(s, paper, 0)[0]
    first = read_segment(s, seg.id)
    assert {st.id for st in read_segment(s, seg.id)} == {st.id for st in first}
    drive(s, paper)
    assert {st.id for st in read_segment(s, seg.id)} == {st.id for st in first}  # done too
    assert len(ocsr_steps(s, seg.id)) == 3


def test_choose_auto_after_picks_reads_each_segment_once(db_session):
    s = db_session
    paper = picked(s)
    a, b = segment(s, paper, 0)
    read_segment(s, a.id)
    drive(s, paper)
    new = choose_mode(s, paper.id, "auto")
    assert sorted((st.kind, st.segment_id == b.id, st.page) for st in new) == [
        ("ocsr", True, 0), ("ocsr", True, 0), ("ocsr", True, 0), ("segment_page", False, 1),
    ]  # fmt: skip
    drive(s, paper)
    assert len(ocsr_steps(s, a.id)) == 3 and len(ocsr_steps(s, b.id)) == 3
    assert all(len(ocsr_steps(s, seg.id)) == 3 for seg in segments_of(s, paper))


def test_segment_page_twice_returns_the_waiting_step(db_session):
    s = db_session
    paper = picked(s)
    first = segment_page_on_request(s, paper.id, 0)
    assert segment_page_on_request(s, paper.id, 0).id == first.id
    finish(s, first, segment_result(paper, 0))
    assert segment_page_on_request(s, paper.id, 0) is None  # its boxes are there


def test_segment_page_before_render_is_refused(db_session):
    s = db_session
    paper = make_paper(s, ocsr_mode="ask")
    (check,) = steps(s, paper, "check_pdf")
    finish(s, check, {"pages": 2})
    choose_mode(s, paper.id, "pick")
    with pytest.raises(RetryNotAllowed) as exc:
        segment_page_on_request(s, paper.id, 0)
    assert exc.value.reason == "not_rendered"


def test_segment_page_failed_retries_within_limit(db_session):
    s = db_session
    paper = picked(s)
    from marcus.core.enums import ErrorClass
    from marcus.core.pipeline import fail_step

    def fail(step):
        step.status, step.attempts = "running", 2
        s.flush()
        fail_step(s, step.id, ErrorClass.ENGINE_ERROR, "boom", retryable=True)

    fail(segment_page_on_request(s, paper.id, 0))
    for _ in range(MANUAL_PAGE_RETRIES):
        fail(segment_page_on_request(s, paper.id, 0))
    with pytest.raises(RetryNotAllowed) as exc:
        segment_page_on_request(s, paper.id, 0)
    assert exc.value.reason == "limit"


def test_segment_page_uses_the_cache(db_session):
    s = db_session
    owner = make_owner(s)
    done_first_paper(s, owner)
    paper = picked(s, owner=owner)
    assert segment_page_on_request(s, paper.id, 1) is None
    segs = [seg for seg in segments_of(s, paper) if seg.page == 1]
    assert len(segs) == 2 and all(ocsr_steps(s, seg.id) == [] for seg in segs)
    assert steps(s, paper, "segment_page") == []


@pytest.mark.parametrize("start, mode", [("off", "pick"), ("ask", "ask"), ("pick", "pick")])
def test_wrong_transitions_raise(db_session, start, mode):
    s = db_session
    paper = picked(s) if start == "pick" else make_paper(s, ocsr_mode=start)
    with pytest.raises(ModeNotAllowed):
        choose_mode(s, paper.id, mode)


def test_pick_requests_on_an_auto_paper_raise(db_session):
    s = db_session
    paper = make_paper(s)
    drive(s, paper)
    with pytest.raises(ModeNotAllowed):
        segment_page_on_request(s, paper.id, 0)
    with pytest.raises(ModeNotAllowed):
        read_segment(s, segments_of(s, paper)[0].id)


def test_old_auto_papers_unchanged(db_session):
    s = db_session
    paper = make_paper(s)
    ran = drive(s, paper)
    assert ran.count("segment_page") == 2 and ran.count("ocsr") == 12


# --- Back to pick after "Read all pages" (owner, 2026-11-26) -----------------------------------


def reading(s, pages=2) -> Paper:
    """An auto paper mid-read: page 0 segmented (its OCSR steps waiting), page 1 waiting."""
    paper = asked(s, pages)
    choose_mode(s, paper.id, "auto")
    first = [st for st in steps(s, paper, "segment_page") if st.page == 0][0]
    finish(s, first, segment_result(paper, 0))
    s.refresh(paper)
    return paper


def candidates(s, paper) -> set:
    return set(
        s.execute(
            select(Segment.id).where(Segment.paper_id == paper.id, candidate_clause())
        ).scalars()
    )


def test_auto_to_pick_stops_waiting_work_and_keeps_what_was_read(db_session):
    s = db_session
    paper = reading(s)
    a, b = segments_of(s, paper)
    finish(s, ocsr_steps(s, a.id)[0], OCSR)  # a: one engine done, two waiting
    waiting_page = [st for st in steps(s, paper, "segment_page") if st.page == 1][0]

    choose_mode(s, paper.id, "pick")
    s.refresh(paper)

    assert paper.ocsr_mode == "pick"
    s.refresh(waiting_page)
    assert waiting_page.status == "cancelled"
    assert {st.status for st in ocsr_steps(s, b.id)} == {"cancelled"}
    assert "cancelled" not in {st.status for st in ocsr_steps(s, a.id)}  # started: it finishes
    assert candidates(s, paper) == {b.id}
    new = read_segment(s, b.id)
    assert len(new) == 3 and {st.status for st in new} == {"pending"}
    again = segment_page_on_request(s, paper.id, 1)
    assert again is not None and again.id != waiting_page.id


def test_auto_to_pick_with_nothing_started_closes_the_paper(db_session):
    s = db_session
    paper = reading(s)
    choose_mode(s, paper.id, "pick")
    s.refresh(paper)
    assert paper.status == "done"
    assert candidates(s, paper) == {seg.id for seg in segments_of(s, paper)}


def test_auto_pick_auto_round_trip_reads_everything(db_session):
    s = db_session
    paper = reading(s)
    choose_mode(s, paper.id, "pick")
    new = choose_mode(s, paper.id, "auto")
    assert ("segment_page", 1) in {(st.kind, st.page) for st in new}
    assert sum(st.kind == "ocsr" for st in new) == 6  # both page-0 boxes, three engines each
    drive(s, paper)
    s.refresh(paper)
    assert paper.status == "done"
    assert candidates(s, paper) == set()
